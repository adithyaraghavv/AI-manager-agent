"""Test harness for the SharePoint storage backend.

Kept *outside* backend/tests/ on purpose: those tests import the app's
services layer and rely on a fake Supabase; these tests should exercise
only ``app/storage/sharepoint.py`` (and the DI factory) in isolation so
a failure here points straight at the SharePoint integration, not at
some unrelated services-layer regression.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the backend package importable ("import app.storage.sharepoint")
# without an editable install — matches how backend/tests/conftest.py does it.
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
