"""Seeds master template files + DB rows for local/dev testing.

Some doc types (Approved SRS, Approved HLD, Approved LLD) get the real
Marlabs template files, sourced from the team's existing library (Azure
DevOps "RAG Agent" repo). Everything else still gets placeholder text until
a real file is available — see docs/AI_Agent_Discovery_Documentation.md,
section 8.

Uses the same Supabase REST client the running app uses (SUPABASE_URL/
SUPABASE_KEY in .env), not a direct Postgres connection — this is meant to
be run wherever the app itself runs, on any network, including ones that
block direct DB ports. Only Alembic migrations still need a direct
connection, since PostgREST has no schema-migration endpoint.

Idempotent: safe to re-run. Existing placeholder files/rows are left as-is
unless --force is passed, so it won't clobber real templates once they exist.
"""

import argparse
from pathlib import Path

from app.config import settings
from app.core.file_naming import slugify
from app.core.phase_config import get_phase_config
from app.db.rest_client import SupabaseRestClient
from app.storage.local import LocalFilesystemStorage

PLACEHOLDER_EXTENSION = "txt"

# Real Marlabs template files, sourced from the team's existing library
# (Azure DevOps "RAG Agent" repo). Only doc types with a genuine matching
# file are listed here — everything else still gets the placeholder text
# until the real file is available.
REAL_TEMPLATES_DIR = Path(__file__).parent / "seed_assets" / "real_templates"
REAL_TEMPLATE_FILES: dict[str, str] = {
    "Approved SRS": "srs.docx",
    "Approved HLD": "hld.docx",
    "Approved LLD": "lld.docx",
}


def _placeholder_content(doc_type: str, phase_name: str) -> bytes:
    return (
        f"MOCK TEMPLATE — {doc_type}\n"
        f"Phase: {phase_name}\n\n"
        "This is a placeholder standing in for the real Marlabs template until "
        "SharePoint access is available. Safe to use for testing the request/gate/"
        "download/upload flow end-to-end. Replace by swapping the storage backend "
        "and re-pointing TEMPLATE_STORE_PATH — no code changes required.\n"
    ).encode("utf-8")


def seed_templates(rest: SupabaseRestClient, force: bool = False) -> None:
    config = get_phase_config()
    storage = LocalFilesystemStorage(settings.template_store_path)

    for phase in config.phases:
        folder = f"{phase.sequence:02d}_{phase.name}"
        for doc_type in phase.required_documents:
            real_file = REAL_TEMPLATE_FILES.get(doc_type)
            extension = (
                real_file.rsplit(".", 1)[-1] if real_file else PLACEHOLDER_EXTENSION
            )
            filename = f"{slugify(doc_type)}.{extension}"
            storage_path = f"{folder}/{filename}"

            if force or not storage.exists(storage_path):
                if real_file:
                    content = (REAL_TEMPLATES_DIR / real_file).read_bytes()
                else:
                    content = _placeholder_content(doc_type, phase.name)
                storage.save(storage_path, content)

            existing = rest.select_one("templates", doc_type=doc_type)
            if existing is None:
                rest.insert(
                    "templates",
                    {
                        "doc_type": doc_type,
                        "storage_path": storage_path,
                        "filename": filename,
                    },
                )
            elif force:
                rest.update(
                    "templates",
                    {"id": existing["id"]},
                    {"storage_path": storage_path, "filename": filename},
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing placeholder files/DB rows",
    )
    args = parser.parse_args()

    rest = SupabaseRestClient(settings.supabase_url, settings.supabase_key)
    try:
        seed_templates(rest, force=args.force)
        print("Seeded template library (files + DB rows) for local/dev testing.")
    finally:
        rest.close()


if __name__ == "__main__":
    main()
