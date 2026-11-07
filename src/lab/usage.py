"""Uso real (poe.ninja) × teste de remoção no PoB × nota do mapa de âncoras.

Porte do `lab usage` do projeto PoE 1 (2026-11-05), com uma diferença: no PoE 2 a remoção também tira **nós de
ascendência e keystones**, um por vez, não só uniques e joias. O caso que motivou: o Gemling Legionnaire tinha os
nós-chave (Advanced Thaumaturgy, Essence of Virtue) em ~100% dos personagens e nota 0 no mapa.

Para cada personagem da amostra: carrega o código do PoB, mede, tira uma peça por vez e mede de novo. O delta é o
quanto aquela build perde sem a peça, com a config que o personagem exportou. Tirar um nó do meio da ascendência
desliga os que dependem dele (o PoB poda o que fica sem ligação): o delta inclui esses nós. Peças cujo valor o PoB
não modela (requisito de atributo, buff desligado na config) medem perto de zero: a tabela marca isso em vez de
tratar como "não vale".
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import statistics
import time
from collections import defaultdict
from functools import lru_cache

from src import ninja, storage
from src.economy import CATEGORY

FIELDS = ["CombinedDPS", "TotalEHP", "Life", "EnergyShield"]
CACHE = storage.DATA / "cache" / "ninja" / "remocao"
REPORTS = storage.ROOT / "builds-teste" / "uso"
NODE_KINDS = ("ascendancy", "keystone")

_ITEM = re.compile(r'<Item id="(\d+)"[^>]*>(.*?)</Item>', re.S)
# A ordem dos atributos muda entre exportações do PoB: ler cada um à parte.
_TAG = re.compile(r"<(Slot|Socket)\b[^>]*/>")
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_SPEC = re.compile(r'(<Spec\b[^>]*\bnodes=")([^"]*)(")')


def items_of(xml: str) -> dict:
    """{id: (raridade, nome, base)} dos itens do XML do PoB."""
    out = {}
    for m in _ITEM.finditer(xml):
        body = [l.strip() for l in m.group(2).splitlines() if l.strip()]
        at = next((i for i, l in enumerate(body) if l.startswith("Rarity:")), None)
        if at is None:
            continue
        rarity = body[at].split(":", 1)[1].strip()
        name = html.unescape(body[at + 1]) if at + 1 < len(body) else "?"
        base = html.unescape(body[at + 2]) if at + 2 < len(body) else ""
        out[m.group(1)] = (rarity, name, base)
    return out


def equipped(xml: str) -> list[tuple[str, str, str, str]]:
    """[(tipo, onde, id do item, tag)] do que está equipado (sem o swap de arma)."""
    slots, sockets = [], []
    for m in _TAG.finditer(xml):
        attrs = dict(_ATTR.findall(m.group(0)))
        item_id = attrs.get("itemId", "0")
        if item_id == "0":
            continue
        if m.group(1) == "Slot" and "Swap" not in attrs.get("name", "Swap"):
            slots.append(("slot", attrs["name"], item_id, m.group(0)))
        elif m.group(1) == "Socket" and attrs.get("nodeId"):
            sockets.append(("socket", attrs["nodeId"], item_id, m.group(0)))
    return slots + sockets


def without(xml: str, tag: str, item_id: str) -> str:
    return xml.replace(tag, tag.replace(f'itemId="{item_id}"', 'itemId="0"', 1), 1)


def allocated(xml: str) -> list[str]:
    m = _SPEC.search(xml)
    return [n for n in m.group(2).split(",") if n] if m else []


def without_node(xml: str, node: str) -> str:
    """O XML sem o nó na árvore ativa (o primeiro Spec)."""
    def drop(m):
        kept = [n for n in m.group(2).split(",") if n and n != node]
        return m.group(1) + ",".join(kept) + m.group(3)
    return _SPEC.sub(drop, xml, count=1)


@lru_cache(maxsize=4)
def node_index(tree_version: str = "") -> dict:
    """{id: (tipo, nome)} dos nós de ascendência (notáveis) e keystones da árvore instalada (camada por cima)."""
    from src.tree_importer import pob_tree_file
    path = pob_tree_file()
    if tree_version and path:
        from src.pob_layer import resolve
        candidate = resolve(path.parents[2], f"TreeData/{tree_version}/tree.json")
        path = candidate if candidate.is_file() else path
    if not path:
        return {}
    tree = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for key, node in (tree.get("nodes") or {}).items():
        if not isinstance(node, dict) or not node.get("name"):
            continue
        if node.get("ascendancyName") and node.get("isNotable"):
            out[str(key)] = ("ascendancy", node["name"])
        elif node.get("isKeystone"):
            out[str(key)] = ("keystone", node["name"])
    return out


def label(rarity: str, name: str, base: str, kind: str) -> str | None:
    """Uniques pelo nome; joias raras/mágicas agrupadas; o resto (raros de slot) fica de fora."""
    if rarity == "UNIQUE":
        return name
    if kind == "socket":
        return f"{rarity.title()} Jewel"
    return None


def ablate(lab, xml: str, config: dict | None = None) -> dict:
    """{base: stats, rows: [{item, tipo, raridade, onde, dps, ehp}]}; dps/ehp = fração perdida sem a peça."""
    def measure(text):
        lab.load_xml(text, "uso")
        if config:
            lab.config(config)
        s = lab.stats(FIELDS, minion=True)
        minion = s.pop("minion", None) or {}
        if not s.get("CombinedDPS") and minion.get("CombinedDPS"):
            # Build de minion/companion: o dano é o do minion (o EHP continua sendo o do personagem).
            s["CombinedDPS"], s["minion"] = minion["CombinedDPS"], True
        return s

    base = measure(xml)
    rows = []
    if not base.get("CombinedDPS"):
        return {"base": base, "rows": rows}

    def row(name, kind, rarity, where, s):
        ehp = 1 - s["TotalEHP"] / base["TotalEHP"] if base.get("TotalEHP") else None
        rows.append({"item": name, "tipo": kind, "raridade": rarity, "onde": where,
                     "dps": round(1 - (s.get("CombinedDPS") or 0) / base["CombinedDPS"], 4),
                     "ehp": None if ehp is None else round(ehp, 4)})

    info = items_of(xml)
    for kind, where, item_id, tag in equipped(xml):
        rarity, name, base_type = info.get(item_id, ("?", "?", ""))
        name_out = label(rarity, name, base_type, kind)
        if name_out:
            row(name_out, "item", rarity, where, measure(without(xml, tag, item_id)))
    version = (re.search(r'<Spec\b[^>]*\btreeVersion="([^"]+)"', xml) or [None, ""])[1]
    nodes = node_index(version)
    for node in allocated(xml):
        hit = nodes.get(node)
        if hit:
            row(hit[1], hit[0], "NÓ", node, measure(without_node(xml, node)))
    return {"base": {k: base.get(k) for k in FIELDS + ["minion"] if k in base}, "rows": rows}


def map_scores() -> dict:
    """{nome: (maior score de âncora, [verbo:recurso das arestas com score])} de uniques, joias e nós."""
    from src.economy import EconomyMap, current_map
    em = current_map()
    kinds = {"UNIQUE", "JEWEL_UNIQUE", "TIME_LOST", "TIMELESS", "ASCENDANCY_NODE", "KEYSTONE"}
    out = {}
    for r in em.records:
        if r["kind"] in kinds and r["name"]:
            out.setdefault(r["name"], (0, []))
    for e in em.edges:
        r = em.records[e["i"]]
        if r["kind"] not in kinds:
            continue
        score = EconomyMap._anchor_score(e, False)
        best, tags = out.get(r["name"], (0, []))
        if score:
            tags = tags + [f'{e["verb"]}:{e["resource"]}']
        out[r["name"]] = (max(best, score), tags)
    return out


def _cache_key(version: str, account: str, name: str, config: dict | None) -> str:
    raw = json.dumps([version, account, name, config or {}, "nos-v1"], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def run(classe: str, skill: str = "", amostra: int = 10, league: str | None = None, config: dict | None = None,
        lab_factory=None, progress=None, momento: str = "") -> dict:
    """classe: ascendência como o poe.ninja escreve (Gemling Legionnaire). momento: time machine ("day-3", "week-4")."""
    from src.lab.engine import Lab
    amostra = max(1, min(int(amostra or 10), 40))
    found = ninja.search(league, momento, **{"class": classe, "skills": skill})
    if not found["total"]:
        raise ValueError(f"nenhum personagem no poe.ninja para class={classe!r} skills={skill!r}")
    total, sample = found["total"], found["characters"][:amostra]
    rows, builds, errors = [], [], []
    CACHE.mkdir(parents=True, exist_ok=True)
    lab = None
    try:
        for account, name in sample:
            path = CACHE / f'{_cache_key(found["version"] + momento, account, name, config)}.json'
            if path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
            else:
                try:
                    xml = ninja.pob_xml(ninja.character(account, name, league, momento)["pathOfBuildingExport"])
                except Exception as exc:  # personagem privado, removido ou sem código
                    errors.append(f"{account}/{name}: {exc}")
                    continue
                if lab is None:
                    lab = (lab_factory or Lab)()
                try:
                    result = ablate(lab, xml, config)
                except Exception as exc:  # build que o PoB não carrega
                    errors.append(f"{account}/{name}: {exc}")
                    continue
                path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                time.sleep(0.5)  # educado com o poe.ninja
            builds.append(f"{account}/{name}")
            for r in result["rows"]:
                rows.append({**r, "build": f"{account}/{name}"})
            if progress:
                progress(len(builds), len(sample))
    finally:
        if lab is not None:
            lab.close()

    use = {n: c / total for n, c in found["dims"].get("items", [])}
    use.update({n: c / total for n, c in found["dims"].get("keypassives", [])})
    scores = map_scores()
    groups = defaultdict(list)
    for r in rows:
        groups[r["item"]].append(r)
    table = []
    for item, rs in groups.items():
        used_in = len({r["build"] for r in rs})
        dps = statistics.median(r["dps"] for r in rs)
        ehps = [r["ehp"] for r in rs if r["ehp"] is not None]
        ehp = statistics.median(ehps) if ehps else 0.0
        kind = rs[0].get("tipo", "item")
        known = kind != "item" or all(r["raridade"] == "UNIQUE" for r in rs)
        score, tags = scores.get(item, (0 if known else None, []))  # unique ou nó sem aresta pontuada = nota 0
        pct = use.get(item)
        if pct is None and kind != "item":
            pct = used_in / max(len(builds), 1)  # nó fora da lista de keypassives: uso na amostra
        flag = ""
        if score is not None and pct is not None and pct >= 0.2:
            if score == 0 and ehp >= 0.05 and dps < 0.03:
                flag = "força por magnitude (defesa): o PoB mede, o mapa não pontua"
            elif score == 0 and max(dps, ehp) >= 0.05:
                flag = "lacuna do leitor: muito usado, pesa no PoB e o mapa dá 0"
            elif abs(dps) < 0.01 and ehp < 0.02:
                flag = "valor fora do PoB ou condição desligada: muito usado e o teste mede ~0"
        table.append({"item": item, "tipo": kind, "uso_pct": None if pct is None else round(100 * pct, 1),
                      "amostra": f"{used_in}/{len(builds)}", "dps_sem": round(-100 * dps, 1),
                      "ehp_sem": round(-100 * ehp, 1), "dps_max_sem": round(-100 * max(r["dps"] for r in rs), 1),
                      "nota_mapa": score, "arestas": sorted(set(tags))[:4], "sinal": flag})
    table.sort(key=lambda t: (-(t["uso_pct"] or 0), t["dps_sem"]))
    # Nota alta no mapa e quase ninguém usa, no mesmo arquétipo (recursos das arestas pontuadas do que >= 20% usam).
    archetype = {tag.split(":", 1)[1] for t in table if (t["uso_pct"] or 0) >= 20
                 for tag in scores.get(t["item"], (0, []))[1]
                 if CATEGORY.get(tag.split(":", 1)[1]) in ("stack", "state", "entity")}
    from src.economy import current_map
    many = {r["name"] for r in current_map().records if (r.get("choices") or 0) >= 10}
    hidden = sorted(((s, n) for n, (s, tags) in scores.items()
                     if s >= 3 and use.get(n, 0) < 0.01 and n not in many
                     and archetype & {tag.split(":", 1)[1] for tag in tags}), reverse=True)
    out = {"ok": True, "liga": found["league"], "momento": momento or "agora",
           "filtro": {"class": classe, "skills": skill}, "personagens": total, "amostra": len(builds),
           "erros": errors[:5], "tabela": table, "nota_alta_uso_baixo": [n for _s, n in hidden[:15]],
           "uso_top": {d: ninja.usage(found["dims"], total, d, 15) for d in ("skills", "keypassives", "items")},
           "aviso": "Amostra = os primeiros personagens da lista do poe.ninja (viés para gear de topo). Delta = peça "
                    "removida (slot vazio ou nó fora da árvore, com os nós que dependiam dele), com a config "
                    "exportada; o que o PoB não modela mede ~0. Nota do mapa ordena, não é poder."}
    out["relatorio"] = write_report(out)
    return out


def write_report(out: dict) -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]+", "-", f'{out["liga"]}-{out["filtro"]["class"]}-{out["filtro"]["skills"] or "todas"}-'
                                   f'{out["momento"]}').strip("-").lower()
    lines = [f'# Uso × remoção × mapa — {out["filtro"]["class"]} {out["filtro"]["skills"]} ({out["liga"]}, '
             f'{out["momento"]})', "",
             f'{out["personagens"]} personagens no poe.ninja; amostra de {out["amostra"]}. {out["aviso"]}', "",
             "| Peça | Tipo | Uso | Amostra | DPS sem ela | EHP sem ela | Nota do mapa | Sinal |",
             "|---|---|---|---|---|---|---|---|"]
    for t in out["tabela"]:
        uso = "—" if t["uso_pct"] is None else f'{t["uso_pct"]}%'
        nota = "—" if t["nota_mapa"] is None else t["nota_mapa"]
        lines.append(f'| {t["item"]} | {t["tipo"]} | {uso} | {t["amostra"]} | {t["dps_sem"]}% | {t["ehp_sem"]}% | '
                     f'{nota} | {t["sinal"]} |')
    lines += ["", "Nota alta no mapa e uso < 1%: " + (", ".join(out["nota_alta_uso_baixo"]) or "nenhum")]
    path = REPORTS / f"{slug}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
