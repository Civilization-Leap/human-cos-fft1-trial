"""Small stdlib HTTP transport shared by S2-L provider adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from http.client import IncompleteRead
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from human_cos.models.errors import ModelAdapterError
from human_cos.models.types import AdapterErrorCode, ModelIdentity


class HeaderLike(Protocol):
    def get(self, name: str, default: str | None = None) -> str | None: ...


class HttpResponseLike(Protocol):
    headers: HeaderLike

    def read(self) -> bytes: ...

    def close(self) -> None: ...


class HttpOpener(Protocol):
    def __call__(self, request: Request, timeout: float) -> HttpResponseLike: ...


def _default_opener(request: Request, timeout: float) -> HttpResponseLike:
    return cast(HttpResponseLike, urlopen(request, timeout=timeout))


def _error_code(http_status: int, body: str) -> tuple[AdapterErrorCode, bool]:
    lowered = body.lower()
    if http_status in {401, 403}:
        return AdapterErrorCode.AUTHENTICATION, False
    if http_status == 429:
        return AdapterErrorCode.RATE_LIMIT, True
    if "content" in lowered and ("filter" in lowered or "safety" in lowered):
        return AdapterErrorCode.CONTENT_FILTER, False
    if 500 <= http_status <= 599:
        return AdapterErrorCode.PROVIDER_UNAVAILABLE, True
    return AdapterErrorCode.INVALID_RESPONSE, False


def request_json(
    *,
    identity: ModelIdentity,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    timeout: float,
    opener: HttpOpener | None,
) -> tuple[dict[str, Any], str | None]:
    encoded = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
    request = Request(url, data=encoded, headers=dict(headers), method="POST")
    active_opener = opener or _default_opener
    response: HttpResponseLike | None = None
    try:
        response = active_opener(request, timeout)
        raw = response.read()
        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        code, retryable = _error_code(exc.code, body)
        raise ModelAdapterError(
            code,
            identity,
            f"{identity.provider} returned HTTP {exc.code}",
            retryable=retryable,
        ) from exc
    except TimeoutError as exc:
        raise ModelAdapterError(
            AdapterErrorCode.TIMEOUT,
            identity,
            f"{identity.provider} request timed out",
            retryable=True,
        ) from exc
    except (IncompleteRead, ConnectionResetError) as exc:
        raise ModelAdapterError(
            AdapterErrorCode.PROVIDER_UNAVAILABLE,
            identity,
            f"{identity.provider} response body was interrupted",
            retryable=True,
        ) from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            code = AdapterErrorCode.TIMEOUT
            message = f"{identity.provider} request timed out"
        else:
            code = AdapterErrorCode.PROVIDER_UNAVAILABLE
            message = f"{identity.provider} transport unavailable"
        raise ModelAdapterError(code, identity, message, retryable=True) from exc
    finally:
        if response is not None:
            response.close()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelAdapterError(
            AdapterErrorCode.INVALID_RESPONSE,
            identity,
            f"{identity.provider} returned invalid JSON",
            retryable=False,
        ) from exc
    if not isinstance(parsed, dict):
        raise ModelAdapterError(
            AdapterErrorCode.INVALID_RESPONSE,
            identity,
            f"{identity.provider} returned a non-object JSON response",
            retryable=False,
        )
    return cast(dict[str, Any], parsed), request_id
