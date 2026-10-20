# Fontes

Toda fonte externa usada no projeto, com URL, data de acesso e o que se tirou dela.

## Tabelas oficiais da ANS

| O quê | URL | Acesso | Verificação |
|---|---|---|---|
| Padrão TISS 202609, componente "Representação de Conceitos em Saúde" (ZIP) | https://www.ans.gov.br/arquivos/extras/tiss/Padrao_TISS_Representacao_de_Conceitos_em_Saude_202609.zip | 20/10/2026 | SHA-256 `7f3d7a9794a8929fddd6f13af26dd9496087bf8b8670f275bd7ecd9a2f64172d` |

- **Tabela 38, mensagens de glosa.** Planilha `TUSS - Demais terminologias - VERSÃO 202609.xlsx`, aba `Tab 38`.
  Extraída para `dados/tabela38/tabela38.csv`, com 470 códigos. Detalhes em `dados/tabela38/fonte.json`.
- **Tabela 22, procedimentos e eventos em saúde.** Planilha `TUSS 22 - PROCEDIMENTOS E EVENTOS EM SAÚDE - VERSÃO
  202609.xlsx`. Extraída para `dados/tabela22/tabela22.csv`, com 5.969 códigos. Detalhes em
  `dados/tabela22/fonte.json`.
- Para refazer a extração: baixe o ZIP e rode `python -m dados.tabela38.extrair CAMINHO_DO_ZIP`.

## Base de conhecimento (base/)

| O quê | URL | Acesso | Verificação |
|---|---|---|---|
| Padrão TISS, Componente Organizacional, setembro/2026 | https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss/PadroTISS_ComponenteOrganizacional_202609.pdf | 20/10/2026 | SHA-256 `fc973a683f772143d3355604e6e0566491756c49c657e1b12b0b33564d63d2d3` |

- Usado em `base/tiss_conceitos.md`: itens 31 a 33 (processos), 49 (demonstrativos de retorno), 50 (envio de
  documentos), 51 (recurso de glosa), 55 e 56 (protocolo e conteúdo do demonstrativo de análise de conta), 102 e 103
  (Tabela 38). Os trechos são resumos da equipe, não transcrição.
- O componente não traz definição de glosa "administrativa" e "técnica" nem um prazo único de recurso. As notas
  sobre isso em `base/notas_dominio.md` dizem que são proposta da equipe.
- O componente cita a RN 501 da ANS como base do padrão. A equipe **não verificou** a vigência dessa norma, então ela
  não é citada nos recursos (regra do `CLAUDE.md`).

## Números de mercado (README, BMC, pitch)

| Número | Fonte | Acesso |
|---|---|---|
| 53.055.406 beneficiários em planos de assistência médica, junho/2026 | [ANS, Dados Gerais](https://www.gov.br/ans/pt-br/acesso-a-informacao/perfil-do-setor/dados-gerais) ("Atualizado em 05/10/2026", "Dados atualizados até 08/2026") | 20/10/2026 |
| 667 operadoras médico-hospitalares com beneficiários, agosto/2026 | mesma página | 20/10/2026 |

## Documentação técnica

| O quê | URL | Acesso | Uso |
|---|---|---|---|
| Claude Code, permissões | https://code.claude.com/docs/en/permissions | 20/10/2026 | sintaxe do `deny` de leitura no Windows |
| Apache License 2.0 | https://www.apache.org/licenses/LICENSE-2.0.txt | 20/10/2026 | texto do `LICENSE` |
| Claude API, Python SDK (tool use, saída estruturada, fallbacks) | documentação oficial embarcada no Claude Code (skill claude-api) e https://docs.claude.com | 20/10/2026 | `agente/llm.py` |
