"""Cliente do LLM: Anthropic de verdade, com cache em disco e modo demo, ou um cliente falso.

- Cache por SHA-256 de (modelo, esforço, sistema, mensagens, ferramentas, etapa e versão do prompt),
  em `cache/`. Só entra dado fictício e pseudonimizado.
- Com MODO_DEMO=1, só lê do cache: a demo roda sem internet. Cache ausente vira erro `SemCache`.
- `ClienteFalso` devolve respostas roteirizadas, para os testes não gastarem API.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
PASTA_CACHE = RAIZ / "cache"
MODELO_PADRAO = "claude-sonnet-5-5"
# US$ por milhão de tokens: entrada, saída, leitura de cache, escrita de cache
PRECOS = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
TIPOS_REPLAY = {"text", "tool_use", "thinking", "redacted_thinking"}


class ErroLLM(RuntimeError):
    """Falha ao chamar o modelo. `fatal` = não adianta tentar de novo (chave, crédito, permissão)."""

    def __init__(self, msg: str, fatal: bool = False):
        super().__init__(msg)
        self.fatal = fatal


class SemCache(ErroLLM):
    """Modo demo ligado e a resposta não está no cache."""


@dataclass
class RespostaLLM:
    content: list[dict]
    stop_reason: str
    modelo: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    tokens_cache_leitura: int = 0
    tokens_cache_escrita: int = 0
    latencia_ms: int = 0
    do_cache: bool = False

    @property
    def texto(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def chamadas(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]

    @property
    def custo_usd(self) -> float:
        if self.do_cache:
            return 0.0
        p = PRECOS.get(self.modelo, PRECOS[MODELO_PADRAO])
        return (
            self.tokens_entrada * p[0]
            + self.tokens_saida * p[1]
            + self.tokens_cache_leitura * p[2]
            + self.tokens_cache_escrita * p[3]
        ) / 1_000_000


@dataclass
class Pedido:
    etapa: str
    versao: str
    system: str
    messages: list[dict]
    tools: list[dict] = field(default_factory=list)
    max_tokens: int = 16000

    def chave(self, modelo: str, esforco: str) -> str:
        bruto = json.dumps(
            {
                "modelo": modelo,
                "esforco": esforco,
                "etapa": self.etapa,
                "versao": self.versao,
                "system": self.system,
                "messages": self.messages,
                "tools": self.tools,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _bloco_para_dict(b) -> dict:
    d = b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b)
    t = d.get("type")
    if t == "text":
        return {"type": "text", "text": d.get("text", "")}
    if t == "tool_use":
        return {"type": "tool_use", "id": d["id"], "name": d["name"], "input": d.get("input", {})}
    if t == "thinking":
        return {
            "type": "thinking",
            "thinking": d.get("thinking", ""),
            "signature": d.get("signature", ""),
        }
    if t == "redacted_thinking":
        return {"type": "redacted_thinking", "data": d.get("data", "")}
    return d


def para_historico(content: list[dict]) -> list[dict]:
    """Blocos que voltam no histórico da conversa, sem alteração."""
    return [b for b in content if b.get("type") in TIPOS_REPLAY]


class ClienteAnthropic:
    def __init__(self, modelo: str | None = None, modo_demo: bool | None = None):
        load_dotenv(RAIZ / ".env")
        self.modelo = modelo or os.getenv("AGENTE_MODELO") or MODELO_PADRAO
        self.esforco = os.getenv("AGENTE_ESFORCO", "medium")
        self.modo_demo = (
            modo_demo if modo_demo is not None else os.getenv("MODO_DEMO", "0").strip() == "1"
        )
        self.usar_fallback = os.getenv("AGENTE_FALLBACK", "1") != "0"
        self._cliente = None
        self.pasta_cache = Path(os.getenv("AGENTE_PASTA_CACHE") or PASTA_CACHE)
        self.pasta_cache.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ cache
    def _arquivo(self, chave: str) -> Path:
        return self.pasta_cache / f"{chave}.json"

    def _ler_cache(self, chave: str) -> RespostaLLM | None:
        arq = self._arquivo(chave)
        if not arq.exists():
            return None
        d = json.loads(arq.read_text(encoding="utf-8"))["resposta"]
        r = RespostaLLM(**d)
        r.do_cache = True
        r.latencia_ms = 0
        return r

    def _gravar_cache(self, chave: str, pedido: Pedido, r: RespostaLLM) -> None:
        reg = {
            "meta": {"etapa": pedido.etapa, "versao": pedido.versao, "modelo": self.modelo},
            "resposta": {k: v for k, v in r.__dict__.items() if k != "do_cache"},
        }
        self._arquivo(chave).write_text(
            json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )

    # ------------------------------------------------------------------ API
    def _api(self):
        if self._cliente is None:
            if not os.getenv("ANTHROPIC_API_KEY"):
                raise ErroLLM(
                    "ANTHROPIC_API_KEY não definida (copie .env.example para .env)", fatal=True
                )
            import anthropic

            self._cliente = anthropic.Anthropic(max_retries=3, timeout=180.0)
        return self._cliente

    def criar(self, pedido: Pedido) -> RespostaLLM:
        chave = pedido.chave(self.modelo, self.esforco)
        em_cache = self._ler_cache(chave)
        if em_cache is not None:
            return em_cache
        if self.modo_demo:
            raise SemCache(f"modo demo: sem resposta em cache para a etapa {pedido.etapa}")
        import anthropic

        params = dict(
            model=self.modelo,
            max_tokens=pedido.max_tokens,
            system=pedido.system,
            messages=pedido.messages,
            output_config={"effort": self.esforco},
            cache_control={"type": "ephemeral"},
        )
        if pedido.tools:
            params["tools"] = pedido.tools
        t0 = time.monotonic()
        try:
            resp = self._chamar(params)
        except anthropic.AuthenticationError as e:
            raise ErroLLM("chave da API inválida (401)", fatal=True) from e
        except anthropic.PermissionDeniedError as e:
            raise ErroLLM(f"sem permissão para o modelo {self.modelo} (403)", fatal=True) from e
        except anthropic.NotFoundError as e:
            raise ErroLLM(f"modelo {self.modelo} não encontrado (404)", fatal=True) from e
        except anthropic.RateLimitError as e:
            raise ErroLLM("limite de uso da API atingido (429)") from e
        except anthropic.BadRequestError as e:
            msg = str(getattr(e, "message", e))
            fatal = "credit" in msg.lower() or "billing" in msg.lower()
            raise ErroLLM(f"requisição recusada pela API (400): {msg[:300]}", fatal=fatal) from e
        except anthropic.APIStatusError as e:
            raise ErroLLM(f"erro da API ({e.status_code})") from e
        except anthropic.APIConnectionError as e:
            raise ErroLLM("sem conexão com a API") from e
        u = resp.usage
        r = RespostaLLM(
            content=[_bloco_para_dict(b) for b in resp.content],
            stop_reason=resp.stop_reason or "",
            modelo=self.modelo,
            tokens_entrada=getattr(u, "input_tokens", 0) or 0,
            tokens_saida=getattr(u, "output_tokens", 0) or 0,
            tokens_cache_leitura=getattr(u, "cache_read_input_tokens", 0) or 0,
            tokens_cache_escrita=getattr(u, "cache_creation_input_tokens", 0) or 0,
            latencia_ms=int((time.monotonic() - t0) * 1000),
        )
        if r.stop_reason == "refusal":
            raise ErroLLM("o modelo recusou a requisição (refusal)")
        self._gravar_cache(chave, pedido, r)
        return r

    def _chamar(self, params: dict):
        import anthropic

        cli = self._api()
        if self.usar_fallback:
            try:
                return cli.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            except anthropic.BadRequestError as e:
                if "fallback" not in str(getattr(e, "message", e)).lower():
                    raise
                self.usar_fallback = False  # conta sem acesso ao beta: segue sem fallback
        return cli.messages.create(**params)


class ClienteFalso:
    """Cliente roteirizado para testes. `roteiro(pedido) -> RespostaLLM | list[dict] | str`."""

    def __init__(self, roteiro: Callable[[Pedido], object], modelo: str = "falso"):
        self.roteiro = roteiro
        self.modelo = modelo
        self.esforco = "falso"
        self.modo_demo = False
        self.pedidos: list[Pedido] = []

    def criar(self, pedido: Pedido) -> RespostaLLM:
        self.pedidos.append(pedido)
        r = self.roteiro(pedido)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, RespostaLLM):
            return r
        if isinstance(r, str):
            r = [{"type": "text", "text": r}]
        stop = "tool_use" if any(b.get("type") == "tool_use" for b in r) else "end_turn"
        return RespostaLLM(
            content=r, stop_reason=stop, modelo=self.modelo, tokens_entrada=100, tokens_saida=50
        )
