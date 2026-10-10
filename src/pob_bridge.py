from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zlib
from src import build_library, ggg_api

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POB_DIR = PROJECT_ROOT / "data" / "pob"
CURRENT_XML = POB_DIR / "current.xml"
CURRENT_JSON = POB_DIR / "current.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_ENGINE = "http://127.0.0.1:8000"


def _looks_like_xml(text: str) -> bool:
    s = text.lstrip()
    return s.startswith("<?xml") or s.startswith("<PathOfBuilding2")


def _pobb_raw_url(source: str) -> str | None:
    source = source.strip()
    parsed = urlparse(source if "://" in source else "")
    if parsed.scheme:
        host = (parsed.hostname or "").lower()
        if host != "pobb.in" and not host.endswith(".pobb.in"):
            raise ValueError("Por segurança, links remotos aceitos nesta etapa devem ser do pobb.in.")
        url = source.rstrip("/")
        return url if url.endswith("/raw") else url + "/raw"

    if re.fullmatch(r"[A-Za-z0-9_-]{4,80}", source):
        return f"https://pobb.in/{source}/raw"
    return None


def fetch_source(source: str, timeout: int = 25) -> tuple[str, str]:
    """
    Accept:
      - pobb.in URL / bare id
      - local file containing XML or raw PoB code
      - raw XML
      - raw PoB export code
    Returns (payload, source_label).
    """
    source = source.strip()
    if not source:
        raise ValueError("Informe um link pobb.in, código de exportação ou arquivo local.")

    p = Path(source)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8").strip(), str(p.resolve())

    if _looks_like_xml(source):
        return source, "XML colado"

    raw_url = _pobb_raw_url(source)
    if raw_url:
        req = urllib.request.Request(
            raw_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/plain,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read().decode("utf-8", errors="replace").strip()
        except urllib.error.HTTPError as exc:
            raise ValueError(f"pobb.in respondeu HTTP {exc.code}. Confira o link.") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Não foi possível acessar pobb.in: {exc.reason}") from exc
        if not payload or payload.lstrip().startswith("<!DOCTYPE html"):
            raise ValueError("O endpoint /raw não retornou um código PoB válido.")
        return payload, raw_url

    # Treat sufficiently long non-URL strings as export code.
    compact = "".join(source.split())
    if len(compact) >= 100:
        return compact, "Código PoB colado"

    raise ValueError("Formato não reconhecido. Use pobb.in, XML, arquivo local ou código PoB.")


def _is_zlib_wrapped(data: bytes) -> bool:
    if len(data) < 2:
        return False
    cmf, flg = data[0], data[1]
    return (cmf & 0x0F) == 8 and (((cmf << 8) | flg) % 31 == 0)


def decode_payload(payload: str) -> str:
    payload = payload.strip()
    if _looks_like_xml(payload):
        xml = payload
    else:
        standard = "".join(payload.split()).replace("-", "+").replace("_", "/")
        standard += "=" * ((4 - len(standard) % 4) % 4)
        try:
            compressed = base64.b64decode(standard, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("O código PoB não é base64 válido ou foi cortado.") from exc

        primary = 15 if _is_zlib_wrapped(compressed) else -15
        alternate = -15 if primary == 15 else 15
        try:
            raw = zlib.decompress(compressed, wbits=primary)
        except zlib.error:
            try:
                raw = zlib.decompress(compressed, wbits=alternate)
            except zlib.error as exc:
                raise ValueError("Não foi possível descompactar o código PoB.") from exc
        try:
            xml = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("O conteúdo decodificado não é XML UTF-8 válido.") from exc

    xml = xml.strip()
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"XML PoB inválido: {exc}") from exc

    tag = root.tag.split("}")[-1]
    if tag != "PathOfBuilding2":
        if tag == "PathOfBuilding":
            raise ValueError("Esse código é de PoE1. Precisamos de um export do Path of Building PoE2.")
        raise ValueError(f"Raiz XML inesperada: {tag}")
    return xml


def _truth(value: str | None, default=True) -> bool:
    if value is None:
        return default
    return str(value).lower() not in {"false", "0", "no"}


def _find_active_child(container, child_name: str, active_keys: tuple[str, ...]):
    if container is None:
        return None
    children = [x for x in list(container) if x.tag.split("}")[-1] == child_name]
    if not children:
        return None

    active_value = None
    for key in active_keys:
        if container.attrib.get(key):
            active_value = container.attrib.get(key)
            break

    if active_value is not None:
        for child in children:
            if child.attrib.get("id") == active_value or child.attrib.get("index") == active_value:
                return child
    return children[0]


def _player_stats(root) -> dict[str, float | str]:
    stats = {}
    for node in root.iter():
        if node.tag.split("}")[-1] != "PlayerStat":
            continue
        name = node.attrib.get("stat")
        value = node.attrib.get("value")
        if not name or value is None:
            continue
        try:
            number = float(value)
            stats[name] = int(number) if number.is_integer() else number
        except ValueError:
            stats[name] = value
    return stats


def _skill_groups(root) -> list[dict]:
    skills_container = next((x for x in root.iter() if x.tag.split("}")[-1] == "Skills"), None)
    skill_set = _find_active_child(
        skills_container, "SkillSet",
        ("activeSkillSet", "activeSkillSetId", "activeSkillSetIndex")
    )
    parent = skill_set if skill_set is not None else skills_container
    if parent is None:
        return []

    groups = []
    for skill in parent.iter():
        if skill.tag.split("}")[-1] != "Skill":
            continue
        if not _truth(skill.attrib.get("enabled"), True):
            continue
        gems = []
        for gem in list(skill):
            if gem.tag.split("}")[-1] != "Gem":
                continue
            if not _truth(gem.attrib.get("enabled"), True):
                continue
            name = (
                gem.attrib.get("nameSpec")
                or gem.attrib.get("name")
                or gem.attrib.get("skillId")
                or gem.attrib.get("gemId")
                or "Gem sem nome"
            )
            gems.append({
                "name": name,
                "level": gem.attrib.get("level"),
                "quality": gem.attrib.get("quality"),
                "skill_id": gem.attrib.get("skillId") or gem.attrib.get("gemId"),
            })
        if not gems:
            continue

        try:
            main_idx = int(skill.attrib.get("mainActiveSkill", "1")) - 1
        except ValueError:
            main_idx = 0
        if not 0 <= main_idx < len(gems):
            main_idx = 0

        groups.append({
            "label": skill.attrib.get("label") or skill.attrib.get("slot") or "",
            "slot": skill.attrib.get("slot") or skill.attrib.get("source") or "",
            "main_index": main_idx,
            "main_gem": gems[main_idx]["name"],
            "gems": gems,
        })
    return groups


def _tree_summary(root) -> dict:
    tree = next((x for x in root.iter() if x.tag.split("}")[-1] == "Tree"), None)
    spec = _find_active_child(tree, "Spec", ("activeSpec", "activeSpecId", "activeSpecIndex"))
    if spec is None:
        spec = next((x for x in root.iter() if x.tag.split("}")[-1] == "Spec"), None)
    if spec is None:
        return {"allocated_nodes": 0, "ascendancy_internal_id": None, "tree_version": None}

    nodes = [x for x in (spec.attrib.get("nodes") or "").split(",") if x.strip()]
    return {
        "allocated_nodes": len(nodes),
        "node_refs": nodes,
        "base_hashes": nodes,
        "specialisations": {},
        "quest_stats": [],
        "ascendancy_internal_id": (
            spec.attrib.get("ascendancyInternalId")
            or spec.attrib.get("ascendClassName")
            or spec.attrib.get("ascendClassId")
        ),
        "tree_version": spec.attrib.get("treeVersion") or spec.attrib.get("version"),
    }


_POB_CONTROL_PREFIX = re.compile(r"^(?:\{(?:variant|range|crafted|implicit|rune|enchant|fractured|custom|tags)[^{}]*\})+", re.I)
_POB_MOD_DESCRIPTOR = re.compile(r'^\{\s*(?:crafted\s+)?(?:prefix|suffix|implicit|rune|enchant|fractured)\s+modifier\b', re.I)


_ITEM_META_PREFIXES = (
    "quality:", "item class:", "item level:", "levelreq:", "level req:", "requires level",
    "armour:", "evasion rating:", "energy shield:", "block chance:",
    "physical damage:", "elemental damage:", "critical hit chance:",
    "attacks per second:", "weapon range:", "spirit:", "charm slots:",
    "sockets:", "limited to:", "radius:", "crafted:", "mirrored:",
    "prefix:", "suffix:", "implicits:", "variant:",
)


def _item_trade_lines(lines: list[str]) -> list[str]:
    """Keep likely affix text while leaving final validation to the live trade stat catalog."""
    out=[]
    for row in lines[3:]:
        value=row.strip()
        if not value or set(value)<=set("- "):
            continue
        # PoB may include human-readable modifier descriptor rows and compact
        # control tags. Descriptor rows are metadata; compact tags can be
        # removed while keeping the rendered modifier text that follows.
        if _POB_MOD_DESCRIPTOR.match(value):
            continue
        value=_POB_CONTROL_PREFIX.sub("",value).strip()
        low=value.casefold()
        if not value or low in {"corrupted", "unidentified", "split", "mirrored", "fractured item"}:
            continue
        if any(low.startswith(prefix) for prefix in _ITEM_META_PREFIXES):
            continue
        out.append(value)
    return out[:24]


def _item_text_info(text: str) -> dict:
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    rarity = ""
    name = ""
    base_type = ""

    if lines and lines[0].lower().startswith("rarity:"):
        rarity = lines[0].split(":", 1)[1].strip().title()
        if len(lines) > 1:
            name = lines[1]
        if len(lines) > 2:
            base_type = lines[2]
    else:
        if lines:
            name = lines[0]
        if len(lines) > 1:
            base_type = lines[1]

    return {
        "rarity": rarity,
        "name": name or base_type or "Item sem nome",
        "base_type": base_type,
        "preview": lines[:18],
        "trade_lines": _item_trade_lines(lines),
        "text": text or "",
    }


def _item_summary(root) -> dict:
    """
    PoB stores Item definitions directly under <Items>.
    The active <ItemSet> normally contains <Slot name="..." itemId="..."> refs.

    v0.9 incorrectly searched for <Item> inside the active ItemSet, producing
    zero equipped items for normal PoB exports.
    """
    items_container = next(
        (x for x in root.iter() if x.tag.split("}")[-1] == "Items"),
        None
    )
    if items_container is None:
        return {
            "count": 0,
            "defined_count": 0,
            "items": [],
            "slots": [],
            "unresolved_slots": [],
        }

    # Current/common PoB keeps definitions directly under <Items>.
    item_nodes = [
        x for x in list(items_container)
        if x.tag.split("}")[-1] == "Item"
    ]

    item_set = _find_active_child(
        items_container,
        "ItemSet",
        ("activeItemSet", "activeItemSetId", "activeItemSetIndex"),
    )

    # Older/alternate exports may nest <Item> directly in <ItemSet>.
    legacy_nested_items = []
    if not item_nodes and item_set is not None:
        legacy_nested_items = [
            x for x in list(item_set)
            if x.tag.split("}")[-1] == "Item"
        ]
        item_nodes = legacy_nested_items

    ordered = []
    by_id = {}
    for index, node in enumerate(item_nodes, 1):
        text = "".join(node.itertext()).strip()
        info = _item_text_info(text)
        record = {
            "id": node.attrib.get("id") or str(index),
            "index": index,
            **info,
        }
        ordered.append(record)
        if node.attrib.get("id"):
            by_id[str(node.attrib["id"])] = record

    slots = []
    unresolved = []
    if item_set is not None:
        for slot in item_set.iter():
            if slot.tag.split("}")[-1] != "Slot":
                continue
            slot_name = slot.attrib.get("name") or slot.attrib.get("slot") or "Unknown"
            item_id = str(slot.attrib.get("itemId") or slot.attrib.get("item") or "0")
            if item_id in {"", "0", "None"}:
                continue

            # Prefer explicit Item@id. Fall back to PoB's common 1-based
            # positional item references.
            item = by_id.get(item_id)
            if item is None:
                try:
                    idx = int(item_id) - 1
                    if 0 <= idx < len(ordered):
                        item = ordered[idx]
                except (TypeError, ValueError):
                    pass

            if item is None:
                unresolved.append({"slot": slot_name, "item_id": item_id})
                continue

            slots.append({
                "slot": slot_name,
                "item_id": item_id,
                "item": item,
            })

    # Older/alternate format: nested Item nodes themselves represent the
    # active set and may not have Slot references.
    if not slots and legacy_nested_items:
        for index, item in enumerate(ordered, 1):
            slots.append({
                "slot": f"Item {index}",
                "item_id": item["id"],
                "item": item,
            })

    # Some exports may not include an ItemSet. Keep all definitions visible,
    # but distinguish "defined" from "equipped".
    visible_items = [x["item"] for x in slots] if slots else ordered

    return {
        "count": len(slots),
        "defined_count": len(ordered),
        "items": visible_items,
        "slots": slots,
        "unresolved_slots": unresolved,
    }



def _config_summary(root) -> dict:
    container = next(
        (x for x in root.iter() if x.tag.split("}")[-1] in {"Config", "Configuration"}),
        None
    )
    if container is None:
        return {"count": 0, "values": {}}

    active = _find_active_child(
        container,
        "ConfigSet",
        ("activeConfigSet", "activeConfigSetId", "activeConfigSetIndex"),
    )
    parent = active if active is not None else container

    values = {}
    # PoB configuration exports have changed shape over time. Preserve common
    # key/value attributes without inventing semantics.
    for node in parent.iter():
        tag = node.tag.split("}")[-1]
        if tag not in {"Input", "ConfigInput", "Setting"}:
            continue
        key = (
            node.attrib.get("name")
            or node.attrib.get("id")
            or node.attrib.get("key")
        )
        if not key:
            continue
        value = (
            node.attrib.get("value")
            or node.attrib.get("number")
            or node.attrib.get("string")
            or node.attrib.get("boolean")
        )
        if value is None and (node.text or "").strip():
            value = (node.text or "").strip()
        values[str(key)] = value

    return {"count": len(values), "values": values}

def parse_build(xml: str, source_label: str = "") -> dict:
    root = ET.fromstring(xml)
    build = next((x for x in root.iter() if x.tag.split("}")[-1] == "Build"), None)
    attrs = build.attrib if build is not None else {}

    stats = _player_stats(root)
    groups = _skill_groups(root)
    tree = _tree_summary(root)
    items = _item_summary(root)
    config = _config_summary(root)

    # Curated set first, but retain all PlayerStats for inspection.
    interesting_order = [
        "FullDPS", "CombinedDPS", "TotalDPS", "WithDotDPS", "TotalDot",
        "AverageDamage", "AverageBurstDamage", "Speed", "HitChance",
        "PreEffectiveCritChance", "CritChance", "CritMultiplier",
        "Life", "EnergyShield", "Mana", "Armour", "Evasion",
        "EffectiveHitPool", "EHP",
        "FireResist", "ColdResist", "LightningResist", "ChaosResist",
        "Str", "Dex", "Int",
    ]
    curated = {key: stats[key] for key in interesting_order if key in stats}

    main_socket = attrs.get("mainSocketGroup") or attrs.get("mainSkillIndex")
    try:
        main_socket_index = int(main_socket) - 1 if main_socket else None
    except ValueError:
        main_socket_index = None

    selected_main = None
    if main_socket_index is not None and 0 <= main_socket_index < len(groups):
        selected_main = groups[main_socket_index]["main_gem"]

    return {
        "source": source_label,
        "source_type": "pob-xml",
        "has_pob_xml": True,
        "class_name": attrs.get("className") or attrs.get("class") or "",
        "ascendancy": attrs.get("ascendClassName") or attrs.get("ascendancyName") or "",
        "level": int(attrs.get("level", "0") or 0),
        "target_version": attrs.get("targetVersion") or root.attrib.get("targetVersion"),
        "main_socket_group": main_socket,
        "main_skill": selected_main,
        "player_stats": curated,
        "all_player_stats": stats,
        "player_stat_count": len(stats),
        "skills": groups,
        "skill_group_count": len(groups),
        "tree": tree,
        "items": items,
        "config": config,
    }


def save_current(xml: str, summary: dict):
    POB_DIR.mkdir(parents=True, exist_ok=True)
    summary=dict(summary)
    summary["has_pob_xml"]=True
    CURRENT_XML.write_text(xml, encoding="utf-8")
    CURRENT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),encoding="utf-8")


