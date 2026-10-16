"""Busca gulosa de passivas: a cada rodada, o caminho de maior ganho por ponto medido no PoB.

O ganho é a função `measure` do chamador (quais grupos ler, quais métricas), pesada
por `weights`. Olha poucos passos à frente; não garante o ótimo.
"""
from __future__ import annotations

from src.lab.engine import Lab, score


def greedy_tree(lab: Lab, class_name: str, budget: int, measure, weights: dict, ascendancy: str | None = None,
                notable_reach: int = 6, small_reach: int = 2, forced_first: str | None = None,
                allow_keystones: bool = False, progress=None) -> dict:
    """Aloca até `budget` pontos a partir da árvore carregada; devolve a ordem e as métricas finais."""
    ctx = lab.tree_context()
    alloc = {n["id"] for n in ctx["nodes"] if n["allocated"]}
    start = set(alloc)
    base = measure()
    order, spent = [], 0

    def take(path, by_id):
        nonlocal spent
        alloc.update(path)
        lab.set_nodes(class_name, alloc, ascendancy)
        for nid in path:
            spent += 1
            n = by_id[nid]
            order.append({"ponto": spent, "id": nid, "nome": n["name"], "tipo": n["kind"], "stats": n["stats"]})

    if forced_first:
        by_id = {n["id"]: n for n in ctx["nodes"]}
        target = min((n for n in ctx["nodes"] if n["name"] == forced_first and n.get("path_distance")),
                     key=lambda n: n["path_distance"])
        take(lab.plan(target["id"])["add_ids"], by_id)
        base = measure()

    while spent < budget:
        ctx = lab.tree_context()
        by_id = {n["id"]: n for n in ctx["nodes"]}
        remaining, best = budget - spent, None
        for n in ctx["nodes"]:
            d = n.get("path_distance")
            if n["allocated"] or n.get("ascendancy") or not n.get("editable") or not d or d > remaining:
                continue
            if n["kind"] == "Keystone" and not allow_keystones:
                continue
            if (n["kind"] == "Notable" and d > notable_reach) or (n["kind"] not in ("Notable", "Keystone") and d > small_reach):
                continue
            try:
                path = lab.plan(n["id"])["add_ids"]
            except Exception:
                continue
            if not path or len(path) > remaining:
                continue
            lab.set_nodes(class_name, alloc | set(path), ascendancy)
            m = measure()
            gain = score(m, base, weights) / len(path)
            if best is None or gain > best[0]:
                best = (gain, path, m)
        lab.set_nodes(class_name, alloc, ascendancy)
        if not best or best[0] <= 1e-6:
            break
        _gain, path, base = best
        take(path, by_id)
        if progress:
            progress(f"{spent}/{budget} -> {order[-1]['nome']} {base}")
    return {"ordem": order, "final": base, "nos": sorted(alloc - start)}
