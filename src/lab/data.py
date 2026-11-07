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


def data_file(*parts: str) -> Path:
    """Arquivo de Data/ do PoB com a camada pob-layer por cima (dados regenerados do cliente, se houver)."""
    from ..pob_layer import resolve
    return resolve(pob_data_dir().parent, "/".join(("Data",) + parts))


def data_files(folder: str, suffix: str = ".lua") -> list[Path]:
    """Arquivos de Data/<folder>/ do PoB e da camada (a camada vence no mesmo nome), em ordem de nome."""
    from ..pob_layer import LAYER_DIR
    names = set()
    for base in (pob_data_dir() / folder, LAYER_DIR / "Data" / folder):
        if base.is_dir():
            names.update(f for f in os.listdir(base) if f.endswith(suffix))
    return [data_file(folder, n) for n in sorted(names)]


def max_roll(text: str) -> str:
    """'(5-8)' -> '8': o teto da faixa."""
    return re.sub(r"\((-?[\d.]+)-(-?[\d.]+)\)", lambda m: m.group(2), text)


@lru_cache(maxsize=None)
def load_bases(file: str, include_league: bool = False) -> tuple:
    """Bases de Data/Bases/<file>. include_league=True traz também as de liga (`liga`) e as ocultas no PoB
    (`oculta`: hidden = true), que a campanha não dá; o juiz precisa delas para reconhecer o item e
    classificá-lo como degrau 4."""
    text = data_file("Bases", file).read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'itemBases\["([^"]+)"\] = \{(.*?)\n\}', text, re.S):
        name, body = m.group(1), m.group(2)
        league = any(s in name for s in _SKIP_BASES)
        hidden = "hidden = true" in body
        if (hidden or league) and not include_league:
            continue
        limit = re.search(r"socketLimit = (\d+)", body)
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
            "liga": league, "oculta": hidden, "socket_limit": int(limit.group(1)) if limit else None,
        })
    return tuple(out)


@lru_cache(maxsize=None)
def all_bases() -> dict:
    """Todas as bases de Data/Bases/*.lua por nome, inclusive as de liga (sem frascos)."""
    out = {}
    for f in (p.name for p in data_files("Bases")):
        if f not in ("flask.lua",):
            for b in load_bases(f, include_league=True):
                out.setdefault(b["name"], {**b, "file": f})
    return out


_RANGE = re.compile(r"\((-?[\d.]+)-(-?[\d.]+)\)")


@lru_cache(maxsize=None)
def load_affixes() -> tuple:
    """Prefixos e sufixos de ModItem.lua com as faixas de valor ("(a-b)" preservado), para o juiz.

    Cada mod: {id, type, lines, level (item level mínimo), group, weights, tags}. Mods com peso 0 em toda
    base (essência, corrupção) ficam de fora: não saem de drop nem de craft comum.
    """
    text = data_file("ModItem.lua").read_text(encoding="utf-8")
    mods = []
    for m in re.finditer(r'\n\t\["([^"]+)"\] = \{ type = "(Prefix|Suffix)", affix = "[^"]*", (.*?), statOrder = .*?level = (\d+), '
                         r'group = "([^"]+)", weightKey = \{(.*?)\}, weightVal = \{(.*?)\}, modTags = \{(.*?)\}', text):
        weights = tuple(zip(re.findall(r'"([^"]+)"', m.group(6)), [int(x) for x in re.findall(r"-?\d+", m.group(7))]))
        if not any(v > 0 for _k, v in weights):
            continue
        mods.append({"id": m.group(1), "type": m.group(2), "lines": tuple(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(3))),
                     "level": int(m.group(4)), "group": m.group(5), "weights": weights,
                     "tags": frozenset(re.findall(r'"([^"]+)"', m.group(8)))})
    return tuple(mods)


def affix_pool(base: dict) -> list[dict]:
    """Mods que podem existir na base (qualquer item level): peso > 0 na primeira tag da base que casa."""
    return [m for m in load_affixes() if applies(m, base["tags"])]


