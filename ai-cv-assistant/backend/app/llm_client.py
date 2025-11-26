import httpx
from typing import List, Dict, Any
from .config import settings


async def call_llm(messages: List[Dict[str, str]]) -> str:
    """
    OpenAI uyumlu bir /chat/completions endpoint'ine istek atar.
    Local open-source model için de aynı formatı kullanıyoruz.
    """
    url = f"{settings.llm_api_base}/chat/completions"

    payload: Dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }

    headers = {
        "Content-Type": "application/json",
        # Bazı local serverlar key istemez; ama header zarar vermez.
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    # OpenAI uyumlu cevap formatı:
    # { "choices": [ { "message": {"role": "assistant", "content": "..."} } ] }
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"LLM cevabı beklenmeyen formatta: {data}") from exc
