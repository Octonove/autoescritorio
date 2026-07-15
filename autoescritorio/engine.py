"""Motor de automatizacion: en un hilo de fondo evalua los disparadores de las
reglas activas y ejecuta sus acciones. Los disparadores de estado (proceso,
ventana, USB, archivo) disparan SOLO en la transicion (cuando aparece algo nuevo),
nunca en bucle. Toma una linea base al arrancar para no disparar con lo ya existente."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime

from . import actions, rules, winutil

logger = logging.getLogger(__name__)

TICK = 0.15            # cadencia base (atajos/portapapeles)
HEAVY_EVERY = 7        # cada ~1 s: procesos, ventanas, unidades, carpetas
COOLDOWN = 1.5         # segundos minimos entre disparos de una misma regla


class Engine:
    def __init__(self, get_rules, on_log=None, notify=None):
        self.get_rules = get_rules
        self.on_log = on_log or (lambda *_: None)
        self.notify = notify
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state: dict = {}
        self._last_fire: dict = {}
        # atajos por EVENTOS (RegisterHotKey): no pierde pulsaciones y consume el
        # combo (la tecla no se auto-repite en el destino). Sustituye al polling.
        self._hotkeys = winutil.HotkeyListener(self._on_hotkey, self._on_hotkey_failed)
        # id de hotkey -> (id de regla, teclas del combo). Un solo dict que se
        # reasigna de forma ATOMICA (el hilo del listener lo lee sin lock).
        self._hk: dict[int, tuple[str, set]] = {}
        # serializa la EJECUCION de acciones: dos atajos pulsados a la vez no
        # deben inyectar texto simultaneamente (saldria entremezclado).
        self._action_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._state.clear()
        self._last_fire.clear()
        self._sync_hotkeys()      # fija los specs ANTES de arrancar el bucle...
        self._hotkeys.start()     # ...para que el registro inicial cree la cola
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._log("Motor en marcha.")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        self._hotkeys.stop()
        self._log("Motor detenido.")

    def reload(self) -> None:
        """Tras editar reglas. NO borra todo el estado (eso reiniciaba los timers y
        la linea base de TODAS las reglas). _st() re-baseliniza solo las reglas cuyo
        disparador cambio; aqui solo se limpia el estado de reglas ya eliminadas."""
        try:
            ids = {r.id for r in self.get_rules()}
            for k in list(self._state):
                if k not in ids:
                    del self._state[k]
        except Exception:  # noqa: BLE001
            pass
        if self.running:
            self._sync_hotkeys()

    # ------------------------------------------------------------- atajos
    def _sync_hotkeys(self) -> None:
        """(Re)registra los atajos de las reglas activas via RegisterHotKey."""
        specs, hk, hid = [], {}, 1
        for r in self._enabled_rules():
            if r.trigger_type != "hotkey":
                continue
            parsed = rules.parse_combo(str((r.trigger_params or {}).get("combo", "")))
            # se EXIGE al menos un modificador: registrar una tecla suelta
            # (p. ej. 'A') la secuestraria en TODO el sistema.
            if not parsed or not parsed.get("key") or not parsed.get("mods"):
                continue
            specs.append((hid, parsed["mods"], parsed["key"]))
            hk[hid] = (r.id, set(parsed["mods"]) | {parsed["key"]})
            hid += 1
        self._hk = hk                     # reasignacion atomica
        self._hotkeys.set_hotkeys(specs)

    def _enabled_rules(self) -> list:
        try:
            return [r for r in self.get_rules() if r.enabled]
        except Exception:  # noqa: BLE001
            return []

    def _on_hotkey(self, hotkey_id: int) -> None:
        """WM_HOTKEY: dispara la regla en un hilo aparte (una accion lenta -p.ej.
        esperar a soltar teclas- no debe bloquear el bucle de mensajes)."""
        entry = self._hk.get(hotkey_id)   # lectura atomica del dict actual
        if not entry:
            return
        rid, combo = entry
        rule = next((r for r in self._enabled_rules() if r.id == rid), None)
        if rule is None:
            return

        def _run():
            # espera a soltar TODO el combo (incl. la letra) antes de actuar: si
            # no, la tecla del atajo se auto-repetiria en el texto inyectado.
            if combo:
                winutil.wait_keys_up(combo)
            # per_event: los atajos son acciones DELIBERADAS del usuario; cada
            # pulsacion debe disparar (sin el cooldown de los disparos de estado).
            self._fire(rule, {}, per_event=True)
        threading.Thread(target=_run, daemon=True).start()

    def _on_hotkey_failed(self, fallidos: list) -> None:
        hk = self._hk
        try:
            reglas = {r.id: r for r in self.get_rules()}
            for h in fallidos:
                entry = hk.get(h)
                r = reglas.get(entry[0]) if entry else None
                if r:
                    self._log(f"⚠ El atajo de «{r.name}» ya lo usa otro programa; "
                              "elige otra combinacion.")
        except Exception:  # noqa: BLE001
            pass

    def _log(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.on_log(f"[{ts}] {text}")
        except Exception:  # noqa: BLE001
            pass

    def _run(self) -> None:
        tick = 0
        while not self._stop.is_set():
            heavy = (tick % HEAVY_EVERY == 0)
            try:
                snapshot = self._snapshots(heavy)
                for rule in list(self.get_rules()):
                    if not rule.enabled:
                        continue
                    self._eval_rule(rule, snapshot, heavy)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error en el motor: %s", exc)
            tick += 1
            self._stop.wait(TICK)

    def _snapshots(self, heavy: bool) -> dict:
        s = {"now": time.time()}
        # el portapapeles solo se lee si hay una regla que lo vigila: abrirlo en
        # cada tick era innecesario y podia bloquear el motor (otras apps lo
        # bloquean con frecuencia), retrasando el resto de disparadores.
        if any(r.trigger_type == "clipboard_text" for r in self._enabled_rules()):
            s["clip"] = winutil.get_clipboard_text()
        else:
            s["clip"] = ""
        if heavy:
            s["procs"] = winutil.list_processes()
            s["titles"] = winutil.list_window_titles()
            s["drives"] = winutil.removable_drives()
        return s

    def _st(self, rule) -> dict:
        # firma del disparador: si cambia (regla editada), se re-baseliniza SOLO
        # esta regla; las demas conservan su estado y sus timers.
        sig = (rule.trigger_type, json.dumps(rule.trigger_params, sort_keys=True, default=str))
        st = self._state.get(rule.id)
        if st is None or st.get("_sig") != sig:
            st = {"_sig": sig}
            self._state[rule.id] = st
        return st

    def _eval_rule(self, rule, snap: dict, heavy: bool) -> None:
        t = rule.trigger_type
        tp = rule.trigger_params or {}
        st = self._st(rule)
        first = not st.get("_init")

        if t == "interval":
            try:
                secs = max(1, int(tp.get("segundos", 300)))
            except (ValueError, TypeError):
                return
            if first:
                st["next"] = snap["now"] + secs
                st["_init"] = True
                return
            if snap["now"] >= st.get("next", 0):
                st["next"] = snap["now"] + secs
                self._fire(rule, {})
            return

        if t == "daily":
            hhmm = datetime.now().strftime("%H:%M")
            today = datetime.now().strftime("%Y-%m-%d")
            st["_init"] = True
            target = _norm_hhmm(str(tp.get("hora", "")))   # "9:00" -> "09:00"
            if target and hhmm == target and st.get("last_date") != today:
                st["last_date"] = today
                self._fire(rule, {})
            return

        if t == "hotkey":
            return   # los atajos van por eventos (RegisterHotKey), no por polling

        if t == "clipboard_text":
            cur = snap.get("clip", "")
            needle = str(tp.get("contiene", "")).strip().lower()
            if first:
                st["prev"] = cur
                st["_init"] = True
                return
            if not cur:
                return   # portapapeles bloqueado por otra app o vacio: no toca prev
            if cur != st.get("prev", "") and (not needle or needle in cur.lower()):
                self._fire(rule, {"text": cur})
            st["prev"] = cur
            return

        # --- disparadores de estado (solo en los ticks "pesados") ---
        if not heavy:
            return

        if t == "process_started":
            name = str(tp.get("nombre", "")).strip().lower()
            cur = snap.get("procs", set())
            if first:
                st["seen"] = cur
                st["_init"] = True
                return
            if name and name in cur and name not in st.get("seen", set()):
                self._fire(rule, {})
            st["seen"] = cur
            return

        if t == "process_stopped":
            name = str(tp.get("nombre", "")).strip().lower()
            cur = snap.get("procs", set())
            if first:
                st["seen"] = cur
                st["_init"] = True
                return
            if name and name in st.get("seen", set()) and name not in cur:
                self._fire(rule, {})
            st["seen"] = cur
            return

        if t == "window_opened":
            needle = str(tp.get("titulo", "")).strip().lower()
            cur = {w for w in snap.get("titles", []) if needle in w.lower()} if needle else set()
            if first:
                st["seen"] = cur
                st["_init"] = True
                return
            new = cur - st.get("seen", set())
            if new:
                self._fire(rule, {"window": sorted(new)[0]})
            st["seen"] = cur
            return

        if t == "usb_connected":
            cur = snap.get("drives", set())
            if first:
                st["seen"] = cur
                st["_init"] = True
                return
            new = cur - st.get("seen", set())
            if new:
                self._fire(rule, {"drive": sorted(new)[0]})
            st["seen"] = cur
            return

        if t == "file_new":
            folder = str(tp.get("carpeta", "")).strip()
            ext = str(tp.get("ext", "")).strip().lower()
            if ext and not ext.startswith("."):
                ext = "." + ext          # acepta 'pdf' o '.pdf'
            from pathlib import Path
            p = Path(folder)
            try:
                cur = {f.name: f.stat().st_size for f in p.iterdir() if f.is_file()
                       and (not ext or f.suffix.lower() == ext)}
            except OSError:
                return
            if first:
                st["seen"] = set(cur)
                st["pending"] = {}
                st["_init"] = True
                return
            seen = st.setdefault("seen", set())
            pending = st.setdefault("pending", {})
            ready = []
            for name, size in cur.items():
                if name in seen:
                    continue
                # esperar a que el tamano se estabilice (archivo terminado de copiar)
                if name in pending and pending[name] == size:
                    ready.append(name)
                else:
                    pending[name] = size     # sigue creciendo o recien visto: esperar
            MAX_PER_TICK = 25
            if len(ready) > MAX_PER_TICK:
                self._log(f"«{rule.name}»: {len(ready)} archivos nuevos; proceso "
                          f"los primeros {MAX_PER_TICK}.")
            for name in ready[:MAX_PER_TICK]:
                seen.add(name)
                pending.pop(name, None)
                self._fire(rule, {"file": str(p / name)}, per_event=True)
            # limpia de 'pending' lo que ya no esta
            for gone in [n for n in pending if n not in cur]:
                pending.pop(gone, None)
            return

    def _fire(self, rule, context: dict, *, per_event: bool = False) -> None:
        now = time.time()
        if not per_event and now - self._last_fire.get(rule.id, 0) < COOLDOWN:
            return
        self._last_fire[rule.id] = now
        with self._action_lock:   # una accion cada vez (no solapar inyecciones)
            try:
                res = actions.execute(rule.action_type, rule.action_params, context,
                                      notify=self.notify)
                self._log(f"✓ «{rule.name}» → {res}")
            except Exception as exc:  # noqa: BLE001
                self._log(f"✗ «{rule.name}» fallo: {exc}")


def _norm_hhmm(s: str) -> str:
    """'9:00' -> '09:00'; devuelve '' si no es una hora valida."""
    import re
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s or "")
    if not m:
        return ""
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return ""
    return f"{h:02d}:{mi:02d}"
