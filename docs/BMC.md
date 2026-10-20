# Business Model Canvas — Agente de Glosas

Versão da equipe para o hackathon. Onde depende de pesquisa de mercado ou das entrevistas, o campo diz
`[A CONFIRMAR COM DADO/ENTREVISTA]`. Nenhum número aqui foi inventado.

## 1. Segmentos de clientes

- **Principal:** clínicas médicas pequenas e médias que atendem por convênio e fazem o próprio faturamento.
- **Usuário:** o faturista ou a pessoa do administrativo que confere demonstrativos e recorre de glosas.
- **Decisor:** sócio médico ou gestor da clínica.
- **Depois:** empresas terceirizadas de faturamento, que atendem várias clínicas.
- Quantas clínicas, quantos demonstrativos por mês e quanto tempo cada um leva:
  `[A CONFIRMAR COM DADO/ENTREVISTA]`.

## 2. Proposta de valor

- **Menos glosa perdida por prazo:** o painel mostra o prazo final de cada demonstrativo e destaca os próximos 10
  dias.
- **Menos horas de análise:** o agente lê qualquer layout, aponta cada glosa com página e linha e já entrega o
  rascunho do recurso.
- **Confiança:** cada número é conferido pelo código, cada código pela Tabela 38 oficial, e o que é incerto vai para
  revisão humana com o motivo.
- **Privacidade:** dados pessoais saem do texto antes do modelo.
- O que muda na rotina e quanto tempo economiza: `[A CONFIRMAR COM DADO/ENTREVISTA]`. Não prometemos percentual de
  recuperação.

## 3. Canais

- Venda direta para clínicas da região, começando por Goiânia.
- Parceria com contadores e empresas de faturamento, que já falam com essas clínicas.
- Associações e sindicatos de clínicas e de prestadores: `[A CONFIRMAR COM DADO/ENTREVISTA]`.
- Teste gratuito com os demonstrativos do último mês.

## 4. Relacionamento

- Onboarding assistido no primeiro mês: configurar as operadoras e os prazos do contrato da clínica.
- Suporte por mensagem.
- Relatório mensal: glosas encontradas, recursos enviados, prazos cumpridos.

## 5. Fontes de receita

- Assinatura mensal por clínica, com faixas por volume de demonstrativos.
- Alternativa a testar: valor por demonstrativo analisado.
- Preço: `[A CONFIRMAR COM DADO/ENTREVISTA]`. Não definimos preço sem ouvir as clínicas.

## 6. Recursos principais

- O agente: orquestrador, prompts versionados, verificadores e avaliação contra gabarito.
- A base de conhecimento: Tabela 38 oficial e regras de recurso validadas por especialista.
- O conjunto de avaliação, que cresce com cada layout novo.
- A equipe: desenvolvimento e conhecimento de faturamento.

## 7. Atividades principais

- Manter a Tabela 38 e a base atualizadas a cada versão do Padrão TISS.
- Aprender layouts novos de operadoras e medir a qualidade a cada mudança.
- Validar a classificação de recorribilidade com especialistas em faturamento.
- Garantir segurança e LGPD.

## 8. Parcerias principais

- Especialistas em faturamento médico, para validar as regras.
- Contadores e empresas de faturamento, como canal.
- Provedor do modelo de linguagem (Anthropic).
- Jurídico, para os fundamentos normativos dos recursos.

## 9. Estrutura de custos

- Custo de API por demonstrativo: medido pela trilha do agente em `avaliacao/RESULTADO.md`.
- Hospedagem e armazenamento.
- Desenvolvimento e manutenção.
- Validação com especialistas.
- Aquisição de clientes.
- Valores: `[A CONFIRMAR COM DADO/ENTREVISTA]`.

## Contexto de mercado com fonte

- 53.055.406 beneficiários em planos de assistência médica em junho de 2026 e 667 operadoras médico-hospitalares com
  beneficiários em agosto de 2026
  ([ANS, Dados Gerais](https://www.gov.br/ans/pt-br/acesso-a-informacao/perfil-do-setor/dados-gerais), acesso em
  20/10/2026).
- Tamanho do mercado de clínicas pequenas e taxa de glosa: `[A CONFIRMAR COM DADO/ENTREVISTA]`.
