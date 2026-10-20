"""Filtro de instruções dentro do documento, aplicado antes do LLM.

Conteúdo do PDF é dado, não instrução. Trechos que parecem ordens ao sistema são
retirados do texto enviado ao modelo e viram um alerta `instrucao_no_documento`.
O prompt de sistema reforça a mesma regra; o filtro é a primeira barreira.
"""

from __future__ import annotations

import re
import unicodedata

from agente.modelos import Alerta
from agente.pdf import Linha

PADROES = [
    r"\b(sistema|system|assistente|assistant|agente|modelo|ia|ai)\s*:",
    r"\bignor(e|ar|em|ando)\b.{0,40}\b(regras?|instrucoes|instrucao|anteriores|acima|tudo)",
    r"\bdesconsider(e|ar|em)\b.{0,40}\b(regras?|instrucoes|instrucao|anteriores|acima)",
    r"\bmarqu(e|ar|em)\b.{0,30}\b(todas?|todos?)\b.{0,30}\b(glosas?|itens?|recorrive)",
    r"\bnovas?\s+instruc",
    r"\bprompt\b",
    r"\bvoce\s+(agora\s+)?(e|deve|precisa)\b",
    r"\bresponda\s+(apenas|somente)\b",
    r"\bclassifique\b.{0,30}\b(todas?|todos?)\b",
    r"\baprov(e|ar|em)\b.{0,30}\b(todas?|todos?|recursos?)\b",
    r"\bignore (all|previous|the)\b",
    r"<\s*/?\s*(system|instructions?|documento)\s*>",
]
RE_INJECAO = re.compile("|".join(f"(?:{p})" for p in PADROES), re.IGNORECASE)
MARCA = "[TRECHO REMOVIDO: possível instrução dentro do documento]"


def _sem_acento(texto: str) -> str:
    """Remove acentos sem mudar o comprimento, para as posições baterem com o original."""
    return "".join(
        unicodedata.normalize("NFKD", c)[0] if unicodedata.normalize("NFKD", c) else c
        for c in texto
    )


def filtrar_instrucoes(linhas: list[Linha]) -> tuple[list[Linha], list[Alerta]]:
    """Corta do primeiro padrão suspeito até o fim da linha e registra o alerta."""
    saida: list[Linha] = []
    alertas: list[Alerta] = []
    for lin in linhas:
        m = RE_INJECAO.search(_sem_acento(lin.texto))
        if not m:
            saida.append(lin)
            continue
        trecho = lin.texto[m.start() :]
        alertas.append(
            Alerta(
                tipo="instrucao_no_documento",
                motivo="Texto no documento parece uma instrução ao sistema; foi ignorado.",
                pagina=lin.pagina,
                linha=lin.linha,
                trecho=trecho[:200],
            )
        )
        novo = (lin.texto[: m.start()].rstrip() + " " + MARCA).strip()
        saida.append(Linha(lin.pagina, lin.linha, novo))
    return saida, alertas
