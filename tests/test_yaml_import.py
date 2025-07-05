import pytest

def test_can_import_yaml():
    import yaml
    assert yaml.__version__ is not None
