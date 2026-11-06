"""The website, for gunicorn:  gunicorn wsgi:app  (finds the code in backend/ by itself; no shell or PYTHONPATH needed)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "backend"))

from trust.web import app  # noqa: E402,F401
