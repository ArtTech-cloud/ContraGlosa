# Estado do projeto — 21/10/2026

Resumo para a equipe chegar no sábado com o projeto instalado.

> O contexto completo (domínio, arquitetura, decisões, configuração, linha do tempo) está em `docs/CONTEXTO.md`.

## Situação

O agente já rodou no modelo real, o Claude Haiku 5.5. O teste de fumaça passou, a avaliação tem números reais e o
cache do modo demo cobre os 15 documentos (10 de desenvolvimento e 5 de validação) com a configuração padrão. A demo
roda offline: o agente responde do cache em menos de 1 segundo por documento, e a tela mostra o resultado em cerca
de 5 segundos, porque a trilha espera 0,6 s entre os passos para a banca acompanhar.

Se alguém mudar um prompt, um documento ou a base, o cache daquela parte deixa de valer. Nesse caso, rode de novo
com a chave no `.env` (copie de `.env.example`):

```bash
python -m agente.fumaca
```

```bash
python -m agente.avaliar
```

A avaliação roda os 10 documentos de desenvolvimento, grava o relatório e popula o cache de uma vez. Para os 5 de
validação, use `python -m agente.avaliar --conjunto validacao`. Depois, faça o commit de `cache/` e de `avaliacao/`. Deixe `PSEUDONIMO_SEGREDO` vazio, senão o cache não serve para o resto da equipe.
Ative o ambiente antes (`.venv\Scripts\activate`): com o Python global falta o `rank_bm25`.

## O que funciona

- **Dados:** 10 demonstrativos fictícios de desenvolvimento em 3 layouts (Aurora, Boreal e Cerrado), 6 normais e
  4 adversos, e 5 de validação em `dados/validacao/`, com um quarto layout (D). Todos têm gabarito. Os códigos vêm das Tabelas 38 e 22 oficiais da ANS (Padrão TISS 202609), com SHA-256 registrado.
- **Agente:** 4 etapas com prompts versionados (triagem, extração, análise e redação), retries com o erro como
  contexto, fallbacks para revisão humana, confiança, trilha JSONL e cache por SHA-256.
- **Verificadores:** soma em centavos, evidência de página e linha, existência do código na Tabela 38, fontes da
  análise, e valores, normas, dados pessoais e campos do recurso.
- **Segurança:** pseudonimização de nome, CPF e carteira antes do LLM, e filtro de instruções no documento.
- **Interface:** o plano do front (`docs/PLANO-FRONT.md`, D40) em cinco páginas (Início, Prazos, Pendências, Como
  funciona, Qualidade): chegada com uma ação, trilha ao vivo com o resultado de cada etapa, número-herói, glosas por
  prioridade com semáforo e prova, recurso pronto no fim e agenda de prazos da sessão. Métricas de experiência em
  `avaliacao/EXPERIENCIA.md` (6,1 s no pior caso até o número, 2 cliques até copiar). Conferida no navegador no
  modo demo.
- **Testes:** 230 testes passam, incluindo ponta a ponta nos 15 documentos com o cliente falso e as regras da tela
  (semáforo, prioridade, agenda). Isso prova o encanamento, os verificadores e a avaliação, não a qualidade do
  modelo.
- **Instalação do zero:** refeita em 21/10, depois do redesenho da tela: clone do GitHub, ambiente novo,
  `pip install`, 230 testes, os 15 documentos no modo demo sem chave e sem `.env`, e a tela de ponta a ponta no
  navegador (D42).
- **Revisão independente:** um subagente tentou quebrar o projeto. Os 14 achados confirmados foram corrigidos e
  viraram testes em `tests/test_revisao.py` (ver D19 a D28 em `docs/DECISOES.md`).

## Métricas atuais

Com o Claude Haiku 5.5 e o prompt de análise v2, todas as metas foram batidas: recall, valores, decisão,
evidência e casos adversos em 100%. A latência média foi de 20,7 s por documento ao vivo, e o custo, de US$ 0,03
pelos 10 documentos. A primeira versão acertava 78,6% das decisões. A evolução e a leitura honesta desses números
estão em `avaliacao/RESULTADO.md`.

No **conjunto de validação** (5 documentos que o agente nunca viu, com o layout novo D, 18 glosas), rodado uma vez
só e sem ajuste depois, também deu 100% em todas as metas (`avaliacao/VALIDACAO.md`).

## Para a demo

- O app abre com o **modo demo ligado**. O interruptor fica na **barra lateral**, embaixo das páginas. No
  celular, a barra recolhe num menu (o botão » no canto de cima).
- A página **Prazos** mostra só o que foi analisado na sessão e começa vazia. Analise `boreal_01` e
  `adverso_injecao` antes de abri-la, ou clique em "Analisar todos os exemplos".
- O roteiro está na parte 2 do `docs/PITCH.md`. O detalhe técnico de cada análise fica em "Ver detalhes técnicos",
  embaixo da trilha.
- O botão de envio do PDF ("Upload", "200MB per file") é texto fixo do Streamlit e aparece em inglês.
- O nome do produto é **ContraGlosa** (D41). O prompt de sistema ainda diz "Agente de Glosas": trocar exige um prompt
  v2, nova avaliação e cache novo.

## O que está frágil

- **100% em 30 + 18 glosas fictícias não é garantia.** O conjunto de validação reduz o risco de ajuste ao teste, mas
  os dois conjuntos foram desenhados pela equipe. Se a pessoa 2 criar documentos novos no sábado, eles entram num
  conjunto novo, rodado uma vez antes de qualquer ajuste.
- **O verificador já teve dois falsos positivos** (senha e token de carteira com 8 dígitos), ambos corrigidos. A
  medida "recurso aprovado para cada glosa recorrível" agora mostra esse tipo de falha no relatório.
- **O modelo varia.** Duas rodadas iguais da v1 deram 78,6% e 82,1%. Para comparar versões, rode mais de uma vez.
- **Modelo Haiku 5.5.** É o padrão desde 20/10/2026 (D29): mais barato e rápido, mas é o menor modelo. Se a
  avaliação ficar abaixo das metas, teste `AGENTE_ESFORCO=high` ou `AGENTE_MODELO=claude-sonnet-5-5`, sempre medindo
  com `python -m agente.avaliar`. O Haiku não tem fallback de recusa no servidor; uma recusa vira pendência.
- **Filtro de injeção por padrões.** Pega as variantes testadas, mas não toda formulação possível. O prompt de
  sistema e a avaliação são as outras barreiras.
- **Pseudonimização por padrões.** Nome em caixa mista, sem rótulo e solto no texto não é detectado.
- **Classificação de recorribilidade** é proposta da equipe, a validar com especialista.
- **Sem OCR:** página escaneada vai para revisão humana.
- **O visual depende do Streamlit 1.66.** O CSS (`static/estilo.css`) usa a estrutura interna da tela. Por isso o
  `requirements.txt` prende o Streamlit em `>=1.66,<1.67` (D42). Não atualize no sábado.

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
| Métricas de experiência da tela | `python -m agente.experiencia` |
| Testar outra versão de prompt | `AGENTE_PROMPTS=analise=v2 python -m agente.avaliar` |
| Gerar os dados de novo | `python -m dados.gerar` |

A divisão das tarefas está em `docs/TAREFAS-SABADO.md`.
