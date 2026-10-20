"""Carrega as tabelas oficiais, a classificação de demonstração e as operadoras fictícias."""

from __future__ import annotations

import csv
import functools
import unicodedata
from pathlib import Path

import yaml

from agente.dinheiro import parse_brl

RAIZ = Path(__file__).resolve().parents[2]


@functools.cache
def tabela38() -> dict[str, dict]:
    with open(RAIZ / "dados" / "tabela38" / "tabela38.csv", encoding="utf-8") as f:
        return {r["codigo"]: r for r in csv.DictReader(f)}


@functools.cache
def tabela22() -> dict[str, dict]:
    with open(RAIZ / "dados" / "tabela22" / "tabela22.csv", encoding="utf-8") as f:
        return {r["codigo"]: r for r in csv.DictReader(f)}


@functools.cache
def classificacao() -> dict[str, dict]:
    with open(RAIZ / "base" / "classificacao_demo.yaml", encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    return {c["codigo"]: c for c in dados["codigos"]}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


@functools.cache
def operadoras() -> list[dict]:
    with open(RAIZ / "dados" / "operadoras.yaml", encoding="utf-8") as f:
        ops = yaml.safe_load(f)["operadoras"]
    for o in ops:
        o["valor_consulta_centavos"] = parse_brl(o["valor_consulta"])
    return ops


def achar_operadora(nome: str | None) -> dict | None:
    """Acha a operadora fictícia pelo nome ou apelido ("Operadora Aurora", "AURORA", "Boreal")."""
    if not nome:
        return None
    n = _norm(nome)
    for o in operadoras():
        if o["apelido"] in n or _norm(o["nome"]) in n:
            return o
    return None
