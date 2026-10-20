"""Painel: totais e prazos calculados só por código, nunca pelo LLM."""

from __future__ import annotations

from agente.ferramentas.basicas import prazo_recurso


def painel(resultado) -> dict:
    itens = resultado.itens
    glosas = resultado.glosas
    soma = lambda dec: sum(g.valor_glosado for g in glosas if g.decisao == dec)  # noqa: E731
    p = {
        "total_apresentado": sum(it.apresentado for it in itens),
        "total_glosado": sum(it.glosado for it in itens),
        "total_pago": sum(it.pago for it in itens),
        "recorrivel": soma("recorrer"),
        "nao_recorrivel": soma("nao_recorrer"),
        "a_classificar": soma("revisao_humana"),
        "n_itens": len(itens),
        "n_glosas": len(glosas),
        "n_recursos": len(resultado.recursos),
        "n_pendencias": len(resultado.pendencias),
        "n_alertas": len(resultado.alertas),
        "prazo": None,
    }
    tri = resultado.triagem
    if tri and tri.data_emissao:
        pr = prazo_recurso(tri.data_emissao, tri.operadora)
        if pr.get("ok"):
            p["prazo"] = pr
    return p


def painel_geral(resultados: list) -> dict:
    """Soma de vários documentos e a lista de prazos, do mais próximo ao mais distante."""
    chaves = ["total_apresentado", "total_glosado", "recorrivel", "nao_recorrivel", "a_classificar"]
    tot = {k: sum(r.painel.get(k, 0) for r in resultados) for k in chaves}
    prazos = [
        {"documento": r.documento, **r.painel["prazo"], "recorrivel": r.painel["recorrivel"]}
        for r in resultados
        if r.painel.get("prazo")
    ]
    prazos.sort(key=lambda x: x["dias_restantes"])
    tot["prazos"] = prazos
    return tot
