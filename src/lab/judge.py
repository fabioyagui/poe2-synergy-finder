"""Juiz das builds por etapas (PoE 2): aprova ou reprova cada XML do PoB com motivos e dá uma nota medida.

Porte do juiz do projeto PoE 1 (2026-10-24) com as regras do PoE 2:

- Camada 1, legalidade: pontos de passiva (nível − 1 + pontos de missão) e de ascendência (Trials) dentro
  do orçamento da etapa, soquete de joia com joia, nível mínimo das gems, atributos exigidos, nível exigido
  e item level dos itens, cada mod de item possível na base e no item level (faixas de ModItem.lua do PoB
  instalado, até 3 prefixos e 3 sufixos, um mod por grupo), soquetes de runa dentro do limite da base.
- Degraus por trilha (método do autor): supports por skill, gemas lineage, uniques e bases de liga.
- Camada 2, sustentação: Spirit reservado contra o disponível, mana/s da skill principal contra a
  regeneração, maldições contra o limite, resistências e vida + ES mínimas por faixa (`METAS`).
- Registro da âncora: toda pasta de build precisa de `ancora.md` (por que esta skill, contra quais
  alternativas, com que evidência, e a linha `Trilha:`).

A parte pura (`judge_stage`, `check_item`, `check_anchor`) recebe os fatos já medidos; `measure` e
`judge_build` usam o motor. A nota não é /100: é √(DPS × EHP) medida no PoB, comparável só entre versões
da mesma etapa, e só vale com a etapa aprovada. Em build de minion o DPS é o do minion da skill principal
(um minion, não o grupo).
"""
from __future__ import annotations

import itertools
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from src.lab import data, stages
from src.lab.engine import gem_level

# Ascensões: (nível a partir do qual o juiz supõe a ascensão feita, pontos de ascendência acumulados, nome).
# PoE 2 0.5: Trial of the Sekhemas (Ato 2) ou Trial of Chaos (Ato 3) para as duas primeiras; as duas últimas
# no fim de jogo. Níveis são escolha de método calibrável, não dado do PoB. [VERIFY in game]
ASCENSIONS = ((22, 2, "1ª ascensão"), (38, 4, "2ª ascensão"), (60, 6, "3ª ascensão"), (75, 8, "4ª ascensão"))

# Metas mínimas por faixa: (nível a partir do qual vale, resistência elemental mínima, vida + ES mínima).
# Escolha de método do juiz, não regra do jogo; a penalidade de resistência da faixa já vem da config.
METAS = (
    (1, 0, 300),      # Ato 1
    (12, 0, 500),     # Ato 2
    (28, 10, 900),    # Ato 3
    (44, 30, 1400),   # Ato 4
    (51, 45, 1900),   # Interlúdios
    (65, 75, 2800),   # mapas: resistência no teto
    (80, 75, 4000),   # mapas de tier alto
)
# Item level máximo obtível: na campanha a área acompanha o personagem (até 2 níveis acima, escolha do
# juiz); nos mapas, até a área mais alta que dá drop. [VERIFY in game] o 82.
MAX_ITEM_LEVEL, CAMPAIGN_ILVL_SLACK = 82, 2
POB_DEFAULT_PENALTY = -60  # ConfigOptions.lua do PoB 2: resistancePenalty defaultIndex 7 = "Endgame (-60%)"
MANA_FLASK_LEVEL = 28  # Atos 1–2: a sustentação vem do frasco de mana (escolha de método do juiz)
ELEMENTS = ("FireResist", "ColdResist", "LightningResist")
STAT_FIELDS = ["CombinedDPS", "TotalEHP", "TotalDPS", "TotalDot", "Duration", "Speed", "Life", "EnergyShield", "Mana", "ManaCost",
               "ManaPerSecondCost", "ManaRegenRecovery", "ManaLeechGainRate", "ManaUnreserved", "EnemyCurseLimit",
               "Spirit", "SpiritUnreserved", "Str", "ReqStr", "Dex", "ReqDex", "Int", "ReqInt", *ELEMENTS, "ChaosResist"]
GEAR_SLOTS = ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap", "Helmet", "Body Armour", "Gloves", "Boots",
              "Amulet", "Ring 1", "Ring 2", "Belt")
