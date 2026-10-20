Etapa 3 de 4: análise.

Decida, para cada glosa listada, se vale recorrer.

Contexto do demonstrativo:
- operadora: {operadora}
- data de emissão: {data_emissao}

Todos os itens extraídos (o índice identifica o item):

{itens}

Glosas a analisar (índices): {glosas}

Documento completo, para conferir observações, senhas e outras linhas:

<documento>
{documento}
</documento>

Ferramentas disponíveis:
- consultar_t38: confirma o código de glosa na Tabela 38 oficial e traz o critério de demonstração.
- consultar_operadora: prazo de recurso, valor contratado da consulta e intervalo de retorno da operadora.
- calcular_intervalo: dias entre duas datas, calculados pelo código.
- buscar_base: trechos da base de conhecimento, cada um com um id.

Como decidir:

1. Chame consultar_t38 para cada código de glosa.
2. Siga o critério de recorribilidade do código ("recorribilidade" em classificacao_demo):
   - "sim": decida "recorrer". Os documentos típicos são anexados pelo faturista depois; não é preciso que o PDF
     os mostre. Só não recorra se o próprio documento mostrar que a glosa procede.
   - "nao": decida "nao_recorrer". Só mude se o documento trouxer evidência explícita de que a glosa está errada.
     Falta de informação no documento não é motivo para revisão humana nesses códigos.
   - "depende": aplique o critério do código à evidência do documento. Se a evidência que o critério pede não
     estiver no documento, a decisão é "revisao_humana" e a justificativa diz o que conferir.
3. Use só o que o critério do código pede. Não acrescente exigências que ele não menciona: por exemplo, se o
   critério pede apenas que exista senha de autorização, não exija a validade da senha.
4. Quando o critério depender de datas ou valores, use as ferramentas: consultar_operadora para o intervalo de
   retorno e o valor contratado, e calcular_intervalo para os dias entre datas. Não faça contas de cabeça.
5. Procure a evidência no próprio documento: outra consulta do mesmo token CART, outra cobrança do mesmo
   procedimento, uma senha de autorização e a validade dela.
6. Cite em "fontes" os ids dos trechos que sustentam a decisão. Use os ids "t38-XXXX" e "op-xxx" e os de
   buscar_base. Só cite id que apareceu em resultado de ferramenta.

Devolva este JSON, com exatamente uma decisão por glosa listada:

```json
{{
  "decisoes": [
    {{
      "item": 0,
      "decisao": "recorrer, nao_recorrer ou revisao_humana",
      "confianca": "alta, media ou baixa",
      "justificativa": "duas a quatro frases, citando a evidência do documento",
      "fontes": ["t38-1509"],
      "documentos": ["documentos que o faturista deve anexar ao recurso"]
    }}
  ]
}}
```

Confiança: "alta" quando o critério e a evidência são claros, inclusive quando você segue um critério "sim" ou
"nao" sem evidência em contrário; "media" quando há evidência mas alguma
interpretação; "baixa" quando você está em dúvida. Confiança baixa vai para revisão humana.
