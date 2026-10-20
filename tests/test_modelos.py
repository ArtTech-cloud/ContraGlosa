import pytest
from pydantic import ValidationError

from agente.modelos import DecisaoGlosa, ItemExtraido, parse_data


def _item(**kw):
    base = dict(
        pagina=1,
        linha=10,
        guia="123456789",
        data_atendimento="05/09/2026",
        beneficiario="CART-ab12cd34",
        codigo_procedimento="10101012",
        valor_apresentado="135,00",
        valor_glosado="15,00",
        valor_pago="120,00",
        codigo_glosa="1705",
    )
    base.update(kw)
    return ItemExtraido(**base)


def test_item_converte_para_centavos():
    it = _item()
    assert (it.apresentado, it.glosado, it.pago) == (13500, 1500, 12000)
    assert it.tem_glosa


def test_item_recusa_valor_com_ponto_decimal():
    with pytest.raises(ValidationError):
        _item(valor_glosado="15.00")


def test_item_recusa_codigo_glosa_errado():
    with pytest.raises(ValidationError):
        _item(codigo_glosa="17A5")


def test_item_recusa_campo_extra():
    with pytest.raises(ValidationError):
        _item(inventado="x")


def test_item_sem_glosa():
    it = _item(valor_glosado="0,00", valor_pago="135,00", codigo_glosa="")
    assert it.codigo_glosa is None and not it.tem_glosa


def test_decisao_enum():
    with pytest.raises(ValidationError):
        DecisaoGlosa(item=0, decisao="talvez", confianca="alta", justificativa="xxxxxxxxxxxx")


def test_parse_data():
    assert parse_data("05/09/2026").isoformat() == "2026-09-05"
    assert parse_data("2026-09-05").isoformat() == "2026-09-05"
