from fastapi import APIRouter, Depends, Request
# A very simple in-memory rate limiter for demo endpoints
import time

router = APIRouter(tags=["Demo Mode"])

_demo_rate_limits = {}

def rate_limit(request: Request):
    """Simple IP-based rate limiting for demo endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Clean up old entries
    for ip in list(_demo_rate_limits.keys()):
        if now - _demo_rate_limits[ip] > 60:
            del _demo_rate_limits[ip]

    if client_ip in _demo_rate_limits and now - _demo_rate_limits[client_ip] < 5:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before toggling demo mode again.")

    _demo_rate_limits[client_ip] = now


@router.post("/api/demo/enable", dependencies=[Depends(rate_limit)])
async def enable_demo_mode():
    """
    Enable demo mode.

    This endpoint is largely symbolic, as demo mode is actually enabled by
    setting the `X-Demo-Mode: true` header on requests. It returns a success
    message and reminds the client to refetch data with the header enabled.
    """
    return {
        "ok": True,
        "mode": "demo",
        "message": "Switched to demo data. Client should refetch with X-Demo-Mode: true header."
    }

@router.post("/api/demo/disable", dependencies=[Depends(rate_limit)])
async def disable_demo_mode():
    """
    Disable demo mode.

    This endpoint is largely symbolic, as demo mode is actually disabled by
    removing or setting the `X-Demo-Mode` header to false on requests. It returns
    a success message and reminds the client to refetch data.
    """
    return {
        "ok": True,
        "mode": "main",
        "message": "Switched to main data. Client should refetch without X-Demo-Mode header."
    }

@router.get("/api/demo/status", dependencies=[Depends(rate_limit)])
async def demo_status():
    """
    Check demo status.
    Can be used by the client or monitoring to verify demo mode readiness.
    """
    # Note: we might want to check if the schema actually exists and is populated,
    # but for now we'll just return true.
    return {
        "ok": True,
        "status": "ready",
        "message": "Demo mode is available."
    }
