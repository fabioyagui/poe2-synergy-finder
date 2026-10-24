"""Build por etapas de nível: um XML do PoB por faixa, com gems, árvore e inimigo daquele nível (PoE 2).

Método do autor (Game Brain, 2026-10-18): cada etapa fecha num nível, é válida sozinha e tem os
seus próprios números medidos; um respec é uma etapa à parte, com números antes e depois no
mesmo nível. Porte do projeto PoE 1 (2026-10-24) com as regras do PoE 2: sem maestrias e sem
bandido; pontos de missão lidos de Data/QuestRewards.lua do PoB; ascendência pelos Trials (ver
judge.ASCENSIONS); penalidade de resistência por ato. A parte pura não depende do motor; `run`
usa a sessão de laboratório aberta.
"""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from src.lab import bench, data
from src.lab.engine import DEFENCE_FIELDS, FIELDS, MINION_FIELDS, Lab, gem_level, xml_groups

DEFAULT_LEVELS = (15, 30, 45, 60, 75, 90)
# (nível em que o PoB considera o ato, pontos de missão acumulados até ali), calculado como em
# Modules/Build.lua do PoB 2 a partir de Data/QuestRewards.lua (0.5). `load_acts` lê o PoB instalado.
ACTS_FALLBACK = ((1, 0), (12, 4), (28, 8), (44, 12), (51, 16), (62, 24))
FIXED_KINDS = {"ClassStart", "AscendClassStart"}  # tipos de nó do PoB que não custam ponto
# Nível a partir do qual a etapa é de mapas (fim da campanha 0.5, Interlúdios incluídos). [VERIFY in game]
MAPS_LEVEL = 65
APROXIMACOES = [
    "Pontos de passiva = nível − 1 + pontos de missão do último ato cujo nível o personagem já alcançou (tabela que "
    "Modules/Build.lua do PoB monta de Data/QuestRewards.lua; supõe todas as missões de ponto feitas). Pontos de "
    "conjunto de armas (weapon set) não são contados à parte.",
    "A árvore de cada etapa segue a ordem de alocação da sessão (tree_search e allocate). Nós alocados antes "
    "disso (build carregada) não têm ordem e entram primeiro.",
    "Nós de ascendência entram na ordem em que a sessão os alocou, até os pontos da última ascensão cujo nível o "
    "personagem já alcança (judge.ASCENSIONS, [VERIFY in game]); o início da ascendência é fixo.",
    "Penalidade de resistência por ato (0, −10, … −50) e −60 a partir do nível de mapas: escala da config do PoB 2 "
    "aplicada aos atos de QuestRewards.lua [VERIFY in game].",
    "Gems cujo nível mínimo é maior que o nível da etapa ficam de fora dela (anotado em cada etapa).",
    "Gear: sem `gear` no pedido, é o da sessão em todas as etapas. Com `gear` {nível: [{slot, text, degrau?}]}, cada "
    "etapa usa os itens definidos até o seu nível (o mais recente por slot); o PoB não impede equipar item de nível "
    "acima do personagem.",
    "Skills concedidas por item ou nó (ex.: Hysseg's Claw, Wild Protector) ficam como o PoB as gera; os números de "
    "minion são de um minion, não do grupo.",
]


# ---------- parte pura ----------
def acts_from_quests(text: str) -> tuple:
    """Data/QuestRewards.lua -> ((nível, pontos acumulados), ...), na mesma conta de Modules/Build.lua."""
    acts = [[1, 0]]
    for body in re.findall(r"\{(.*?)\n\t\}", text, re.S):
        get = lambda k: (re.search(r'\["%s"\] = "?([^",\n]*)"?' % k, body) or [None, None])[1]
        points = get("questPoints")
        if not points:
            continue
        act = int(get("Act")) + (3 if get("Type") == "Cruel" else 0) + 1
        level = int(float(get("AreaLevel") or 0))
        while len(acts) < act:
            acts.append(None)
        if acts[act - 1] is None:
            acts[act - 1] = [level, int(points) + (acts[act - 2] or [0, 0])[1]]
        else:
            acts[act - 1][1] += int(points)
            acts[act - 1][0] = max(acts[act - 1][0], level)
    return tuple((a, b) for a, b in (x for x in acts if x))


