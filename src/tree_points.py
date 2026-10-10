from __future__ import annotations

from collections import Counter, defaultdict

TREE_NODE_KINDS = {
    "PASSIVE", "NOTABLE", "KEYSTONE", "JEWEL_SOCKET",
    "ASCENDANCY_NODE", "TREE_START", "TREE_DECORATION",
}
SEMANTIC_RELATIONS = {
    "PRODUCES", "ENABLES", "AMPLIFIES", "REDUCES", "MODIFIES",
    "REQUIRES", "PREVENTS", "CONSUMES", "GENERATES", "CREATES",
    "PREVENTS_CONSUMPTION",
}


def _s(v):
    return "" if v is None else str(v).strip()


def _refs(tree: dict) -> list[dict]:
    tree = tree or {}
    refs = []

    base = tree.get("base_hashes")
    if base is None:
        base = tree.get("node_refs")
    if base is None:
        base = tree.get("nodes")
    for value in base or []:
        if _s(value):
            refs.append({
                "ref": _s(value),
                "pool": "base",
                "specialisation": "",
            })

    specialisations = tree.get("specialisations") or {}
    if isinstance(specialisations, dict):
        for key, values in specialisations.items():
            for value in values or []:
                if _s(value):
                    refs.append({
                        "ref": _s(value),
                        "pool": "specialisation",
                        "specialisation": _s(key),
                    })
    elif isinstance(specialisations, list):
        for value in specialisations:
            if _s(value):
                refs.append({
                    "ref": _s(value),
                    "pool": "specialisation",
                    "specialisation": "",
                })

    return refs


def _maps(catalog):
    by_hash = {}
    by_node_id = {}
    by_source = {}

    for e in catalog.ordered:
        if e.get("kind") not in TREE_NODE_KINDS:
            continue
        if e.get("raw_dataset") != "tree_nodes":
            continue

        for value in (e.get("node_hash"),):
            if _s(value):
                by_hash[_s(value)] = e

        for value in (e.get("node_id"), e.get("raw_key")):
            if _s(value):
                by_node_id[_s(value)] = e

        sid = _s(e.get("source_id"))
        if sid:
            by_source[sid] = e
            if sid.startswith("node:"):
                by_node_id.setdefault(sid[5:], e)

    return by_hash, by_node_id, by_source


def _point_cost(e: dict):
    meta = e.get("node_meta") or {}
    raw = meta.get("skill_points")
    if raw is None:
        raw = meta.get("skillPoints")

    if isinstance(raw, bool):
        raw = None

    if isinstance(raw, (int, float)) and raw > 0:
        return raw, True

    # Most selectable allocations are one point. We keep the fact that this is
    # the normal unit separate from explicitly declared multi-point metadata.
    if e.get("selectable", True) and e.get("kind") not in {"TREE_START", "TREE_DECORATION"}:
        return 1, False

    return 0, False


def _stats_preview(e: dict) -> list[str]:
    texts = []
    for row in e.get("texts", []):
        text = _s(row.get("text"))
        if text and text not in texts:
            texts.append(text)
        if len(texts) >= 4:
            break

    if not texts:
        for row in e.get("stats", [])[:4]:
            texts.append(f"{row.get('id')} = {row.get('value')}")
    return texts


def _node_row(e: dict, ref: dict) -> dict:
    cost, explicit = _point_cost(e)
    return {
        "resolved": True,
        "entity_id": e.get("id"),
        "ref": ref["ref"],
        "pool": ref["pool"],
        "specialisation": ref.get("specialisation", ""),
        "name": e.get("name") or ref["ref"],
        "kind": e.get("kind") or "PASSIVE",
        "node_hash": e.get("node_hash"),
        "node_id": e.get("node_id"),
        "ascendancy": e.get("ascendancy") or "",
        "ascendancy_id": e.get("ascendancy_id") or "",
        "is_notable": bool(e.get("is_notable")),
        "is_keystone": bool(e.get("is_keystone")),
        "selectable": bool(e.get("selectable", True)),
        "point_cost": cost,
        "point_cost_explicit": explicit,
        "summary": e.get("summary") or "",
        "stats_preview": _stats_preview(e),
        "tags": list(e.get("tags") or []),
    }