def save_current_native(summary: dict):
    POB_DIR.mkdir(parents=True, exist_ok=True)
    summary=dict(summary)
    summary["has_pob_xml"]=False
    CURRENT_XML.unlink(missing_ok=True)
    CURRENT_JSON.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")


def load_current() -> dict | None:
    if not CURRENT_JSON.exists(): return None
    try:
        data=json.loads(CURRENT_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data,dict) else None
    except Exception:
        return None



def clear_current(stop_engine: bool=True) -> dict:
    previous=load_current()
    CURRENT_XML.unlink(missing_ok=True)
    CURRENT_JSON.unlink(missing_ok=True)
    engine_stopped=False
    if stop_engine:
        try:
            from src.pob_engine import ENGINE
            if ENGINE.is_running():
                ENGINE.stop(force=True)
                engine_stopped=True
        except Exception:
            pass
    return {"cleared": previous is not None, "engine_stopped": engine_stopped}


def load_current_xml() -> str:
    current=load_current()
    if current and current.get("has_pob_xml") is False:
        raise ValueError("A build atual veio diretamente da GGG e ainda não possui XML PoB. O Finder pode usá-la, mas o motor PoB precisa de uma etapa de conversão separada.")
    if not CURRENT_XML.exists():
        raise ValueError("Nenhuma build PoB/XML está ativa.")
    return CURRENT_XML.read_text(encoding="utf-8")


