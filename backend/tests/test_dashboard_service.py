from datetime import datetime, timedelta, timezone

from app.core.phase_config import Phase, PhaseConfig
from app.services.dashboard_service import list_client_statuses

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
        Phase(name="Requirement Analysis", sequence=2, required_documents=("BRD",)),
    ]
)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_client_with_no_documents_is_blocked_at_first_phase(rest):
    rest.insert("clients", {"name": "Acme", "created_at": _iso(datetime.now(timezone.utc))})

    [status] = list_client_statuses(rest, CONFIG)

    assert status.client_name == "Acme"
    assert status.phases_complete == 0
    assert status.current_phase == "Pre-requisites"
    assert set(status.missing_documents) == {"MSA", "SOW"}


def test_client_with_all_phases_complete_has_no_current_phase(rest):
    client = rest.insert("clients", {"name": "Acme", "created_at": _iso(datetime.now(timezone.utc))})
    now = datetime.now(timezone.utc)
    for doc_type in ("MSA", "SOW", "BRD"):
        rest.insert(
            "client_documents",
            {"client_id": client["id"], "doc_type": doc_type, "uploaded_at": _iso(now)},
        )

    [status] = list_client_statuses(rest, CONFIG)

    assert status.phases_complete == 2
    assert status.current_phase is None
    assert status.missing_documents == ()


def test_recent_activity_is_not_stale(rest):
    client = rest.insert("clients", {"name": "Acme", "created_at": _iso(datetime.now(timezone.utc))})
    rest.insert(
        "client_documents",
        {"client_id": client["id"], "doc_type": "MSA", "uploaded_at": _iso(datetime.now(timezone.utc))},
    )

    [status] = list_client_statuses(rest, CONFIG)

    assert status.is_stale is False


def test_old_activity_on_incomplete_client_is_stale(rest):
    old = datetime.now(timezone.utc) - timedelta(days=10)
    client = rest.insert("clients", {"name": "Acme", "created_at": _iso(old)})
    rest.insert("client_documents", {"client_id": client["id"], "doc_type": "MSA", "uploaded_at": _iso(old)})

    [status] = list_client_statuses(rest, CONFIG)

    assert status.current_phase == "Pre-requisites"  # SOW still missing
    assert status.is_stale is True
    assert status.days_since_activity > 3


def test_old_activity_on_complete_client_is_not_stale(rest):
    # A client that finished everything a while ago isn't "stuck" — staleness
    # only makes sense for clients still mid-phase.
    old = datetime.now(timezone.utc) - timedelta(days=10)
    client = rest.insert("clients", {"name": "Acme", "created_at": _iso(old)})
    for doc_type in ("MSA", "SOW", "BRD"):
        rest.insert("client_documents", {"client_id": client["id"], "doc_type": doc_type, "uploaded_at": _iso(old)})

    [status] = list_client_statuses(rest, CONFIG)

    assert status.current_phase is None
    assert status.is_stale is False


def test_soft_deleted_client_does_not_appear_on_dashboard(rest):
    rest.insert("clients", {"name": "Acme", "created_at": _iso(datetime.now(timezone.utc)), "deleted_at": _iso(datetime.now(timezone.utc))})

    assert list_client_statuses(rest, CONFIG) == []
