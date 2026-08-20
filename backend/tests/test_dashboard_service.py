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


def test_list_client_statuses_uses_constant_round_trips(rest):
    # Regression guard for the F2 N+1: before this fix, the dashboard fired
    # 1 + N REST calls (one for the clients list, then one per client for its
    # documents). At 50 clients + 200 docs that meant 51 sequential HTTP
    # round-trips — dominant latency on the dashboard load. This test pins
    # the shape at 2 round-trips regardless of N: one select_active for
    # clients, one select_in for all their documents.
    now = datetime.now(timezone.utc)
    doc_types = ("MSA", "SOW", "BRD", "TRD")
    for i in range(50):
        client = rest.insert("clients", {"name": f"Client-{i}", "created_at": _iso(now)})
        for doc_type in doc_types:
            rest.insert(
                "client_documents",
                {"client_id": client["id"], "doc_type": doc_type, "uploaded_at": _iso(now)},
            )

    rest.call_counts.clear()  # ignore inserts above; measure only the read path
    statuses = list_client_statuses(rest, CONFIG)

    assert len(statuses) == 50
    # Plain per-client rest.select() must not be used — that was the N+1 shape.
    assert rest.call_counts.get("select", 0) == 0
    # One clients-fetch and one batch documents-fetch, regardless of N.
    assert rest.call_counts.get("select_active", 0) == 1
    assert rest.call_counts.get("select_in", 0) == 1


def test_list_client_statuses_returns_empty_without_hitting_documents(rest):
    # No clients means no documents fetch is needed at all — this both
    # preserves behavior (empty list) and avoids a pointless round-trip.
    rest.call_counts.clear()
    assert list_client_statuses(rest, CONFIG) == []
    assert rest.call_counts.get("select_in", 0) == 0


def test_list_client_statuses_still_filters_soft_deleted_documents(rest):
    # select_in doesn't apply a deleted_at filter server-side, so the service
    # is expected to drop soft-deleted docs in Python. Guard that here.
    client = rest.insert("clients", {"name": "Acme", "created_at": _iso(datetime.now(timezone.utc))})
    now = datetime.now(timezone.utc)
    rest.insert(
        "client_documents",
        {"client_id": client["id"], "doc_type": "MSA", "uploaded_at": _iso(now)},
    )
    rest.insert(
        "client_documents",
        {"client_id": client["id"], "doc_type": "SOW", "uploaded_at": _iso(now), "deleted_at": _iso(now)},
    )

    [status] = list_client_statuses(rest, CONFIG)

    # SOW was soft-deleted, so Pre-requisites remains incomplete.
    assert status.current_phase == "Pre-requisites"
    assert "SOW" in status.missing_documents