SWAP_SLOTS = ("Weapon 1 Swap", "Weapon 2 Swap")
AFFIX_LIMIT = {"RARE": (3, 3), "MAGIC": (1, 1), "NORMAL": (0, 0)}
MAPS_LEVEL = stages.MAPS_LEVEL
# Trilhas do método (Game Brain). Legalidade do jogo vale sempre; o que é degrau de gear só vale na campanha e
# na starter. Etapa abaixo do nível de mapas é sempre campanha; acima, a trilha declarada da build.
TRILHAS = ("campanha", "starter", "desbalanceada")
# Supports por skill: a gem começa com poucos soquetes e Jeweller's Orbs abrem até 5. Teto por trilha é escolha
# de método (o jogo permite 5 em qualquer nível): campanha 3, starter 4, desbalanceada 5.
MAX_SUPPORTS = {"campanha": 3, "starter": 4, "desbalanceada": 5}
GAME_MAX_SUPPORTS = 5
UNIQUES_ALLOWED = {"campanha": False, "starter": False, "desbalanceada": True}
DEFAULT_TRILHA = "starter"
# Config honesta: condição ligada na config precisa de um produtor na build (texto de gems, nós, itens).
# (variável do ConfigOptions.lua do PoB, regex do produtor, regex que não conta como produtor)
CONFIG_PRODUCERS = {
    "usePowerCharges": (r"Power Charge", r"maximum Power Charges|Power Charge Duration"),
    "useFrenzyCharges": (r"Frenzy Charge", r"maximum Frenzy Charges|Frenzy Charge Duration"),
    "useEnduranceCharges": (r"Endurance Charge", r"maximum Endurance Charges|Endurance Charge Duration"),
    "buffOnslaught": (r"Onslaught", None), "buffFortification": (r"Fortif", None), "buffArcaneSurge": (r"Arcane Surge", None),
    "buffTailwind": (r"Tailwind", None), "buffElusive": (r"Elusive", None),
    "multiplierWitheredStackCount": (r"\bWither", None), "conditionEnemyCursed": (r"\bCurse|\bHex\b", None),
    "conditionEnemyPoisoned": (r"Poison", None), "conditionEnemyBleeding": (r"Bleed", None),
    "conditionEnemyIgnited": (r"Ignite|\bFire\b", None), "conditionEnemyShocked": (r"Shock|Lightning", None),
    "conditionEnemyChilled": (r"Chill|\bCold\b", None), "conditionEnemyFrozen": (r"Freez|\bCold\b", None),
    "conditionEnemyIntimidated": (r"Intimidat", None), "conditionEnemyMaimed": (r"\bMaim", None),
    "conditionEnemyImmobilised": (r"Immobilis|\bPin|Freez|Heavy Stun", None), "conditionEnemyPinned": (r"\bPin", None),
    "conditionEnemyHeavyStunned": (r"Heavy Stun", None), "conditionEnemyArmourBroken": (r"Armour Break|Break Armour|Fully Broken", None),
    "conditionEnemyFireExposure": (r"Exposure", None), "conditionEnemyColdExposure": (r"Exposure", None),
    "conditionEnemyLightningExposure": (r"Exposure", None),
}
ANCHOR_FILE = "ancora.md"
ANCHOR_SECTIONS = ("Skill", "Por que", "Alternativas", "Evidência")
_TRILHA_LINE = re.compile(r"^\s*\**Trilha\**\s*:\s*\**\s*(campanha|starter|desbalanceada)", re.I | re.M)


def _fail(regra: str, motivo: str) -> dict:
    return {"regra": regra, "motivo": motivo}


def max_item_level(level: int) -> int:
    return MAX_ITEM_LEVEL if level >= MAPS_LEVEL else min(MAX_ITEM_LEVEL, level + CAMPAIGN_ILVL_SLACK)


def meta_for(level: int) -> dict:
    lvl, res, pool = max((m for m in METAS if m[0] <= level), key=lambda m: m[0])
    return {"desde": lvl, "resistencia": res, "vida_es": pool}


def ascendancy_points(level: int) -> int:
    return max((pts for lvl, pts, _n in ASCENSIONS if lvl <= level), default=0)


# ---------- leitura do XML ----------
def parse_build(xml: str) -> dict:
    """Fatos do XML do PoB que não dependem do motor."""
    root = ET.fromstring(xml)
    build = root.find("Build")
    spec_parent = root.find("Tree")
    active_spec = int(spec_parent.get("activeSpec") or 1) if spec_parent is not None else 1
    specs = root.findall("Tree/Spec")
    spec = specs[min(active_spec, len(specs)) - 1] if specs else None
    nodes = [int(x) for x in (spec.get("nodes") or "").split(",") if x.strip()] if spec is not None else []
    sockets = {int(s.get("nodeId")): int(s.get("itemId") or 0) for s in spec.iter("Socket")} if spec is not None else {}
    skills_parent = root.find("Skills")
    active_set = (skills_parent.get("activeSkillSet") or "1") if skills_parent is not None else "1"
    skill_sets = root.findall("Skills/SkillSet")
    skill_set = next((s for s in skill_sets if s.get("id") == active_set), skill_sets[0] if skill_sets else None)
    groups = []
    for skill in (skill_set if skill_set is not None else root.findall("Skills/Skill")):
        if skill.tag != "Skill":
            continue
        gems = [{"name": g.get("nameSpec") or "", "level": int(g.get("level") or 1), "enabled": g.get("enabled") != "false",
                 "quality": int(g.get("quality") or 0), "skill_id": g.get("skillId") or ""} for g in skill.findall("Gem")]
        groups.append({"enabled": skill.get("enabled") != "false", "source": skill.get("source") or "", "gems": gems})
    items = {}
    for item in root.findall("Items/Item"):
        items[int(item.get("id") or 0)] = parse_item(item.text or "")
    items_parent = root.find("Items")
    active_items = (items_parent.get("activeItemSet") or "1") if items_parent is not None else "1"
    item_sets = root.findall("Items/ItemSet")
    item_set = next((s for s in item_sets if s.get("id") == active_items), item_sets[0] if item_sets else None)
    slots = {}
    for slot in (item_set.findall("Slot") if item_set is not None else root.findall("Items/Slot")):
        item_id = int(slot.get("itemId") or 0)
        if item_id:
            slots[slot.get("name")] = item_id
    config = {}
    config_parent = root.find("Config")
    if config_parent is not None:
        active_cfg = config_parent.get("activeConfigSet") or "1"
        sets = config_parent.findall("ConfigSet")
        cfg = next((s for s in sets if s.get("id") == active_cfg), sets[0] if sets else config_parent)
        for inp in cfg.findall("Input"):
            value = inp.get("number") or inp.get("string") or inp.get("boolean")
            config[inp.get("name")] = float(value) if inp.get("number") is not None else value
    return {"level": int(build.get("level") or 1), "class": build.get("className") or "",
            "ascendancy": build.get("ascendClassName") or "", "nodes": nodes, "sockets": sockets, "groups": groups,
            "items": items, "slots": slots, "config": config}


