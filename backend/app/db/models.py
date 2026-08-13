from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Phase(Base):
    """Mirrors config/sdlc_phase_config.json — seeded, not hand-edited."""

    __tablename__ = "phases"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    sequence: Mapped[int] = mapped_column(unique=True, nullable=False)

    required_documents: Mapped[list["RequiredDocument"]] = relationship(back_populates="phase")


class RequiredDocument(Base):
    """A document type required by a phase, e.g. 'MSA' under Pre-requisites."""

    __tablename__ = "required_documents"
    __table_args__ = (UniqueConstraint("phase_id", "doc_type", name="uq_phase_doc_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("phases.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)

    phase: Mapped["Phase"] = relationship(back_populates="required_documents")


class Template(Base):
    """One canonical template per document type, stored in the master template folder."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    documents: Mapped[list["ClientDocument"]] = relationship(back_populates="client")


class ClientDocument(Base):
    """A completed document filed for a client under a specific phase/doc type.
    Always points at the CURRENT (latest) version — full version history lives
    in DocumentVersion, never overwritten or deleted."""

    __tablename__ = "client_documents"
    __table_args__ = (UniqueConstraint("client_id", "doc_type", name="uq_client_doc_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    phase_name: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())

    client: Mapped["Client"] = relationship(back_populates="documents")


class DocumentVersion(Base):
    """One immutable snapshot of a client's document at the moment it was
    uploaded. Every upload for a given (client, doc_type) creates a NEW row
    here — nothing is ever overwritten or deleted, so the full history is
    always recoverable. ClientDocument tracks only the current pointer;
    this table is the source of truth for "what did version 2 look like."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("client_id", "doc_type", "version_number", name="uq_client_doc_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())


class NotApplicableDocument(Base):
    """Marks a document type as not required for a specific client — e.g. the
    client already handed over finished requirements in the SOW, so
    "Requirement Analysis" documents don't apply to this engagement. Gating
    treats a marked doc_type the same as an existing one (it stops counting
    as missing), without actually creating a fake ClientDocument row."""

    __tablename__ = "not_applicable_documents"
    __table_args__ = (UniqueConstraint("client_id", "doc_type", name="uq_client_doc_not_applicable"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    marked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SowMetadata(Base):
    """AI-extracted key facts pulled from a client's filed SOW — contract
    value, start/end dates, and a scope summary — so a PM can ask for them
    directly instead of opening the document. Extraction is on-demand (a
    chat request re-runs it against whatever SOW is currently on file) and
    this row is simply overwritten each time; it's a cache of the last
    extraction, not a source of truth independent of the SOW file itself."""

    __tablename__ = "sow_metadata"
    __table_args__ = (UniqueConstraint("client_id", name="uq_client_sow_metadata"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    contract_value: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    scope_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(server_default=func.now())
