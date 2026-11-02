"""
Evidence sources: GDELT, Google News RSS, IUCN, Wikipedia, Wikidata.

All five lived inside `extinction_risk_service.py` with private caches, private
throttles and twelve separate httpx clients. They are ordinary sources, so they
belong beside the others — the extinction-risk service keeps its analysis and
loses its transport.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import quote_plus

from data.envelope import Result, ok
from data.http import fetch

logger = logging.getLogger("ecopath.data.evidence")

# Google News locale per country, so results match the species' range.
RSS_LOCALES = {
    "IN": ("IN", "IN:en"), "LK": ("LK", "LK:en"), "NP": ("NP", "NP:en"),
    "BD": ("BD", "BD:en"), "PK": ("PK", "PK:en"),
}
DEFAULT_LOCALE = ("US", "US:en")


def _item(query: str, title: str, url: str, snippet: str, source: str,
          seendate: Optional[str] = None) -> dict:
    return {"query": query, "title": title, "url": url, "snippet": snippet or title,
            "source": source, "seendate": seendate, "language": "en"}


# ─── GDELT ───────────────────────────────────────────────────────────────────

async def gdelt(query: str, max_records: int = 6) -> Result:
    """
    News articles from GDELT's document index.

    GDELT rate-limits aggressively; the source spec caps concurrency at 2 and
    the shared layer honours its Retry-After, replacing the bespoke cooldown
    and throttle globals this used to need.
    """
    res = await fetch("gdelt", "search", "", params={
        "query": query, "mode": "ArtList", "format": "json",
        "maxrecords": max_records, "sort": "hybridrel",
    })
    if not res.ok:
        return ok([], "gdelt", "search", degraded=True, note=res.error)

    articles = (res.data or {}).get("articles", []) if isinstance(res.data, dict) else []
    return ok([
        _item(query, a.get("title") or "Untitled article", a.get("url") or "",
              a.get("excerpt") or a.get("title") or "",
              a.get("domain") or "GDELT", a.get("seendate"))
        for a in articles if a.get("url")
    ], "gdelt", "search", cached=res.provenance.cached)


# ─── Google News RSS ─────────────────────────────────────────────────────────

async def news_rss(query: str, max_records: int = 6,
                   country_code: Optional[str] = None) -> Result:
    gl, ceid = RSS_LOCALES.get((country_code or "").upper(), DEFAULT_LOCALE)
    res = await fetch("news", "search",
                      f"https://news.google.com/rss/search?q={quote_plus(query)}"
                      f"&hl=en&gl={gl}&ceid={ceid}",
                      parse="text")
    if not res.ok:
        return ok([], "news", "search", degraded=True, note=res.error)

    try:
        channel = ET.fromstring(res.data).find("channel")
    except ET.ParseError as e:
        return ok([], "news", "search", degraded=True, note=f"malformed RSS: {e}")
    if channel is None:
        return ok([], "news", "search", degraded=True, note="RSS had no channel")

    items = []
    for entry in channel.findall("item")[:max_records]:
        url = (entry.findtext("link") or "").strip()
        if not url:
            continue
        items.append(_item(
            query,
            (entry.findtext("title") or "Untitled article").strip(),
            url,
            re.sub(r"<[^>]+>", "", entry.findtext("description") or "").strip(),
            (entry.findtext("source") or "Google News RSS").strip(),
            (entry.findtext("pubDate") or "").strip() or None,
        ))
    return ok(items, "news", "search", cached=res.provenance.cached)


# ─── IUCN ────────────────────────────────────────────────────────────────────

async def iucn_status(scientific_name: str) -> Result:
    """
    Official IUCN status via the keyed API, falling back to the public site.

    The fallback exists because the API token is optional; when it is missing
    the scrape is the only route, and the result is marked degraded so callers
    can weight it accordingly.
    """
    from data.registry import get_source

    if get_source("iucn").available:
        res = await fetch("iucn", "species", f"species/{quote_plus(scientific_name)}",
                          params={"token": get_source("iucn").key})
        results = (res.data or {}).get("result", []) if res.ok else []
        if results:
            r = results[0]
            return ok({
                "category": r.get("category"),
                "population_trend": r.get("population_trend"),
                "scientific_name": r.get("scientific_name"),
                "source_url": f"https://www.iucnredlist.org/search?query={quote_plus(scientific_name)}",
            }, "iucn", "species", cached=res.provenance.cached)

    return await _iucn_public(scientific_name)


async def _iucn_public(scientific_name: str) -> Result:
    res = await fetch("iucn_public", "search",
                      f"/search?query={quote_plus(scientific_name)}&searchType=species",
                      parse="text")
    if not res.ok:
        return ok({}, "iucn_public", "search", degraded=True, note=res.error)

    flattened = re.sub(r"\s+", " ", res.data or "")
    name = re.escape(scientific_name)
    match = re.search(
        rf"_{name}_.*?\[(?P<category>[a-z]{{2}})\]\((?P<url>https://www\.iucnredlist\.org/species/\d+/\d+)",
        flattened, re.IGNORECASE)
    if not match:
        return ok({}, "iucn_public", "search", degraded=True,
                  note=f"No IUCN entry parsed for {scientific_name}")

    return ok({
        "category": match.group("category").upper(),
        "source_url": match.group("url"),
    }, "iucn_public", "search", cached=res.provenance.cached, degraded=True,
        note="Parsed from the public IUCN site; no API token configured")


# ─── Wikipedia ───────────────────────────────────────────────────────────────

async def wikipedia_summary(scientific_name: str, common_name: str = "") -> Result:
    """Species summary, trying the scientific name then the common name."""
    for candidate in [c for c in (scientific_name, common_name) if c]:
        slug = candidate.replace(" ", "_")
        res = await fetch("wikipedia", "summary", f"page/summary/{quote_plus(slug)}")
        if res.ok and (res.data or {}).get("extract"):
            d = res.data
            return ok({
                "title": d.get("title"),
                "extract": d.get("extract"),
                "thumbnail": (d.get("thumbnail") or {}).get("source"),
                "url": (d.get("content_urls", {}).get("desktop", {}).get("page")
                        or f"https://en.wikipedia.org/wiki/{slug}"),
            }, "wikipedia", "summary", cached=res.provenance.cached)
    return ok({}, "wikipedia", "summary", degraded=True,
              note=f"No Wikipedia page found for {scientific_name or common_name}")


# ─── Wikidata ────────────────────────────────────────────────────────────────

IUCN_QID_TO_CODE = {
    "Q211005": "LC", "Q719675": "NT", "Q278113": "VU",
    "Q11394": "EN", "Q219127": "CR", "Q239509": "EW", "Q237350": "EX",
}


async def wikidata_iucn(scientific_name: str) -> Result:
    """IUCN status via SPARQL — the last resort when the API and scrape fail."""
    sparql = f"""
    SELECT ?species ?statusLabel WHERE {{
      ?species wdt:P225 "{scientific_name}" ; wdt:P141 ?status .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }} LIMIT 1
    """
    res = await fetch("wikidata", "iucn", "sparql",
                      params={"query": sparql, "format": "json"})
    if not res.ok:
        return ok({}, "wikidata", "iucn", degraded=True, note=res.error)

    bindings = (res.data or {}).get("results", {}).get("bindings", [])
    if not bindings:
        return ok({}, "wikidata", "iucn", degraded=True,
                  note=f"No Wikidata IUCN statement for {scientific_name}")

    row = bindings[0]
    uri = row.get("species", {}).get("value")
    label = row.get("statusLabel", {}).get("value", "")
    qid = uri.rsplit("/", 1)[-1] if uri else ""
    return ok({
        "category": IUCN_QID_TO_CODE.get(qid) or _label_to_code(label),
        "label": label,
        "source_url": uri or "https://www.wikidata.org",
    }, "wikidata", "iucn", cached=res.provenance.cached, degraded=True,
        note="Derived from Wikidata rather than IUCN directly")


def _label_to_code(label: str) -> Optional[str]:
    mapping = {
        "least concern": "LC", "near threatened": "NT", "vulnerable": "VU",
        "endangered": "EN", "critically endangered": "CR",
        "extinct in the wild": "EW", "extinct": "EX", "data deficient": "DD",
    }
    return mapping.get(label.strip().lower())
