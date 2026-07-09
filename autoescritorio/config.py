"""Configuracion, rutas y persistencia de reglas de AutoEscritorio (shim del
nucleo compartido octonove_core.config)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from octonove_core.config import get_data_dir as _get_data_dir
from octonove_core.config import load_config as _load_config
from octonove_core.config import save_config as _save_config
from octonove_core.config import setup_logging as _setup_logging

from . import APP_NAME

logger = logging.getLogger(__name__)


def get_data_dir():
    return _get_data_dir(APP_NAME)


CONFIG_PATH = get_data_dir() / "config.json"
RULES_PATH = get_data_dir() / "rules.json"
LOG_PATH = get_data_dir() / "autoescritorio.log"


@dataclass
class AppConfig:
    start_engine_on_open: bool = True    # arrancar el motor al abrir
    ollama_model: str = ""
    seen_welcome: bool = False


def load_config() -> AppConfig:
    return _load_config(CONFIG_PATH, AppConfig)


def save_config(cfg: AppConfig) -> None:
    _save_config(cfg, CONFIG_PATH)


def setup_logging() -> None:
    _setup_logging(LOG_PATH)
