"""Leitura dos dados do PoB instalado: bases, mods, gems e efeitos de qualidade.

Nada aqui é inventado: os coeficientes vêm dos arquivos Data/*.lua do checkout
configurado em data/pob/engine_config.json.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from src import pob_engine, storage

# família de gem (crafting_type) -> classe que começa com a arma, arquivo de bases e filtro da base
FAMILY = {
    "Quarterstaff": ("Monk", "staff.lua", "Quarterstaff"),
    "Spear": ("Huntress", "spear.lua", "Spear"),
    "Mace": ("Warrior", "mace.lua", "Two Hand"),
    "Bow": ("Ranger", "bow.lua", "Bow"),
    "Crossbow": ("Mercenary", "crossbow.lua", "Crossbow"),
    "Elemental": ("Sorceress", None, None),
    "Occult": ("Witch", None, None),
    "Primal": ("Druid", None, None),
}
# bases de liga/variantes que não existem na campanha normal
_SKIP_BASES = ("Runemastered", "Runeforged")


def pob_data_dir() -> Path:
    src = pob_engine._expand(pob_engine.load_config().get("pob_src_path"))
    if not src or not (src / "Data").is_dir():
        raise FileNotFoundError("PoB não configurado: use Build atual → Motor PoB → Detectar.")
    return src / "Data"


def max_roll(text: str) -> str:
    """'(5-8)' -> '8': o teto da faixa."""
    return re.sub(r"\((-?[\d.]+)-(-?[\d.]+)\)", lambda m: m.group(2), text)


@lru_cache(maxsize=None)
def load_bases(file: str) -> tuple:
    text = (pob_data_dir() / "Bases" / file).read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'itemBases\["([^"]+)"\] = \{(.*?)\n\}', text, re.S):
        name, body = m.group(1), m.group(2)
        if "hidden = true" in body or any(s in name for s in _SKIP_BASES):
            continue
        tags = set(re.findall(r"(\w+) = true", re.search(r"tags = \{(.*?)\}", body).group(1)))
        lvl = re.search(r"req = \{[^}]*level = (\d+)", body)
        implicit = re.search(r'implicit = "([^"]*)"', body)
        kind = re.search(r'type = "([^"]+)"', body)
        sub = re.search(r'subType = "([^"]+)"', body)
        phys = re.search(r"PhysicalMin = (\d+), PhysicalMax = (\d+)", body)
        out.append({
            "name": name, "tags": frozenset(tags), "level": int(lvl.group(1)) if lvl else 1,
            "type": kind.group(1) if kind else "", "subtype": sub.group(1) if sub else "",
            "implicit": max_roll(implicit.group(1)).replace("\\n", "\n") if implicit else "",
            "physical": (int(phys.group(1)), int(phys.group(2))) if phys else None,
            "elemental": bool(re.search(r"(Fire|Cold|Lightning|Chaos)Min", body)),
        })
    return tuple(out)


def weapon_for(family: str, level: int) -> str | None:
    """Base branca mais alta da família que o nível permite, sem dano elemental embutido."""
    _cls, file, needle = FAMILY[family]
    if not file:
        return None
    ok = [b for b in load_bases(file) if b["level"] <= level and b["physical"] and not b["elemental"]
          and needle in f'{b["name"]} {b["type"]} {b["subtype"]}']
    ok.sort(key=lambda b: (b["level"], b["physical"]))
    return ok[-1]["name"] if ok else None


@lru_cache(maxsize=None)
def load_mods() -> tuple:
    text = (pob_data_dir() / "ModItem.lua").read_text(encoding="utf-8")
    mods = []
    pattern = (r'\n\t\["([^"]+)"\] = \{ type = "(Prefix|Suffix)", affix = "[^"]*", (.*?), statOrder = .*?level = (\d+), '
               r'group = "([^"]+)", weightKey = \{(.*?)\}, weightVal = \{(.*?)\}')
    for m in re.finditer(pattern, text):
        lines = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(3))
        keys = re.findall(r'"([^"]+)"', m.group(6))
        vals = [int(x) for x in re.findall(r"-?\d+", m.group(7))]
        mods.append({"id": m.group(1), "type": m.group(2), "lines": tuple(max_roll(x) for x in lines),
                     "level": int(m.group(4)), "group": m.group(5), "weights": tuple(zip(keys, vals))})
    return tuple(mods)


def applies(mod: dict, tags) -> bool:
    """Regra do PoB: vale a primeira chave de peso que casa com as tags da base."""
    for key, val in mod["weights"]:
        if key in tags:
            return val > 0
    return False


def best_tier_by_group(tags, item_level: int) -> list[dict]:
    """Um mod por grupo: o de maior tier que o nível do item permite na base."""
    best = {}
    for mod in load_mods():
        if mod["level"] <= item_level and applies(mod, tags):
            if mod["group"] not in best or mod["level"] > best[mod["group"]]["level"]:
                best[mod["group"]] = mod
    return list(best.values())


def item_text(base: dict, mods, item_level: int, rarity: str = "RARE", name: str = "Plano") -> str:
    lines = [f"Rarity: {rarity}", name, base["name"], f"Item Level: {item_level}"]
    if base["implicit"]:
        imp = base["implicit"].split("\n")
        lines.append(f"Implicits: {len(imp)}")
        lines += imp
    else:
        lines.append("Implicits: 0")
    for mod in mods:
        lines += list(mod["lines"])
    return "\n".join(lines)


def skills_by_family() -> dict[str, list[tuple[int, str]]]:
    """Skills ativas lançadas, por família, com o tier de criação (do catálogo RePoE do Finder)."""
    out = {}
    with storage.connect() as c:
        for row in c.execute("SELECT payload FROM raw_records WHERE dataset='gems'"):
            g = json.loads(row["payload"])
            if g.get("gem_type") != "active" or (g.get("base_item") or {}).get("release_state") != "released":
                continue
            tier = g.get("crafting_level") or 0
            if tier < 1:
                continue
            for fam in g.get("crafting_types") or []:
                out.setdefault(fam, []).append((tier, g["base_item"]["display_name"]))
    return {k: sorted(v) for k, v in out.items()}


@lru_cache(maxsize=None)
def quality_effects() -> dict[str, dict]:
    """Por gem: efeito normal e efeito adicional de qualidade (Advanced Thaumaturgy), por 1% de qualidade."""
    data = pob_data_dir()
    gems = (data / "Gems.lua").read_text(encoding="utf-8")
    granted = {}
    for m in re.finditer(r'\["Metadata/Items/Gems?/[^"]+"\] = \{(.*?)\n\t\},', gems, re.S):
        body = m.group(1)
        n = re.search(r'name = "([^"]+)"', body)
        ge = re.search(r'grantedEffectId = "([^"]+)"', body)
        t = re.search(r"Tier = (\d+)", body)
        if n and ge:
            granted[ge.group(1)] = (n.group(1), int(t.group(1)) if t else 0)
    out = {}
    for f in sorted(os.listdir(data / "Skills")):
        if not f.endswith(".lua"):
            continue
        text = (data / "Skills" / f).read_text(encoding="utf-8")
        for sid, body in re.findall(r'skills\["([^"]+)"\] = \{(.*?)\n\tlevels = ', text, re.S):
            if sid not in granted:
                continue
            q = re.search(r"\n\tqualityStats = \{(.*?)\n\t\},", body, re.S)
            a = re.search(r"altQualityStats = \{(.*?)\n\t\},", body, re.S)
            name, tier = granted[sid]
            out[name] = {
                "tier": tier,
                "quality": [(s, float(v)) for s, v in re.findall(r'\{ "([^"]+)", ([\d.\-]+)', q.group(1))] if q else [],
                "additional": [(s, float(v)) for s, v in re.findall(r'\{ "([^"]+)", ([\d.\-]+)', a.group(1))] if a else [],
            }
    return out
