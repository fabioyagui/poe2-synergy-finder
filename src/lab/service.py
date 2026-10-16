"""Entrada HTTP/MCP do laboratório: valida parâmetros, sobe um motor próprio e devolve a medição.

Usa um EngineClient separado do motor do Finder, para não tocar na build atual do
usuário. Uma medição por vez.
"""
from __future__ import annotations

import threading

from src import pob_engine
from src.lab import bench, data
from src.lab.engine import Lab

_lock = threading.Lock()
LEVEL_MIN, LEVEL_MAX = 1, 100


def _family_of(skill: str, family: str | None) -> tuple[str, str]:
    catalog = data.skills_by_family()
    matches = {fam: name for fam, rows in catalog.items() for _tier, name in rows if name.casefold() == skill.casefold()}
    if family:
        if family not in data.FAMILY:
            raise ValueError(f"família inválida: {family}. Use uma de {', '.join(data.FAMILY)}.")
        if family not in matches:
            raise ValueError(f'"{skill}" não é uma skill ativa da família {family}.')
        return family, matches[family]
    if not matches:
        raise ValueError(f'"{skill}" não é uma skill ativa lançada do catálogo. Confira o nome com economy_lookup.')
    if len(matches) > 1:
        raise ValueError(f'"{skill}" existe em mais de uma família ({", ".join(sorted(matches))}); informe family.')
    (family, name), = matches.items()
    return family, name


def verify_anchor(args: dict) -> dict:
    skill = str(args.get("skill") or "").strip()
    if not skill:
        raise ValueError("Informe a skill.")
    level = int(args.get("level") or 14)
    if not LEVEL_MIN <= level <= LEVEL_MAX:
        raise ValueError(f"level deve ficar entre {LEVEL_MIN} e {LEVEL_MAX}.")
    family, name = _family_of(skill, args.get("family") or None)
    if not pob_engine.setup_status()["ready"]:
        raise ValueError("Motor PoB não configurado. Use Build atual → Motor PoB → Detectar.")
    with _lock:
        with Lab() as lab:
            weapon = data.weapon_for(family, level)
            rows = bench.verify_anchor(lab, family, name, level)
    specific = [r for r in rows if not r["generic"]]
    return {
        "skill": name, "family": family, "class": data.FAMILY[family][0], "level": level, "weapon": weapon,
        "conditions_tested": list(bench.CONDITIONS),
        "specific": specific, "generic": [r for r in rows if r["generic"]],
        "verdict": ("âncora confirmada: multiplicador próprio medido no PoB" if specific else
                    "nenhum multiplicador próprio medido; só os genéricos (shock, armadura quebrada) ou nada"),
        "caveats": ["arma branca, sem supports, sem árvore, inimigo normal do mesmo nível",
                    "condições que o PoB não modela não aparecem (stages, empowered, consumo de Frenzy, minions)"],
    }
