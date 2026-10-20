# Estado do projeto — 20/10/2026

Resumo para a equipe chegar no sábado com o projeto instalado.

> **Atualização de 20/10/2026, 19h:** a chave da API chegou e a avaliação real rodou: todas as metas bateram
> (decisão 90%, recall 100%, valores 100%, evidência 100%, 4 de 4 adversos). O bloqueio descrito abaixo acabou.
> O estado completo e atual está em `docs/CONTEXTO.md`; esta página será refeita antes de sábado.

## Situação

O agente já rodou no modelo real, o Claude Haiku 5.5. O teste de fumaça passou, a avaliação tem números reais e o
cache do modo demo cobre os 10 documentos com a configuração padrão. A demo roda offline em menos de 1 segundo por
documento.

Se alguém mudar um prompt, um documento ou a base, o cache daquela parte deixa de valer. Nesse caso, rode de novo
com a chave no `.env` (copie de `.env.example`):

```bash
python -m agente.fumaca
```

```bash
python -m agente.avaliar
```

A avaliação roda os 10 documentos, grava o relatório e popula o cache de uma vez. Depois, faça o commit de
`cache/` e de `avaliacao/`. Deixe `PSEUDONIMO_SEGREDO` vazio, senão o cache não serve para o resto da equipe.
Ative o ambiente antes (`.venv\Scripts\activate`): com o Python global falta o `rank_bm25`.

## O que funciona

- **Dados:** 10 demonstrativos fictícios em 3 layouts (Aurora, Boreal e Cerrado): 6 normais e 4 adversos, com
  gabarito. Os códigos vêm das Tabelas 38 e 22 oficiais da ANS (Padrão TISS 202609), com SHA-256 registrado.
- **Agente:** 4 etapas com prompts versionados (triagem, extração, análise e redação), retries com o erro como
  contexto, fallbacks para revisão humana, confiança, trilha JSONL e cache por SHA-256.
- **Verificadores:** soma em centavos, evidência de página e linha, existência do código na Tabela 38, fontes da
  análise, e valores, normas, dados pessoais e campos do recurso.
- **Segurança:** pseudonimização de nome, CPF e carteira antes do LLM, e filtro de instruções no documento.
- **Interface:** análise de um documento com trilha ao vivo, lote com painel de prazos, pendências e qualidade.
  Foi conferida no navegador com respostas de teste.
- **Testes:** 205 testes passam, incluindo ponta a ponta nos 10 documentos com o cliente falso. Isso prova o
  encanamento, os verificadores e a avaliação, não a qualidade do modelo.
- **Instalação do zero:** clone limpo, ambiente novo, `pip install`, testes e app sobem sem erro.
- **Revisão independente:** um subagente tentou quebrar o projeto. Os 14 achados confirmados foram corrigidos e
  viraram testes em `tests/test_revisao.py` (ver D19 a D28 em `docs/DECISOES.md`).

## Métricas atuais

Com o Claude Haiku 5.5 e o prompt de análise v2, todas as metas foram batidas: recall, valores, decisão,
evidência e casos adversos em 100%. A latência média foi de 20,7 s por documento ao vivo, e o custo, de US$ 0,03
pelos 10 documentos. A primeira versão acertava 78,6% das decisões. A evolução e a leitura honesta desses números
estão em `avaliacao/RESULTADO.md`.

## O que está frágil

- **100% em 30 glosas não é garantia.** O prompt v2 foi ajustado olhando os erros deste mesmo conjunto. Medir em
  documentos novos, que o agente nunca viu, é o trabalho mais útil da pessoa 1 e da pessoa 2 no sábado.
- **O modelo varia.** Duas rodadas iguais da v1 deram 78,6% e 82,1%. Para comparar versões, rode mais de uma vez.
- **Modelo Haiku 5.5.** É o padrão desde 20/10/2026 (D29): mais barato e rápido, mas é o menor modelo. Se a
  avaliação ficar abaixo das metas, teste `AGENTE_ESFORCO=high` ou `AGENTE_MODELO=claude-sonnet-5-5`, sempre medindo
  com `python -m agente.avaliar`. O Haiku não tem fallback de recusa no servidor; uma recusa vira pendência.
- **Filtro de injeção por padrões.** Pega as variantes testadas, mas não toda formulação possível. O prompt de
  sistema e a avaliação são as outras barreiras.
- **Pseudonimização por padrões.** Nome em caixa mista, sem rótulo e solto no texto não é detectado.
- **Classificação de recorribilidade** é proposta da equipe, a validar com especialista.
- **Sem OCR:** página escaneada vai para revisão humana.

## Comandos para sábado

| Para quê | Comando |
|---|---|
| Instalar | `python -m venv .venv`, ativar e `pip install -r requirements.txt` |
| Testes | `python -m pytest -q` |
| Lint | `ruff check . && ruff format --check .` |
| App | `streamlit run app.py` |
| Avaliação completa (gasta API) | `python -m agente.avaliar` |
| Avaliação de um documento | `python -m agente.avaliar --docs aurora_01` |
| Avaliação só com o cache | `python -m agente.avaliar --demo` |
| Testar outra versão de prompt | `AGENTE_PROMPTS=analise=v2 python -m agente.avaliar` |
| Gerar os dados de novo | `python -m dados.gerar` |

A divisão das tarefas está em `docs/TAREFAS-SABADO.md`.
