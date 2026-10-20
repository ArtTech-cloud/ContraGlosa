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

## Documentação técnica

| O quê | URL | Acesso | Uso |
|---|---|---|---|
| Claude Code, permissões | https://code.claude.com/docs/en/permissions | 20/10/2026 | sintaxe do `deny` de leitura no Windows |
| Apache License 2.0 | https://www.apache.org/licenses/LICENSE-2.0.txt | 20/10/2026 | texto do `LICENSE` |
