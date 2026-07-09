"""Capa de IA local OPCIONAL via Ollama: shim del nucleo compartido
(octonove_core.llm) con los defaults de generacion de AutoEscritorio."""

from __future__ import annotations

from octonove_core.llm import (  # noqa: F401
    OLLAMA_URL,
    _cache,
    _get,
    _resolve_ollama_url,
    available,
    default_model,
    has_gpu,
    list_models,
    recommend_model,
    reset_cache,
    set_model,
    system_ram_gb,
)
from octonove_core.llm import generate as _generate


def generate(prompt: str, *, system: str | None = None, model: str | None = None,
             timeout: float = 120.0, temperature: float = 0.1) -> str | None:
    """Defaults propios de esta app: temperatura 0.1 (CRITICO: nl.py parsea el JSON
    de reglas de la respuesta y necesita salidas deterministas; llama generate()
    sin pasar temperature)."""
    return _generate(prompt, system=system, model=model, timeout=timeout,
                     temperature=temperature)
