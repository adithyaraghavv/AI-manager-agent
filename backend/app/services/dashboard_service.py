"""Cross-client status view for a manager dashboard.

Unlike everything else in app.services, this deliberately has no gating
concept — it aggregates every client's progress so a manager/PM lead can see
the whole portfolio at a glance, including which clients are stuck and for
how long. Read-only, no hard-block logic involved.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings
from app.core.gating import missing_documents
from app.core.phase_config import PhaseConfig
from app.core.timestamps import parse_supabase_ts
from app.db.rest_client import SupabaseRestClient


@dataclass
class ClientStatus:
    client_name: str
    total_phases: int
    phases_complete: int
    current_phase: str | None  # None means every phase is complete
    missing_documents: tuple[str, ...]
    last_activity_at: datetime | None
    days_since_activity: float | None
    is_stale: bool


def list_client_statuses(
    rest: SupabaseRestClient, config: PhaseConfig
) -> list[ClientStatus]:
    clients = rest.select_active("clients")
    now = datetime.now(timezone.utc)
    statuses = []

    for client in clients:
        documents = rest.select("client_documents", client_id=client["id"])
        existing = {doc["doc_type"] for doc in documents}

        phases_complete = 0
        current_phase: str | None = None
        current_missing: tuple[str, ...] = ()
        for phase in config.phases:
            missing = missing_documents(phase, existing)
            if missing:
                if current_phase is None:
                    current_phase = phase.name
                    current_missing = missing
            else:
                phases_complete += 1

        timestamps = [
            parse_supabase_ts(doc["uploaded_at"])
            for doc in documents
            if doc.get("uploaded_at")
        ]
        if not timestamps and client.get("created_at"):
            timestamps = [parse_supabase_ts(client["created_at"])]
        last_activity = max(timestamps) if timestamps else None

        days_since = (
            (now - last_activity).total_seconds() / 86400 if last_activity else None
        )
        is_stale = (
            current_phase is not None
            and days_since is not None
            and days_since > settings.stale_after_days
        )

        statuses.append(
            ClientStatus(
                client_name=client["name"],
                total_phases=len(config.phases),
                phases_complete=phases_complete,
                current_phase=current_phase,
                missing_documents=current_missing,
                last_activity_at=last_activity,
                days_since_activity=days_since,
                is_stale=is_stale,
            )
        )

    return statuses
