"""Dinheiro sempre em centavos (int). Nunca float.

`parse_brl` é a única porta de entrada de valores em reais vindos de texto.
"""

from __future__ import annotations

import re

_RE_BRL = re.compile(r"^(-)?\s*(?:R\$\s*)?(-)?\s*(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?$")


class ValorInvalido(ValueError):
    """Texto que não é um valor em reais no formato brasileiro."""


def parse_brl(texto: str) -> int:
    """Converte "R$ 1.234,56", "1234,56", "-15,00" ou "135" em centavos.

    Aceita só o formato brasileiro: ponto como separador de milhar e vírgula
    decimal. "1,234.56" e "12.5" são recusados de propósito, para não trocar
    vírgula por ponto em silêncio.
    """
    if not isinstance(texto, str):
        raise ValorInvalido(f"esperado texto, recebido {type(texto).__name__}")
    s = texto.strip().replace(" ", " ")
    m = _RE_BRL.match(s)
    if not m:
        raise ValorInvalido(f"valor em reais inválido: {texto!r}")
    negativo = bool(m.group(1) or m.group(2))
    inteiros = int(m.group(3).replace(".", ""))
    dec = m.group(4) or "0"
    centavos = inteiros * 100 + int(dec.ljust(2, "0"))
    return -centavos if negativo else centavos


def format_brl(centavos: int, simbolo: bool = True) -> str:
    """Formata centavos como "R$ 1.234,56"."""
    if not isinstance(centavos, int) or isinstance(centavos, bool):
        raise TypeError("centavos deve ser int")
    sinal = "-" if centavos < 0 else ""
    c = abs(centavos)
    inteiros = f"{c // 100:,}".replace(",", ".")
    texto = f"{sinal}{inteiros},{c % 100:02d}"
    return f"R$ {texto}" if simbolo else texto


RE_VALOR_NO_TEXTO = re.compile(r"(?:R\$\s*)?-?\d{1,3}(?:\.\d{3})*,\d{2}\b")


def valores_no_texto(texto: str) -> list[int]:
    """Todos os valores no formato 1.234,56 (com ou sem R$) que aparecem no texto."""
    return [parse_brl(m.group(0)) for m in RE_VALOR_NO_TEXTO.finditer(texto)]
