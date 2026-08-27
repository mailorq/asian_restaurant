import importlib

import pytest

MIGRATION = "operations.migrations.0008_operationcommand_command_plane"


class _QS:
    def __init__(self, exists: bool):
        self._exists = exists

    def using(self, _alias):
        return self

    def exists(self) -> bool:
        return self._exists


class _Model:
    def __init__(self, exists: bool):
        self.objects = _QS(exists)


class _Apps:
    def __init__(self, exists: bool):
        self._exists = exists

    def get_model(self, _app, _model):
        return _Model(self._exists)


class _Schema:
    class connection:
        alias = "default"


def _preflight():
    return importlib.import_module(MIGRATION)._forbid_legacy_rows


def test_0008_preflight_blocks_legacy_rows():
    with pytest.raises(RuntimeError):
        _preflight()(_Apps(exists=True), _Schema())


def test_0008_preflight_allows_empty_table():
    _preflight()(_Apps(exists=False), _Schema())  # must not raise
