import pytest

from agente.dinheiro import ValorInvalido, format_brl, parse_brl, valores_no_texto


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("R$ 1.234,56", 123456),
        ("1.234,56", 123456),
        ("135,00", 13500),
        ("135", 13500),
        ("0,05", 5),
        ("0,5", 50),
        ("-15,00", -1500),
        ("R$ -15,00", -1500),
        ("R$ 1.000.000,01", 100000001),
        ("  42,10 ", 4210),
    ],
)
def test_parse_brl(texto, esperado):
    assert parse_brl(texto) == esperado
    assert isinstance(parse_brl(texto), int)


@pytest.mark.parametrize(
    "texto", ["1,234.56", "12.5", "abc", "", "1.23,45", "R$", "1,234", "12,345"]
)
def test_parse_brl_recusa_formato_errado(texto):
    with pytest.raises(ValorInvalido):
        parse_brl(texto)


def test_parse_brl_recusa_float():
    with pytest.raises(ValorInvalido):
        parse_brl(12.5)  # type: ignore[arg-type]


def test_format_brl():
    assert format_brl(123456) == "R$ 1.234,56"
    assert format_brl(5) == "R$ 0,05"
    assert format_brl(-1500) == "R$ -15,00"
    assert format_brl(100000001, simbolo=False) == "1.000.000,01"


def test_format_recusa_float():
    with pytest.raises(TypeError):
        format_brl(12.5)  # type: ignore[arg-type]


def test_ida_e_volta():
    for c in [0, 1, 99, 100, 13500, 987654321]:
        assert parse_brl(format_brl(c)) == c


def test_valores_no_texto():
    assert valores_no_texto("Glosado R$ 15,00 de 135,00; protocolo 123456") == [1500, 13500]