_PREFIX_MARK = re.compile(r"^(\{[^}]*\})+")
_SPECIAL_MARKS = ("{desecrated}", "{mutated}", "{fractured}", "{crafted}")


def parse_item(text: str) -> dict:
    """Texto de item do PoB -> raridade, nome, base, item level, nível exigido, implícitos, explícitos, runas.

    No PoB 2 a contagem "Implicits:" inclui as linhas de runa e de enchant, então elas não caem nos explícitos.
    Linhas marcadas {desecrated}/{mutated}/{fractured}/{crafted} ficam em `especiais`: não saem do pool de drop.
    """
    lines = [l.strip() for l in text.replace("&apos;", "'").splitlines() if l.strip()]
    rarity = lines[0].split(":", 1)[1].strip().upper() if lines and lines[0].lower().startswith("rarity:") else ""
    body = lines[1:] if rarity else lines
    name = body[0] if body else ""
    base = body[1] if rarity in ("RARE", "UNIQUE", "RELIC") and len(body) > 1 else name
    if rarity == "MAGIC":
        base = max((b for b in data.all_bases() if b in name), key=len, default=name) if _bases_ok() else name
    head, runes = {}, []
    implicits, explicits, especiais = [], [], []
    n_imp = None
    for l in body[1:]:
        if n_imp is None:
            m = re.match(r"^([A-Za-z ]+):\s*(.*)$", l)
            if m and m.group(1) == "Implicits":
                n_imp = int(m.group(2) or 0)
                continue
            if m and m.group(1) == "Rune":
                runes.append(m.group(2))
                continue
            if m:
                head[m.group(1)] = m.group(2)
            continue
        clean = _PREFIX_MARK.sub("", l).strip()
        if not clean:
            continue
        if len(implicits) < n_imp:
            implicits.append(clean)
        elif any(mark in l for mark in _SPECIAL_MARKS):
            especiais.append(clean)
        else:
            explicits.append(clean)

    def num(key):
        try:
            return int(float(head.get(key)))
        except (TypeError, ValueError):
            return None
    sockets = (head.get("Sockets") or "").split()
    return {"rarity": rarity, "name": name, "base": base, "item_level": num("Item Level"), "level_req": num("LevelReq"),
            "implicits": implicits, "explicits": explicits, "especiais": especiais, "runes": runes,
            "rune_sockets": sum(1 for s in sockets if s == "S") if sockets else None,
            "grants": [m.group(1) for l in implicits + explicits if (m := re.match(r"Grants Skill: (?:Level \d+ )?(.+)$", l))]}


def _bases_ok() -> bool:
    try:
        data.pob_data_dir()
        return True
    except Exception:
        return False


# ---------- mods de item ----------
def _compile(line: str):
    """'+(10-24) to maximum Life' -> (regex, [(mín, máx)]); números fixos do texto ficam literais."""
    parts, ranges, pos = [], [], 0
    for m in data._RANGE.finditer(line):
        parts.append(re.escape(line[pos:m.start()]))
        parts.append(r"(-?[\d.]+)")
        lo, hi = float(m.group(1)), float(m.group(2))
        ranges.append((min(lo, hi), max(lo, hi)))
        pos = m.end()
    parts.append(re.escape(line[pos:]))
    return re.compile("^" + "".join(parts) + "$", re.I), ranges


_COMPILED: dict = {}


def _line_match(mod_line: str, item_line: str):
    """None se o formato não casa; senão (dentro da faixa?, valores, faixas)."""
    if mod_line not in _COMPILED:
        _COMPILED[mod_line] = _compile(mod_line)
    rx, ranges = _COMPILED[mod_line]
    m = rx.match(item_line)
    if not m:
        return None
    values = [float(v) for v in m.groups()]
    return all(lo - 1e-9 <= v <= hi + 1e-9 for v, (lo, hi) in zip(values, ranges)), values, ranges


