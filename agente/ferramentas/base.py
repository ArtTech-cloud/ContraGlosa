"""buscar_base: BM25 local sobre base/*.md. Cada trecho tem id e fonte.

Os trechos de códigos (t38-XXXX) e de operadoras (op-xxx) são gerados a partir da
Tabela 38 oficial, da classificação de demonstração e de dados/operadoras.yaml, para
nunca divergirem dessas fontes.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from agente.ferramentas.dados_ref import classificacao, operadoras, tabela38

PASTA_BASE = Path(__file__).resolve().parents[2] / "base"
RE_TRECHO = re.compile(r"^## \[id: ([a-z0-9-]+)\]\s*$", re.MULTILINE)
STOP = set(
    "a o e de da do das dos em no na nos nas um uma para por com sem que se ao aos ou os as "
    "é ser são foi como mais menos the of".split()
)


@dataclass(frozen=True)
class Trecho:
    id: str
    fonte: str
    texto: str
    arquivo: str


def _tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return [t for t in re.findall(r"[a-z0-9]+", s) if t not in STOP and len(t) > 1]


def gerar_markdown_derivado() -> None:
    """Grava base/codigos_t38.md e base/operadoras.md a partir das fontes de dados."""
    t38 = tabela38()
    linhas = [
        "# Códigos da Tabela 38 usados na demonstração",
        "",
        "Gerado por `agente.ferramentas.base.gerar_markdown_derivado`. A descrição é a oficial; a classificação é",
        "DEMONSTRAÇÃO — proposta da equipe, a validar com especialista.",
        "",
    ]
    for cod, c in sorted(classificacao().items()):
        linhas += [
            f"## [id: t38-{cod}]",
            "fonte: Tabela 38, Padrão TISS 202609 (ANS), descrição oficial; classificação de demonstração "
            "da equipe (base/classificacao_demo.yaml).",
            f'Código {cod}: "{t38[cod]["descricao"]}". Grupo: {c["grupo"]}. Recorribilidade padrão: '
            f"{c['recorribilidade']}. Documentos típicos: {', '.join(c['documentos_tipicos']) or 'nenhum'}. "
            f"{c['justificativa']}",
            "",
        ]
    (PASTA_BASE / "codigos_t38.md").write_text("\n".join(linhas), encoding="utf-8", newline="\n")
    linhas = [
        "# Operadoras fictícias",
        "",
        "Gerado a partir de `dados/operadoras.yaml`. PARÂMETROS FICTÍCIOS de demonstração.",
        "",
    ]
    for o in operadoras():
        linhas += [
            f"## [id: op-{o['apelido']}]",
            "fonte: dados/operadoras.yaml (parâmetros fictícios criados pela equipe).",
            f"{o['nome']} (fictícia). Prazo de recurso de glosa: {o['prazo_recurso_dias']} dias corridos a partir "
            f"da emissão do demonstrativo. Valor contratado da consulta (10101012): R$ {o['valor_consulta']}. "
            f"Intervalo de retorno de consulta: {o['dias_retorno']} dias.",
            "",
        ]
    (PASTA_BASE / "operadoras.md").write_text("\n".join(linhas), encoding="utf-8", newline="\n")


@functools.cache
def trechos() -> tuple[Trecho, ...]:
    out: list[Trecho] = []
    for arq in sorted(PASTA_BASE.glob("*.md")):
        txt = arq.read_text(encoding="utf-8")
        partes = RE_TRECHO.split(txt)
        # partes = [preâmbulo, id1, corpo1, id2, corpo2, ...]
        for i in range(1, len(partes), 2):
            tid, corpo = partes[i], partes[i + 1].strip()
            fonte, _, texto = corpo.partition("\n")
            if not fonte.startswith("fonte:"):
                raise ValueError(f"trecho {tid} em {arq.name} sem linha 'fonte:'")
            out.append(
                Trecho(tid, fonte.removeprefix("fonte:").strip(), " ".join(texto.split()), arq.name)
            )
    ids = [t.id for t in out]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de trecho repetidos na base")
    return tuple(out)


@functools.cache
def _indice() -> BM25Okapi:
    return BM25Okapi([_tokens(t.id.replace("-", " ") + " " + t.texto) for t in trechos()])


def ids_validos() -> set[str]:
    return {t.id for t in trechos()}


def buscar_base(consulta: str, k: int = 4) -> list[dict]:
    """Os k trechos mais parecidos com a consulta, com id, fonte e texto."""
    k = max(1, min(int(k), 8))
    tks = _tokens(consulta)
    ts = trechos()
    if not tks:
        return []
    notas = _indice().get_scores(tks)
    ordem = sorted(range(len(ts)), key=lambda i: notas[i], reverse=True)[:k]
    return [
        {"id": ts[i].id, "fonte": ts[i].fonte, "texto": ts[i].texto} for i in ordem if notas[i] > 0
    ]
