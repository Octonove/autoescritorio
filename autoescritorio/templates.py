"""Plantillas de reglas listas para usar.

Cada plantilla es una regla completa con valores por defecto sensatos (usando
las carpetas reales del usuario). El usuario las anade con un clic desde el
dialogo 'Ejemplos'. Sirven de punto de partida y de muestra de lo que la app
puede hacer (incluidos los marcadores dinamicos {date}/{time}/{clipboard}).
"""

from __future__ import annotations

import os
from pathlib import Path

from .rules import Rule


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _first_existing(*names: str) -> str:
    """Primera subcarpeta del home que exista (Descargas o Downloads, etc.)."""
    home = _home()
    for n in names:
        if (home / n).is_dir():
            return str(home / n)
    return str(home / names[0])


def catalog() -> list[dict]:
    """Lista de plantillas: {titulo, desc, factory()->Rule}. Se calcula al vuelo
    para reflejar las carpetas reales del equipo."""
    descargas = _first_existing("Descargas", "Downloads")
    documentos = _first_existing("Documentos", "Documents")
    escritorio = _first_existing("Escritorio", "Desktop")
    pdfs = str(Path(documentos) / "PDFs")
    diario = str(Path(documentos) / "AutoEscritorio" / "portapapeles.txt")

    def _r(name, tt, tp, at, ap) -> Rule:
        return Rule(name=name, trigger_type=tt, trigger_params=tp,
                    action_type=at, action_params=ap)

    return [
        {"titulo": "Insertar la fecha de hoy",
         "desc": "Pulsa Ctrl+Alt+D y escribe la fecha (DD/MM/AAAA) donde tengas el cursor.",
         "factory": lambda: _r("Insertar la fecha de hoy",
                               "hotkey", {"combo": "ctrl+alt+d"},
                               "type_text", {"texto": "{date}"})},
        {"titulo": "Insertar fecha y hora",
         "desc": "Pulsa Ctrl+Alt+T y escribe la fecha y la hora actuales.",
         "factory": lambda: _r("Insertar fecha y hora",
                               "hotkey", {"combo": "ctrl+alt+t"},
                               "type_text", {"texto": "{datetime}"})},
        {"titulo": "Mi firma de correo",
         "desc": "Pulsa Ctrl+Alt+F y escribe tu firma. Editala con tus datos.",
         "factory": lambda: _r("Mi firma de correo",
                               "hotkey", {"combo": "ctrl+alt+f"},
                               "type_text", {"texto": "Un saludo,\nNombre Apellidos\n"
                                                      "empresa · correo@ejemplo.com"})},
        {"titulo": "Ordenar los PDF de Descargas",
         "desc": f"Cada 5 min mueve los .pdf de «{Path(descargas).name}» a una carpeta PDFs.",
         "factory": lambda: _r("Ordenar los PDF de Descargas",
                               "interval", {"segundos": 300},
                               "move_files", {"origen": descargas, "patron": "*.pdf",
                                              "destino": pdfs})},
        {"titulo": "Copia de seguridad al conectar un USB",
         "desc": "Cuando conectes un USB, copia tu carpeta Documentos a la unidad.",
         "factory": lambda: _r("Copia de seguridad al conectar un USB",
                               "usb_connected", {},
                               "copy_files", {"origen": documentos, "patron": "*.*",
                                              "destino": "{drive}\\Backup"})},
        {"titulo": "Guardar todo lo que copio",
         "desc": "Cada vez que copies texto, lo guarda con fecha en un archivo.",
         "factory": lambda: _r("Guardar todo lo que copio",
                               "clipboard_text", {"contiene": ""},
                               "write_log", {"ruta": diario, "texto": "{clipboard}"})},
        {"titulo": "Pausa activa cada hora",
         "desc": "Cada hora te avisa para descansar la vista (regla 20-20-20).",
         "factory": lambda: _r("Pausa activa cada hora",
                               "interval", {"segundos": 3600},
                               "notify", {"titulo": "Descansa la vista",
                                          "mensaje": "Mira algo lejano 20 segundos."})},
        {"titulo": "Abrir tu correo al iniciar la manana",
         "desc": "Todos los dias a las 09:00 abre tu correo en el navegador.",
         "factory": lambda: _r("Abrir el correo por la manana",
                               "daily", {"hora": "09:00"},
                               "open", {"destino": "https://mail.google.com"})},
        {"titulo": "Aviso al conectar un USB",
         "desc": "Te muestra una notificacion en cuanto se conecta una unidad USB.",
         "factory": lambda: _r("Aviso al conectar un USB",
                               "usb_connected", {},
                               "notify", {"titulo": "USB conectado",
                                          "mensaje": "Se ha conectado la unidad {drive}"})},
        {"titulo": "Registrar cuando abres un programa",
         "desc": "Anota en un archivo cada vez que se abre el Bloc de notas (editable).",
         "factory": lambda: _r("Registrar apertura de un programa",
                               "process_started", {"nombre": "notepad.exe"},
                               "write_log", {"ruta": str(Path(escritorio) / "registro.txt"),
                                             "texto": "Se abrio notepad.exe"})},
    ]
