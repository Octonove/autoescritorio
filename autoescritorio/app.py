"""Ventana principal de AutoEscritorio."""

from __future__ import annotations

import logging
import threading
import webbrowser
from tkinter import ttk, messagebox, filedialog
import tkinter as tk

from . import APP_NAME, APP_VERSION, theme
from . import rules as R
from . import actions, engine, nl, llm
from .config import AppConfig, load_config, save_config, RULES_PATH

logger = logging.getLogger(__name__)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1060x720")
        self.minsize(940, 640)
        theme.apply(self)
        try:
            from pathlib import Path
            ico = Path(__file__).resolve().parent.parent / "build" / "icon.ico"
            if ico.is_file():
                self.iconbitmap(str(ico))
        except tk.TclError:
            pass

        self.cfg: AppConfig = load_config()
        self.rules: list[R.Rule] = R.load_rules(RULES_PATH)
        self._closing = False
        self.engine = engine.Engine(get_rules=lambda: self.rules,
                                    on_log=self._log, notify=self._notify)

        self._build_ui()
        self._refresh_rules()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._first_run_check)
        if self.cfg.start_engine_on_open and self.rules:
            self.after(500, self._start_engine)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        theme.header(self, APP_NAME, "Automatiza tu PC con reglas «cuando pasa X, haz Y» · 100% local")
        self.status = theme.status_bar(self, "Motor detenido.")

        bar = ttk.Frame(self, padding=(14, 10)); bar.pack(fill="x")
        self.btn_engine = ttk.Button(bar, text="▶  Activar motor", style="Go.TButton",
                                     command=self._toggle_engine)
        self.btn_engine.pack(side="left")
        self.lbl_engine = ttk.Label(bar, text="● Parado", style="Muted.TLabel")
        self.lbl_engine.pack(side="left", padx=12)
        ttk.Button(bar, text="IA (Ollama)…", command=self._ollama_dialog).pack(side="right")
        ttk.Button(bar, text="⚙ Opciones", command=self._settings_dialog).pack(side="right", padx=(0, 6))

        nlf = ttk.Frame(self, padding=(14, 0)); nlf.pack(fill="x")
        ttk.Label(nlf, text="Describe una automatizacion:", style="H.TLabel").pack(side="left")
        self.var_nl = tk.StringVar()
        ent = ttk.Entry(nlf, textvariable=self.var_nl)
        ent.pack(side="left", fill="x", expand=True, padx=8)
        ent.bind("<Return>", lambda e: self._nl_create())
        ttk.Button(nlf, text="Crear con IA", style="Primary.TButton",
                   command=self._nl_create).pack(side="left")
        ttk.Label(nlf, text="ej. «cuando conecte un USB, abre la calculadora»",
                  style="Muted.TLabel").pack(anchor="w", padx=(0, 0), pady=(2, 0))

        body = ttk.Frame(self, padding=(14, 8)); body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # reglas
        left = ttk.LabelFrame(body, text="Reglas", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.lst = tk.Listbox(left, height=16, activestyle="none", font=(theme.FONT, 10),
                              bg=theme.WHITE, fg=theme.TEXT, selectbackground=theme.PRIMARY,
                              selectforeground=theme.WHITE)
        self.lst.pack(fill="both", expand=True)
        self.lst.bind("<Double-Button-1>", lambda e: self._edit_rule())
        rb = ttk.Frame(left); rb.pack(fill="x", pady=(6, 0))
        ttk.Button(rb, text="+ Nueva", command=self._new_rule).pack(side="left")
        ttk.Button(rb, text="Editar", command=self._edit_rule).pack(side="left", padx=4)
        ttk.Button(rb, text="Activar/Pausar", command=self._toggle_rule).pack(side="left")
        ttk.Button(rb, text="Probar", command=self._test_rule).pack(side="left", padx=4)
        ttk.Button(rb, text="Eliminar", command=self._delete_rule).pack(side="right")

        # registro de actividad
        right = ttk.LabelFrame(body, text="Actividad", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        self.log = tk.Text(right, height=16, wrap="word", font=(theme.FONT, 9),
                           bg="#0F172A", fg="#CBD5E1", relief="flat", padx=8, pady=6)
        sb = ttk.Scrollbar(right, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set, state="disabled")
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    # -------------------------------------------------------------- motor
    def _toggle_engine(self) -> None:
        if self.engine.running:
            self._stop_engine()
        else:
            self._start_engine()

    def _start_engine(self) -> None:
        if not self.rules:
            messagebox.showinfo(APP_NAME, "Crea al menos una regla antes de activar el motor.")
            return
        self.engine.start()
        self.btn_engine.config(text="⏹  Detener motor", style="Stop.TButton")
        self.lbl_engine.config(text="● Activo")
        self._set_status("Motor activo: vigilando tus reglas.")

    def _stop_engine(self) -> None:
        self.engine.stop()
        self.btn_engine.config(text="▶  Activar motor", style="Go.TButton")
        self.lbl_engine.config(text="● Parado")
        self._set_status("Motor detenido.")

    # -------------------------------------------------------------- reglas
    def _refresh_rules(self) -> None:
        sel = self.lst.curselection()
        self.lst.delete(0, "end")
        for r in self.rules:
            mark = "✔" if r.enabled else "✗"
            self.lst.insert("end", f" {mark}  {r.name}   ·   {r.summary()}")
        if sel and sel[0] < len(self.rules):
            self.lst.selection_set(sel[0])

    def _cur_rule(self) -> R.Rule | None:
        s = self.lst.curselection()
        return self.rules[s[0]] if s else None

    def _new_rule(self) -> None:
        self._rule_editor(R.Rule())

    def _edit_rule(self) -> None:
        r = self._cur_rule()
        if r is None:
            messagebox.showinfo(APP_NAME, "Selecciona una regla.")
            return
        self._rule_editor(r, editing=True)

    def _toggle_rule(self) -> None:
        r = self._cur_rule()
        if r is not None:
            r.enabled = not r.enabled
            self._persist()
            self.engine.reload()
            self._refresh_rules()

    def _delete_rule(self) -> None:
        s = self.lst.curselection()
        if not s:
            return
        if messagebox.askyesno(APP_NAME, "¿Eliminar la regla seleccionada?"):
            del self.rules[s[0]]
            self._persist()
            self.engine.reload()
            self._refresh_rules()

    def _test_rule(self) -> None:
        r = self._cur_rule()
        if r is None:
            return
        ctx = {"file": "(ejemplo).txt", "drive": "E:", "text": "(texto)", "window": "(ventana)"}

        def runner():
            try:
                res = actions.execute(r.action_type, r.action_params, ctx, notify=self._notify)
                self._log(f"▶ Prueba «{r.name}» → {res}")
            except Exception as exc:  # noqa: BLE001
                self._log(f"✗ Prueba «{r.name}» fallo: {exc}")
        threading.Thread(target=runner, daemon=True).start()

    def _nl_create(self) -> None:
        order = self.var_nl.get().strip()
        if not order:
            return
        self._set_status("Interpretando con IA…")

        def runner():
            rule, err = nl.rule_from_text(order, model=(self.cfg.ollama_model or None))
            self._ui(lambda: self._nl_done(rule, err))
        threading.Thread(target=runner, daemon=True).start()

    def _nl_done(self, rule, err) -> None:
        self._set_status("")
        if err:
            messagebox.showinfo(APP_NAME, err)
            return
        self.var_nl.set("")
        self._rule_editor(rule)   # abre el editor para revisar/confirmar

    # -------------------------------------------------------------- editor
    def _rule_editor(self, rule: R.Rule, editing: bool = False) -> None:
        win = tk.Toplevel(self); theme.center_window(win)
        win.title("Editar regla" if editing else "Nueva regla")
        win.configure(bg=theme.BG); win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=16); frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Nombre", style="H.TLabel").pack(anchor="w")
        v_name = tk.StringVar(value=rule.name)
        ttk.Entry(frm, textvariable=v_name, width=48).pack(anchor="w", fill="x", pady=(0, 8))

        # disparador
        ttk.Label(frm, text="CUANDO (disparador)", style="H.TLabel").pack(anchor="w")
        tlabels = [R.TRIGGERS[k]["label"] for k in R.TRIGGERS]
        tkeys = list(R.TRIGGERS)
        v_trig = tk.StringVar(value=R.TRIGGERS[rule.trigger_type]["label"])
        ttk.Combobox(frm, textvariable=v_trig, values=tlabels, state="readonly",
                     width=46).pack(anchor="w")
        tfields = ttk.Frame(frm); tfields.pack(fill="x", pady=(2, 8))
        t_widgets: dict = {}

        ttk.Label(frm, text="HAZ (accion)", style="H.TLabel").pack(anchor="w")
        alabels = [R.ACTIONS[k]["label"] for k in R.ACTIONS]
        akeys = list(R.ACTIONS)
        v_act = tk.StringVar(value=R.ACTIONS[rule.action_type]["label"])
        ttk.Combobox(frm, textvariable=v_act, values=alabels, state="readonly",
                     width=46).pack(anchor="w")
        afields = ttk.Frame(frm); afields.pack(fill="x", pady=(2, 8))
        a_widgets: dict = {}

        def trig_key():
            return tkeys[tlabels.index(v_trig.get())]

        def act_key():
            return akeys[alabels.index(v_act.get())]

        def render_trig(*_a):
            t_widgets.clear()
            self._render_fields(tfields, R.TRIGGERS[trig_key()]["fields"],
                                rule.trigger_params, t_widgets, win)

        def render_act(*_a):
            a_widgets.clear()
            self._render_fields(afields, R.ACTIONS[act_key()]["fields"],
                                rule.action_params, a_widgets, win)

        v_trig.trace_add("write", render_trig)
        v_act.trace_add("write", render_act)
        render_trig(); render_act()

        def save():
            rule.name = v_name.get().strip() or "Regla"
            rule.trigger_type = trig_key()
            rule.trigger_params = {k: var.get() for k, var in t_widgets.items()}
            rule.action_type = act_key()
            rule.action_params = {k: var.get() for k, var in a_widgets.items()}
            err = rule.validate()
            if err:
                messagebox.showwarning(APP_NAME, err, parent=win)
                return
            if not editing and rule not in self.rules:
                self.rules.append(rule)
            self._persist()
            self.engine.reload()
            self._refresh_rules()
            win.destroy()
        ttk.Button(frm, text="Guardar regla", style="Primary.TButton", command=save).pack(
            anchor="e", pady=(8, 0))
        win.grab_set()

    def _render_fields(self, parent, fields, values, store: dict, win) -> None:
        for w in parent.winfo_children():
            w.destroy()
        for key, label, kind, default in fields:
            row = ttk.Frame(parent); row.pack(fill="x", pady=2)
            ttk.Label(row, text=label + ":", width=26, style="CardMuted.TLabel").pack(side="left")
            val = values.get(key, default)
            if kind == "int":
                var = tk.StringVar(value=str(val))
                ttk.Spinbox(row, from_=1, to=86400, textvariable=var, width=12).pack(side="left")
            elif kind in ("folder", "file"):
                var = tk.StringVar(value=str(val))
                ttk.Entry(row, textvariable=var, width=30).pack(side="left", fill="x", expand=True)

                def browse(v=var, k=kind):
                    p = (filedialog.askdirectory(parent=win) if k == "folder"
                         else filedialog.askopenfilename(parent=win))
                    if p:
                        v.set(p)
                ttk.Button(row, text="…", width=3, command=browse).pack(side="left", padx=(4, 0))
            else:   # text / hotkey
                var = tk.StringVar(value=str(val))
                ttk.Entry(row, textvariable=var, width=34).pack(side="left", fill="x", expand=True)
            store[key] = var

    # -------------------------------------------------------------- toast / log
    def _notify(self, title: str, msg: str) -> None:
        self._ui(lambda: self._show_toast(title, msg))

    def _show_toast(self, title: str, msg: str) -> None:
        try:
            t = tk.Toplevel(self)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            f = tk.Frame(t, bg=theme.NAVY, padx=14, pady=10)
            f.pack()
            tk.Label(f, text=title, bg=theme.NAVY, fg="#fff", font=(theme.FONT, 10, "bold"),
                     anchor="w", justify="left").pack(anchor="w")
            if msg:
                tk.Label(f, text=msg, bg=theme.NAVY, fg="#CBD5E1", font=(theme.FONT, 9),
                         wraplength=280, anchor="w", justify="left").pack(anchor="w")
            t.update_idletasks()
            sw, sh = t.winfo_screenwidth(), t.winfo_screenheight()
            t.geometry(f"+{sw - t.winfo_width() - 24}+{sh - t.winfo_height() - 60}")
            t.after(4000, lambda: (t.winfo_exists() and t.destroy()))
        except tk.TclError:
            pass

    def _log(self, text: str) -> None:
        self._ui(lambda: self._append_log(text))

    def _append_log(self, text: str) -> None:
        try:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            # limita el historial
            if int(self.log.index("end-1c").split(".")[0]) > 500:
                self.log.delete("1.0", "200.0")
            self.log.configure(state="disabled")
        except tk.TclError:
            pass

    # -------------------------------------------------------------- dialogos
    def _settings_dialog(self) -> None:
        win = tk.Toplevel(self); theme.center_window(win)
        win.title("Opciones"); win.configure(bg=theme.BG); win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=16); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Opciones", style="H.TLabel").pack(anchor="w", pady=(0, 8))
        v_start = tk.BooleanVar(value=self.cfg.start_engine_on_open)
        ttk.Checkbutton(frm, text="Activar el motor automaticamente al abrir la app",
                        variable=v_start).pack(anchor="w")
        ttk.Label(frm, text=f"Las reglas se guardan en:\n{RULES_PATH}", style="Muted.TLabel",
                  justify="left").pack(anchor="w", pady=(10, 0))

        def save():
            self.cfg.start_engine_on_open = bool(v_start.get())
            save_config(self.cfg)
            win.destroy()
        ttk.Button(frm, text="Guardar", style="Primary.TButton", command=save).pack(anchor="e", pady=(12, 0))
        win.grab_set()

    def _ollama_dialog(self) -> None:
        win = tk.Toplevel(self); theme.center_window(win)
        win.title("Configurar IA local (Ollama)"); win.configure(bg=theme.BG)
        win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=18); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="IA local opcional con Ollama", style="H.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Con Ollama puedes crear reglas escribiendolas en lenguaje natural.\n"
                  "Es gratis y todo ocurre en tu PC. Sin ella, crea las reglas a mano.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(2, 10))
        ram, gpu = llm.system_ram_gb(), llm.has_gpu()
        rec, size, motivo = llm.recommend_model(ram, gpu)
        info = ttk.LabelFrame(frm, text="Tu equipo", padding=10); info.pack(fill="x")
        ttk.Label(info, text=f"RAM: {ram:.0f} GB · GPU NVIDIA: {'si' if gpu else 'no'}",
                  style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(info, text=f"Recomendado: {rec} ({size}) — {motivo}", style="CardMuted.TLabel",
                  wraplength=380, justify="left").pack(anchor="w", pady=(4, 0))
        body = ttk.Frame(frm); body.pack(fill="x")

        def render():
            for w in body.winfo_children():
                w.destroy()
            mods = llm.list_models(timeout=5.0)
            if mods:
                ttk.Label(body, text=f"✓ Ollama detectado ({len(mods)} modelo/s). Ya puedes usar "
                          "'Crear con IA'.", style="CardMuted.TLabel", wraplength=380,
                          justify="left").pack(anchor="w", pady=(10, 0))
            else:
                g = ttk.LabelFrame(body, text="Como activarla (una vez)", padding=10)
                g.pack(fill="x", pady=(10, 0))
                ttk.Label(g, text="1. Instala Ollama (ollama.com).\n2. En una terminal pega:",
                          style="CardMuted.TLabel", justify="left").pack(anchor="w")
                cmd = f"ollama run {rec}"
                ent = ttk.Entry(g, width=30); ent.insert(0, cmd); ent.configure(state="readonly")
                ent.pack(side="left", pady=(2, 0))
                ttk.Button(g, text="Copiar", command=lambda: (self.clipboard_clear(),
                           self.clipboard_append(cmd))).pack(side="left", padx=6, pady=(2, 0))
        ttk.Button(frm, text="🔄 Probar conexion", command=render).pack(anchor="w", pady=(10, 0))
        ttk.Button(frm, text="Abrir ollama.com",
                   command=lambda: webbrowser.open("https://ollama.com")).pack(anchor="w", pady=(6, 0))
        render()
        win.grab_set()

    # -------------------------------------------------------------- varios
    def _ui(self, fn) -> None:
        if self._closing:
            return
        try:
            self.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _set_status(self, text: str) -> None:
        try:
            self.status.config(text=text)
        except tk.TclError:
            pass

    def _persist(self) -> None:
        R.save_rules(RULES_PATH, self.rules)

    def _first_run_check(self) -> None:
        if self._closing or self.cfg.seen_welcome:
            return
        self.cfg.seen_welcome = True
        save_config(self.cfg)
        messagebox.showinfo(
            APP_NAME, "Bienvenido a AutoEscritorio.\n\n"
            "Crea reglas «cuando pasa X, haz Y»: por ejemplo, cuando conectes un USB que "
            "se abra una carpeta, o un atajo que escriba tu firma.\n\n"
            "1. Pulsa '+ Nueva' (o describe la regla con IA arriba).\n"
            "2. Activa el motor.\n\nTodo ocurre en tu PC, sin nube.")

    def _on_close(self) -> None:
        self._closing = True
        try:
            self.engine.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def main() -> None:
    from .config import setup_logging
    setup_logging()
    App().mainloop()
