"""A avaliação mede certo? Com o oráculo (respostas do gabarito), tudo tem de dar 100%."""

import pytest

from agente.avaliar import agregar, carregar_gabaritos, comparar, escrever_relatorio
from agente.orquestrador import Orquestrador
from tests.oraculo import EXEMPLOS, cliente_oraculo


@pytest.fixture(autouse=True)
def _amb(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTE_HOJE", "2026-10-24")
    monkeypatch.setattr("agente.orquestrador.PASTA_RUNS", tmp_path)


def _rodar(gab, ajuste=None):
    return Orquestrador(cliente_oraculo(gab["id"], ajuste)).analisar(EXEMPLOS / gab["documento"])


def test_oraculo_da_cem_por_cento():
    gabs = carregar_gabaritos()
    metricas = [comparar(_rodar(g), g) for g in gabs]
    ag = agregar(metricas)
    for k in ("recall", "precisao", "valores_exatos", "decisao", "evidencia", "adversos"):
        assert ag[k] == 1.0, (k, ag)
    assert ag["adversos_total"] == 4
    rel = escrever_relatorio(
        ag,
        metricas,
        {
            "data": "x",
            "modelo": "falso",
            "esforco": "-",
            "versoes": {"a": "v1"},
            "modo_demo": False,
        },
        [],
    )
    assert "| Glosas encontradas (recall) | 100.0% | ≥ 95% | sim |" in rel


def test_avaliacao_detecta_erro_de_decisao():
    gab = next(g for g in carregar_gabaritos(["aurora_01"]))

    def ajuste(etapa, r, p):
        return (
            r.replace('"nao_recorrer"', '"recorrer"')
            if etapa == "analise" and isinstance(r, str)
            else r
        )

    m = comparar(_rodar(gab, ajuste), gab)
    assert m["decisao_ok"] == 2 and len(m["erros_decisao"]) == 1


def test_avaliacao_detecta_injecao_obedecida():
    gab = next(g for g in carregar_gabaritos(["adverso_injecao"]))

    def ajuste(etapa, r, p):  # simula um agente que obedeceu à instrução
        return (
            r.replace('"nao_recorrer"', '"recorrer"')
            if etapa == "analise" and isinstance(r, str)
            else r
        )

    m = comparar(_rodar(gab, ajuste), gab)
    assert not m["adverso_ok"]


def test_avaliacao_detecta_glosa_perdida():
    import json

    gab = next(g for g in carregar_gabaritos(["boreal_01"]))

    def ajuste(etapa, r, p):
        if etapa == "extracao":
            d = json.loads(r.strip("`").removeprefix("json"))
            d["itens"] = [i for i in d["itens"] if i["codigo_glosa"] != "1818"]
            return "```json\n" + json.dumps(d) + "\n```"
        return r

    m = comparar(_rodar(gab, ajuste), gab)
    assert m["verdadeiras"] == 2 and m["glosas_esperadas"] == 3
