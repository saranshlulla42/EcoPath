# Goal: Live GBIF Data Fetching

We will transition the EcoPath dashboard from a "local ingest-first" model to a "live-fetch" model. This means that instead of restricting the detail view only to birds imported into the local Supabase PostgreSQL database, we will dynamically fetch data from GBIF and calculate analytics directly in the user’s browser.

## User Review Required

> [!CAUTION]
> The original setup relied on pre-computed PostgreSQL background tasks to identify statistical anomalies across 10 years and fetch precise Map points. Removing the local database means: 
> 1. We'll be constrained to GBIF’s immediate API limits limit (fetch only up to 300 records dynamically per species).
> 2. The heatmap will only show a snapshot of occurrences.
> 3. Your Xeno-Canto recordings and custom backend-generated descriptions will be temporarily bypassed unless we re-introduce a backend proxy.

If you are okay with shifting entirely to a stateless frontend for the species detail dashboard, please approve the plan below!

## Proposed Changes

---

### Frontend

#### [MODIFY] [page.tsx](file:///home/saranshlulla/Documents/Capstone/ecopath/frontend/app/page.tsx)
- The search functionality will rely on `s.gbif_key` to navigate to `/species/[gbif_key]`, completely stripping out the local DB `s.id` ingestion alerts.

#### [MODIFY] [species/[id]/page.tsx](file:///home/saranshlulla/Documents/Capstone/ecopath/frontend/app/species/[id]/page.tsx)
- Re-architect API fetching to ignore the local FastApi server wrapper.
- Use `fetch` on `https://api.gbif.org/v1/species/{usageKey}` to get species classification.
- Use `fetch` on `https://api.gbif.org/v1/occurrence/search?taxonKey={usageKey}&country=IN&limit=300` to stream real-time occurrences.
- Map the immediate occurrence JSON output to group counts by year locally to recreate the `<AreaChart>` and local anomaly functionality (`computeClientAnomalies`).

### Backend

#### [MODIFY] [species.py](file:///home/saranshlulla/Documents/Capstone/ecopath/backend/routers/species.py)
- Change `/search` to natively return the `gbif_key` on the search results natively, alongside the `common_name` and `image_url` proxy responses so the frontend can properly route immediately.

## Open Questions

> [!WARNING]
> Do you want to preserve the AI-generated `Ask EcoPath (Chat)` interface and Map functionalities on the backend? Those routers currently use the `Species UUID` to query the database contexts. Switching the IDs strictly to `gbif_key` will impact their RAG context retrieval.

## Verification Plan

### Automated Tests
- Run search queries for non-seeded birds, verify the immediate link execution to the detail page.
- Evaluate the Network Tab to assure we directly ping `api.gbif.org` as opposed to `localhost:8001`.
