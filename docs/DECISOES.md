# Decisões

Registro curto das decisões tomadas durante a construção. Uma linha de contexto, a decisão e o porquê.

## E0 — Repositório e ambiente

- **D01 · Pasta do repositório.** O plano previa `D:\Hackathon\agente-glosas`. A sessão de trabalho foi aberta em
  `D:\HackathonGlosas`, que também fica fora de `D:\AS-Sistemas\`. O repositório nasce nessa pasta.
- **D02 · Código reaproveitado: nenhum.** O repositório indicado para reaproveitamento (`ArtTech-cloud/ContraGlosa`)
  estava vazio no GitHub em 20/10/2026, sem nenhum branch. Nenhum outro código foi usado: todo o código aqui foi
  escrito do zero, respeitando a regra de separação do `CLAUDE.md`.
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

## E7.1 — Revisão independente

Um subagente que não escreveu o código revisou o projeto contra o `PLANO.md` e o `CLAUDE.md` e tentou quebrá-lo.
Tudo o que ele confirmou foi corrigido, com um teste de regressão em `tests/test_revisao.py`.

- **D19 · Evidência mais estrita.** Antes, a linha citada só precisava conter os valores apresentado e glosado como
  substring, e a guia em qualquer ponto da página. Trocar guia e código entre dois itens de mesmo valor passava.
  Agora os três valores precisam estar na linha como números inteiros, o código de glosa na linha ou logo abaixo, e
  a guia até 6 linhas acima.
- **D20 · Decisão duplicada vira revisão humana.** Antes, a primeira decisão de um item repetido valia em silêncio.
- **D21 · Fonte precisa ter vindo de uma ferramenta.** Uma fonte que existe na base mas não foi consultada na análise
  (por exemplo, `op-boreal` num documento da Aurora) é recusada.
- **D22 · Triagem conferida contra o PDF.** A data de emissão e a operadora lidas pelo modelo precisam estar escritas
  no documento. Se não estiverem, o prazo não é calculado e vira pendência. Assim o prazo continua sendo do código.
- **D23 · Pseudonimização ampliada.** Cobre rótulos no feminino, "Titular", "Nome do paciente", CPF em 5 formatos,
  carteira com hífen ou barra, CNS, e-mail e telefone. O nome também é trocado sem acento e na forma "primeiro +
  último". Número rotulado como guia, protocolo, lote ou senha não vira token. **Limitação conhecida:** nome em caixa
  mista sem rótulo e longe da carteira ("Rafael Barbosa Pereira" solto numa observação) não é detectado. Isso está nas
  Limitações do README.
- **D24 · Verificador de recurso ampliado.** Detecta dinheiro em qualquer formato ("R$ 500", "R$ 500.00", "R$ 12,5")
  e recusa o que não estiver no formato brasileiro ou não for um valor do próprio item. Recusa valor por extenso e
  outra moeda, e mais formas de citação normativa ("RN/ANS 395", "Lei dos Planos de Saúde", "§", "inciso", "CDC"...).
  Recusa código de glosa ou de procedimento fora das tabelas oficiais.
- **D25 · Filtro de injeção revisto.** Pega mais formas, inclusive inglês, homoglifo cirílico, "[INST]" e instrução
  quebrada em duas linhas. Deixou de marcar texto normal ("Modelo: Demonstrativo", "Você deve enviar o recurso em até
  30 dias"). O corte vai até o fim da frase ou o próximo valor e preserva os dados de um item na mesma linha.
- **D26 · Robustez de entrada.** Bloco de ferramenta malformado, JSON muito aninhado, dois blocos JSON, zero itens,
  PDF com BOM, caminho inexistente e PDF com senha viram pendência ou erro tratado, nunca exceção na tela. Uma falha
  interna inesperada também vira pendência e a trilha é gravada.
- **D27 · Dinheiro sem ambiguidade.** `parse_brl` aceita só dígitos ASCII e um sinal; valor de item não pode ser
  negativo.
- **D28 · `PSEUDONIMO_SEGREDO` vazio na demo.** O `.env.example` agora diz para deixar vazio: um segredo diferente muda
  os tokens e o modo demo não acha o cache.

## Depois da entrega da E7

- **D29 · Modelo padrão: `claude-haiku-5-5`.** Decisão do Arthur em 20/10/2026, no lugar do `claude-sonnet-5-5`.
  O custo cai de US$ 2 / US$ 10 para US$ 0,10 / US$ 0,50 por milhão de tokens de entrada e saída, para prompts de até
  100K tokens, e a latência também cai. O Haiku 5.5 não tem fallback de recusa no servidor: a documentação diz para não
  enviar `fallbacks`, então o cliente deixa de enviar esse parâmetro para modelos Haiku (D10 continua valendo para
  Sonnet e Opus). O pensamento adaptativo fica ligado, porque a documentação avisa que, com ele desligado, o Haiku pode
  pular uma chamada de ferramenta necessária quando a resposta também precisa sair em JSON. `CLAUDE.md`, `PLANO.md`
  e `.env.example` foram atualizados. As metas da avaliação não mudam.

## E4 — Avaliação com o modelo real

- **D30 · Dados corrigidos pelo que o agente apontou.** Na primeira avaliação, o agente mandou para revisão humana a
  glosa 1006 (beneficiário desligado) do `aurora_01`. O motivo: o mesmo beneficiário tinha outro exame pago no mesmo
  dia, na mesma guia. Ele estava certo, e o erro era dos dados fictícios. O `adverso_injecao` tinha a mesma falha. Nos
  dois, o exame da mesma guia passou a ser glosado também com 1006. O total de glosas foi de 28 para 30. As duas
  primeiras linhas da evolução usam os dados antigos.
- **D31 · Prompt de análise v2 como padrão.** Com o v1, o Haiku pedia revisão humana em códigos "sim" e "não" por
  falta de informação, e exigia a validade da senha no código 1818. O v2 manda seguir o critério desses códigos e
  usar só o que o critério pede. A nota de autorização da base também ficou explícita. Decisão: de 90% para 100%.
  Risco: o ajuste foi feito olhando os erros do mesmo conjunto de avaliação.
- **D32 · Falso positivo no verificador de recurso.** A regra nova da D24, que recusa código de 8 dígitos fora da
  Tabela 22, recusou uma senha de autorização de 8 dígitos. Agora a senha do item e números rotulados como senha ou
  autorização são aceitos, com teste de regressão.
- **D33 · Cache do modo demo.** O cache em `cache/` foi gerado pelas rodadas reais da avaliação. Ele cobre a
  configuração padrão (análise v2) dos 10 documentos e também as respostas da v1. Nenhum arquivo do cache tem dado
  pessoal (conferido com `dados_pessoais_restantes`). Custo de API do desenvolvimento até aqui: cerca de US$ 0,15.

## Depois da E7 — itens restantes

- **D34 · E5.5 (ler página escaneada com a visão do modelo) não será feita.** Ela conflita com uma regra fixa do
  `CLAUDE.md`: antes de qualquer chamada ao LLM, nome e CPF saem do texto. Numa imagem não há como retirar esses dados
  sem OCR, e OCR está fora do escopo. Mandar a imagem ao modelo exporia nome, CPF e carteira. A página sem texto segue
  indo para revisão humana com a pendência `pagina_ilegivel`. Se a equipe quiser a E5.5, o caminho é OCR local para
  achar e tarjar os dados pessoais antes, o que exige uma dependência nova.
- **D35 · Conjunto de validação separado.** O 100% da avaliação foi medido no mesmo conjunto usado para ajustar o
  prompt de análise v2. Para saber se o agente generaliza, foram criados 5 documentos novos em `dados/validacao/`, com
  um quarto layout (D, modelo novo da Aurora) e combinações de cenários que o agente nunca viu. A regra: este conjunto
  é rodado com a configuração já escolhida e **não é usado para ajustar prompt nem base**. O resultado fica em
  `avaliacao/VALIDACAO.md`, separado do `RESULTADO.md`.
