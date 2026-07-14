"""AutoEscritorio — automatiza tu PC con reglas "cuando pasa X, haz Y", en local.

Un Power Automate / Zapier del escritorio: defines disparadores (un atajo, un
archivo nuevo, que se abra un programa, una hora, un USB…) y acciones (abrir
algo, mover archivos, escribir texto, una notificacion…). El motor corre en
segundo plano. Sin nube ni cuentas: tus automatizaciones se quedan en tu PC.
"""

from __future__ import annotations

APP_NAME = "AutoEscritorio"
APP_VERSION = "1.1.0"   # fuente unica de version: build-installer.ps1 la inyecta al .iss
