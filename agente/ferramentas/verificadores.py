"""Verificadores: o código fiscaliza o que o agente produziu."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agente.dinheiro import RE_MOEDA_OU_EXTENSO, dinheiro_no_texto, format_brl
from agente.ferramentas.dados_ref import tabela22, tabela38
from agente.modelos import DecisaoGlosa, ItemExtraido
from agente.pdf import DocumentoTexto
from agente.pseudonimo import dados_pessoais_restantes

# Qualquer forma de citar norma. Não há norma verificada na base, então nenhuma pode aparecer.
RE_NORMA = re.compile(
    r"\bRN\b|\bRDC\b|\bIN\s*(n\W{0,3})?\d|\bLei\b|\bLeis\b|\bRes\.\s|\bResolu[cç](ã|a)o\b|\bResolu[cç][oõ]es\b|"
    r"\bS[uú]mula\b|\bCDC\b|\bConstitui[cç][aã]o\b|\bC[oó]digo\s+(Civil|Penal|de\s+Defesa)|§|\bincisos?\b|"
    r"\bart(igo)?s?\b\.?\s*\d|\bPortaria\b|\bDecreto\b|\bCONSU\b|\bInstru[cç][aã]o\s+Normativa\b|"
    r"\bjurisprud[eê]ncia\b|\bTJ[A-Z]{2}\b|\bSTJ\b|\bSTF\b",
    re.IGNORECASE,
)
RE_CODIGO_CITADO = re.compile(
    r"(?:glosa|c[oó]d(?:igo)?\.?|motivo)\D{0,25}?(?<![0-9])([0-9]{4})(?![0-9])", re.IGNORECASE
)
# não começa colado em letra ou hífen: o token CART-43054511 pode sair só com algarismos
RE_OITO_DIGITOS = re.compile(r"(?<![0-9A-Za-z\-])[0-9]{8}(?![0-9])")
RE_VALOR_LINHA = re.compile(r"(?<![0-9.,])(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2}(?![0-9])")
RE_ROTULO_SENHA = re.compile(r"(senha|autoriza[cç][aã]o)\b[^\n0-9]{0,30}$", re.IGNORECASE)
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
    """Confere o rascunho de recurso antes de mostrá-lo ao faturista.

    `valores_permitidos` são os valores deste item e o valor contratado da operadora.
    """
    v = Verificacao()
    # 1. todo valor citado existe nos dados do item, e no formato brasileiro
    for trecho, centavos in dinheiro_no_texto(texto):
        if centavos is None:
            v.falha(f"valor '{trecho}' fora do formato brasileiro (use R$ 1.234,56)")
        elif centavos not in valores_permitidos:
            v.falha(f"valor {format_brl(centavos)} citado no texto não existe nos dados do item")
    m = RE_MOEDA_OU_EXTENSO.search(texto)
    if m:
        v.falha(f"valor por extenso ou em outra moeda ('{m.group(0)}'); use só R$ 1.234,56")
    # 2. nenhuma norma: não há norma verificada na base
    m = RE_NORMA.search(texto.replace(FUNDAMENTO, ""))
    if m:
        base = texto.replace(FUNDAMENTO, "")
        trecho = re.match(r"[^\n,;:]{0,40}", base[m.start() :]).group(0).strip()
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
    for m in RE_OITO_DIGITOS.finditer(texto):
        numero = m.group(0)
        if numero == (item.senha or "") or RE_ROTULO_SENHA.search(
            texto[max(0, m.start() - 40) : m.start()]
        ):
            continue  # senha de autorização também tem 8 dígitos
        if numero not in tabela22() and numero not in item.guia:
            v.falha(f"código de procedimento {m.group(0)} não consta na Tabela 22 oficial")
    return v


def _tem_valor(linha: str, valor: str) -> bool:
    """O valor aparece como número inteiro na linha ("35,00" não casa dentro de "135,00")."""
    alvo = valor.replace("R$", "").strip()
    return any(m.group(0) == alvo for m in RE_VALOR_LINHA.finditer(linha))


def verificar_evidencia(item: ItemExtraido, doc: DocumentoTexto) -> str | None:
    """A linha citada é mesmo a deste item? Devolve o erro ou None.

    - os valores apresentado, glosado e pago estão na linha;
    - o código do procedimento está na linha ou até 3 linhas acima;
    - o código de glosa está na linha ou logo abaixo, sem passar por outra linha de valores;
    - a guia está na linha ou até 6 linhas acima, na mesma página.
    """
    lin = doc.linha(item.pagina, item.linha)
    if lin is None:
        return f"página {item.pagina}, linha {item.linha} não existe no documento"
    faltando = [
        nome
        for nome, valor in (
            ("apresentado", item.valor_apresentado),
            ("glosado", item.valor_glosado),
            ("pago", item.valor_pago),
        )
        if not _tem_valor(lin.texto, valor)
    ]
    if faltando:
        return (
            f"a linha p{item.pagina} l{item.linha} não contém o valor {' nem '.join(faltando)} "
            f"do item da guia {item.guia}: '{lin.texto[:120]}'"
        )
    acima = doc.janela(item.pagina, max(1, item.linha - 3), depois=min(3, item.linha - 1))
    if item.codigo_procedimento not in acima:
        return f"procedimento {item.codigo_procedimento} não aparece em p{item.pagina} l{item.linha} nem logo acima"
    if item.codigo_glosa:
        achou = False
        for k in range(item.linha, item.linha + 3):
            prox = doc.linha(item.pagina, k)
            if prox is None:
                break
            if k > item.linha and RE_VALOR_LINHA.search(prox.texto):
                break  # chegou na linha de outro item
            if re.search(rf"(?<![0-9]){item.codigo_glosa}(?![0-9])", prox.texto):
                achou = True
                break
        if not achou:
            return f"código de glosa {item.codigo_glosa} não está em p{item.pagina} l{item.linha} nem logo abaixo"
    guia_perto = doc.janela(item.pagina, max(1, item.linha - 6), depois=min(6, item.linha - 1))
    if item.guia not in guia_perto:
        return (
            f"guia {item.guia} não aparece em p{item.pagina} l{item.linha} nem nas 6 linhas acima"
        )
    return None


def verificar_analise(
    decisoes: list[DecisaoGlosa],
    indices_esperados: list[int],
    ids_validos: set[str],
    citaveis: set[str] | None = None,
) -> list[str]:
    """Cada glosa recebe exatamente uma decisão, e toda fonte citada existe e veio de uma ferramenta."""
    erros = []
    vistos = [d.item for d in decisoes]
    faltam = sorted(set(indices_esperados) - set(vistos))
    sobram = sorted(set(vistos) - set(indices_esperados))
    if faltam:
        erros.append(f"faltam decisões para os itens {faltam}")
    if sobram:
        erros.append(f"decisões para itens que não são glosas analisáveis: {sobram}")
    for i in sorted({x for x in vistos if vistos.count(x) > 1}):
        erros.append(f"item {i}: mais de uma decisão para o mesmo item")
    for d in decisoes:
        for f in d.fontes:
            if f not in ids_validos:
                erros.append(f"item {d.item}: fonte '{f}' não existe na base")
            elif citaveis is not None and f not in citaveis:
                erros.append(
                    f"item {d.item}: fonte '{f}' não veio de nenhuma ferramenta nesta análise"
                )
        if not d.fontes:
            erros.append(f"item {d.item}: a justificativa precisa citar ao menos um id da base")
    return erros
