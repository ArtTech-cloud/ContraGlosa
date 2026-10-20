# Fluxo do agente

Princípio: **o agente faz o trabalho e ferramentas determinísticas fiscalizam o agente.** O LLM decide o que exige
leitura e julgamento: extração, enquadramento e redação. O código decide o que exige certeza: soma, existência do
código, prazo, evidência e totais do painel.

```mermaid
flowchart TD
    PDF[PDF do demonstrativo] --> L["Leitura (pdfplumber)<br/>texto com página e linha"]
    L -->|página sem texto| P1[[pendência pagina_ilegivel]]
    L --> PS["Pseudonimização<br/>nome e CPF saem, carteira vira token HMAC"]
    PS --> F["Filtro de instruções<br/>texto suspeito sai antes do LLM"]
    F -->|achou instrução| A1[[alerta instrucao_no_documento]]
    F --> T["1 · Triagem (LLM)<br/>tipo, operadora, data de emissão"]
    T -->|não é demonstrativo| P2[[pendência documento_nao_reconhecido]]
    T --> E["2 · Extração (LLM)<br/>todos os itens + totais impressos"]
    E <-->|evidência confere?| VE{{verificar_evidencia}}
    E <-->|soma fecha?| CS{{conferir_soma}}
    CS -->|divergiu após releitura| P3[[pendência soma_divergente]]
    E --> CT{{"consultar_t38 (código)"}}
    CT -->|código não existe| P4[[pendência codigo_inexistente<br/>revisão humana]]
    CT --> AN["3 · Análise (LLM + ferramentas)<br/>recorrer, não recorrer ou revisão humana"]
    AN <--> TL{{"consultar_t38 · consultar_operadora<br/>calcular_intervalo · buscar_base (BM25)"}}
    AN <-->|cada glosa decidida? fontes existem?| VA{{verificar_analise}}
    AN -->|confiança baixa| P5[[pendência confianca_baixa<br/>revisão humana]]
    AN --> R["4 · Redação (LLM)<br/>rascunho por glosa recorrível"]
    R <-->|valores, normas, dados pessoais, campos| VR{{verificar_recurso}}
    VR -->|reprovado 3 vezes| P6[[pendência recurso_recusado]]
    R --> C["Consolidar (código)<br/>painel: totais, recorrível, a classificar, prazos"]
    C --> UI[Tela + trilha JSONL em .runs/]
```

Losangos duplos são código, não LLM. Em qualquer etapa do LLM, se a saída não validar, a etapa refaz com o erro
como contexto, no máximo 2 vezes. Depois disso, o caso vai para revisão humana com o motivo.

## Contrato de cada etapa

| Etapa | Recebe | Ferramentas | Devolve (validado por pydantic) | Fiscalização pelo código |
|---|---|---|---|---|
| Leitura | PDF | — | linhas `(página, linha, texto)` | página com menos de 20 caracteres vira `pagina_ilegivel`; PDF corrompido vira `documento_nao_reconhecido` |
| Pseudonimização | linhas | — | linhas com `[NOME]`, `[CPF]` e `CART-xxxxxxxx` | a numeração de página e linha não muda |
| Filtro de instruções | linhas | — | linhas sem o trecho suspeito | alerta com página, linha e trecho |
| 1 · Triagem | primeiras 40 linhas | — | `Triagem`: tipo, operadora, competência, data de emissão, protocolo | data válida; tipo `demonstrativo_retorno` para seguir |
| 2 · Extração | documento inteiro | — | `Extracao`: itens com página, linha, guia, data, token, procedimento, valores e código de glosa; totais impressos | valores no formato BRL viram centavos (`parse_brl`); `verificar_evidencia` confere cada linha citada; `conferir_soma` confere soma e totais, com uma releitura |
| Conferência do código | glosas extraídas | `consultar_t38` | existe ou não na Tabela 38 oficial | inexistente nunca vai ao LLM |
| 3 · Análise | itens, glosas, documento | `consultar_t38`, `consultar_operadora`, `calcular_intervalo`, `buscar_base` | `Analise`: decisão, confiança, justificativa, ids das fontes, documentos | `verificar_analise`: uma decisão por glosa e todo id existe na base; confiança baixa vira revisão humana |
| 4 · Redação | glosas a recorrer com a análise | — | `Redacao`: um texto por glosa | `verificar_recurso`: todo valor existe nos dados, nenhuma norma citada, `[FUNDAMENTO A CONFIRMAR]`, protocolo e assinatura `[A PREENCHER]`, nenhum dado pessoal, guia, procedimento e código citados |
| Consolidar | resultado | `prazo_recurso` | painel em centavos e prazo final | 100% código |

## Prompts

Um arquivo por etapa e versão em `agente/prompts/` (`sistema_v1.md`, `triagem_v1.md`, `extracao_v1.md`,
`analise_v1.md`, `redacao_v1.md`). `AGENTE_PROMPTS=analise=v2` troca a versão de uma etapa. A versão entra na chave
do cache e na trilha.

## Casos adversos

| Caso | Documento | O que acontece |
|---|---|---|
| Total impresso ≠ soma das linhas | `adverso_soma.pdf` | `conferir_soma` diverge, o agente relê uma vez, a divergência persiste e vira `soma_divergente` |
| Código fora da Tabela 38 | `adverso_codigo.pdf` | o código não existe, a glosa vai para revisão humana com "código não consta na Tabela 38 oficial" |
| Instrução no documento | `adverso_injecao.pdf` | o filtro retira o trecho, gera `instrucao_no_documento` e o prompt de sistema reforça que o documento é dado |
| Página só com imagem | `adverso_imagem.pdf` | a página 2 não tem texto e vira `pagina_ilegivel`; a página 1 é analisada |

## Trilha

Cada execução grava `.runs/<data>_<documento>.jsonl`, fora do git. Cada linha tem a etapa, a versão do prompt, o
modelo, as ferramentas chamadas com argumento e resultado resumidos, os tokens, a latência e se veio do cache. A
última linha resume custo, pendências e alertas.
