"""Modelos de dados (pydantic). O que vem do LLM é validado aqui antes de ser usado."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agente.dinheiro import parse_brl

Decisao = Literal["recorrer", "nao_recorrer", "revisao_humana"]
Confianca = Literal["alta", "media", "baixa"]
TipoPendencia = Literal[
    "soma_divergente",
    "totais_ausentes",
    "codigo_inexistente",
    "pagina_ilegivel",
    "documento_sem_texto",
    "documento_nao_reconhecido",
    "validacao_falhou",
    "evidencia_nao_confere",
    "confianca_baixa",
    "recurso_recusado",
    "sem_cache",
    "erro_api",
]
TipoAlerta = Literal["instrucao_no_documento", "dado_pessoal_no_texto"]


def parse_data(texto: str) -> dt.date:
    """Aceita dd/mm/aaaa ou aaaa-mm-dd."""
    t = (texto or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return dt.date.fromisoformat(t)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- saída das etapas do LLM ----------


class Triagem(_Base):
    tipo_documento: Literal["demonstrativo_retorno", "outro"]
    operadora: str
    competencia: str | None = None
    data_emissao: str | None = Field(None, description="dd/mm/aaaa, como impresso")
    protocolo: str | None = None
    legivel: bool = True
    observacao: str = ""

    @field_validator("data_emissao")
    @classmethod
    def _data(cls, v: str | None) -> str | None:
        if v:
            parse_data(v)
        return v


class ItemExtraido(_Base):
    pagina: int = Field(ge=1)
    linha: int = Field(ge=1)
    guia: str
    data_atendimento: str
    beneficiario: str = Field(description="token da carteira, como aparece no texto")
    codigo_procedimento: str
    descricao: str = ""
    quantidade: int = Field(1, ge=0)
    valor_apresentado: str
    valor_glosado: str
    valor_pago: str
    codigo_glosa: str | None = None
    motivo_glosa: str | None = None
    observacao: str | None = None
    senha: str | None = None

    @field_validator("valor_apresentado", "valor_glosado", "valor_pago")
    @classmethod
    def _valor(cls, v: str) -> str:
        parse_brl(v)
        return v.strip()

    @field_validator("data_atendimento")
    @classmethod
    def _data(cls, v: str) -> str:
        parse_data(v)
        return v.strip()

    @field_validator("codigo_procedimento")
    @classmethod
    def _proc(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{8}", v):
            raise ValueError("código de procedimento deve ter 8 dígitos")
        return v

    @field_validator("codigo_glosa")
    @classmethod
    def _glosa(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not re.fullmatch(r"\d{4}", v):
            raise ValueError("código de glosa deve ter 4 dígitos, como impresso")
        return v

    @property
    def apresentado(self) -> int:
        return parse_brl(self.valor_apresentado)

    @property
    def glosado(self) -> int:
        return parse_brl(self.valor_glosado)

    @property
    def pago(self) -> int:
        return parse_brl(self.valor_pago)

    @property
    def tem_glosa(self) -> bool:
        return self.glosado > 0 or self.codigo_glosa is not None


class TotaisImpressos(_Base):
    valor_apresentado: str | None = None
    valor_glosado: str | None = None
    valor_pago: str | None = None
    pagina: int | None = None
    linha: int | None = None

    @field_validator("valor_apresentado", "valor_glosado", "valor_pago")
    @classmethod
    def _valor(cls, v: str | None) -> str | None:
        if v is not None:
            parse_brl(v)
            return v.strip()
        return v


class Extracao(_Base):
    itens: list[ItemExtraido]
    totais: TotaisImpressos | None = None


class DecisaoGlosa(_Base):
    item: int = Field(ge=0, description="índice do item na lista extraída")
    decisao: Decisao
    confianca: Confianca
    justificativa: str = Field(min_length=10)
    fontes: list[str] = Field(default_factory=list, description="ids de trechos da base")
    documentos: list[str] = Field(default_factory=list, description="documentos para anexar")


class Analise(_Base):
    decisoes: list[DecisaoGlosa]


class Recurso(_Base):
    item: int = Field(ge=0)
    texto: str = Field(min_length=50)


class Redacao(_Base):
    recursos: list[Recurso]


# ---------- registro do que aconteceu ----------


class Pendencia(_Base):
    tipo: TipoPendencia
    motivo: str
    pagina: int | None = None
    linha: int | None = None
    item: int | None = None


class Alerta(_Base):
    tipo: TipoAlerta
    motivo: str
    pagina: int | None = None
    linha: int | None = None
    trecho: str | None = None


class ChamadaFerramenta(_Base):
    nome: str
    argumentos: dict
    resultado: str
    aprovado: bool | None = None


class PassoTrilha(_Base):
    etapa: str
    versao_prompt: str | None = None
    modelo: str | None = None
    status: Literal["ok", "retry", "fallback", "erro", "info"] = "ok"
    detalhe: str = ""
    ferramentas: list[ChamadaFerramenta] = Field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    latencia_ms: int = 0
    do_cache: bool = False
