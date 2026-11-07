"""Melhor gear para um nível: cada base e cada mod permitido é testado no PoB e entra pelo ganho medido.

Produz duas versões por slot: "rare" (3 prefixos + 3 sufixos no teto da faixa, o limite
teórico) e "magic" (melhor prefixo + melhor sufixo, o que dá para achar na campanha). Na trilha campanha
(etapa abaixo do nível de mapas) o drop não é escolhido: `judge.CAMPAIGN_GEAR` limita quantas peças têm afixo
e quantos afixos cada uma; as de menor ganho medido voltam a base branca.
"""
from __future__ import annotations

from src.lab import data, judge
from src.lab.engine import Lab, score

ARMOUR_SLOTS = (("Body Armour", "body.lua"), ("Helmet", "helmet.lua"), ("Gloves", "gloves.lua"), ("Boots", "boots.lua"))
JEWELLERY_SLOTS = (("Amulet", "amulet.lua"), ("Ring 1", "ring.lua"), ("Ring 2", "ring.lua"), ("Belt", "belt.lua"))


def default_slots(weapon_file: str, weapon_tag: str, armour_tags) -> list[tuple]:
    """(slot, arquivo de bases, filtro) para uma arma de duas mãos e um conjunto de armaduras."""
    armour_tags = set(armour_tags)
    slots = [("Weapon 1", weapon_file, lambda b: weapon_tag in b["tags"])]
    slots += [(slot, file, lambda b: bool(b["tags"] & armour_tags)) for slot, file in ARMOUR_SLOTS]
    slots += [(slot, file, lambda b: True) for slot, file in JEWELLERY_SLOTS]
    return slots


def cap_affixes(gains, pre: list, suf: list, per_piece: int) -> tuple[list, list]:
    """Os melhores afixos medidos (gains ordenado por ganho) até `per_piece`, mantendo a divisão prefixo/sufixo."""
    if len(pre) + len(suf) <= per_piece:
        return pre, suf
    best = [m for _g, m in gains if m in pre or m in suf][:per_piece]
    return [m for m in pre if m in best], [m for m in suf if m in best]


def over_budget(chosen: dict, pieces: int) -> list[str]:
    """Slots com afixo além das `pieces` de maior ganho medido (voltam a base branca)."""
    affixed = sorted((s for s, c in chosen.items() if c["prefixos"] or c["sufixos"]), key=lambda s: -chosen[s]["ganho"])
    return affixed[pieces:]


def search_gear(lab: Lab, xml: str, level: int, measure, weights: dict, slots, item_level: int | None = None,
                config: dict | None = None, prefixes: int = 3, suffixes: int = 3, progress=None,
                trilha: str | None = None) -> dict:
    item_level = item_level or level + 1
    config = config or {}
    # Campanha: drop não é escolhido. Limite de peças com afixo e de afixos por peça (judge.CAMPAIGN_GEAR).
    campanha = judge.trilha_of(level, trilha) == "campanha"
    pieces, per_piece = judge.campaign_gear(level) if campanha else (len(slots), prefixes + suffixes)

    def equip(slot, text):
        lab.equip(slot, text)

    lab.load_xml(xml, "gear")
    lab.config(config)
    start = measure()
    chosen, report, base_of = {}, [], {}
    for slot, file, keep in slots:
        bases = [b for b in data.load_bases(file) if b["level"] <= level and keep(b)]
        current = measure()
        scored = []
        for b in bases:
            try:
                equip(slot, data.item_text(b, [], item_level, "NORMAL"))
                scored.append((score(measure(), current, weights), b))
            except Exception:
                continue
        if not scored:
            continue
        base = max(scored, key=lambda x: x[0])[1]
        equip(slot, data.item_text(base, [], item_level, "NORMAL"))
        with_base = measure()
        gains = []
        for mod in data.best_tier_by_group(base["tags"], item_level):
            try:
                equip(slot, data.item_text(base, [mod], item_level))
                g = score(measure(), with_base, weights)
            except Exception:
                continue
            if g > 1e-4:
                gains.append((g, mod))
        gains.sort(key=lambda x: -x[0])
        pre = [m for _g, m in gains if m["type"] == "Prefix"][:prefixes]
        suf = [m for _g, m in gains if m["type"] == "Suffix"][:suffixes]
        pre, suf = cap_affixes(gains, pre, suf, per_piece)
        chosen[slot] = {"rare": data.item_text(base, pre + suf, item_level),
                        "magic": data.item_text(base, pre[:1] + suf[:1], item_level, "MAGIC"),
                        "prefixos": pre, "sufixos": suf}
        equip(slot, chosen[slot]["rare"])
        after = measure()
        base_of[slot] = base
        chosen[slot]["ganho"] = score(after, with_base, weights) if pre or suf else 0.0
        report.append({"slot": slot, "base": base["name"], "prefixos": [" / ".join(m["lines"]) for m in pre],
                       "sufixos": [" / ".join(m["lines"]) for m in suf],
                       "ganhos": [(round(g, 3), m["type"], " / ".join(m["lines"])) for g, m in gains[:8]], "depois": after})
        if progress:
            progress(f'{slot}: {base["name"]} {after}')

    # Peças além do limite da faixa voltam a base branca (ficam as de maior ganho medido).
    for slot in over_budget(chosen, pieces):
        white = data.item_text(base_of[slot], [], item_level, "NORMAL")
        chosen[slot].update(rare=white, magic=white, prefixos=[], sufixos=[], branca=True)
        for r in report:
            if r["slot"] == slot:
                r.update(prefixos=[], sufixos=[], branca="limite de peças com afixo da faixa (judge.CAMPAIGN_GEAR)")

    finals = {}
    for label in ("rare", "magic"):
        lab.load_xml(xml, f"gear {label}")
        lab.config(config)
        for slot, texts in chosen.items():
            equip(slot, texts[label])
        finals[label] = {"stats": measure(), "xml": lab.export_xml()}
    return {"sem_gear": start, "slots": report, "itens": chosen, "finais": finals}