def import_build(source: str) -> dict:
    payload, label = fetch_source(source)
    xml = decode_payload(payload)
    summary = parse_build(xml, label)
    record = build_library.save_build(xml, summary)
    summary["library_id"] = record["id"]
    save_current(xml, summary)
    return summary


def library_list(q="", class_name="", ascendancy="", main_skill="", min_level=0, sync=True):
    sync_result={"checked":0,"imported":0}
    if sync:
        sync_result=build_library.sync_siblings(parse_build)
    data=build_library.list_builds(q, class_name, ascendancy, main_skill, min_level)
    data["sync"] = sync_result
    data["sources"] = build_library.source_status()
    gstatus=ggg_api.status()
    for row in data["sources"]:
        if row.get("id")=="ggg":
            row["status"]="ready" if gstatus.get("configured") else "blocked-registration"
            row["detail"]=("Integração OAuth + personagem PoE2 implementada. " + gstatus.get("registration_note", ""))
    return data


def library_use(build_id: str) -> dict:
    record=build_library.get_record(build_id) or {}
    if record.get("has_pob_xml") is False or record.get("payload_kind")=="ggg-character":
        payload=build_library.get_native_payload(build_id)
        summary=ggg_api.character_to_summary(payload,record.get("source") or "GGG API")
        summary["library_id"]=build_id
        save_current_native(summary)
        return summary
    xml=build_library.get_xml(build_id)
    summary=parse_build(xml, record.get("source") or "Biblioteca local")
    summary["library_id"] = build_id
    save_current(xml, summary)
    return summary


