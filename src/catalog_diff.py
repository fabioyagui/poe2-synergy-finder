"""Diff entre duas versões do catálogo RePoE do PoE 2 (gems e árvore), para conferir as notas de um patch nos dados.

As notas dizem o que a GGG quis anunciar; o diff mostra o que mudou nos arquivos do jogo, inclusive o que as
notas não citam. Compara pastas cruas do RePoE: a de "antes" é a versão importada na base (a pasta gravada em
`meta.import`, normalmente `data/raw/snapshots/<id>`; ou `data/raw/repoe`), a de "depois" é o snapshot
baixado mais recente (`data/raw/snapshots/<id>`). A base guarda uma versão só, por isso o diff lê as pastas.

Arquivos e campos do RePoE do PoE 2 (não os do PoE 1): `skill_gems.min.json` (gem por id de item: nome,
tipo, tags, skills concedidas, tier de gema bruta, lineage) e `skills.min.json` (skill por id: tempo de
conjuração, tipos, `static` com cooldown/usos/custos/reservas, `per_level` nos níveis 1 e máximo, e cada
`stat_set` com stats fixos e por nível, ex. damage_multiplier). A árvore é `passive_skill_trees/Default.min.json`
(`passives`: nome, keystone, notável, soquete, ascendência, stats). Só skills concedidas por gem entram no
detalhe; as outras (monstros, minions, disparadas) só são contadas. Não diz se a mudança é buff ou nerf: isso
é leitura, com o PoB medindo (`lab hypothesis` antes do PoB novo).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

GEMS = "skill_gems.min.json"
SKILLS = "skills.min.json"
TREE = "passive_skill_trees/Default.min.json"
GEM_FIELDS = ("gem_type", "tags", "grants_skills", "crafting_level", "crafting_types", "is_lineage", "color")
SKILL_STATIC = ("cooldown", "stored_uses", "costs", "reservations", "attack_speed_multiplier", "cost_multiplier", "cooldown_bypass_type")
NODE_FIELDS = ("name", "is_keystone", "is_notable", "is_jewel_socket", "ascendancy", "stats")


def _read(folder: Path, name: str):
    for p in (folder / name, folder / name.replace(".min.json", ".json"), folder / Path(name).name):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8-sig"))
    return None


def _version(folder: Path) -> str:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("repoe_version") or "?"
    except (OSError, ValueError):
        return "?"


def has_catalog(folder) -> bool:
    folder = Path(folder)
    return all(_read(folder, n) is not None for n in (GEMS, SKILLS))


def imported_folder() -> Path | None:
    """Pasta do catálogo importado na base (meta.import.folder) se ainda existir com os arquivos; senão o snapshot
    em data/raw/snapshots cujo skill_gems tem o mesmo sha256 do importado (a pasta pode ter mudado de lugar)."""
    try:
        from . import storage
        meta = storage.meta().get("import") or {}
    except Exception:
        return None
    folder = meta.get("folder")
    if folder and has_catalog(folder):
        return Path(folder)
    wanted = (meta.get("hashes") or {}).get(GEMS)
    root = storage.DATA / "raw" / "snapshots"
    if wanted and root.is_dir():
        import hashlib
        for p in sorted(root.iterdir()):
            if p.is_dir() and (p / GEMS).is_file() and hashlib.sha256((p / GEMS).read_bytes()).hexdigest() == wanted and has_catalog(p):
                return p
    return None


def latest_snapshot(root: Path, exclude: Path | None = None) -> Path | None:
    """Snapshot baixado mais recente (por data do skill_gems) que tenha gems e skills, fora `exclude`."""
    if not root.is_dir():
        return None
    snaps = [p for p in root.iterdir() if p.is_dir() and has_catalog(p)
             and not (exclude and p.resolve() == Path(exclude).resolve())]
    return max(snaps, key=lambda p: (p / GEMS).stat().st_mtime) if snaps else None


def _flat(value, prefix: str = "") -> dict:
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list) and value and all(isinstance(x, (dict, list)) or x is None for x in value):
        for i, v in enumerate(value):
            out.update(_flat(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = value
    return out


def _top_level(per_level: dict) -> str:
    keys = [k for k in per_level if str(k).isdigit()]
    return str(max((int(k) for k in keys), default=1))


def skill_view(skill: dict) -> dict:
    """O que pesa no número: tempo de conjuração, tipos, `static`, níveis 1 e máximo, e cada stat_set."""
    active = skill.get("active_skill") or {}
    view = {"cast_time": skill.get("cast_time"), "types": sorted(active.get("types") or []),
            "weapon_restrictions": sorted(active.get("weapon_restrictions") or []),
            "static": {k: v for k, v in (skill.get("static") or {}).items() if k in SKILL_STATIC}}
    levels = skill.get("per_level") or {}
    top = _top_level(levels)
    for level in ("1", top):
        view[f"L{level}"] = {k: v for k, v in (levels.get(level) or {}).items() if k in SKILL_STATIC}
    support = skill.get("support_gem") or {}
    if support:
        view["support"] = {k: sorted(v) if isinstance(v, list) else v for k, v in support.items()
                           if k in ("added_types", "allowed_types", "excluded_types")}
    sets = {}
    for ss in skill.get("stat_sets") or []:
        sid = str(ss.get("id") or len(sets))
        static = ss.get("static") or {}
        row = {"stats": {s.get("id"): s.get("value") for s in static.get("stats") or [] if isinstance(s, dict)},
               "quality": [q.get("stats") for q in static.get("quality_stats") or [] if isinstance(q, dict)]}
        plv = ss.get("per_level") or {}
        stop = _top_level(plv)
        for level in ("1", stop):
            row[f"L{level}"] = plv.get(level) or {}
        sets[sid] = row
    view["stat_sets"] = sets
    return view


def gem_view(gem: dict, skills: dict) -> dict:
    view = {k: (sorted(gem[k]) if isinstance(gem.get(k), list) else gem.get(k)) for k in GEM_FIELDS}
    view["skills"] = {sid: skill_view(skills[sid]) for sid in gem.get("grants_skills") or [] if sid in skills}
    return _flat(view)


def node_view(node: dict) -> dict:
    return _flat({k: node.get(k) for k in NODE_FIELDS})


def _changes(before: dict, after: dict) -> list[dict]:
    keys = sorted(set(before) | set(after))
    return [{"campo": k, "antes": before.get(k), "depois": after.get(k)} for k in keys if before.get(k) != after.get(k)]


def _gem_name(gem: dict, key: str) -> str:
    return (gem.get("base_item") or {}).get("display_name") or key


def diff(old_folder, new_folder) -> dict:
    old_folder, new_folder = Path(old_folder), Path(new_folder)
    old_gems, new_gems = _read(old_folder, GEMS), _read(new_folder, GEMS)
    old_skills, new_skills = _read(old_folder, SKILLS), _read(new_folder, SKILLS)
    if not all(isinstance(x, dict) for x in (old_gems, new_gems, old_skills, new_skills)):
        raise ValueError(f"{GEMS} ou {SKILLS} ausente ou inválido em uma das pastas ({old_folder} / {new_folder})")
    gems = {"novas": [], "removidas": [], "alteradas": []}
    for key in sorted(set(old_gems) | set(new_gems)):
        a, b = old_gems.get(key), new_gems.get(key)
        if a is None:
            gems["novas"].append({"id": key, "nome": _gem_name(b, key), "tipo": b.get("gem_type"), "tags": b.get("tags") or [],
                                  "skills": b.get("grants_skills") or []})
        elif b is None:
            gems["removidas"].append({"id": key, "nome": _gem_name(a, key)})
        else:
            changes = _changes(gem_view(a, old_skills), gem_view(b, new_skills))
            if changes:
                gems["alteradas"].append({"id": key, "nome": _gem_name(b, key), "mudancas": changes})
    granted = {sid for g in list(old_gems.values()) + list(new_gems.values()) for sid in g.get("grants_skills") or []}
    others = {"novas": [], "removidas": [], "alteradas": []}
    for key in sorted(set(old_skills) | set(new_skills)):
        if key in granted:
            continue
        a, b = old_skills.get(key), new_skills.get(key)
        if a is None:
            others["novas"].append(key)
        elif b is None:
            others["removidas"].append(key)
        elif skill_view(a) != skill_view(b):
            others["alteradas"].append(key)
    out = {"antes": {"pasta": str(old_folder), "versao": _version(old_folder)},
           "depois": {"pasta": str(new_folder), "versao": _version(new_folder)}, "gems": gems, "skills_sem_gem": others}
    old_tree, new_tree = _read(old_folder, TREE), _read(new_folder, TREE)
    if isinstance(old_tree, dict) and isinstance(new_tree, dict):
        a_nodes, b_nodes = old_tree.get("passives") or {}, new_tree.get("passives") or {}
        tree = {"novos": [], "removidos": [], "alterados": []}
        for key in sorted(set(a_nodes) | set(b_nodes), key=str):
            a, b = a_nodes.get(key), b_nodes.get(key)
            if a is None:
                tree["novos"].append({"hash": key, "nome": b.get("name"), "keystone": bool(b.get("is_keystone")),
                                      "notavel": bool(b.get("is_notable")), "ascendancy": b.get("ascendancy"), "stats": b.get("stats")})
            elif b is None:
                tree["removidos"].append({"hash": key, "nome": a.get("name")})
            else:
                changes = _changes(node_view(a), node_view(b))
                if changes:
                    tree["alterados"].append({"hash": key, "nome": b.get("name"), "mudancas": changes})
        out["arvore"] = tree
    else:
        out["arvore"] = None
    out["resumo"] = {"gems_novas": len(gems["novas"]), "gems_removidas": len(gems["removidas"]), "gems_alteradas": len(gems["alteradas"]),
                     "skills_sem_gem_novas": len(others["novas"]), "skills_sem_gem_removidas": len(others["removidas"]),
                     "skills_sem_gem_alteradas": len(others["alteradas"]),
                     **({"nos_novos": len(out["arvore"]["novos"]), "nos_removidos": len(out["arvore"]["removidos"]),
                         "nos_alterados": len(out["arvore"]["alterados"])} if out["arvore"] else {"arvore": "ausente em uma das pastas"})}
    out["total"] = sum(v for v in out["resumo"].values() if isinstance(v, int))
    return out


def _short(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= 120 else text[:117] + "…"


def to_markdown(result: dict) -> str:
    a, b, r = result["antes"], result["depois"], result["resumo"]
    lines = [f"# Diff do catálogo RePoE (PoE 2): {a['versao']} → {b['versao']}", "",
             f"Antes: `{a['pasta']}`  ", f"Depois: `{b['pasta']}`", "",
             "Mudanças nos dados do jogo, não leitura de buff ou nerf; o número vem do PoB (`lab hypothesis` antes do PoB novo). "
             + json.dumps(r, ensure_ascii=False), ""]
    if not result["total"]:
        lines += ["Nenhuma diferença.", ""]
    g = result["gems"]
    if g["novas"]:
        lines += ["## Gems novas", ""] + [f"- {x['nome']} (`{x['id']}`, {x['tipo']}): {', '.join(x['tags'])}" for x in g["novas"]] + [""]
    if g["removidas"]:
        lines += ["## Gems removidas", ""] + [f"- {x['nome']} (`{x['id']}`)" for x in g["removidas"]] + [""]
    if g["alteradas"]:
        lines += ["## Gems alteradas", ""]
        for x in g["alteradas"]:
            lines.append(f"### {x['nome']} (`{x['id']}`)")
            lines += [f"- `{c['campo']}`: {_short(c['antes'])} → {_short(c['depois'])}" for c in x["mudancas"]]
            lines.append("")
    o = result.get("skills_sem_gem") or {}
    if any(o.values()):
        lines += ["## Skills sem gem (monstros, minions, disparadas): só contadas", ""]
        for k in ("novas", "removidas", "alteradas"):
            if o.get(k):
                lines.append(f"- {k}: {len(o[k])}: " + ", ".join(o[k][:40]) + (" …" if len(o[k]) > 40 else ""))
        lines.append("")
    t = result.get("arvore")
    if t:
        if t["novos"]:
            lines += ["## Nós novos", ""] + [f"- {x['nome']} ({x['hash']}){' · keystone' if x['keystone'] else ''}{' · notável' if x['notavel'] else ''}"
                                             f"{' · ' + x['ascendancy'] if x['ascendancy'] else ''}: {_short(x['stats'])}" for x in t["novos"]] + [""]
        if t["removidos"]:
            lines += ["## Nós removidos", ""] + [f"- {x['nome']} ({x['hash']})" for x in t["removidos"]] + [""]
        if t["alterados"]:
            lines += ["## Nós alterados", ""]
            for x in t["alterados"]:
                lines.append(f"- **{x['nome']}** ({x['hash']}): " + "; ".join(
                    f"`{c['campo']}` {_short(c['antes'])} → {_short(c['depois'])}" for c in x["mudancas"]))
            lines.append("")
    return "\n".join(lines)


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", str(name)).strip() or "diff"


def run(antes=None, depois=None, name: str | None = None, out_dir: Path | None = None) -> dict:
    """Resolve as pastas (antes = importada na base; depois = snapshot mais recente), faz o diff e grava .md e .json."""
    from . import storage
    root = storage.DATA / "raw" / "snapshots"
    old = Path(antes) if antes else (imported_folder() or (storage.DATA / "raw" / "repoe"))
    if not has_catalog(old):
        raise ValueError(f"pasta de antes sem {GEMS}/{SKILLS}: {old}. Informe antes=<pasta do RePoE>.")
    new = Path(depois) if depois else latest_snapshot(root, exclude=old)
    if new is None:
        raise ValueError(f"nenhum snapshot baixado além do importado em {root}. Baixe a versão nova (Atualizar) ou informe depois=<pasta>.")
    if not has_catalog(new):
        raise ValueError(f"pasta de depois sem {GEMS}/{SKILLS}: {new}")
    result = diff(old, new)
    out_dir = Path(out_dir or (storage.DATA.parent / "builds-teste" / "patch"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe(name or f"diff {result['antes']['versao']} - {result['depois']['versao']} {time.strftime('%Y-%m-%d')}")
    md, js = out_dir / f"{stem}.md", out_dir / f"{stem}.json"
    md.write_text(to_markdown(result), encoding="utf-8")
    js.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"resumo": result["resumo"], "total": result["total"], "antes": result["antes"], "depois": result["depois"],
            "relatorio": str(md), "json": str(js),
            "aviso": "mudança nos dados, não buff ou nerf; skill, keystone ou ascendência nova não é simulável por hipótese"}