def analyze(catalog, build_summary: dict) -> dict:
    tree = (build_summary or {}).get("tree") or {}
    refs = _refs(tree)
    by_hash, by_node_id, by_source = _maps(catalog)

    nodes = []
    unresolved = []
    seen = set()

    for ref in refs:
        dedupe_key = (ref["pool"], ref.get("specialisation", ""), ref["ref"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        value = ref["ref"]
        e = (
            by_hash.get(value)
            or by_node_id.get(value)
            or by_source.get(value)
            or by_source.get("node:" + value)
        )

        if not e:
            row = {
                "resolved": False,
                "entity_id": None,
                "ref": value,
                "pool": ref["pool"],
                "specialisation": ref.get("specialisation", ""),
                "name": f"Nó {value}",
                "kind": "UNRESOLVED",
                "point_cost": None,
                "point_cost_explicit": False,
                "summary": "",
                "stats_preview": [],
                "tags": [],
            }
            nodes.append(row)
            unresolved.append(row)
            continue

        nodes.append(_node_row(e, ref))

    resolved = [n for n in nodes if n["resolved"]]
    selectable = [
        n for n in resolved
        if n["selectable"] and n["kind"] not in {"TREE_START", "TREE_DECORATION"}
    ]

    by_kind = Counter(n["kind"] for n in resolved)
    base_refs = [n for n in nodes if n["pool"] == "base"]
    spec_refs = [n for n in nodes if n["pool"] == "specialisation"]

    explicit_cost_total = sum(
        n["point_cost"]
        for n in selectable
        if n["point_cost_explicit"] and isinstance(n["point_cost"], (int, float))
    )
    detected_point_units = sum(
        n["point_cost"]
        for n in selectable
        if isinstance(n["point_cost"], (int, float))
    )

    # Mechanics represented by allocated resolved nodes.
    mechanics = {}
    for n in resolved:
        e = catalog.entries.get(n["entity_id"]) if n["entity_id"] else None
        if not e:
            continue
        for link in e.get("links", []):
            if link.get("relation") not in SEMANTIC_RELATIONS:
                continue
            concept = _s(link.get("concept"))
            if not concept:
                continue
            bucket = mechanics.setdefault(concept, {
                "concept": concept,
                "label": _s(link.get("label")) or concept,
                "count": 0,
                "relations": set(),
                "nodes": [],
            })
            bucket["count"] += 1
            bucket["relations"].add(link.get("relation"))
            if n["name"] not in bucket["nodes"]:
                bucket["nodes"].append(n["name"])

    mechanics_rows = []
    for value in mechanics.values():
        mechanics_rows.append({
            "concept": value["concept"],
            "label": value["label"],
            "count": value["count"],
            "relations": sorted(value["relations"]),
            "nodes": value["nodes"][:12],
        })
    mechanics_rows.sort(key=lambda x: (-x["count"], x["label"].casefold()))

    quest_stats = tree.get("quest_stats") or []

    return {
        "source_type": build_summary.get("source_type") or "pob-xml",
        "tree_version": tree.get("tree_version"),
        "catalog_tree_version": catalog.tree_meta.get("repoe_version"),
        "allocated_nodes_reported": int(tree.get("allocated_nodes") or len(refs)),
        "references_total": len(nodes),
        "resolved": len(resolved),
        "unresolved": len(unresolved),
        "coverage_pct": round((len(resolved) / len(nodes) * 100), 1) if nodes else 0,
        "base_references": len(base_refs),
        "specialisation_references": len(spec_refs),
        "detected_point_units": detected_point_units,
        "explicit_multi_point_units": explicit_cost_total,
        "breakdown": {
            "passive": by_kind.get("PASSIVE", 0),
            "notable": by_kind.get("NOTABLE", 0),
            "keystone": by_kind.get("KEYSTONE", 0),
            "jewel_socket": by_kind.get("JEWEL_SOCKET", 0),
            "ascendancy": by_kind.get("ASCENDANCY_NODE", 0),
            "tree_start": by_kind.get("TREE_START", 0),
            "decoration": by_kind.get("TREE_DECORATION", 0),
        },
        "nodes": nodes,
        "unresolved_refs": unresolved,
        "mechanics": mechanics_rows[:40],
        "quest_stats": quest_stats,
        "notes": [
            "Pontos restantes não são estimados: o Finder mostra apenas alocações observadas na fonte.",
            "Nós não resolvidos permanecem visíveis; não são descartados nem renomeados por aproximação.",
            "Pontos de especialização da GGG são mantidos separados dos hashes base.",
        ],
    }
