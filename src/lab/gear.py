"""Melhor gear para um nível: cada base e cada mod permitido é testado no PoB e entra pelo ganho medido.

Produz duas versões por slot: "rare" (3 prefixos + 3 sufixos no teto da faixa, o limite
teórico) e "magic" (melhor prefixo + melhor sufixo, o que dá para achar na campanha).
"""
from __future__ import annotations

from src.lab import data
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


def search_gear(lab: Lab, xml: str, level: int, measure, weights: dict, slots, item_level: int | None = None,
                config: dict | None = None, prefixes: int = 3, suffixes: int = 3, progress=None) -> dict:
    item_level = item_level or level + 1
    config = config or {}

    def equip(slot, text):
        lab.equip(slot, text)

    lab.load_xml(xml, "gear")
    lab.config(config)
    start = measure()
    chosen, report = {}, []
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
        chosen[slot] = {"rare": data.item_text(base, pre + suf, item_level),
                        "magic": data.item_text(base, pre[:1] + suf[:1], item_level, "MAGIC")}
        equip(slot, chosen[slot]["rare"])
        after = measure()
        report.append({"slot": slot, "base": base["name"], "prefixos": [" / ".join(m["lines"]) for m in pre],
                       "sufixos": [" / ".join(m["lines"]) for m in suf],
                       "ganhos": [(round(g, 3), m["type"], " / ".join(m["lines"])) for g, m in gains[:8]], "depois": after})
        if progress:
            progress(f'{slot}: {base["name"]} {after}')

    finals = {}
    for label in ("rare", "magic"):
        lab.load_xml(xml, f"gear {label}")
        lab.config(config)
        for slot, texts in chosen.items():
            equip(slot, texts[label])
        finals[label] = {"stats": measure(), "xml": lab.export_xml()}
    return {"sem_gear": start, "slots": report, "itens": chosen, "finais": finals}
