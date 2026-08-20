from fastapi import APIRouter, Depends

from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.deps import get_config, get_rest_client
from app.services.dashboard_service import list_client_statuses

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/clients/status")
def clients_status(
    rest: SupabaseRestClient = Depends(get_rest_client),
    config: PhaseConfig = Depends(get_config),
):
    statuses = list_client_statuses(rest, config)
    return {
        "clients": [
            {
                "client_name": s.client_name,
                "total_phases": s.total_phases,
                "phases_complete": s.phases_complete,
                "current_phase": s.current_phase,
                "missing_documents": list(s.missing_documents),
                "last_activity_at": s.last_activity_at.isoformat()
                if s.last_activity_at
                else None,
                "days_since_activity": (
                    round(s.days_since_activity, 1)
                    if s.days_since_activity is not None
                    else None
                ),
                "is_stale": s.is_stale,
            }
            for s in statuses
        ]
    }