@lru_cache(maxsize=None)
def _gems_by_name() -> dict[str, dict]:
    """Gems.lua + Skills/*.lua do PoB: nome (casefold) -> {name, effect, lineage, support, levels}.

    levels = {nível da gem: nível de personagem exigido}, do levelRequirement do efeito concedido.
    """
    reqs = {}
    for f in data_files("Skills"):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r'skills\["([^"]+)"\] = \{(.*?)\n\}', text, re.S):
            lv = re.search(r"\n\tlevels = \{(.*)", m.group(2), re.S)
            if lv:
                table = {int(a): int(b) for a, b in re.findall(r"\[(\d+)\] = \{[^{}]*?levelRequirement = (\d+)", lv.group(1))}
                if table:
                    reqs[m.group(1)] = table
    out = {}
    text = data_file("Gems.lua").read_text(encoding="utf-8")
    for body in re.findall(r'\n\t\["Metadata/Items/Gems?/[^"]+"\] = \{(.*?)\n\t\}', text, re.S):
        name = re.search(r'\n\t\tname = "([^"]+)"', body)
        effect = re.search(r'grantedEffectId = "([^"]+)"', body)
        if not (name and effect):
            continue
        gem_type = re.search(r'gemType = "([^"]*)"', body)
        tags = re.search(r"\n\t\ttags = \{(.*?)\n\t\t\}", body, re.S)
        out.setdefault(name.group(1).casefold(), {
            "name": name.group(1), "effect": effect.group(1), "lineage": "lineage = true" in body,
            "support": bool(gem_type and "Support" in gem_type.group(1)), "levels": reqs.get(effect.group(1)) or {},
            "tags": frozenset(re.findall(r"(\w+) = true", tags.group(1))) if tags else frozenset()})
    return out


@lru_cache(maxsize=None)
def gem_tiers() -> dict[str, int]:
    """Tier de cada gem (crafting_level do RePoE, por nome casefold): o nível de gema bruta (uncut) de que ela é
    cortada. 0 = não sai de gema bruta (concedida por item ou nó, lineage). Vazio sem o catálogo importado."""
    out = {}
    try:
        with storage.connect() as c:
            for row in c.execute("SELECT source_id, payload FROM raw_records WHERE dataset='gems'"):
                g = json.loads(row["payload"])
                name = (g.get("base_item") or {}).get("display_name")
                if name and isinstance(g.get("crafting_level"), int):
                    out.setdefault(str(name).casefold(), g["crafting_level"])
    except Exception:
        return {}
    return out


def gem_info(name: str) -> dict | None:
    """Gem do PoB pelo nome (aceita o sufixo " Support"); None se o PoB não a conhece. Traz `tier` do catálogo."""
    wanted = str(name or "").strip().casefold()
    table = _gems_by_name()
    info = table.get(wanted) or table.get(wanted.removesuffix(" support"))
    if info is None:
        return None
    return {**info, "tier": gem_tiers().get(info["name"].casefold())}


def gem_levels(name: str) -> dict | None:
    """Nível de personagem exigido por nível de gem; None fora do PoB (o chamador usa a tabela usual)."""
    info = gem_info(name)
    return (info or {}).get("levels") or None


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
def load_mods(file: str = "ModItem.lua") -> tuple:
    """Afixos de um arquivo Data/Mod*.lua do PoB (ModItem.lua por padrão; ModJewel.lua para joias)."""
    return parse_mods_text(data_file(file).read_text(encoding="utf-8"))


def parse_mods_text(text: str) -> tuple:
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


_UNIQUE_META = re.compile(r"^(League|Requires|Implicits|Variant|Source|Limited to|Has Alt Variant|Selected Variant|"
                          r"Selected Alt Variant|Sockets|LevelReq|Radius|Talisman Tier|Upgrade|Drop|Changelog|Elder Item|"
                          r"Shaper Item|Historic$|Corrupted$)\b")
_UNIQUE_PREFIX = re.compile(r"^(\{[^}]*\})+")


def parse_uniques_text(text: str) -> list[dict]:
    """Blocos [[ ... ]] dos arquivos Data/Uniques do PoB -> {name, base, league, lines}.

    Fica só a variante atual (a última declarada) e o teto da faixa de cada mod.
    """
    out = []
    for block in re.findall(r"\[\[\n(.*?)\n\]\]", text, re.S):
        raw = [l.rstrip() for l in block.split("\n") if l.strip()]
        if len(raw) < 2:
            continue
        name, rest = raw[0], raw[1:]
        variants = sum(1 for l in rest if l.startswith("Variant:"))
        league = next((l.split(":", 1)[1].strip() for l in rest if l.startswith("League:")), "")
        radius = next((l.split(":", 1)[1].strip() for l in rest if l.startswith("Radius:")), "")

        def current(l):
            tags = re.findall(r"\{(\w+):([^}]*)\}", l)
            chosen = next((v for k, v in tags if k == "variant"), None)
            return chosen is None or not variants or str(variants) in [x.strip() for x in chosen.split(",")]

        # A base pode mudar por variante: "{variant:1}Ironclad Vestments" / "{variant:2}Gilded Vest".
        bases = []
        for l in rest:
            clean = _UNIQUE_PREFIX.sub("", l).strip()
            if _UNIQUE_META.match(clean) or re.search(r"[\d%+]", clean):
                break
            bases.append((current(l), clean))
        base = next((b for ok, b in bases if ok), bases[0][1] if bases else "")
        body = rest[len(bases):]
        lines = []
        for l in body:
            if not current(l):
                continue
            clean = _UNIQUE_PREFIX.sub("", l).strip()
            if not clean or _UNIQUE_META.match(clean):
                continue
            lines.append(max_roll(clean))
        if lines:
            out.append({"name": name, "base": base, "league": league, "lines": lines, "radius": radius})
    return out


