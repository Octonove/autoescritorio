"""Lenguaje natural -> regla, usando Ollama (opcional). Le damos el catalogo de
disparadores y acciones y le pedimos un JSON estricto que validamos contra el
catalogo. Si algo no encaja, devolvemos un error y el usuario usa el editor."""

from __future__ import annotations

import json
import logging

from . import llm, rules

logger = logging.getLogger(__name__)


def _catalog_text() -> str:
    lines = ["DISPARADORES (trigger_type : campos):"]
    for k, v in rules.TRIGGERS.items():
        fields = ", ".join(f"{f[0]}" for f in v["fields"]) or "(sin campos)"
        lines.append(f"  {k} — {v['label']}  | campos: {fields}")
    lines.append("ACCIONES (action_type : campos):")
    for k, v in rules.ACTIONS.items():
        fields = ", ".join(f"{f[0]}" for f in v["fields"]) or "(sin campos)"
        lines.append(f"  {k} — {v['label']}  | campos: {fields}")
    return "\n".join(lines)


_SYS = ("Eres un asistente que convierte una orden en lenguaje natural en una regla "
        "de automatizacion. Respondes SOLO con un objeto JSON valido, sin texto extra.")

_PROMPT = """Convierte esta orden en una regla. Usa EXCLUSIVAMENTE los tipos y campos
de este catalogo:

{catalog}

Devuelve EXACTAMENTE este JSON (rellena trigger_params y action_params solo con los
campos del tipo elegido):
{{
  "name": "nombre corto de la regla",
  "trigger_type": "...",
  "trigger_params": {{}},
  "action_type": "...",
  "action_params": {{}}
}}

ORDEN: "{order}"
"""


# Unificado en el core; se conserva el nombre privado (los tests lo usan).
from octonove_core.jsonutil import extract_json as _extract_json  # noqa: E402


def rule_from_text(order: str, model: str | None = None):
    """Devuelve (Rule, None) o (None, mensaje_error)."""
    order = (order or "").strip()
    if not order:
        return None, "Escribe que quieres automatizar."
    if not llm.available():
        return None, "Para el lenguaje natural necesitas Ollama. Tambien puedes crear la regla a mano."
    raw = llm.generate(_PROMPT.format(catalog=_catalog_text(), order=order),
                       system=_SYS, model=model)
    data = _extract_json(raw or "")
    if not isinstance(data, dict):
        return None, "No entendi la orden. Prueba a reformularla o usa el editor manual."
    tt = data.get("trigger_type")
    at = data.get("action_type")
    if tt not in rules.TRIGGERS or at not in rules.ACTIONS:
        return None, "La orden no encaja con los disparadores/acciones disponibles."
    # filtra parametros a los campos validos del tipo
    tparams = _filter_fields(data.get("trigger_params"), rules.TRIGGERS[tt]["fields"])
    aparams = _filter_fields(data.get("action_params"), rules.ACTIONS[at]["fields"])
    rule = rules.Rule(name=str(data.get("name") or "Regla")[:60], trigger_type=tt,
                      trigger_params=tparams, action_type=at, action_params=aparams)
    err = rule.validate()
    if err:
        return None, f"La regla generada esta incompleta: {err} Revisala en el editor."
    return rule, None


def _filter_fields(params, fields) -> dict:
    params = params if isinstance(params, dict) else {}
    keys = {f[0] for f in fields}
    return {k: v for k, v in params.items() if k in keys}