def check_item(item: dict, base: dict, pool: list[dict]) -> list[dict]:
    """Reprovas de um item raro/mágico/normal: cada explícito explicado por um mod possível na base e no
    item level, sem repetir grupo, dentro do limite de prefixos e sufixos."""
    out = []
    rarity, ilvl = item["rarity"], item.get("item_level") or 1
    label = f"{item['name']} ({base['name']}, ilvl {ilvl})"
    lines = item["explicits"]
    if rarity not in AFFIX_LIMIT:
        return out
    max_pre, max_suf = AFFIX_LIMIT[rarity]
    cands = []
    for mod in pool:
        if mod["level"] > ilvl:
            continue
        options = [[i for i, l in enumerate(lines) if (r := _line_match(ml, l)) and r[0]] for ml in mod["lines"]]
        for combo in itertools.product(*options):
            if len(set(combo)) == len(combo):
                cands.append((mod, frozenset(combo)))

    def solve(remaining: frozenset, groups: frozenset, pre: int, suf: int):
        if not remaining:
            return []
        first = min(remaining)
        for mod, cover in cands:
            if first not in cover or not cover <= remaining or mod["group"] in groups:
                continue
            p, s = pre + (mod["type"] == "Prefix"), suf + (mod["type"] == "Suffix")
            if p > max_pre or s > max_suf:
                continue
            rest = solve(remaining - cover, groups | {mod["group"]}, p, s)
            if rest is not None:
                return [(mod, cover)] + rest
        return None

    if solve(frozenset(range(len(lines))), frozenset(), 0, 0) is not None:
        return out
    explained = set()
    for i, l in enumerate(lines):
        if any(i in cover for _m, cover in cands):
            explained.add(i)
            continue
        shape = [(mod, r) for mod in pool for ml in mod["lines"] if (r := _line_match(ml, l))]
        if not shape:
            out.append(_fail("gear: mod", f"{label}: '{l}' não é prefixo nem sufixo possível nesta base"))
            continue
        ok_level = [(mod, r) for mod, r in shape if mod["level"] <= ilvl]
        teto = max((r[2][0][1] for mod, r in ok_level if r[2]), default=None)
        precisa = min((mod["level"] for mod, r in shape if r[0]), default=None)
        if precisa is not None and precisa > ilvl:
            out.append(_fail("gear: tier", f"{label}: '{l}' exige item level {precisa}" +
                             (f"; o teto no ilvl {ilvl} é {teto:g}" if teto is not None else "")))
        elif shape and not any(r[0] for _m, r in shape):
            out.append(_fail("gear: tier", f"{label}: '{l}' fora de qualquer faixa da base" +
                             (f" (teto no ilvl {ilvl}: {teto:g})" if teto is not None else "")))
    if not out and explained == set(range(len(lines))):
        out.append(_fail("gear: afixos", f"{label}: os {len(lines)} explícitos não cabem em {max_pre} prefixos + "
                                         f"{max_suf} sufixos sem repetir grupo de mod"))
    return out


# ---------- registro da âncora ----------
def check_anchor(folder: Path | None) -> dict:
    """`ancora.md` da pasta: seções obrigatórias, ao menos duas alternativas descartadas e a linha Trilha."""
    if folder is None:
        return {"ok": None, "motivo": "XML avulso: registro da âncora só é exigido de uma pasta de build"}
    path = Path(folder) / ANCHOR_FILE
    if not path.exists():
        return {"ok": False, "motivo": f"falta {ANCHOR_FILE}: por que esta skill, contra quais alternativas, com que evidência"}
    text = path.read_text(encoding="utf-8")
    heads = [h.strip().casefold() for h in re.findall(r"^#+\s*(.+)$", text, re.M)]
    missing = [s for s in ANCHOR_SECTIONS if not any(h.startswith(s.casefold()) for h in heads)]
    alt = re.search(r"^#+\s*Alternativas.*?$(.*?)(?=^#+\s|\Z)", text, re.M | re.S | re.I)
    n_alt = len(re.findall(r"^\s*[-*]\s+\S", alt.group(1), re.M)) if alt else 0
    if missing:
        return {"ok": False, "motivo": f"{ANCHOR_FILE} sem as seções: {', '.join(missing)}"}
    if n_alt < 2:
        return {"ok": False, "motivo": f"{ANCHOR_FILE} lista {n_alt} alternativa(s); o mínimo é 2"}
    m = _TRILHA_LINE.search(text)
    if not m:
        return {"ok": False, "motivo": f"{ANCHOR_FILE} sem a linha 'Trilha: campanha | starter | desbalanceada' "
                                       "(a trilha decide quais limites de gear valem)"}
    return {"ok": True, "motivo": f"{ANCHOR_FILE} com {n_alt} alternativas, trilha {m.group(1).casefold()}",
            "trilha": m.group(1).casefold()}


# ---------- etapas.md ----------
def declared_stages(md: str) -> dict:
    """{título da etapa: {pontos}} lidos do etapas.md."""
    out = {}
    for title, body in re.findall(r"^## (L\d+[^\n]*)\n(.*?)(?=^## |\Z)", md, re.M | re.S):
        pts = re.search(r"Pontos: (\d+) de (\d+)", body)
        out[title.strip()] = {"pontos": int(pts.group(1)) if pts else None}
    return out


# ---------- julgamento puro ----------
def trilha_of(level: int, trilha: str | None) -> str:
    trilha = str(trilha or DEFAULT_TRILHA).strip().casefold()
    if trilha not in TRILHAS:
        raise ValueError(f"trilha deve ser uma de {', '.join(TRILHAS)}")
    return "campanha" if level < MAPS_LEVEL else trilha


