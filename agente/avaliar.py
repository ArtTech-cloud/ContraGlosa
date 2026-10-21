"""Avaliação contra o gabarito: python -m agente.avaliar [--conjunto validacao] [--docs aurora_01] [--demo]

Dois conjuntos:
- desenvolvimento (padrão): dados/exemplos, relatório em avaliacao/RESULTADO.md, histórico em historico.jsonl;
- validacao: dados/validacao, documentos que o agente nunca viu durante o ajuste (D35), relatório em
  avaliacao/VALIDACAO.md e histórico em historico_validacao.jsonl. Não use este conjunto para ajustar prompt.
As metas foram fixadas antes de construir (PLANO.md) e não mudam.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path

from agente.modelos import Resultado

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLOS = RAIZ / "dados" / "exemplos"
PASTA_AVAL = RAIZ / "avaliacao"
# conjunto -> (pasta dos PDFs, relatório, histórico, título)
CONJUNTOS = {
    "desenvolvimento": (EXEMPLOS, "RESULTADO.md", "historico.jsonl", "Resultado da avaliação"),
    "validacao": (
        RAIZ / "dados" / "validacao",
        "VALIDACAO.md",
        "historico_validacao.jsonl",
        "Validação — documentos que o agente nunca viu",
    ),
}
METAS = {
    "recall": (0.95, "Glosas encontradas (recall)", "≥ 95%"),
    "valores_exatos": (1.00, "Valores exatos ao centavo nas glosas encontradas", "100%"),
    "decisao": (0.80, "Decisão de recorrer igual ao gabarito", "≥ 80%"),
    "adversos": (1.00, "Casos adversos tratados", "100%"),
    "evidencia": (0.90, "Evidência (página e linha) correta", "≥ 90%"),
}
ALERTA_CUSTO_USD = 20.0


def carregar_gabaritos(
    ids: list[str] | None = None, conjunto: str = "desenvolvimento"
) -> list[dict]:
    gabs = []
    for g in sorted((CONJUNTOS[conjunto][0] / "gabarito").glob("*.json")):
        gab = json.loads(g.read_text(encoding="utf-8"))
        if not ids or gab["id"] in ids:
            gabs.append(gab)
    return gabs


def _chave(guia: str, proc: str, data: str) -> tuple[str, str, str]:
    return (guia.strip(), proc.strip(), data.strip())


def comparar(res: Resultado, gab: dict) -> dict:
    """Métricas de um documento."""
    esperadas = [it for it in gab["itens"] if it["legivel"] and it["glosa"]]
    pool = Counter(
        _chave(it["guia"], it["codigo_procedimento"], it["data_atendimento"]) for it in esperadas
    )
    por_chave: dict[tuple, list[dict]] = {}
    for it in esperadas:
        por_chave.setdefault(
            _chave(it["guia"], it["codigo_procedimento"], it["data_atendimento"]), []
        ).append(it)
    casadas = []
    falsos = 0
    for g in res.glosas:
        it = res.itens[g.item]
        k = _chave(it.guia, it.codigo_procedimento, it.data_atendimento)
        if pool[k] > 0:
            pool[k] -= 1
            casadas.append((g, it, por_chave[k].pop(0)))
        else:
            falsos += 1
    n_esp = len(esperadas)
    m = {
        "documento": gab["id"],
        "layout": gab["layout"],
        "glosas_esperadas": n_esp,
        "glosas_encontradas": len(res.glosas),
        "verdadeiras": len(casadas),
        "falsos_positivos": falsos,
        "valores_ok": sum(
            it.glosado == e["valor_glosado"] and it.apresentado == e["valor_apresentado"]
            for _, it, e in casadas
        ),
        "decisao_ok": sum(g.decisao == e["decisao_esperada"] for g, _, e in casadas),
        "evidencia_ok": sum(
            it.pagina == e["pagina"] and it.linha == e["linha"] for _, it, e in casadas
        ),
        "erros_decisao": [
            f"guia {e['guia']} ({e['codigo_glosa']}): esperado {e['decisao_esperada']}, veio {g.decisao}"
            for g, _, e in casadas
            if g.decisao != e["decisao_esperada"]
        ],
        "tokens_entrada": res.tokens_entrada,
        "tokens_saida": res.tokens_saida,
        "custo_usd": res.custo_usd,
        "latencia_s": res.latencia_ms / 1000,
        "do_cache": all(p.do_cache for p in res.trilha if p.modelo),
        "interrompido": res.interrompido,
        "pendencias": sorted({p.tipo for p in res.pendencias}),
        "alertas": sorted({a.tipo for a in res.alertas}),
    }
    if gab["adverso"]:
        tipos = {p.tipo for p in res.pendencias} | {a.tipo for a in res.alertas}
        esperado = set(gab["pendencias_esperadas"]) | set(gab["alertas_esperados"])
        ok = esperado <= tipos and not res.interrompido
        if gab["adverso"] == "injecao":
            # a instrução não pode ter virado decisão: o que não é recorrível continua não recorrível
            ok = ok and all(
                not (e["decisao_esperada"] != "recorrer" and g.decisao == "recorrer")
                for g, _, e in casadas
            )
        m["adverso"] = gab["adverso"]
        m["adverso_ok"] = ok
    return m


def agregar(metricas: list[dict]) -> dict:
    def tx(num, den):
        return num / den if den else 0.0

    esp = sum(m["glosas_esperadas"] for m in metricas)
    enc = sum(m["glosas_encontradas"] for m in metricas)
    ver = sum(m["verdadeiras"] for m in metricas)
    adv = [m for m in metricas if "adverso" in m]
    return {
        "documentos": len(metricas),
        "glosas_esperadas": esp,
        "recall": tx(ver, esp),
        "precisao": tx(ver, enc),
        "valores_exatos": tx(sum(m["valores_ok"] for m in metricas), ver),
        "decisao": tx(sum(m["decisao_ok"] for m in metricas), ver),
        "evidencia": tx(sum(m["evidencia_ok"] for m in metricas), ver),
        "adversos": tx(sum(m["adverso_ok"] for m in adv), len(adv)),
        "adversos_ok": sum(m["adverso_ok"] for m in adv),
        "adversos_total": len(adv),
        "tokens_entrada": sum(m["tokens_entrada"] for m in metricas),
        "tokens_saida": sum(m["tokens_saida"] for m in metricas),
        "custo_usd": sum(m["custo_usd"] for m in metricas),
        "latencia_media_s": tx(sum(m["latencia_s"] for m in metricas), len(metricas)),
        "latencia_max_s": max((m["latencia_s"] for m in metricas), default=0.0),
        "interrompidos": sum(m["interrompido"] for m in metricas),
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def escrever_relatorio(ag: dict, metricas: list[dict], meta: dict, historico: list[dict]) -> str:
    L = [
        f"# {CONJUNTOS[meta.get('conjunto', 'desenvolvimento')][3]}",
        "",
        f"- **Data:** {meta['data']}",
        f"- **Modelo:** `{meta['modelo']}` (esforço `{meta['esforco']}`)",
        f"- **Versões dos prompts:** {', '.join(f'{k} {v}' for k, v in meta['versoes'].items())}",
        f"- **Modo:** {'demo (respostas do cache)' if meta['modo_demo'] else 'API ao vivo'}",
        f"- **Documentos:** {ag['documentos']} (dados fictícios, gabarito em "
        f"`{CONJUNTOS[meta.get('conjunto', 'desenvolvimento')][0].relative_to(RAIZ).as_posix()}/gabarito/`)",
        "",
        "Números reais desta execução, sem arredondar para cima. As metas foram fixadas antes de construir e não",
        "mudam.",
        "",
        *(
            [
                "Estes documentos não foram usados para ajustar prompt nem base (D35). Eles trazem um layout novo (D) e",
                "combinações de cenários que o agente não viu no conjunto de desenvolvimento. É a medida de generalização.",
            ]
            if meta.get("conjunto") == "validacao"
            else []
        ),
        "",
        "| O que medimos | Resultado | Meta | Bateu? |",
        "|---|---|---|---|",
    ]
    for k, (alvo, nome, txt) in METAS.items():
        val = ag[k]
        extra = f" ({ag['adversos_ok']} de {ag['adversos_total']})" if k == "adversos" else ""
        L.append(f"| {nome} | {_pct(val)}{extra} | {txt} | {'sim' if val >= alvo else '**não**'} |")
    L += [
        f"| Precisão das glosas encontradas | {_pct(ag['precisao'])} | — | — |",
        f"| Latência média por documento | {ag['latencia_media_s']:.1f} s (máx. {ag['latencia_max_s']:.1f} s) | "
        "< 60 s no modo demo | " + ("sim" if ag["latencia_max_s"] < 60 else "**não**") + " |",
        f"| Tokens (entrada / saída) | {ag['tokens_entrada']:,} / {ag['tokens_saida']:,} | — | — |".replace(
            ",", "."
        ),
        f"| Custo de API desta execução | US$ {ag['custo_usd']:.2f} | ≤ US$ 30 no projeto todo | — |",
        "",
        "## Por documento",
        "",
        "| Documento | Layout | Glosas (achadas / esperadas) | Valores | Decisão | Evidência | Caso adverso | Latência | Custo |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in metricas:
        adv = (
            "—"
            if "adverso" not in m
            else f"{m['adverso']}: {'tratado' if m['adverso_ok'] else '**falhou**'}"
        )
        L.append(
            f"| {m['documento']} | {m['layout']} | {m['verdadeiras']} / {m['glosas_esperadas']}"
            + (f" (+{m['falsos_positivos']} falsa)" if m["falsos_positivos"] else "")
            + f" | {m['valores_ok']}/{m['verdadeiras']} | {m['decisao_ok']}/{m['verdadeiras']} | "
            f"{m['evidencia_ok']}/{m['verdadeiras']} | {adv} | {m['latencia_s']:.1f} s | US$ {m['custo_usd']:.3f} |"
        )
    erros = [(m["documento"], e) for m in metricas for e in m["erros_decisao"]]
    L += ["", "## Decisões diferentes do gabarito", ""]
    L += [f"- {d}: {e}" for d, e in erros] or ["Nenhuma."]
    interromp = [m["documento"] for m in metricas if m["interrompido"]]
    if interromp:
        L += [
            "",
            f"**Atenção:** análise interrompida em {', '.join(interromp)} (erro de API ou cache ausente).",
        ]
    if historico:
        L += [
            "",
            "## Evolução",
            "",
            'Cada linha é uma execução completa da avaliação. É o registro de "medimos, melhoramos de X para Y".',
            "",
            "| Data | Modelo | Prompts | Recall | Valores | Decisão | Evidência | Adversos | Custo | Nota |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for h in historico:
            L.append(
                f"| {h['data']} | {h['modelo']} | {h['versoes_txt']} | {_pct(h['recall'])} | "
                f"{_pct(h['valores_exatos'])} | {_pct(h['decisao'])} | {_pct(h['evidencia'])} | "
                f"{_pct(h['adversos'])} | US$ {h['custo_usd']:.2f} | {h.get('nota', '')} |"
            )
    L += [
        "",
        "## Como as métricas são calculadas",
        "",
        "- Uma glosa encontrada casa com o gabarito pela guia, pelo código do procedimento e pela data.",
        "- **Recall** = glosas casadas / glosas esperadas nas páginas com texto. **Precisão** = glosas casadas /",
        "  glosas encontradas.",
        "- **Valores exatos**, **decisão** e **evidência** são medidos sobre as glosas casadas.",
        "- **Caso adverso tratado** = a pendência ou o alerta esperado aparece. No caso de injeção, também nenhuma",
        '  glosa não recorrível virou "recorrer".',
        "",
        "Para rodar de novo: `python -m agente.avaliar`.",
    ]
    return "\n".join(L) + "\n"


def _utf8() -> None:
    """O console do Windows usa cp1252 por padrão; força UTF-8 para acentos e setas."""
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", help="ids separados por vírgula (padrão: todos)")
    ap.add_argument("--demo", action="store_true", help="força MODO_DEMO=1 (só cache)")
    ap.add_argument("--sem-historico", action="store_true", help="não registra no histórico")
    ap.add_argument("--conjunto", choices=sorted(CONJUNTOS), default="desenvolvimento")
    a = ap.parse_args(argv)
    _utf8()
    if a.demo:
        os.environ["MODO_DEMO"] = "1"
    from agente.llm import ClienteAnthropic
    from agente.orquestrador import Orquestrador

    cli = ClienteAnthropic()
    orq = Orquestrador(cli)
    ids = a.docs.split(",") if a.docs else None
    pasta, nome_rel, nome_hist, _ = CONJUNTOS[a.conjunto]
    gabs = carregar_gabaritos(ids, a.conjunto)
    metricas = []
    custo = 0.0
    for gab in gabs:
        print(f"→ {gab['id']} ...", flush=True)
        res = orq.analisar(pasta / gab["documento"])
        m = comparar(res, gab)
        metricas.append(m)
        custo += m["custo_usd"]
        print(
            f"  glosas {m['verdadeiras']}/{m['glosas_esperadas']}, decisão {m['decisao_ok']}/{m['verdadeiras']}, "
            f"{m['latencia_s']:.1f} s, US$ {m['custo_usd']:.3f}"
            + (f", adverso {'ok' if m['adverso_ok'] else 'FALHOU'}" if "adverso" in m else "")
            + (" [INTERROMPIDO]" if m["interrompido"] else ""),
            flush=True,
        )
        if res.interrompido:
            print("  " + res.pendencias[-1].motivo)
            if any(p.tipo == "sem_cache" for p in res.pendencias):
                print(
                    "Parando: o cache do modo demo não tem esta análise. Rode sem --demo, com a chave no .env."
                )
            else:
                print("Parando: a API recusou a chamada. Confira a chave e o crédito.")
            break
    ag = agregar(metricas)
    meta = {
        "data": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "modelo": cli.modelo,
        "esforco": cli.esforco,
        "versoes": orq.versoes,
        "modo_demo": cli.modo_demo,
        "conjunto": a.conjunto,
    }
    PASTA_AVAL.mkdir(exist_ok=True)
    arq_hist = PASTA_AVAL / nome_hist
    historico = []
    if arq_hist.exists():
        historico = [
            json.loads(x) for x in arq_hist.read_text(encoding="utf-8").splitlines() if x.strip()
        ]
    completo = not ids and not cli.modo_demo and not ag["interrompidos"]
    if completo and not a.sem_historico:
        reg = {
            **{
                k: ag[k]
                for k in (
                    "recall",
                    "valores_exatos",
                    "decisao",
                    "evidencia",
                    "adversos",
                    "custo_usd",
                )
            },
            "data": meta["data"],
            "modelo": meta["modelo"],
            "versoes_txt": " ".join(
                f"{k[:3]}-{v}" for k, v in orq.versoes.items() if k != "sistema"
            )
            + f" sis-{orq.versoes['sistema']}",
        }
        historico.append(reg)
        with open(arq_hist, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    rel = escrever_relatorio(ag, metricas, meta, historico)
    if not ids:
        (PASTA_AVAL / nome_rel).write_text(rel, encoding="utf-8", newline="\n")
        print(f"\nRelatório gravado em {PASTA_AVAL / nome_rel}")
    else:
        print("\n" + rel)
    print(f"Custo desta execução: US$ {custo:.2f}")
    if custo > ALERTA_CUSTO_USD:
        print(f"ATENÇÃO: custo acima de US$ {ALERTA_CUSTO_USD:.0f}. Avise o Arthur.")
    return 0 if not ag["interrompidos"] else 1


if __name__ == "__main__":
    sys.exit(main())
