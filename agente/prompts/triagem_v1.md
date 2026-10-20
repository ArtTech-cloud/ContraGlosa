Etapa 1 de 4: triagem.

Leia o início do documento abaixo e identifique o que ele é.

<documento>
{documento}
</documento>

Devolva este JSON:

```json
{{
  "tipo_documento": "demonstrativo_retorno ou outro",
  "operadora": "nome da operadora como impresso",
  "competencia": "mês de referência como impresso, ou null",
  "data_emissao": "data de emissão do demonstrativo em dd/mm/aaaa, ou null se não houver",
  "protocolo": "número do protocolo do lote, ou null",
  "legivel": true,
  "observacao": "frase curta sobre algo incomum, ou string vazia"
}}
```

- "demonstrativo_retorno" vale para demonstrativo de análise de conta, de pagamento ou relatório de retorno de
  faturamento com itens cobrados e glosados. Qualquer outro documento é "outro".
- A data de emissão pode aparecer como "Data de emissão", "Emitido em", "Data do demonstrativo" ou parecido.
- "legivel" é false se o texto estiver tão truncado que não dá para identificar itens e valores.
