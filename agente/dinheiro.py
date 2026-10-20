"""Dinheiro sempre em centavos (int). Nunca float.

`parse_brl` é a única porta de entrada de valores em reais vindos de texto.
"""

from __future__ import annotations

import re

# [0-9] e não \d: \d aceitaria dígitos Unicode como "１２３" ou "٣".
_RE_BRL = re.compile(
    r"^(-)?\s*(?:R\$\s*)?(-)?\s*([0-9]{1,3}(?:\.[0-9]{3})*|[0-9]+)(?:,([0-9]{1,2}))?$"
)


class ValorInvalido(ValueError):
    """Texto que não é um valor em reais no formato brasileiro."""


def parse_brl(texto: str) -> int:
    """Converte "R$ 1.234,56", "1234,56", "-15,00" ou "135" em centavos.

    Aceita só o formato brasileiro: ponto como separador de milhar e vírgula
    decimal. "1,234.56" e "12.5" são recusados de propósito, para não trocar
    vírgula por ponto em silêncio. Um único sinal de menos, no máximo.
    """
    if not isinstance(texto, str):
        raise ValorInvalido(f"esperado texto, recebido {type(texto).__name__}")
    s = texto.strip().replace(" ", " ")
    m = _RE_BRL.match(s)
    if not m or (m.group(1) and m.group(2)):
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


# Valor no formato brasileiro completo, sem começar no meio de outro número ("1500,00" não vira "500,00").
RE_VALOR_NO_TEXTO = re.compile(
    r"(?<![0-9.,])(?:R\$\s*)?-?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2}(?![0-9])"
)
# Qualquer coisa que pareça dinheiro, em qualquer formato, para o verificador conferir.
RE_DINHEIRO_AMPLO = re.compile(
    r"R\$\s*-?[0-9][0-9.,]*|(?<![0-9.,/])-?[0-9][0-9.]*,[0-9]+(?![0-9/])|(?<![0-9.,/])[0-9]+\.[0-9]{2}(?![0-9.,/])"
)
RE_MOEDA_OU_EXTENSO = re.compile(
    r"\b(reais|real|centavos?|d[oó]lar(es)?|USD|US\$|EUR|euros?)\b", re.IGNORECASE
)


def valores_no_texto(texto: str) -> list[int]:
    """Todos os valores no formato 1.234,56 (com ou sem R$) que aparecem no texto."""
    return [parse_brl(m.group(0)) for m in RE_VALOR_NO_TEXTO.finditer(texto)]


def dinheiro_no_texto(texto: str) -> list[tuple[str, int | None]]:
    """Cada menção que parece dinheiro: (trecho, centavos) ou (trecho, None) se o formato não for o brasileiro."""
    out = []
    for m in RE_DINHEIRO_AMPLO.finditer(texto):
        trecho = m.group(0).rstrip(".,")
        try:
            out.append((trecho, parse_brl(trecho)))
        except ValorInvalido:
            out.append((trecho, None))
    return out
