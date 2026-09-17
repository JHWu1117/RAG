"""Compatibility namespace for the historical top-level import path."""

from importlib import import_module

_package = import_module("src.ingestion")
__path__ = _package.__path__

