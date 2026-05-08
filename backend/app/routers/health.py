"""Service-health endpoints driving the LED strip in the KB Monitor.

The HealthMonitor (see app.services.health_monitor) probes services on
a 30s cadence and pushes state changes via Socket.IO. These endpoints
support: (a) initial fetch on first paint, (b) manual force-refresh
when the user clicks the LED strip's refresh button.
"""

from fastapi import APIRouter, HTTPException

from app.services.health_monitor import get_monitor

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/services")
async def get_services_health() -> dict:
    """Return the current cached service-health snapshot. Cheap, non-
    blocking — does NOT trigger a probe. Use /services/refresh to
    force one."""
    monitor = get_monitor()
    if monitor is None:
        raise HTTPException(
            status_code=503,
            detail="HealthMonitor not yet started",
        )
    return monitor.get_state()


@router.post("/services/refresh")
async def refresh_services_health() -> dict:
    """Trigger an immediate probe cycle and return the resulting state.
    Bounded by the probe timeouts; typically returns within a few
    seconds. Used by the LED strip's manual refresh button."""
    monitor = get_monitor()
    if monitor is None:
        raise HTTPException(
            status_code=503,
            detail="HealthMonitor not yet started",
        )
    return await monitor.force_refresh()