def current_tree_analysis(catalog) -> dict:
    from src.tree_points import analyze
    current = load_current()
    if not current:
        raise ValueError("Nenhuma build ativa para analisar a árvore.")
    return analyze(catalog, current)


def library_delete(build_id: str) -> dict:
    current=load_current() or {}
    was_current=str(current.get("library_id") or "") == str(build_id)
    deleted=build_library.delete_build(build_id)
    cleared={"cleared":False,"engine_stopped":False}
    if deleted and was_current:
        cleared=clear_current(stop_engine=True)
    return {"deleted":deleted,"id":build_id,"was_current":was_current and deleted,**cleared}


def ggg_import_character(name: str) -> dict:
    character=ggg_api.get_character(name)
    summary=ggg_api.character_to_summary(character)
    record=build_library.save_native_build(character,summary,source_override=summary.get("source"))
    summary["library_id"]=record["id"]
    save_current_native(summary)
    return summary


def ggg_import_snapshot(payload) -> dict:
    parsed=ggg_api.import_snapshot_json(payload)
    character=parsed["character"]
    summary=parsed["summary"]
    record=build_library.save_native_build(character,summary,source_override=summary.get("source"))
    summary["library_id"]=record["id"]
    save_current_native(summary)
    return summary


def _json_request(url: str, method="GET", payload=None, timeout=4):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise ConnectionError("O motor PoB respondeu algo que não é JSON.") from exc


