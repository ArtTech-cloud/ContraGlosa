"""Métricas de experiência da tela (docs/PLANO-FRONT.md): python -m agente.experiencia

Roda os 15 exemplos no modo demo (só cache, sem internet) e grava avaliacao/EXPERIENCIA.md com:
- o tempo do clique em "Analisar" até o número-herói: o tempo medido do agente mais a pausa de
  apresentação entre os passos da trilha, que é fixa;
- quantas glosas ficam em 🟡 Confira ou ⚪ Revisão humana (o agente sabe quando não sabe);
- os cliques da chegada até copiar o primeiro recurso, contados no roteiro da tela.

A tela mostra o tempo real de cada análise em "Ver detalhes técnicos" ("do clique ao resultado").
Os relatórios RESULTADO.md e VALIDACAO.md são de agente.avaliar e não são tocados aqui.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections import Counter
from pathlib import Path

from agente.consolidar import semaforo
from agente.llm import ClienteAnthropic
from agente.orquestrador import Orquestrador

RAIZ = Path(__file__).resolve().parents[1]
PASTAS = {"exemplos": RAIZ / "dados" / "exemplos", "validacao": RAIZ / "dados" / "validacao"}
SAIDA = RAIZ / "avaliacao" / "EXPERIENCIA.md"
PAUSA_APRESENTACAO = 0.6  # o mesmo valor de app.py: espera entre os passos da trilha no modo demo
META_SEGUNDOS = 60
META_CLIQUES = 3
# Da chegada até copiar o primeiro recurso, com o exemplo do pitch já selecionado:
# 1. "Analisar o exemplo"; 2. o botão de copiar no canto do primeiro recurso.
CLIQUES_ATE_COPIAR = 2


def medir() -> list[dict]:
    linhas = []
    for conjunto, pasta in PASTAS.items():
        for pdf in sorted(pasta.glob("*.pdf")):
            res = Orquestrador(ClienteAnthropic(modo_demo=True)).analisar(pdf)
            cores = Counter(semaforo(g, res)[0] for g in res.glosas)
            agente_s = res.latencia_ms / 1000
            linhas.append(
                {
                    "documento": pdf.stem,
                    "conjunto": conjunto,
                    "normal": conjunto == "exemplos" and not pdf.stem.startswith("adverso_"),
                    "agente_s": agente_s,
                    "tela_s": agente_s + PAUSA_APRESENTACAO * len(res.trilha),
                    "passos": len(res.trilha),
                    "glosas": len(res.glosas),
                    "pronto": cores["pronto"],
                    "confira": cores["confira"],
                    "revisao": cores["revisao"],
                    "interrompido": res.interrompido,
                }
            )
    return linhas


def _s(segundos: float, casas: int = 1) -> str:
    return f"{segundos:.{casas}f} s".replace(".", ",")


def relatorio(linhas: list[dict]) -> str:
    pior = max(linhas, key=lambda x: x["tela_s"])
    normais = [x for x in linhas if x["normal"]]
    g_normais = sum(x["glosas"] for x in normais)
    nao_prontas = sum(x["confira"] + x["revisao"] for x in normais)
    interrompidos = [x["documento"] for x in linhas if x["interrompido"]]
    hoje = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    out = [
        "# Experiência de uso",
        "",
        f"- **Data:** {hoje}",
        "- **Modo:** demo (só cache, sem internet)",
        f"- **Documentos:** {len(linhas)} (10 de desenvolvimento e 5 de validação, todos fictícios)",
        "",
        "Metas do plano do front (`docs/PLANO-FRONT.md`). O tempo na tela é o tempo medido do agente "
        f"mais a pausa fixa de {_s(PAUSA_APRESENTACAO)} entre os passos da trilha (ritmo de "
        "apresentação). Sem essa pausa, a tela mostra o resultado no tempo do agente.",
        "",
        "| O que medimos | Resultado | Meta | Bateu? |",
        "|---|---|---|---|",
        f"| Tempo até o primeiro valor, modo demo (pior caso: {pior['documento']}) | "
        f"{_s(pior['tela_s'])} | < {META_SEGUNDOS} s | "
        f"{'sim' if pior['tela_s'] < META_SEGUNDOS else 'não'} |",
        f"| Cliques da chegada até copiar o primeiro recurso | {CLIQUES_ATE_COPIAR} | "
        f"≤ {META_CLIQUES} | {'sim' if CLIQUES_ATE_COPIAR <= META_CLIQUES else 'não'} |",
        "",
        f"**Glosas em 🟡 Confira ou ⚪ Revisão humana nos 6 exemplos normais:** {nao_prontas} de "
        f"{g_normais}. Meta: registrar.",
        "",
        "Os cliques foram contados no roteiro da tela, não por script: com o exemplo do pitch já "
        'selecionado, (1) "Analisar o exemplo" e (2) o botão de copiar no canto do primeiro recurso. '
        "Rolar a página não conta como clique.",
        "",
        "## Por documento",
        "",
        "| Documento | Conjunto | Agente | Na tela | Passos da trilha | Glosas | 🟢 Pronto | "
        "🟡 Confira | ⚪ Revisão humana |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for x in linhas:
        out.append(
            f"| {x['documento']} | {x['conjunto']} | {_s(x['agente_s'], 2)} | {_s(x['tela_s'])} | "
            f"{x['passos']} | {x['glosas']} | {x['pronto']} | {x['confira']} | {x['revisao']} |"
        )
    if interrompidos:
        out += ["", f"**Interrompidos (fora do cache?):** {', '.join(interrompidos)}"]
    out += ["", "Comando: `python -m agente.experiencia`.", ""]
    return "\n".join(out)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    linhas = medir()
    SAIDA.write_text(relatorio(linhas), encoding="utf-8")
    print(f"gravado {SAIDA.relative_to(RAIZ)}")
    return 1 if any(x["interrompido"] for x in linhas) else 0


if __name__ == "__main__":
    sys.exit(main())
