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

## E1 a E5 — Agente, dados e interface

- **D08 · JSON validado pelo código, não pela API.** Cada etapa pede JSON no texto, e o código valida com pydantic.
  Se falhar, refaz com o erro como contexto, até 2 vezes. Isso deixa o retry visível na trilha, como pede o plano, e
  não depende de recursos da API que não puderam ser testados sem chave no dia da construção.
- **D09 · Ferramentas extras: `consultar_operadora` e `calcular_intervalo`.** O valor contratado e o intervalo de
  retorno de cada operadora fictícia vêm de `dados/operadoras.yaml` por uma ferramenta de código, e os dias entre
  datas são calculados pelo código. Assim o modelo não faz conta de cabeça. O prazo final de recurso é calculado só
  pelo código, no painel (`prazo_recurso`).
- **D10 · Fallback de recusa ligado por padrão.** As chamadas usam `fallbacks: "default"` (beta
  `server-side-fallback-2026-07-01`), como a documentação recomenda para o Sonnet 5.5. Se a conta não tiver acesso
  ao beta, o cliente desliga o fallback sozinho e segue. `AGENTE_FALLBACK=0` desliga.
- **D11 · `pandas` e `Pillow` sem entrada nova no requirements.** O `pandas` já vem com o Streamlit e é usado só nas
  tabelas da tela. O `Pillow` já vem com o `pdfplumber` e é usado só pelo gerador, para desenhar a página escaneada
  do caso adverso.
- **D12 · Segredo padrão do token da carteira.** Sem `PSEUDONIMO_SEGREDO`, o HMAC usa um segredo fixo de demo. O token
  precisa ser estável para o cache do modo offline funcionar. Em uso real, o segredo deve ser definido no `.env`.
- **D13 · "Depende" sem evidência vira revisão humana.** No gabarito, um código com recorribilidade "depende" é
  "recorrer" ou "não recorrer" quando o documento traz a evidência (datas, senha, valor contratado), e
  "revisão humana" quando não traz. O agente segue a mesma regra no prompt.
- **D14 · Evidência é a linha dos valores.** Página e linha de um item apontam para a linha onde estão o valor
  apresentado e o glosado. O verificador confere se esses valores estão nessa linha e se o código do procedimento e a
  guia estão por perto. Nos três layouts isso é inequívoco.
- **D15 · Soma não conferida quando há página sem texto.** Se uma página não tem texto, os totais impressos incluem
  itens que o agente não pode ler. Nesse caso a soma não é conferida, e a pendência é `pagina_ilegivel`, não
  `soma_divergente`.
- **D16 · Oráculo só nos testes.** `tests/oraculo.py` responde a partir do gabarito, para testar o encanamento e a
  avaliação sem gastar API. Ele nunca é usado pelo app nem pela avaliação, e o cache do modo demo só pode ser gerado
  pelo modelo real (`python -m agente.avaliar`).
- **D17 · Código inexistente nunca chega ao modelo.** O código consulta a Tabela 38 antes da análise. Código que não
  existe vai direto para revisão humana com a pendência `codigo_inexistente`, sem dar ao modelo a chance de adivinhar.
- **D18 · Confiança baixa e evidência que não confere bloqueiam o recurso.** Decisão com confiança baixa vira revisão
  humana, com a sugestão do agente registrada. Item cuja evidência não conferiu não recebe recurso automático.
