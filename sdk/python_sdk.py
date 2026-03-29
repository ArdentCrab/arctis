"""Auto-generated SDK stub."""

import requests

SDK_TITLE = 'Arctis'
def get_health(base_url: str, api_key: str) -> dict:
    r = requests.get(f"{base_url}/health", headers={"X-API-Key": api_key})
    r.raise_for_status()
    return r.json()
