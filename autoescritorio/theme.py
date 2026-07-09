"""Sistema de diseno de AutoEscritorio: tema navy/terracota compartido de la suite
(octonove_core.theme) + los estilos propios del motor (Go/Stop.TButton, OK.TLabel)."""

from __future__ import annotations

from tkinter import ttk

from octonove_core.theme import *  # noqa: F401,F403
from octonove_core.theme import apply as _core_apply
from octonove_core.theme import BG, DANGER, FONT, F_SMALL, SUCCESS, WHITE


def apply(root) -> None:
    _core_apply(root)
    st = ttk.Style(root)
    # Estilos exclusivos del motor start/stop de esta app.
    st.configure("OK.TLabel", background=BG, foreground=SUCCESS, font=F_SMALL)
    st.configure("Go.TButton", font=(FONT, 12, "bold"), padding=(20, 11), relief="flat",
                 background=SUCCESS, foreground=WHITE, bordercolor=SUCCESS)
    st.map("Go.TButton", background=[("active", "#15803D"), ("pressed", "#166534")])
    st.configure("Stop.TButton", font=(FONT, 12, "bold"), padding=(20, 11), relief="flat",
                 background=DANGER, foreground=WHITE, bordercolor=DANGER)
    st.map("Stop.TButton", background=[("active", "#B91C1C"), ("pressed", "#991B1B")])
