"""Mapa de economia de recursos do PoE2: recurso | verbo | efeito.

Porta o método do le-economy (Last Epoch) para o catálogo RePoE do Finder:

  1. Âncora: efeito que LÊ ou REPLICA um recurso e dá dano "more" (ou remove
     um limite/custo).
  2. Conectores: tudo que PRODUZ esse recurso.
  3. Escala: o que amplifica o recurso ou a saída da âncora.

As arestas são palpites por regra sobre o texto do jogo. Não são mecânica
confirmada nem pontuação de poder: quem valida número é o PoB.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import re
import threading

VERBS = {
    "PRODUCES": "cria, aplica ou ganha o recurso",
    "CONSUMES": "gasta ou remove o recurso",
    "READS": "escala com a quantidade/presença do recurso sem gastar",
    "REPLICATES": "repete ou multiplica um efeito pela contagem do recurso",
    "CONVERTS": "transforma um recurso ou tipo em outro",
    "LIMITS": "impõe teto, custo ou restrição",
    "UNLOCKS": "aumenta o teto ou remove custo/consumo",
    "AMPLIFIES": "mais efeito, magnitude, duração ou chance do recurso",
    "AMBIGUOUS": "menção sem verbo reconhecido; conferir à mão",
}

METHOD = "\n".join([
    "1. Âncora: efeito que READS/REPLICATES/CONSUMES um recurso e dá dano 'more' (ou UNLOCKS teto/custo). Use economy_anchors.",
    "2. Conectores: tudo que PRODUCES esse recurso, em slots diferentes (skill, support, passiva, ascendência). Use economy_resource com verbs=[PRODUCES, UNLOCKS].",
    "3. Escala: o que AMPLIFIES o recurso. Âncora em recurso sem produtores nem amplificadores é armadilha.",
    "4. Conflitos: LIMITS e textos com 'cannot', 'instead', 'no longer'. Leia o texto inteiro com economy_lookup.",
    "5. Itens: kinds=[JEWELS] (afixos de joia rara, Time-Lost, joias unique, Timeless) e kinds=[AUGMENTS] (Runes, Soul Cores, Idols). "
    "Joia de raio não tem valor fixo (depende dos nós no raio); Rune, Soul Core e Idol disputam o mesmo socket de item. "
    "Cada registro traz o degrau de obtenção estimado (1 garantido ... 4 específico).",
    "Toda aresta é palpite por regra sobre texto do jogo. Cite o texto exato e valide no PoB antes de concluir.",
])

# ---------- léxico ----------
# Tag de palavra-chave do jogo ([Tag|texto] no RePoE) -> (recurso, categoria).
# Categorias: stack, entity, pool, state, event, stat, type, damage.
TAG_RESOURCES = {
    # acumuláveis e cargas
    "Rage": ("rage", "stack"), "Combo": ("combo", "stack"), "Glory": ("glory", "stack"),
    "Seal": ("seal", "stack"), "Volatility": ("volatility", "stack"), "Heat": ("heat", "stack"),
    "ElementalInfusion": ("infusion", "stack"), "VerisiumInfusion": ("infusion", "stack"),
    "Power": ("power", "stack"), "Withered": ("withered", "stack"), "Incision": ("incision", "stack"),
    "Impale": ("impale", "stack"), "CorruptedBlood": ("corrupted blood", "stack"),
    "FlamesOfChayula": ("flames of chayula", "stack"), "PurpleFlamesOfChayula": ("flames of chayula", "stack"),
    "Jade": ("jade", "stack"), "Ammunition": ("ammunition", "stack"),
    # ailments e debuffs
    "Ignite": ("ignite", "state"), "Shock": ("shock", "state"), "Chill": ("chill", "state"),
    "Freeze": ("freeze", "state"), "Frozen": ("freeze", "state"), "Poison": ("poison", "state"),
    "Bleeding": ("bleed", "state"), "Electrocute": ("electrocute", "state"), "Stun": ("stun", "state"),
    "HeavyStun": ("heavy stun", "state"), "HeavyStunPlayer": ("heavy stun", "state"),
    "PrimedStun": ("heavy stun", "state"), "Daze": ("daze", "state"), "Pinned": ("pin", "state"),
    "Immobilised": ("immobilise", "state"), "Blind": ("blind", "state"), "Maim": ("maim", "state"),
    "Slow": ("slow", "state"), "Hinder": ("hinder", "state"), "Curse": ("curse", "state"),
    "Mark": ("mark", "state"), "Exposure": ("exposure", "state"), "ArmourBreak": ("armour break", "state"),
    "Flammability": ("flammability", "state"), "CriticalWeakness": ("critical weakness", "state"),
    "Intimidate": ("intimidate", "state"), "ParriedDebuff": ("parried", "state"),
    "Ailments": ("ailment", "state"), "ElementalAilments": ("ailment", "state"),
    "DamagingAilments": ("ailment", "state"), "NonDamagingAilments": ("ailment", "state"),
    "Burning": ("ignite", "state"), "Aggravate": ("bleed", "state"), "Knockback": ("knockback", "state"),
    # estados do personagem
    "Shapeshift": ("shapeshift", "state"), "Empowered": ("empowered", "state"),
    "LowLife": ("low life", "state"), "LowMana": ("low mana", "state"),
    "Surrounded": ("surrounded", "state"), "ArcaneSurge": ("arcane surge", "state"),
    "Onslaught": ("onslaught", "state"), "UnholyMight": ("unholy might", "state"),
    "AncestralBoost": ("ancestral boost", "state"), "PerfectTiming": ("perfect timing", "state"),
    "Archon": ("archon", "state"), "ElementalArchon": ("archon", "state"), "Guard": ("guard", "state"),
    "Channelling": ("channelling", "state"), "DualWield": ("dual wield", "state"),
    "Presence": ("presence", "state"), "Sustained": ("sustained", "state"),
    # entidades
    "Minion": ("minion", "entity"), "TemporaryMinion": ("minion", "entity"),
    "Companion": ("companion", "entity"), "Totem": ("totem", "entity"), "Ballista": ("totem", "entity"),
    "Remnant": ("remnant", "entity"), "Corpse": ("corpse", "entity"), "Projectile": ("projectile", "entity"),
    "IceCrystals": ("ice crystal", "entity"), "IceFragment": ("ice fragment", "entity"),
    "Hazard": ("hazard", "entity"), "Grenade": ("grenade", "entity"), "Banner": ("banner", "entity"),
    "Offering": ("offering", "entity"), "Orb": ("orb", "entity"), "Plant": ("plant", "entity"),
    "Aftershock": ("aftershock", "entity"), "MoltenFissure": ("molten fissure", "entity"),
    "Trap": ("trap", "entity"), "Idol": ("idol", "entity"), "Allies": ("ally", "entity"),
    "IgnitedGround": ("ignited ground", "entity"), "ChilledGround": ("chilled ground", "entity"),
    "ShockedGround": ("shocked ground", "entity"), "JaggedGround": ("jagged ground", "entity"),
    "OilGround": ("oil", "entity"), "Oil": ("oil", "entity"), "ConsecratedGround": ("consecrated ground", "entity"),
    "ThornyGround": ("thorny ground", "entity"), "ElementalGround": ("elemental ground", "entity"),
    # reservatórios
    "EnergyShield": ("energy shield", "pool"), "Spirit": ("spirit", "pool"), "Ward": ("ward", "pool"),
    "Flask": ("flask", "pool"), "Charm": ("charm", "pool"), "Energy": ("energy", "pool"),
    # eventos
    "Critical": ("critical hit", "event"), "Block": ("block", "event"), "Parry": ("parry", "event"),
    "Deflect": ("deflect", "stat"), "CullingStrike": ("culling strike", "event"),
    "Warcry": ("warcry", "event"), "Chain": ("chain", "event"), "Pierce": ("pierce", "event"),
    "Fork": ("fork", "event"), "Shatter": ("shatter", "event"), "Overkill": ("overkill", "event"),
    "KillingBlow": ("kill", "event"), "Detonator": ("detonate", "event"),
    "FinalStrike": ("final strike", "event"), "MinionDeath": ("minion death", "event"),
    "Reviving": ("minion death", "event"),
    # atributos e stats que outros efeitos convertem em multiplicador
    "Strength": ("strength", "stat"), "Dexterity": ("dexterity", "stat"),
    "Intelligence": ("intelligence", "stat"), "Attributes": ("attributes", "stat"),
    "Armour": ("armour", "stat"), "Evasion": ("evasion", "stat"), "Accuracy": ("accuracy", "stat"),
    "Thorns": ("thorns", "stat"), "SkillSpeed": ("skill speed", "stat"),
    "StunThreshold": ("stun threshold", "stat"), "Resistances": ("resistances", "stat"),
    "MaximumResistances": ("resistances", "stat"), "CooldownRecovery": ("cooldown", "stat"),
    "Reservation": ("reservation", "stat"), "LifeLeech": ("leech", "stat"), "ManaLeech": ("leech", "stat"),
    "Leech": ("leech", "stat"), "Recoup": ("recoup", "stat"),
}
# Recursos sem tag própria no texto do jogo.
PLAIN_RESOURCES = {
    "power charge": ("stack", r"power charges?"),
    "frenzy charge": ("stack", r"frenzy charges?"),
    "endurance charge": ("stack", r"endurance charges?"),
    "flask charge": ("pool", r"(?:flask|charm) charges?"),
    "stage": ("stack", r"stages?"),
    "mana": ("pool", r"mana"),
    "life": ("pool", r"life"),
    "skeleton": ("entity", r"skeletons?|skeletal \w+"),
    "area": ("stat", r"area of effect"),
    "duration": ("stat", r"duration"),
    "kill": ("event", r"on kill|when you kill|kill(?:s|ed|ing)? an? enemy|killing blow"),
    # joias: o que uma joia de raio/unique altera ou destrava
    "passive": ("stat", r"passive skills?|passives(?: in radius)?|notable passive skills?|small passive skills?"),
    "jewel": ("entity", r"(?:corrupted |magic |socketed |sinister )*jewels?(?: sockets?)?"),
    # entidades criadas por uma skill e lidas por outra (interação skill -> skill)
    "whirlwind": ("entity", r"whirlwinds?"),
    "twister": ("entity", r"twisters?"),
    "lodged spear": ("entity", r"lodged spears?|spears? (?:is |are )?lodged"),
    "hit": ("event", r"on hit|when you hit|per enemy hit|enem(?:y|ies) hit"),
}
# Tão comuns que só fazem barulho no ranking de âncoras.
UNIVERSAL = {"hit", "life", "mana", "duration", "area", "projectile", "critical hit", "resistances",
             "chain", "pierce", "fork", "attributes"}

_PLAIN = [(name, cat, re.compile(r"(?<![\w'])(?:" + pat + r")(?![\w])", re.I))
          for name, (cat, pat) in PLAIN_RESOURCES.items()]
CATEGORY = {name: cat for name, cat in TAG_RESOURCES.values()}
CATEGORY.update({name: cat for name, (cat, _pat) in PLAIN_RESOURCES.items()})

_MARKUP = re.compile(r"\[([^\]|]+)(?:\|([^\]]*))?\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def parse_markup(original: str) -> tuple[str, list[tuple[str, int, int]]]:
    """Remove a marcação [Tag|texto] e devolve o texto limpo + (tag, início, fim)."""
    out, spans, pos = [], [], 0
    length = 0
    for m in _MARKUP.finditer(original):
        before = original[pos:m.start()]
        out.append(before)
        length += len(before)
        shown = m.group(2) if m.group(2) is not None else m.group(1)
        spans.append((m.group(1), length, length + len(shown)))
        out.append(shown)
        length += len(shown)
        pos = m.end()
    out.append(original[pos:])
    return "".join(out), spans


# Texto de item do PoB não tem marcação [Tag]: os recursos com tag são procurados pelo nome, com flexões.
_IRREGULAR = {
    "freeze": r"freez(?:e|es|ed|ing)|frozen", "bleed": r"bleed(?:s|ing)?|bleeds", "ignite": r"ignit(?:e|es|ed|ing)",
    "armour break": r"armour break\w*|(?:fully )?broken armour", "shapeshift": r"shapeshift\w*",
    "critical hit": r"critical hits?|critical (?:strike|hit) chance", "minion death": r"minions? (?:die|dies|died)",
    "oil": r"oil(?:ed)?(?: ground)?", "energy": r"energy(?! shield)",
}
_SKIP_FALLBACK = set(PLAIN_RESOURCES) | {"ally", "hit", "kill", "orb", "plant", "trap", "chain", "block"}


def _fallback_patterns():
    out = []
    for name in sorted({name for name, _cat in TAG_RESOURCES.values()} - _SKIP_FALLBACK):
        pat = _IRREGULAR.get(name) or (re.escape(name) + r"(?:s|es|ed|d|ing)?")
        out.append((name, re.compile(r"(?<![\w'])(?:" + pat + r")(?![\w])", re.I)))
    return out


_FALLBACK = _fallback_patterns()


def mentions(clause: str, spans: list[tuple[str, int, int]], plain_tags: bool = False) -> list[tuple[str, int, int]]:
    """(recurso, início, fim) sem sobreposição; termos sem tag ganham das tags genéricas.

    `plain_tags=True` (texto de item, sem marcação) procura também os recursos com tag pelo nome.
    """
    found = []
    for name, _cat, rx in _PLAIN:
        for m in rx.finditer(clause):
            found.append((0, -(m.end() - m.start()), name, m.start(), m.end()))
    if plain_tags:
        for name, rx in _FALLBACK:
            for m in rx.finditer(clause):
                found.append((1, -(m.end() - m.start()), name, m.start(), m.end()))
    for tag, s, e in spans:
        hit = TAG_RESOURCES.get(tag)
        if hit:
            found.append((1, -(e - s), hit[0], s, e))
    found.sort()
    taken, out = [], []
    for _prio, _len, name, s, e in found:
        if any(not (e <= a or s >= b) for a, b in taken):
            continue
        taken.append((s, e))
        out.append((name, s, e))
    return sorted(out, key=lambda x: x[1])


# ---------- verbos ----------
# {R} é a menção. A ordem importa: entre os verbos simples vence a primeira regra que casar.
_NOT_LINK = r"(?: (?!while|whilst|if|when|against|to|per|for|with|on|from|by|and|or)\w+%?)"
_RULES = [
    ("UNLOCKS", [
        # PoE 1, Anathema: "Your Curse Limit is equal to your maximum Power Charges"
        r"{R} limit (?:is|are) equal to",
        r"(?:\+\d+|additional|increased|more)(?: \w+){0,3} maximum (?:number of )?(?:\w+ ){0,2}{R}",
        r"{R}[^.]{0,25}(?:is|are) not consumed",
        r"(?:do(?:es)? not|without|cannot) (?:consum|remov|expend|los)\w*[^.]{0,25}{R}",
        r"no {R} cost", r"{R}[^.]{0,15}costs? no",
        r"chance to not (?:consume|remove|lose)[^.]{0,25}{R}", r"{R}[^.]{0,25}no maximum",
        # joias que removem uma restrição da árvore
        r"{R}[^.]{0,30}can be allocated", r"can allocate[^.]{0,20}{R}",
    ]),
    ("LIMITS", [
        r"cannot (?:\w+ ){0,3}{R}", r"{R}[^.]{0,30}cannot", r"(?:lose|loses) all {R}",
        r"limited to[^.]{0,20}{R}", r"no longer[^.]{0,30}{R}", r"maximum of \d+ (?:\w+ ){0,2}{R}",
    ]),
    ("REPLICATES", [
        r"additional (?:\w+%? ){0,6}(?:per|for each|for every) (?:\w+ ){0,2}{R}",
        r"(?:\brepeats?\b|additional times?|twice)[^.]{0,30}(?:per|for each|for every) (?:\w+ ){0,2}{R}",
        r"{R}[^.]{0,30}(?:\brepeats?\b|an additional time|twice|trigger\w* again)",
        r"(?:per|for each|for every) (?:\w+ ){0,2}{R}[^.]{0,30}(?:\brepeats?\b|additional (?:\w+ ){0,3}|twice)",
    ]),
    ("CONSUMES", [
        r"(?:consum|spend|sacrific|expend|detonat|remov)\w*(?: \w+){0,5} {R}",
        r"{R}(?: \w+){0,3} (?:consumed|spent|expended|sacrificed|removed|detonated)",
        r"(?:lose|loses|losing) (?:\w+ ){0,3}{R}", r"costs? (?:\w+ ){0,3}{R}",
    ]),
    ("CONVERTS", [
        r"{R}[^.]{0,30}converted to", r"converted to[^.]{0,20}{R}",
        r"{R}[^.]{0,25}instead of", r"instead of[^.]{0,25}{R}",
        r"modifiers to[^.]{0,30}{R}[^.]{0,20}also apply", r"also appl(?:y|ies) to[^.]{0,30}{R}",
        r"{R}[^.]{0,30}also appl(?:y|ies) to", r"convert\w*(?: \w+%?){0,6} to (?:\w+ ){0,2}{R}",
        r"{R}[^.]{0,30}(?:are|is) conquered by",
        r"{R}[^.]{0,20}(?:is|are|counts?) (?:also )?(?:treated|considered|counted) as",
    ]),
    ("READS", [
        r"(?:per|for each|for every) (?:\d+ )?(?:\w+ ){0,3}{R}",
        r"(?:based on|proportional to|equal to)[^.]{0,30}{R}",
        r"(?:while|whilst|if|when|against|versus|during)(?: \w+){0,3} {R}",
        r"{R} (?:enem(?:y|ies)|targets?|monsters?)", r"(?:enem(?:y|ies)|targets?) (?:\w+ ){0,2}{R}",
    ]),
    ("PARTICIPLE", []),
    ("AMPLIFIES", [
        r"(?:increased|more|reduced|less|faster|slower)" + _NOT_LINK + r"{0,4} {R}",
    ]),
    ("PRODUCES", [
        r"(?:gains?|grants?|generat\w+|creat\w+|appl(?:y|ies|ying)|inflict\w*|summon\w*|spawn\w*|leav\w+|build\w*|caus\w+|recover\w*|restor\w*|refresh\w*|kicks? up|whips? up|lodg\w+)(?: \w+%?){0,6} {R}",
        r"chance to (?:\w+ ){0,3}{R}", r"^{R} (?:\w+ ){0,2}(?:on|when)\b",
        r"{R} (?:all |nearby |the |any )?(?:enem|target|everything|them|you\b)",
        r"{R}(?: \w+){0,3} (?:is|are) (?:created|generated|granted|applied|inflicted)",
    ]),
    ("AMPLIFIES", [
        r"(?:additional|\+\d+%?)(?: \w+){0,4} {R}",
        r"{R} (?:\w+ ){0,2}(?:magnitude|effect|duration|chance|damage|gain|generation|build ?up|limit|rating)",
        r"(?:magnitude|effect|duration|chance) of (?:\w+ ){0,3}{R}",
        r"^(?:your )?{R} (?:\w+ )?(?:have|has|deal|gain|take|cause|recover|regenerate|revive|use|gets?)\b",
    ]),
    ("READS", [
        r"recently (?:\w+ ){0,3}{R}", r"{R}(?: \w+){0,3} recently", r"(?:you|have|having|with) (?:\w+ ){0,4}{R}",
        r"(?:near|in|within|from|by) (?:\w+ ){0,3}{R}",
    ]),
]
_TOKEN = "\x00"
_COMPILED = [(verb, [re.compile(p.replace("{R}", _TOKEN), re.I) for p in pats]) for verb, pats in _RULES]
_STRUCTURAL = ("UNLOCKS", "LIMITS", "REPLICATES", "CONSUMES", "CONVERTS")
_PARTICIPLE = re.compile(r"(?:ed|en)$", re.I)
_BECOMES = re.compile(r"(?:becomes?|are|is|be|get|gets)(?: \w+)? $", re.I)
MORE_RX = re.compile(
    r"\bmore\b(?! than)|as extra|\bdouble\b|\btwice\b|\brepeats?\b|additional (?:time|projectile|chain|strike|attack|cast)", re.I)
# "Pins as though dealing 600% more Damage", "more susceptible to being Frozen", "more Stun buildup":
# é acúmulo de ailment/stun, não dano. O texto parece âncora e não é.
BUILDUP_RX = re.compile(r"as though|susceptible|build-?up|more (?:likely|quickly|easily|effective at|chance to)", re.I)
DEFENCE_RX = re.compile(r"\b(?:evasion|armour|energy shield|guard|stun threshold|ailment threshold|recovery|regenerat\w*|"
                        r"block chance|resistances?|deflection|maximum life|maximum mana|life leech|mana leech)\b", re.I)
DAMAGE_RX = re.compile(r"\bdamage\b|\bdps\b|projectiles?|repeat|chain|hits?\b|strikes?\b|magnitude", re.I)
# Recursos que só existem dentro de uma skill: os Stages do Flameblast não alimentam o Volcano.
PER_SKILL_RESOURCES = {"stage"}


def axis_of(text: str) -> str:
    """Em que eixo o multiplicador paga: 'dano', 'defesa' ou 'acumulo'."""
    if BUILDUP_RX.search(text):
        return "acumulo"
    if DEFENCE_RX.search(text) and not DAMAGE_RX.search(text):
        return "defesa"
    return "dano"


def verbs_for(clause: str, start: int, end: int, resource: str) -> list[str]:
    """Verbos de uma menção: até 2 estruturais, senão o primeiro simples."""
    lo, hi = max(0, start - 140), min(len(clause), end + 140)
    window = clause[lo:start] + _TOKEN + clause[end:hi]
    category = CATEGORY.get(resource)
    found = []
    for verb, patterns in _COMPILED:
        if verb == "PARTICIPLE":
            # "Ignited enemies" lê o estado; "become Empowered" produz.
            if category == "state" and _PARTICIPLE.search(clause[start:end]):
                found.append("PRODUCES" if _BECOMES.search(clause[lo:start]) else "READS")
        elif verb not in found and any(p.search(window) for p in patterns):
            found.append(verb)
    # Reservatórios não têm "teto destravado": vida máxima é só um stat maior.
    if category == "pool":
        found = ["AMPLIFIES" if v == "UNLOCKS" and "maximum" in window.lower() else v for v in found]
    # Evento não é "produzido": "inflict X on Hit" lê o hit.
    if category == "event":
        found = ["READS" if v == "PRODUCES" else v for v in found]
    found = list(dict.fromkeys(found))
    structural = [v for v in found if v in _STRUCTURAL][:2]
    if structural:
        return structural
    if found:
        return found[:1]
    return ["READS"] if category == "event" else []


# ---------- registros ----------
_RECORD_KINDS = {"SKILL", "META", "SUPPORT", "PASSIVE", "NOTABLE", "KEYSTONE", "ASCENDANCY_NODE"}
# Kinds lidos dos itens do PoB (o catálogo RePoE não tem texto de item).
JEWEL_KINDS = {"JEWEL_MOD", "TIME_LOST", "JEWEL_UNIQUE", "TIMELESS"}
AUGMENT_KINDS = {"RUNE", "SOUL_CORE", "IDOL", "AUGMENT"}
ITEM_KINDS = {"UNIQUE", "MOD"} | JEWEL_KINDS | AUGMENT_KINDS

# Poder por magnitude que não cita um recurso do léxico (porte do PoE 1, 2026-11-07). No PoE 1, a varredura de uso
# (poe.ninja 3.29) achou cada família num item muito usado que o mapa deixava em 0. No PoE 2, o Gemling Legionnaire
# (2% no dia 3 da Runes of Aldur, 37,5% no dia 3 da Forbidden Rites) tinha os nós-chave com nota 0: nível de gem,
# qualidade de gem e supports conectados não eram recursos. (pseudo-recurso, verbo, score, regra sobre a linha)
MAGNITUDE = [
    # PoE 1, Ming's Heart: "Gain 60% of Physical Damage as Extra Chaos Damage"
    ("damage as extra", "CONVERTS", 3, re.compile(r"\bgain (?:an? )?(?:additional )?\d+% of [^.]{0,40}damage as extra\b", re.I)),
    # PoE 1, Mystic Refractor: "Skills fire 3 additional Projectiles"
    ("additional projectiles", "REPLICATES", 2.5,
     re.compile(r"\b(?:fires?|skills fire|shoots?) (?:an? |\d+ )additional projectiles?\b", re.I)),
    # PoE 1, Nebulis: "8% increased Elemental Damage per 1% ... Resistance above 75%"
    ("resistance overcap", "READS", 3, re.compile(r"\bper \d+% [^.]{0,50}resistances? above (?:75%|maximum)", re.I)),
    # PoE 1, The Taming: "for each type of Elemental Ailment on Enemy"
    ("ailment types", "READS", 3,
     re.compile(r"\b(?:for each|per) (?:type of |different )?(?:elemental )?ailments?\b[^.]{0,20}(?:on|inflicted|affecting)", re.I)),
    # PoE 2, Gemling: "+2 to Level of all Skills with an Intelligence requirement", "+1 to Level of all Minion Skills"
    ("gem levels", "AMPLIFIES", 2,
     re.compile(r"\+\d+ to level of (?:all )?(?:[\w-]+ ){0,5}(?:skills?|skill gems|gems)\b", re.I)),
    # PoE 2, Gemling: "Gem Quality grants Socketed Skills an additional effect" (a qualidade paga duas vezes em cada
    # gem) e "+2% to Quality of all Skills"
    ("gem quality", "AMPLIFIES", 3, re.compile(r"\bgem quality grants\b[^.]{0,40}additional effect", re.I)),
    ("gem quality", "AMPLIFIES", 1.5, re.compile(r"\+\d+% to quality of (?:all )?(?:[\w-]+ ){0,3}(?:skills?|gems)\b", re.I)),
    # PoE 2, Gemling: "per Connected Red Support Gem", "per 3 Blue Support Gems Socketed", "colour of Socketed Support"
    ("support gems", "READS", 2,
     re.compile(r"\b(?:per|for each) (?:\d+ )?(?:connected |socketed )?(?:colour of )?(?:socketed )?(?:red |green |blue )?support gems?\b", re.I)),
    # PoE 2, Gemling Essence of Virtue: "Grants Skill: Virtuous Barrier" (skill de graça, sem slot de gem)
    ("granted skill", "UNLOCKS", 2, re.compile(r"^grants skill: ", re.I)),
]
MAGNITUDE_CATEGORY = {"damage as extra": "stat", "additional projectiles": "stat", "resistance overcap": "stat",
                      "ailment types": "stat", "gem levels": "stat", "gem quality": "stat", "support gems": "entity",
                      "granted skill": "entity"}
CATEGORY.update(MAGNITUDE_CATEGORY)

# Atalhos aceitos no filtro `kinds` das ferramentas: JEWELS = só joias, AUGMENTS = só augments de item.
KIND_GROUPS = {
    "JEWELS": JEWEL_KINDS, "AUGMENTS": AUGMENT_KINDS, "ITEMS": ITEM_KINDS,
    "GEMS": {"SKILL", "META", "SUPPORT"}, "TREE": {"PASSIVE", "NOTABLE", "KEYSTONE", "ASCENDANCY_NODE"},
}
# Degrau de obtenção (método do autor): 1 garantido, 2 craft simples, 3 roll alto/drop limitado, 4 específico.
# Estimativa por tipo de item, não por item: um Rune raro ou um Soul Core comum fogem da tabela.
DEGRAU = {"MOD": 2, "JEWEL_MOD": 2, "RUNE": 1, "SOUL_CORE": 3, "IDOL": 3, "AUGMENT": 4,
          "TIME_LOST": 4, "UNIQUE": 4, "JEWEL_UNIQUE": 4, "TIMELESS": 4}
RADIUS_NOTE = ("O valor depende dos nós dentro do raio no socket escolhido; não é um número fixo. "
               "Medir no PoB com a joia encaixada.")
SOCKET_NOTE = "Ocupa um socket de item: Runes, Soul Cores e Idols se excluem no mesmo socket."
JEWEL_BASES = {"Ruby", "Emerald", "Sapphire", "Diamond", "Timeless Jewel"}
_JEWEL_BASE_OF = {"strjewel": "Ruby", "dexjewel": "Emerald", "intjewel": "Sapphire",
                  "str_radius_jewel": "Time-Lost Ruby", "dex_radius_jewel": "Time-Lost Emerald",
                  "int_radius_jewel": "Time-Lost Sapphire", "radius_jewel": "Time-Lost (qualquer)"}
# Legião -> joia Timeless que existe na 0.5. As outras legiões do arquivo são herança do PoE1.
TIMELESS_JEWELS = {"kalguur": ("Heroic Tragedy", "Kalguur"), "abyss": ("Undying Hate", "Abyssals")}


def _item_record(rid: str, kind: str, name: str, owner: str, lines, tags, source: str, radius: str = "") -> dict:
    lines = [str(l).replace("\\n", " ") for l in lines]
    out = {"id": rid, "kind": kind, "name": name, "owner": owner, "ascendancy": "", "tags": list(tags),
           "lines": lines, "originals": lines, "source": source, "degrau": DEGRAU.get(kind)}
    if radius:
        out["radius"] = radius
        out["note"] = RADIUS_NOTE
    elif kind in AUGMENT_KINDS:
        out["note"] = SOCKET_NOTE
    return out


def records_from_uniques(uniques) -> list[dict]:
    """Uniques do PoB como registros do mapa: são os conectores que o catálogo RePoE não tem.

    Joias unique (bases Ruby/Emerald/Sapphire/Diamond/Timeless/Time-Lost) viram JEWEL_UNIQUE, com o raio.
    """
    out = []
    for u in uniques:
        if not u.get("lines"):
            continue
        base = u.get("base") or ""
        jewel = base in JEWEL_BASES or base.startswith("Time-Lost")
        kind = "JEWEL_UNIQUE" if jewel else "UNIQUE"
        tags = [u["league"]] if u.get("league") else []
        out.append(_item_record(f'unique:{u["name"]}', kind, u["name"], base, u["lines"], tags,
                                "Uniques/jewel.lua" if jewel else "Uniques/*.lua",
                                radius=(u.get("radius") or "") if jewel else ""))
    return out


def _best_by_group(mods):
    best = {}
    for mod in mods:
        if mod["group"] not in best or mod["level"] > best[mod["group"]]["level"]:
            best[mod["group"]] = mod
    return best.values()


def records_from_mods(mods) -> list[dict]:
    """Mods de item do PoB, um registro por grupo (o tier mais alto), com as classes de item que o recebem."""
    out = []
    for mod in _best_by_group(mods):
        slots = [k for k, v in mod["weights"] if v > 0 and k != "default"]
        if not slots:
            continue
        lines = [l.replace("\\n", " ") for l in mod["lines"]]
        out.append(_item_record(f'mod:{mod["id"]}', "MOD", f'{mod["type"]}: {lines[0]}', ", ".join(slots[:6]),
                                lines, slots, "ModItem.lua"))
    return out


def records_from_jewel_mods(mods) -> list[dict]:
    """Afixos de ModJewel.lua: JEWEL_MOD (joia rara) ou TIME_LOST (afixo de raio), por grupo."""
    out, seen = [], set()
    for mod in mods:
        keys = [k for k, v in mod["weights"] if v > 0 and k != "jewel"]
        if not keys:
            continue
        radius = any(k.endswith("radius_jewel") for k in keys)
        # Afixo de raio e afixo de joia rara dividem o grupo no PoB: um registro de cada.
        if (mod["group"], radius) in seen:
            continue
        seen.add((mod["group"], radius))
        bases = [_JEWEL_BASE_OF.get(k, k) for k in keys]
        lines = [l.replace("\\n", " ") for l in mod["lines"]]
        # Nos Time-Lost o afixo vale para as passivas pequenas dentro do raio; o PoB guarda só o stat.
        name = f'Time-Lost {mod["type"]} in Radius: {lines[0]}' if radius else f'{mod["type"]}: {lines[0]}'
        out.append(_item_record(f'jewelmod:{mod["id"]}', "TIME_LOST" if radius else "JEWEL_MOD", name,
                                ", ".join(bases), lines, bases, "ModJewel.lua",
                                radius="Small na base; Medium/Large por afixo" if radius else ""))
    return out


def records_from_augments(augments) -> list[dict]:
    """Runes, Soul Cores, Idols (e outros augments de ModRunes.lua): um registro por item, slots nas tags."""
    kinds = {"Rune": "RUNE", "SoulCore": "SOUL_CORE", "Idol": "IDOL"}
    out = []
    for a in augments:
        lines = list(dict.fromkeys(l for slot_lines in a["slots"].values() for l in slot_lines))
        if not lines:
            continue
        slots = list(a["slots"])
        kind = kinds.get(a["type"], "AUGMENT")
        tags = ([a["type"]] if kind == "AUGMENT" else []) + slots
        out.append(_item_record(f'augment:{a["name"]}', kind, a["name"], ", ".join(slots[:6]), lines, tags, "ModRunes.lua"))
    return out


def records_from_timeless(passives, jewels=None) -> list[dict]:
    """Passivas concedidas pelas joias Timeless (por tipo de passiva, não por seed), só das legiões com joia na 0.5."""
    jewels = TIMELESS_JEWELS if jewels is None else jewels
    out = []
    for p in passives:
        if p["legion"] not in jewels or not p.get("lines"):
            continue
        jewel, legion = jewels[p["legion"]]
        out.append(_item_record(f'timeless:{p["id"]}', "TIMELESS", f'{p["name"]} ({jewel})', jewel, p["lines"],
                                [legion, p["kind"]], "TimelessJewelData/LegionPassives.lua", radius="Very Large"))
    return out


def pob_records() -> tuple[list[dict], dict]:
    """Registros extras lidos do PoB instalado; vazio (com o motivo) quando ele não está configurado."""
    try:
        from src.lab import data
        uniques, mods, quality = data.load_uniques(), data.load_mods(), data.quality_effects()
    except Exception as exc:
        return [], {"pob_items": f"indisponível: {exc}"}
    records = records_from_uniques(uniques) + records_from_mods(mods)
    lacunas = []
    for label, loader, builder in (("joias (ModJewel.lua)", lambda: data.load_mods("ModJewel.lua"), records_from_jewel_mods),
                                   ("augments (ModRunes.lua)", data.load_augments, records_from_augments),
                                   ("Timeless (LegionPassives.lua)", data.load_timeless, records_from_timeless)):
        try:
            loaded = loader()
            records += builder(loaded)
            if builder is records_from_timeless:
                leftover = sorted({p["legion"] for p in loaded if p["legion"] not in TIMELESS_JEWELS})
                if leftover:
                    lacunas.append(f"Timeless: legiões sem joia na 0.5 ignoradas ({', '.join(leftover)}); seeds não enumeradas.")
        except Exception as exc:
            lacunas.append(f"{label} indisponível: {exc}")
    lacunas.append("Cluster jewels: sem base nem unique nos dados da 0.5; não importados.")
    lacunas.append("Joias de raio e Timeless: o efeito depende dos nós no raio; só o texto do afixo entra no mapa.")
    counts = Counter(r["kind"] for r in records)
    info = {"pob_items": {"uniques": len(uniques), "mod_groups": counts["MOD"],
                          "quality_effects": sum(1 for q in quality.values() if q["additional"]),
                          "by_kind": {k: counts[k] for k in sorted(ITEM_KINDS) if counts[k]},
                          "lacunas": lacunas}}
    return records, info


def expand_kinds(kinds) -> set[str] | None:
    """Filtro `kinds` com atalhos (JEWELS, AUGMENTS, ITEMS, GEMS, TREE) expandidos; None = sem filtro."""
    if not kinds:
        return None
    out = set()
    for k in kinds:
        key = str(k).strip().upper()
        if not key:
            continue
        out |= KIND_GROUPS.get(key, {key})
    return out or None


def record_from_entity(entity: dict) -> dict | None:
    """Reduz uma entidade do catálogo a nome + linhas de texto únicas."""
    if entity.get("kind") not in _RECORD_KINDS:
        return None
    if entity.get("availability") not in (None, "", "released", "not_verified"):
        return None
    if "DNT" in str(entity.get("name") or ""):
        return None
    texts = list(entity.get("texts") or [])
    for component in entity.get("components") or []:
        texts.extend(component.get("texts") or [])
    lines: dict[str, tuple[str, str]] = {}
    for t in texts:
        original = str(t.get("original") or t.get("text") or "")
        if not original.strip() or "DNT" in original:
            continue
        for part in _SENTENCE.split(original):
            part = part.strip()
            if not part:
                continue
            clean, _spans = parse_markup(part)
            # Texto por nível de gem só muda o número: fica o último (nível mais alto).
            lines[_NUMBER.sub("#", clean)] = (clean, part)
    if not lines:
        return None
    return {
        "id": entity["id"], "kind": entity["kind"], "name": entity.get("name") or "",
        "owner": entity.get("ascendancy") or entity.get("attribute") or "",
        "ascendancy": entity.get("ascendancy") or "",
        "tags": list(entity.get("tags") or []),
        "lines": [clean for clean, _orig in lines.values()],
        "originals": [orig for _clean, orig in lines.values()],
    }


def edges_for(record: dict) -> list[dict]:
    edges = []
    for original in record["originals"]:
        clause, spans = parse_markup(original)
        for family, verb, score, rx in MAGNITUDE:
            if rx.search(clause):
                edges.append({"resource": family, "verb": verb, "text": clause, "fixed": score})
        found = mentions(clause, spans, plain_tags=record.get("kind") in ITEM_KINDS)
        for resource, s, e in found:
            for verb in verbs_for(clause, s, e, resource) or ["AMBIGUOUS"]:
                name = f'{resource} ({record["name"]})' if resource in PER_SKILL_RESOURCES else resource
                edges.append({"resource": name, "verb": verb, "text": clause})
    resolved = {x["resource"] for x in edges if x["verb"] != "AMBIGUOUS"}
    seen, out = set(), []
    for x in edges:
        if x["verb"] == "AMBIGUOUS" and x["resource"] in resolved:
            continue
        key = (x["resource"], x["verb"], x["text"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


class EconomyMap:
    def __init__(self, records: list[dict], meta: dict | None = None, quality: dict | None = None):
        self.records = records
        self.meta = meta or {}
        self.quality = quality or {}  # gem -> efeitos de qualidade (normal e adicional), do PoB
        self.edges = []
        for index, record in enumerate(records):
            for edge in edges_for(record):
                edge["i"] = index
                self.edges.append(edge)
        self.resources = self._resource_table()

    @classmethod
    def from_entities(cls, entities, meta: dict | None = None) -> "EconomyMap":
        records = [r for r in (record_from_entity(e) for e in entities) if r]
        return cls(records, meta)

    def _resource_table(self) -> dict[str, dict]:
        by_resource = defaultdict(list)
        for e in self.edges:
            by_resource[e["resource"]].append(e)
        table = {}
        for name, edges in by_resource.items():
            verbs = Counter(e["verb"] for e in edges)
            producers = [self.records[e["i"]] for e in edges if e["verb"] == "PRODUCES"]
            sinks = defaultdict(set)
            for e in edges:
                if e["verb"] in ("READS", "REPLICATES", "CONSUMES"):
                    sinks[axis_of(e["text"])].add(e["i"])
            table[name] = {
                "resource": name, "category": CATEGORY.get(name.split(" (")[0], ""), "mentions": len(edges),
                # o recurso que "paga duas vezes": quantos registros distintos leem o recurso em cada eixo
                "sinks_dano": len(sinks["dano"]), "sinks_defesa": len(sinks["defesa"]),
                "paga_em": sorted(k for k in ("dano", "defesa") if sinks[k]),
                "producers": verbs["PRODUCES"], "consumers": verbs["CONSUMES"], "readers": verbs["READS"],
                "replicas": verbs["REPLICATES"], "unlocks": verbs["UNLOCKS"], "limits": verbs["LIMITS"],
                "amplifies": verbs["AMPLIFIES"], "conversions": verbs["CONVERTS"], "ambiguous": verbs["AMBIGUOUS"],
                "producer_slots": dict(Counter(r["kind"] for r in producers)),
            }
        return table

    # ---------- consultas ----------
    def _edge_out(self, e: dict) -> dict:
        r = self.records[e["i"]]
        out = {"resource": e["resource"], "verb": e["verb"], "text": e["text"],
               "name": r["name"], "kind": r["kind"], "id": r["id"]}
        if r["ascendancy"]:
            out["ascendancy"] = r["ascendancy"]
        self._item_fields(r, out)
        q = self.quality.get(r["name"])
        if q and q.get("additional"):
            # O que a qualidade passa a fazer com Advanced Thaumaturgy (por 1% de qualidade).
            out["quality_additional"] = [f"{stat} {value:g}/1%" for stat, value in q["additional"]]
        return out

    @staticmethod
    def _item_fields(r: dict, out: dict) -> dict:
        """Campos de item: base/slot, degrau de obtenção, raio e aviso (raio ou socket exclusivo)."""
        if r["kind"] in ITEM_KINDS:
            out["item"] = r["owner"]
            for key in ("degrau", "radius", "note", "source"):
                if r.get(key) is not None:
                    out[key] = r[key]
        return out

    def _pass(self, e: dict, kinds: set[str] | None, ascendancy: str) -> bool:
        r = self.records[e["i"]]
        if kinds and r["kind"] not in kinds:
            return False
        # Nós de outra ascendência não são alcançáveis pela build.
        return not (ascendancy and r["ascendancy"] and r["ascendancy"].casefold() != ascendancy.casefold())

    def resolve(self, name: str) -> str | None:
        q = str(name or "").strip().casefold()
        if not q:
            return None
        if q in self.resources:
            return q
        for candidate in sorted(self.resources):
            if candidate.startswith(q):
                return candidate
        return next((c for c in sorted(self.resources) if q in c), None)

    def status(self) -> dict:
        by_category = defaultdict(list)
        for name, row in sorted(self.resources.items()):
            by_category[row["category"] or "outros"].append(name)
        return {"ok": True, "meta": self.meta, "records": len(self.records), "edges": len(self.edges),
                "records_by_kind": dict(sorted(Counter(r["kind"] for r in self.records).items())),
                "kind_groups": {k: sorted(v) for k, v in KIND_GROUPS.items()},
                "verbs": VERBS, "method": METHOD, "resources_by_category": dict(by_category)}

    @staticmethod
    def _anchor_score(e: dict, include_plain_reads: bool) -> float:
        axis = axis_of(e["text"])
        if axis == "acumulo":
            return 0
        more = bool(MORE_RX.search(e["text"]))
        if "fixed" in e:  # família de MAGNITUDE: score pela regra
            base = e["fixed"]
        elif e["verb"] == "REPLICATES":
            base = 5
        elif e["verb"] == "READS" and more:
            base = 4
        elif e["verb"] == "CONSUMES" and more:
            base = 3.5
        elif e["verb"] == "UNLOCKS":
            base = 2
        elif e["verb"] == "READS" and include_plain_reads:
            base = 1
        else:
            return 0
        # Multiplicador de defesa vale, mas não compete de igual com um de dano.
        return base / 2 if axis == "defesa" else base

    def anchors(self, resource: str = "", kinds=None, ascendancy: str = "", include_plain_reads: bool = False,
                include_universal: bool = False, limit: int = 40) -> dict:
        want = self.resolve(resource) if resource else None
        if resource and not want:
            return {"ok": False, "error": f'Nenhum recurso casa com "{resource}". Chame economy_status para ver a lista.'}
        kinds = expand_kinds(kinds)
        cap = max(1, min(int(limit or 40), 200))
        scored = []
        for e in self.edges:
            if want and e["resource"] != want:
                continue
            if not want and not include_universal and e["resource"] in UNIVERSAL:
                continue
            if not self._pass(e, kinds, ascendancy):
                continue
            score = self._anchor_score(e, include_plain_reads)
            if score:
                row = self.resources[e["resource"]]
                # Desempate: recurso com mais formas de ser produzido e amplificado escala mais.
                scored.append((score, row["producers"] + row["amplifies"] + row["unlocks"], e))
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]["resource"], x[2]["text"]))
        seen, results, per_resource = set(), [], Counter()
        for score, _breadth, e in scored:
            r = self.records[e["i"]]
            # Uma linha por registro+recurso; passivas pequenas repetem o mesmo nó várias vezes.
            key = (r["name"], r["kind"], e["resource"])
            if key in seen:
                continue
            seen.add(key)
            per_resource[e["resource"]] += 1
            if len(results) >= cap:
                continue
            row = self.resources[e["resource"]]
            results.append({"score": score, "axis": axis_of(e["text"]), **self._edge_out(e),
                            "scaling": {"producers": row["producers"], "producer_slots": row["producer_slots"],
                                        "amplifies": row["amplifies"], "unlocks": row["unlocks"],
                                        "limits": row["limits"]}})
        # Onde há mais multiplicadores possíveis: recursos com mais âncoras distintas.
        by_resource = [{"resource": name, "anchors": count, "producers": self.resources[name]["producers"],
                        "amplifies": self.resources[name]["amplifies"], "unlocks": self.resources[name]["unlocks"],
                        "paga_em": self.resources[name]["paga_em"]}
                       for name, count in per_resource.most_common(15)]
        return {"ok": True, "total": len(seen), "by_resource": by_resource, "results": results,
                "hint": "Próximo: economy_resource no recurso da âncora com verbs=[PRODUCES, UNLOCKS] para listar conectores."}

    def resource(self, resource: str, verbs=None, kinds=None, ascendancy: str = "", limit_per_verb: int = 25) -> dict:
        name = self.resolve(resource)
        if not name:
            return {"ok": False, "error": f'Nenhum recurso casa com "{resource}". Chame economy_status para ver a lista.'}
        wanted = {str(v).upper() for v in verbs} if verbs else None
        kinds = expand_kinds(kinds)
        per = max(1, min(int(limit_per_verb or 25), 200))
        groups = defaultdict(list)
        for e in self.edges:
            if e["resource"] == name and (not wanted or e["verb"] in wanted) and self._pass(e, kinds, ascendancy):
                groups[e["verb"]].append(e)
        by_verb = {}
        for verb in VERBS:
            if verb in groups:
                g = groups[verb]
                by_verb[verb] = {"count": len(g), "meaning": VERBS[verb],
                                 "edges": [self._edge_out(e) for e in g[:per]], "truncated": len(g) > per}
        return {"ok": True, "resource": self.resources[name], "by_verb": by_verb}

    def pairs(self, resource: str = "", kinds=None, ascendancy: str = "", limit: int = 30) -> dict:
        """Pares skill -> skill: um registro PRODUCES o recurso, outro o lê, consome ou replica com 'more'.

        É onde a assimetria costuma morar no PoE 2 (Whirling Slash cria Whirlwind; Twister consome e replica).
        Mesma pontuação de anchors; o par exige registros diferentes. `self_loop` marca âncora que também produz.
        """
        want = self.resolve(resource) if resource else None
        if resource and not want:
            return {"ok": False, "error": f'Nenhum recurso casa com "{resource}". Chame economy_status para ver a lista.'}
        kinds = expand_kinds(kinds)
        cap = max(1, min(int(limit or 30), 200))
        producers, anchors = defaultdict(list), []
        for e in self.edges:
            if want and e["resource"] != want:
                continue
            if not want and e["resource"] in UNIVERSAL:
                continue
            if not self._pass(e, kinds, ascendancy):
                continue
            if e["verb"] == "PRODUCES":
                producers[e["resource"]].append(e)
            else:
                score = self._anchor_score(e, False)
                if score and e["verb"] != "UNLOCKS":
                    anchors.append((score, e))
        anchors.sort(key=lambda x: (-x[0], x[1]["resource"], x[1]["text"]))
        rows, seen, without = [], set(), []
        for score, e in anchors:
            r = self.records[e["i"]]
            key = (r["name"], r["kind"], e["resource"])
            if key in seen:
                continue
            seen.add(key)
            others, mine = {}, False
            for p in producers.get(e["resource"], []):
                pr = self.records[p["i"]]
                if pr["name"] == r["name"] and pr["kind"] == r["kind"]:
                    mine = True
                    continue
                others.setdefault((pr["name"], pr["kind"]), self._edge_out(p))
            row = {"score": score, "axis": axis_of(e["text"]), "anchor": self._edge_out(e), "self_loop": mine,
                   "producers": list(others.values())[:8], "producer_count": len(others),
                   "producer_slots": dict(Counter(k for _n, k in others))}
            (rows if others else without).append(row)
        return {"ok": True, "total": len(rows), "results": rows[:cap],
                "anchors_without_producer": [{"anchor": w["anchor"], "score": w["score"], "self_loop": w["self_loop"]}
                                             for w in without[:10]],
                "hint": "Par = hipótese por texto. Medir no lab a âncora com e sem a condição que o produtor cria; "
                        "o que o PoB não modela fica pendente de jogo."}

    def lookup(self, query: str, kinds=None, limit: int = 30) -> dict:
        q = str(query or "").strip().casefold()
        if not q:
            return {"ok": False, "error": "Informe um texto para buscar."}
        kinds = expand_kinds(kinds)
        per_record = defaultdict(list)
        for e in self.edges:
            pair = {"resource": e["resource"], "verb": e["verb"]}
            if pair not in per_record[e["i"]]:
                per_record[e["i"]].append(pair)
        hits = []
        for index, r in enumerate(self.records):
            if kinds and r["kind"] not in kinds:
                continue
            in_name = q in r["name"].casefold()
            if in_name or any(q in line.casefold() for line in r["lines"]):
                hits.append((0 if r["name"].casefold() == q else 1 if in_name else 2, r["name"], index))
        hits.sort()
        cap = max(1, min(int(limit or 30), 200))
        return {"ok": True, "query": query, "total": len(hits), "truncated": len(hits) > cap,
                "results": [self._item_fields(self.records[i], {
                                "name": self.records[i]["name"], "kind": self.records[i]["kind"],
                                "id": self.records[i]["id"], "ascendancy": self.records[i]["ascendancy"] or None,
                                "text": self.records[i]["lines"], "resources": per_record.get(i, [])})
                            for _rank, _name, i in hits[:cap]]}


# ---------- cache sobre o catálogo do Finder ----------
_lock = threading.Lock()
_cached: tuple[str, EconomyMap] | None = None


def current_map() -> EconomyMap:
    """Mapa do catálogo importado; reconstruído só quando a importação muda."""
    global _cached
    from src import storage
    meta = storage.meta()
    stamp = json.dumps(meta, sort_keys=True, ensure_ascii=False)
    with _lock:
        if _cached and _cached[0] == stamp:
            return _cached[1]
        with storage.connect() as c:
            entities = [json.loads(row["payload"]) for row in c.execute("SELECT payload FROM entities")]
        info = {key: {k: value.get(k) for k in ("source", "repoe_version", "imported_at")}
                for key, value in meta.items() if isinstance(value, dict)}
        extra, extra_info = pob_records()
        info.update(extra_info)
        records = [r for r in (record_from_entity(e) for e in entities) if r] + extra
        try:
            from src.lab import data
            quality = data.quality_effects()
        except Exception:
            quality = {}
        built = EconomyMap(records, info, quality)
        _cached = (stamp, built)
        return built
