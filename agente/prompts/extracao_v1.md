Etapa 2 de 4: extração.

Extraia todos os itens cobrados do demonstrativo abaixo, com e sem glosa, e os totais impressos. Os layouts mudam
de uma operadora para outra: a ordem das colunas, os rótulos e a posição dos totais variam. Leia pelo sentido, não
por posição fixa.

<documento>
{documento}
</documento>

Devolva este JSON:

```json
{{
  "itens": [
    {{
      "pagina": 1,
      "linha": 9,
      "guia": "número da guia",
      "data_atendimento": "dd/mm/aaaa",
      "beneficiario": "token CART-xxxxxxxx do beneficiário",
      "codigo_procedimento": "8 dígitos",
      "descricao": "descrição do procedimento como impressa",
      "quantidade": 1,
      "valor_apresentado": "valor cobrado pelo prestador",
      "valor_glosado": "valor glosado ou recusado",
      "valor_pago": "valor pago, liberado ou aceito",
      "codigo_glosa": "4 dígitos do motivo da glosa, ou null se não houver",
      "motivo_glosa": "texto do motivo, se impresso, ou null",
      "observacao": "observação ligada a este item ou à sua guia, ou null",
      "senha": "senha de autorização ligada ao item ou à guia, ou null"
    }}
  ],
  "totais": {{
    "valor_apresentado": "total apresentado/informado/cobrado impresso, ou null",
    "valor_glosado": "total glosado/recusado impresso, ou null",
    "valor_pago": "total pago/liberado/aceito impresso, ou null",
    "pagina": 1,
    "linha": 13
  }}
}}
```

Regras:

- "pagina" e "linha" do item são as da linha onde estão os valores do item (apresentado e glosado).
- Copie os valores exatamente como impressos, sem "R$": "135,00", "1.234,56". Valor glosado zero é "0,00".
- Sinônimos comuns: apresentado = informado = cobrado; pago = liberado = aceito; glosado = recusado.
- Quando o beneficiário aparece só no cabeçalho da guia, repita o token dele em cada item da guia.
- Um mesmo procedimento pode aparecer duas vezes. Extraia cada ocorrência como um item separado.
- Não pule itens. Não some nem calcule valores: o código confere a soma depois.
- Se o documento tiver uma página sem texto, extraia apenas o que está nas páginas com texto.