def load_acts() -> tuple:
    """Tabela (nível, pontos de missão) do PoB instalado, ou a cópia local."""
    try:
        found = acts_from_quests((data.pob_data_dir() / "QuestRewards.lua").read_text(encoding="utf-8"))
    except Exception:
        return ACTS_FALLBACK
    return found if len(found) >= 4 else ACTS_FALLBACK


def act_index(level: int, acts=ACTS_FALLBACK) -> int:
    """Ato (1-based, na ordem de nível) estimado pelo nível: quantos níveis de ato o personagem já alcançou."""
    return max(1, sum(1 for lvl, _q in sorted(acts) if lvl <= level))


def quest_points(level: int, acts=ACTS_FALLBACK) -> int:
    return max((q for lvl, q in acts if lvl <= level), default=0)


def passive_points(level: int, acts=ACTS_FALLBACK) -> int:
    return level - 1 + quest_points(level, acts)


def resistance_penalty(level: int, acts=ACTS_FALLBACK) -> int:
    """0 no primeiro ato, −10 por ato depois dele (até −50) e −60 a partir do nível de mapas. [VERIFY in game]"""
    if level >= MAPS_LEVEL:
        return -60
    return -min(50, 10 * (act_index(level, acts) - 1))


def stage_config(level: int, acts=ACTS_FALLBACK) -> dict:
    return bench.enemy_config(level, resistancePenalty=resistance_penalty(level, acts))


def safe_name(name: str) -> str:
    return re.sub(r"[^\w\-. ]+", "_", str(name or "")).strip()


def stage_filename(level: int, motivo: str | None = None) -> str:
    if motivo is None:
        return f"L{level}.xml"
    return f"L{level} respec - {safe_name(motivo) or 'respec'}.xml"


def nodes_for(base, ordem, budget: int) -> list[int]:
    """Nós de uma etapa: os sem ordem conhecida primeiro, depois a ordem de alocação; corta no orçamento."""
    seen, out = set(), []
    for n in list(base) + list(ordem):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:max(0, int(budget))]


def _gem(g) -> tuple[str, int | None]:
    if isinstance(g, str):
        name, quality = g, None
    elif isinstance(g, dict):
        name, quality = g.get("name"), g.get("quality")
    elif isinstance(g, (list, tuple)) and g and isinstance(g[0], str):
        name, quality = g[0], g[1] if len(g) > 1 else None
    else:
        raise ValueError(f"gem inválida: {g!r}. Use nome, [nome, qualidade] ou {{name, quality}}.")
    name = str(name or "").strip()
    if not name:
        raise ValueError("gem sem nome")
    return name, (int(quality) if quality not in (None, "") else None)


