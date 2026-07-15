"""Utilidades de Windows via ctypes para los disparadores y acciones del motor.
Sin dependencias externas: procesos, ventanas, unidades, portapapeles y envio de
teclas/texto."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    WIN = True
except Exception as exc:  # noqa: BLE001
    WIN = False
    logger.warning("API de Windows no disponible: %s", exc)


def _declare_prototypes() -> None:
    """OBLIGATORIO en Python 64-bit: sin restype/argtypes, ctypes trunca los
    handles/punteros a 32 bits -> corrupcion y segfault."""
    c = ctypes
    w = wintypes
    _kernel32.CreateToolhelp32Snapshot.restype = w.HANDLE
    _kernel32.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    _kernel32.Process32First.restype = w.BOOL
    _kernel32.Process32First.argtypes = [w.HANDLE, c.c_void_p]
    _kernel32.Process32Next.restype = w.BOOL
    _kernel32.Process32Next.argtypes = [w.HANDLE, c.c_void_p]
    _kernel32.CloseHandle.argtypes = [w.HANDLE]
    _kernel32.GlobalLock.restype = c.c_void_p
    _kernel32.GlobalLock.argtypes = [w.HANDLE]
    _kernel32.GlobalUnlock.argtypes = [w.HANDLE]
    _kernel32.GetLogicalDrives.restype = w.DWORD
    _kernel32.GetDriveTypeW.restype = w.UINT
    _kernel32.GetDriveTypeW.argtypes = [w.LPCWSTR]
    _user32.OpenClipboard.argtypes = [w.HWND]
    _user32.CloseClipboard.argtypes = []
    _user32.GetClipboardData.restype = w.HANDLE
    _user32.GetClipboardData.argtypes = [w.UINT]
    _user32.IsWindowVisible.argtypes = [w.HWND]
    _user32.GetWindowTextLengthW.argtypes = [w.HWND]
    _user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    _user32.GetAsyncKeyState.restype = c.c_short
    _user32.GetAsyncKeyState.argtypes = [c.c_int]
    _user32.SendInput.restype = w.UINT
    # dwExtraInfo es ULONG_PTR (8 bytes en x64) -> c_void_p, no un puntero a c_ulong
    _user32.keybd_event.argtypes = [w.BYTE, w.BYTE, w.DWORD, c.c_void_p]


if WIN:
    try:
        _declare_prototypes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron declarar prototipos: %s", exc)


# --- procesos ---------------------------------------------------------------
def list_processes() -> set[str]:
    """Nombres (.exe) de los procesos en ejecucion, en minusculas."""
    if not WIN:
        return set()
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]
    out: set[str] = set()
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    INVALID = (1 << 64) - 1   # INVALID_HANDLE_VALUE como puntero sin signo
    if not snap or snap == INVALID:
        return out
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = _kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            try:
                name = entry.szExeFile.decode("mbcs", "replace").lower()
            except Exception:  # noqa: BLE001
                name = ""
            if name:
                out.add(name)
            ok = _kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snap)
    return out


# --- ventanas ---------------------------------------------------------------
def list_window_titles() -> list[str]:
    if not WIN:
        return []
    titles: list[str] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd):
            n = _user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                _user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value:
                    titles.append(buf.value)
        return True
    try:
        _user32.EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("EnumWindows fallo: %s", exc)
    return titles


# --- unidades ---------------------------------------------------------------
def removable_drives() -> set[str]:
    """Letras de unidades extraibles (USB) conectadas, p.ej. {'E:'}."""
    if not WIN:
        return set()
    DRIVE_REMOVABLE = 2
    out: set[str] = set()
    mask = _kernel32.GetLogicalDrives()
    for i in range(26):
        if mask & (1 << i):
            letter = f"{chr(65 + i)}:"
            try:
                if _kernel32.GetDriveTypeW(letter + "\\") == DRIVE_REMOVABLE:
                    out.add(letter)
            except Exception:  # noqa: BLE001
                pass
    return out


# --- portapapeles -----------------------------------------------------------
def get_clipboard_text() -> str:
    if not WIN:
        return ""
    CF_UNICODETEXT = 13
    if not _user32.OpenClipboard(0):
        return ""
    try:
        h = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = _kernel32.GlobalLock(h)
        if not ptr:
            return ""
        try:
            return ctypes.c_wchar_p(ptr).value or ""
        finally:
            _kernel32.GlobalUnlock(h)
    except Exception:  # noqa: BLE001
        return ""
    finally:
        _user32.CloseClipboard()


# --- envio de teclas / texto ------------------------------------------------
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# shift, ctrl, alt, win-izq, win-der
_MOD_VKS = (0x10, 0x11, 0x12, 0x5B, 0x5C)


def wait_modifiers_released(timeout: float = 1.5) -> bool:
    """Espera a que Ctrl/Alt/Shift/Win esten FISICAMENTE soltados. Devuelve True
    si se soltaron, False si al vencer el plazo seguian pulsados.

    Las reglas se disparan tipicamente con un ATAJO: en el momento de ejecutar
    la accion, el usuario aun tiene Ctrl/Alt pulsados. Si se inyecta el texto o
    la combinacion en ese instante, la app destino recibe Ctrl+letra (atajos) en
    vez de texto: 'no escribe nada' aunque el envio fue correcto. El plazo (1.5s)
    es < que el join de parada del motor (2s), para no dejar teclas 'colgadas'.
    """
    if not WIN:
        return True
    import time
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if not any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MOD_VKS):
            return True
        time.sleep(0.02)
    return False


def press_combo(parsed: dict) -> bool:
    """parsed = {'mods': set(vk), 'key': vk}. Pulsa la combinacion. Devuelve
    False si no se pudo (los modificadores del disparador seguian pulsados: se
    aborta en vez de inyectar un combo corrupto)."""
    if not WIN or not parsed:
        return False
    if not wait_modifiers_released():   # aun con Ctrl/Alt del atajo: no inyectar
        logger.warning("press_combo abortado: modificadores del atajo aun pulsados.")
        return False
    mods = list(parsed.get("mods", []))
    key = parsed.get("key")
    for vk in mods:
        _user32.keybd_event(vk, 0, 0, 0)
    if key:
        _user32.keybd_event(key, 0, 0, 0)
        _user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
    for vk in reversed(mods):
        _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    return True


class _KEYBDINPUT(ctypes.Structure if WIN else object):
    if WIN:
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p)]   # ULONG_PTR


class _MOUSEINPUT(ctypes.Structure if WIN else object):
    # No se usa para nada, pero es el miembro MAS GRANDE de la union INPUT: sin
    # el, sizeof(INPUT) sale 32 en x64 en vez de 40, SendInput rechaza el cbSize
    # y devuelve 0 -> el texto NUNCA se escribia (fallo silencioso historico).
    if WIN:
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


if WIN:
    class _INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    # argtypes de SendInput: hay que declararlo AQUI, despues de definir _INPUT,
    # o el puntero LPINPUT se trunca a 32 bits en x64 (corrupcion de struct).
    try:
        _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    except Exception:  # noqa: BLE001
        pass


def type_text(text: str) -> int:
    """Escribe texto unicode donde este el foco (SendInput KEYEVENTF_UNICODE).

    Devuelve cuantas unidades UTF-16 se INYECTARON de verdad (0 si SendInput
    fue bloqueado, p.ej. la ventana activa corre como administrador). Antes se
    daba por hecho el exito y el registro decia 'Escrito N caracteres' aunque
    no se hubiera escrito nada.
    """
    if not WIN or not text:
        return 0
    if not wait_modifiers_released():
        # con Ctrl/Alt del atajo aun pulsados, el texto llegaria como atajos:
        # mejor no escribir nada y reportarlo honestamente
        logger.warning("type_text abortado: modificadores del atajo aun pulsados.")
        return 0
    INPUT_KEYBOARD = 1
    # utf-16-le: los caracteres fuera del BMP (emoji) viajan como par sustituto
    raw = text.encode("utf-16-le")
    codes = [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]
    inputs = []
    for code in codes:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = _INPUT()
            inp.type = INPUT_KEYBOARD
            inp.ki = _KEYBDINPUT(0, code, flags, 0, None)
            inputs.append(inp)
    n = len(inputs)
    arr = (_INPUT * n)(*inputs)
    sent = int(_user32.SendInput(n, arr, ctypes.sizeof(_INPUT)))
    if sent < n:
        logger.warning("SendInput inyecto %d/%d eventos (¿ventana elevada?)", sent, n)
    return sent // 2


def key_down(vk: int) -> bool:
    if not WIN:
        return False
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)
