# CivicPulse App Package
import sys
import types
from pathlib import Path

# Ensure 'backend' is recognized as a package pointing to parent of 'app'
_app_parent = str(Path(__file__).resolve().parent.parent)
if "backend" not in sys.modules:
    try:
        import backend  # noqa: F401
    except ImportError:
        _backend_pkg = types.ModuleType("backend")
        _backend_pkg.__path__ = [_app_parent]
        sys.modules["backend"] = _backend_pkg
