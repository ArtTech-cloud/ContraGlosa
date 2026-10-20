"""Teste de fumaça da API: uma chamada mínima ao modelo configurado.

Uso: python -m agente.fumaca
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY não definida. Copie .env.example para .env e preencha a chave.")
        return 2
    import anthropic

    from agente.llm import MODELO_PADRAO

    modelo = os.getenv("AGENTE_MODELO", MODELO_PADRAO)
    cliente = anthropic.Anthropic()
    try:
        resp = cliente.messages.create(
            model=modelo,
            max_tokens=64,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Responda apenas: ok"}],
        )
    except anthropic.AuthenticationError:
        print("Chave inválida (401).")
        return 1
    except anthropic.PermissionDeniedError:
        print("Chave sem permissão para este modelo (403).")
        return 1
    except anthropic.APIStatusError as e:
        print(f"Erro da API ({e.status_code}): {e.message}")
        return 1
    except anthropic.APIConnectionError:
        print("Sem conexão com a API.")
        return 1
    texto = "".join(b.text for b in resp.content if b.type == "text")
    print(
        f"modelo={resp.model} resposta={texto!r} tokens_in={resp.usage.input_tokens} tokens_out={resp.usage.output_tokens}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
