"""Compatibility namespace for the historical top-level import path."""

from importlib import import_module

_package = import_module("src.observability")
__path__ = _package.__path__

