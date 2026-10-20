"""Pseudonimização antes de qualquer chamada ao LLM.

- CPF sai e vira [CPF];
- nome de beneficiário sai e vira [NOME];
- número de carteira vira um token estável CART-xxxxxxxx (HMAC-SHA256), para o agente
  ainda reconhecer o mesmo beneficiário em linhas diferentes sem ver o número.

A troca é feita linha a linha, então página e linha continuam valendo.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field

from agente.pdf import Linha

# Segredo padrão fixo só para a demo: o token precisa ser o mesmo entre execuções para o cache
# do modo offline funcionar. Em uso real, defina PSEUDONIMO_SEGREDO no .env.
SEGREDO_DEMO = "agente-glosas-demo-akcit-2026"

RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|(?<![\d.])\b\d{11}\b(?![\d.])")
# (?<![\d/.,]) impede começar no ano de uma data ("05/09/2026 4038 ...") ou no meio de um valor
RE_CARTEIRA = re.compile(
    r"(?<![\d/.,])\d{4}[ .]\d{4}[ .]\d{4}[ .]\d{4}(?![\d,])|(?<![\d/.,])\d{12,20}(?![\d,])"
)
RE_TOKEN = re.compile(r"CART-[0-9a-f]{8}")
# palavra de nome em maiúsculas: "MARIA", "DA", ou inicial com ou sem ponto ("F", "F.")
_PALAVRA = r"(?:[A-ZÀ-Ý]{2,}|[A-Z]\.?)(?![\w-])"
RE_NOME_MAIUSC = re.compile(rf"{_PALAVRA}(?:\s+{_PALAVRA}){{1,5}}")
RE_NOME_FIM = re.compile(rf"({_PALAVRA}(?:\s+{_PALAVRA}){{1,5}})$")
RE_NOME_ROTULO = re.compile(
    r"(?:Nome do )?(?:Benefici[aá]rio|Paciente|Nome)\s*[:\-]\s*"
    r"(?P<nome>[A-ZÀ-Ý][A-Za-zÀ-ÿ.]+(?:\s+(?:d[aeo]s?|e|[A-ZÀ-Ý][A-Za-zÀ-ÿ.]*)){1,5})"
)
_CONECTIVOS = {"DE", "DA", "DO", "DOS", "DAS", "E"}
# palavras que encerram o nome: rótulos de campo que costumam vir logo depois dele
_PARADA = {
    "CARTEIRA",
    "CART",
    "CPF",
    "GUIA",
    "SENHA",
    "MATRÍCULA",
    "MATRICULA",
    "CÓDIGO",
    "CODIGO",
    "DATA",
    "PLANO",
    "BENEFICIÁRIO",
    "BENEFICIARIO",
    "TOTAL",
    "VALOR",
    "PROCEDIMENTO",
    "CNS",
}


@dataclass
class Pseudonimizado:
    linhas: list[Linha]
    tokens: dict[str, str] = field(default_factory=dict)  # token -> carteira original
    nomes: set[str] = field(default_factory=set)
    cpfs: int = 0

    def reidentificar(self, texto: str) -> str:
        """Troca os tokens de volta pelo número da carteira. Só para exibir localmente."""
        return RE_TOKEN.sub(lambda m: self.tokens.get(m.group(0), m.group(0)), texto)


def token_carteira(numero: str, segredo: str | None = None) -> str:
    chave = (segredo or os.getenv("PSEUDONIMO_SEGREDO") or SEGREDO_DEMO).encode()
    digitos = re.sub(r"\D", "", numero)
    return "CART-" + hmac.new(chave, digitos.encode(), hashlib.sha256).hexdigest()[:8]


def _limpa_nome(nome: str) -> str:
    partes: list[str] = []
    for p in nome.split():
        if p.upper().strip(".:") in _PARADA or p.startswith(("CART-", "[")):
            break
        partes.append(p)
    while partes and partes[-1].upper() in _CONECTIVOS:
        partes.pop()
    while partes and partes[0].upper() in _CONECTIVOS:
        partes.pop(0)
    return " ".join(partes)


def pseudonimizar(linhas: list[Linha], segredo: str | None = None) -> Pseudonimizado:
    res = Pseudonimizado(linhas=[])
    textos: list[str] = []
    for lin in linhas:
        t = lin.texto
        t, n = RE_CPF.subn("[CPF]", t)
        res.cpfs += n

        def _cart(m: re.Match) -> str:
            tok = token_carteira(m.group(0), segredo)
            res.tokens[tok] = m.group(0)
            return tok

        t = RE_CARTEIRA.sub(_cart, t)
        # nome com rótulo: "Beneficiário: Maria S. Costa"
        for m in RE_NOME_ROTULO.finditer(t):
            nome = _limpa_nome(m.group("nome"))
            if len(nome.split()) >= 2:
                res.nomes.add(nome)
        # nome em maiúsculas logo depois ou logo antes do token da carteira
        for m in RE_TOKEN.finditer(t):
            depois = RE_NOME_MAIUSC.match(t, m.end() + 1) if m.end() < len(t) else None
            if depois:
                res.nomes.add(_limpa_nome(depois.group(0)))
            ma = RE_NOME_FIM.search(t[: m.start()].rstrip())
            if ma:
                res.nomes.add(_limpa_nome(ma.group(1)))
        textos.append(t)
    # segunda passada: o nome some de qualquer lugar onde apareça (observações etc.)
    nomes = sorted((n for n in res.nomes if len(n) >= 5 and " " in n), key=len, reverse=True)
    for lin, t in zip(linhas, textos, strict=True):
        for nome in nomes:
            t = re.sub(re.escape(nome), "[NOME]", t, flags=re.IGNORECASE)
        res.linhas.append(Linha(lin.pagina, lin.linha, t))
    res.nomes = set(nomes)
    return res


def dados_pessoais_restantes(texto: str, nomes: set[str] | None = None) -> list[str]:
    """Lista o que ainda parece dado pessoal em claro no texto (para os verificadores)."""
    achados = []
    if RE_CPF.search(texto):
        achados.append("CPF")
    if RE_CARTEIRA.search(texto):
        achados.append("número de carteira")
    for n in nomes or ():
        if n and re.search(re.escape(n), texto, flags=re.IGNORECASE):
            achados.append(f"nome '{n}'")
    return achados
