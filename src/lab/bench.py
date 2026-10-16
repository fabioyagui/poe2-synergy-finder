"""Benchmark de skills e verificação de âncoras no PoB.

- skill_parts: dano de uma skill em cada parte (conjunto de stats), numa build mínima.
- benchmark: todas as skills disponíveis num nível, por família.
- verify_conditions: quanto o dano sobe com cargas ou com cada estado do inimigo.
  É o que transforma uma âncora lida no texto em multiplicador medido.
"""
from __future__ import annotations

from src.lab import data
from src.lab.engine import FIELDS, Lab, gem_level, normal, with_stat_set

# condição -> config do PoB. A lista cresce conforme o PoB expõe mais condições.
CONDITIONS = {
    "cargas (3 de cada)": {"usePowerCharges": True, "useFrenzyCharges": True, "useEnduranceCharges": True},
    "congelado": {"conditionEnemyFrozen": True},
    "com shock": {"conditionEnemyShocked": True},
    "em chamas": {"conditionEnemyIgnited": True},
    "heavy stun": {"conditionEnemyHeavyStunned": True},
    "armadura quebrada": {"conditionEnemyArmourBroken": True},
    "com chill": {"conditionEnemyChilled": True},
    "envenenado": {"conditionEnemyPoisoned": True},
    "sangrando": {"conditionEnemyBleeding": True},
    "preso (pin)": {"conditionEnemyPinned": True},
    "atordoado (daze)": {"conditionEnemyDazed": True},
    "imobilizado": {"conditionEnemyImmobilised": True},
    "vida cheia": {"conditionEnemyFullLife": True},
    "vida baixa": {"conditionEnemyLowLife": True},
}
# Multiplicadores que quase toda skill recebe; não distinguem uma âncora.
GENERIC_CONDITIONS = {"com shock", "armadura quebrada", "preso (pin)"}


def _all_off(conditions=CONDITIONS) -> dict:
    return {k: False for cfg in conditions.values() for k in cfg}


def enemy_config(level: int, **extra) -> dict:
    """Inimigo normal do nível do personagem, sem penalidade de resistência da campanha."""
    return {"enemyIsBoss": "None", "enemyLevel": level, "resistancePenalty": 0, **extra}


def minimal_build(lab: Lab, class_name: str, level: int, weapon: str | None, skill: str, glevel: int | None = None,
                  quality: int = 0, ascendancy: str | None = None, nodes=()) -> tuple[int, str]:
    """Build de uma skill só, arma branca; devolve o índice do grupo e o XML exportado."""
    lab.new_build(class_name, level, ascendancy=ascendancy, nodes=nodes, weapon=normal(weapon) if weapon else None)
    group = lab.group([(skill, glevel or gem_level(level), quality)])
    lab.select(group)
    return group, lab.export_xml()


def skill_parts(lab: Lab, xml: str, config: dict, fields=None, max_parts: int = 4) -> list[dict]:
    """Stats de cada parte da skill da primeira gem do XML; para quando as partes repetem ou acabam."""
    rows, last = [], None
    for idx in range(1, max_parts + 1):
        try:
            lab.load_xml(with_stat_set(xml, idx), "lab")
            lab.config(config)
            s = lab.stats(fields)
        except Exception:
            if rows:
                break  # a skill não tem mais partes
            raise
        key = (round(s.get("AverageDamage") or 0, 2), round(s.get("TotalDPS") or 0, 2), s.get("ProjectileCount"))
        if key == last:
            break
        last = key
        rows.append(s)
    return rows


def benchmark(lab: Lab, levels, families=None, modes=None, progress=print) -> list[dict]:
    """Dano de toda skill disponível em cada nível, por família, com arma branca e sem supports."""
    families = families or list(data.FAMILY)
    modes = modes or {"sem cargas": {}, "3 cargas": CONDITIONS["cargas (3 de cada)"]}
    catalog = data.skills_by_family()
    results = []
    for level in levels:
        glevel = gem_level(level)
        for fam in families:
            cls = data.FAMILY[fam][0]
            weapon = data.weapon_for(fam, level)
            for tier, skill in catalog.get(fam, []):
                if tier > glevel:
                    continue
                for label, extra in modes.items():
                    try:
                        _group, xml = minimal_build(lab, cls, level, weapon, skill, glevel)
                        rows = skill_parts(lab, xml, enemy_config(level, **_all_off(), **extra))
                    except Exception as exc:
                        results.append({"level": level, "family": fam, "skill": skill, "tier": tier, "mode": label, "error": str(exc)[:120]})
                        lab.restart_if_dead()
                        continue
                    for part, s in enumerate(rows, 1):
                        results.append({"level": level, "family": fam, "class": cls, "weapon": weapon, "skill": skill, "tier": tier,
                                        "mode": label, "part": part, "avg": round(s.get("AverageDamage") or 0, 1),
                                        "dps": round(s.get("TotalDPS") or 0, 1), "speed": round(s.get("Speed") or 0, 2),
                                        "proj": s.get("ProjectileCount"), "mana": s.get("ManaCost")})
            if progress:
                progress(f"{level} {fam} ok {len(results)}")
    return results


def verify_conditions(lab: Lab, xml: str, level: int, conditions=None, threshold: float = 1.03, max_parts: int = 3) -> list[dict]:
    """Para cada parte da skill e cada condição, o multiplicador de dano por acerto medido no PoB.

    Só devolve o que subiu acima do limiar. Serve para confirmar (ou derrubar) uma
    âncora apontada pelo mapa de economia.
    """
    conditions = conditions or CONDITIONS
    off = _all_off(conditions)
    out, last = [], None
    for idx in range(1, max_parts + 1):
        try:
            lab.load_xml(with_stat_set(xml, idx), "lab")
            lab.config(enemy_config(level, **off))
            base = lab.stats()
        except Exception:
            break
        b_avg, b_dps = base.get("AverageDamage") or 0, base.get("TotalDPS") or 0
        if b_avg <= 0:
            continue
        if (round(b_avg, 2), round(b_dps, 2)) == last:
            break
        last = (round(b_avg, 2), round(b_dps, 2))
        for name, cfg in conditions.items():
            try:
                lab.config({**off, **cfg})
                s = lab.stats()
            except Exception:
                continue
            avg = s.get("AverageDamage") or 0
            if avg > b_avg * threshold:
                out.append({"part": idx, "cond": name, "generic": name in GENERIC_CONDITIONS, "base": round(b_avg, 1),
                            "com": round(avg, 1), "mult": round(avg / b_avg, 2), "proj": s.get("ProjectileCount"),
                            "dps": [round(b_dps, 1), round(s.get("TotalDPS") or 0, 1)]})
    return out


def verify_anchor(lab: Lab, family: str, skill: str, level: int, **kw) -> list[dict]:
    """Atalho: build mínima da família + verify_conditions."""
    cls = data.FAMILY[family][0]
    _group, xml = minimal_build(lab, cls, level, data.weapon_for(family, level), skill)
    return verify_conditions(lab, xml, level, **kw)
