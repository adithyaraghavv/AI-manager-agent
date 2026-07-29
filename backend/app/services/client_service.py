"""Client folder lifecycle: creation of the client row + full phase sub-structure
on first contact, and lookup of which documents already exist for a client."""
from sqlalchemy.orm import Session

from app.core.phase_config import PhaseConfig
from app.db.models import Client, ClientDocument
from app.storage.base import StorageBackend


def get_or_create_client(db: Session, storage: StorageBackend, config: PhaseConfig, client_name: str) -> Client:
    client = db.query(Client).filter_by(name=client_name).one_or_none()
    is_new = client is None
    if client is None:
        client = Client(name=client_name)
        db.add(client)
        db.commit()
        db.refresh(client)

    if is_new or not storage.exists(client_name):
        storage.make_dir(client_name)
        for phase in config.phases:
            storage.make_dir(f"{client_name}/{phase.sequence:02d}_{phase.name}")

    return client


def existing_document_types(db: Session, client: Client) -> set[str]:
    return {doc.doc_type for doc in db.query(ClientDocument).filter_by(client_id=client.id).all()}
