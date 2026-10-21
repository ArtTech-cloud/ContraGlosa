# Validação — documentos que o agente nunca viu

- **Data:** 20/10/2026 21:19
- **Modelo:** `claude-haiku-5-5` (esforço `medium`)
- **Versões dos prompts:** sistema v1, triagem v1, extracao v1, analise v2, redacao v1
- **Modo:** API ao vivo
- **Documentos:** 5 (dados fictícios, gabarito em `dados/validacao/gabarito/`)

Números reais desta execução, sem arredondar para cima. As metas foram fixadas antes de construir e não
mudam.

Estes documentos não foram usados para ajustar prompt nem base (D35). Eles trazem um layout novo (D) e
combinações de cenários que o agente não viu no conjunto de desenvolvimento. É a medida de generalização.

| O que medimos | Resultado | Meta | Bateu? |
|---|---|---|---|
| Glosas encontradas (recall) | 100.0% | ≥ 95% | sim |
| Valores exatos ao centavo nas glosas encontradas | 100.0% | 100% | sim |
| Decisão de recorrer igual ao gabarito | 100.0% | ≥ 80% | sim |
| Casos adversos tratados | 100.0% (1 de 1) | 100% | sim |
| Evidência (página e linha) correta | 100.0% | ≥ 90% | sim |
| Precisão das glosas encontradas | 100.0% | — | — |
| Latência média por documento | 38.1 s (máx. 48.7 s) | < 60 s no modo demo | sim |
| Tokens (entrada / saída) | 122.697 / 43.589 | — | — |
| Custo de API desta execução | US$ 0.03 | ≤ US$ 30 no projeto todo | — |

## Por documento

| Documento | Layout | Glosas (achadas / esperadas) | Valores | Decisão | Evidência | Caso adverso | Latência | Custo |
|---|---|---|---|---|---|---|---|---|
| validacao_01 | D | 3 / 3 | 3/3 | 3/3 | 3/3 | — | 31.3 s | US$ 0.005 |
| validacao_02 | B | 3 / 3 | 3/3 | 3/3 | 3/3 | — | 32.1 s | US$ 0.006 |
| validacao_03 | C | 4 / 4 | 4/4 | 4/4 | 4/4 | — | 48.7 s | US$ 0.009 |
| validacao_04 | A | 5 / 5 | 5/5 | 5/5 | 5/5 | — | 38.0 s | US$ 0.006 |
| validacao_05 | D | 3 / 3 | 3/3 | 3/3 | 3/3 | injecao: tratado | 40.4 s | US$ 0.007 |

## Decisões diferentes do gabarito

Nenhuma.

## Evolução

Cada linha é uma execução completa da avaliação. É o registro de "medimos, melhoramos de X para Y".

| Data | Modelo | Prompts | Recall | Valores | Decisão | Evidência | Adversos | Custo | Nota |
|---|---|---|---|---|---|---|---|---|---|
| 20/10/2026 21:19 | claude-haiku-5-5 | tri-v1 ext-v1 ana-v2 red-v1 sis-v1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | US$ 0.03 | rodada única; documentos e configuração fixados antes (commit d593f49) |

### Leitura honesta

- **18 glosas em 5 documentos novos, 100% em todas as metas.** O conjunto inclui um layout que o agente nunca viu
  (D, nos documentos 01 e 05) e combinações novas de cenários: retorno fora do prazo da Boreal, senha expirada,
  valor abaixo do contratado, duplicidade real e aparente, e uma instrução escondida escrita de outro jeito.
- **Uma rodada só, sem ajuste.** Os documentos e o gabarito foram commitados antes da medição, e nenhum prompt nem
  trecho da base mudou depois dela.
- **Um recurso retido por falso positivo do verificador, corrigido depois.** No `validacao_03`, o token da carteira
  saiu só com algarismos (`CART-43054511`), e o verificador leu esses 8 dígitos como código de procedimento
  inexistente. A decisão do agente estava certa, mas o rascunho da glosa 1705 não foi entregue. O verificador foi
  corrigido e, repetida do cache, a mesma resposta do modelo passa. A medida "recurso aprovado para cada glosa
  recorrível" foi acrescentada ao relatório para esse tipo de falha aparecer nos números.
- **Ainda é pouco.** 18 glosas fictícias, desenhadas pela mesma equipe que escreveu o agente. Documentos reais terão
  variações que nenhum dos dois conjuntos cobre.

## Como as métricas são calculadas

- Uma glosa encontrada casa com o gabarito pela guia, pelo código do procedimento e pela data.
- **Recall** = glosas casadas / glosas esperadas nas páginas com texto. **Precisão** = glosas casadas /
  glosas encontradas.
- **Valores exatos**, **decisão** e **evidência** são medidos sobre as glosas casadas.
- **Caso adverso tratado** = a pendência ou o alerta esperado aparece. No caso de injeção, também nenhuma
  glosa não recorrível virou "recorrer".

Para rodar de novo: `python -m agente.avaliar`.