def engine_status(base_url: str = DEFAULT_ENGINE) -> dict:
    try:
        data = _json_request(base_url.rstrip("/") + "/health", timeout=2)
        return {
            "connected": True,
            "base_url": base_url,
            "health": data,
        }
    except Exception as exc:
        return {
            "connected": False,
            "base_url": base_url,
            "error": str(exc),
        }


def engine_load_current(base_url: str = DEFAULT_ENGINE) -> dict:
    xml = load_current_xml()
    base = base_url.rstrip("/")
    loaded = _json_request(
        base + "/build/load/xml",
        method="POST",
        payload={"xml": xml, "name": "Synergy Finder imported build"},
        timeout=20,
    )
    info = _json_request(base + "/build/info", timeout=8)
    calc = _json_request(base + "/calc", timeout=15)
    skills = _json_request(base + "/skills", timeout=8)
    return {
        "connected": True,
        "loaded": loaded,
        "build_info": info,
        "calc": calc,
        "skills": skills,
    }


# v0.11 direct stdio engine integration
def stdio_engine_status():
    from src.pob_engine import ENGINE
    return ENGINE.status()

def stdio_setup_status():
    from src.pob_engine import setup_status
    return setup_status()

def stdio_auto_detect():
    from src.pob_engine import auto_detect
    return auto_detect()

