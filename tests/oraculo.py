"""Cliente falso que responde a partir do gabarito. SÓ PARA TESTES.

Serve para provar que o encanamento (orquestrador, verificadores, painel, avaliação) funciona sem
gastar API. Não mede a qualidade do agente: quem responde aqui é o gabarito.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from agente.dinheiro import format_brl
from agente.llm import ClienteFalso, Pedido

EXEMPLOS = Path(__file__).resolve().parents[1] / "dados" / "exemplos"


VALIDACAO = EXEMPLOS.parent / "validacao"


def pasta_de(doc_id: str) -> Path:
    """Pasta do documento: validação (dados/validacao) ou desenvolvimento (dados/exemplos)."""
    return VALIDACAO if doc_id.startswith("validacao_") else EXEMPLOS


def gabarito(doc_id: str) -> dict:
    return json.loads(
        (pasta_de(doc_id) / "gabarito" / f"{doc_id}.json").read_text(encoding="utf-8")
    )


def _v(c: int) -> str:
    return format_brl(c, simbolo=False)


def _json(obj) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False) + "\n```"


def _linhas_do_prompt(texto: str) -> dict[tuple[int, int], str]:
    out = {}
    for m in re.finditer(r"^\[p(\d+) l(\d+)\] (.*)$", texto, re.MULTILINE):
        out[(int(m.group(1)), int(m.group(2)))] = m.group(3)
    return out


def _token(linhas: dict, pagina: int, linha: int) -> str:
    for k in range(0, 5):
        t = linhas.get((pagina, linha - k), "")
        m = re.search(r"CART-[0-9a-f]{8}", t)
        if m:
            return m.group(0)
    return "CART-00000000"


def itens_extraidos(gab: dict, prompt: str) -> list[dict]:
    linhas = _linhas_do_prompt(prompt)
    out = []
    for it in gab["itens"]:
        if not it["legivel"]:
            continue
        senha = None
        perto = " ".join(linhas.get((it["pagina"], it["linha"] - k), "") for k in range(0, 4))
        perto += " " + linhas.get((it["pagina"], it["linha"] + 2), "")
        m = re.search(r"Senha (?:de autoriza\S+ )?(\d{8})", perto)
        if m and it["codigo_glosa"] in ("1818", "1414"):
            senha = m.group(1)
        out.append(
            {
                "pagina": it["pagina"],
                "linha": it["linha"],
                "guia": it["guia"],
                "data_atendimento": it["data_atendimento"],
                "beneficiario": _token(linhas, it["pagina"], it["linha"]),
                "codigo_procedimento": it["codigo_procedimento"],
                "descricao": "procedimento",
                "quantidade": 1,
                "valor_apresentado": _v(it["valor_apresentado"]),
                "valor_glosado": _v(it["valor_glosado"]),
                "valor_pago": _v(it["valor_pago"]),
                "codigo_glosa": it["codigo_glosa"],
                "motivo_glosa": None,
                "observacao": None,
                "senha": senha,
            }
        )
    return out


def recurso_modelo(it: dict) -> str:
    return (
        f"Recurso de glosa — guia {it['guia']}\n"
        f"Procedimento {it['codigo_procedimento']}, glosa código {it['codigo_glosa']}.\n"
        f"Valor apresentado R$ {_v(it['valor_apresentado'])}; valor glosado R$ {_v(it['valor_glosado'])}.\n"
        "Solicitamos a revisão da glosa e o pagamento do valor glosado, conforme a documentação anexa.\n"
        "Fundamento normativo: [FUNDAMENTO A CONFIRMAR]\n"
        "Protocolo do recurso: [A PREENCHER]\n"
        "Assinatura do responsável: [A PREENCHER]\n"
    )


def roteiro_oraculo(doc_id: str, ajuste=None):
    """`ajuste(etapa, resposta_padrao, pedido)` permite trocar respostas para simular falhas."""
    gab = gabarito(doc_id)
    legiveis = [it for it in gab["itens"] if it["legivel"]]

    def responder(p: Pedido):
        prompt = p.messages[0]["content"]
        if p.etapa == "triagem":
            r = _json(
                {
                    "tipo_documento": "demonstrativo_retorno",
                    "operadora": gab["operadora"],
                    "competencia": "09/2026",
                    "data_emissao": gab["data_emissao"],
                    "protocolo": "123",
                    "legivel": True,
                    "observacao": "",
                }
            )
        elif p.etapa == "extracao":
            t = gab["totais_impressos"]
            r = _json(
                {
                    "itens": itens_extraidos(gab, prompt),
                    "totais": {
                        "valor_apresentado": _v(t["valor_apresentado"]),
                        "valor_glosado": _v(t["valor_glosado"]),
                        "valor_pago": _v(t["valor_pago"]),
                        "pagina": 1,
                        "linha": 1,
                    },
                }
            )
        elif p.etapa == "analise":
            ultimo = p.messages[-1]["content"]
            if isinstance(ultimo, str):  # primeira volta: pede as ferramentas
                idx = [
                    int(x)
                    for x in re.search(r"Glosas a analisar \(índices\): ([\d, ]+)", prompt)
                    .group(1)
                    .split(",")
                ]
                r = [
                    {
                        "type": "tool_use",
                        "id": f"t{i}",
                        "name": "consultar_t38",
                        "input": {"codigo": legiveis[i]["codigo_glosa"]},
                    }
                    for i in idx
                ]
            else:
                idx = [
                    int(x)
                    for x in re.search(r"Glosas a analisar \(índices\): ([\d, ]+)", prompt)
                    .group(1)
                    .split(",")
                ]
                r = _json(
                    {
                        "decisoes": [
                            {
                                "item": i,
                                "decisao": legiveis[i]["decisao_esperada"],
                                "confianca": "alta",
                                "justificativa": legiveis[i]["nota"] or "conforme critério",
                                "fontes": [f"t38-{legiveis[i]['codigo_glosa']}"],
                                "documentos": ["guia"],
                            }
                            for i in idx
                        ]
                    }
                )
        elif p.etapa == "redacao":
            idx = [int(m) for m in re.findall(r"^\[item (\d+)\]", prompt, re.MULTILINE)]
            r = _json(
                {"recursos": [{"item": i, "texto": recurso_modelo(legiveis[i])} for i in idx]}
            )
        else:
            raise AssertionError(p.etapa)
        return ajuste(p.etapa, r, p) if ajuste else r

    return responder


def cliente_oraculo(doc_id: str, ajuste=None) -> ClienteFalso:
    return ClienteFalso(roteiro_oraculo(doc_id, ajuste))
