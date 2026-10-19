"""Thin host adapter; the independently maintained plugin owns its implementation."""
import importlib.util
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def plugin():
    path=Path(__file__).resolve().parent/'_internal/plugins/offline_previs/plugin.py'
    spec=importlib.util.spec_from_file_location('myridtv_plugin_offline_previs',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
