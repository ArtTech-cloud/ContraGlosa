"""Definições das ferramentas que o LLM pode chamar, e o executor."""

from __future__ import annotations

import json

from agente.ferramentas.base import buscar_base
from agente.ferramentas.basicas import consultar_operadora, consultar_t38, intervalo_dias


def _schema(props: dict, req: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": req, "additionalProperties": False}


FERRAMENTAS_ANALISE = [
    {
        "name": "consultar_t38",
        "description": (
            "Consulta um código de glosa na Tabela 38 oficial da ANS (Padrão TISS 202609). Diz se o código existe, "
            "traz a descrição oficial e o critério de recorribilidade de demonstração (id da base: t38-<código>)."
        ),
        "strict": True,
        "input_schema": _schema(
            {"codigo": {"type": "string", "description": "4 dígitos"}}, ["codigo"]
        ),
    },
    {
        "name": "consultar_operadora",
        "description": (
            "Parâmetros fictícios de uma operadora: prazo de recurso em dias, valor contratado da consulta 10101012 "
            "e intervalo de retorno em dias (id da base: op-<apelido>)."
        ),
        "strict": True,
        "input_schema": _schema({"nome": {"type": "string"}}, ["nome"]),
    },
    {
        "name": "calcular_intervalo",
        "description": "Número de dias corridos entre duas datas no formato dd/mm/aaaa (data_fim − data_inicio).",
        "strict": True,
        "input_schema": _schema(
            {"data_inicio": {"type": "string"}, "data_fim": {"type": "string"}},
            ["data_inicio", "data_fim"],
        ),
    },
    {
        "name": "buscar_base",
        "description": (
            "Busca trechos na base de conhecimento (conceitos do Padrão TISS, notas de domínio, códigos e "
            "operadoras). Cada trecho tem um id que deve ser citado em 'fontes'."
        ),
        "strict": True,
        "input_schema": _schema(
            {"consulta": {"type": "string"}, "k": {"type": "integer", "description": "1 a 8"}},
            ["consulta", "k"],
        ),
    },
]


def executar(nome: str, args: dict) -> tuple[str, list[str]]:
    """Roda a ferramenta. Devolve (resultado em JSON, ids da base que o resultado tornou citáveis)."""
    try:
        if nome == "consultar_t38":
            r = consultar_t38(str(args.get("codigo", "")))
            ids = [f"t38-{r['codigo']}"] if r.get("classificacao_demo") else []
        elif nome == "consultar_operadora":
            r = consultar_operadora(str(args.get("nome", "")))
            ids = [r["fonte_id"]] if r.get("encontrada") else []
        elif nome == "calcular_intervalo":
            r = intervalo_dias(str(args.get("data_inicio", "")), str(args.get("data_fim", "")))
            ids = []
        elif nome == "buscar_base":
            r = buscar_base(str(args.get("consulta", "")), int(args.get("k", 4) or 4))
            ids = [t["id"] for t in r]
        else:
            return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}), []
    except (ValueError, TypeError) as e:
        return json.dumps({"erro": f"argumentos inválidos: {e}"}, ensure_ascii=False), []
    return json.dumps(r, ensure_ascii=False), ids
