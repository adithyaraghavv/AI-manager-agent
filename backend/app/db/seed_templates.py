"""Seeds placeholder master template files + DB rows for local/dev testing.

This exists because we don't yet have SharePoint access to the real template
library (see docs/AI_Agent_Discovery_Documentation.md, section 8). It's a
stand-in for that library, not a separate code path: it writes into the same
`templates` table and the same `TEMPLATE_STORE_PATH` storage backend that
production SharePoint-backed templates will use once that access lands.

Migrating to real SharePoint templates later needs ZERO changes here or in
any service code — only:
  1. A SharePointStorage implementation of StorageBackend (app/storage/base.py)
  2. Re-pointing TEMPLATE_STORE_PATH (or swapping which backend get_template_storage()
     constructs, in app/deps.py) at that implementation
  3. Re-running a real-template equivalent of this seed script (or updating the
     `templates` table's storage_path/filename directly) to point at the real files

Idempotent: safe to re-run. Existing placeholder files/rows are left as-is
unless --force is passed, so it won't clobber real templates once they exist.
"""
import argparse

from sqlalchemy.orm import Session

from app.core.file_naming import slugify
from app.core.phase_config import get_phase_config
from app.db.models import Template
from app.db.session import SessionLocal
from app.storage.local import LocalFilesystemStorage
from app.config import settings

PLACEHOLDER_EXTENSION = "txt"


def _placeholder_content(doc_type: str, phase_name: str) -> bytes:
    return (
        f"MOCK TEMPLATE — {doc_type}\n"
        f"Phase: {phase_name}\n\n"
        "This is a placeholder standing in for the real Marlabs template until "
        "SharePoint access is available. Safe to use for testing the request/gate/"
        "download/upload flow end-to-end. Replace by swapping the storage backend "
        "and re-pointing TEMPLATE_STORE_PATH — no code changes required.\n"
    ).encode("utf-8")


def seed_templates(db: Session, force: bool = False) -> None:
    config = get_phase_config()
    storage = LocalFilesystemStorage(settings.template_store_path)

    for phase in config.phases:
        folder = f"{phase.sequence:02d}_{phase.name}"
        for doc_type in phase.required_documents:
            filename = f"{slugify(doc_type)}.{PLACEHOLDER_EXTENSION}"
            storage_path = f"{folder}/{filename}"

            if force or not storage.exists(storage_path):
                storage.save(storage_path, _placeholder_content(doc_type, phase.name))

            template = db.query(Template).filter_by(doc_type=doc_type).one_or_none()
            if template is None:
                db.add(Template(doc_type=doc_type, storage_path=storage_path, filename=filename))
            elif force:
                template.storage_path = storage_path
                template.filename = filename

    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing placeholder files/DB rows"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_templates(db, force=args.force)
        print("Seeded mock template library (files + DB rows) for local/dev testing.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
