"""Verificadores: o código fiscaliza o que o agente produziu."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agente.dinheiro import format_brl, valores_no_texto
from agente.ferramentas.dados_ref import tabela38
from agente.modelos import DecisaoGlosa, ItemExtraido
from agente.pdf import DocumentoTexto
from agente.pseudonimo import dados_pessoais_restantes

RE_NORMA = re.compile(
    r"\bRN\s*(n[ºo°.]?\s*)?\d|\bResolu[cç][aã]o\s+(Normativa|CONSU|RDC)|\bLei\s+(n[ºo°.]?\s*)?\d|"
    r"\bLei\s+Federal|\bart(igo)?\.?\s*\d+|\bInstru[cç][aã]o\s+Normativa|\bPortaria\s+(n[ºo°.]?\s*)?\d|"
    r"\bS[uú]mula\s+\d|\bCONSU\b|\bDecreto\s+(n[ºo°.]?\s*)?\d|\bC[oó]digo\s+de\s+Defesa",
    re.IGNORECASE,
)
RE_CODIGO_CITADO = re.compile(
    r"(?:glosa|c[oó]digo|motivo)\s*(?:n[ºo°.]?\s*)?(\d{4})\b", re.IGNORECASE
)
FUNDAMENTO = "[FUNDAMENTO A CONFIRMAR]"


@dataclass
class Verificacao:
    ok: bool = True
    erros: list[str] = field(default_factory=list)

    def falha(self, msg: str) -> None:
        self.ok = False
        self.erros.append(msg)


def verificar_recurso(
    texto: str,
    item: ItemExtraido,
    valores_permitidos: set[int],
    nomes: set[str] | None = None,
) -> Verificacao:
    """Confere o rascunho de recurso antes de mostrá-lo ao faturista."""
    v = Verificacao()
    # 1. todo valor citado existe nos dados extraídos (ou nos parâmetros da operadora)
    for c in valores_no_texto(texto):
        if c not in valores_permitidos:
            v.falha(f"valor {format_brl(c)} citado no texto não existe nos dados extraídos")
    # 2. nenhuma norma fora da base: não há norma verificada, então nenhuma pode ser citada
    m = RE_NORMA.search(texto)
    if m:
        trecho = re.match(r"[^\n,;:]{0,40}", texto[m.start() :]).group(0).strip()
        v.falha(f"citação normativa '{trecho}' não verificada; remova e use {FUNDAMENTO}")
    if FUNDAMENTO not in texto:
        v.falha(f"falta o marcador {FUNDAMENTO} no lugar do fundamento normativo")
    # 3. campos a preencher pelo faturista
    if not re.search(r"protocolo[^\n]{0,60}\[A PREENCHER", texto, re.IGNORECASE):
        v.falha("falta 'Protocolo ... [A PREENCHER]' para o número do protocolo")
    if not re.search(
        r"assinatura[^\n]{0,60}\[A PREENCHER|\[A PREENCHER[^\]\n]{0,40}assinatura",
        texto,
        re.IGNORECASE,
    ):
        v.falha("falta o campo de assinatura com [A PREENCHER]")
    # 4. nenhum dado pessoal em claro
    for achado in dados_pessoais_restantes(texto, nomes):
        v.falha(f"dado pessoal em claro no texto: {achado}")
    # 5. identificação do item e códigos
    if item.guia not in texto:
        v.falha(f"o recurso precisa citar a guia {item.guia}")
    if item.codigo_procedimento not in texto:
        v.falha(f"o recurso precisa citar o procedimento {item.codigo_procedimento}")
    if item.codigo_glosa and item.codigo_glosa not in texto:
        v.falha(f"o recurso precisa citar o código de glosa {item.codigo_glosa}")
    for m in RE_CODIGO_CITADO.finditer(texto):
        cod = m.group(1)
        if cod not in tabela38() and cod != item.codigo_glosa:
            v.falha(f"código {cod} citado não consta na Tabela 38 oficial")
    return v


def verificar_evidencia(item: ItemExtraido, doc: DocumentoTexto) -> str | None:
    """A linha citada contém os valores do item? Devolve o erro ou None."""
    lin = doc.linha(item.pagina, item.linha)
    if lin is None:
        return f"página {item.pagina}, linha {item.linha} não existe no documento"
    faltando = [
        nome
        for nome, valor in (
            ("apresentado", item.valor_apresentado),
            ("glosado", item.valor_glosado),
        )
        if _so_valor(valor) not in lin.texto
    ]
    if faltando:
        return (
            f"a linha p{item.pagina} l{item.linha} não contém o valor {' e '.join(faltando)} "
            f"do item da guia {item.guia}: '{lin.texto[:120]}'"
        )
    perto = doc.janela(item.pagina, max(1, item.linha - 3), depois=3)
    if item.codigo_procedimento not in perto:
        return f"procedimento {item.codigo_procedimento} não aparece perto de p{item.pagina} l{item.linha}"
    if item.guia not in doc.janela(item.pagina, max(1, item.linha - 4), depois=4) and not any(
        item.guia in x.texto for x in doc.pagina(item.pagina)
    ):
        return f"guia {item.guia} não aparece na página {item.pagina}"
    return None


def _so_valor(v: str) -> str:
    return v.replace("R$", "").strip()


def verificar_analise(
    decisoes: list[DecisaoGlosa], indices_esperados: list[int], ids_validos: set[str]
) -> list[str]:
    """Cada glosa recebe exatamente uma decisão, e toda fonte citada existe na base."""
    erros = []
    vistos = [d.item for d in decisoes]
    faltam = sorted(set(indices_esperados) - set(vistos))
    sobram = sorted(set(vistos) - set(indices_esperados))
    if faltam:
        erros.append(f"faltam decisões para os itens {faltam}")
    if sobram:
        erros.append(f"decisões para itens que não são glosas analisáveis: {sobram}")
    if len(vistos) != len(set(vistos)):
        erros.append("há item com mais de uma decisão")
    for d in decisoes:
        for f in d.fontes:
            if f not in ids_validos:
                erros.append(f"item {d.item}: fonte '{f}' não existe na base")
        if not d.fontes:
            erros.append(f"item {d.item}: a justificativa precisa citar ao menos um id da base")
    return erros
