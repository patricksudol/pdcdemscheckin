import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.onetapcheckin.com"


class OneTapError(Exception):
    pass


def _request(api_key: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    try:
        with urlopen(Request(url, headers={"X-API-Key": api_key}), timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode())
    except HTTPError as error:
        if error.code in {401, 403}:
            raise OneTapError("OneTap rejected the API key") from error
        raise OneTapError(f"OneTap API request failed ({error.code})") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise OneTapError("Could not retrieve data from OneTap") from error


def _all(api_key: str, path: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 0
    while True:
        params = {**(extra or {}), "page": page, "pageSize": 1000}
        data = _request(api_key, path, params).get("data", [])
        if not isinstance(data, list):
            raise OneTapError("OneTap returned an unexpected response")
        items.extend(item for item in data if isinstance(item, dict))
        if len(data) < 1000:
            return items
        page += 1


async def export(
    api_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    lists = await asyncio.to_thread(_all, api_key, "/api/lists")
    profiles = await asyncio.to_thread(_all, api_key, "/api/profiles")
    participants: dict[str, list[dict[str, Any]]] = {}
    for item in lists:
        if list_id := str(item.get("id") or ""):
            participants[list_id] = await asyncio.to_thread(
                _all, api_key, "/api/participants", {"listId": list_id}
            )
    return lists, profiles, participants