def _gem(name: str) -> dict:
    try:
        return data.gem_info(name) or {}
    except Exception:
        return {}


def judge_stage(xml: str, facts: dict, declared: dict | None = None, pool_of=None, trilha: str | None = None,
                gem_of=None, bases=None) -> dict:
    """Veredito de uma etapa.

    facts = {"stats": {...} (STAT_FIELDS medidos no PoB), "minion": {...} ou None, "tree": {id: {kind, name,
    ascendancy}}, "allocated": [ids alocados pelo PoB]}. declared = linha do etapas.md, se houver.
    pool_of(base), gem_of(nome) e bases (dict por nome) são injetáveis nos testes.
    """
    b = parse_build(xml)
    level, st, tree = b["level"], facts.get("stats") or {}, facts.get("tree") or {}
    track = trilha_of(level, trilha)
    allocated = list(facts.get("allocated") or b["nodes"])
    fails, avisos = [], []
    pool_of = pool_of or data.affix_pool
    gem_of = gem_of or _gem
    if bases is None:
        bases = data.all_bases() if _bases_ok() else {}

    # Pontos de passiva e de ascendência.
    acts = stages.load_acts()
    budget = stages.passive_points(level, acts)
    kind = lambda n: (tree.get(n) or {}).get("kind")
    asc = [n for n in allocated if (tree.get(n) or {}).get("ascendancy") and kind(n) not in stages.FIXED_KINDS]
    used = [n for n in allocated if not (tree.get(n) or {}).get("ascendancy") and kind(n) not in stages.FIXED_KINDS]
    asc_budget = ascendancy_points(level)
    if len(used) > budget:
        fails.append(_fail("pontos", f"{len(used)} pontos de passiva; a etapa L{level} tem {budget} "
                                     f"({level - 1} de nível + {stages.quest_points(level, acts)} de missão)"))
    elif budget - len(used) > 2:
        avisos.append(f"{budget - len(used)} pontos de passiva sem uso")
    if len(asc) > asc_budget:
        nxt = next((f"{n} (nível {lvl})" for lvl, pts, n in ASCENSIONS if pts >= len(asc)), "4ª ascensão")
        fails.append(_fail("ascendência", f"{len(asc)} pontos de ascendência no L{level}; o orçamento é {asc_budget} "
                                          f"(precisa da {nxt}; tabela ASCENSIONS, [VERIFY in game])"))
    if declared and declared.get("pontos") is not None and declared["pontos"] > len(used):
        fails.append(_fail("pontos", f"etapas.md declara {declared['pontos']} pontos, o PoB alocou {len(used)}: "
                                     "nós planejados foram descartados"))

    # Soquetes de joia.
    for n in allocated:
        if kind(n) == "Socket":
            item_id = b["sockets"].get(n, 0)
            if not item_id or item_id not in b["items"]:
                fails.append(_fail("joia", f"soquete {n} alocado sem joia"))

    # Gems: nível exigido, supports por skill, lineage, support repetido.
    seen_supports = {}
    for gi, group in enumerate(b["groups"], 1):
        if not group["enabled"]:
            continue
        active = [g for g in group["gems"] if g["enabled"] and g["name"]]
        supports = [g for g in active if gem_of(g["name"]).get("support")]
        if supports:
            cap = min(MAX_SUPPORTS[track], GAME_MAX_SUPPORTS)
            if len(supports) > GAME_MAX_SUPPORTS:
                fails.append(_fail("supports", f"grupo {gi}: {len(supports)} supports; o jogo permite {GAME_MAX_SUPPORTS} por skill"))
            elif len(supports) > cap:
                fails.append(_fail("supports", f"grupo {gi}: {len(supports)} supports no L{level}; na trilha {track} o degrau "
                                               f"fecha em {cap} (soquetes extras pedem Jeweller's Orbs; escolha de método)"))
            if group["source"]:
                avisos.append(f"grupo {gi} é concedido por item/nó ({group['source']}) e tem supports: [VERIFY in game] "
                              "se a skill concedida aceita supports")
        for g in supports:
            seen_supports.setdefault(g["name"], []).append(gi)
            if gem_of(g["name"]).get("lineage") and not UNIQUES_ALLOWED[track]:
                fails.append(_fail("gems: degrau", f"grupo {gi}: {g['name']} é support lineage (drop raro, degrau 4); "
                                                   f"na trilha {track} o gear para no degrau 2"))
        if track == "campanha" and any(g.get("quality") for g in active):
            avisos.append(f"grupo {gi}: gems com qualidade no L{level} (qualidade é degrau 3 na campanha)")
        for g in active:
            if group["source"] and g is active[0]:
                continue  # nível de skill concedida vem do item ou do nó, não de uma gem
            table = gem_of(g["name"]).get("levels")
            if not table:
                avisos.append(f"gem {g['name']} fora do PoB: nível exigido não conferido")
                continue
            allowed = gem_level(level, table)
            tier = gem_of(g["name"]).get("tier") if g is active[0] else None
            if tier and allowed < tier:
                need = table.get(tier)
                fails.append(_fail("gem", f"grupo {gi}: {g['name']} é tier {tier} (cortada de gema bruta nível {tier}, personagem nível "
                                          f"{need if need is not None else '?'}); no L{level} a gema mais alta é nível {allowed}"))
            elif tier and g["level"] < tier:
                fails.append(_fail("gem", f"grupo {gi}: {g['name']} nível {g['level']} abaixo do tier {tier}: a gema cortada "
                                          f"começa no nível da gema bruta"))
            if g["level"] > allowed:
                need = table.get(g["level"])
                fails.append(_fail("gem", f"grupo {gi}: {g['name']} nível {g['level']} exige personagem nível "
                                          f"{need if need is not None else '> máximo natural'}; no L{level} o máximo é {allowed}"))
    for name, where in seen_supports.items():
        if len(where) > 1:
            msg = f"{name} em {len(where)} grupos ({', '.join(map(str, where))})"
            if gem_of(name).get("lineage"):
                fails.append(_fail("supports", msg + ": support lineage é um só por personagem"))
            else:
                avisos.append(msg + ": [VERIFY in game] se o mesmo support pode estar em duas skills")

    # Atributos exigidos (gems e itens), medidos no PoB.
    for attr in ("Str", "Dex", "Int"):
        have, need = st.get(attr), st.get("Req" + attr)
        if isinstance(have, (int, float)) and isinstance(need, (int, float)) and need > have:
            fails.append(_fail("atributos", f"{attr} {have:g} abaixo do exigido {need:g}"))

    # Itens: nível exigido, item level, degrau por trilha, mods, soquetes de runa, skill do segundo conjunto.
    for slot in GEAR_SLOTS:
        item = b["items"].get(b["slots"].get(slot, 0))
        if not item:
            continue
        if item.get("level_req") and item["level_req"] > level:
            fails.append(_fail("gear: nível", f"{slot}: {item['name']} exige nível {item['level_req']} (etapa L{level})"))
        ilvl_cap = max_item_level(level)
        if item.get("item_level") and item["item_level"] > ilvl_cap:
            fails.append(_fail("gear: item level", f"{slot}: {item['name']} tem item level {item['item_level']}; no L{level} "
                                                   f"o máximo obtível é {ilvl_cap}"))
            item = {**item, "item_level": ilvl_cap}
        if slot in SWAP_SLOTS and item.get("grants"):
            avisos.append(f"{slot}: {item['name']} concede {', '.join(item['grants'])} do segundo conjunto de armas; o PoB a mantém "
                          "ativa com o outro conjunto empunhado: [VERIFY in game]")
        if item["rarity"] in ("UNIQUE", "RELIC"):
            if not UNIQUES_ALLOWED[track]:
                fails.append(_fail("gear: degrau", f"{slot}: {item['name']} é unique (degrau 4); na trilha {track} o gear "
                                                   "para em degrau 2 (craft simples)"))
            continue
        base = bases.get(item["base"])
        if not base:
            avisos.append(f"{slot}: base {item['base']!r} não encontrada; mods não conferidos")
            continue
        if base.get("liga") or base.get("oculta"):
            what = "de liga" if base.get("liga") else "oculta no PoB (hidden = true)"
            if not UNIQUES_ALLOWED[track]:
                fails.append(_fail("gear: degrau", f"{slot}: base {base['name']} é {what}, não drop comum; na trilha {track} é degrau 4"))
            else:
                avisos.append(f"{slot}: base {base['name']} é {what}: [VERIFY in game] se é obtível nesta liga")
        if base["level"] > level and not item.get("level_req"):
            fails.append(_fail("gear: nível", f"{slot}: base {base['name']} exige nível {base['level']} (etapa L{level})"))
        if item.get("rune_sockets") and base.get("socket_limit") and item["rune_sockets"] > base["socket_limit"]:
            fails.append(_fail("soquetes", f"{slot}: {item['rune_sockets']} soquetes de runa; a base {base['name']} "
                                           f"permite {base['socket_limit']}"))
        if item.get("especiais"):
            avisos.append(f"{slot}: {len(item['especiais'])} mod(s) fora do pool de drop (desecrated/fractured/mutated): "
                          "não conferidos")
        for f in check_item(item, base, pool_of(base)):
            f["motivo"] = f"{slot}: {f['motivo']}"
            fails.append(f)

    # Config honesta: condição ligada precisa de um produtor na build.
    texts = [g["name"] for grp in b["groups"] if grp["enabled"] for g in grp["gems"] if g["enabled"]]
    texts += [t for name in list(texts) for t in sorted(gem_of(name).get("tags") or ())]
    texts += [l for it in b["items"].values() for l in it["implicits"] + it["explicits"]]
    texts += [st_ for n in allocated for st_ in (tree.get(n) or {}).get("stats") or []]
    for var, (need, skip) in CONFIG_PRODUCERS.items():
        value = b["config"].get(var)
        if not value or value in ("false", "0", 0):
            continue
        hits = [t for t in texts if re.search(need, t, re.I) and not (skip and re.search(skip, t, re.I))]
        if not hits:
            fails.append(_fail("config", f"{var} ligado na config sem produtor na build (gems, nós ou itens)"))

    # Config da medição: penalidade de resistência da faixa.
    pen = b["config"].get("resistancePenalty", POB_DEFAULT_PENALTY)  # o PoB não grava o valor padrão
    want = stages.resistance_penalty(level, acts)
    if int(pen) != want:
        fails.append(_fail("config", f"penalidade de resistência {int(pen)}; a faixa do L{level} é {want}"))

    # Camada 2: sustentação.
    if isinstance(st.get("SpiritUnreserved"), (int, float)) and st["SpiritUnreserved"] < 0:
        fails.append(_fail("spirit", f"Spirit reservado acima do disponível: {st.get('Spirit')} de Spirit, "
                                     f"{st['SpiritUnreserved']:g} livres"))
    cost, regen = mana_per_second(st), (st.get("ManaRegenRecovery") or 0) + (st.get("ManaLeechGainRate") or 0)
    if cost is not None and cost > regen + 1e-6:
        msg = f"gasto de {cost:.1f} mana/s na skill principal ({mana_rhythm(st)}) contra {regen:.1f}/s de regeneração + leech"
        if level < MANA_FLASK_LEVEL:
            avisos.append(msg + f" (abaixo do L{MANA_FLASK_LEVEL} o frasco de mana cobre; escolha de método)")
        else:
            fails.append(_fail("mana", msg))
    if isinstance(st.get("ManaCost"), (int, float)) and st["ManaCost"] > 0 and (st.get("ManaUnreserved") or 0) < st["ManaCost"]:
        fails.append(_fail("mana", f"mana livre {st.get('ManaUnreserved') or 0:g} menor que o custo de uma conjuração {st['ManaCost']:g}"))
    curses, marks = curses_applied(b["groups"], gem_of)
    limit = st.get("EnemyCurseLimit")
    if isinstance(limit, (int, float)) and len(curses) > limit:
        fails.append(_fail("maldições", f"{len(curses)} maldições aplicadas ({', '.join(curses)}) e limite {limit:g}"))
    if len(marks) > 1:
        fails.append(_fail("maldições", f"{len(marks)} marcas ({', '.join(marks)}); só uma fica ativa"))
    meta = meta_for(level)
    for e in ELEMENTS:
        v = st.get(e)
        if isinstance(v, (int, float)) and v < meta["resistencia"]:
            fails.append(_fail("resistência", f"{e} {v:g}% abaixo da meta {meta['resistencia']}% da faixa L{meta['desde']}+"))
    pool = (st.get("Life") or 0) + (st.get("EnergyShield") or 0)
    if pool < meta["vida_es"]:
        fails.append(_fail("vida", f"vida + ES {pool:g} abaixo da meta {meta['vida_es']} da faixa L{meta['desde']}+"))

    minion = facts.get("minion") or {}
    player_dps = st.get("CombinedDPS") or 0
    dps, fonte = (player_dps, "jogador") if player_dps or not minion.get("TotalDPS") else (minion["TotalDPS"], "minion (um)")
    ehp = st.get("TotalEHP") or 0
    nota = math.sqrt(max(dps, 0) * max(ehp, 0))
    return {"nivel": level, "trilha": track, "aprovada": not fails, "reprovas": fails, "avisos": avisos,
            "medidas": {"DPS": round(dps, 1), "DPS_fonte": fonte, "TotalEHP": round(ehp, 1), "Life": st.get("Life"),
                        "EnergyShield": st.get("EnergyShield"), "Spirit": st.get("Spirit"), "SpiritUnreserved": st.get("SpiritUnreserved"),
                        "ManaPorSegundoRitmo": round(cost, 2) if cost is not None else None, "ManaRegen+Leech": round(regen, 2),
                        "pontos": f"{len(used)}/{budget}", "ascendencia": f"{len(asc)}/{asc_budget}",
                        "maldicoes": f"{len(curses)}/{limit if limit is not None else '?'}",
                        "resistencias": [st.get(e) for e in ELEMENTS], "atributos": [st.get(a) for a in ("Str", "Dex", "Int")]},
            "nota": round(nota, 1)}


