"""Cliente de laboratório sobre o EngineClient: builds mínimas, seleção de skill e leitura de stats."""
from __future__ import annotations

import math
import re

from src import pob_engine

FIELDS = ["TotalDPS", "CombinedDPS", "AverageDamage", "AverageHit", "Speed", "HitChance", "CritChance",
          "ManaCost", "Life", "Mana", "PowerCharges", "PowerChargesMax", "RemovablePowerCharges",
          "FrenzyCharges", "RemovableFrenzyCharges", "ProjectileCount", "AreaOfEffectRadiusMetres",
          "TotalDot", "IgniteDPS", "BleedDPS", "PoisonDPS", "WithPoisonDPS", "WithBleedDPS", "WithIgniteDPS"]
DEFENCE_FIELDS = ["TotalEHP", "EnergyShield", "Evasion", "Armour", "FireResist", "ColdResist", "LightningResist", "ChaosResist"]

# Nível de gem liberado por nível de personagem (levelRequirement das gems no PoB).
_GEM_LEVEL_REQ = [0, 3, 6, 10, 14, 18, 22, 26, 31, 36, 41, 46, 52, 58, 64, 66, 72, 78, 84, 90]


def gem_level(char_level: int) -> int:
    return max(i + 1 for i, req in enumerate(_GEM_LEVEL_REQ) if req <= char_level)


def normal(base: str) -> str:
    """Texto de item branco, como o PoB o importa."""
    return f"Rarity: NORMAL\n{base}\n{base}"


def with_stat_set(xml: str, index: int, skill_id: str | None = None) -> str:
    """Força um conjunto de stats (parte da skill) na primeira gem, ou na gem de skill_id.

    O bridge não expõe essa escolha, então ela é feita no XML antes de recarregar.
    """
    # Uma escolha anterior deixa <Gem ...><StatSetIndex/>...</Gem>; volta a gem ao formato fechado antes de trocar.
    xml = re.sub(r"(<Gem\b[^>]*?)>\s*(?:<StatSet(?:Calcs)?Index\b[^>]*/>\s*)*</Gem>", r"\1/>", xml)
    pattern = r'(<Gem [^>]*skillId="' + re.escape(skill_id) + r'"[^>]*?)/>' if skill_id else r"(<Gem [^>]*?)/>"

    def add(m):
        sid = skill_id or re.search(r'skillId="([^"]+)"', m.group(1)).group(1)
        return (m.group(1) + f'><StatSetIndex grantedEffect="{sid}" index="{index}"/>'
                f'<StatSetCalcsIndex grantedEffect="{sid}" index="{index}"/></Gem>')

    out = re.sub(pattern, add, xml, count=1)
    if out == xml:
        raise ValueError("gem não encontrada no XML para fixar o conjunto de stats")
    return out


def xml_groups(xml: str) -> list[dict]:
    """Grupos de skill do XML, na ordem do PoB: [{index, gems:[nome], skill_id}]."""
    out = []
    for i, block in enumerate(re.findall(r"<Skill\b[^>]*>(.*?)</Skill>", xml, re.S), 1):
        gems = re.findall(r'<Gem\b[^>]*nameSpec="([^"]*)"', block)
        skill_id = re.search(r'<Gem\b[^>]*skillId="([^"]+)"', block)
        out.append({"index": i, "gems": gems, "skill_id": skill_id.group(1) if skill_id else None})
    return out


def score(after: dict, before: dict, weights: dict) -> float:
    """Soma ponderada de log-razões; 0 significa nenhuma mudança."""
    return sum(w * math.log(max(after.get(k) or 0, 1e-9) / max(before.get(k) or 0, 1e-9)) for k, w in weights.items())


class Lab:
    def __init__(self, engine: pob_engine.EngineClient | None = None):
        self.engine = engine or pob_engine.EngineClient()
        if not self.engine.is_running():
            self.engine.start()
        self.classes = {}
        for c in self.req("get_classes")["result"]["classes"]:
            self.classes[c["name"]] = {"id": c["classId"], "ascendancies": {a["name"]: a["id"] for a in c["ascendancies"]}}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def req(self, action: str, params: dict | None = None, timeout: int = 40) -> dict:
        return self.engine.request(action, params or {}, timeout=timeout)

    def close(self):
        self.engine.stop()

    def restart_if_dead(self):
        if not self.engine.is_running():
            self.engine.start()

    # ---------- montagem ----------
    def class_ids(self, class_name: str, ascendancy: str | None = None) -> tuple[int, int]:
        cls = self.classes[class_name]
        return cls["id"], cls["ascendancies"][ascendancy] if ascendancy else 0

    def new_build(self, class_name: str, level: int, ascendancy: str | None = None, nodes=(), weapon: str | None = None):
        class_id, asc_id = self.class_ids(class_name, ascendancy)
        self.req("new_build")
        self.req("set_tree", {"classId": class_id, "ascendClassId": asc_id, "nodes": list(nodes)})
        self.req("set_level", {"level": level})
        if weapon:
            self.equip("Weapon 1", weapon)

    def set_nodes(self, class_name: str, nodes, ascendancy: str | None = None):
        class_id, asc_id = self.class_ids(class_name, ascendancy)
        self.req("set_tree", {"classId": class_id, "ascendClassId": asc_id, "nodes": sorted(nodes)})

    def equip(self, slot: str, text: str):
        self.req("add_item_text", {"text": text, "slotName": slot})

    def group(self, gems) -> int:
        """gems: [(nome, nível)] ou [(nome, nível, qualidade)]; o primeiro é a skill ativa."""
        index = self.req("create_socket_group")["socketGroup"]["index"]
        for gem in gems:
            params = {"groupIndex": index, "gemName": gem[0], "level": gem[1]}
            if len(gem) > 2:
                params["quality"] = gem[2]
            self.req("add_gem", params)
        return index

    def config(self, values: dict):
        self.req("set_config", values)

    def select(self, group: int, active: int = 1, part: int | None = None):
        sel = {"mainSocketGroup": group, "mainActiveSkill": active}
        if part is not None:
            sel["skillPart"] = part
        self.req("set_main_selection", sel)

    def select_part(self, group: int, part: int, active: int = 1):
        """Seleciona um grupo e força a parte (conjunto de stats) da skill ativa dele.

        O bridge não expõe a parte; ela é fixada no XML e a build é recarregada.
        """
        xml = self.export_xml()
        groups = xml_groups(xml)
        if not 1 <= group <= len(groups) or not groups[group - 1]["skill_id"]:
            raise ValueError(f"grupo {group} não existe ou não tem skill")
        self.load_xml(with_stat_set(xml, part, groups[group - 1]["skill_id"]), "lab")
        self.select(group, active)

    # ---------- leitura ----------
    def stats(self, fields=None) -> dict:
        out = self.req("get_stats", {"fields": list(fields or FIELDS)})["stats"]
        out.pop("_meta", None)
        return out

    def load_xml(self, xml: str, name: str = "lab"):
        self.engine.load_xml(xml, name)

    def export_xml(self) -> str:
        return self.req("export_build_xml")["xml"]

    def tree_context(self) -> dict:
        """Nós com distância de caminho, alocação e ascendência (extensão SynergyWorkbench)."""
        return self.req("sf_workbench_visual", timeout=120)["result"]

    def plan(self, node_id: int) -> dict:
        """Caminho normal até um nó, calculado pelo PoB (extensão SynergyTree)."""
        return self.req("sf_tree_plan", {"node_id": node_id})["result"]
