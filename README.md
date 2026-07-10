# AutoEscritorio

Automatización de escritorio para **Windows** (estilo Power Automate, pero simple y **100% local**): reglas *disparador → acción* que vigilan tu PC y actúan por ti.

## ⬇️ Descargar (Windows 10/11)

### ➡️ [**Descargar AutoEscritorio (instalador .exe)**](https://github.com/Octonove/autoescritorio/releases/latest/download/AutoEscritorio-Setup.exe)

Descarga **directa** del instalador, sin registro. También puedes ver la [última versión y notas](https://github.com/Octonove/autoescritorio/releases/latest).

> Si Windows muestra *"Windows protegió tu PC"* (es normal en programas nuevos sin firma): pulsa **Más información → Ejecutar de todas formas**. Se instala sin permisos de administrador.

---

## Funciones

**Disparadores**: cada X tiempo · a una hora diaria · atajo de teclado global · archivo nuevo en una carpeta (espera a que termine de copiarse) · se abre/cierra un programa · aparece una ventana · se conecta un USB · copias texto al portapapeles.

**Acciones**: abrir programa/archivo/URL · ejecutar comando (sin shell: los datos del disparador nunca pueden inyectar) · notificación · escribir texto · pulsar teclas · mover/copiar archivos (sin sobrescribir) · reproducir sonido · anotar en un log.

- **Reglas en lenguaje natural** (opcional, [Ollama](https://ollama.com)): «cuando conecte un USB, abre la calculadora» → regla lista.
- Motor por transiciones con línea base (no dispara con lo ya existente), cooldown anti-ráfagas y registro de actividad.

## Stack

Python 3 + Tkinter (ttk) · ctypes/Win32 (hotkeys, procesos, portapapeles, SendInput) · Ollama opcional.

Depende del paquete compartido de la suite [`octonove-core`](https://github.com/Octonove/octonove-core) (tema, capa Ollama, config): debe estar en el `sys.path` del entorno (vía `.pth` o copia junto al proyecto).

## Compilar

```powershell
.\build\build.ps1              # ejecutable (PyInstaller onedir)
.\build\build-installer.ps1    # instalador (Inno Setup)
```

## Tests

```powershell
python -m pytest tests/ -q
```

## Licencia

[MIT](LICENSE) — © 2026 Octonove.
