"""Filtro de instruções dentro do documento, aplicado antes do LLM.

Conteúdo do PDF é dado, não instrução. Trechos que parecem ordens ao sistema são
retirados do texto enviado ao modelo e viram um alerta `instrucao_no_documento`.
O prompt de sistema reforça a mesma regra; o filtro é a primeira barreira, não a única.

O corte vai do início do trecho suspeito até o fim da frase, ou até o próximo valor em
reais da linha, para não apagar os dados de um item que esteja na mesma linha.
"""

from __future__ import annotations

import re
import unicodedata

from agente.modelos import Alerta
from agente.pdf import Linha

# Letras de outros alfabetos que imitam letras latinas (homoglifos mais comuns).
_HOMOGLIFOS = str.maketrans(
    "аеорсухіѕјԁνАЕОРСХІЅЈМТНКВ",
    "aeopcyxisjdvAEOPCXISJMTHKB",
)

# Os padrões rodam sobre o texto sem acento e em minúsculas.
PADROES = [
    # papel do interlocutor com dois-pontos ou travessão
    r"\b(sistema|system|assistente|assistant|instrucao|instrucoes|instruction|instructions)\s*[:\-—–]",
    r"\bs\s?y\s?s\s?t\s?e\s?m\s*:",
    r"\[/?inst\]|<<\s*/?sys\s*>>|#{2,}\s*(instruc|system)",
    r"<\s*/?\s*(system|instructions?|documento)\s*>",
    # ordens para ignorar regras
    r"\b(ignor\w*|desconsider\w*|esque[cç]\w*|disregard|forget|override)\b.{0,40}"
    r"\b(regras?|instruc\w*|anteriores|acima|tudo|rules|instructions|previous|above)\b",
    r"\bnovas?\s+instruc",
    r"\bnew\s+instructions?\b",
    r"\bprompt\b",
    # ordens sobre como decidir as glosas
    r"\b(marqu\w*|classifiqu\w*|consider\w*|trat\w*|defina|coloque|aprov\w*)\b.{0,40}"
    r"\b(como\s+recorr\w*|recorrive\w*|para\s+recorrer|como\s+aprovad\w*)",
    r"\b(marqu\w*|classifiqu\w*)\b.{0,15}\b(todas?|cada)\b.{0,15}\b(as\s+)?(glosas?|uma\s+das\s+glosas)\b",
    r"\b(aprov\w*)\b.{0,30}\b(todas?\s+as\s+glosas|todos\s+os\s+recursos\s+(automaticamente|sem))",
    r"\bo\s+(sistema|modelo|agente|assistente)\s+(deve|precisa|vai|tem\s+que)\b",
    r"\bnota\s+(ao|para\s+o)\s+(analisador|sistema|modelo|agente|assistente|revisor\s+automatico)\b",
    r"\bvoce\s*,?\s*(o\s+)?(modelo|agente|assistente|ia)\b",
    r"\bvoce\s+agora\s+(e|vai|deve|sera)\b",
    r"\b(you\s+are\s+now|act\s+as|from\s+now\s+on)\b",
    r"\bresponda\s+(apenas|somente|so)\s+(com|ok|sim|\"|')",
]
RE_INJECAO = re.compile("|".join(f"(?:{p})" for p in PADROES), re.IGNORECASE)
RE_FIM_TRECHO = re.compile(
    r"[.;!?](\s|$)|(?<![0-9.,])(R\$\s*)?[0-9]{1,3}(\.[0-9]{3})*,[0-9]{2}|(?<![0-9])[0-9]{8}(?![0-9])"
)
MARCA = "[TRECHO REMOVIDO: possível instrução dentro do documento]"


def normalizar(texto: str) -> str:
    """Sem acento, sem homoglifos, minúsculas, com o mesmo comprimento do original."""
    t = texto.translate(_HOMOGLIFOS)
    return "".join((unicodedata.normalize("NFKD", c)[:1] or c).lower() for c in t)


def _cortar(texto: str, inicio: int) -> tuple[str, str]:
    """Remove de `inicio` até o fim da frase ou o próximo valor; devolve (novo texto, trecho removido)."""
    m = RE_FIM_TRECHO.search(texto, inicio)
    if m and m.group(0)[:1] in ".;!?":
        fim = m.start() + 1
    elif m:
        fim = m.start()
    else:
        fim = len(texto)
    trecho = texto[inicio:fim]
    novo = (texto[:inicio].rstrip() + " " + MARCA + " " + texto[fim:].lstrip()).strip()
    return novo, trecho


def _alerta(lin: Linha, trecho: str) -> Alerta:
    return Alerta(
        tipo="instrucao_no_documento",
        motivo="Texto no documento parece uma instrução ao sistema; foi ignorado.",
        pagina=lin.pagina,
        linha=lin.linha,
        trecho=trecho.strip()[:200],
    )


def filtrar_instrucoes(linhas: list[Linha]) -> tuple[list[Linha], list[Alerta]]:
    saida = list(linhas)
    alertas: list[Alerta] = []
    # 1. instrução numa linha só (pode haver mais de uma na mesma linha)
    for i, lin in enumerate(saida):
        texto = lin.texto
        mudou = False
        for _ in range(5):
            m = RE_INJECAO.search(normalizar(texto))
            if not m:
                break
            texto, trecho = _cortar(texto, m.start())
            alertas.append(_alerta(lin, trecho))
            mudou = True
        if mudou:
            saida[i] = Linha(lin.pagina, lin.linha, texto)
    # 2. instrução quebrada entre duas linhas da mesma página ("Ignore" / "as regras anteriores")
    for i in range(len(saida) - 1):
        a, b = saida[i], saida[i + 1]
        if a.pagina != b.pagina or MARCA in a.texto or MARCA in b.texto:
            continue
        junto = a.texto + " " + b.texto
        m = RE_INJECAO.search(normalizar(junto))
        if m and m.start() < len(a.texto) and m.end() > len(a.texto) + 1:
            novo_a, trecho_a = _cortar(a.texto, m.start())
            novo_b, trecho_b = _cortar(b.texto, 0)
            saida[i] = Linha(a.pagina, a.linha, novo_a)
            saida[i + 1] = Linha(b.pagina, b.linha, novo_b)
            alertas.append(_alerta(a, trecho_a + " / " + trecho_b))
    return saida, alertas
