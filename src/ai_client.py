"""Klient för lokal AI med OpenAI-kompatibelt API.

Fungerar mot t.ex. LM Studio, Ollama (via dess /v1-endpoint), vLLM,
text-generation-webui eller llama.cpp:s server — allt som exponerar
/v1/chat/completions enligt OpenAI:s API-format.
"""
from __future__ import annotations

import logging

from .config import AIConfig

logger = logging.getLogger(__name__)


def build_openai_client(ai_cfg: AIConfig):
    """Skapar en OpenAI-klient pekad mot en lokal OpenAI-kompatibel endpoint."""
    if not ai_cfg.enabled:
        return None
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Paketet 'openai' saknas. Installera med: pip install openai"
        ) from exc

    return OpenAI(
        base_url=ai_cfg.base_url,
        api_key=ai_cfg.api_key,
        timeout=ai_cfg.timeout,
    )


def chat_completion(client, model: str, system: str, user: str) -> str:
    """Enkel wrapper för ett chat completion-anrop mot den lokala AI:n."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()
