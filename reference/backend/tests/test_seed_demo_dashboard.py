from app.core.phase_config import get_phase_config
from app.db.seed_demo_dashboard import seed_demo_dashboard
from app.services.dashboard_service import list_client_statuses


def test_seed_produces_a_stale_client_stuck_on_requirement_analysis(rest):
    seed_demo_dashboard(rest, "Globex Industries", days_stale=5)

    [status] = list_client_statuses(rest, get_phase_config())

    assert status.client_name == "Globex Industries"
    assert status.current_phase == "Requirement Analysis"
    assert status.phases_complete == 1  # Pre-requisites done
    assert status.is_stale is True
    assert status.days_since_activity > 3


def test_seed_is_idempotent_and_refreshes_timestamps(rest):
    seed_demo_dashboard(rest, "Globex Industries", days_stale=5)
    seed_demo_dashboard(rest, "Globex Industries", days_stale=1)  # re-run, fresher

    clients = rest.select("clients")
    assert len(clients) == 1  # no duplicate client row

    [status] = list_client_statuses(rest, get_phase_config())
    assert status.is_stale is False  # 1 day ago is under the 3-day threshold now