def mana_per_second(st: dict) -> float | None:
    """Mana/s da skill principal no ritmo real: conjuração contínua (ManaPerSecondCost do PoB), ou, para uma
    skill só de dano contínuo com duração, um recast por duração quando isso é mais lento que a cadência."""
    cost, speed, duration = st.get("ManaCost"), st.get("Speed"), st.get("Duration")
    if not isinstance(cost, (int, float)) or cost <= 0:
        return None
    if _dot_only(st) and isinstance(duration, (int, float)) and duration > 0 and isinstance(speed, (int, float)):
        return cost * min(speed, 1 / duration)
    return st.get("ManaPerSecondCost")


def _dot_only(st: dict) -> bool:
    return not (st.get("TotalDPS") or 0) and (st.get("TotalDot") or 0) > 0


def mana_rhythm(st: dict) -> str:
    speed, duration = st.get("Speed") or 0, st.get("Duration") or 0
    if _dot_only(st) and duration > 0 and speed > 1 / duration:
        return f"um recast por duração de {duration:.2f} s; conjurando sem parar seriam {st.get('ManaPerSecondCost', 0):.1f}/s"
    return "conjurando sem parar"


def curses_applied(groups: list[dict], gem_of=None) -> tuple[list[str], list[str]]:
    """Maldições e marcas nos grupos ativos, pelas tags da gem no PoB (curse, mark)."""
    gem_of = gem_of or _gem
    curses, marks = [], []
    for group in groups:
        if not group["enabled"]:
            continue
        for g in group["gems"]:
            info = gem_of(g["name"]) if g["enabled"] and g["name"] else {}
            tags = set(info.get("tags") or ())
            if info.get("support"):
                continue
            if "mark" in tags:
                marks.append(g["name"])
            elif "curse" in tags:
                curses.append(g["name"])
    return sorted(set(curses)), sorted(set(marks))


