"""conferir_soma, consultar_t38, calcular_prazo e consultar_operadora."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

from agente.dinheiro import format_brl, parse_brl
from agente.ferramentas.dados_ref import achar_operadora, classificacao, tabela38
from agente.modelos import ItemExtraido, TotaisImpressos, parse_data

DIAS_URGENTE = 10


def hoje() -> dt.date:
    """Data de referência. AGENTE_HOJE=aaaa-mm-dd fixa a data (útil para a demo e os testes)."""
    v = os.getenv("AGENTE_HOJE")
    return dt.date.fromisoformat(v) if v else dt.date.today()


# ------------------------------------------------------------------ conferir_soma


@dataclass
class ResultadoSoma:
    ok: bool
    diferencas: dict[str, tuple[int, int]] = field(
        default_factory=dict
    )  # campo -> (soma, impresso)
    itens_inconsistentes: list[int] = field(default_factory=list)
    sem_totais: bool = False

    def resumo(self) -> str:
        if self.sem_totais:
            return "totais impressos não encontrados; soma não conferida"
        partes = []
        for campo, (soma, impresso) in self.diferencas.items():
            partes.append(
                f"{campo}: soma das linhas {format_brl(soma)} × impresso {format_brl(impresso)} "
                f"(diferença {format_brl(impresso - soma)})"
            )
        for i in self.itens_inconsistentes:
            partes.append(f"item {i}: apresentado − glosado ≠ pago")
        return "; ".join(partes) if partes else "soma das linhas confere com os totais impressos"


def conferir_soma(itens: list[ItemExtraido], totais: TotaisImpressos | None) -> ResultadoSoma:
    """Confere, em centavos, a soma das linhas com os totais impressos e cada linha consigo mesma."""
    res = ResultadoSoma(ok=True)
    for i, it in enumerate(itens):
        if it.apresentado - it.glosado != it.pago:
            res.itens_inconsistentes.append(i)
    campos = {
        "valor_apresentado": sum(it.apresentado for it in itens),
        "valor_glosado": sum(it.glosado for it in itens),
        "valor_pago": sum(it.pago for it in itens),
    }
    impressos = {c: parse_brl(getattr(totais, c)) for c in campos if totais and getattr(totais, c)}
    if not impressos:
        res.sem_totais = True
    for c, impresso in impressos.items():
        if campos[c] != impresso:
            res.diferencas[c] = (campos[c], impresso)
    res.ok = not res.diferencas and not res.itens_inconsistentes and not res.sem_totais
    return res


# ------------------------------------------------------------------ consultar_t38


def consultar_t38(codigo: str) -> dict:
    """Existe na Tabela 38 oficial? Devolve a descrição oficial e a classificação de demonstração."""
    cod = (codigo or "").strip()
    reg = tabela38().get(cod)
    if not reg:
        return {
            "codigo": cod,
            "existe": False,
            "mensagem": "código não consta na Tabela 38 oficial (Padrão TISS 202609). "
            "Não presuma o significado.",
        }
    out = {
        "codigo": cod,
        "existe": True,
        "descricao_oficial": reg["descricao"],
        "fonte": "Tabela 38, Padrão TISS 202609 (ANS)",
    }
    cl = classificacao().get(cod)
    if cl:
        out["classificacao_demo"] = {
            "aviso": "DEMONSTRAÇÃO — proposta da equipe, a validar com especialista",
            "grupo": cl["grupo"],
            "recorribilidade": cl["recorribilidade"],
            "documentos_tipicos": cl["documentos_tipicos"],
            "criterio": cl["justificativa"],
        }
    else:
        out["classificacao_demo"] = None
    return out


# ------------------------------------------------------------------ calcular_prazo


def prazo_recurso(
    data_emissao: str | dt.date, operadora: str | None, ref: dt.date | None = None
) -> dict:
    """Prazo final do recurso: emissão + dias da operadora (parâmetro fictício)."""
    op = achar_operadora(operadora)
    if op is None:
        return {
            "ok": False,
            "mensagem": f"operadora '{operadora}' sem parâmetro de prazo cadastrado",
        }
    emissao = parse_data(data_emissao) if isinstance(data_emissao, str) else data_emissao
    final = emissao + dt.timedelta(days=op["prazo_recurso_dias"])
    ref = ref or hoje()
    restantes = (final - ref).days
    return {
        "ok": True,
        "operadora": op["nome"],
        "data_emissao": emissao.strftime("%d/%m/%Y"),
        "prazo_dias": op["prazo_recurso_dias"],
        "prazo_final": final.strftime("%d/%m/%Y"),
        "dias_restantes": restantes,
        "vencido": restantes < 0,
        "urgente": 0 <= restantes <= DIAS_URGENTE,
        "parametro_ficticio": True,
    }


def intervalo_dias(data_inicio: str, data_fim: str) -> dict:
    a, b = parse_data(data_inicio), parse_data(data_fim)
    return {"data_inicio": data_inicio, "data_fim": data_fim, "dias": (b - a).days}


def calcular_prazo(tipo: str, **kw) -> dict:
    """Ferramenta para o LLM: tipo 'recurso' (data_emissao, operadora) ou 'intervalo' (data_inicio, data_fim)."""
    try:
        if tipo == "recurso":
            return prazo_recurso(kw["data_emissao"], kw.get("operadora"))
        if tipo == "intervalo":
            return intervalo_dias(kw["data_inicio"], kw["data_fim"])
    except (KeyError, ValueError) as e:
        return {"ok": False, "mensagem": f"argumentos inválidos: {e}"}
    return {"ok": False, "mensagem": "tipo deve ser 'recurso' ou 'intervalo'"}


# ------------------------------------------------------------------ consultar_operadora


def consultar_operadora(nome: str) -> dict:
    op = achar_operadora(nome)
    if op is None:
        return {"encontrada": False, "mensagem": f"operadora '{nome}' não cadastrada"}
    return {
        "encontrada": True,
        "nome": op["nome"],
        "prazo_recurso_dias": op["prazo_recurso_dias"],
        "valor_consulta_contratado": op["valor_consulta"],
        "dias_retorno": op["dias_retorno"],
        "aviso": "parâmetros fictícios de demonstração",
        "fonte_id": f"op-{op['apelido']}",
    }
