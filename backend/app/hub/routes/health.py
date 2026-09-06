"""Health endpoint."""
from fastapi import APIRouter

from app.hub import __version__
from app.hub.adapters.registry import registry
from app.hub.runtime import get_runtime
from app.hub.schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness + registered adapters."""
    runtime = get_runtime()
    return HealthOut(status="ok", version=__version__, adapters=registry.ids(), sia_receiver="sia" in runtime.services)
