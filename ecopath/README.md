# 🦜 EcoPath — Diagnostic Ecological Intelligence Dashboard

> A research-grade dashboard for Indian bird biodiversity that doesn't just show *what* happened to a population — it explains *why*.

## Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 14 (App Router, TypeScript), Tailwind CSS, shadcn/ui |
| **Maps** | MapLibre GL JS (react-map-gl), OpenFreeMap tiles |
| **Backend** | FastAPI (Python 3.11+) |
| **Database** | Supabase (PostgreSQL 15 + PostGIS 3.4) |
| **Intelligence** | Gemini 1.5 Pro (Reasoning), Gemini 1.5 Flash (Vision ID) |
| **Data Sources** | GBIF API, Open-Meteo, xeno-canto (bird calls) |

## Project Structure

```
ecopath/
├── frontend/          # Next.js 14 application
├── backend/           # FastAPI application
├── database/          # SQL migration scripts (run in Supabase SQL editor)
└── scripts/           # Utility scripts
```

## Quick Start

### 1. Database
Run SQL files in order in the Supabase SQL editor:
```
database/01_extensions.sql
database/02_schema.sql
database/03_seed_species.sql
database/04_functions.sql
database/05_migration_seed.sql
```

### 2. Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your secrets
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local  # fill in NEXT_PUBLIC_ vars
npm run dev
```

The app will be available at http://localhost:3000 and the API at http://localhost:8000.

## Features
- 🔍 **Dual-Mode ID** — Text autocomplete or image upload (Gemini Vision)
- 🗺️ **Analytical Maps** — 10-year population heatmaps with temporal slider
- 🦅 **Migration Corridors** — Animated LineString routes (2015–2024)
- 🧠 **Forensic Engine** — ±25% anomaly detection vs. 5-year rolling average
- 💬 **Causal Reasoning Agent** — RAG chatbot powered by Gemini 1.5 Pro
- 🎵 **Bird Calls** — Real xeno-canto recordings per species
