"""
EcoPath — Extinction Risk Router

Provides a local decision-support report endpoint for bird species extinction risk.
The endpoint is intentionally framed as a draft for conservation experts, not an
automated verdict.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from models.schemas import ExtinctionRiskReportRequest, ExtinctionRiskReportResponse
from services.extinction_risk_service import generate_extinction_risk_report


logger = logging.getLogger("ecopath.extinction_risk.router")
router = APIRouter()


@router.post("/report", response_model=ExtinctionRiskReportResponse)
async def create_extinction_risk_report(request: ExtinctionRiskReportRequest):
    """
    Generate a reviewer-facing extinction-risk decision-support draft.

    The service uses structured species metadata plus species-scoped threat evidence
    and synthesizes a local report through Ollama.
    """
    logger.info(
        "Received extinction-risk report request for species=%s, gbif_key=%s, country=%s",
        request.species_name, request.gbif_key, request.country_code
    )
    try:
        result = await generate_extinction_risk_report(
            species_name=request.species_name,
            gbif_key=request.gbif_key,
            country_code=request.country_code,
            language=request.language,
        )
        logger.info("Successfully generated report for species=%s", request.species_name)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Failed to generate extinction-risk report for %s: %s", request.species_name, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to generate report: {exc}")