# ---------- motor ----------
def measure(lab, xml: str) -> dict:
    """Carrega o XML no PoB e lê os fatos de que o juiz precisa."""
    lab.load_xml(xml, "juiz")
    ctx = lab.tree_context()
    tree = {n["id"]: {"kind": n["kind"], "name": n["name"], "ascendancy": n.get("ascendancy"), "stats": n.get("stats") or []}
            for n in ctx["nodes"]}
    raw = lab.stats(STAT_FIELDS, minion=True)
    minion = raw.pop("minion", None)
    return {"stats": raw, "minion": minion, "tree": tree, "allocated": [n["id"] for n in ctx["nodes"] if n["allocated"]]}


def stage_files(folder: Path) -> list[Path]:
    """L<nível>.xml e respecs da pasta, em ordem de nível (respec depois da etapa do mesmo nível)."""
    files = [p for p in Path(folder).glob("L*.xml") if re.match(r"^L\d+(\.xml| respec - )", p.name)]
    return sorted(files, key=lambda p: (int(re.match(r"L(\d+)", p.name).group(1)), "respec" in p.name))


def judge_build(path, lab=None, trilha: str | None = None) -> dict:
    """Julga uma pasta de etapas (L*.xml, etapas.md, ancora.md) ou um XML avulso."""
    from src.lab.engine import Lab
    path = Path(path)
    folder = path if path.is_dir() else None
    files = stage_files(path) if folder else [path]
    if not files:
        raise ValueError(f"nenhum L<nível>.xml em {path}")
    md = (folder / "etapas.md").read_text(encoding="utf-8") if folder and (folder / "etapas.md").exists() else ""
    declared = declared_stages(md) if md else {}
    anchor = check_anchor(folder)
    trilha = trilha or anchor.get("trilha") or DEFAULT_TRILHA
    if not anchor.get("trilha") and folder is not None:
        anchor["motivo"] += f"; trilha {trilha} assumida"
    own = lab is None
    lab = lab or Lab()
    try:
        etapas = []
        for f in files:
            xml = f.read_text(encoding="utf-8")
            decl = next((v for k, v in declared.items() if _same_title(k, f.stem)), None)
            verdict = judge_stage(xml, measure(lab, xml), decl, trilha=trilha)
            etapas.append({"arquivo": f.name, **verdict})
    finally:
        if own:
            lab.close()
    aprovada = all(e["aprovada"] for e in etapas) and anchor["ok"] is not False
    notas = [e["nota"] for e in etapas if e["nota"] > 0]
    nota = math.exp(sum(math.log(n) for n in notas) / len(notas)) if notas and len(notas) == len(etapas) else 0.0
    return {"build": path.name, "trilha": trilha, "aprovada": aprovada, "nota": round(nota, 1),
            "nota_definicao": "média geométrica de √(DPS × TotalEHP) das etapas, medida no PoB headless (DPS do jogador, ou de um "
                              "minion da skill principal quando o jogador não causa dano); compara versões da mesma build com as "
                              "mesmas etapas; só vale com a build aprovada",
            "registro_ancora": anchor, "etapas": etapas,
            "reprovas": sum(len(e["reprovas"]) for e in etapas) + (anchor["ok"] is False),
            "regras": {"ascensoes": [{"nivel": l, "pontos": p, "nome": n} for l, p, n in ASCENSIONS],
                       "metas": [{"desde": l, "resistencia": r, "vida_es": v} for l, r, v in METAS],
                       "trilhas": {t: f"até {MAX_SUPPORTS[t]} supports por skill, " + ("uniques, lineage e bases de liga permitidos"
                                                                                        if UNIQUES_ALLOWED[t] else "sem uniques, lineage nem bases de liga (degrau 4)")
                                   for t in TRILHAS},
                       "fonte_metas": "escolha de método do juiz (calibrável em src/lab/judge.py: METAS, ASCENSIONS, MAX_SUPPORTS), não regra do jogo",
                       "pontos": "nível − 1 + pontos de missão (Data/QuestRewards.lua do PoB); campanha abaixo do L" + str(MAPS_LEVEL),
                       "mana": "gasto/s da skill principal <= regeneração + leech; frascos não contam"}}


def _same_title(declared: str, stem: str) -> bool:
    norm = lambda s: re.sub(r"[^\w]+", " ", s).strip().casefold()
    return norm(declared) == norm(stem)
