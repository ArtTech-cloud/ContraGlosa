# Tarefas de sábado, 24/10/2026 — 9h às 15h30

Quatro pessoas, quatro frentes. **Congelamento às 15h30:** tudo no GitHub.

## Marcos do dia

| Hora | Marco |
|---|---|
| 9h00 | todos com o projeto rodando (ver "como começar") |
| 10h00 | conversa com o mentor; a pessoa 1 anota os ajustes |
| 13h30 | congelar funcionalidades: daí em diante, só correção de defeito |
| 14h30 | ensaio geral do pitch com a demo |
| 15h15 | conferir o GitHub: README, BMC, pitch, fluxo, código, `avaliacao/RESULTADO.md` e `avaliacao/EXPERIENCIA.md` |
| 15h30 | congelamento |

## Para todos: como começar em 15 minutos

```bash
git clone https://github.com/ArtTech-cloud/ContraGlosa.git
```

```bash
cd ContraGlosa
```

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
python -m pytest -q
```

```bash
streamlit run app.py
```

Leia nesta ordem: `docs/CONTEXTO.md`, `README.md` e `docs/fluxo.md`.

**A tela, em 1 minuto.** O app abre na página **Início**, com o modo demo ligado: as respostas vêm de `cache/`, sem
internet e sem chave. O interruptor fica em **Ajustes**, no canto do cabeçalho. As páginas são:

| Página | O que mostra |
|---|---|
| Início | enviar um PDF ou ver um exemplo; a trilha do agente ao vivo; quanto pode ser recorrido; as glosas com semáforo e a prova; os recursos prontos |
| Prazos | a agenda das glosas recorríveis **analisadas nesta sessão**. Começa vazia: analise algo antes ou clique em "Analisar todos os exemplos" |
| Pendências | o que foi para revisão humana, com o motivo |
| Como funciona | o fluxo do agente e o contrato de cada etapa |
| Qualidade | as métricas contra o gabarito, a validação e a experiência de uso |

## Pessoa 1 — agente e avaliação

- **Objetivo:** melhorar as métricas com os ajustes do mentor das 10h.
- **Arquivos:** `agente/prompts/`, `agente/orquestrador.py`, `agente/avaliar.py`, `avaliacao/RESULTADO.md`.
- **Primeira tarefa (pequena):** rode `python -m agente.avaliar --docs aurora_01` e leia a trilha em `.runs/`.
- **Para mudar um prompt:** copie `analise_v1.md` para `analise_v2.md`, edite, rode com `AGENTE_PROMPTS=analise=v2` e
  compare. A avaliação completa registra a evolução no relatório. Nunca baixe uma meta.
- **Cuidado com o custo:** cada avaliação completa custa o que está no fim do relatório. Avise o Arthur se o total
  passar de US$ 20.
- **Depois da última avaliação boa:** confirme que o cache em `cache/` foi atualizado e faça o commit dele. Sem isso,
  o modo demo não funciona com o prompt novo.
- **Perguntas da banca para saber responder:**
  - "Como vocês sabem que funciona?" (métricas e gabarito)
  - "E se o modelo inventar um valor?" (verificadores)
  - "Por que 4 etapas e não um agente só?" (cada etapa com prompt, ferramentas e validação próprios)

## Pessoa 2 — dados e casos adversos

- **Objetivo:** mais robustez: novas variações de layout e novos casos adversos.
- **Arquivos:** `dados/gerar.py`, `dados/operadoras.yaml`, `agente/guardrails.py`, `agente/pseudonimo.py`, `tests/`.
- **Primeira tarefa (pequena):** acrescente uma frase de injeção nova em `tests/test_pseudonimo.py`
  (`test_injecao_variantes`) e veja se o filtro pega. Se não pegar, ajuste `agente/guardrails.py`.
- **Regra:** códigos só das tabelas oficiais em `dados/tabela38/` e `dados/tabela22/`. Rode `python -m dados.gerar`
  e `python -m pytest -q` depois de qualquer mudança. Documento novo precisa de cache novo (pessoa 1).
- **Perguntas da banca para saber responder:**
  - "O que acontece com entrada inesperada?" (os 4 casos adversos)
  - "De onde vêm os códigos?" (Tabela 38 oficial da ANS, com SHA-256)
  - "E se o PDF tiver uma instrução escondida?" (filtro, prompt de sistema e avaliação)

## Pessoa 3 — interface e demo

- **Objetivo:** demo clara em 60 segundos e vídeo de backup.
- **Arquivos:** `app.py`, `static/estilo.css`, `docs/PLANO-FRONT.md` (o que cada tela precisa responder e a lista
  do que é proibido) e `docs/PITCH.md` (parte 2, o roteiro da demo).
- **Primeira tarefa (pequena):** siga o roteiro da parte 2 do pitch com `boreal_01` e `adverso_injecao` e anote o que
  confunde quem vê pela primeira vez.
- **Até 13h30:** polimento. O visual está em `static/estilo.css` e `.streamlit/config.toml` (D38); ajuste ali,
  sem espalhar estilo pelo `app.py`. As regras que decidem algo na tela (semáforo, ordem das glosas, agenda) estão em
  `agente/consolidar.py`, com testes: mude ali, não no `app.py`. Depois de mexer na tela, rode
  `python -m agente.experiencia` e confira o tempo e os cliques. Depois das 13h30, só correção.
- **Cuidado:** o CSS usa a estrutura interna do Streamlit e foi testado na versão do `requirements.txt`. Não
  atualize o Streamlit no sábado.
- **Até 14h30:** grave o vídeo de backup da demo (2 minutos), seguindo o roteiro do pitch, e salve no notebook e no
  celular. Antes de gravar, analise `boreal_01` e `adverso_injecao`, para a página Prazos ter o que mostrar.
- **Perguntas da banca para saber responder:**
  - "Mostre o fluxo do agente." (trilha ao vivo)
  - "Onde está a evidência dessa decisão?" (clique na glosa: página, linha e fonte)
  - "Posso confiar nisso?" (semáforo: 🟢 só quando a confiança é alta e todos os verificadores aprovaram)
  - "Funciona sem internet?" (modo demo com cache)

## Pessoa 4 — pitch e BMC

- **Objetivo:** pitch de 3 minutos ensaiado 3 vezes, com as entrevistas da semana.
- **Arquivos:** `docs/PITCH.md`, `docs/BMC.md`, `docs/ROTEIRO-ENTREVISTA.md`.
- **Primeira tarefa (pequena):** passe as anotações das entrevistas para a tabela do roteiro e escolha 2 frases
  literais para o pitch.
- **Regras:** número de mercado só com fonte e link. Não prometa percentual de recuperação. Campos sem dado ficam
  `[A CONFIRMAR COM DADO/ENTREVISTA]`.
- **Perguntas da banca para saber responder:**
  - "Quem é o cliente e quem paga?" (persona e BMC)
  - "Vocês falaram com clientes?" (entrevistas, com números citados por eles)
  - "Qual o diferencial?" (domínio embutido e agente fiscalizado por código)

## O que está pronto e o que está frágil

Ver `docs/ESTADO.md`, que é atualizado no fim da construção.
