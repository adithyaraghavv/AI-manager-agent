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
    """A completed document filed for a client under a specific phase/doc type."""

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
