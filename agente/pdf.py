"""Extração de texto do PDF com página e linha (pdfplumber). Sem OCR."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

MIN_CARACTERES_PAGINA = 20


class PDFInvalido(ValueError):
    """Arquivo que não abre como PDF."""


@dataclass(frozen=True)
class Linha:
    pagina: int
    linha: int
    texto: str


@dataclass
class DocumentoTexto:
    nome: str
    sha256: str
    total_paginas: int
    linhas: list[Linha] = field(default_factory=list)
    paginas_sem_texto: list[int] = field(default_factory=list)

    def linha(self, pagina: int, linha: int) -> Linha | None:
        for lin in self.linhas:
            if lin.pagina == pagina and lin.linha == linha:
                return lin
        return None

    def janela(self, pagina: int, linha: int, depois: int = 2) -> str:
        """Texto da linha indicada e das `depois` linhas seguintes da mesma página."""
        return "\n".join(
            lin.texto
            for lin in self.linhas
            if lin.pagina == pagina and linha <= lin.linha <= linha + depois
        )

    def pagina(self, n: int) -> list[Linha]:
        return [lin for lin in self.linhas if lin.pagina == n]


def extrair_texto(origem: str | Path | bytes, nome: str | None = None) -> DocumentoTexto:
    """Lê o PDF e devolve as linhas numeradas por página (1, 2, ...)."""
    if isinstance(origem, (str, Path)):
        dados = Path(origem).read_bytes()
        nome = nome or Path(origem).name
    else:
        dados = origem
        nome = nome or "documento.pdf"
    if not dados.startswith(b"%PDF"):
        raise PDFInvalido("o arquivo não começa com a assinatura %PDF")
    doc = DocumentoTexto(nome=nome, sha256=hashlib.sha256(dados).hexdigest(), total_paginas=0)
    try:
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            doc.total_paginas = len(pdf.pages)
            for p, page in enumerate(pdf.pages, start=1):
                texto = page.extract_text() or ""
                if len("".join(texto.split())) < MIN_CARACTERES_PAGINA:
                    doc.paginas_sem_texto.append(p)
                    continue
                n = 0
                for bruto in texto.split("\n"):
                    t = " ".join(bruto.split())
                    if t:
                        n += 1
                        doc.linhas.append(Linha(p, n, t))
    except Exception as e:  # pdfminer levanta vários tipos para PDF corrompido
        raise PDFInvalido(f"não foi possível ler o PDF: {type(e).__name__}") from e
    if doc.total_paginas == 0:
        raise PDFInvalido("o PDF não tem páginas")
    return doc


def formatar_para_llm(linhas: list[Linha]) -> str:
    """Uma linha por linha do PDF, com o local entre colchetes: [p1 l12] texto."""
    return "\n".join(f"[p{lin.pagina} l{lin.linha}] {lin.texto}" for lin in linhas)
