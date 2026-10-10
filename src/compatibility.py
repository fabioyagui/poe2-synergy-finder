"""Type rules, not a full in-game socket validator.

Postfix reduction follows PoB CalcTools.doesTypeExpressionMatch:
OR remaining stack entries after processing the explicit AND/OR/NOT operators.
Missing/malformed information returns None, never an automatic approval.
"""
from __future__ import annotations
import re
OPS = {'AND', 'OR', 'NOT'}

def token(value):
    if not isinstance(value, str) or not value.strip() or value.strip().isdigit():
        raise ValueError('Tipo vazio, numérico ou desconhecido.')
    result = re.sub(r'[^A-Z0-9]', '', value.upper())
    if not result: raise ValueError('Tipo sem identificador.')
    return result

def evaluate(expression, types: set[str], empty=False) -> bool | None:
    if not isinstance(expression, list):
        return None
    if not expression:
        return empty
    stack = []
    try:
        types = {token(x) for x in types}
        for raw in expression:
            t = token(raw)
            if t == 'NOT':
                if not stack: return None
                stack[-1] = not stack[-1]
            elif t in {'AND', 'OR'}:
                if len(stack) < 2: return None
                b, a = stack.pop(), stack.pop()
                stack.append(a and b if t == 'AND' else a or b)
            else:
                stack.append(t in types)
        return any(stack)
    except (ValueError, TypeError):
        return None

def check(types, allowed, excluded) -> dict:
    if not types:
        return {'status': 'unknown', 'reason': 'Tipos da skill não disponíveis.'}
    allow = evaluate(allowed, types, empty=True)
    exclude = evaluate(excluded, types, empty=False)
    if allow is None or exclude is None:
        return {'status': 'unknown', 'reason': 'Expressão de compatibilidade ausente ou inválida.'}
    if not allow:
        return {'status': 'incompatible', 'reason': 'A skill não satisfaz a expressão de tipos exigida pelo support.'}
    if exclude:
        return {'status': 'incompatible', 'reason': 'Uma exclusão do support é ativada pelos tipos presentes neste conjunto.'}
    return {'status': 'type_match', 'reason': 'Passou nas regras de tipo conhecidas. Atributos, sockets e todas as exceções do jogo não são simulados.'}

def expression_signature(expr):
    if not isinstance(expr, list): return None
    try:
        ts = [token(x) for x in expr]
    except ValueError:
        return None
    return tuple(ts) if any(x in OPS for x in ts) else tuple(sorted(set(ts)))