@lru_cache(maxsize=None)
def load_uniques() -> tuple:
    """Todos os uniques do PoB (sem os gerados/de corrida da pasta Special)."""
    out = []
    for f in data_files("Uniques"):
        out.extend(parse_uniques_text(f.read_text(encoding="utf-8")))
    new = data_file("Uniques", "Special", "New.lua")
    if new.exists():
        out.extend(parse_uniques_text(new.read_text(encoding="utf-8")))
    return tuple(out)


@lru_cache(maxsize=None)
def quality_effects() -> dict[str, dict]:
    """Por gem: efeito normal e efeito adicional de qualidade (Advanced Thaumaturgy), por 1% de qualidade."""
    gems = data_file("Gems.lua").read_text(encoding="utf-8")
    granted = {}
    for m in re.finditer(r'\["Metadata/Items/Gems?/[^"]+"\] = \{(.*?)\n\t\},', gems, re.S):
        body = m.group(1)
        n = re.search(r'name = "([^"]+)"', body)
        ge = re.search(r'grantedEffectId = "([^"]+)"', body)
        t = re.search(r"Tier = (\d+)", body)
        if n and ge:
            granted[ge.group(1)] = (n.group(1), int(t.group(1)) if t else 0)
    out = {}
    for f in data_files("Skills"):
        text = f.read_text(encoding="utf-8")
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


# ---------- augments de item (Runes, Soul Cores, Idols) e Timeless ----------
def parse_augments_text(text: str) -> list[dict]:
    """Data/ModRunes.lua -> [{name, type, slots: {slot: [linhas]}}]. Linhas "Bonded:" ficam como estão."""
    out = []
    for name, body in re.findall(r'\n\t\["([^"]+)"\] = \{(.*?)\n\t\},', text, re.S):
        slots, kind = {}, ""
        for slot, inner in re.findall(r'\n\t\t\["([^"]+)"\] = \{(.*?)\n\t\t\},', body, re.S):
            t = re.search(r'type = "(\w+)"', inner)
            kind = kind or (t.group(1) if t else "")
            lines = [max_roll(l) for l in re.findall(r'\n\t{4}"((?:[^"\\]|\\.)*)",', inner)]
            if lines:
                slots[slot] = lines
        if slots:
            out.append({"name": name, "type": kind, "slots": slots})
    return out


@lru_cache(maxsize=None)
def load_augments() -> tuple:
    return tuple(parse_augments_text(data_file("ModRunes.lua").read_text(encoding="utf-8")))


def parse_timeless_text(text: str) -> list[dict]:
    """TimelessJewelData/LegionPassives.lua -> passivas concedidas: {id, legion, name, lines, kind}.

    `kind` é keystone, notable ou small. Uma entrada por passiva concedida, não por seed.
    """
    out = []
    for body in re.findall(r"\n\t\t\{\n(.*?)\n\t\t\},", text, re.S):
        pid = re.search(r'\["id"\] = "([^"]+)"', body)
        name = re.search(r'\["dn"\] = "([^"]+)"', body)
        sd = re.search(r'\["sd"\] = \{(.*?)\n\t\t\t\}', body, re.S)
        if not (pid and name and sd):
            continue
        lines = [max_roll(l) for l in re.findall(r'"((?:[^"\\]|\\.)*)"', sd.group(1))]
        if not lines:
            continue
        legion = re.match(r"[a-z]+", pid.group(1)).group(0)
        kind = "keystone" if '["ks"] = true' in body else "notable" if '["not"] = true' in body else "small"
        out.append({"id": pid.group(1), "legion": legion, "name": name.group(1), "lines": lines, "kind": kind})
    return out


@lru_cache(maxsize=None)
def load_timeless() -> tuple:
    path = data_file("TimelessJewelData", "LegionPassives.lua")
    return tuple(parse_timeless_text(path.read_text(encoding="utf-8")))
