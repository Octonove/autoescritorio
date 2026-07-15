"""Modelo de reglas (Disparador -> Accion), catalogo de tipos y persistencia.

Cada regla tiene un disparador (trigger) y una accion. El catalogo describe los
campos de cada tipo, lo que permite a la UI construir el editor automaticamente.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# kind: text | int | folder | file | hotkey
TRIGGERS: dict[str, dict] = {
    "interval": {"label": "Cada cierto tiempo",
                 "fields": [("segundos", "Cada (segundos)", "int", 300)]},
    "daily": {"label": "Todos los dias a una hora",
              "fields": [("hora", "Hora (HH:MM)", "text", "09:00")]},
    "hotkey": {"label": "Un atajo de teclado",
               "fields": [("combo", "Combinacion", "hotkey", "ctrl+alt+a")]},
    "file_new": {"label": "Aparece un archivo nuevo en una carpeta",
                 "fields": [("carpeta", "Carpeta a vigilar", "folder", ""),
                            ("ext", "Solo esta extension (opcional, .pdf)", "text", "")]},
    "process_started": {"label": "Se abre un programa",
                        "fields": [("nombre", "Nombre del .exe", "text", "notepad.exe")]},
    "process_stopped": {"label": "Se cierra un programa",
                        "fields": [("nombre", "Nombre del .exe", "text", "notepad.exe")]},
    "window_opened": {"label": "Se abre una ventana con cierto titulo",
                      "fields": [("titulo", "El titulo contiene", "text", "")]},
    "usb_connected": {"label": "Se conecta una unidad USB", "fields": []},
    "clipboard_text": {"label": "Copias texto al portapapeles",
                       "fields": [("contiene", "Solo si contiene (opcional)", "text", "")]},
}

ACTIONS: dict[str, dict] = {
    "open": {"label": "Abrir un programa, archivo o URL",
             "fields": [("destino", "Programa, archivo o URL", "text", "")]},
    "run": {"label": "Ejecutar un comando",
            "fields": [("comando", "Linea de comandos", "text", "")]},
    "notify": {"label": "Mostrar una notificacion",
               "fields": [("titulo", "Titulo", "text", "AutoEscritorio"),
                          ("mensaje", "Mensaje", "text", "")]},
    "type_text": {"label": "Escribir un texto (donde tengas el cursor)",
                  "fields": [("texto", "Texto a escribir", "text", "")]},
    "keys": {"label": "Pulsar una combinacion de teclas",
             "fields": [("combo", "Combinacion (ej. ctrl+s)", "hotkey", "ctrl+s")]},
    "move_files": {"label": "Mover archivos de una carpeta a otra",
                   "fields": [("origen", "Carpeta origen", "folder", ""),
                              ("patron", "Patron (ej. *.pdf)", "text", "*.*"),
                              ("destino", "Carpeta destino", "folder", "")]},
    "copy_files": {"label": "Copiar archivos de una carpeta a otra",
                   "fields": [("origen", "Carpeta origen", "folder", ""),
                              ("patron", "Patron (ej. *.pdf)", "text", "*.*"),
                              ("destino", "Carpeta destino", "folder", "")]},
    "play_sound": {"label": "Reproducir un sonido",
                   "fields": [("ruta", "Archivo .wav (vacio = bip del sistema)", "file", "")]},
    "write_log": {"label": "Anotar una linea en un archivo de texto",
                  "fields": [("ruta", "Archivo de texto", "file", ""),
                             ("texto", "Texto a anotar", "text", "")]},
}

def _next_id() -> str:
    # uuid: unico SIEMPRE, tambien al crear reglas sobre otras ya cargadas de
    # disco. (Un contador incremental colisionaba con los ids ya persistidos ->
    # dos reglas con el mismo id compartian estado en el motor y dejaban de
    # dispararse.)
    return uuid.uuid4().hex[:12]


@dataclass
class Rule:
    name: str = "Nueva regla"
    enabled: bool = True
    trigger_type: str = "interval"
    trigger_params: dict = field(default_factory=dict)
    action_type: str = "notify"
    action_params: dict = field(default_factory=dict)
    id: str = field(default_factory=_next_id)

    def summary(self) -> str:
        t = TRIGGERS.get(self.trigger_type, {}).get("label", self.trigger_type)
        a = ACTIONS.get(self.action_type, {}).get("label", self.action_type)
        return f"Cuando: {t}  →  {a}"

    def validate(self) -> str | None:
        """Devuelve un mensaje de error, o None si es valida."""
        if self.trigger_type not in TRIGGERS:
            return "Disparador desconocido."
        if self.action_type not in ACTIONS:
            return "Accion desconocida."
        tp, ap = self.trigger_params, self.action_params
        if self.trigger_type == "interval":
            try:
                if int(tp.get("segundos", 0)) < 1:
                    return "El intervalo debe ser de al menos 1 segundo."
            except (ValueError, TypeError):
                return "El intervalo debe ser un numero."
        if self.trigger_type == "daily" and not _valid_hhmm(tp.get("hora", "")):
            return "La hora debe tener formato HH:MM (00:00 a 23:59)."
        if self.trigger_type == "hotkey":
            pc = parse_combo(tp.get("combo", ""))
            if not pc:
                return "La combinacion de teclas no es valida."
            if not pc.get("mods"):
                return ("El atajo necesita al menos Ctrl, Alt, Shift o Win "
                        "(una tecla sola bloquearia esa tecla en todo Windows).")
        if self.trigger_type == "file_new" and not str(tp.get("carpeta", "")).strip():
            return "Indica la carpeta a vigilar."
        if self.action_type == "open" and not str(ap.get("destino", "")).strip():
            return "Indica que abrir."
        if self.action_type == "run" and not str(ap.get("comando", "")).strip():
            return "Indica el comando a ejecutar."
        if self.action_type == "keys" and not parse_combo(ap.get("combo", "")):
            return "La combinacion de teclas no es valida."
        if self.action_type in ("move_files", "copy_files"):
            if not str(ap.get("origen", "")).strip() or not str(ap.get("destino", "")).strip():
                return "Indica las carpetas origen y destino."
        return None


def _valid_hhmm(s: str) -> bool:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s or "")
    if not m:
        return False
    h, mi = int(m.group(1)), int(m.group(2))
    return 0 <= h <= 23 and 0 <= mi <= 59


# --- combinaciones de teclas -------------------------------------------------
_VK = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
_MODS = {"ctrl", "control", "alt", "shift", "win"}


def parse_combo(combo: str):
    """'ctrl+alt+g' -> {'mods': set(vk), 'key': vk} o None si invalida."""
    parts = [p.strip().lower() for p in (combo or "").split("+") if p.strip()]
    if not parts:
        return None
    mods, key = set(), None
    for p in parts:
        if p in _MODS:
            mods.add(_VK[p])
        elif p in _VK:
            key = _VK[p]
        elif len(p) == 1 and (p.isalnum()):
            key = ord(p.upper())
        else:
            return None
    if key is None:
        return None
    return {"mods": mods, "key": key}


def substitute(params: dict, context: dict) -> dict:
    """Reemplaza marcadores como {file} en los valores de la accion."""
    out = {}
    for k, v in params.items():
        if isinstance(v, str):
            for ck, cv in context.items():
                v = v.replace("{" + ck + "}", str(cv))
        out[k] = v
    return out


# --- persistencia ------------------------------------------------------------
def load_rules(path) -> list[Rule]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("rules.json corrupto: %s", exc)
        return []
    rules = []
    known = {f for f in Rule().__dict__}
    for item in (data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        try:
            r = Rule(**{k: v for k, v in item.items() if k in known})
            if not isinstance(r.trigger_params, dict):
                r.trigger_params = {}
            if not isinstance(r.action_params, dict):
                r.action_params = {}
            # descarta tipos fuera del catalogo: el editor los construye a partir
            # de TRIGGERS/ACTIONS y reventaria con KeyError si el JSON esta editado a mano
            if r.trigger_type not in TRIGGERS or r.action_type not in ACTIONS:
                logger.warning("Regla «%s» ignorada: tipo desconocido (%s/%s).",
                               r.name, r.trigger_type, r.action_type)
                continue
            rules.append(r)
        except (TypeError, ValueError):
            continue
    # sanea ids duplicados o vacios (versiones antiguas con contador incremental
    # podian persistir ids repetidos, que en el motor comparten estado)
    vistos: set[str] = set()
    for r in rules:
        if not r.id or r.id in vistos:
            r.id = _next_id()
        vistos.add(r.id)
    return rules


def save_rules(path, rules: list[Rule]) -> None:
    try:
        Path(path).write_text(json.dumps([asdict(r) for r in rules], indent=2, ensure_ascii=False),
                              encoding="utf-8")
    except OSError as exc:
        logger.error("No se pudieron guardar las reglas: %s", exc)
