"""Entrada HTTP/MCP do laboratório.

Duas coisas moram aqui:

- `verify_anchor`: medição isolada, abre e fecha um motor próprio.
- a **sessão de laboratório**: uma build de trabalho num segundo motor, separada da
  build atual do Finder, que o agente monta e mede passo a passo (`handle`).

Uma sessão por vez; toda ação fica registrada e sai junto com o export.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import zlib
from pathlib import Path

from src import pob_engine
from src.lab import bench, data, gear, tree
from src.lab.engine import DEFENCE_FIELDS, FIELDS, Lab, gem_level, normal, xml_groups

_lock = threading.RLock()
_session: dict | None = None
LEVEL_MIN, LEVEL_MAX = 1, 100
CLASSES = {"Witch", "Ranger", "Warrior", "Sorceress", "Huntress", "Mercenary", "Monk", "Druid"}
PROJECT = Path(__file__).resolve().parents[2]
EXPORT_DIR = PROJECT / "builds-teste"
COMPACT = ["TotalDPS", "CombinedDPS", "AverageDamage", "Speed", "CritChance", "HitChance", "ManaCost", "ProjectileCount",
           "PowerCharges", "PowerChargesMax", "FrenzyCharges", "IgniteDPS", "BleedDPS", "PoisonDPS",
           "Life", "Mana", "EnergyShield", "Evasion", "Armour", "TotalEHP", "FireResist", "ColdResist", "LightningResist", "ChaosResist"]
# Condições de configuração que o laboratório sabe ligar. Não é a lista completa do PoB.
CONFIG_OPTIONS = {
    "enemyLevel": "nível do inimigo (inteiro)",
    "enemyIsBoss": "None | Boss | Pinnacle | Uber",
    "resistancePenalty": "0 no ato 1, -10 no ato 2, -60 no fim de jogo",
    "usePowerCharges / useFrenzyCharges / useEnduranceCharges": "true liga as cargas no máximo",
    "overridePowerCharges": "número de Power Charges (0 = máximo)",
    "multiplierRage": "Rage atual",
    "conditionEnemyShocked / Frozen / Chilled / Ignited / Poisoned / Bleeding": "estado do inimigo",
    "conditionEnemyHeavyStunned / Stunned / Dazed / Pinned / Immobilised / ArmourBroken": "estado do inimigo",
    "conditionEnemyFullLife / LowLife / RareOrUnique": "estado do inimigo",
}


# ---------- verificação isolada ----------
def _family_of(skill: str, family: str | None) -> tuple[str, str]:
    catalog = data.skills_by_family()
    matches = {fam: name for fam, rows in catalog.items() for _tier, name in rows if name.casefold() == skill.casefold()}
    if family:
        if family not in data.FAMILY:
            raise ValueError(f"família inválida: {family}. Use uma de {', '.join(data.FAMILY)}.")
        if family not in matches:
            raise ValueError(f'"{skill}" não é uma skill ativa da família {family}.')
        return family, matches[family]
    if not matches:
        raise ValueError(f'"{skill}" não é uma skill ativa lançada do catálogo. Confira o nome com economy_lookup.')
    if len(matches) > 1:
        raise ValueError(f'"{skill}" existe em mais de uma família ({", ".join(sorted(matches))}); informe family.')
    (family, name), = matches.items()
    return family, name


def _require_engine():
    if not pob_engine.setup_status()["ready"]:
        raise RuntimeError("Motor PoB não configurado. Use Build atual → Motor PoB → Detectar.")


def verify_anchor(args: dict) -> dict:
    skill = str(args.get("skill") or "").strip()
    if not skill:
        raise ValueError("Informe a skill.")
    level = _level(args.get("level"), 14)
    family, name = _family_of(skill, args.get("family") or None)
    _require_engine()
    with _lock:
        with Lab() as lab:
            weapon = data.weapon_for(family, level)
            rows = bench.verify_anchor(lab, family, name, level)
    specific = [r for r in rows if not r["generic"]]
    return {
        "skill": name, "family": family, "class": data.FAMILY[family][0], "level": level, "weapon": weapon,
        "conditions_tested": list(bench.CONDITIONS),
        "specific": specific, "generic": [r for r in rows if r["generic"]],
        "verdict": ("âncora confirmada: multiplicador próprio medido no PoB" if specific else
                    "nenhum multiplicador próprio medido; só os genéricos (shock, armadura quebrada) ou nada"),
        "caveats": ["arma branca, sem supports, sem árvore, inimigo normal do mesmo nível",
                    "condições que o PoB não modela não aparecem (stages, empowered, consumo de Frenzy, minions)"],
    }


# ---------- sessão ----------
def _level(value, default=None) -> int:
    level = int(value if value not in (None, "") else default)
    if not LEVEL_MIN <= level <= LEVEL_MAX:
        raise ValueError(f"level deve ficar entre {LEVEL_MIN} e {LEVEL_MAX}.")
    return level


def _current() -> dict:
    if not _session:
        raise RuntimeError("Nenhuma sessão de laboratório aberta. Chame lab open primeiro.")
    _session["lab"].restart_if_dead()
    return _session


def _compact(stats: dict) -> dict:
    out = {}
    for k in COMPACT:
        v = stats.get(k)
        if isinstance(v, bool) or v in (None, 0, 0.0):
            continue
        out[k] = round(v, 1) if isinstance(v, float) else v
    return out


def _log(action: str, params: dict):
    _session["log"].append({"t": round(time.time() - _session["t0"], 1), "action": action,
                            "params": json.loads(json.dumps(params, default=str))[:1] if isinstance(params, list) else
                            {k: (v if len(str(v)) < 200 else str(v)[:200] + "…") for k, v in params.items()}})


def _summary(s: dict) -> dict:
    lab: Lab = s["lab"]
    xml = lab.export_xml()
    return {"name": s["name"], "class": s["class"], "ascendancy": s["ascendancy"], "level": s["level"],
            "groups": xml_groups(xml), "selected": s.get("selected"), "stats": _compact(lab.stats(FIELDS + DEFENCE_FIELDS)),
            "actions": len(s["log"])}


def _measure_from(spec: dict):
    """metrics: {"nome": {"group": 1, "part": 2, "field": "TotalDPS"}} -> função que lê tudo de uma vez."""
    if not isinstance(spec, dict) or not spec:
        raise ValueError('metrics deve ser {"nome": {"group": 1, "field": "TotalDPS", "part": opcional}}')
    for k, v in spec.items():
        if not isinstance(v, dict) or "field" not in v:
            raise ValueError(f'metrics[{k!r}] precisa de "field"')

    def measure():
        s = _current()
        lab: Lab = s["lab"]
        out = {}
        for name, m in spec.items():
            group, part = int(m.get("group") or 1), m.get("part")
            key = (group, int(part)) if part else (group, None)
            if key != s.get("selected_key"):
                if part:
                    lab.select_part(group, int(part))
                else:
                    lab.select(group)
                s["selected_key"] = key
            out[name] = lab.stats(FIELDS + DEFENCE_FIELDS).get(m["field"]) or 0
        return out
    return measure


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-. ]+", "_", str(name or "lab")).strip() or "lab"


def _pob_code(xml: str) -> str:
    return base64.b64encode(zlib.compress(xml.encode("utf-8"), 9)).decode().replace("+", "-").replace("/", "_")


def _pob_builds_dir() -> Path | None:
    home = Path(os.environ.get("USERPROFILE", Path.home()))
    for candidate in (home / "OneDrive" / "Documents" / "Path of Building (PoE2)" / "Builds",
                      home / "Documents" / "Path of Building (PoE2)" / "Builds"):
        if candidate.is_dir():
            return candidate
    return None


def act_open(p: dict) -> dict:
    global _session
    source = str(p.get("from") or "new")
    name = str(p.get("name") or f"lab {time.strftime('%Y-%m-%d %H%M')}")
    _require_engine()
    if _session:
        act_close({})
    lab = Lab()
    try:
        if source == "current":
            from src import pob_bridge
            xml = pob_bridge.load_current_xml()
            lab.load_xml(xml, name)
            info = pob_bridge.load_current() or {}
            cls, asc, level = info.get("class_name") or "", info.get("ascendancy") or "", int(info.get("level") or 1)
            if asc in ("None", ""):
                asc = ""
        elif source == "new":
            cls = str(p.get("class") or "")
            if cls not in CLASSES:
                raise ValueError(f"class inválida: {cls!r}. Use uma de {', '.join(sorted(CLASSES))}.")
            asc = str(p.get("ascendancy") or "")
            if asc and asc not in lab.classes[cls]["ascendancies"]:
                raise ValueError(f"ascendância {asc!r} não é de {cls}: {', '.join(lab.classes[cls]['ascendancies'])}")
            level = _level(p.get("level"), 1)
            weapon = p.get("weapon")
            lab.new_build(cls, level, asc or None, weapon=normal(weapon) if weapon else None)
            lab.config(bench.enemy_config(level))
        else:
            raise ValueError('from deve ser "new" ou "current"')
    except Exception:
        lab.close()
        raise
    _session = {"lab": lab, "name": name, "class": cls, "ascendancy": asc, "level": level, "log": [], "t0": time.time(),
                "selected": None, "selected_key": None}
    _log("open", p)
    return _summary(_session)


def act_status(p: dict) -> dict:
    if not _session:
        return {"open": False}
    return {"open": True, **_summary(_current())}


def act_close(p: dict) -> dict:
    global _session
    if not _session:
        return {"open": False}
    actions = len(_session["log"])
    try:
        _session["lab"].close()
    finally:
        _session = None
    return {"open": False, "closed_after_actions": actions}


def act_add_skill(p: dict) -> dict:
    s = _current()
    raw = p.get("gems")
    if not isinstance(raw, list) or not raw:
        raise ValueError('gems deve ser uma lista: [["Falling Thunder", 5], ["Lightning Attunement", 1, 20]] ou [{"name","level","quality"}]')
    gems = []
    for g in raw:
        if isinstance(g, dict):
            g = [g.get("name"), g.get("level"), g.get("quality")]
        g = list(g) + [None, None]
        name, level, quality = str(g[0] or "").strip(), g[1], g[2]
        if not name:
            raise ValueError("gem sem nome")
        gem = (name, int(level) if level not in (None, "") else gem_level(s["level"]))
        if quality not in (None, ""):
            gem += (int(quality),)
        gems.append(gem)
    index = s["lab"].group(gems)
    s["lab"].select(index)
    s["selected"], s["selected_key"] = {"group": index, "part": None}, (index, None)
    _log("add_skill", p)
    return {"group": index, "groups": xml_groups(s["lab"].export_xml()), "stats": _compact(s["lab"].stats())}


def act_equip(p: dict) -> dict:
    s = _current()
    slot = str(p.get("slot") or "").strip()
    if not slot:
        raise ValueError("slot obrigatório (ex.: Weapon 1, Body Armour, Ring 1)")
    text = p.get("text")
    if not text and p.get("base"):
        text = normal(str(p["base"]))
    if not text:
        raise ValueError('informe text (texto do item como o PoB importa) ou base (nome da base branca)')
    s["lab"].equip(slot, str(text))
    _log("equip", p)
    return {"slot": slot, "item": str(text).splitlines()[1:3], "stats": _compact(s["lab"].stats(FIELDS + DEFENCE_FIELDS))}


def act_config(p: dict) -> dict:
    s = _current()
    values = p.get("values") if isinstance(p.get("values"), dict) else {k: v for k, v in p.items() if k != "values"}
    if not values:
        raise ValueError('informe values: {"usePowerCharges": true, "enemyLevel": 14}')
    for k, v in values.items():
        if not isinstance(v, (bool, int, float, str)):
            raise ValueError(f"valor de {k} deve ser booleano, número ou texto")
    s["lab"].config(values)
    _log("config", p)
    return {"applied": values, "stats": _compact(s["lab"].stats(FIELDS + DEFENCE_FIELDS))}


def act_config_options(p: dict) -> dict:
    return {"options": CONFIG_OPTIONS, "conditions_in_verify_anchor": list(bench.CONDITIONS),
            "note": "Lista curada; o PoB tem mais opções e condições que esta sessão ainda não enumera."}


def act_allocate(p: dict) -> dict:
    s = _current()
    lab: Lab = s["lab"]
    ctx = lab.tree_context()
    current = {n["id"] for n in ctx["nodes"] if n["allocated"] and not n.get("ascendancy")}
    if p.get("nodes") is not None:
        wanted = {int(x) for x in p["nodes"]}
    else:
        wanted = (current | {int(x) for x in p.get("add") or []}) - {int(x) for x in p.get("remove") or []}
    known = {n["id"]: n for n in ctx["nodes"]}
    unknown = sorted(x for x in wanted if x not in known)
    if unknown:
        raise ValueError(f"nós desconhecidos: {unknown[:10]}")
    lab.set_nodes(s["class"], wanted, s["ascendancy"] or None)
    s["selected_key"] = None
    _log("allocate", p)
    names = [known[x]["name"] for x in sorted(wanted - current)]
    return {"allocated": len(wanted), "added": names[:40], "removed": len(current - wanted),
            "stats": _compact(lab.stats(FIELDS + DEFENCE_FIELDS))}


def act_select(p: dict) -> dict:
    s = _current()
    group, part, active = int(p.get("group") or 1), p.get("part"), int(p.get("active") or 1)
    if part:
        s["lab"].select_part(group, int(part), active)
    else:
        s["lab"].select(group, active)
    s["selected"], s["selected_key"] = {"group": group, "part": int(part) if part else None}, (group, int(part) if part else None)
    _log("select", p)
    return {"selected": s["selected"], "stats": _compact(s["lab"].stats())}


def act_stats(p: dict) -> dict:
    s = _current()
    fields = p.get("fields")
    stats = s["lab"].stats(fields if isinstance(fields, list) and fields else FIELDS + DEFENCE_FIELDS)
    return {"stats": _compact(stats) if not fields else {k: stats.get(k) for k in fields}}


def act_tree_search(p: dict) -> dict:
    s = _current()
    budget = int(p.get("budget") or 0)
    if not 1 <= budget <= 60:
        raise ValueError("budget deve ficar entre 1 e 60 pontos")
    weights = p.get("weights") or {}
    measure = _measure_from(p.get("metrics") or {})
    if not weights or any(k not in p["metrics"] for k in weights):
        raise ValueError("weights deve usar os nomes de metrics")
    s["selected_key"] = None
    result = tree.greedy_tree(s["lab"], s["class"], budget, measure, weights, ascendancy=s["ascendancy"] or None,
                              notable_reach=int(p.get("notable_reach") or 6), small_reach=int(p.get("small_reach") or 2),
                              forced_first=p.get("forced_first") or None, allow_keystones=bool(p.get("allow_keystones")))
    _log("tree_search", p)
    return result


def act_gear_search(p: dict) -> dict:
    s = _current()
    weights = p.get("weights") or {}
    measure = _measure_from(p.get("metrics") or {})
    if not weights or any(k not in p["metrics"] for k in weights):
        raise ValueError("weights deve usar os nomes de metrics")
    weapon_file, weapon_tag = p.get("weapon_file"), p.get("weapon_tag")
    armour_tags = p.get("armour_tags") or ["dex_int_armour", "dex_armour", "int_armour"]
    if not (weapon_file and weapon_tag):
        raise ValueError('informe weapon_file (ex.: staff.lua) e weapon_tag (ex.: warstaff)')
    level = _level(p.get("level"), s["level"])
    xml = s["lab"].export_xml()
    s["selected_key"] = None
    result = gear.search_gear(s["lab"], xml, level, measure, weights, gear.default_slots(weapon_file, weapon_tag, armour_tags),
                              item_level=p.get("item_level"), prefixes=int(p.get("prefixes") or 3), suffixes=int(p.get("suffixes") or 3))
    paths = {}
    EXPORT_DIR.mkdir(exist_ok=True)
    for label, final in result["finais"].items():
        path = EXPORT_DIR / f"{_safe_name(s['name'])}-gear-{label}.xml"
        path.write_text(final["xml"], encoding="utf-8")
        paths[label] = str(path)
    s["lab"].load_xml(xml, s["name"])  # a sessão volta ao estado anterior à busca
    _log("gear_search", p)
    return {"sem_gear": result["sem_gear"], "slots": result["slots"],
            "finais": {k: v["stats"] for k, v in result["finais"].items()}, "arquivos": paths}


def act_export(p: dict) -> dict:
    s = _current()
    name = _safe_name(p.get("name") or s["name"])
    xml = s["lab"].export_xml()
    EXPORT_DIR.mkdir(exist_ok=True)
    xml_path, code_path, log_path = EXPORT_DIR / f"{name}.xml", EXPORT_DIR / f"{name}.codigo-pob.txt", EXPORT_DIR / f"{name}.log.json"
    xml_path.write_text(xml, encoding="utf-8")
    code_path.write_text(_pob_code(xml), encoding="utf-8")
    log_path.write_text(json.dumps({"name": s["name"], "class": s["class"], "level": s["level"], "log": s["log"]},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"xml": str(xml_path), "codigo_pob": str(code_path), "log": str(log_path)}
    if p.get("to_pob"):
        folder = _pob_builds_dir()
        if not folder:
            out["pob"] = "pasta de builds do Path of Building não encontrada"
        else:
            target = folder / f"{name}.xml"
            target.write_text(xml, encoding="utf-8")
            out["pob"] = str(target)
    _log("export", p)
    return out


ACTIONS = {
    "open": act_open, "status": act_status, "close": act_close, "add_skill": act_add_skill, "equip": act_equip,
    "config": act_config, "config_options": act_config_options, "allocate": act_allocate, "select": act_select,
    "stats": act_stats, "tree_search": act_tree_search, "gear_search": act_gear_search, "export": act_export,
}


def handle(action: str, params: dict | None) -> dict:
    fn = ACTIONS.get(str(action or "").strip())
    if not fn:
        raise ValueError(f"ação desconhecida: {action!r}. Ações: {', '.join(ACTIONS)}")
    with _lock:
        return fn(params if isinstance(params, dict) else {})
