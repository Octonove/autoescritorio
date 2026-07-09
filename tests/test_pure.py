"""Tests de logica pura de AutoEscritorio."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoescritorio import rules as R, actions, nl  # noqa: E402


# --- reglas ------------------------------------------------------------------
def test_parse_combo():
    c = R.parse_combo("ctrl+alt+g")
    assert c and c["key"] == ord("G") and len(c["mods"]) == 2
    assert R.parse_combo("ctrl+s")["key"] == ord("S")
    assert R.parse_combo("f9")["key"] == 0x78
    assert R.parse_combo("") is None
    assert R.parse_combo("ctrl") is None       # falta la tecla
    assert R.parse_combo("ctrl+??") is None


def test_valid_hhmm():
    assert R._valid_hhmm("09:00") and R._valid_hhmm("23:59") and R._valid_hhmm("0:05")
    assert not R._valid_hhmm("24:00") and not R._valid_hhmm("9") and not R._valid_hhmm("ab:cd")


def test_substitute():
    out = R.substitute({"destino": "abre {file} ya", "x": 3}, {"file": "C:/a.txt"})
    assert out["destino"] == "abre C:/a.txt ya"
    assert out["x"] == 3


def test_rule_validate():
    r = R.Rule(trigger_type="interval", trigger_params={"segundos": 5},
               action_type="notify", action_params={"titulo": "t", "mensaje": "m"})
    assert r.validate() is None
    bad = R.Rule(trigger_type="interval", trigger_params={"segundos": 0}, action_type="notify")
    assert bad.validate() is not None
    bad2 = R.Rule(trigger_type="daily", trigger_params={"hora": "99:99"}, action_type="notify")
    assert bad2.validate() is not None
    bad3 = R.Rule(trigger_type="file_new", trigger_params={"carpeta": ""}, action_type="notify")
    assert bad3.validate() is not None
    bad4 = R.Rule(trigger_type="interval", trigger_params={"segundos": 5},
                  action_type="open", action_params={"destino": ""})
    assert bad4.validate() is not None


def test_rule_summary():
    r = R.Rule(trigger_type="usb_connected", action_type="open")
    s = r.summary()
    assert "USB" in s and "→" in s


def test_rules_roundtrip(tmp_path):
    path = tmp_path / "rules.json"
    rules = [R.Rule(name="A", trigger_type="hotkey", trigger_params={"combo": "ctrl+alt+a"},
                    action_type="notify", action_params={"titulo": "Hola"}),
             R.Rule(name="B", enabled=False, trigger_type="interval",
                    trigger_params={"segundos": 60}, action_type="play_sound")]
    R.save_rules(path, rules)
    back = R.load_rules(path)
    assert len(back) == 2
    assert back[0].name == "A" and back[0].trigger_params["combo"] == "ctrl+alt+a"
    assert back[1].enabled is False


def test_load_rules_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("no es json", encoding="utf-8")
    assert R.load_rules(p) == []
    assert R.load_rules(tmp_path / "noexiste.json") == []


# --- acciones ----------------------------------------------------------------
def test_action_move_and_copy(tmp_path):
    src = tmp_path / "src"; dst = tmp_path / "dst"
    src.mkdir()
    for n in ("a.pdf", "b.pdf", "c.txt"):
        (src / n).write_text("x", encoding="utf-8")
    res = actions.execute("copy_files", {"origen": str(src), "patron": "*.pdf", "destino": str(dst)})
    assert "2" in res
    assert (dst / "a.pdf").is_file() and (src / "a.pdf").is_file()  # copia: origen intacto
    res2 = actions.execute("move_files", {"origen": str(src), "patron": "*.pdf", "destino": str(dst)})
    assert "2" in res2
    assert not (src / "a.pdf").exists()      # movido


def test_copy_no_silent_overwrite(tmp_path):
    src = tmp_path / "s"; dst = tmp_path / "d"; src.mkdir()
    (src / "a.txt").write_text("v1", encoding="utf-8")
    actions.execute("copy_files", {"origen": str(src), "patron": "*.txt", "destino": str(dst)})
    (src / "a.txt").write_text("v2", encoding="utf-8")
    actions.execute("copy_files", {"origen": str(src), "patron": "*.txt", "destino": str(dst)})
    names = sorted(p.name for p in dst.iterdir())
    assert names == ["a (1).txt", "a.txt"]   # no se sobrescribe en silencio


def test_action_write_log(tmp_path):
    log = tmp_path / "sub" / "log.txt"
    actions.execute("write_log", {"ruta": str(log), "texto": "evento {file}"}, {"file": "x.pdf"})
    content = log.read_text(encoding="utf-8")
    assert "evento x.pdf" in content


def test_action_unknown():
    with pytest.raises(actions.ActionError):
        actions.execute("inventada", {})


def test_action_open_empty():
    with pytest.raises(actions.ActionError):
        actions.execute("open", {"destino": ""})


# --- lenguaje natural --------------------------------------------------------
def test_nl_extract_json():
    raw = 'claro: {"name":"x","trigger_type":"usb_connected","trigger_params":{},' \
          '"action_type":"open","action_params":{"destino":"calc"}} fin'
    d = nl._extract_json(raw)
    assert d["trigger_type"] == "usb_connected" and d["action_params"]["destino"] == "calc"


def test_nl_extract_json_invalid():
    assert nl._extract_json("sin json") is None


def test_nl_filter_fields():
    fields = R.ACTIONS["notify"]["fields"]
    out = nl._filter_fields({"titulo": "T", "mensaje": "M", "colado": "x"}, fields)
    assert out == {"titulo": "T", "mensaje": "M"}


def test_nl_catalog_text_has_types():
    txt = nl._catalog_text()
    assert "usb_connected" in txt and "type_text" in txt and "move_files" in txt
