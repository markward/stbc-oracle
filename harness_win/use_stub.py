"""pytest plugin (-p use_stub, with this folder on PYTHONPATH): install the pure-Python
_dauntless_host stand-in before Dauntless's conftest can put the C++ build on sys.path. Needed only
where the real extension also exists (the Mac, for validation); on Windows there is no build/python."""
import importlib.util
import os
import sys

_spec = importlib.util.spec_from_file_location(
    "_dauntless_host", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_dauntless_host.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["_dauntless_host"] = _mod
os.environ.setdefault("DAUNTLESS_STUB_HOST", "1")
