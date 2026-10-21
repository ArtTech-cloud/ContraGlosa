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


# ---------------------------------------------------------------- regras da tela (código, não LLM)
def semaforo(glosa, resultado) -> tuple[str, str]:
    """Pronto, confira ou revisão humana, com o motivo em uma linha.

    - pronto: confiança alta e nenhum verificador alertou (evidência confere e, se é para recorrer,
      o recurso foi aprovado);
    - confira: confiança média ou algum verificador alertou;
    - revisao: o agente não decidiu (pendência).
    """
    if glosa.decisao == "revisao_humana":
        motivo = next(
            (p.motivo for p in resultado.pendencias if p.item == glosa.item),
            "o agente não decidiu esta glosa",
        )
        return "revisao", motivo
    if not glosa.evidencia_ok:
        return "confira", "a linha citada não confere com o PDF"
    if glosa.decisao == "recorrer" and not any(r.item == glosa.item for r in resultado.recursos):
        return "confira", "o verificador reteve o recurso desta glosa"
    if glosa.confianca != "alta":
        return "confira", "confiança média do agente"
    return "pronto", ""


def glosas_priorizadas(resultado) -> list:
    """Prazo mais curto primeiro e, no empate, maior valor. Num documento, o prazo é um só."""
    pr = resultado.painel.get("prazo") or {}
    dias = pr.get("dias_restantes", 10**6)
    return sorted(resultado.glosas, key=lambda g: (dias, -g.valor_glosado, g.item))


def agenda(resultados: list) -> list[dict]:
    """Cada glosa recorrível de todos os documentos, do vencimento mais próximo ao mais distante."""
    linhas = []
    for r in resultados:
        pr = r.painel.get("prazo")
        if not pr:
            continue
        for g in r.glosas:
            if g.decisao != "recorrer":
                continue
            linhas.append(
                {
                    "documento": r.documento,
                    "operadora": pr["operadora"],
                    "guia": g.guia,
                    "codigo_glosa": g.codigo_glosa,
                    "descricao": g.descricao_oficial or "",
                    "valor": g.valor_glosado,
                    "prazo_final": pr["prazo_final"],
                    "dias_restantes": pr["dias_restantes"],
                    "vencido": pr["vencido"],
                }
            )
    linhas.sort(key=lambda x: (x["dias_restantes"], -x["valor"]))
    return linhas


def campos_a_preencher(texto: str) -> tuple[list[str], list[str]]:
    """Os rótulos dos campos [A PREENCHER] e dos [FUNDAMENTO A CONFIRMAR] de um recurso."""
    preencher, confirmar = [], []
    for linha in texto.splitlines():
        rotulo = linha.split(":")[0].strip() if ":" in linha else "campo sem rótulo"
        preencher += [rotulo] * linha.count("[A PREENCHER]")
        confirmar += [rotulo] * linha.count("[FUNDAMENTO A CONFIRMAR]")
    return preencher, confirmar
