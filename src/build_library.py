from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "data" / "builds"
INDEX_FILE = LIB_DIR / "index.json"
DELETED_FILE = LIB_DIR / "deleted.json"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_index(rows: list[dict]):
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(INDEX_FILE)



def _load_deleted() -> set[str]:
    if not DELETED_FILE.exists():
        return set()
    try:
        data=json.loads(DELETED_FILE.read_text(encoding="utf-8"))
        if isinstance(data,list):
            return {str(x).lower() for x in data if isinstance(x,str)}
    except Exception:
        pass
    return set()


def _write_deleted(ids: set[str]):
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    tmp=DELETED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DELETED_FILE)


def _restore_deleted(build_id: str):
    deleted=_load_deleted()
    if build_id.lower() in deleted:
        deleted.discard(build_id.lower())
        _write_deleted(deleted)


def _source_kind(source: str) -> str:
    s = (source or "").lower()
    if "pobb.in" in s:
        return "pobb.in"
    if "ggg api" in s or "pathofexile api" in s:
        return "GGG API"
    if "poe.ninja" in s:
        return "poe.ninja-pob"
    if s.endswith(".xml") or "\\" in source or "/" in source:
        return "arquivo local"
    if source:
        return "PoB"
    return "local"


def _skill_preview(summary: dict) -> list[dict]:
    out=[]
    for group in (summary.get("skills") or [])[:8]:
        out.append({
            "label": group.get("label") or group.get("main_gem") or "",
            "main_gem": group.get("main_gem") or "",
            "gems": [g.get("name") for g in (group.get("gems") or []) if g.get("name")][:8],
        })
    return out


def _gear_preview(summary: dict) -> list[str]:
    names=[]
    for slot in (summary.get("items") or {}).get("slots", [])[:12]:
        item=slot.get("item") or {}
        name=item.get("name") or item.get("base_type")
        if name:
            names.append(name)
    return names


def _compact(summary: dict, build_id: str, xml_hash: str, imported_at: str, source_override: str | None=None) -> dict:
    source = source_override if source_override is not None else (summary.get("source") or "")
    main = summary.get("main_skill") or "Build"
    asc = summary.get("ascendancy") or summary.get("class_name") or "Classe"
    level = int(summary.get("level") or 0)
    return {
        "id": build_id,
        "sha256": xml_hash,
        "title": f"{main} · {asc} · Lv{level or '?'}",
        "imported_at": imported_at,
        "source": source,
        "source_kind": _source_kind(source),
        "class_name": summary.get("class_name") or "",
        "ascendancy": summary.get("ascendancy") or "",
        "level": level,
        "main_skill": summary.get("main_skill") or "",
        "character_name": summary.get("character_name") or "",
        "league": summary.get("league") or "",
        "payload_kind": summary.get("source_type") or "pob-xml",
        "has_pob_xml": bool(summary.get("has_pob_xml", True)),
        "skill_group_count": int(summary.get("skill_group_count") or 0),
        "tree_nodes": int((summary.get("tree") or {}).get("allocated_nodes") or 0),
        "tree_base_refs": len((summary.get("tree") or {}).get("base_hashes") or (summary.get("tree") or {}).get("node_refs") or []),
        "tree_specialisation_refs": sum(
            len(v or [])
            for v in ((summary.get("tree") or {}).get("specialisations") or {}).values()
        ) if isinstance((summary.get("tree") or {}).get("specialisations"), dict) else 0,
        "items_count": int((summary.get("items") or {}).get("count") or 0),
        "player_stats": dict(summary.get("player_stats") or {}),
        "skills_preview": _skill_preview(summary),
        "gear_preview": _gear_preview(summary),
    }


def save_build(xml: str, summary: dict, source_override: str | None=None, restore_deleted: bool=True) -> dict:
    raw = xml.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    build_id = digest[:16]
    if restore_deleted:
        _restore_deleted(build_id)
    rows = _load_index()
    existing = next((r for r in rows if r.get("sha256") == digest), None)
    imported_at = existing.get("imported_at") if existing else _now()
    record = _compact(summary, build_id, digest, imported_at, source_override)
    if existing:
        rows[rows.index(existing)] = record
    else:
        rows.append(record)
    rows.sort(key=lambda r: r.get("imported_at", ""), reverse=True)
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    (LIB_DIR / f"{build_id}.xml").write_text(xml, encoding="utf-8")
    _write_index(rows)
    return record


