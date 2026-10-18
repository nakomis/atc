"""Minimal HTTP client for ATC's own API, over Leia's mTLS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

DEFAULT_URL = "https://atc.plane.home.nakomis.com"
DEFAULT_CERT = Path("~/.config/nakomis/client.crt").expanduser()
DEFAULT_KEY = Path("~/.config/nakomis/client.key").expanduser()


class AtcHttp:
    def __init__(
        self,
        url: str = DEFAULT_URL,
        cert: Path = DEFAULT_CERT,
        key: Path = DEFAULT_KEY,
        transport: httpx.BaseTransport | None = None,
    ):
        kwargs: dict[str, Any] = {"base_url": url, "timeout": 60.0}
        if transport is not None:
            kwargs["transport"] = transport
        else:
            kwargs["cert"] = (str(cert), str(key))
        self._http = httpx.Client(**kwargs)

    def get(self, path: str, **params: Any) -> Any:
        r = self._http.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    def get_status(self, path: str) -> tuple[int, Any]:
        """GET returning (status, json) without raising, so callers can handle 404."""
        r = self._http.get(path)
        try:
            data = r.json()
        except ValueError:
            data = r.text
        return r.status_code, data

    def put(self, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        """Return (status, json) without raising, so callers can handle 409."""
        r = self._http.put(path, json=body)
        try:
            data = r.json()
        except ValueError:
            data = r.text
        return r.status_code, data
