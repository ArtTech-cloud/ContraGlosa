# Estado do projeto — 20/10/2026

Resumo para a equipe chegar no sábado com o projeto instalado.

## Bloqueio principal: falta a chave da API

Até agora, **nenhuma chamada ao modelo real foi feita**, porque o ambiente de construção não tinha
`ANTHROPIC_API_KEY`. Tudo o que depende do modelo foi construído e testado com um cliente falso, mas três coisas
só existem depois de rodar com a chave:

1. o teste de fumaça da API (E0.4);
2. os números reais da avaliação (E4.1 a E4.3), em `avaliacao/RESULTADO.md`;
3. o cache do modo demo (E4.4), em `cache/`. **Sem ele, o modo demo mostra "sem resposta em cache".**

Para destravar, com a chave no `.env` (copie de `.env.example`):

```bash
python -m agente.fumaca
```

```bash
python -m agente.avaliar
```

A avaliação roda os 10 documentos, grava o relatório e popula o cache de uma vez. Depois, faça o commit de
`cache/` e de `avaliacao/`. Deixe `PSEUDONIMO_SEGREDO` vazio, senão o cache não serve para o resto da equipe.

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

Ainda não há métricas do modelo real. A avaliação contra o gabarito foi validada com o cliente falso: ela dá 100%
quando as respostas são as do gabarito e detecta decisão errada, injeção obedecida e glosa perdida.

## O que está frágil

- **Prompts nunca rodaram no modelo real.** É provável que a primeira avaliação mostre ajustes a fazer,
  principalmente na extração do layout Boreal (beneficiário só no cabeçalho da guia) e na análise de retorno e
  duplicidade. Esse é o trabalho da pessoa 1 no sábado.
- **Fallback de recusa (beta).** O cliente usa `fallbacks: "default"`. Se a conta não tiver o beta, ele desliga
  sozinho. Se der problema, use `AGENTE_FALLBACK=0`.
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
