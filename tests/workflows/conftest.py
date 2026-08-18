"""Isolation marker for the workflows test suite.

Keeps pytest from confusing this suite with `backend/tests/` — those tests import
from `backend.app.*` and rely on their own conftest. These tests only touch YAML
files under `.github/` and have no import-path overlap.
"""