def save_native_build(payload: dict, summary: dict, source_override: str | None=None, restore_deleted: bool=True) -> dict:
    canonical=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    digest=hashlib.sha256(canonical).hexdigest()
    build_id=digest[:16]
    if restore_deleted:
        _restore_deleted(build_id)
    rows=_load_index()
    existing=next((r for r in rows if r.get("sha256")==digest),None)
    imported_at=existing.get("imported_at") if existing else _now()
    summary=dict(summary)
    summary["has_pob_xml"]=False
    record=_compact(summary,build_id,digest,imported_at,source_override)
    record["payload_kind"]=summary.get("source_type") or "native-json"
    record["has_pob_xml"]=False
    if existing: rows[rows.index(existing)]=record
    else: rows.append(record)
    rows.sort(key=lambda r:r.get("imported_at",""),reverse=True)
    LIB_DIR.mkdir(parents=True,exist_ok=True)
    (LIB_DIR/f"{build_id}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    _write_index(rows)
    return record


def get_native_payload(build_id: str) -> dict:
    if not build_id or not all(c in "0123456789abcdef" for c in build_id.lower()) or len(build_id)!=16:
        raise ValueError("ID de build inválido.")
    path=LIB_DIR/f"{build_id}.json"
    if not path.exists(): raise ValueError("Snapshot nativo não encontrado na biblioteca local.")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise ValueError("Snapshot nativo corrompido.")
    return data


def get_record(build_id: str) -> dict | None:
    return next((r for r in _load_index() if r.get("id") == build_id), None)


def get_xml(build_id: str) -> str:
    if not build_id or not all(c in "0123456789abcdef" for c in build_id.lower()) or len(build_id) != 16:
        raise ValueError("ID de build inválido.")
    path = LIB_DIR / f"{build_id}.xml"
    if not path.exists():
        raise ValueError("Build não encontrada na biblioteca local.")
    return path.read_text(encoding="utf-8")


def delete_build(build_id: str) -> bool:
    rows = _load_index()
    record = next((r for r in rows if r.get("id") == build_id), None)
    keep = [r for r in rows if r.get("id") != build_id]
    if record is None:
        return False
    deleted=_load_deleted()
    deleted.add(str(build_id).lower())
    _write_deleted(deleted)
    _write_index(keep)
    (LIB_DIR / f"{build_id}.xml").unlink(missing_ok=True)
    (LIB_DIR / f"{build_id}.json").unlink(missing_ok=True)
    return True


def _blob(row: dict) -> str:
    parts=[
        row.get("title",""), row.get("source",""), row.get("class_name",""),
        row.get("ascendancy",""), row.get("main_skill",""),
        row.get("character_name",""), row.get("league",""),
    ]
    for g in row.get("skills_preview",[]):
        parts.append(g.get("label", ""));parts.append(g.get("main_gem", ""));parts.extend(g.get("gems", []))
    parts.extend(row.get("gear_preview", []))
    return " ".join(str(x) for x in parts if x).casefold()


def list_builds(q="", class_name="", ascendancy="", main_skill="", min_level=0) -> dict:
    rows = _load_index()
    query=(q or "").strip().casefold()
    def ok(r):
        if query and query not in _blob(r): return False
        if class_name and r.get("class_name") != class_name: return False
        if ascendancy and r.get("ascendancy") != ascendancy: return False
        if main_skill and r.get("main_skill") != main_skill: return False
        if int(r.get("level") or 0) < int(min_level or 0): return False
        return True
    results=[r for r in rows if ok(r)]
    def values(key): return sorted({r.get(key) for r in rows if r.get(key)}, key=str.casefold)
    return {
        "results": results,
        "total": len(results),
        "library_total": len(rows),
        "facets": {
            "classes": values("class_name"),
            "ascendancies": values("ascendancy"),
            "main_skills": values("main_skill"),
        },
    }


def _family_root() -> Path:
    return PROJECT_ROOT.parent.parent


def sync_siblings(parse_callback) -> dict:
    """Read-only migration from sibling Finder folders; current library is deduped by XML hash."""
    family = _family_root()
    imported=0;checked=0
    if not family.exists():
        return {"checked":0,"imported":0}
    for version_dir in family.glob("poe2-synergy-finder-v*"):
        root = version_dir / "poe2-synergy-finder"
        try:
            if root.resolve() == PROJECT_ROOT.resolve():
                continue
        except Exception:
            pass
        # Old/current build from every version.
        xml_path=root/"data"/"pob"/"current.xml"
        json_path=root/"data"/"pob"/"current.json"
        if xml_path.exists():
            checked+=1
            try:
                xml=xml_path.read_text(encoding="utf-8")
                summary=None
                if json_path.exists():
                    try:summary=json.loads(json_path.read_text(encoding="utf-8"))
                    except Exception:summary=None
                if not isinstance(summary,dict):
                    summary=parse_callback(xml, f"Migrada de {version_dir.name}")
                digest=hashlib.sha256(xml.encode("utf-8")).hexdigest()
                if digest[:16].lower() in _load_deleted():
                    continue
                before=len(_load_index())
                save_build(xml,summary,source_override=summary.get("source") or f"Migrada de {version_dir.name}",restore_deleted=False)
                if len(_load_index())>before:imported+=1
            except Exception:
                pass
        # v0.13+ libraries in siblings.
        idx=root/"data"/"builds"/"index.json"
        if idx.exists():
            try:
                sibling_rows=json.loads(idx.read_text(encoding="utf-8"))
            except Exception:
                sibling_rows=[]
            for row in sibling_rows if isinstance(sibling_rows,list) else []:
                bid=row.get("id")
                sp=root/"data"/"builds"/f"{bid}.xml"
                if not bid or not sp.exists():continue
                checked+=1
                try:
                    xml=sp.read_text(encoding="utf-8")
                    summary=parse_callback(xml,row.get("source") or f"Migrada de {version_dir.name}")
                    digest=hashlib.sha256(xml.encode("utf-8")).hexdigest()
                    if digest[:16].lower() in _load_deleted():
                        continue
                    before=len(_load_index())
                    save_build(xml,summary,source_override=row.get("source") or summary.get("source"),restore_deleted=False)
                    if len(_load_index())>before:imported+=1
                except Exception:
                    pass
    return {"checked":checked,"imported":imported}


def source_status() -> list[dict]:
    return [
        {
            "id":"local","name":"Biblioteca local","status":"ready",
            "detail":"PoB/XML já importados ficam pesquisáveis e podem virar a Build atual com um clique."
        },
        {
            "id":"ggg","name":"Minha conta GGG","status":"planned",
            "detail":"Fonte oficial possível via OAuth account:characters. Exige um client OAuth registrado para este aplicativo."
        },
        {
            "id":"poeninja","name":"poe.ninja · Builds globais","status":"restricted",
            "detail":"A API de builds/perfis do poe.ninja não é pública para terceiros. A interface fica preparada para uma fonte autorizada futura, sem usar endpoints internos."
        },
    ]
