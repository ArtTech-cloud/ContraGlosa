"""Agente de Glosas — interface da demo (Streamlit).

    streamlit run app.py

Com o modo demo ligado, as respostas do modelo vêm do cache em cache/ e a demo roda sem internet.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from agente.consolidar import painel_geral
from agente.dinheiro import format_brl
from agente.ferramentas.base import trechos
from agente.llm import MODELO_PADRAO, ClienteAnthropic
from agente.modelos import PassoTrilha, Resultado
from agente.orquestrador import Orquestrador
from agente.pdf import PDFInvalido, extrair_texto
from agente.pseudonimo import pseudonimizar

RAIZ = Path(__file__).resolve().parent
EXEMPLOS = RAIZ / "dados" / "exemplos"
VALIDACAO = RAIZ / "dados" / "validacao"
ROTULO_DECISAO = {
    "recorrer": "Recorrer",
    "nao_recorrer": "Não recorrer",
    "revisao_humana": "Revisão humana",
}
ICONE_STATUS = {"ok": "✅", "retry": "🔁", "fallback": "⚠️", "erro": "❌", "info": "ℹ️"}
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

st.set_page_config(page_title="Agente de Glosas", page_icon="🩺", layout="wide")


@st.cache_data
def _trechos() -> dict[str, dict]:
    return {t.id: {"fonte": t.fonte, "texto": t.texto} for t in trechos()}


def _brl(c: int) -> str:
    return format_brl(int(c))


def _linhas_pseudonimizadas(dados: bytes, nome: str) -> dict[tuple[int, int], str]:
    try:
        doc = extrair_texto(dados, nome=nome)
    except PDFInvalido:
        return {}
    return {(lin.pagina, lin.linha): lin.texto for lin in pseudonimizar(doc.linhas).linhas}


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
    cab = f"{ic} **{nome}**" + (f" — {' · '.join(extra)}" if extra else "")
    linhas = [cab]
    if p.detalhe:
        linhas.append(f"   {p.detalhe}")
    for f in p.ferramentas:
        marca = "" if f.aprovado is None else (" ✅" if f.aprovado else " ❌")
        args = ", ".join(f"{k}={v}" for k, v in f.argumentos.items())
        linhas.append(f"   ↳ `{f.nome}({args})`{marca} {f.resultado[:140]}")
    return "\n\n".join(linhas)


def analisar(dados: bytes, nome: str, modo_demo: bool, area) -> Resultado:
    cli = ClienteAnthropic(modo_demo=modo_demo)
    with area.status(f"Analisando {nome}…", expanded=True) as status:

        def ao_passo(p: PassoTrilha) -> None:
            status.markdown(_texto_passo(p))

        res = Orquestrador(cli, ao_passo=ao_passo).analisar(dados, nome=nome)
        estado = "error" if res.interrompido else "complete"
        status.update(
            label=f"{nome}: {len(res.glosas)} glosa(s), {len(res.recursos)} recurso(s), "
            f"{len(res.pendencias)} pendência(s) — {res.latencia_ms / 1000:.1f} s",
            state=estado,
            expanded=False,
        )
    return res


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.title("🩺 Agente de Glosas")
    st.caption(
        "Lê o demonstrativo da operadora, encontra as glosas, decide se vale recorrer e redige o recurso."
    )
    modo_demo = st.toggle(
        "Modo demo (offline)",
        value=os.getenv("MODO_DEMO", "1") == "1",
        help="Usa as respostas gravadas em cache/. Não precisa de internet nem de chave da API.",
    )
    if not modo_demo and not os.getenv("ANTHROPIC_API_KEY"):
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env")
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.warning("Sem ANTHROPIC_API_KEY no .env: ligue o modo demo ou configure a chave.")
    st.caption(f"Modelo: `{os.getenv('AGENTE_MODELO', MODELO_PADRAO)}`")
    st.divider()
    st.markdown("**Dados 100% fictícios.** Operadoras, clínica e pacientes são inventados.")

aba_analise, aba_lote, aba_pend, aba_qualidade = st.tabs(
    ["Análise", "Todos os exemplos", "Pendências", "Qualidade"]
)

# ---------------------------------------------------------------- análise de um documento
with aba_analise:
    caminhos = {p.name: p for p in sorted(EXEMPLOS.glob("*.pdf"))}
    caminhos |= {p.name: p for p in sorted(VALIDACAO.glob("*.pdf"))}
    c1, c2 = st.columns([2, 3])
    with c1:
        escolha = st.selectbox(
            "Escolha um exemplo",
            list(caminhos),
            index=0,
            format_func=lambda n: (
                n + ("  (validação: nunca visto no ajuste)" if n.startswith("validacao_") else "")
            ),
        )
    with c2:
        enviado = st.file_uploader("ou envie um PDF (só dado fictício)", type=["pdf"])
    if enviado is not None:
        dados, nome = enviado.getvalue(), enviado.name
    else:
        dados, nome = caminhos[escolha].read_bytes(), escolha
    with open(caminhos[escolha], "rb") as f:
        st.download_button(
            "Baixar o PDF de exemplo", f.read(), file_name=escolha, mime="application/pdf"
        )

    if st.button("Analisar", type="primary"):
        st.session_state["res"] = analisar(dados, nome, modo_demo, st)
        st.session_state["linhas"] = _linhas_pseudonimizadas(dados, nome)

    res: Resultado | None = st.session_state.get("res")
    if res:
        pnl = res.painel
        st.subheader(f"Resultado — {res.documento}")
        if res.interrompido:
            st.error(res.pendencias[-1].motivo if res.pendencias else "análise interrompida")
        m = st.columns(5)
        m[0].metric("Total apresentado", _brl(pnl["total_apresentado"]))
        m[1].metric("Total glosado", _brl(pnl["total_glosado"]))
        m[2].metric("Recorrível", _brl(pnl["recorrivel"]))
        m[3].metric("A classificar", _brl(pnl["a_classificar"]), help="vai para revisão humana")
        m[4].metric("Não recorrível", _brl(pnl["nao_recorrivel"]))
        pr = pnl.get("prazo")
        if pr:
            txt = (
                f"Prazo de recurso ({res.triagem.operadora}): **{pr['prazo_final']}** — "
                f"{pr['dias_restantes']} dia(s) a partir de hoje. Parâmetro fictício: {pr['prazo_dias']} dias "
                "da emissão."
            )
            if pr["vencido"]:
                st.error("Prazo vencido. " + txt)
            elif pr["urgente"]:
                st.warning("⏰ Prazo nos próximos 10 dias. " + txt)
            else:
                st.info(txt)
        for a in res.alertas:
            st.error(
                f"🛡️ **Instrução dentro do documento ignorada** (página {a.pagina}, linha {a.linha}): "
                f"“{a.trecho}”. O texto foi retirado antes do modelo e não influenciou as decisões."
            )
        if res.pendencias:
            st.warning(
                f"{len(res.pendencias)} pendência(s) para revisão humana — veja a aba Pendências."
            )

        if res.glosas:
            st.markdown("#### Glosas")
            linhas = st.session_state.get("linhas", {})
            tabela = pd.DataFrame(
                [
                    {
                        "Guia": g.guia,
                        "Procedimento": g.codigo_procedimento,
                        "Glosa": g.codigo_glosa or "—",
                        "Descrição oficial (Tabela 38)": g.descricao_oficial
                        or "não consta na Tabela 38",
                        "Valor glosado": _brl(g.valor_glosado),
                        "Decisão": ROTULO_DECISAO[g.decisao],
                        "Confiança": g.confianca,
                        "Onde": f"página {g.pagina}, linha {g.linha}",
                        "Quem decidiu": "agente" if g.origem == "agente" else "código",
                    }
                    for g in res.glosas
                ]
            )
            st.dataframe(tabela, hide_index=True, width="stretch")
            base = _trechos()
            for g in res.glosas:
                with st.expander(
                    f"{ROTULO_DECISAO[g.decisao]} · guia {g.guia} · glosa {g.codigo_glosa} · {_brl(g.valor_glosado)}"
                ):
                    st.markdown(g.justificativa)
                    trecho_pdf = linhas.get((g.pagina, g.linha))
                    if trecho_pdf:
                        st.caption(
                            f"Evidência no PDF (página {g.pagina}, linha {g.linha}, pseudonimizada):"
                        )
                        st.code(trecho_pdf, language=None)
                    if g.documentos:
                        st.markdown("**Documentos para anexar:** " + "; ".join(g.documentos))
                    for fid in g.fontes:
                        t = base.get(fid)
                        if t:
                            with st.popover(f"📎 {fid}"):
                                st.markdown(t["texto"])
                                st.caption("Fonte: " + t["fonte"])

        if res.recursos:
            st.markdown("#### Rascunhos de recurso")
            st.caption(
                "Cada rascunho passou pelo verificador: valores conferidos, nenhuma norma inventada, nenhum dado "
                "pessoal em claro. Complete os campos [A PREENCHER] e troque o token CART pelo número da carteira."
            )
            for r in res.recursos:
                it = res.itens[r.item]
                with st.expander(
                    f"Recurso — guia {it.guia} · procedimento {it.codigo_procedimento}"
                ):
                    st.code(r.texto, language=None)
                    st.download_button(
                        "Baixar .txt",
                        r.texto.encode("utf-8"),
                        file_name=f"recurso_guia_{it.guia}_{it.codigo_procedimento}.txt",
                        key=f"dl_{res.documento}_{r.item}",
                    )

        with st.expander("Trilha completa do agente"):
            for p in res.trilha:
                st.markdown(_texto_passo(p))
            st.caption(
                f"Modelo {res.modelo} · prompts {res.versoes_prompt} · {res.tokens_entrada:,} tokens de entrada, "
                f"{res.tokens_saida:,} de saída · custo estimado US$ {res.custo_usd:.4f}".replace(
                    ",", "."
                )
            )

# ---------------------------------------------------------------- lote
with aba_lote:
    st.markdown(
        "Analisa os 10 demonstrativos fictícios e mostra o painel consolidado com os prazos."
    )
    if st.button("Analisar todos os exemplos"):
        resultados = []
        for arq in sorted(EXEMPLOS.glob("*.pdf")):
            resultados.append(analisar(arq.read_bytes(), arq.name, modo_demo, st))
        st.session_state["lote"] = resultados
    lote = st.session_state.get("lote")
    if lote:
        pg = painel_geral(lote)
        m = st.columns(4)
        m[0].metric("Total glosado", _brl(pg["total_glosado"]))
        m[1].metric("Recorrível", _brl(pg["recorrivel"]))
        m[2].metric("A classificar", _brl(pg["a_classificar"]))
        m[3].metric("Não recorrível", _brl(pg["nao_recorrivel"]))
        st.markdown("#### Prazos de recurso")
        df = pd.DataFrame(
            [
                {
                    "Documento": p["documento"],
                    "Operadora": p["operadora"],
                    "Prazo final": p["prazo_final"],
                    "Dias restantes": p["dias_restantes"],
                    "Recorrível": _brl(p["recorrivel"]),
                    "Próximos 10 dias": "⏰ sim"
                    if p["urgente"]
                    else ("vencido" if p["vencido"] else ""),
                }
                for p in pg["prazos"]
            ]
        )
        st.dataframe(df, hide_index=True, width="stretch")

# ---------------------------------------------------------------- pendências
with aba_pend:
    fonte = st.session_state.get("lote") or (
        [st.session_state["res"]] if st.session_state.get("res") else []
    )
    linhas = []
    for r in fonte:
        for p in r.pendencias:
            linhas.append(
                {
                    "Documento": r.documento,
                    "Tipo": p.tipo,
                    "Motivo": p.motivo,
                    "Onde": f"p{p.pagina} l{p.linha}"
                    if p.pagina and p.linha
                    else (f"p{p.pagina}" if p.pagina else ""),
                }
            )
        for a in r.alertas:
            linhas.append(
                {
                    "Documento": r.documento,
                    "Tipo": f"alerta: {a.tipo}",
                    "Motivo": f"{a.motivo} “{a.trecho}”",
                    "Onde": f"p{a.pagina} l{a.linha}",
                }
            )
    if linhas:
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    else:
        st.info("Nenhuma pendência. Rode uma análise primeiro.")

# ---------------------------------------------------------------- qualidade
with aba_qualidade:
    sub_dev, sub_val = st.tabs(["Desenvolvimento", "Validação (documentos nunca vistos)"])
    for aba, nome_arq, cmd in (
        (sub_dev, "RESULTADO.md", "python -m agente.avaliar"),
        (sub_val, "VALIDACAO.md", "python -m agente.avaliar --conjunto validacao"),
    ):
        with aba:
            arq = RAIZ / "avaliacao" / nome_arq
            if arq.exists():
                st.markdown(arq.read_text(encoding="utf-8"))
            else:
                st.info(f"Ainda não há avaliação. Rode `{cmd}`.")