def stdio_save_config(values):
    from src.pob_engine import save_config, setup_status
    save_config(values or {})
    return setup_status()

def stdio_install_bridge():
    from src.pob_engine import install_bridge
    return install_bridge()

def stdio_start():
    from src.pob_engine import ENGINE
    return ENGINE.start()

def stdio_stop():
    from src.pob_engine import ENGINE
    return ENGINE.stop()

def stdio_load_current():
    from src.pob_engine import ENGINE
    xml = load_current_xml()
    ENGINE.load_xml(xml, "Synergy Finder imported build")
    return ENGINE.calculate_snapshot()

def stdio_snapshot():
    from src.pob_engine import ENGINE
    return ENGINE.calculate_snapshot()


def stdio_install_pob_checkout():
    from src.pob_engine import install_pob_checkout
    return install_pob_checkout()


def stdio_virtual_context():
    from src.pob_engine import ENGINE
    if not ENGINE.is_running():
        raise RuntimeError("Motor PoB não está ativo.")
    xml=load_current_xml()
    ENGINE.load_xml(xml,"Synergy Finder virtual context")
    return {"skills":ENGINE.get_skill_groups(),"supports":[]}

def stdio_compatible_supports(params):
    from src.pob_engine import ENGINE
    if not ENGINE.is_running():
        raise RuntimeError("Motor PoB não está ativo.")
    if not isinstance(params, dict):
        raise ValueError("Pedido inválido.")
    xml=load_current_xml()
    ENGINE.load_xml(xml,"Synergy Finder compatibility context")
    return ENGINE.get_compatible_support_gems(
        int(params.get("groupIndex") or 0)
    )

def stdio_compare_supports(params):
    from src.pob_engine import ENGINE
    if not ENGINE.is_running():
        raise RuntimeError("Motor PoB não está ativo.")
    return ENGINE.compare_support_setup(
        load_current_xml(),
        int(params.get("groupIndex") or 0),
        params.get("supports") or [],
    )
