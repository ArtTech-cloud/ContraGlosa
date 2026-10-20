# Decisões

Registro curto das decisões tomadas durante a construção. Uma linha de contexto, a decisão e o porquê.

## E0 — Repositório e ambiente

- **D01 · Pasta do repositório.** O plano previa `D:\Hackathon\agente-glosas`. A sessão de trabalho foi aberta em
  `D:\HackathonGlosas`, que também fica fora de `D:\AS-Sistemas\`. O repositório nasce nessa pasta.
- **D02 · Código reaproveitado: nenhum.** O repositório indicado para reaproveitamento (`ArtTech-cloud/ContraGlosa`)
  estava vazio no GitHub em 20/10/2026, sem nenhum branch. O único `glosas-mvp` encontrado na máquina é um ZIP cujo
  histórico aponta para `D:\AS-Sistemas\glosas-mvp`, que é projeto da A&S. A regra de separação do `CLAUDE.md` proíbe
  ler ou copiar esse material, então ele não foi aberto. Todo o código aqui foi escrito do zero.
- **D03 · Bloqueio de `D:\AS-Sistemas`.** `.claude/settings.json` tem `deny` de `Read` e `Edit` para
  `//d/AS-Sistemas/**` (e a variação com `D` maiúsculo). A documentação do Claude Code diz que, no Windows, os caminhos
  são normalizados para a forma POSIX (`C:\Users` vira `/c/Users`) e que `//` marca caminho absoluto. Testado em
  20/10/2026: a ferramenta Read recusou um arquivo dentro da pasta. A regra cobre as ferramentas de arquivo, não
  comandos de shell; a disciplina para o shell é do próprio agente.
- **D04 · Licença.** `LICENSE` é o texto oficial da Apache-2.0, baixado de apache.org, sem alteração. O titular
  provisório ("Equipe Agente de Glosas — AKCIT Camp 2026") está no arquivo `NOTICE`, como o apêndice da licença
  recomenda. **A equipe precisa confirmar o titular.**
- **D05 · Dependência extra: `python-dotenv`.** Carrega o `.env` com a chave da API sem exigir que cada pessoa da
  equipe exporte variáveis no terminal. Pequena e sem dependências próprias.
- **D06 · Extração das tabelas da ANS só com a biblioteca padrão.** Um `.xlsx` é um ZIP de XML; ler com `zipfile` e
  `xml.etree` evita adicionar `openpyxl` ou `pandas`.
- **D07 · Tabela 22 também vem do arquivo oficial.** Os itens dos demonstrativos fictícios têm código de procedimento.
  O mesmo ZIP da ANS traz a Tabela 22 (procedimentos), então os códigos de procedimento também são extraídos dela,
  pelo mesmo princípio da Tabela 38: nada de memória.
