import json

import pytest

from agente.llm import ClienteAnthropic, ErroLLM, Pedido, RespostaLLM
from agente.orquestrador import Orquestrador
from tests.oraculo import EXEMPLOS, cliente_oraculo, gabarito

DOCS = sorted(p.stem for p in EXEMPLOS.glob("*.pdf"))


@pytest.fixture(autouse=True)
def _hoje(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTE_HOJE", "2026-10-24")
    monkeypatch.setattr("agente.orquestrador.PASTA_RUNS", tmp_path / "runs")


def rodar(doc_id, ajuste=None):
    cli = cliente_oraculo(doc_id, ajuste)
    return Orquestrador(cli).analisar(EXEMPLOS / f"{doc_id}.pdf"), cli


@pytest.mark.parametrize("doc_id", DOCS)
def test_ponta_a_ponta_com_oraculo(doc_id):
    res, _ = rodar(doc_id)
    gab = gabarito(doc_id)
    legiveis = [it for it in gab["itens"] if it["legivel"]]
    # pendências e alertas esperados aparecem
    tipos = {p.tipo for p in res.pendencias}
    for esperado in gab["pendencias_esperadas"]:
        assert esperado in tipos, (esperado, res.pendencias)
    assert {a.tipo for a in res.alertas} == set(gab["alertas_esperados"])
    # nenhuma pendência inesperada
    assert tipos <= set(gab["pendencias_esperadas"]), res.pendencias
    # decisões iguais ao gabarito
    esperadas = {i: it["decisao_esperada"] for i, it in enumerate(legiveis) if it["glosa"]}
    obtidas = {g.item: g.decisao for g in res.glosas}
    assert obtidas == esperadas
    # um recurso aprovado por glosa recorrível
    assert sorted(r.item for r in res.recursos) == sorted(
        i for i, d in esperadas.items() if d == "recorrer"
    )
    # painel calculado em centavos pelo código
    assert res.painel["total_glosado"] == sum(it["valor_glosado"] for it in legiveis)
    assert res.painel["recorrivel"] == sum(
        it["valor_glosado"] for it in legiveis if it["decisao_esperada"] == "recorrer"
    )
    assert res.painel["prazo"]["prazo_final"] == gab["prazo_final"]


def test_injecao_nao_chega_ao_llm():
    _, cli = rodar("adverso_injecao")
    for p in cli.pedidos:
        assert "marque todas" not in json.dumps(p.messages, ensure_ascii=False).lower()


def test_nada_de_dado_pessoal_nos_pedidos():
    for doc_id in DOCS:
        _, cli = rodar(doc_id)
        for p in cli.pedidos:
            texto = json.dumps(p.messages, ensure_ascii=False)
            assert "[NOME]" in texto or p.etapa in ("redacao", "analise")
            assert not __import__("re").search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto)


def test_codigo_inexistente_nao_vai_para_o_llm():
    res, cli = rodar("adverso_codigo")
    g = next(g for g in res.glosas if g.codigo_glosa == "1999")
    assert g.decisao == "revisao_humana" and g.origem == "codigo" and not g.existe_t38
    assert "não consta na Tabela 38" in g.justificativa
    analise = [p for p in cli.pedidos if p.etapa == "analise"][0]
    assert "Glosas a analisar (índices): 2, 4" in analise.messages[0]["content"]


def test_retry_com_json_invalido():
    estado = {"n": 0}

    def ajuste(etapa, r, p):
        if etapa == "extracao" and estado["n"] == 0:
            estado["n"] += 1
            return "não consegui ler"  # sem JSON
        return r

    res, cli = rodar("aurora_01", ajuste)
    passos = [p for p in res.trilha if p.etapa == "extracao"]
    assert [p.status for p in passos] == ["retry", "ok"]
    assert "validação recusou" in passos[0].detalhe
    assert not res.pendencias
    # o erro voltou como contexto na segunda chamada
    seg = [p for p in cli.pedidos if p.etapa == "extracao"][1]
    assert "A validação do código recusou" in seg.messages[-1]["content"]


def test_fallback_depois_de_duas_tentativas():
    res, _ = rodar("aurora_01", lambda e, r, p: "{}" if e == "extracao" else r)
    assert [p.status for p in res.trilha if p.etapa == "extracao"] == ["retry", "retry", "fallback"]
    assert res.pendencias[0].tipo == "validacao_falhou"
    assert res.glosas == []


