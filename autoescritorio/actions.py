"""Ejecucion de las acciones de una regla. Todo local. Las acciones que necesitan
interfaz (notificacion) se delegan a un callback que pasa la app."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from . import rules, winutil

logger = logging.getLogger(__name__)

# Unificada en el core: gana el guard de plataforma (0 en no-Windows; un
# creationflags != 0 fuera de Windows lanzaria ValueError en Popen).
from octonove_core.procutil import CREATE_NO_WINDOW  # noqa: E402


class ActionError(Exception):
    pass


def _is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


def _base_context(params: dict) -> dict:
    """Marcadores dinamicos disponibles SIEMPRE en cualquier accion:
    {date} fecha de hoy (DD/MM/AAAA), {time} hora (HH:MM), {datetime} ambas,
    {clipboard} el texto del portapapeles. Hacen utiles plantillas como
    'insertar la fecha' o 'guardar lo copiado'."""
    now = datetime.now()
    base = {
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M"),
        "datetime": now.strftime("%d/%m/%Y %H:%M"),
    }
    # el portapapeles solo se lee si alguna plantilla lo pide (abrirlo tiene coste)
    if any("{clipboard}" in str(v) for v in (params or {}).values()):
        base["clipboard"] = winutil.get_clipboard_text()
    return base


def _safe_for_path(value: str) -> str:
    r"""Version de un valor apta para nombres de archivo/carpeta: sustituye los
    caracteres que en Windows son estructurales (\ / : * ? " < > |) o saltos de
    linea por un guion. Asi {date} (DD/MM/AAAA) o {time} (HH:MM) usados en una
    RUTA no crean subcarpetas ni flujos NTFS ocultos."""
    out = value
    for ch in '\\/:*?"<>|\r\n\t':
        out = out.replace(ch, "-")
    return out


def execute(action_type: str, params: dict, context: dict | None = None, *, notify=None) -> str:
    """Ejecuta la accion y devuelve un texto descriptivo para el registro."""
    ctx_full = {**_base_context(params), **(context or {})}   # el evento pisa a los base
    p = rules.substitute(params or {}, ctx_full)
    context = ctx_full
    # Los campos de tipo carpeta/archivo se sustituyen con marcadores SANEADOS:
    # {date}/{time} llevan '/' y ':' que romperian la ruta (subcarpetas o ADS).
    ruta_ctx = {k: (_safe_for_path(v) if isinstance(v, str) else v)
                for k, v in ctx_full.items()}
    for k, _lbl, kind, _def in rules.ACTIONS.get(action_type, {}).get("fields", []):
        if kind in ("folder", "file") and isinstance((params or {}).get(k), str):
            p[k] = rules.substitute({k: params[k]}, ruta_ctx)[k]

    if action_type == "open":
        dest = str(p.get("destino", "")).strip()
        if not dest:
            raise ActionError("No se indico que abrir.")
        if _is_url(dest):
            webbrowser.open(dest)
        else:
            os.startfile(dest)   # programa, archivo o carpeta
        return f"Abierto: {dest}"

    if action_type == "run":
        # SEGURIDAD: NADA de shell=True. Se trocea el comando ORIGINAL (con los
        # marcadores intactos) y el contexto se sustituye por TOKEN, de modo que
        # {file}/{text}/{clipboard} son siempre UN argumento y no pueden inyectar
        # comandos (p.ej. un archivo llamado "x && borrar.exe").
        import shlex
        raw = str((params or {}).get("comando", "")).strip()
        if not raw:
            raise ActionError("Comando vacio.")
        try:
            tokens = shlex.split(raw, posix=False)
        except ValueError:
            tokens = raw.split()
        ctx = context or {}
        args = []
        for tok in tokens:
            for ck, cv in ctx.items():
                tok = tok.replace("{" + ck + "}", str(cv))
            if len(tok) >= 2 and tok[0] == tok[-1] == '"':
                tok = tok[1:-1]
            args.append(tok)
        if not args:
            raise ActionError("Comando vacio.")
        try:
            subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)
        except OSError as exc:
            raise ActionError(f"No se pudo ejecutar: {exc}") from exc
        return f"Ejecutado: {raw}"

    if action_type == "notify":
        title = str(p.get("titulo", "AutoEscritorio"))
        msg = str(p.get("mensaje", ""))
        if notify:
            notify(title, msg)
        else:
            try:
                import winsound
                winsound.MessageBeep()
            except Exception:  # noqa: BLE001
                pass
        return f"Notificacion: {title}"

    if action_type == "type_text":
        txt = str(p.get("texto", ""))
        unidades = len(txt.encode("utf-16-le")) // 2
        escritas = winutil.type_text(txt)
        if txt and escritas <= 0:
            raise ActionError("No se pudo escribir el texto (¿la ventana activa "
                              "se ejecuta como administrador?).")
        if escritas < unidades:
            return f"Escrito parcialmente ({escritas}/{unidades} caracteres)"
        return f"Escrito ({len(txt)} caracteres)"

    if action_type == "keys":
        parsed = rules.parse_combo(str(p.get("combo", "")))
        if not parsed:
            raise ActionError("Combinacion de teclas invalida.")
        if not winutil.press_combo(parsed):
            raise ActionError("No se pudo enviar la combinacion (¿seguias pulsando "
                              "el atajo? sueltalo antes).")
        return f"Teclas: {p.get('combo')}"

    if action_type in ("move_files", "copy_files"):
        return _file_op(action_type, p)

    if action_type == "play_sound":
        ruta = str(p.get("ruta", "")).strip()
        try:
            import winsound
            if ruta and Path(ruta).is_file():
                winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep()
        except Exception as exc:  # noqa: BLE001
            raise ActionError(f"No se pudo reproducir: {exc}") from exc
        return "Sonido reproducido"

    if action_type == "write_log":
        ruta = str(p.get("ruta", "")).strip()
        if not ruta:
            raise ActionError("Indica el archivo de registro.")
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {p.get('texto', '')}\n"
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(line)
        return f"Anotado en {ruta}"

    raise ActionError(f"Accion desconocida: {action_type}")


def _file_op(action_type: str, p: dict) -> str:
    origen = Path(str(p.get("origen", "")).strip())
    destino = Path(str(p.get("destino", "")).strip())
    patron = str(p.get("patron", "*.*")).strip() or "*.*"
    if not origen.is_dir():
        raise ActionError("La carpeta origen no existe.")
    destino.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in origen.glob(patron):
        if not src.is_file():
            continue
        dst = _unique_path(destino / src.name)   # nunca sobrescribe en silencio
        try:
            if action_type == "move_files":
                shutil.move(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
            n += 1
        except (OSError, shutil.Error) as exc:
            logger.warning("No se pudo procesar %s: %s", src, exc)
    verbo = "movidos" if action_type == "move_files" else "copiados"
    return f"{n} archivo(s) {verbo}"


def _unique_path(dst: Path) -> Path:
    """Si el destino ya existe, anade ' (1)', ' (2)'… para no sobrescribir."""
    if not dst.exists():
        return dst
    stem, suffix, parent = dst.stem, dst.suffix, dst.parent
    for i in range(1, 10000):
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    return dst