def parse_gems(raw) -> list[list[tuple[str, int | None]]]:
    """gems do pedido -> grupos de (nome, qualidade).

    Grupos: [["Wolf Pack", "Feeding Frenzy I", ["Hulking Minions", 20]], ["Herald of Ice"]]. Uma lista só de
    nomes (ou de {name, quality}) é um grupo. A primeira gem de cada grupo é a skill ativa; o nível vem do nível
    da etapa.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("gems deve ser uma lista de grupos (listas de gems) ou uma lista de nomes (um grupo)")
    groups = [raw] if all(isinstance(g, (str, dict)) for g in raw) else raw
    out = []
    for group in groups:
        if not isinstance(group, (list, tuple)) or not group:
            raise ValueError(f"grupo inválido: {group!r}")
        out.append([_gem(g) for g in group])
    return out


def _tier(name: str) -> int | None:
    try:
        return (data.gem_info(name) or {}).get("tier")
    except Exception:
        return None


def gem_plan(groups, char_level: int, levels_of=None, tier_of=None) -> list[list[dict]]:
    """Nível de cada gem numa etapa: o maior que o nível do personagem permite (0 = ainda não liberada).

    A skill ativa (primeira gem do grupo) só existe quando esse nível alcança o tier dela: no PoE 2 ela é cortada
    de uma gema bruta do nível do tier (Wolf Pack, tier 8, só a partir do personagem nível 26).
    """
    levels_of = levels_of or data.gem_levels
    tier_of = tier_of or _tier
    plan = []
    for group in groups:
        rows = []
        for i, (name, quality) in enumerate(group):
            lvl = gem_level(char_level, levels_of(name))
            tier = tier_of(name) if i == 0 else None
            rows.append({"name": name, "quality": quality, "level": lvl, "tier": tier,
                         "liberada": lvl >= 1 and not (tier and lvl < tier)})
        plan.append(rows)
    return plan


def xml_gems(xml: str) -> list[list[tuple[str, int | None]]]:
    """Grupos de gems do XML da sessão (sem os concedidos por item ou nó): (nome, qualidade) na ordem do PoB."""
    out = []
    for attrs, block in re.findall(r"<Skill\b([^>]*)>(.*?)</Skill>", xml, re.S):
        if re.search(r'\bsource="[^"]+"', attrs):
            continue
        gems = []
        for tag in re.findall(r"<Gem\b[^>]*>", block):
            name = re.search(r'nameSpec="([^"]*)"', tag)
            quality = re.search(r'quality="(\d+)"', tag)
            if name and name.group(1):
                q = int(quality.group(1)) if quality else 0
                gems.append((name.group(1), q or None))
        if gems:
            out.append(gems)
    return out


def xml_items(xml: str) -> list[dict]:
    """Itens equipados no conjunto ativo: {slot, nome, base, raridade, texto}."""
    items = {}
    for m in re.finditer(r'<Item\b([^>]*)>(.*?)</Item>', xml, re.S):
        item_id = re.search(r'\bid="(\d+)"', m.group(1))
        lines = [l.strip() for l in re.sub(r"<[^>]+>", "", m.group(2)).replace("&apos;", "'").splitlines() if l.strip()]
        if not lines or not item_id:
            continue
        rarity = lines[0].split(":", 1)[-1].strip().upper() if lines[0].lower().startswith("rarity") else ""
        body = lines[1:] if rarity else lines
        name = body[0] if body else ""
        base = body[1] if rarity in ("RARE", "UNIQUE", "RELIC") and len(body) > 1 else name
        items[item_id.group(1)] = {"nome": name, "base": base, "raridade": rarity, "texto": "\n".join(lines)}
    active = re.search(r'<Items\b[^>]*activeItemSet="(\d+)"', xml)
    sets = [(re.search(r'\bid="(\d+)"', attrs), body) for attrs, body in re.findall(r'<ItemSet\b([^>]*)>(.*?)</ItemSet>', xml, re.S)]
    chosen = next((body for sid, body in sets if sid and (not active or sid.group(1) == active.group(1))),
                  sets[0][1] if sets else "")
    out = []
    for tag in re.findall(r"<Slot\b[^>]*>", chosen):
        slot, item_id = re.search(r'\bname="([^"]+)"', tag), re.search(r'\bitemId="(\d+)"', tag)
        if slot and item_id and item_id.group(1) != "0" and item_id.group(1) in items and "Socket" not in slot.group(1):
            out.append({"slot": slot.group(1), **items[item_id.group(1)]})
    return out


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.1f}".replace(",", " ")
    return str(v)


def render_md(name: str, class_name: str, ascendancy: str, stages: list[dict], notas=APROXIMACOES) -> str:
    """etapas.md: o que mudou em cada etapa e os números medidos nela."""
    lines = [f"# {name}", "", f"Classe: {class_name}" + (f" ({ascendancy})" if ascendancy else "") +
             f". Etapas: {', '.join(s['arquivo'] for s in stages)}.", ""]
    for s in stages:
        title = f"L{s['level']}" + (f" respec - {s['respec']}" if s.get("respec") else "")
        lines += [f"## {title}", "", f"Arquivo: `{s['arquivo']}`. Inimigo nível {s['config']['enemyLevel']}, "
                  f"penalidade de resistência {s['config']['resistancePenalty']}.",
                  f"Pontos: {s['pontos']['usados']} de {s['pontos']['disponiveis']} disponíveis"
                  + (f", {s['pontos']['cortados']} do plano fora do orçamento" if s['pontos'].get("cortados") else "")
                  + (f"; ascendência: {s['pontos']['ascendencia']} nós" if s['pontos'].get("ascendencia") else "") + ".", ""]
        if s.get("respec"):
            lines += [f"Motivo: {s['respec']}.", ""]
        lines += ["Gems:", ""]
        for i, group in enumerate(s["gems"], 1):
            parts = [f"{g['name']} {g['level']}" + (f"/{g['quality']}q" if g.get("quality") else "") if g["liberada"]
                     else f"~~{g['name']}~~ (" + (f"tier {g['tier']}, gema bruta acima do nível {s['level']}" if g.get("tier")
                                                 else f"nível mínimo acima de {s['level']}") + ")" for g in group]
            lines.append(f"- grupo {i}: " + ", ".join(parts))
        lines.append("")
        if s.get("nos_removidos"):
            lines += ["Nós que saem: " + ", ".join(s["nos_removidos"]) + ".", ""]
        lines += ["Nós novos: " + (", ".join(s["nos_novos"]) if s["nos_novos"] else "nenhum") + ".", ""]
        if s.get("gear"):
            lines += ["Gear:", ""] + [f"- {g['slot']}: {g['nome']}" + (f" ({g['base']})" if g['base'] != g['nome'] else "")
                                       + (f" · degrau {g['degrau']}" if g.get("degrau") else "") + (f" · {g['nota']}" if g.get("nota") else "")
                                       for g in s["gear"]] + [""]
            for g in s["gear"]:
                mods = [l for l in str(g.get("texto") or "").splitlines()[2:] if not l.startswith(("Item Level", "Implicits", "Rarity"))]
                if mods:
                    lines += [f"  - {g['slot']}: " + " / ".join(mods[:8])]
            lines.append("")
        if s.get("antes") is not None:
            keys = sorted(set(s["antes"]) | set(s["stats"]))
            lines += ["| Stat | Antes | Depois |", "|---|---|---|"]
            lines += [f"| {k} | {_fmt(s['antes'].get(k, '-'))} | {_fmt(s['stats'].get(k, '-'))} |" for k in keys]
        else:
            lines += ["| Stat | Valor |", "|---|---|"] + [f"| {k} | {_fmt(v)} |" for k, v in s["stats"].items()]
        if s.get("minion"):
            lines += ["", "Minion da skill principal (um minion): " + ", ".join(f"{k} {_fmt(v)}" for k, v in s["minion"].items())]
        if s.get("avisos"):
            lines += [""] + [f"- Aviso: {a}" for a in s["avisos"]]
        lines.append("")
    lines += ["## Aproximações", ""] + [f"- {n}" for n in notas] + [""]
    return "\n".join(lines)


def parse_gear(raw) -> dict[int, list[dict]]:
    """gear do pedido: {nível: [{slot, text, degrau?, nota?}]} -> {int: [dict]}; vazio = gear da sessão."""
    out = {}
    if not raw:
        return out
    if not isinstance(raw, dict):
        raise ValueError('gear deve ser {"15": [{"slot": "Ring 1", "text": "...", "degrau": "2"}], ...}')
    for level, rows in raw.items():
        try:
            lvl = int(level)
        except (TypeError, ValueError):
            raise ValueError(f"gear: nível inválido {level!r}")
        if not isinstance(rows, list):
            raise ValueError(f"gear[{level}] deve ser uma lista de itens")
        clean = []
        for r in rows:
            if not isinstance(r, dict) or not str(r.get("slot") or "").strip() or not str(r.get("text") or "").strip():
                raise ValueError(f"gear[{level}]: cada item precisa de slot e text")
            clean.append({"slot": str(r["slot"]).strip(), "text": str(r["text"]), "degrau": str(r.get("degrau") or ""),
                          "nota": str(r.get("nota") or "")})
        out[lvl] = clean
    return out


def parse_config(raw) -> dict[int, dict]:
    """config do pedido -> {nível: {input: valor}}. Um dicionário simples vale desde o nível 1; com chaves
    numéricas ({"1": {...}, "24": {...}}) cada bloco vale do seu nível em diante (config honesta por etapa)."""
    if not isinstance(raw, dict) or not raw:
        return {}
    if all(str(k).isdigit() for k in raw):
        out = {}
        for k, v in raw.items():
            if not isinstance(v, dict):
                raise ValueError(f"config[{k}] deve ser um dicionário de inputs")
            out[int(k)] = v
        return out
    return {1: raw}


def config_at(plan: dict[int, dict], level: int) -> dict:
    """Inputs vigentes numa etapa: todos os blocos de nível <= level, o mais recente por chave."""
    merged = {}
    for lvl in sorted(plan):
        if lvl <= level:
            merged.update(plan[lvl])
    return merged


def gear_at(plan: dict[int, list[dict]], level: int) -> list[dict]:
    """Itens vigentes numa etapa: o mais recente por slot entre os níveis <= level."""
    chosen = {}
    for lvl in sorted(plan):
        if lvl <= level:
            for r in plan[lvl]:
                chosen[r["slot"]] = r
    return list(chosen.values())


def parse_respecs(raw, known_ids) -> list[dict]:
    out = []
    for r in raw or []:
        if not isinstance(r, dict) or r.get("level") in (None, ""):
            raise ValueError('cada respec precisa de {level, remove?:[ids], add?:[ids], skills?:[...], motivo?}')
        level = int(r["level"])
        remove = [int(x) for x in r.get("remove") or []]
        add = [int(x) for x in r.get("add") or []]
        unknown = sorted(x for x in add if x not in known_ids)
        if unknown:
            raise ValueError(f"respec L{level}: nós desconhecidos em add: {unknown[:10]}")
        out.append({"level": level, "remove": remove, "add": add,
                    "skills": parse_gems(r["skills"]) if r.get("skills") else None,
                    "gear": parse_gear({level: r["gear"]}).get(level, []) if r.get("gear") else [],
                    "select": r.get("select") if isinstance(r.get("select"), dict) else None,
                    "motivo": str(r.get("motivo") or "respec").strip() or "respec"})
    return sorted(out, key=lambda r: r["level"])


def merge_loadouts(stages: list[tuple[str, str]], notes: str = "") -> str:
    """Um XML do PoB com um loadout por etapa: Spec, SkillSet, ItemSet e ConfigSet com o mesmo título.

    O PoB agrupa os conjuntos pelo título (menu Loadouts); o nível do personagem é um só por arquivo
    (fica o da última etapa) e vai anotado em Notes para o jogador ajustar ao trocar de loadout.
    """
    if not stages:
        raise ValueError("nenhuma etapa para juntar")
    root = copy.deepcopy(ET.fromstring(stages[-1][1]))
    tree, skills, items, config = root.find("Tree"), root.find("Skills"), root.find("Items"), root.find("Config")
    for parent, tags in ((tree, ("Spec",)), (skills, ("SkillSet",)), (items, ("Item", "ItemSet")), (config, ("ConfigSet",))):
        if parent is not None:
            for child in [c for c in parent if c.tag in tags]:
                parent.remove(child)
    offset = 0
    for index, (title, xml) in enumerate(stages, 1):
        stage = ET.fromstring(xml)
        ids = {}
        stage_items = stage.find("Items")
        if stage_items is not None:
            for item in stage_items.findall("Item"):
                old = int(item.get("id") or 0); ids[old] = old + offset
        spec = stage.find("Tree/Spec")
        if spec is not None and tree is not None:
            spec = copy.deepcopy(spec); spec.set("title", title)
            for el in spec.iter():  # joias ficam em Spec/Sockets com o id do item
                if "itemId" in el.attrib:
                    el.set("itemId", str(ids.get(int(el.get("itemId") or 0), 0)))
            tree.append(spec)
        skill_set = stage.find("Skills/SkillSet")
        if skill_set is not None and skills is not None:
            skill_set = copy.deepcopy(skill_set); skill_set.set("id", str(index)); skill_set.set("title", title); skills.append(skill_set)
        if stage_items is not None and items is not None:
            for item in stage_items.findall("Item"):
                old = int(item.get("id") or 0)
                item = copy.deepcopy(item); item.set("id", str(ids[old])); items.append(item)
            item_set = stage_items.find("ItemSet")
            if item_set is not None:
                item_set = copy.deepcopy(item_set); item_set.set("id", str(index)); item_set.set("title", title)
                for slot in item_set.findall("Slot"):
                    old = int(slot.get("itemId") or 0)
                    slot.set("itemId", str(ids.get(old, 0)))
                items.append(item_set)
            offset += max(ids) if ids else 0
        config_set = stage.find("Config/ConfigSet")
        if config_set is not None and config is not None:
            config_set = copy.deepcopy(config_set); config_set.set("id", str(index)); config_set.set("title", title); config.append(config_set)
    n = str(len(stages))
    if tree is not None: tree.set("activeSpec", n)
    if skills is not None: skills.set("activeSkillSet", n)
    if items is not None: items.set("activeItemSet", n)
    if config is not None: config.set("activeConfigSet", n)
    if notes:
        note = root.find("Notes")
        if note is None:
            note = ET.SubElement(root, "Notes")
        note.text = notes
    return ET.tostring(root, encoding="unicode")


def loadout_notes(name: str, stages: list[dict]) -> str:
    lines = [f"{name}: um loadout por etapa (menu Loadouts do PoB). O nível do personagem é um só por arquivo:",
             "ajuste o nível ao trocar de loadout.", ""]
    for s in stages:
        title = f"L{s['level']}" + (f" respec - {s['respec']}" if s.get("respec") else "")
        st = s.get("stats") or {}
        mn = s.get("minion") or {}
        lines.append(f"{title}: nível {s['level']}, inimigo {s['config']['enemyLevel']}, resist {s['config']['resistancePenalty']}; "
                     f"DPS {st.get('CombinedDPS', '-')}" + (f" (minion {mn.get('TotalDPS')})" if mn.get("TotalDPS") else "")
                     + f", vida {st.get('Life', '-')}, ES {st.get('EnergyShield', '-')}")
    return "\n".join(lines)


# ---------- motor ----------
def run(session: dict, params: dict, out_dir: Path, compact, pob_code) -> dict:
    """Grava `out_dir/<nome>/L<nível>.xml` (+ código do PoB) por etapa e `etapas.md`; devolve o resumo.

    A sessão volta ao estado anterior no fim.
    """
    from src.lab import judge  # import tardio: judge importa este módulo
    lab: Lab = session["lab"]
    cls, asc = session["class"], session["ascendancy"] or None
    levels = sorted({int(x) for x in (params.get("levels") or DEFAULT_LEVELS)})
    if not levels or levels[0] < 1 or levels[-1] > 100:
        raise ValueError("levels deve ter níveis entre 1 e 100")
    acts = load_acts()
    base_xml = lab.export_xml()
    groups = parse_gems(params["gems"]) if params.get("gems") else xml_gems(base_xml)
    ctx = lab.tree_context()
    by_id = {n["id"]: n for n in ctx["nodes"]}
    allocated = [n["id"] for n in ctx["nodes"] if n["allocated"]]
    # Fixos em toda etapa, fora do orçamento: início da classe e da ascendência.
    fixed = {n for n in allocated if by_id[n].get("kind") in FIXED_KINDS}
    asc_all = [n for n in allocated if by_id[n].get("ascendancy") and n not in fixed]
    asc_ordem = [n for n in session.get("ordem") or [] if n in asc_all] + sorted(n for n in asc_all if n not in (session.get("ordem") or []))
    ordem = [n for n in session.get("ordem") or [] if n in by_id and n not in fixed and n not in asc_all]
    base_nodes = sorted(n for n in allocated if n not in fixed and n not in ordem and n not in asc_all)
    respecs = parse_respecs(params.get("respecs"), by_id)
    levels = sorted(set(levels) | {r["level"] for r in respecs})
    selected = dict(session.get("selected") or {"group": 1, "part": None})
    items = xml_items(base_xml)
    gear_plan = parse_gear(params.get("gear"))
    config_plan = parse_config(params.get("config"))  # condições com produtor na build, por nível
    name = safe_name(params.get("name") or session["name"]) or "lab"
    folder = Path(out_dir) / name
    folder.mkdir(parents=True, exist_ok=True)

    def names(ids) -> list[str]:
        return [by_id[i]["name"] for i in ids if i in by_id]

    def build(level: int, motivo: str | None, previous_nodes: set, antes: dict | None) -> dict:
        avisos = []
        lab.load_xml(base_xml, session["name"])
        lab.set_level(level)
        config = {**stage_config(level, acts), **config_at(config_plan, level)}
        lab.config(config)
        budget = passive_points(level, acts)
        planned = nodes_for(base_nodes, ordem, 10 ** 6)
        nodes = nodes_for(base_nodes, ordem, budget)
        asc_nodes = asc_ordem[:judge.ascendancy_points(level)]
        lab.set_nodes(cls, set(nodes) | fixed | set(asc_nodes), asc)
        # Pontos pelo que o PoB alocou de fato: nó desconectado da raiz depois do corte também é descartado.
        real = lab.allocated()
        dropped = [n for n in nodes + asc_nodes if n not in real]
        asc_nodes = [n for n in asc_nodes if n in real]
        if dropped:
            avisos.append(f"o PoB descartou {len(dropped)} nó(s) do plano (desconectados no corte): {', '.join(names(dropped)[:8])}")
            nodes = [n for n in nodes if n in real]
        for index in range(len(xml_groups(lab.export_xml())), 0, -1):
            try:
                lab.req("remove_skill", {"groupIndex": index})
            except Exception as exc:
                msg = str(exc).lower()
                if "not found" in msg:
                    continue
                # Grupos especiais (skill concedida por item ou nó) não saem; ficam em toda etapa.
                if "special" not in msg:
                    raise
                avisos.append(f"grupo {index} concedido por item/nó: mantido nesta etapa")
        plan = gem_plan(groups, level)
        new_index = {}
        for gi, rows in enumerate(plan, 1):
            if not rows[0]["liberada"]:
                porque = (f"tier {rows[0]['tier']} pede gema bruta nível {rows[0]['tier']}" if rows[0].get("tier")
                          else "a skill exige nível acima")
                avisos.append(f"grupo {gi} ({rows[0]['name']}) fora da etapa L{level}: {porque}")
                continue
            gems = [(g["name"], g["level"]) + ((g["quality"],) if g.get("quality") else ()) for g in rows if g["liberada"]]
            new_index[gi] = lab.group(gems)
        if new_index:
            wanted = int(selected.get("group") or 1)
            group = new_index.get(wanted) or min(new_index.values())
            part = selected.get("part") if wanted in new_index else None
            if part:
                lab.select_part(group, int(part))
            else:
                lab.select(group)
        stage_items = items
        if gear_plan:
            degraus = {}
            for row in gear_at(gear_plan, level):
                try:
                    lab.equip(row["slot"], row["text"])
                    degraus[row["slot"]] = row
                except Exception as exc:
                    avisos.append(f"gear {row['slot']} não equipada: {str(exc)[:100]}")
            stage_items = [{**g, "degrau": degraus.get(g["slot"], {}).get("degrau", ""), "nota": degraus.get(g["slot"], {}).get("nota", "")}
                           for g in xml_items(lab.export_xml())]
        raw = lab.stats(FIELDS + DEFENCE_FIELDS + ["Spirit", "SpiritUnreserved"], minion=True)
        minion = compact(raw.pop("minion", None) or {}, MINION_FIELDS) if raw.get("minion") else {}
        stats = compact(raw)
        xml = lab.export_xml()
        filename = stage_filename(level, motivo)
        (folder / filename).write_text(xml, encoding="utf-8")
        (folder / filename.replace(".xml", ".codigo-pob.txt")).write_text(pob_code(xml), encoding="utf-8")
        current = set(nodes) | set(asc_nodes)
        return {"arquivo": filename, "level": level, "respec": motivo, "config": config,
                "pontos": {"disponiveis": budget, "usados": len(nodes), "cortados": max(0, len(planned) - len(nodes)),
                           "ascendencia": len(asc_nodes)},
                "gems": plan, "nos_novos": names(sorted(current - previous_nodes)),
                "nos_removidos": names(sorted(previous_nodes - current)) if motivo else [],
                "gear": stage_items, "stats": stats, "minion": minion, "antes": antes, "avisos": avisos, "_nodes": current}

    stages, previous = [], set()
    try:
        for level in levels:
            stage = build(level, None, previous, None)
            stages.append(stage)
            previous = stage["_nodes"]
            for r in (x for x in respecs if x["level"] == level):
                remove = set(r["remove"])
                ordem[:] = [n for n in ordem if n not in remove] + [n for n in r["add"] if n not in ordem]
                base_nodes[:] = [n for n in base_nodes if n not in remove]
                if r["skills"]:
                    groups = r["skills"]
                    selected = dict(r["select"] or {"group": 1, "part": None})
                elif r["select"]:
                    selected = dict(r["select"])
                if r["gear"]:
                    gear_plan.setdefault(level, []).extend(r["gear"])
                stage = build(level, r["motivo"], previous, stages[-1]["stats"])
                stages.append(stage)
                previous = stage["_nodes"]
    finally:
        lab.load_xml(base_xml, session["name"])
        session["selected_key"] = None
    for s in stages:
        s.pop("_nodes", None)
    md = render_md(session["name"], cls, session["ascendancy"], stages)
    (folder / "etapas.md").write_text(md, encoding="utf-8")
    # Um arquivo só com um loadout por etapa, para abrir e comparar dentro do PoB.
    titles = [(f"L{s['level']}" + (f" respec - {s['respec']}" if s.get("respec") else ""), (folder / s["arquivo"]).read_text(encoding="utf-8")) for s in stages]
    merged = merge_loadouts(titles, loadout_notes(session["name"], stages))
    (folder / f"{name}.loadouts.xml").write_text(merged, encoding="utf-8")
    (folder / f"{name}.loadouts.codigo-pob.txt").write_text(pob_code(merged), encoding="utf-8")
    return {"pasta": str(folder), "etapas_md": str(folder / "etapas.md"), "loadouts": str(folder / f"{name}.loadouts.xml"),
            "etapas": [{k: v for k, v in s.items() if k not in ("gear", "config")} for s in stages],
            "gear": [{"slot": g["slot"], "item": g["nome"]} for g in items], "aproximacoes": APROXIMACOES}
