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
import unicodedata
from dataclasses import dataclass, field

from agente.pdf import Linha

# Segredo padrão fixo só para a demo: o token precisa ser o mesmo entre execuções para o cache
# do modo offline funcionar. Em uso real, defina PSEUDONIMO_SEGREDO no .env.
SEGREDO_DEMO = "agente-glosas-demo-akcit-2026"

_SEP = r"[ .\-/]"
# carteira: 16 dígitos agrupados de 4 em 4 (espaço, ponto, hífen ou barra) ou 12 a 20 dígitos seguidos.
# (?<![\d/.,]) impede começar no ano de uma data ("05/09/2026 4038 ...") ou no meio de um valor.
RE_CARTEIRA = re.compile(
    rf"(?<![0-9/.,])[0-9]{{4}}{_SEP}[0-9]{{4}}{_SEP}[0-9]{{4}}{_SEP}[0-9]{{4}}(?![0-9,])"
    r"|(?<![0-9/.,])[0-9]{12,20}(?![0-9,])"
)
# CNS (Cartão Nacional de Saúde) agrupado 3-4-4-4
RE_CNS = re.compile(r"(?<![0-9/.,])[0-9]{3}[ .][0-9]{4}[ .][0-9]{4}[ .][0-9]{4}(?![0-9,])")
# CPF: 123.456.789-01, 123.456.789.01, 123 456 789 01, 123456789-01 ou 12345678901
RE_CPF = re.compile(
    r"(?<![0-9])(?:[0-9]{3}\.[0-9]{3}\.[0-9]{3}[-.][0-9]{2}|[0-9]{3} [0-9]{3} [0-9]{3}[ -][0-9]{2}"
    r"|[0-9]{9}-[0-9]{2}|[0-9]{11})(?![0-9])"
)
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_TELEFONE = re.compile(r"(?<![0-9])(?:\(?[0-9]{2}\)?\s?)?9?[0-9]{4}-[0-9]{4}(?![0-9])")
# número com rótulo de guia, protocolo, lote ou senha não é carteira
RE_ROTULO_NAO_CARTEIRA = re.compile(
    r"(guia|protocolo|lote|senha|autoriza\w*)\W{0,3}(n[ºo°.]*\s*)?$", re.IGNORECASE
)
RE_TOKEN = re.compile(r"CART-[0-9a-f]{8}")
# palavra de nome em maiúsculas: "MARIA", "DA", ou inicial com ou sem ponto ("F", "F.")
_PALAVRA = r"(?:[A-ZÀ-Ý]{2,}|[A-Z]\.?)(?![\w-])"
RE_NOME_MAIUSC = re.compile(rf"{_PALAVRA}(?:\s+{_PALAVRA}){{1,5}}")
RE_NOME_FIM = re.compile(rf"({_PALAVRA}(?:\s+{_PALAVRA}){{1,5}})$")
RE_NOME_ROTULO = re.compile(
    r"(?i:nome\s+d[oa]\s+(?:paciente|benefici[aá]ri[oa]|titular)|benefici[aá]ri[oa]|paciente|titular|"
    r"dependente|respons[aá]vel|segurad[oa]|nome)\s*[:\-]\s*"
    r"(?P<nome>[A-ZÀ-Ý][A-Za-zÀ-ÿ.']+(?:\s+(?:d[aeo]s?|e|[A-ZÀ-Ý][A-Za-zÀ-ÿ.']*)){1,5})"
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


def _sem_acento(texto: str) -> str:
    """Tira acentos e põe em minúsculas sem mudar o comprimento (as posições batem com o original)."""
    return "".join((unicodedata.normalize("NFKD", c)[:1] or c).lower() for c in texto)


def _variantes(nome: str) -> list[str]:
    """O nome completo e a forma 'primeiro + último' ("JOSÉ DE SOUZA" -> "jose souza")."""
    partes = [p for p in nome.split() if p.upper() not in _CONECTIVOS]
    vs = {_sem_acento(nome)}
    if len(partes) >= 2 and len(partes[0]) >= 3 and len(partes[-1].strip(".")) >= 3:
        vs.add(_sem_acento(f"{partes[0]} {partes[-1]}"))
    return sorted(vs, key=len, reverse=True)


def _trocar_nome(texto: str, variantes: list[str]) -> str:
    for v in variantes:
        base = _sem_acento(texto)
        padrao = re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, v.split())) + r"(?!\w)")
        partes, ult = [], 0
        for m in padrao.finditer(base):
            partes.append(texto[ult : m.start()])
            partes.append("[NOME]")
            ult = m.end()
        partes.append(texto[ult:])
        texto = "".join(partes)
    return texto


def pseudonimizar(linhas: list[Linha], segredo: str | None = None) -> Pseudonimizado:
    res = Pseudonimizado(linhas=[])
    textos: list[str] = []
    for lin in linhas:
        t = lin.texto

        def _cart(m: re.Match, t_atual: str) -> str:
            if RE_ROTULO_NAO_CARTEIRA.search(t_atual[: m.start()]):
                return m.group(0)
            tok = token_carteira(m.group(0), segredo)
            res.tokens[tok] = m.group(0)
            return tok

        t = RE_CARTEIRA.sub(lambda m, _t=t: _cart(m, _t), t)
        t = RE_CNS.sub("[CNS]", t)
        t, n = RE_CPF.subn("[CPF]", t)
        res.cpfs += n
        t = RE_EMAIL.sub("[EMAIL]", t)
        t = RE_TELEFONE.sub("[TELEFONE]", t)
        # nome com rótulo: "Beneficiária: Maria S. Costa", "Titular: JOANA DARC"
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
    # segunda passada: o nome some de qualquer lugar onde apareça (observações etc.), com ou sem acento
    nomes = sorted((n for n in res.nomes if len(n) >= 5 and " " in n), key=len, reverse=True)
    variantes = sorted({v for n in nomes for v in _variantes(n)}, key=len, reverse=True)
    for lin, t in zip(linhas, textos, strict=True):
        res.linhas.append(Linha(lin.pagina, lin.linha, _trocar_nome(t, variantes)))
    res.nomes = set(nomes)
    return res


def dados_pessoais_restantes(texto: str, nomes: set[str] | None = None) -> list[str]:
    """Lista o que ainda parece dado pessoal em claro no texto (para os verificadores)."""
    achados = []
    if RE_CPF.search(texto):
        achados.append("CPF")
    if RE_CARTEIRA.search(texto) or RE_CNS.search(texto):
        achados.append("número de carteira ou CNS")
    if RE_EMAIL.search(texto):
        achados.append("e-mail")
    base = _sem_acento(texto)
    for n in nomes or ():
        if n and any(re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", base) for v in _variantes(n)):
            achados.append(f"nome '{n}'")
    return achados
