import base64
import time

import httpx


async def claim_access_url(setup_token: str) -> str:
    """Exchange a one-time setup token for a permanent SimpleFIN access URL."""
    try:
        claim_url = base64.b64decode(setup_token.strip()).decode()
    except Exception as exc:
        raise ValueError("Invalid setup token: could not base64-decode") from exc

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(claim_url, content=b"")
    except httpx.RequestError as exc:
        raise ValueError(f"Could not reach SimpleFIN to claim token: {exc}") from exc

    if response.status_code != 200:
        raise ValueError(
            f"Failed to claim token: {response.status_code} from SimpleFIN"
        )
    return response.text.strip()


async def fetch_simplefin_data(access_url: str) -> dict:
    """GET /accounts from the SimpleFIN bridge for the last 30 days."""
    start_date = int(time.time()) - (30 * 24 * 3600)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{access_url}/accounts",
                params={"start-date": str(start_date)},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"SimpleFIN returned an error: {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Could not reach SimpleFIN bridge: {exc}") from exc
