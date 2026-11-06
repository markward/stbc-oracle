"""Pure-Python stand-in for Dauntless's C++ extension, for HEADLESS duel runs on a machine without
the C++ build (the Windows PC). Put this folder first on PYTHONPATH; never use it for the game.

What a headless duel uses from the real module (measured on the Mac, 2026-10-16, with a logging
proxy over the real extension during Galaxy-Keldon duels):
  - transform_* (the native transform store): NOT provided here, so engine.appc.transform_store
    selects its PythonTransformStore. Both keep doubles and share a conformance test
    (tests/unit/test_transform_store_conformance.py), so behaviour is the same.
  - nif_shapes(path): the hull meshes the duel harness traces (hull line of sight, shield-face box).
    Served from hull_shapes.json.gz, which each user exports from their OWN game install with the
    real extension (nif_shapes of each stock ship, saved as JSON keyed by the path relative to the
    game folder, lower-case, '/'). It is game asset data: never commit it (.gitignore). A path that
    is not in the file RAISES: a silent miss would make every subsystem "hittable" and quietly
    change results.
  - set_* renderer pushes, audio, keys, InstanceId, ambient_gradient_set_enabled: no-ops here.
  - developer_mode: False.
"""
import gzip
import json
import os

developer_mode = False

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHAPES = None


def _shapes():
    global _SHAPES
    if _SHAPES is None:
        with gzip.open(os.path.join(_HERE, "hull_shapes.json.gz"), "rt") as fh:
            _SHAPES = json.load(fh)
    return _SHAPES


def nif_shapes(path):
    key = str(path).replace("\\", "/").lower()
    i = key.find("data/models/")
    if i < 0 or key[i:] not in _shapes():
        raise KeyError("hull_shapes.json.gz has no shapes for %r - export it from your "
                       "own game install with the real extension before running this ship here" % path)
    return _shapes()[key[i:]]


class _NoOp:
    """Callable and attribute-able no-op for renderer/audio/input calls a headless run makes."""

    def __call__(self, *a, **k):
        return None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _NOOP

    def __bool__(self):
        return False

    def __int__(self):
        return 0


_NOOP = _NoOp()


def __getattr__(name):
    # transform_* must stay absent so the Python transform store is chosen
    if name.startswith("transform_") or name.startswith("__"):
        raise AttributeError(name)
    return _NOOP
