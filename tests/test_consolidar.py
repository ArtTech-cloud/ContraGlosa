import pytest

from agente.consolidar import agenda, campos_a_preencher, glosas_priorizadas, semaforo
from agente.orquestrador import Orquestrador
from tests.oraculo import EXEMPLOS, cliente_oraculo


@pytest.fixture(autouse=True)
def _hoje(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTE_HOJE", "2026-10-24")
    monkeypatch.setattr("agente.orquestrador.PASTA_RUNS", tmp_path / "runs")


def rodar(doc_id):
    return Orquestrador(cliente_oraculo(doc_id)).analisar(EXEMPLOS / f"{doc_id}.pdf")


def test_semaforo_pronto_quando_tudo_confere():
    res = rodar("boreal_01")
    assert {semaforo(g, res)[0] for g in res.glosas} == {"pronto"}


def test_semaforo_revisao_quando_o_agente_nao_decide():
    res = rodar("adverso_codigo")
    cores = {g.codigo_glosa: semaforo(g, res) for g in res.glosas}
    assert any(cor == "revisao" and "Tabela 38" in motivo for cor, motivo in cores.values())


def test_semaforo_confira_com_confianca_media_ou_recurso_retido():
    res = rodar("boreal_01")
    g = next(g for g in res.glosas if g.decisao == "recorrer")
    assert semaforo(g.model_copy(update={"confianca": "media"}), res)[0] == "confira"
    sem_recurso = res.model_copy(update={"recursos": []})
    cor, motivo = semaforo(g, sem_recurso)
    assert cor == "confira" and "verificador" in motivo


def test_prioridade_maior_valor_primeiro():
    res = rodar("boreal_01")
    valores = [g.valor_glosado for g in glosas_priorizadas(res)]
    assert valores == sorted(valores, reverse=True)


def test_agenda_so_tem_recorriveis_em_ordem_de_vencimento():
    resultados = [rodar(d) for d in ("aurora_01", "boreal_01", "cerrado_01")]
    linhas = agenda(resultados)
    n_recorrer = sum(g.decisao == "recorrer" for r in resultados for g in r.glosas)
    assert len(linhas) == n_recorrer
    chaves = [(x["dias_restantes"], -x["valor"]) for x in linhas]
    assert chaves == sorted(chaves)


def test_campos_a_preencher():
    texto = (
        "Fundamento normativo: [FUNDAMENTO A CONFIRMAR]\n"
        "Protocolo do recurso: [A PREENCHER]\n"
        "Assinatura do responsável: [A PREENCHER]\n"
    )
    assert campos_a_preencher(texto) == (
        ["Protocolo do recurso", "Assinatura do responsável"],
        ["Fundamento normativo"],
    )


def test_resultado_parcial_visivel_durante_a_analise():
    vistos = []
    orq = Orquestrador(cliente_oraculo("boreal_01"))
    orq.ao_passo = lambda p: vistos.append((p.etapa, len(orq.resultado.itens)))
    res = orq.analisar(EXEMPLOS / "boreal_01.pdf")
    assert orq.resultado is res
    # depois da conferência da soma, os itens já estão no resultado em construção
    assert dict(vistos)["consultar_t38"] == len(res.itens)
