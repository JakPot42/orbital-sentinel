# Orbital Sentinel — Space Domain Awareness Brief Generator

Live space domain awareness tool — pulls real conjunction data from the 18th Space Defense Squadron, propagates orbital trajectories with sgp4, flags close approach events by collision probability, and generates plain-language SDA briefs.

Built for space operations analysts and defense contractors who need a fast read on what's at risk in the next 72 hours without digging through raw CDM files.

**Live demo:** https://orbital-sentinel-65cj.onrender.com

---

## What It Does

The 18th Space Defense Squadron (18th SDS) publishes Conjunction Data Messages (CDMs) for thousands of close approach events daily — all unclassified, all free. The data exists; the hard part is making it readable. Orbital Sentinel automates that workflow:

1. **Ingest** — pulls live CDMs from Space-Track.org (18th SDS `cdm_public` class) using authenticated API
2. **Propagate** — sgp4 library computes current positions from Two-Line Element (TLE) sets for each object pair
3. **Score** — probability of collision (Pc) computed from covariance data; miss distance extracted from CDM
4. **Rank** — conjunctions sorted by risk tier: CRITICAL (Pc ≥ 10⁻⁴), HIGH (Pc ≥ 10⁻⁵), MEDIUM, LOW
5. **Visualize** — interactive 3D Plotly orbital geometry plot showing approach geometry for each event
6. **Brief** — Claude writes a plain-language SDA executive brief covering the highest-risk conjunctions

---

## Live Verification (June 17, 2026)

Pulled 50 real conjunctions from Space-Track. Top result:

> **FENGYUN 1C DEB × SL-16 DEB** — CRITICAL  
> Pc = 1.6 × 10⁻³ | Miss distance: 8 m  
> (FENGYUN 1C debris field from 2007 ASAT test; SL-16 Russian rocket body)

This is publicly reported data. The tool surfaces it with context, not raw numbers.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python |
| Orbital mechanics | sgp4 (TLE propagation) |
| Live data | Space-Track.org CDM API (`cdm_public` class, authenticated) |
| TLE source | Celestrak API (free, no auth) |
| AI | Claude Haiku (SDA executive brief) |
| 3D visualization | Plotly (interactive orbital geometry) |
| PDF export | ReportLab (DEMO watermark) |
| Database | SQLite + SQLAlchemy 2.0 |
| Frontend | Jinja2 templates + vanilla CSS |
| Deploy | Render (DEMO_MODE=False — live CDM data) |

---

## Quick Start

```bash
git clone https://github.com/JakPot42/orbital-sentinel.git
cd orbital-sentinel
cp .env.example .env
# Add to .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   SPACETRACK_USER=your@email.com
#   SPACETRACK_PASS=yourpassword
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\uvicorn main:app --reload
```

Open http://localhost:8000

Space-Track accounts are free at space-track.org. Accept the user agreement — CDM data is unclassified and publicly available.

---

## Architecture

```
spacetrack_client.py   Space-Track.org authentication + CDM query (cdm_public class)
sgp4_propagator.py     TLE parsing, sgp4 position propagation, miss distance geometry
risk_engine.py         Pc threshold classification (CRITICAL / HIGH / MEDIUM / LOW)
visualization.py       Plotly 3D orbital geometry (approach vectors, perigee, conjunction point)
claude_analyst.py      Claude Haiku: CDM data → plain-language SDA executive brief
pdf_export.py          ReportLab PDF export with DEMO watermark
seed_data.py           5 pre-baked demo conjunctions for DEMO_MODE=True runs
models.py              SQLAlchemy ORM (ConjunctionEvent, SDABrief)
main.py                FastAPI routes, Jinja rendering, lifespan seed
```

---

## Key Architecture Decisions

**Why CDMs, not just TLE-based proximity detection:**
TLE-based close approach detection requires propagating thousands of objects against each other — computationally expensive and duplicating work the 18th SDS already does. CDMs are the 18th SDS's pre-computed conjunction assessments; using them directly is both more efficient and more operationally realistic.

**Why sgp4 for propagation:**
sgp4 is the standard for unclassified orbital propagation. The library handles the math; the domain work is understanding what the inputs mean (TLE epoch, B* drag term, mean motion derivatives) and what the outputs represent (ECI coordinates, validity windows).

**Why the SDA framing, not ASAT:**
"Which satellites are at risk of close approach in the next 72 hours" is published by the 18th SDS. "How to intercept a satellite" is not. Same orbital mechanics core, completely different defensibility.

---

## Honest Limitations

- Pc computation depends on covariance quality in the CDM — 18th SDS covariances are good for screened conjunctions but have known limitations for newly tracked objects.
- sgp4 propagation degrades beyond a few days from the TLE epoch; this tool is designed for the 72-hour window where CDMs are most relevant.
- Plain-language briefs are for situational awareness only — no operational tasking or collision avoidance maneuver planning.
- Render's free tier spins down after 15 minutes of inactivity; first request after spin-down takes ~30 seconds.

---

## API Keys Required

| Key | Source | Cost |
|-----|--------|------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | ~$0.01/brief (Haiku) |
| `SPACETRACK_USER` / `SPACETRACK_PASS` | space-track.org (free account) | Free |

---

## Tests

```bash
venv\Scripts\python.exe -m pytest tests/ -v
# 148 passed
```

Covers: CDM parsing, sgp4 propagation math, risk tier classification, Pc threshold boundaries, brief parsing, PDF export structure, seed data load.

---

*DEMONSTRATION ONLY — conjunction data is unclassified public information from Space-Track.org. Not for operational space traffic management use.*
