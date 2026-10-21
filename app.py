"""Agente de Glosas — interface da demo (Streamlit).

    streamlit run app.py

Com o modo demo ligado, as respostas do modelo vêm do cache em cache/ e a demo roda sem internet.

Páginas, na ordem do pitch (docs/PITCH.md):
- Início: os demonstrativos, a trilha ao vivo por etapa e o resultado (painel, glosas, recursos);
- Prazos: os exemplos de uma vez, com o que vence nos próximos 10 dias;
- Revisão humana: as pendências e os alertas, com o que fazer em cada caso;
- Como funciona: o fluxo e o contrato de cada etapa (docs/fluxo.md);
- Qualidade: avaliacao/RESULTADO.md e avaliacao/VALIDACAO.md.

Visual: tema em .streamlit/config.toml e CSS em static/estilo.css (D37, D38). Todo texto que vem do
documento ou do modelo e entra em HTML passa por html.escape: conteúdo de PDF é dado, não marcação.
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

from agente.consolidar import painel_geral
from agente.dinheiro import format_brl
from agente.ferramentas.base import trechos
from agente.llm import MODELO_PADRAO, ClienteAnthropic
from agente.modelos import PassoTrilha, Resultado, parse_data
from agente.orquestrador import Orquestrador
from agente.pdf import PDFInvalido, extrair_texto
from agente.pseudonimo import pseudonimizar

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
ICONE_DECISAO = {"recorrer": "🟢", "nao_recorrer": "⚪", "revisao_humana": "🟠"}
ROTULO_CONFIANCA = {"alta": "alta", "media": "média", "baixa": "baixa"}
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
# As fases que a tela mostra lado a lado: nome, quem faz e as etapas da trilha que entram nela.
FASES = [
    ("Leitura", "código", ("leitura",)),
    ("1 · Triagem", "agente", ("triagem",)),
    ("2 · Extração", "agente + verificadores", ("extracao", "conferir_soma", "consultar_t38")),
    ("3 · Análise", "agente + base", ("analise",)),
    ("4 · Redação", "agente + verificador", ("redacao", "verificar_recurso")),
    ("Painel", "código", ()),
]
INDICE_FASE = {etapa: i for i, (_, _, etapas) in enumerate(FASES) for etapa in etapas}
ESTADO_FASE = {
    "pendente": ("○", "aguardando"),
    "rodando": ("◐", "rodando…"),
    "ok": ("✓", "ok"),
    "retry": ("↻", "refeita"),
    "fallback": ("!", "atenção"),
    "erro": ("✕", "erro"),
    "pulada": ("–", "não se aplica"),
}
GRAVIDADE = {"pendente": 0, "rodando": 0, "pulada": 0, "ok": 1, "info": 1, "retry": 2}
GRAVIDADE |= {"fallback": 3, "erro": 4}
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
# Para a revisão humana: o que cada pendência quer dizer e o que a faturista faz.
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
    "predio": '<path d="M4 21V6l8-3v18M12 8h8v13M4 21h16M8 9v.01M8 13v.01M8 17v.01M16 12v.01M16 16v.01"/>',
    "camadas": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "lupa": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "alerta": '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17v.01"/>',
    "pulso": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
}


def _svg(nome: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{_ICONES[nome]}</svg>'
    )


def _html(conteudo: str, lugar=None) -> None:
    (lugar or st).markdown(conteudo, unsafe_allow_html=True)


st.set_page_config(page_title="Agente de Glosas", page_icon="🩺", layout="wide")
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


def _grupos() -> dict[str, list[str]]:
    cat = _catalogo()
    dev = {n: m for n, m in cat.items() if m["conjunto"] == "desenvolvimento"}
    return {
        "Exemplos": [n for n, m in dev.items() if not m["adverso"]],
        "Casos adversos": [n for n, m in dev.items() if m["adverso"]],
        "Nunca vistos": [n for n, m in cat.items() if m["conjunto"] == "validacao"],
    }


def _grupo_de(nome: str) -> str:
    return next((g for g, nomes in _grupos().items() if nome in nomes), "Exemplos")


def _descricao(nome: str) -> str:
    m = _catalogo().get(nome, {})
    partes = [m.get("operadora", ""), f"layout {m['layout']}" if m.get("layout") else ""]
    if m.get("adverso"):
        partes.append("caso adverso: " + CASO_ADVERSO.get(m["adverso"], m["adverso"]))
    if m.get("conjunto") == "validacao":
        partes.append("nunca visto no ajuste")
    return " · ".join(p for p in partes if p)


def _chave(nome: str) -> str:
    return re.sub(r"\W", "_", Path(nome).stem)


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


def _texto_passo(p: PassoTrilha) -> str:
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


def _tiles(itens: list[tuple[str, str, str]], destaque: int | None = None) -> str:
    """Blocos de número: (ícone, rótulo, valor). Rótulo e valor já vêm escapados."""
    blocos = [
        f'<div class="tile{" destaque-tile" if i == destaque else ""}">'
        f'<span class="tile-ic">{_svg(ic)}</span><small>{rot}</small><b>{val}</b></div>'
        for i, (ic, rot, val) in enumerate(itens)
    ]
    return '<div class="tiles">' + "".join(blocos) + "</div>"


def _secao(titulo: str, lado: str = "") -> None:
    _html(f'<div class="secao"><h3>{titulo}</h3><span>{lado}</span></div>')


# ================================================================= estado da sessão
def _modo_demo() -> bool:
    return st.session_state.get("modo_demo", True)


def _caixa() -> list[Resultado] | None:
    """A caixa de entrada: os 10 exemplos já analisados. No modo demo, sai do cache na hora."""
    if st.session_state.get("lote") is None and _modo_demo():
        resultados = []
        for nome, m in _catalogo().items():
            if m["conjunto"] != "desenvolvimento":
                continue
            cli = ClienteAnthropic(modo_demo=True)
            dados = Path(m["caminho"]).read_bytes()
            resultados.append(Orquestrador(cli).analisar(dados, nome=nome))
        st.session_state["lote"] = resultados
    return st.session_state.get("lote")


def _abrir_documento(nome: str, rodar: bool) -> None:
    """Callback: escolhe o documento (e, se pedido, já analisa)."""
    st.session_state["origem"] = _grupo_de(nome)
    st.session_state["selecionado"] = nome
    if rodar:
        st.session_state["rodar_agora"] = True


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
        st.caption(
            "Dados 100% fictícios. Operadoras, clínica e pacientes são inventados. Nome e CPF "
            "saem antes de qualquer chamada ao modelo."
        )


def _topo_hero() -> None:
    c1, c2 = st.columns([5, 1], vertical_alignment="center")
    with c1:
        _html(
            f'<div class="marca"><span class="marca-ic">{_svg("pulso")}</span>'
            "<div>Agente de Glosas<small>o agente lê · o código confere</small></div></div>"
        )
    with c2, st.container(horizontal=True, horizontal_alignment="right"):
        _ajustes()


def _hero_compacto(titulo: str, subtitulo: str) -> None:
    with st.container(key="hero"):
        _topo_hero()
        _html(
            f'<div class="hero-texto compacto"><div class="pergunta">{titulo}</div>'
            f'<div class="saudacao">{subtitulo}</div></div>'
        )


def _saudacao() -> str:
    h = dt.datetime.now().hour
    return "Bom dia" if h < 12 else ("Boa tarde" if h < 18 else "Boa noite")


def _hero_inicio(lote: list[Resultado] | None) -> None:
    with st.container(key="hero"):
        _topo_hero()
        prazos = painel_geral(lote)["prazos"] if lote else []
        rotulo = "Próximo prazo de recurso" if prazos else ""
        _html(
            f'<div class="hero-texto"><div class="saudacao">{_saudacao()}, faturista</div>'
            '<div class="pergunta">Quais glosas vamos analisar hoje?</div>'
            f'<div class="rotulo">{rotulo}</div></div>'
        )
        if not prazos:
            return
        p = prazos[0]
        with st.container(key="destaque"):
            dias = p["dias_restantes"]
            quando = "vencido" if p["vencido"] else f"{dias} dia(s)"
            _html(
                f'<div class="destaque"><span class="ic-quadrado">{_svg("doc")}</span><div>'
                f"<b>{escape(p['documento'])}</b>"
                f'<div class="sub">{escape(p["operadora"])} · {_brl(p["recorrivel"])} recorrível</div>'
                f'<div class="linha-meta"><span>{_svg("calendario")} {escape(p["prazo_final"])}'
                f"</span><span>{_svg('relogio')} {quando}</span></div></div></div>"
            )
            b1, b2 = st.columns(2)
            if b1.button("Ver todos os prazos", width="stretch", icon=":material/event:"):
                st.switch_page(PAGINA_PRAZOS)
            b2.button(
                "Analisar agora",
                type="primary",
                width="stretch",
                icon=":material/play_arrow:",
                on_click=_abrir_documento,
                args=(p["documento"], True),
            )


# ================================================================= fases (a faixa da trilha)
def _estados_fases(trilha: list[PassoTrilha], fim: bool, interrompido: bool = False) -> list[str]:
    estados = ["pendente"] * len(FASES)
    ultima = -1
    for p in trilha:
        i = INDICE_FASE.get(p.etapa)
        if i is None:  # etapa "fluxo": erro geral, marca a fase em que parou
            if p.status == "erro":
                estados[max(ultima, 0)] = "erro"
            continue
        if GRAVIDADE[p.status] > GRAVIDADE[estados[i]]:
            estados[i] = p.status
        ultima = max(ultima, i)
    if fim:
        estados = ["pulada" if e == "pendente" else e for e in estados]
        estados[-1] = "erro" if interrompido else "ok"
    elif ultima + 1 < len(FASES):
        estados[ultima + 1] = "rodando"
    return ["ok" if e == "info" else e for e in estados]


def _fases_html(estados: list[str]) -> str:
    blocos = []
    for (nome, quem, _), estado in zip(FASES, estados, strict=True):
        simbolo, texto = ESTADO_FASE[estado]
        blocos.append(
            f'<div class="fase fase-{estado}"><span class="fase-sim">{simbolo}</span>'
            f"<b>{nome}</b><small>{quem}</small><small>{texto}</small></div>"
        )
    return '<div class="fases">' + "".join(blocos) + "</div>"


# ================================================================= análise
def analisar(dados: bytes, nome: str, area, lugar_fases=None) -> Resultado:
    modo_demo = _modo_demo()
    cli = ClienteAnthropic(modo_demo=modo_demo)
    pausa = PAUSA_APRESENTACAO if modo_demo and st.session_state.get("ritmo", True) else 0
    trilha: list[PassoTrilha] = []
    with area.status(f"Analisando {nome}…", expanded=lugar_fases is not None) as status:

        def ao_passo(p: PassoTrilha) -> None:
            trilha.append(p)
            status.markdown(_texto_passo(p))
            if lugar_fases is not None:
                _html(_fases_html(_estados_fases(trilha, fim=False)), lugar_fases)
            if pausa:
                time.sleep(pausa)

        res = Orquestrador(cli, ao_passo=ao_passo).analisar(dados, nome=nome)
        if lugar_fases is not None:
            _html(_fases_html(_estados_fases(res.trilha, True, res.interrompido)), lugar_fases)
        status.update(
            label=f"{nome}: {len(res.glosas)} glosa(s), {len(res.recursos)} recurso(s), "
            f"{len(res.pendencias)} pendência(s) — {res.latencia_ms / 1000:.1f} s",
            state="error" if res.interrompido else "complete",
            expanded=False,
        )
    return res


def _cabecalho_documento(res: Resultado) -> None:
    tri = res.triagem
    chips = ""
    if tri:
        chips = f'<span class="chip">{_svg("predio")} {escape(tri.operadora)}</span>'
        for rotulo, valor in (
            ("competência", tri.competencia),
            ("emitido em", tri.data_emissao),
            ("protocolo", tri.protocolo),
        ):
            if valor:
                chips += f'<span class="chip cinza">{rotulo} {escape(valor)}</span>'
    _html(
        f'<div class="titulo-cartao" style="font-size:1.45rem">{escape(res.documento)}</div>'
        f"<div>{chips}</div>"
    )


def _avisos(res: Resultado) -> None:
    pnl = res.painel
    if res.interrompido:
        st.error(
            res.pendencias[-1].motivo if res.pendencias else "Análise interrompida.",
            icon=":material/error:",
        )
    pr = pnl.get("prazo")
    if pr:
        txt = (
            f"**Prazo de recurso: {pr['prazo_final']}** — {pr['dias_restantes']} dia(s) a partir de "
            f"hoje. Parâmetro fictício da {res.triagem.operadora}: {pr['prazo_dias']} dias da emissão."
        )
        if pr["vencido"]:
            st.error("Prazo vencido. " + txt, icon=":material/event_busy:")
        elif pr["urgente"]:
            st.warning("Vence nos próximos 10 dias. " + txt, icon=":material/alarm:")
        else:
            st.info(txt, icon=":material/event:")
    for a in res.alertas:
        st.error(
            f"**Instrução dentro do documento ignorada** ({_onde(a.pagina, a.linha)}): "
            f"“{a.trecho}”. O texto foi retirado antes do modelo e não influenciou as decisões.",
            icon=":material/shield:",
        )


def _tiles_painel(pnl: dict) -> str:
    return _tiles(
        [
            ("doc", "Total apresentado", _brl(pnl["total_apresentado"])),
            ("glosa", "Total glosado", _brl(pnl["total_glosado"])),
            ("moeda", "Recorrível", _brl(pnl["recorrivel"])),
            ("pessoa", "A classificar", _brl(pnl["a_classificar"])),
            ("check", "Não recorrível", _brl(pnl["nao_recorrivel"])),
        ],
        destaque=2,
    )


def _aba_glosas(res: Resultado) -> None:
    if not res.glosas:
        st.info("Nenhuma glosa encontrada neste documento.", icon=":material/check:")
        return
    tabela = pd.DataFrame(
        [
            {
                "Decisão": f"{ICONE_DECISAO[g.decisao]} {ROTULO_DECISAO[g.decisao]}",
                "Guia": g.guia,
                "Procedimento": g.codigo_procedimento,
                "Glosa": g.codigo_glosa or "—",
                "Descrição oficial (Tabela 38)": g.descricao_oficial or "não consta na Tabela 38",
                "Valor glosado": _brl(g.valor_glosado),
                "Confiança": ROTULO_CONFIANCA[g.confianca],
                "Onde": _onde(g.pagina, g.linha),
            }
            for g in res.glosas
        ]
    )
    st.dataframe(
        tabela,
        hide_index=True,
        width="stretch",
        column_config={
            "Decisão": st.column_config.TextColumn(width="medium"),
            "Descrição oficial (Tabela 38)": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption("Abra uma glosa para ver a justificativa, a evidência no PDF e as fontes.")
    base = _trechos()
    linhas = st.session_state.get("linhas", {})
    for g in res.glosas:
        cor = COR_DECISAO[g.decisao]
        rotulo = (
            f":{cor}[**{ROTULO_DECISAO[g.decisao]}**] · guia {g.guia} · glosa "
            f"{g.codigo_glosa or '—'} · {_brl(g.valor_glosado)}"
        )
        with st.expander(rotulo):
            esq, dir_ = st.columns([3, 2], gap="large")
            with esq:
                st.markdown("**Justificativa**")
                st.markdown(g.justificativa)
                if g.documentos:
                    st.markdown("**Documentos para anexar**")
                    st.markdown("\n".join(f"- {d}" for d in g.documentos))
            with dir_:
                st.markdown(
                    f":{cor}-badge[{ROTULO_DECISAO[g.decisao]}] "
                    f":gray-badge[confiança {ROTULO_CONFIANCA[g.confianca]}] "
                    f":gray-badge[decidido pelo {'agente' if g.origem == 'agente' else 'código'}]"
                )
                trecho_pdf = linhas.get((g.pagina, g.linha))
                st.markdown(f"**Evidência no PDF** · {_onde(g.pagina, g.linha)}")
                if trecho_pdf:
                    st.code(trecho_pdf, language=None, wrap_lines=True)
                    st.caption("Texto já pseudonimizado: é o que o modelo viu.")
                if g.fontes:
                    st.markdown("**Fontes da base**")
                    for fid in g.fontes:
                        t = base.get(fid)
                        if t:
                            with st.popover(fid, icon=":material/attach_file:"):
                                st.markdown(t["texto"])
                                st.caption("Fonte: " + t["fonte"])


def _aba_recursos(res: Resultado) -> None:
    if not res.recursos:
        st.info("Nenhuma glosa recorrível neste documento.", icon=":material/info:")
        return
    st.caption(
        "Cada rascunho passou pelo verificador: valores conferidos, nenhuma norma inventada, nenhum "
        "dado pessoal em claro. Complete os campos [A PREENCHER] e troque o token CART pelo número da "
        "carteira. O botão no canto do texto copia o rascunho."
    )
    for r in res.recursos:
        it = res.itens[r.item]
        with st.expander(
            f":material/description: Recurso — guia {it.guia} · procedimento "
            f"{it.codigo_procedimento} · {_brl(it.glosado)}",
            expanded=len(res.recursos) == 1,
        ):
            st.code(r.texto, language=None, wrap_lines=True)
            st.download_button(
                "Baixar .txt",
                r.texto.encode("utf-8"),
                file_name=f"recurso_guia_{it.guia}_{it.codigo_procedimento}.txt",
                key=f"dl_{res.documento}_{r.item}",
                icon=":material/download:",
            )


def _pendencia_html(documento: str, tipo: str, motivo: str, onde: str, alerta: bool) -> str:
    titulo, acao = PENDENCIA.get(tipo, (tipo, ""))
    if alerta:
        titulo, acao = "Instrução no documento", "Nada a fazer: o texto foi ignorado. Só confira."
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


def _aba_pendencias(res: Resultado) -> None:
    if not res.pendencias and not res.alertas:
        st.success("Nada para revisão humana neste documento.", icon=":material/check:")
        return
    _html(_pendencias_html(res))


def _aba_trilha(res: Resultado) -> None:
    for p in res.trilha:
        st.markdown(_texto_passo(p))
    st.caption(
        f"Modelo {res.modelo} · prompts {res.versoes_prompt} · {res.tokens_entrada:,} tokens de "
        f"entrada, {res.tokens_saida:,} de saída · custo estimado US$ {res.custo_usd:.4f}".replace(
            ",", "."
        )
    )


# ================================================================= página: início
def _cartao_documento(nome: str, selecionado: bool) -> None:
    m = _catalogo()[nome]
    classe = "adverso" if m["adverso"] else ("validacao" if m["conjunto"] == "validacao" else "")
    if m["adverso"]:
        sub = "caso adverso: " + CASO_CURTO.get(m["adverso"], m["adverso"])
    elif m["conjunto"] == "validacao":
        sub = "nunca visto no ajuste"
    else:
        sub = "demonstrativo de retorno"
    estado = "sel" if selecionado else "nao"
    with st.container(key=f"doc_{estado}_{_chave(nome)}"):
        _html(
            f'<div class="doc-topo {classe}"><span class="selo">layout {escape(m["layout"])}</span>'
            f"{_svg('alerta' if m['adverso'] else 'doc')}</div>"
            f'<div class="doc-nome">{escape(Path(nome).stem)}</div>'
            f'<div class="doc-sub">{escape(m["operadora"])}<br>{sub}</div>'
        )
        st.button(
            "Selecionado" if selecionado else "Selecionar",
            key=f"b_{_chave(nome)}",
            type="primary" if selecionado else "secondary",
            icon=":material/check:" if selecionado else None,
            width="stretch",
            on_click=_abrir_documento,
            args=(nome, False),
        )


def _grade_documentos(nomes: list[str], selecionado: str) -> None:
    for i in range(0, len(nomes), 4):
        cols = st.columns(4)
        for col, nome in zip(cols, nomes[i : i + 4], strict=False):
            with col:
                _cartao_documento(nome, nome == selecionado)


def pagina_inicio() -> None:
    lote = _caixa()
    _hero_inicio(lote)

    grupos = _grupos()
    st.session_state.setdefault("origem", "Exemplos")
    _secao("Seus demonstrativos", "dados 100% fictícios")
    origem = (
        st.pills(
            "Documento",
            [*grupos, "Enviar PDF"],
            key="origem",
            label_visibility="collapsed",
        )
        or "Exemplos"
    )

    dados = nome = None
    if origem == "Enviar PDF":
        with st.container(key="cartao_envio"):
            enviado = st.file_uploader("PDF do demonstrativo (só dado fictício)", type=["pdf"])
            if enviado is not None:
                dados, nome = enviado.getvalue(), enviado.name
    else:
        opcoes = grupos[origem]
        sel = st.session_state.get("selecionado")
        if sel not in opcoes:
            sel = EXEMPLO_INICIAL if EXEMPLO_INICIAL in opcoes else opcoes[0]
            st.session_state["selecionado"] = sel
        _grade_documentos(opcoes, sel)
        nome = sel
        dados = Path(_catalogo()[sel]["caminho"]).read_bytes()

    clicou = False
    if dados is not None:
        with st.container(key="cartao_selecionado"):
            esq, dir_ = st.columns([3, 2], vertical_alignment="center", gap="large")
            with esq:
                _html(
                    '<div class="sub">Documento selecionado</div>'
                    f'<div class="titulo-cartao" style="font-size:1.6rem">{escape(nome)}</div>'
                    f'<div class="sub">{escape(_descricao(nome) or "PDF enviado")}</div>'
                )
            with dir_:
                m = _catalogo().get(nome, {})
                _html(
                    _tiles(
                        [
                            ("predio", "Operadora", escape(m.get("operadora", "—"))),
                            ("camadas", "Layout", escape(m.get("layout", "—") or "—")),
                        ]
                    )
                )
            clicou = st.button(
                "Analisar demonstrativo",
                type="primary",
                icon=":material/play_arrow:",
                width="stretch",
                key="cta_analisar",
            )
            if origem != "Enviar PDF":
                st.download_button(
                    "Ver o PDF",
                    dados,
                    file_name=nome,
                    mime="application/pdf",
                    icon=":material/picture_as_pdf:",
                    type="tertiary",
                )

    if (clicou or st.session_state.pop("rodar_agora", False)) and dados is not None:
        st.session_state.pop("res", None)
        with st.container(key="cartao_trilha_viva"):
            _html('<div class="titulo-cartao">Trilha do agente, ao vivo</div>')
            lugar = st.empty()
            _html(_fases_html(["pendente"] * len(FASES)), lugar)
            res = analisar(dados, nome, st, lugar)
        st.session_state["res"] = res
        st.session_state["linhas"] = _linhas_pseudonimizadas(dados, nome)
        st.rerun()

    res: Resultado | None = st.session_state.get("res")
    if not res:
        return

    _secao("Resultado da análise", escape(res.documento))
    with st.container(key="cartao_trilha"):
        _html('<div class="titulo-cartao">Trilha do agente</div>')
        _html(_fases_html(_estados_fases(res.trilha, True, res.interrompido)))
    with st.container(key="cartao_resultado"):
        _cabecalho_documento(res)
        _avisos(res)
        _html(_tiles_painel(res.painel))
        n_pend = len(res.pendencias) + len(res.alertas)
        abas = st.tabs(
            [
                f"Glosas ({len(res.glosas)})",
                f"Recursos ({len(res.recursos)})",
                f"Revisão humana ({n_pend})",
                "Trilha completa",
            ]
        )
        with abas[0]:
            _aba_glosas(res)
        with abas[1]:
            _aba_recursos(res)
        with abas[2]:
            _aba_pendencias(res)
        with abas[3]:
            _aba_trilha(res)


# ================================================================= página: prazos
def _faixa_de_dias(prazos: list[dict]) -> str:
    if not prazos:
        return ""
    p0 = prazos[0]
    hoje = parse_data(p0["prazo_final"]) - dt.timedelta(days=p0["dias_restantes"])
    por_dia: dict[dt.date, int] = {}
    for p in prazos:
        d = parse_data(p["prazo_final"])
        por_dia[d] = por_dia.get(d, 0) + 1
    blocos = []
    for i in range(14):
        d = hoje + dt.timedelta(days=i)
        n = por_dia.get(d, 0)
        classe = " com-prazo" if n else (" hoje" if i == 0 else "")
        qtd = (
            f'<span class="qtd">{n} prazo{"s" if n > 1 else ""}</span>'
            if n
            else "<small>&nbsp;</small>"
        )
        rotulo = "hoje" if i == 0 else DIAS_SEMANA[d.weekday()]
        blocos.append(f'<div class="dia{classe}"><small>{rotulo}</small><b>{d.day}</b>{qtd}</div>')
    return '<div class="dias">' + "".join(blocos) + "</div>"


def _lista_prazos(prazos: list[dict]) -> str:
    itens = []
    for p in prazos:
        d = parse_data(p["prazo_final"])
        if p["vencido"]:
            chip = '<span class="chip vermelho">vencido</span>'
        elif p["urgente"]:
            chip = f'<span class="chip laranja">{p["dias_restantes"]} dias</span>'
        else:
            chip = f'<span class="chip cinza">{p["dias_restantes"]} dias</span>'
        itens.append(
            f'<div class="prazo-item{" urgente" if p["urgente"] or p["vencido"] else ""}">'
            f'<div class="prazo-data"><b>{d.day}</b><small>{MESES[d.month - 1]}</small></div>'
            f'<div class="prazo-info"><b>{escape(p["documento"])}</b>'
            f"<small>{escape(p['operadora'])} · prazo final {escape(p['prazo_final'])}</small></div>"
            f'<div class="prazo-valor"><b>{_brl(p["recorrivel"])}</b><small>recorrível</small></div>'
            f"{chip}</div>"
        )
    return '<div class="prazos">' + "".join(itens) + "</div>"


def pagina_prazos() -> None:
    _hero_compacto(
        "Prazos de recurso",
        "Todos os demonstrativos de uma vez: quanto é recorrível e o que vence nos próximos 10 "
        "dias. Os prazos de cada operadora são parâmetros fictícios.",
    )
    with st.container(key="cartao_lote"):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        incluir_validacao = c1.toggle(
            "Incluir os 5 documentos de validação (nunca vistos no ajuste)", value=False
        )
        rodar = c2.button(
            "Analisar todos", type="primary", icon=":material/play_arrow:", width="stretch"
        )
        if rodar:
            nomes = [
                n
                for n, m in _catalogo().items()
                if m["conjunto"] == "desenvolvimento" or incluir_validacao
            ]
            progresso = st.progress(0.0, text="Analisando…")
            resultados = []
            for i, n in enumerate(nomes, 1):
                dados = Path(_catalogo()[n]["caminho"]).read_bytes()
                resultados.append(analisar(dados, n, st))
                progresso.progress(i / len(nomes), text=f"{i} de {len(nomes)} documentos")
            st.session_state["lote"] = resultados
            st.rerun()

    lote = _caixa()
    if not lote:
        st.info(
            "Clique em **Analisar todos**. Fora do modo demo, cada documento chama a API.",
            icon=":material/arrow_upward:",
        )
        return

    pg = painel_geral(lote)
    _html(
        _tiles(
            [
                ("doc", "Documentos", str(len(lote))),
                ("glosa", "Total glosado", _brl(pg["total_glosado"])),
                ("moeda", "Recorrível", _brl(pg["recorrivel"])),
                ("pessoa", "A classificar", _brl(pg["a_classificar"])),
                ("check", "Não recorrível", _brl(pg["nao_recorrivel"])),
            ],
            destaque=2,
        )
    )
    urgentes = [p for p in pg["prazos"] if p["urgente"] or p["vencido"]]
    if urgentes:
        st.warning(
            f"**{len(urgentes)} prazo(s) nos próximos 10 dias**, com "
            f"{_brl(sum(p['recorrivel'] for p in urgentes))} recorríveis.",
            icon=":material/alarm:",
        )

    _secao("Próximos 14 dias", "dias em verde-escuro têm prazo")
    with st.container(key="cartao_dias"):
        _html(_faixa_de_dias(pg["prazos"]))
    _secao("Do mais próximo ao mais distante", f"{len(pg['prazos'])} prazos")
    _html(_lista_prazos(pg["prazos"]))

    _secao("Por documento")
    with st.container(key="cartao_por_documento"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Documento": r.documento,
                        "Glosas": len(r.glosas),
                        "Total glosado": _brl(r.painel.get("total_glosado", 0)),
                        "Recorrível": _brl(r.painel.get("recorrivel", 0)),
                        "A classificar": _brl(r.painel.get("a_classificar", 0)),
                        "Recursos prontos": len(r.recursos),
                        "Revisão humana": len(r.pendencias) + len(r.alertas),
                    }
                    for r in lote
                ]
            ),
            hide_index=True,
            width="stretch",
        )


# ================================================================= página: revisão humana
def pagina_revisao() -> None:
    _hero_compacto(
        "Revisão humana",
        "O que o agente não decide sozinho. Em vez de inventar, ele manda para a faturista com o "
        "motivo e o lugar no PDF.",
    )
    fonte = _caixa() or ([st.session_state["res"]] if st.session_state.get("res") else [])
    if not fonte:
        st.info(
            "Rode uma análise em **Início** ou **Prazos** primeiro.",
            icon=":material/info:",
        )
        return
    n_alertas = sum(len(r.alertas) for r in fonte)
    n_pend = sum(len(r.pendencias) for r in fonte)
    _html(
        _tiles(
            [
                ("doc", "Documentos analisados", str(len(fonte))),
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
    """Linhas da primeira tabela do relatório que têm meta e resposta em "Bateu?"."""
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
    }
    st.session_state.setdefault("conjunto", next(iter(conjuntos)))
    escolha = st.pills("Conjunto", list(conjuntos), key="conjunto", label_visibility="collapsed")
    nome_arq, cmd = conjuntos[escolha or next(iter(conjuntos))]
    arq = RAIZ / "avaliacao" / nome_arq
    if not arq.exists():
        st.info(f"Ainda não há avaliação. Rode `{cmd}`.")
        return
    md = arq.read_text(encoding="utf-8")
    _html(_tiles_metas(_metas(md)))
    _secao("Relatório completo", escape(f"avaliacao/{nome_arq}"))
    with st.container(key="cartao_relatorio"):
        st.markdown(md)


# ================================================================= navegação
PAGINA_INICIO = st.Page(
    pagina_inicio, title="Início", icon=":material/home:", url_path="inicio", default=True
)
PAGINA_PRAZOS = st.Page(
    pagina_prazos, title="Prazos", icon=":material/calendar_month:", url_path="prazos"
)
navegacao = st.navigation(
    [
        PAGINA_INICIO,
        PAGINA_PRAZOS,
        st.Page(
            pagina_revisao,
            title="Revisão humana",
            icon=":material/person_search:",
            url_path="revisao",
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
