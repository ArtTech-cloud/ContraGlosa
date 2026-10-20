import datetime as dt
import json
import re
from pathlib import Path

from agente.ferramentas.base import buscar_base, ids_validos, trechos
from agente.ferramentas.basicas import (
    conferir_soma,
    consultar_operadora,
    consultar_t38,
    intervalo_dias,
    prazo_recurso,
)
from agente.ferramentas.dados_ref import classificacao, tabela22, tabela38
from agente.ferramentas.registro import FERRAMENTAS_ANALISE, executar
from agente.ferramentas.verificadores import verificar_recurso
from agente.modelos import ItemExtraido, TotaisImpressos

RAIZ = Path(__file__).resolve().parents[1]


def _it(ap, gl, pg, **kw):
    d = dict(
        pagina=1,
        linha=1,
        guia="123456789",
        data_atendimento="01/09/2026",
        beneficiario="CART-1",
        codigo_procedimento="10101012",
        valor_apresentado=ap,
        valor_glosado=gl,
        valor_pago=pg,
        codigo_glosa="1509",
    )
    d.update(kw)
    return ItemExtraido(**d)


# ---------------------------------------------------------------- dados oficiais


def test_todo_codigo_dos_dados_ficticios_esta_na_tabela_oficial():
    t38, t22 = tabela38(), tabela22()
    for g in sorted((RAIZ / "dados" / "exemplos" / "gabarito").glob("*.json")):
        gab = json.loads(g.read_text(encoding="utf-8"))
        for it in gab["itens"]:
            assert it["codigo_procedimento"] in t22
            if it["codigo_glosa"]:
                if (
                    gab["adverso"] == "codigo_inexistente"
                    and it["decisao_esperada"] == "revisao_humana"
                ):
                    assert (
                        it["codigo_glosa"] not in t38
                    )  # o inexistente tem de continuar inexistente
                else:
                    assert it["codigo_glosa"] in t38


def test_classificacao_usa_descricao_oficial():
    t38 = tabela38()
    for cod, c in classificacao().items():
        assert c["descricao_oficial"] == t38[cod]["descricao"]
        assert c["recorribilidade"] in {"sim", "nao", "depende"}
        assert c["grupo"] in {
            "elegibilidade",
            "autorizacao",
            "retorno",
            "duplicidade",
            "valor",
            "prazo",
            "preenchimento",
            "outro",
        }


def test_fonte_da_tabela_registrada():
    f = json.loads((RAIZ / "dados" / "tabela38" / "fonte.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{64}", f["sha256_zip"])
    assert f["url"].startswith("https://www.ans.gov.br/")
    assert len(tabela38()) == f["total_codigos"]


# ---------------------------------------------------------------- conferir_soma


def test_conferir_soma_ok():
    itens = [_it("135,00", "15,00", "120,00"), _it("18,50", "0,00", "18,50")]
    r = conferir_soma(
        itens,
        TotaisImpressos(valor_apresentado="153,50", valor_glosado="15,00", valor_pago="138,50"),
    )
    assert r.ok


def test_conferir_soma_divergente():
    itens = [_it("135,00", "15,00", "120,00")]
    r = conferir_soma(
        itens,
        TotaisImpressos(valor_apresentado="235,00", valor_glosado="15,00", valor_pago="120,00"),
    )
    assert not r.ok and r.diferencas == {"valor_apresentado": (13500, 23500)}
    assert "R$ 100,00" in r.resumo()


def test_conferir_soma_linha_inconsistente():
    r = conferir_soma(
        [_it("135,00", "15,00", "121,00")], TotaisImpressos(valor_apresentado="135,00")
    )
    assert not r.ok and r.itens_inconsistentes == [0]


def test_conferir_soma_sem_totais():
    r = conferir_soma([_it("1,00", "0,00", "1,00")], None)
    assert not r.ok and r.sem_totais


# ---------------------------------------------------------------- consultar_t38


def test_consultar_t38():
    r = consultar_t38("1509")
    assert r["existe"] and r["descricao_oficial"] == "CÓDIGO CID INVÁLIDO"
    assert r["classificacao_demo"]["recorribilidade"] == "sim"
    r = consultar_t38("1999")
    assert not r["existe"] and "descricao_oficial" not in r


# ---------------------------------------------------------------- prazos e operadoras


def test_prazo_recurso():
    r = prazo_recurso("01/10/2026", "OPERADORA AURORA", ref=dt.date(2026, 10, 24))
    assert r["prazo_final"] == "31/10/2026" and r["dias_restantes"] == 7 and r["urgente"]
    r = prazo_recurso("01/10/2026", "Operadora Real S.A.")
    assert not r["ok"]


def test_intervalo_e_operadora():
    assert intervalo_dias("04/08/2026", "14/09/2026")["dias"] == 41
    op = consultar_operadora("Boreal")
    assert op["dias_retorno"] == 20 and op["fonte_id"] == "op-boreal"


# ---------------------------------------------------------------- base


def test_base_tem_fonte_em_cada_trecho():
    for t in trechos():
        assert t.fonte and t.texto
    assert {"t38-1509", "op-aurora", "nota-retorno", "tiss-recurso-processo"} <= ids_validos()


def test_buscar_base():
    ids = [r["id"] for r in buscar_base("glosa duplicidade mesma guia mesma data", 3)]
    assert "nota-duplicidade" in ids
    assert buscar_base("", 3) == []


def test_registro_de_ferramentas():
    nomes = {f["name"] for f in FERRAMENTAS_ANALISE}
    assert nomes == {"consultar_t38", "consultar_operadora", "calcular_intervalo", "buscar_base"}
    saida, ids = executar("consultar_t38", {"codigo": "1823"})
    assert json.loads(saida)["existe"] and ids == ["t38-1823"]
    saida, ids = executar("inexistente", {})
    assert "erro" in json.loads(saida)


# ---------------------------------------------------------------- verificar_recurso

BOM = (
    "Recurso de glosa — guia 123456789\nProcedimento 10101012, glosa 1509. Valor glosado R$ 15,00.\n"
    "Fundamento normativo: [FUNDAMENTO A CONFIRMAR]\nProtocolo do recurso: [A PREENCHER]\n"
    "Assinatura do responsável: [A PREENCHER]\n"
)


def test_verificar_recurso_aprova():
    v = verificar_recurso(BOM, _it("135,00", "15,00", "120,00"), {13500, 1500, 12000})
    assert v.ok, v.erros


def test_verificar_recurso_recusa():
    it = _it("135,00", "15,00", "120,00")
    casos = {
        "valor": BOM.replace("R$ 15,00", "R$ 16,00"),
        "norma": BOM.replace("[FUNDAMENTO A CONFIRMAR]", "art. 5º da Lei 9.656"),
        "protocolo": BOM.replace("Protocolo do recurso: [A PREENCHER]", "Protocolo 1"),
        "cpf": BOM + "CPF 123.456.789-00",
        "carteira": BOM + "Carteira 4038 0815 8895 6822",
        "nome": BOM + "Paciente MARIA S COSTA",
        "codigo": BOM + "Ver também glosa 1999.",
        "guia": BOM.replace("123456789", "999"),
    }
    for nome, texto in casos.items():
        v = verificar_recurso(texto, it, {13500, 1500, 12000}, nomes={"MARIA S COSTA"})
        assert not v.ok, nome
