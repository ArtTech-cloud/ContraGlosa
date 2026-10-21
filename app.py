"""Agente de Glosas — interface da demo (Streamlit).

    streamlit run app.py

Com o modo demo ligado, as respostas do modelo vêm do cache em cache/ e a demo roda sem internet.

Cada tela responde, nesta ordem, às quatro perguntas da faturista (docs/PLANO-FRONT.md):
quanto está em jogo, por que foi glosado e qual a prova, até quando posso recorrer, o que eu faço agora.

Páginas:
- Início (F1 a F6): enviar o PDF ou ver um exemplo, a trilha ao vivo com o resultado de cada etapa, o
  número-herói, as glosas por prioridade com a prova e, no fim, os recursos prontos;
- Prazos (F7): a agenda de tudo o que foi analisado na sessão;
- Pendências (F8): o que foi para revisão humana, com o motivo e o que fazer;
- Como funciona: o fluxo e o contrato de cada etapa (docs/fluxo.md);
- Qualidade (F8): avaliacao/RESULTADO.md, VALIDACAO.md e EXPERIENCIA.md.

Visual: tema em .streamlit/config.toml e CSS em static/estilo.css (D37, D38). Todo texto que vem do
documento ou do modelo e entra em HTML passa por html.escape: conteúdo de PDF é dado, não marcação.
Os números vêm sempre do código (agente/consolidar.py), nunca do texto do modelo.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from agente.consolidar import (
    agenda,
    campos_a_preencher,
    glosas_priorizadas,
    painel_geral,
    semaforo,
)
from agente.dinheiro import format_brl
from agente.ferramentas.base import trechos
from agente.llm import MODELO_PADRAO, ClienteAnthropic
from agente.modelos import PassoTrilha, Resultado, parse_data
from agente.orquestrador import Orquestrador
from agente.pdf import PDFInvalido, extrair_texto
from agente.pseudonimo import pseudonimizar

NOME_PRODUTO = "Agente de Glosas"  # provisório: o nome do produto ainda está em decisão
FRASE_CHEGADA = (
    "Envie o demonstrativo de retorno. Em menos de um minuto você sabe quanto foi glosado, o que vale "
    "recorrer e até quando."
)
SELO = "Dados fictícios · nome, CPF e carteira passam pela pseudonimização antes de qualquer envio à IA"

RAIZ = Path(__file__).resolve().parent
EXEMPLOS = RAIZ / "dados" / "exemplos"
VALIDACAO = RAIZ / "dados" / "validacao"
EXEMPLO_INICIAL = "boreal_01.pdf"  # o primeiro da demo no pitch
PAUSA_APRESENTACAO = 0.6  # segundos entre os passos da trilha no modo demo, para a banca acompanhar

ROTULO_DECISAO = {
    "recorrer": "Recorrer",
    "nao_recorrer": "Não recorrer",
    "revisao_humana": "Revisão humana",
}
COR_DECISAO = {"recorrer": "green", "nao_recorrer": "gray", "revisao_humana": "orange"}
ROTULO_CONFIANCA = {"alta": "alta", "media": "média", "baixa": "baixa"}
# Semáforo: sempre ícone e texto juntos, nunca só a cor.
SEMAFORO = {
    "pronto": ("🟢", "Pronto"),
    "confira": ("🟡", "Confira"),
    "revisao": ("⚪", "Revisão humana"),
}
ICONE_STATUS = {
    "ok": ":green[:material/check_circle:]",
    "retry": ":orange[:material/replay:]",
    "fallback": ":orange[:material/warning:]",
    "erro": ":red[:material/error:]",
    "info": ":blue[:material/info:]",
}
NOME_ETAPA = {
    "leitura": "Leitura do PDF, pseudonimização e filtro de instruções",
    "triagem": "Etapa 1 · Triagem",
    "extracao": "Etapa 2 · Extração",
    "conferir_soma": "Verificador · conferir_soma",
    "consultar_t38": "Verificador · consultar_t38",
    "analise": "Etapa 3 · Análise",
    "redacao": "Etapa 4 · Redação",
    "verificar_recurso": "Verificador · verificar_recurso",
    "fluxo": "Fluxo",
}
# A trilha que a faturista vê: o nome de cada passo e as etapas do orquestrador que entram nele.
ETAPAS = [
    ("Lendo o documento", ("leitura", "triagem")),
    ("Extraindo itens", ("extracao",)),
    ("Conferindo a soma", ("conferir_soma",)),
    ("Consultando a Tabela 38 oficial", ("consultar_t38",)),
    ("Analisando cada glosa", ("analise",)),
    ("Redigindo os recursos", ("redacao", "verificar_recurso")),
]
GRUPO_DA_ETAPA = {e: i for i, (_, etapas) in enumerate(ETAPAS) for e in etapas}
SIMBOLO_PASSO = {
    "pendente": "○",
    "rodando": "◐",
    "ok": "✓",
    "alerta": "!",
    "erro": "✕",
    "pulado": "–",
}
CASO_ADVERSO = {
    "soma_divergente": "o total impresso não fecha com a soma das linhas",
    "codigo_inexistente": "código de glosa que não existe na Tabela 38",
    "injecao": "instrução escondida no campo de observações",
    "pagina_sem_texto": "uma página só com imagem, sem texto",
}
CASO_CURTO = {
    "soma_divergente": "soma não fecha",
    "codigo_inexistente": "código inexistente",
    "injecao": "instrução escondida",
    "pagina_sem_texto": "página sem texto",
}
# Para as pendências: o que cada uma quer dizer e o que a faturista faz.
PENDENCIA = {
    "soma_divergente": ("Soma divergente", "Confira os totais com a operadora antes de recorrer."),
    "totais_ausentes": ("Totais ausentes", "Confira se o demonstrativo veio completo."),
    "codigo_inexistente": (
        "Código fora da Tabela 38",
        "O agente não adivinha o significado. Peça à operadora a descrição do código.",
    ),
    "pagina_ilegivel": ("Página sem texto", "Leia a página à mão: o projeto não tem OCR."),
    "documento_sem_texto": (
        "Documento sem texto",
        "Leia o documento à mão: o projeto não tem OCR.",
    ),
    "documento_nao_reconhecido": (
        "Documento não reconhecido",
        "Confira se o arquivo é mesmo um demonstrativo de retorno.",
    ),
    "validacao_falhou": ("Saída inválida do modelo", "Analise as glosas deste documento à mão."),
    "evidencia_nao_confere": (
        "Evidência não confere",
        "A linha citada não tem o valor extraído. Confira no PDF.",
    ),
    "confianca_baixa": ("Confiança baixa", "Decida a glosa com a justificativa do agente."),
    "recurso_recusado": (
        "Recurso retido pelo verificador",
        "O rascunho citou algo que não confere. Redija ou ajuste à mão.",
    ),
    "sem_cache": ("Fora do cache da demo", "Desligue o modo demo e use a chave da API."),
    "erro_api": ("Erro na API", "Tente de novo ou ligue o modo demo."),
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# Ícones de traço simples, desenhados para este projeto (24x24, cor do texto).
_ICONES = {
    "doc": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h4"/>',
    "calendario": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    "relogio": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "moeda": '<circle cx="12" cy="12" r="9"/><path d="M14.5 9.2c-.5-.8-1.4-1.2-2.5-1.2-1.4 0-2.5.8-2.5 2s1.1 1.7 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1.1 0-2-.4-2.5-1.2M12 6.5V8M12 16v1.5"/>',
    "glosa": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M9.5 12.5l5 5M14.5 12.5l-5 5"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "pessoa": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4.5-6 8-6s7 2 8 6"/>',
    "escudo": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "alerta": '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17v.01"/>',
    "pulso": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "cadeado": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
}


def _svg(nome: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{_ICONES[nome]}</svg>'
    )


def _html(conteudo: str, lugar=None) -> None:
    (lugar or st).markdown(conteudo, unsafe_allow_html=True)


st.set_page_config(page_title=NOME_PRODUTO, page_icon="🩺", layout="wide")
# Sem linhas em branco: para o Markdown, uma linha em branco encerra o bloco <style>.
_CSS = re.sub(
    r"/\*.*?\*/|\s*\n\s*", " ", (RAIZ / "static" / "estilo.css").read_text("utf-8"), flags=re.S
)
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# ================================================================= dados e utilidades
@st.cache_data
def _trechos() -> dict[str, dict]:
    return {t.id: {"fonte": t.fonte, "texto": t.texto} for t in trechos()}


@st.cache_data
def _classificacao() -> dict[str, dict]:
    dados = yaml.safe_load((RAIZ / "base" / "classificacao_demo.yaml").read_text(encoding="utf-8"))
    return {c["codigo"]: c for c in dados["codigos"]}


@st.cache_data
def _catalogo() -> dict[str, dict]:
    """Os PDFs de exemplo, com operadora, layout e caso adverso lidos do cabeçalho do gabarito."""
    cat: dict[str, dict] = {}
    for pasta, conjunto in ((EXEMPLOS, "desenvolvimento"), (VALIDACAO, "validacao")):
        for pdf in sorted(pasta.glob("*.pdf")):
            gab = pasta / "gabarito" / f"{pdf.stem}.json"
            meta = json.loads(gab.read_text(encoding="utf-8")) if gab.exists() else {}
            cat[pdf.name] = {
                "caminho": str(pdf),
                "conjunto": conjunto,
                "operadora": meta.get("operadora", ""),
                "layout": meta.get("layout", ""),
                "adverso": meta.get("adverso"),
            }
    return cat


def _descricao(nome: str) -> str:
    m = _catalogo().get(nome, {})
    partes = [m.get("operadora", ""), f"layout {m['layout']}" if m.get("layout") else ""]
    if m.get("adverso"):
        partes.append("caso adverso: " + CASO_ADVERSO.get(m["adverso"], m["adverso"]))
    if m.get("conjunto") == "validacao":
        partes.append("nunca visto no ajuste")
    return " · ".join(p for p in partes if p)


def _rotulo_exemplo(nome: str) -> str:
    m = _catalogo()[nome]
    extra = CASO_CURTO.get(m["adverso"], "") if m["adverso"] else ""
    if m["conjunto"] == "validacao":
        extra = "nunca visto" + (f", {extra}" if extra else "")
    return f"{Path(nome).stem} — {m['operadora']}" + (f" ({extra})" if extra else "")


def _brl(c: int) -> str:
    return format_brl(int(c))


def _linhas_pseudonimizadas(dados: bytes, nome: str) -> dict[tuple[int, int], str]:
    try:
        doc = extrair_texto(dados, nome=nome)
    except PDFInvalido:
        return {}
    return {(lin.pagina, lin.linha): lin.texto for lin in pseudonimizar(doc.linhas).linhas}


def _onde(pagina: int | None, linha: int | None) -> str:
    if pagina and linha:
        return f"página {pagina}, linha {linha}"
    return f"página {pagina}" if pagina else "documento inteiro"


def _motivo_simples(descricao: str | None) -> str:
    """A descrição oficial da Tabela 38, que vem em maiúsculas, em caixa de frase (siglas mantidas)."""
    if not descricao:
        return "Código fora da Tabela 38 oficial"
    return re.sub(
        r"\b(cid|opme|tuss|tiss|ans|cpf|cns|crm|sadt)\b",
        lambda m: m.group(0).upper(),
        descricao.capitalize(),
    )


def _texto_passo(p: PassoTrilha) -> str:
    """O passo como o orquestrador registrou: ferramentas, tokens, latência. Só no detalhe técnico."""
    ic = ICONE_STATUS.get(p.status, "•")
    nome = NOME_ETAPA.get(p.etapa, p.etapa)
    extra = []
    if p.versao_prompt:
        extra.append(f"prompt {p.versao_prompt}")
    if p.tokens_entrada or p.tokens_saida:
        extra.append(f"{p.tokens_entrada:,} → {p.tokens_saida:,} tokens".replace(",", "."))
    if p.latencia_ms:
        extra.append(f"{p.latencia_ms / 1000:.1f} s")
    if p.do_cache:
        extra.append("do cache")
    cab = f"{ic} **{nome}**" + (f" — :gray[{' · '.join(extra)}]" if extra else "")
    linhas = [cab]
    if p.detalhe:
        linhas.append(f"   {p.detalhe}")
    for f in p.ferramentas:
        marca = "" if f.aprovado is None else (" ✅" if f.aprovado else " ❌")
        args = ", ".join(f"{k}={v}" for k, v in f.argumentos.items())
        linhas.append(f"   ↳ `{f.nome}({args})`{marca} {f.resultado[:140]}")
    return "\n\n".join(linhas)


def _tiles(itens: list[tuple], destaque: int | None = None) -> str:
    """Blocos de número: (ícone, rótulo, valor[, classe extra]). Rótulo e valor já vêm escapados."""
    blocos = []
    for i, (ic, rot, val, *classe) in enumerate(itens):
        classes = " ".join(["tile", "destaque-tile" if i == destaque else "", *classe]).strip()
        blocos.append(
            f'<div class="{classes}"><span class="tile-ic">{_svg(ic)}</span>'
            f"<small>{rot}</small><b>{val}</b></div>"
        )
    return '<div class="tiles">' + "".join(blocos) + "</div>"


def _secao(titulo: str, lado: str = "") -> None:
    _html(f'<div class="secao"><h3>{titulo}</h3><span>{lado}</span></div>')


# ================================================================= estado da sessão
def _modo_demo() -> bool:
    return st.session_state.get("modo_demo", True)


def _analisados() -> list[Resultado]:
    """Tudo o que foi analisado nesta sessão, na ordem em que foi analisado."""
    return list(st.session_state.get("analisados", {}).values())


def _registrar(res: Resultado) -> None:
    st.session_state.setdefault("analisados", {})[res.documento] = res


def _marcar_revisado(chave: str) -> None:
    st.session_state.setdefault("revisados", set()).symmetric_difference_update({chave})


# ================================================================= cabeçalho em gradiente
def _ajustes() -> None:
    with st.popover("Ajustes", icon=":material/tune:"):
        st.session_state["modo_demo"] = st.toggle(
            "Modo demo (offline)",
            # Sempre começa ligado (D37): o .env de desenvolvimento traz MODO_DEMO=0 e, carregado
            # na primeira análise, desligaria a demo em toda sessão nova (um F5 no meio do pitch).
            value=_modo_demo(),
            key="w_modo_demo",
            help="Usa as respostas gravadas em cache/. Não precisa de internet nem de chave da API.",
        )
        st.session_state["ritmo"] = st.toggle(
            "Trilha em ritmo de apresentação",
            value=st.session_state.get("ritmo", True),
            key="w_ritmo",
            disabled=not _modo_demo(),
            help="No modo demo o cache responde na hora. Com isto ligado, cada passo da trilha "
            f"espera {PAUSA_APRESENTACAO} s para a banca acompanhar.",
        )
        if not _modo_demo():
            from dotenv import load_dotenv

            load_dotenv(RAIZ / ".env")
            if not os.getenv("ANTHROPIC_API_KEY"):
                st.warning("Sem ANTHROPIC_API_KEY no .env: ligue o modo demo ou configure a chave.")
        st.caption(f"Modelo: `{os.getenv('AGENTE_MODELO', MODELO_PADRAO)}`")


def _topo_hero() -> None:
    c1, c2 = st.columns([5, 1], vertical_alignment="center")
    with c1:
        _html(
            f'<div class="marca"><span class="marca-ic">{_svg("pulso")}</span>'
            f"<div>{escape(NOME_PRODUTO)}<small>o agente lê · o código confere</small></div></div>"
        )
    with c2, st.container(horizontal=True, horizontal_alignment="right"):
        _ajustes()


def _selo() -> str:
    return f'<div class="selo-dados">{_svg("cadeado")} {escape(SELO)}</div>'


def _hero_compacto(titulo: str, subtitulo: str) -> None:
    with st.container(key="hero"):
        _topo_hero()
        _html(
            f'<div class="hero-texto compacto"><div class="pergunta">{titulo}</div>'
            f'<div class="saudacao">{subtitulo}</div>{_selo()}</div>'
        )


def _hero_chegada() -> None:
    with st.container(key="hero"):
        _topo_hero()
        _html(
            f'<div class="hero-texto"><div class="pergunta">{escape(NOME_PRODUTO)}</div>'
            f'<div class="saudacao frase">{escape(FRASE_CHEGADA)}</div>{_selo()}</div>'
        )


# ================================================================= F2: a trilha ao vivo
def _num(padrao: str, texto: str) -> int:
    m = re.search(padrao, texto)
    return int(m.group(1)) if m else 0


def _texto_etapa(i: int, passos: list[PassoTrilha], r: Resultado | None, fim: bool) -> tuple:
    """(estado, texto) de um passo da trilha, com o resultado concreto que já se conhece."""
    pior = "ok"
    for p in passos:
        if p.status == "erro":
            pior = "erro"
        elif p.status in ("fallback", "retry") and pior != "erro":
            pior = "alerta"
    nomes = {p.etapa for p in passos}
    ultimo = passos[-1]
    if pior == "erro":
        return "erro", "A análise parou aqui. O motivo está em Pendências."

    if i == 0:  # leitura + triagem
        leitura = next((p for p in passos if p.etapa == "leitura"), None)
        if leitura and "Pseudonimização" not in leitura.detalhe:
            return "alerta", "Não conseguimos ler o texto deste PDF. Confira à mão."
        partes = [f"{_num(r'^(\d+) página', leitura.detalhe)} página(s)"] if leitura else []
        if r and r.triagem:
            partes.append(r.triagem.operadora)
            if r.triagem.competencia:
                partes.append(f"competência {r.triagem.competencia}")
        texto = ", ".join(partes) + ". Nome, CPF e carteira apagados antes da IA."
        sem_texto = re.search(
            r"páginas sem texto: \[([^\]]*)\]", leitura.detalhe if leitura else ""
        )
        if sem_texto:
            return "alerta", texto + (
                f" Não conseguimos ler a página {sem_texto.group(1)}: vai para revisão humana."
            )
        if any(p.etapa == "triagem" and p.status == "fallback" for p in passos):
            return "alerta", "Não parece um demonstrativo de retorno: vai para revisão humana."
        return ("ok" if "triagem" in nomes or fim else "rodando"), texto

    if i == 1:  # extração
        if r and r.itens:
            glosados = sum(1 for it in r.itens if it.glosado > 0)
            texto = f"{len(r.itens)} itens, {glosados} glosados."
        else:
            texto = "Cada linha cobrada separada, com valores e motivo."
        if pior == "alerta":
            texto += " A primeira leitura foi recusada pelo verificador e refeita."
        return ("ok" if pior == "ok" else "alerta"), texto

    if i == 2:  # soma
        resumo = ultimo.ferramentas[-1].resultado if ultimo.ferramentas else ultimo.detalhe
        if ultimo.status == "ok":
            if r and r.itens:
                total = sum(it.apresentado for it in r.itens)
                return "ok", f"{_brl(total)} = total impresso ✓"
            return "ok", "A soma das linhas bate com o total impresso ✓"
        if ultimo.status == "info":
            return "alerta", "Não dá para conferir a soma: uma página está sem texto."
        m = re.search(r"soma das linhas (R\$ [\d.,]+) × impresso (R\$ [\d.,]+)", resumo)
        if ultimo.status == "retry":
            return "alerta", "A soma não fechou na primeira leitura. Pedimos para reler."
        if m:
            return "alerta", (
                f"Soma divergente: impresso {m.group(2)}, linhas somam {m.group(1)} → enviado "
                "para revisão."
            )
        return "alerta", "Totais impressos não encontrados → enviado para revisão."

    if i == 3:  # Tabela 38
        total = len(ultimo.ferramentas)
        achados = sum(1 for f in ultimo.ferramentas if f.aprovado)
        if achados == total:
            return "ok", f"{achados} de {total} códigos encontrados ✓"
        return "alerta", (
            f"{achados} de {total} códigos encontrados. {total - achados} não existe(m) na tabela "
            "oficial → revisão humana, sem palpite."
        )

    if i == 4:  # análise
        if r and r.glosas:
            cont = {d: sum(g.decisao == d for g in r.glosas) for d in ROTULO_DECISAO}
            texto = (
                f"{len(r.glosas)} glosas: {cont['recorrer']} recorrer, {cont['nao_recorrer']} não "
                f"recorrer, {cont['revisao_humana']} revisão humana."
            )
        else:
            texto = "Para cada glosa, decidido se vale recorrer, com o porquê e a fonte."
        if pior == "alerta":
            texto += " Uma resposta foi recusada pelo verificador e refeita."
        return pior, texto

    # redação + verificador
    verif = next((p for p in passos if p.etapa == "verificar_recurso"), None)
    if not verif:
        return "rodando", "Escrevendo um recurso para cada glosa recorrível…"
    total = len(verif.ferramentas)
    aprovados = sum(1 for f in verif.ferramentas if f.aprovado)
    if aprovados == total:
        return "ok", f"Verificador aprovou {aprovados} de {total} ✓"
    return "alerta", (
        f"Verificador aprovou {aprovados} de {total}. {total - aprovados} retido(s) → revisão humana."
    )


def _estados_trilha(trilha: list[PassoTrilha], r: Resultado | None, fim: bool) -> list[tuple]:
    grupos: list[list[PassoTrilha]] = [[] for _ in ETAPAS]
    for p in trilha:
        if p.etapa in GRUPO_DA_ETAPA:
            grupos[GRUPO_DA_ETAPA[p.etapa]].append(p)
        elif p.status == "erro" and trilha:  # erro geral: marca o último passo visto
            ultimo = max((i for i, g in enumerate(grupos) if g), default=0)
            grupos[ultimo].append(p)
    vistos = [i for i, g in enumerate(grupos) if g]
    ultimo_visto = max(vistos, default=-1)
    estados = []
    for i, passos in enumerate(grupos):
        if passos:
            estado, texto = _texto_etapa(i, passos, r, fim)
            if estado == "rodando" and (fim or i < ultimo_visto):
                estado = "ok"
        elif fim or i < ultimo_visto:
            estado, texto = "pulado", "Não se aplica a este documento."
            if i == 5 and r and not any(g.decisao == "recorrer" for g in r.glosas):
                texto = "Nenhuma glosa recorrível: nada a redigir."
        elif i == ultimo_visto + 1:
            estado, texto = "rodando", "Em andamento…"
        else:
            estado, texto = "pendente", ""
        estados.append((estado, texto))
    return estados


def _trilha_html(estados: list[tuple], r: Resultado | None) -> str:
    partes = []
    for a in r.alertas if r else []:
        partes.append(
            f'<div class="aviso-injecao"><span class="sim">{_svg("escudo")}</span><div>'
            "<b>Encontramos uma instrução escondida no documento</b>"
            f"<small>“{escape(a.trecho or '')}” ({escape(_onde(a.pagina, a.linha))}). Ela foi "
            "ignorada: conteúdo do documento é dado, não ordem.</small></div></div>"
        )
    for (nome, _), (estado, texto) in zip(ETAPAS, estados, strict=True):
        partes.append(
            f'<div class="passo passo-{estado}"><span class="sim">{SIMBOLO_PASSO[estado]}</span>'
            f"<div><b>{escape(nome)}</b><small>{escape(texto)}</small></div></div>"
        )
    return '<div class="passos">' + "".join(partes) + "</div>"


def analisar(dados: bytes, nome: str, lugar=None) -> Resultado:
    """Roda o agente. Com `lugar`, desenha a trilha ao vivo nele."""
    modo_demo = _modo_demo()
    pausa = PAUSA_APRESENTACAO if modo_demo and st.session_state.get("ritmo", True) else 0
    orq = Orquestrador(ClienteAnthropic(modo_demo=modo_demo))
    trilha: list[PassoTrilha] = []

    def ao_passo(p: PassoTrilha) -> None:
        trilha.append(p)
        if lugar is not None:
            _html(_trilha_html(_estados_trilha(trilha, orq.resultado, False), orq.resultado), lugar)
            if pausa:
                time.sleep(pausa)

    orq.ao_passo = ao_passo
    res = orq.analisar(dados, nome=nome)
    _registrar(res)
    return res


# ================================================================= F1: chegada
def _chegada() -> tuple[bytes | None, str | None]:
    """Os bytes e o nome do PDF a analisar agora, ou (None, None)."""
    cat = _catalogo()
    nomes = list(cat)
    with st.container(key="cartao_chegada"):
        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            _html(
                '<div class="titulo-cartao">Envie o demonstrativo de retorno</div>'
                '<div class="sub">O PDF que a operadora mandou. Nesta demo, só dado fictício.</div>'
            )
            enviado = st.file_uploader(
                "PDF do demonstrativo", type=["pdf"], label_visibility="collapsed"
            )
        with c2:
            _html(
                '<div class="titulo-cartao">Ou veja com um exemplo</div>'
                '<div class="sub">Demonstrativos fictícios de três operadoras inventadas.</div>'
            )
            escolha = st.selectbox(
                "Exemplo",
                nomes,
                index=nomes.index(EXEMPLO_INICIAL),
                key="exemplo",
                format_func=_rotulo_exemplo,
                label_visibility="collapsed",
            )
            dados_exemplo = Path(cat[escolha]["caminho"]).read_bytes()
            clicou = st.button(
                "Analisar o exemplo",
                type="primary",
                icon=":material/play_arrow:",
                width="stretch",
            )
            st.download_button(
                "Ver o PDF do exemplo",
                dados_exemplo,
                file_name=escolha,
                mime="application/pdf",
                icon=":material/picture_as_pdf:",
                type="tertiary",
            )
    if enviado is not None and enviado.file_id != st.session_state.get("envio_id"):
        st.session_state["envio_id"] = enviado.file_id
        return enviado.getvalue(), enviado.name
    if clicou:
        return dados_exemplo, escolha
    return None, None


# ================================================================= F3: o número-herói
def _numero_heroi(res: Resultado) -> None:
    pnl = res.painel
    cores = [semaforo(g, res)[0] for g in res.glosas]
    para_conferir = sum(c != "pronto" for c in cores)
    glosas = f"{len(res.glosas)}" + (f" ({para_conferir} para conferir)" if para_conferir else "")
    pr = pnl.get("prazo")
    if pr and pr["vencido"]:
        prazo, classe = f"venceu ({pr['prazo_final'][:5]})", "perigo"
    elif pr:
        dias = pr["dias_restantes"]
        prazo = f"vence em {dias} dia{'s' if dias != 1 else ''} ({pr['prazo_final'][:5]})"
        classe = "perigo" if dias <= 3 else ""
    else:
        prazo, classe = "—", ""
    _html(
        _tiles(
            [
                ("moeda", "Pode ser recorrido", _brl(pnl["recorrivel"])),
                ("glosa", "Glosado no total", _brl(pnl["total_glosado"])),
                ("check", "Glosas", glosas),
                ("calendario", "Prazo mais próximo", prazo, classe),
            ],
            destaque=0,
        )
    )
    if pr:
        st.caption(
            f"Prazo fictício da {res.triagem.operadora}: {pr['prazo_dias']} dias depois da emissão "
            f"({pr['data_emissao']}). Os números desta tela são calculados pelo código, não pela IA."
        )
    if res.interrompido:
        st.error(
            res.pendencias[-1].motivo if res.pendencias else "Análise interrompida.",
            icon=":material/error:",
        )
    for p in res.pendencias:
        if p.item is not None:
            continue  # as pendências de uma glosa aparecem na própria glosa
        if p.tipo == "pagina_ilegivel":
            st.warning(
                f"Não conseguimos ler a página {p.pagina}. Confira à mão.",
                icon=":material/warning:",
            )
        elif p.tipo == "soma_divergente":
            m = re.search(r"soma das linhas (R\$ [\d.,]+) × impresso (R\$ [\d.,]+)", p.motivo)
            valores = f": impresso {m.group(2)}, linhas somam {m.group(1)}" if m else ""
            st.warning(
                f"A soma das linhas não bate com o total impresso{valores}. Confira os totais com "
                "a operadora antes de recorrer.",
                icon=":material/warning:",
            )
        elif p.tipo in PENDENCIA:
            titulo, acao = PENDENCIA[p.tipo]
            st.warning(f"**{titulo}.** {acao}", icon=":material/warning:")
    if res.glosas and not pnl["recorrivel"]:
        cls = _classificacao()
        preenchimento = sum(
            (cls.get(g.codigo_glosa or "", {}).get("grupo") == "preenchimento") for g in res.glosas
        )
        texto = "Nenhuma glosa recorrível neste demonstrativo."
        if preenchimento:
            texto += f" {preenchimento} glosa(s) são de preenchimento e podem ser evitadas no próximo lote."
        st.info(texto, icon=":material/info:")
    elif not res.glosas and not res.interrompido:
        st.success("Nenhuma glosa neste demonstrativo: tudo o que foi cobrado foi pago.")


# ================================================================= F4 e F5: as glosas e a prova
def _chave_revisao(res: Resultado, item: int) -> str:
    return f"{res.documento}#{item}"


def _lista_glosas(res: Resultado) -> None:
    if not res.glosas:
        return
    pr = res.painel.get("prazo") or {}
    revisados = st.session_state.get("revisados", set())
    ordem = glosas_priorizadas(res)
    linhas = []
    for g in ordem:
        cor, motivo_cor = semaforo(g, res)
        icone, rotulo = SEMAFORO[cor]
        linhas.append(
            {
                "Situação": f"{icone} {rotulo}",
                "Valor glosado": _brl(g.valor_glosado),
                "Guia": g.guia,
                "Motivo": _motivo_simples(g.descricao_oficial),
                "Decisão": ROTULO_DECISAO[g.decisao],
                "Prazo final": pr.get("prazo_final", "—"),
                "Onde": _onde(g.pagina, g.linha),
                "Revisado": "✓" if _chave_revisao(res, g.item) in revisados else "",
                "Para conferir": motivo_cor,
            }
        )
    tabela = pd.DataFrame(linhas)
    if not tabela["Para conferir"].any():  # tudo pronto: a coluna só ocuparia espaço
        tabela = tabela.drop(columns="Para conferir")
    evento = st.dataframe(
        tabela,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"tabela_{res.documento}",
        column_config={
            "Situação": st.column_config.TextColumn(width="small"),
            "Motivo": st.column_config.TextColumn(width="medium"),
            "Revisado": st.column_config.TextColumn(width="small"),
            "Para conferir": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption(
        "Prazo mais curto primeiro e, no empate, maior valor. 🟢 Pronto: confiança alta e todos os "
        "verificadores aprovaram. 🟡 Confira: confiança média ou algum verificador alertou. "
        "⚪ Revisão humana: o agente não decidiu. **Clique numa linha para ver a prova.**"
    )
    selecao = evento.selection.rows if evento else []
    _prova(ordem[selecao[0]] if selecao else ordem[0], res)


def _prova(g, res: Resultado) -> None:
    cor, motivo_cor = semaforo(g, res)
    icone, rotulo = SEMAFORO[cor]
    base = _trechos()
    linhas = st.session_state.get("linhas", {}).get(res.documento, {})
    with st.container(key="cartao_prova"):
        _html(
            f'<div class="titulo-cartao">{icone} {rotulo} · {_brl(g.valor_glosado)} · guia '
            f"{escape(g.guia)}</div>"
            + (f'<div class="sub">{escape(motivo_cor)}</div>' if motivo_cor else "")
        )
        esq, dir_ = st.columns([3, 2], gap="large")
        with esq:
            st.markdown("**Por que foi glosada**")
            if g.descricao_oficial:
                st.markdown(f"Código {g.codigo_glosa}: {_motivo_simples(g.descricao_oficial)}.")
                st.caption("Fonte: Tabela 38, Padrão TISS 202609 (ANS), descrição oficial.")
            else:
                st.markdown(
                    f"Código {g.codigo_glosa or '—'}: não consta na Tabela 38 oficial. O agente "
                    "não adivinha o significado."
                )
            titulo = {
                "recorrer": "Por que recorrer",
                "nao_recorrer": "Por que não recorrer",
                "revisao_humana": "Por que foi para revisão humana",
            }[g.decisao]
            st.markdown(
                f"**{titulo}** · :gray-badge[confiança {ROTULO_CONFIANCA[g.confianca]}] "
                f":gray-badge[decidido {'pela IA' if g.origem == 'agente' else 'pelo código'}]"
            )
            st.markdown(g.justificativa)
            fontes = [fid for fid in g.fontes if fid in base]
            if fontes:
                cols = st.columns(len(fontes))
                for col, fid in zip(cols, fontes, strict=True):
                    with col.popover(fid, icon=":material/attach_file:"):
                        st.markdown(base[fid]["texto"])
                        st.caption("Fonte: " + base[fid]["fonte"])
        with dir_:
            st.markdown(f"**Onde está no documento** · {_onde(g.pagina, g.linha)}")
            trecho_pdf = linhas.get((g.pagina, g.linha))
            if trecho_pdf:
                st.code(trecho_pdf, language=None, wrap_lines=True)
                st.caption("Nome e CPF já apagados: é exatamente o que a IA viu.")
            if g.documentos:
                st.markdown("**O que anexar**")
                st.markdown("\n".join(f"- {d}" for d in g.documentos))
            _html(
                '<span class="chip laranja">Classificação de demonstração, a validar com '
                "especialista</span>"
            )


# ================================================================= F6: o recurso pronto
def _recursos(res: Resultado) -> None:
    por_item = {r.item: r for r in res.recursos}
    recorriveis = [g for g in glosas_priorizadas(res) if g.decisao == "recorrer"]
    if not recorriveis:
        return
    _secao("Recursos prontos para revisar e enviar", f"{len(res.recursos)} de {len(recorriveis)}")
    with st.container(key="cartao_recursos"):
        if res.recursos:
            todos = "\n\n" + ("=" * 72 + "\n\n").join(
                por_item[g.item].texto + "\n\n" for g in recorriveis if g.item in por_item
            )
            st.download_button(
                "Baixar todos os recursos (.txt)",
                todos.strip().encode("utf-8"),
                file_name=f"recursos_{Path(res.documento).stem}.txt",
                icon=":material/download:",
                key=f"todos_{res.documento}",
            )
        revisados = st.session_state.get("revisados", set())
        for g in recorriveis:
            r = por_item.get(g.item)
            if r is None:
                st.warning(
                    f"O recurso da guia {g.guia} foi retido pelo verificador. Veja em Pendências.",
                    icon=":material/warning:",
                )
                continue
            preencher, confirmar = campos_a_preencher(r.texto)
            _html(
                f'<div class="titulo-cartao">Recurso · guia {escape(g.guia)} · '
                f"{_brl(g.valor_glosado)}</div>"
                f'<div class="sub">{escape(_motivo_simples(g.descricao_oficial))}</div>'
            )
            avisos = []
            if preencher:
                avisos.append(
                    f"Preencha {len(preencher)} campo(s) antes de enviar: "
                    + ", ".join(c.lower() for c in preencher)
                    + "."
                )
            if confirmar:
                avisos.append(
                    "Confirme o fundamento normativo: o recurso não cita norma que não verificamos."
                )
            if avisos:
                st.warning(" ".join(avisos), icon=":material/edit_note:")
            st.code(r.texto, language=None, wrap_lines=True)
            c1, c2 = st.columns([1, 2], vertical_alignment="center")
            c1.download_button(
                "Baixar .txt",
                r.texto.encode("utf-8"),
                file_name=f"recurso_guia_{g.guia}_{g.codigo_procedimento}.txt",
                key=f"dl_{res.documento}_{r.item}",
                icon=":material/download:",
            )
            chave = _chave_revisao(res, g.item)
            c2.checkbox(
                "Revisei este recurso",
                value=chave in revisados,
                key=f"w_rev_{chave}",
                on_change=_marcar_revisado,
                args=(chave,),
            )
        st.caption(
            "Para copiar, use o botão no canto de cada recurso. Troque o código CART pelo número da "
            "carteira antes de enviar."
        )


# ================================================================= página: início
def pagina_inicio() -> None:
    _hero_chegada()
    dados, nome = _chegada()

    if dados is not None:
        st.session_state["t0"] = time.perf_counter()
        st.session_state.pop("res", None)
        with st.container(key="cartao_trilha_viva"):
            _html('<div class="titulo-cartao">O agente está trabalhando</div>')
            lugar = st.empty()
            _html(_trilha_html(_estados_trilha([], None, False), None), lugar)
            res = analisar(dados, nome, lugar)
        st.session_state["res"] = res
        st.session_state.setdefault("linhas", {})[nome] = _linhas_pseudonimizadas(dados, nome)
        st.rerun()

    res: Resultado | None = st.session_state.get("res")
    if not res:
        return

    t0 = st.session_state.pop("t0", None)
    if t0 is not None:
        st.session_state.setdefault("tempo_ate_valor", {})[res.documento] = time.perf_counter() - t0

    _secao("O que o agente fez", escape(res.documento))
    with st.container(key="cartao_trilha"):
        _html(_trilha_html(_estados_trilha(res.trilha, res, True), res))
        with st.expander("Ver detalhes técnicos", icon=":material/code:"):
            for p in res.trilha:
                st.markdown(_texto_passo(p))
            tempo = st.session_state.get("tempo_ate_valor", {}).get(res.documento)
            st.caption(
                f"Modelo {res.modelo} · prompts {res.versoes_prompt} · {res.tokens_entrada:,} tokens "
                f"de entrada, {res.tokens_saida:,} de saída · custo estimado US$ "
                f"{res.custo_usd:.4f} · agente {res.latencia_ms / 1000:.1f} s".replace(",", ".")
                + (f" · do clique ao resultado {tempo:.1f} s".replace(".", ",") if tempo else "")
            )

    _secao("Quanto está em jogo")
    with st.container(key="cartao_heroi"):
        _numero_heroi(res)

    if res.glosas:
        _secao("Glosas, da mais urgente para a menos urgente", f"{len(res.glosas)} glosas")
        with st.container(key="cartao_glosas"):
            _lista_glosas(res)

    _recursos(res)


# ================================================================= F7: prazos
def _faixa_de_dias(linhas: list[dict]) -> str:
    if not linhas:
        return ""
    p0 = linhas[0]
    hoje = parse_data(p0["prazo_final"]) - dt.timedelta(days=p0["dias_restantes"])
    por_dia: dict[dt.date, int] = {}
    for p in linhas:
        d = parse_data(p["prazo_final"])
        por_dia[d] = por_dia.get(d, 0) + 1
    blocos = []
    for i in range(14):
        d = hoje + dt.timedelta(days=i)
        n = por_dia.get(d, 0)
        classe = " com-prazo" if n else (" hoje" if i == 0 else "")
        qtd = (
            f'<span class="qtd">{n} glosa{"s" if n > 1 else ""}</span>'
            if n
            else "<small>&nbsp;</small>"
        )
        rotulo = "hoje" if i == 0 else DIAS_SEMANA[d.weekday()]
        blocos.append(f'<div class="dia{classe}"><small>{rotulo}</small><b>{d.day}</b>{qtd}</div>')
    return '<div class="dias">' + "".join(blocos) + "</div>"


def _lista_agenda(linhas: list[dict]) -> str:
    itens = []
    for p in linhas:
        d = parse_data(p["prazo_final"])
        dias = p["dias_restantes"]
        if p["vencido"]:
            chip, classe = '<span class="chip vermelho">venceu</span>', " perigo"
        elif dias <= 3:
            chip, classe = f'<span class="chip vermelho">vence em {dias} dias</span>', " perigo"
        elif dias <= 10:
            chip, classe = f'<span class="chip laranja">vence em {dias} dias</span>', " urgente"
        else:
            chip, classe = f'<span class="chip cinza">vence em {dias} dias</span>', ""
        itens.append(
            f'<div class="prazo-item{classe}">'
            f'<div class="prazo-data"><b>{d.day}</b><small>{MESES[d.month - 1]}</small></div>'
            f'<div class="prazo-info"><b>{escape(_motivo_simples(p["descricao"]))}</b>'
            f"<small>guia {escape(p['guia'])} · {escape(p['documento'])} · "
            f"{escape(p['operadora'])}</small></div>"
            f'<div class="prazo-valor"><b>{_brl(p["valor"])}</b><small>pode ser recorrido</small>'
            f"</div>{chip}</div>"
        )
    return '<div class="prazos">' + "".join(itens) + "</div>"


def pagina_prazos() -> None:
    _hero_compacto(
        "Agenda de prazos",
        "Todas as glosas recorríveis dos demonstrativos analisados nesta sessão, do vencimento mais "
        "próximo ao mais distante. Os prazos de cada operadora são parâmetros fictícios.",
    )
    st.info(
        "No produto, você recebe este alerta por e-mail ou WhatsApp 10 e 3 dias antes de cada prazo.",
        icon=":material/notifications:",
    )
    with st.container(key="cartao_lote"):
        c1, c2 = st.columns([2, 1], vertical_alignment="center")
        incluir_validacao = c1.toggle(
            "Incluir os 5 documentos de validação (nunca vistos no ajuste)", value=False
        )
        rodar = c2.button(
            "Analisar todos os exemplos",
            icon=":material/play_arrow:",
            width="stretch",
        )
        if rodar:
            nomes = [
                n
                for n, m in _catalogo().items()
                if m["conjunto"] == "desenvolvimento" or incluir_validacao
            ]
            progresso = st.progress(0.0, text="Analisando…")
            for i, n in enumerate(nomes, 1):
                analisar(Path(_catalogo()[n]["caminho"]).read_bytes(), n)
                progresso.progress(i / len(nomes), text=f"{i} de {len(nomes)} demonstrativos")
            st.rerun()

    lote = _analisados()
    if not lote:
        st.info(
            "Nada analisado ainda nesta sessão. Analise um demonstrativo no Início ou clique em "
            "**Analisar todos os exemplos**.",
            icon=":material/arrow_upward:",
        )
        return

    linhas = agenda(lote)
    pg = painel_geral(lote)
    ate3 = sum(p["valor"] for p in linhas if p["dias_restantes"] <= 3)
    ate10 = sum(p["valor"] for p in linhas if p["dias_restantes"] <= 10)
    _html(
        _tiles(
            [
                ("doc", "Demonstrativos analisados", str(len(lote))),
                ("moeda", "Pode ser recorrido", _brl(pg["recorrivel"])),
                ("alerta", "Vence em até 3 dias", _brl(ate3), "perigo" if ate3 else ""),
                ("calendario", "Vence em até 10 dias", _brl(ate10)),
            ],
            destaque=1,
        )
    )
    if not linhas:
        st.info("Nenhuma glosa recorrível nos demonstrativos analisados.", icon=":material/info:")
        return
    _secao("Próximos 14 dias", "dias em verde-escuro têm prazo")
    with st.container(key="cartao_dias"):
        _html(_faixa_de_dias(linhas))
    n = len(linhas)
    _secao(
        "Do vencimento mais próximo ao mais distante",
        f"{n} glosa{'s' if n != 1 else ''} recorríve{'is' if n != 1 else 'l'}",
    )
    _html(_lista_agenda(linhas))


# ================================================================= F8: pendências
def _pendencia_html(documento: str, tipo: str, motivo: str, onde: str, alerta: bool) -> str:
    titulo, acao = PENDENCIA.get(tipo, (tipo, ""))
    if alerta:
        titulo, acao = "Instrução escondida no documento", "Nada a fazer: foi ignorada. Só confira."
    return (
        f'<div class="pendencia{" alerta" if alerta else ""}">'
        f'<span class="ic-redondo">{_svg("escudo" if alerta else "pessoa")}</span><div>'
        f'<b>{escape(titulo)}</b> <span class="onde">· {escape(documento)} · {escape(onde)}</span>'
        f"<p>{escape(motivo)}</p>"
        + (f'<div class="acao">O que fazer: {escape(acao)}</div>' if acao else "")
        + "</div></div>"
    )


def _pendencias_html(res: Resultado) -> str:
    partes = [
        _pendencia_html(
            res.documento,
            a.tipo,
            f"{a.motivo} “{a.trecho}”",
            _onde(a.pagina, a.linha),
            alerta=True,
        )
        for a in res.alertas
    ]
    partes += [
        _pendencia_html(res.documento, p.tipo, p.motivo, _onde(p.pagina, p.linha), alerta=False)
        for p in res.pendencias
    ]
    return "".join(partes)


def pagina_pendencias() -> None:
    _hero_compacto(
        "Pendências",
        "O que o agente não decide sozinho. Em vez de inventar, ele manda para você com o motivo e "
        "o lugar no PDF.",
    )
    fonte = _analisados()
    if not fonte:
        st.info(
            "Nada analisado ainda nesta sessão. Analise um demonstrativo no Início.",
            icon=":material/info:",
        )
        return
    n_alertas = sum(len(r.alertas) for r in fonte)
    n_pend = sum(len(r.pendencias) for r in fonte)
    _html(
        _tiles(
            [
                ("doc", "Demonstrativos analisados", str(len(fonte))),
                ("pessoa", "Pendências", str(n_pend)),
                ("escudo", "Instruções ignoradas", str(n_alertas)),
            ],
            destaque=1,
        )
    )
    if not n_alertas and not n_pend:
        st.success("Nada para revisão humana.", icon=":material/check:")
        return
    _secao("Para conferir", f"{n_pend + n_alertas} itens")
    _html("".join(_pendencias_html(r) for r in fonte))


# ================================================================= página: como funciona
FLUXO_DOT = """
digraph {
  rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.45;
  node [fontname="Helvetica", fontsize=11, shape=box, style="rounded,filled", color="#2B6467",
        fillcolor="#FFFFFF", fontcolor="#1C2B2D", penwidth=1.2];
  edge [color="#6B8F88", arrowsize=0.7, fontname="Helvetica", fontsize=9, fontcolor="#4E6B65"];

  pdf [label="PDF do\\ndemonstrativo", shape=note, fillcolor="#F1F6F6"];
  leitura [label="Leitura\\npágina e linha"];
  pseudo [label="Pseudonimização\\nnome e CPF saem"];
  filtro [label="Filtro de\\ninstruções"];
  tri [label="1 · Triagem", fillcolor="#2B6467", fontcolor="#FFFFFF"];
  ext [label="2 · Extração", fillcolor="#2B6467", fontcolor="#FFFFFF"];
  an [label="3 · Análise", fillcolor="#2B6467", fontcolor="#FFFFFF"];
  red [label="4 · Redação", fillcolor="#2B6467", fontcolor="#FFFFFF"];
  cons [label="Painel\\ntotais e prazos"];

  node [shape=hexagon, style="filled", fillcolor="#E3EFEE", color="#9DB8B2", fontsize=10];
  soma [label="conferir_soma\\nverificar_evidencia"];
  t38 [label="consultar_t38\\nTabela 38 oficial"];
  base [label="buscar_base · prazo\\nverificar_analise"];
  vr [label="verificar_recurso"];

  node [shape=box, style="rounded,filled,dashed", fillcolor="#FDF0E3", color="#C4610F", fontsize=10];
  hum [label="Revisão humana\\ncom o motivo"];

  pdf -> leitura -> pseudo -> filtro -> tri -> ext -> an -> red -> cons;
  ext -> soma [dir=both, style=dashed];
  ext -> t38 [dir=both, style=dashed];
  an -> base [dir=both, style=dashed];
  red -> vr [dir=both, style=dashed];
  {soma t38 vr} -> hum [color="#C4610F", style=dotted, label="falhou"];
  an -> hum [color="#C4610F", style=dotted, label="confiança baixa"];
  {rank=same; ext; soma; t38}
}
"""


def pagina_fluxo() -> None:
    _hero_compacto(
        "Como o agente funciona",
        "O agente faz o trabalho e o código fiscaliza o agente. O modelo decide o que exige leitura "
        "e julgamento: extração, enquadramento e redação. O código decide o que exige certeza: "
        "soma, existência do código, prazo, evidência e totais.",
    )
    _secao("O fluxo")
    with st.container(key="cartao_fluxo"):
        st.graphviz_chart(FLUXO_DOT, width="stretch")
        st.caption(
            "Verde-escuro: etapas do agente (modelo). Hexágonos: verificadores em código. Laranja: o "
            "caso vai para revisão humana. Se a saída de uma etapa não validar, ela refaz com o erro, "
            "no máximo 2 vezes."
        )
    texto = (RAIZ / "docs" / "fluxo.md").read_text(encoding="utf-8")
    texto = re.sub(r"```mermaid.*?```", "", texto, flags=re.S)
    # Os parágrafos de abertura repetem o cabeçalho; a página segue com o contrato das etapas.
    texto = texto[texto.find("## Contrato") :].replace("\n## ", "\n#### ").replace("## ", "#### ")
    _secao("O contrato de cada etapa")
    with st.container(key="cartao_contrato"):
        st.markdown(texto)


# ================================================================= página: qualidade
def _metas(md: str) -> list[list[str]]:
    """Linhas das tabelas do relatório que têm meta e resposta em "Bateu?"."""
    linhas = []
    for linha in md.splitlines():
        cel = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cel) == 4 and cel[3] in ("sim", "não"):
            linhas.append(cel)
    return linhas


def _tiles_metas(metas: list[list[str]]) -> str:
    blocos = []
    for oque, resultado, meta, bateu in metas:
        ok = bateu == "sim"
        blocos.append(
            f'<div class="tile"><span class="tile-ic">{_svg("check" if ok else "alerta")}</span>'
            f"<small>{escape(oque)}</small><b>{escape(resultado)}</b>"
            f'<span class="meta {"ok" if ok else "nao"}">meta {escape(meta)} · '
            f"{'bateu' if ok else 'não bateu'}</span></div>"
        )
    return '<div class="tiles">' + "".join(blocos) + "</div>"


def pagina_qualidade() -> None:
    _hero_compacto(
        "Qualidade medida",
        "Números reais contra o gabarito, sem arredondar para cima. As metas foram fixadas antes de "
        "construir e não mudam. Os dados são fictícios.",
    )
    conjuntos = {
        "Desenvolvimento (10 documentos)": ("RESULTADO.md", "python -m agente.avaliar"),
        "Validação (5 nunca vistos)": (
            "VALIDACAO.md",
            "python -m agente.avaliar --conjunto validacao",
        ),
        "Experiência de uso": ("EXPERIENCIA.md", "python -m agente.experiencia"),
    }
    st.session_state.setdefault("conjunto", next(iter(conjuntos)))
    escolha = st.pills("Conjunto", list(conjuntos), key="conjunto", label_visibility="collapsed")
    nome_arq, cmd = conjuntos[escolha or next(iter(conjuntos))]
    arq = RAIZ / "avaliacao" / nome_arq
    if not arq.exists():
        st.info(f"Ainda não há medida. Rode `{cmd}`.")
        return
    md = arq.read_text(encoding="utf-8")
    _html(_tiles_metas(_metas(md)))
    _secao("Relatório completo", escape(f"avaliacao/{nome_arq}"))
    with st.container(key="cartao_relatorio"):
        st.markdown(md)


# ================================================================= navegação
navegacao = st.navigation(
    [
        st.Page(
            pagina_inicio, title="Início", icon=":material/home:", url_path="inicio", default=True
        ),
        st.Page(pagina_prazos, title="Prazos", icon=":material/calendar_month:", url_path="prazos"),
        st.Page(
            pagina_pendencias,
            title="Pendências",
            icon=":material/person_search:",
            url_path="pendencias",
        ),
        st.Page(
            pagina_fluxo, title="Como funciona", icon=":material/account_tree:", url_path="fluxo"
        ),
        st.Page(
            pagina_qualidade, title="Qualidade", icon=":material/fact_check:", url_path="qualidade"
        ),
    ],
    position="top",
)
navegacao.run()
