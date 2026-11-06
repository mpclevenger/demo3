"""Run a TRUST command from the top of the repo, with no shell or PYTHONPATH needed.

    python manage.py migrate          set up the database tables (the Procfile's release line)
    python manage.py map 2026-10      any other command: python manage.py --help
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "backend"))

from trust.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
