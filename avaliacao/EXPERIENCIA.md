# Experiência de uso

- **Data:** 20/10/2026 22:44
- **Modo:** demo (só cache, sem internet)
- **Documentos:** 15 (10 de desenvolvimento e 5 de validação, todos fictícios)

Metas do plano do front (`docs/PLANO-FRONT.md`). O tempo na tela é o tempo medido do agente mais a pausa fixa de 0,6 s entre os passos da trilha (ritmo de apresentação). Sem essa pausa, a tela mostra o resultado no tempo do agente.

| O que medimos | Resultado | Meta | Bateu? |
|---|---|---|---|
| Tempo até o primeiro valor, modo demo (pior caso: adverso_soma) | 6,1 s | < 60 s | sim |
| Cliques da chegada até copiar o primeiro recurso | 2 | ≤ 3 | sim |

**Glosas em 🟡 Confira ou ⚪ Revisão humana nos 6 exemplos normais:** 3 de 20. Meta: registrar.

Os cliques foram contados no roteiro da tela, não por script: com o exemplo do pitch já selecionado, (1) "Analisar o exemplo" e (2) o botão de copiar no canto do primeiro recurso. Rolar a página não conta como clique.

## Por documento

| Documento | Conjunto | Agente | Na tela | Passos da trilha | Glosas | 🟢 Pronto | 🟡 Confira | ⚪ Revisão humana |
|---|---|---|---|---|---|---|---|---|
| adverso_codigo | exemplos | 0,09 s | 4,9 s | 8 | 3 | 2 | 0 | 1 |
| adverso_imagem | exemplos | 0,05 s | 4,8 s | 8 | 1 | 1 | 0 | 0 |
| adverso_injecao | exemplos | 0,08 s | 5,5 s | 9 | 4 | 4 | 0 | 0 |
| adverso_soma | exemplos | 0,06 s | 6,1 s | 10 | 2 | 2 | 0 | 0 |
| aurora_01 | exemplos | 0,05 s | 4,8 s | 8 | 4 | 4 | 0 | 0 |
| aurora_02 | exemplos | 0,06 s | 4,9 s | 8 | 3 | 3 | 0 | 0 |
| boreal_01 | exemplos | 0,08 s | 4,9 s | 8 | 3 | 3 | 0 | 0 |
| boreal_02 | exemplos | 0,14 s | 4,9 s | 8 | 3 | 2 | 0 | 1 |
| cerrado_01 | exemplos | 0,09 s | 4,9 s | 8 | 3 | 2 | 0 | 1 |
| cerrado_02 | exemplos | 0,09 s | 4,9 s | 8 | 4 | 3 | 0 | 1 |
| validacao_01 | validacao | 0,06 s | 4,9 s | 8 | 3 | 2 | 0 | 1 |
| validacao_02 | validacao | 0,08 s | 4,9 s | 8 | 3 | 3 | 0 | 0 |
| validacao_03 | validacao | 0,09 s | 4,9 s | 8 | 4 | 2 | 1 | 1 |
| validacao_04 | validacao | 0,09 s | 4,9 s | 8 | 5 | 4 | 0 | 1 |
| validacao_05 | validacao | 0,05 s | 5,4 s | 9 | 3 | 3 | 0 | 0 |

Comando: `python -m agente.experiencia`.
