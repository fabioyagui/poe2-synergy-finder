"""Laboratório de medição no PoB headless.

Tudo aqui parte do mesmo princípio: o texto do jogo gera hipóteses, o PoB confirma
em número. Os módulos:

- engine: sobe o motor, monta builds mínimas e lê stats.
- data: lê bases, mods, gems e efeitos de qualidade dos dados do PoB instalado.
- bench: dano de cada skill por nível e multiplicador de cada condição (verificação de âncoras).
- tree: busca gulosa de passivas medida no PoB.
- gear: melhor base e melhores mods por slot, medidos no PoB.
"""
from src.lab.engine import FIELDS, Lab, gem_level, normal, score, with_stat_set

__all__ = ["FIELDS", "Lab", "gem_level", "normal", "score", "with_stat_set"]
