"""
EcoPath Backend — Pydantic Models / Schemas
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── SPECIES ──────────────────────────────────────────────────────────────────

class SpeciesBase(BaseModel):
    gbif_key: int
    common_name: str
    scientific_name: str
    family: Optional[str] = None
    order_name: Optional[str] = None
    iucn_status: Optional[str] = None
    endemic_india: bool = False
    migratory: bool = False
    primary_habitat: list[str] = []
    primary_range: list[str] = []
    description: Optional[str] = None
    fun_fact: Optional[str] = None


class SpeciesResponse(SpeciesBase):
    id: UUID
    image_url: Optional[str] = None
    gbif_image_url: Optional[str] = None
    xeno_canto_id: Optional[str] = None
    ingested_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SpeciesSearchResult(BaseModel):
    id: Optional[UUID] = None
    gbif_key: int
    common_name: str
    scientific_name: str
    family: Optional[str] = None
    iucn_status: Optional[str] = None
    image_url: Optional[str] = None
    gbif_image_url: Optional[str] = None
    endemic_india: bool = False
    migratory: bool = False


class SpeciesDetail(SpeciesResponse):
    population_history: list["PopulationYearSummary"] = []
    anomalies: list["AnomalyResponse"] = []
    migration_routes: list["MigrationRouteResponse"] = []
    xeno_canto_recording: Optional["XenoCantoRecording"] = None


# ─── POPULATION ───────────────────────────────────────────────────────────────

class PopulationYearSummary(BaseModel):
    year: int
    total_observations: int
    states_observed: int
    rolling_avg_5yr: Optional[float] = None


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    count: int
    state: Optional[str] = None
    year: int


class HeatmapResponse(BaseModel):
    species_id: UUID
    year: int
    geojson: dict[str, Any]  # GeoJSON FeatureCollection
    total_points: int
    max_count: int


# ─── ANOMALY ──────────────────────────────────────────────────────────────────

class AnomalyResponse(BaseModel):
    id: UUID
    species_id: UUID
    year: int
    anomaly_type: str  # surge | dip | local_extinction | recolonization
    magnitude_pct: Optional[float] = None
    severity: Optional[str] = None
    affected_state: Optional[str] = None
    observed_count: Optional[int] = None
    expected_count: Optional[int] = None
    rolling_avg_5yr: Optional[float] = None
    causal_hypothesis: Optional[str] = None
    weather_context: Optional[dict[str, Any]] = None
    confidence_score: Optional[float] = None
    detected_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AnomalyDetectionRequest(BaseModel):
    species_id: Optional[UUID] = None  # None = run for all species
    start_year: int = 2020


# ─── MIGRATION ────────────────────────────────────────────────────────────────

class Waypoint(BaseModel):
    lat: float
    lng: float
    month: int
    location_name: str
    description: Optional[str] = None


class MigrationRouteResponse(BaseModel):
    id: UUID
    species_id: UUID
    route_name: str
    flyway: Optional[str] = None
    season: str
    direction: Optional[str] = None
    waypoints: list[Waypoint] = []
    active_months: list[int] = []
    distance_km: Optional[float] = None
    geojson: Optional[dict[str, Any]] = None  # LineString GeoJSON

    class Config:
        from_attributes = True


# ─── VISION ID ────────────────────────────────────────────────────────────────

class VisionIDRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded image data")
    mime_type: str = Field(default="image/jpeg",
                           description="MIME type of the image")


class VisionIDResponse(BaseModel):
    identified: bool
    common_name: Optional[str] = None
    scientific_name: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    is_bird: bool
    is_real_photo: bool  # spoof detection
    spoof_warning: Optional[str] = None
    matched_species: Optional[SpeciesSearchResult] = None
    reasoning: str


# ─── CHAT ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    species_context: Optional[str] = None  # Species name or GBIF key
    year_context: Optional[int] = None


class ChatStreamChunk(BaseModel):
    delta: str
    done: bool = False
    sources: list[str] = []


# ─── EXTINCTION RISK REPORT ─────────────────────────────────────────────────


class ExtinctionRiskReportRequest(BaseModel):
    species_name: str = Field(..., min_length=2,
                              description="Bird common name or scientific name")
    gbif_key: Optional[int] = Field(
        default=None, description="Optional GBIF species key")
    country_code: Optional[str] = Field(
        default=None, description="Optional ISO country code for localized evidence")
    language: Optional[str] = Field(
        default=None, description="Optional language hint for evidence retrieval")


class ReportEvidenceItem(BaseModel):
    query: str
    title: str
    url: str
    snippet: str
    source: Optional[str] = None
    seendate: Optional[str] = None
    language: Optional[str] = None


class SpeciesProfileSummary(BaseModel):
    gbif_key: Optional[int] = None
    common_name: str
    scientific_name: str
    family: Optional[str] = None
    order_name: Optional[str] = None
    iucn_status: Optional[str] = None
    population_trend: Optional[str] = None
    population_size: Optional[str] = None
    habitat: list[str] = []
    range_summary: list[str] = []
    diet: Optional[str] = None
    breeding_behavior: Optional[str] = None
    migratory_behavior: Optional[str] = None
    source_urls: list[str] = []


class ExtinctionRiskReportResponse(BaseModel):
    species: SpeciesProfileSummary
    current_conservation_status: str
    key_threats: list[str]
    survivability_assessment: str
    mitigation_actions: list[str]
    sources: list[ReportEvidenceItem]
    limited_evidence_reasons: list[str] = []
    reviewer_notes: str
    decision_support_draft: str
    model_name: str
    generation_mode: str
    model_output_status: str
    evidence_items_reviewed: int
    disclaimer: str


# ─── XENO-CANTO ───────────────────────────────────────────────────────────────

class XenoCantoRecording(BaseModel):
    id: str
    species: str
    common_name: str
    country: str
    location: Optional[str] = None
    quality: str  # A, B, C, D, E
    duration: Optional[str] = None
    audio_url: str
    sonogram_url: Optional[str] = None
    recordist: Optional[str] = None
    date: Optional[str] = None