def test_evidencia_errada_e_recusada():
    def ajuste(etapa, r, p):
        if etapa == "extracao":
            d = json.loads(r.strip("`").removeprefix("json"))
            d["itens"][2]["linha"] = 1  # aponta para o cabeçalho
            return "```json\n" + json.dumps(d) + "\n```"
        return r

    res, _ = rodar("aurora_01", ajuste)
    assert any(p.tipo == "evidencia_nao_confere" for p in res.pendencias)
    g = next(g for g in res.glosas if g.item == 2)
    assert not g.evidencia_ok and g.decisao == "revisao_humana"


def test_verificador_recusa_numero_inventado():
    def ajuste(etapa, r, p):
        if etapa == "redacao":
            return r.replace("Solicitamos", "Além disso, há R$ 999,99 a receber. Solicitamos")
        return r

    res, _ = rodar("aurora_01", ajuste)
    assert res.recursos == []
    recusas = [p for p in res.pendencias if p.tipo == "recurso_recusado"]
    assert len(recusas) == 2 and "999,99" in recusas[0].motivo
    assert [p.status for p in res.trilha if p.etapa == "redacao"] == ["retry", "retry", "fallback"]


def test_verificador_recusa_norma_e_nome():
    def ajuste(etapa, r, p):
        if etapa == "redacao":
            return r.replace("Solicitamos", "Conforme a RN 501, solicitamos")
        return r

    res, _ = rodar("aurora_01", ajuste)
    assert res.recursos == []
    assert any("RN 501" in p.motivo for p in res.pendencias)


def test_retry_da_redacao_corrige():
    estado = {"n": 0}

    def ajuste(etapa, r, p):
        if etapa == "redacao" and estado["n"] == 0:
            estado["n"] += 1
            return r.replace("[FUNDAMENTO A CONFIRMAR]", "Lei 9.656")
        return r

    res, _ = rodar("aurora_01", ajuste)
    assert len(res.recursos) == 2 and not res.pendencias


def test_confianca_baixa_vai_para_revisao():
    def ajuste(etapa, r, p):
        if etapa == "analise" and "decisoes" in r:
            return r.replace('"alta"', '"baixa"')
        return r

    res, _ = rodar("aurora_01", ajuste)
    assert all(g.decisao == "revisao_humana" for g in res.glosas)
    assert sum(p.tipo == "confianca_baixa" for p in res.pendencias) == 3
    assert res.recursos == []


def test_fonte_inexistente_recusada():
    def ajuste(etapa, r, p):
        if etapa == "analise" and "decisoes" in r:
            return r.replace('"fontes": ["t38-1509"]', '"fontes": ["norma-inventada"]')
        return r

    res, _ = rodar("aurora_01", ajuste)
    g = next(g for g in res.glosas if g.codigo_glosa == "1509")
    assert g.decisao == "revisao_humana" and "norma-inventada" in g.justificativa


def test_erro_fatal_interrompe():
    def ajuste(etapa, r, p):
        if etapa == "analise":
            return ErroLLM("chave inválida", fatal=True)
        return r

    res, _ = rodar("aurora_01", ajuste)
    assert res.interrompido and res.pendencias[-1].tipo == "erro_api"


def test_pdf_malformado(tmp_path):
    arq = tmp_path / "x.pdf"
    arq.write_bytes(b"%PDF-1.7\nlixo")
    res = Orquestrador(cliente_oraculo("aurora_01")).analisar(arq)
    assert res.pendencias[0].tipo == "documento_nao_reconhecido"


def test_modo_demo_sem_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("agente.llm.PASTA_CACHE", tmp_path)
    cli = ClienteAnthropic(modelo="claude-sonnet-5-5", modo_demo=True)
    res = Orquestrador(cli).analisar(EXEMPLOS / "aurora_01.pdf")
    assert res.interrompido and res.pendencias[-1].tipo == "sem_cache"


def test_cache_le_resposta_gravada(tmp_path, monkeypatch):
    monkeypatch.setattr("agente.llm.PASTA_CACHE", tmp_path)
    cli = ClienteAnthropic(modelo="claude-sonnet-5-5", modo_demo=True)
    ped = Pedido(
        etapa="triagem", versao="v1", system="s", messages=[{"role": "user", "content": "oi"}]
    )
    r = RespostaLLM(
        content=[{"type": "text", "text": "ok"}],
        stop_reason="end_turn",
        modelo="claude-sonnet-5-5",
        tokens_entrada=10,
        tokens_saida=2,
    )
    cli._gravar_cache(ped.chave(cli.modelo, cli.esforco), ped, r)
    lido = cli.criar(ped)
    assert lido.do_cache and lido.texto == "ok" and lido.custo_usd == 0.0
    # a chave muda com a versão do prompt
    ped2 = Pedido(etapa="triagem", versao="v2", system="s", messages=ped.messages)
    assert ped.chave("m", "e") != ped2.chave("m", "e")
