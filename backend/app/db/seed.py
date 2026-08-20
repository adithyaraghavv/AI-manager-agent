"""Seeds phases/required_documents from config/sdlc_phase_config.json.

Idempotent: safe to re-run. The JSON file is the source of truth — this
script only projects it into the DB, it never writes back to the JSON.
"""

from sqlalchemy.orm import Session

from app.core.phase_config import get_phase_config
from app.db.models import Phase, RequiredDocument
from app.db.session import SessionLocal


def seed_phases(db: Session) -> None:
    config = get_phase_config()

    for phase_def in config.phases:
        phase = db.query(Phase).filter_by(name=phase_def.name).one_or_none()
        if phase is None:
            phase = Phase(name=phase_def.name, sequence=phase_def.sequence)
            db.add(phase)
            db.flush()
        else:
            phase.sequence = phase_def.sequence

        existing_doc_types = {rd.doc_type for rd in phase.required_documents}
        for doc_type in phase_def.required_documents:
            if doc_type not in existing_doc_types:
                db.add(RequiredDocument(phase_id=phase.id, doc_type=doc_type))

    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed_phases(db)
        print("Seeded phases and required documents from sdlc_phase_config.json")
    finally:
        db.close()


if __name__ == "__main__":
    main()
