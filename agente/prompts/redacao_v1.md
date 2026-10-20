Etapa 4 de 4: redação.

Escreva um rascunho de recurso de glosa para cada item abaixo. O faturista vai revisar, completar e enviar pelo
canal da operadora.

Operadora: {operadora}
Data de emissão do demonstrativo: {data_emissao}
Protocolo do lote: {protocolo}

Itens a recorrer, com a análise da etapa anterior:

{itens}

Cada recurso deve ter, nesta ordem:

1. Título: "Recurso de glosa — guia <número>".
2. Identificação: operadora, protocolo do lote, guia, data do atendimento, beneficiário (o token CART), código e
   descrição do procedimento, código da glosa com a descrição oficial, valor apresentado e valor glosado.
3. Pedido: revisão da glosa e pagamento do valor glosado.
4. Argumentação: dois a quatro parágrafos curtos, objetivos e respeitosos, com base só na justificativa e nos
   dados acima.
5. Fundamento: a linha "Fundamento normativo: [FUNDAMENTO A CONFIRMAR]".
6. Documentos anexos: lista.
7. Fechamento com as linhas "Protocolo do recurso: [A PREENCHER]" e
   "Assinatura do responsável: [A PREENCHER]".

Regras:

- Use só valores que aparecem nos dados acima, no formato "R$ 1.234,56".
- Não cite lei, resolução, artigo nem norma.
- Não escreva nome, CPF nem número de carteira; use o token CART como está.
- Não invente datas, números de senha nem documentos que não foram mencionados.

Devolva este JSON:

```json
{{
  "recursos": [
    {{"item": 0, "texto": "texto completo do recurso, com quebras de linha \n"}}
  ]
}}
```
