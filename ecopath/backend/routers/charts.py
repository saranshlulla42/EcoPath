"""
EcoPath — Chart spec resolution.

Tools that produce a time series register the full series server-side and hand
the model only a compact summary plus a `series_ref`. The model quotes that ref
in its chart block; the browser resolves it here.

The point is that bulk data crosses the model in neither direction: it is not
ingested as a tool result, and the model does not have to echo every point back
into its JSON answer.
"""

import logging

from fastapi import APIRouter, HTTPException

from agent import chart_store

logger = logging.getLogger("ecopath.charts")
router = APIRouter()


@router.get("/{ref}")
async def get_chart(ref: str) -> dict:
    """Resolve a chart ref to its render spec."""
    spec = chart_store.get(ref)
    if spec is None:
        # Expired with its session, or never existed. The frontend degrades to
        # a short notice; the narrative already carries the numbers.
        raise HTTPException(status_code=404, detail="Chart spec not found or expired")
    return spec
