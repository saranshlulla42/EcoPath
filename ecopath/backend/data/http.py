"""
One HTTP path for every external source.

Previously each caller built its own `httpx.AsyncClient` — 17 of them, with
eight different timeouts, retry on only two, and no rate limiting. A slow or
rate-limited upstream therefore behaved differently depending on which feature
you entered through. Everything now goes through `fetch`, which applies the
source's declared policy: connection reuse, bounded concurrency, retry with
backoff, 429 handling, and caching.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional

import httpx

from data.cache import cache, make_key
from data.envelope import Result, failed, ok
from data.registry import SourceSpec, get_source

logger = logging.getLogger("ecopath.data.http")

_clients: dict[str, httpx.AsyncClient] = {}
_limiters: dict[str, asyncio.Semaphore] = {}
_lock = asyncio.Lock()


async def _client_for(spec: SourceSpec) -> httpx.AsyncClient:
    """One pooled client per source, created once and reused."""
    client = _clients.get(spec.id)
    if client is not None and not client.is_closed:
        return client
    async with _lock:
        client = _clients.get(spec.id)
        if client is None or client.is_closed:
            _clients[spec.id] = httpx.AsyncClient(
                timeout=spec.timeout,
                follow_redirects=True,
                headers=spec.headers or {},
                limits=httpx.Limits(
                    max_connections=spec.concurrency * 2,
                    max_keepalive_connections=spec.concurrency,
                ),
            )
        return _clients[spec.id]


def _limiter_for(spec: SourceSpec) -> asyncio.Semaphore:
    sem = _limiters.get(spec.id)
    if sem is None:
        sem = asyncio.Semaphore(spec.concurrency)
        _limiters[spec.id] = sem
    return sem


async def aclose_all() -> None:
    """Close every pooled client. Called on application shutdown."""
    for client in _clients.values():
        if not client.is_closed:
            await client.aclose()
    _clients.clear()


async def fetch(
    source_id: str,
    operation: str,
    path: str = "",
    *,
    params: Optional[dict] = None,
    method: str = "GET",
    json_body: Optional[dict] = None,
    headers: Optional[dict] = None,
    ttl: Optional[float] = None,
    parse: str = "json",
    use_cache: bool = True,
) -> Result:
    """
    Fetch from a registered source and return a `Result` carrying provenance.

    `path` is appended to the source's base URL; pass "" to hit the base URL
    directly, or an absolute http(s) URL to bypass the base. `parse` is "json",
    "text" or "bytes".
    """
    spec = get_source(source_id)
    params = params or {}

    if not spec.available:
        return failed(spec.id, operation,
                      f"{spec.label} is not configured (missing API key)")

    # An absolute path escapes the base URL — some sources expose endpoints
    # (xeno-canto's download route) outside their API prefix.
    if path.startswith(("http://", "https://")):
        url = path
    elif path:
        url = f"{spec.base_url.rstrip('/')}/{path.lstrip('/')}"
    else:
        url = spec.base_url
    cache_ttl = spec.default_ttl if ttl is None else ttl
    key = make_key(spec.id, operation, {"url": url, "params": params, "body": json_body})

    if use_cache and method == "GET" and cache_ttl > 0:
        hit = cache.get(key)
        if hit is not None:
            return ok(hit, spec.id, operation, cached=True, upstream_url=url, params=params)

    client = await _client_for(spec)
    limiter = _limiter_for(spec)
    last_error = "unknown error"

    for attempt in range(1, spec.max_attempts + 1):
        try:
            async with limiter:
                resp = await client.request(
                    method, url, params=params or None,
                    json=json_body, headers=headers,
                )

            # 429 carries its own backoff hint; honour it rather than guessing.
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 0) or _backoff(attempt))
                last_error = f"{spec.label} rate limited (429)"
                if attempt < spec.max_attempts:
                    logger.warning(f"{spec.label} 429 on {operation}; waiting {wait:.1f}s")
                    await asyncio.sleep(min(wait, 30.0))
                    continue

            # 4xx other than 429 will not improve on retry.
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                return failed(spec.id, operation,
                              f"{spec.label} returned {resp.status_code}",
                              upstream_url=url, params=params)

            resp.raise_for_status()
            payload = _parse(resp, parse)

            if use_cache and method == "GET" and cache_ttl > 0:
                cache.set(key, payload, cache_ttl)
            return ok(payload, spec.id, operation, upstream_url=url, params=params)

        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_error = f"{spec.label} {type(e).__name__}: {e}"
        except httpx.HTTPStatusError as e:
            last_error = f"{spec.label} HTTP {e.response.status_code}"
        except Exception as e:  # parsing and anything unforeseen
            last_error = f"{spec.label} {type(e).__name__}: {e}"

        if attempt < spec.max_attempts:
            await asyncio.sleep(_backoff(attempt))

    logger.warning(f"{spec.label}/{operation} failed after {spec.max_attempts} attempts: {last_error}")
    return failed(spec.id, operation, last_error, upstream_url=url, params=params)


def _parse(resp: httpx.Response, mode: str) -> Any:
    if mode == "json":
        return resp.json()
    if mode == "text":
        return resp.text
    if mode == "bytes":
        return resp.content
    raise ValueError(f"Unknown parse mode {mode!r}")


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter, so retries do not synchronise."""
    return min(2.0 ** attempt, 20.0) * (0.5 + random.random() / 2)
