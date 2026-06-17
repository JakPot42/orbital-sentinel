from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import DEMO_MODE
from database import init_db, get_db
from models import Conjunction
from seed_data import load_seed_data
from risk_engine import categorize_pc, compute_risk_score, format_pc, risk_css_class, object_type_label
from visualization import build_orbital_figure_for_conjunction
from claude_analyst import generate_sda_brief, brief_to_json, brief_from_json, BriefGenerationError
from pdf_export import generate_pdf
from sgp4_propagator import generate_orbital_track


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with get_db() as db:
        load_seed_data(db)
    yield


app = FastAPI(title="Orbital Sentinel", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

templates.env.filters["format_pc"] = format_pc
templates.env.filters["risk_css"] = risk_css_class
templates.env.filters["obj_type"] = object_type_label
templates.env.filters["fromjson"] = brief_from_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tca_hours_from_now(tca: datetime) -> float:
    now = datetime.now(timezone.utc)
    if tca.tzinfo is None:
        tca = tca.replace(tzinfo=timezone.utc)
    return (tca - now).total_seconds() / 3600


def _ingest_cdms(db) -> tuple[int, int]:
    """Fetch live CDMs from Space-Track and upsert to DB. Returns (added, skipped)."""
    from spacetrack_client import fetch_and_parse_cdms, SpaceTrackError

    cdms = fetch_and_parse_cdms()
    added = skipped = 0

    for c in cdms:
        existing = db.query(Conjunction).filter(Conjunction.cdm_id == c["cdm_id"]).first()
        if existing:
            skipped += 1
            continue

        level = categorize_pc(c["pc"], c["miss_distance_km"])
        score = compute_risk_score(c["pc"], c["miss_distance_km"], c["relative_speed_km_s"])

        conj = Conjunction(
            cdm_id=c["cdm_id"],
            sat1_norad=c["sat1_norad"], sat1_name=c["sat1_name"],
            sat1_type=c["sat1_type"],
            sat1_tle1=c["sat1_tle1"], sat1_tle2=c["sat1_tle2"],
            sat2_norad=c["sat2_norad"], sat2_name=c["sat2_name"],
            sat2_type=c["sat2_type"],
            sat2_tle1=c["sat2_tle1"], sat2_tle2=c["sat2_tle2"],
            tca=c["tca"],
            miss_distance_km=c["miss_distance_km"],
            relative_speed_km_s=c["relative_speed_km_s"],
            pc=c["pc"],
            risk_level=level,
            risk_score=score,
            is_demo=False,
        )
        db.add(conj)
        added += 1

    db.commit()
    return added, skipped


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with get_db() as db:
        conjunctions = (
            db.query(Conjunction)
            .order_by(Conjunction.risk_score.desc(), Conjunction.tca.asc())
            .all()
        )
    conj_with_hours = [
        (c, round(_tca_hours_from_now(c.tca), 1))
        for c in conjunctions
    ]
    return templates.TemplateResponse(request, "index.html", {
        "conjunctions": conj_with_hours,
        "demo_mode": DEMO_MODE,
        "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(conjunctions),
        "high_count": sum(1 for c in conjunctions if c.risk_level in ("HIGH", "CRITICAL")),
    })


@app.get("/conjunction/{cdm_id}", response_class=HTMLResponse)
async def conjunction_detail(request: Request, cdm_id: str):
    with get_db() as db:
        conj = db.query(Conjunction).filter(Conjunction.cdm_id == cdm_id).first()
        if not conj:
            raise HTTPException(status_code=404, detail="Conjunction not found")

        # Generate (or retrieve cached) orbital plot
        if not conj.orbital_plot_json:
            plot_json = build_orbital_figure_for_conjunction(conj)
            conj.orbital_plot_json = plot_json
            db.commit()

        # Compute orbital altitudes for display
        now = datetime.now(timezone.utc)
        track1 = generate_orbital_track(conj.sat1_tle1, conj.sat1_tle2, now, n_points=50, n_periods=1)
        track2 = generate_orbital_track(conj.sat2_tle1, conj.sat2_tle2, now, n_points=50, n_periods=1)
        alt1 = track1.get("altitude_km")
        alt2 = track2.get("altitude_km")
        period1 = track1.get("period_min")
        period2 = track2.get("period_min")

        brief = brief_from_json(conj.brief_json) if conj.brief_json else None

        return templates.TemplateResponse(request, "conjunction.html", {
            "conj": conj,
            "plot_json": conj.orbital_plot_json,
            "alt1": alt1, "alt2": alt2,
            "period1": period1, "period2": period2,
            "tca_hours": round(_tca_hours_from_now(conj.tca), 1),
            "brief": brief,
            "demo_mode": DEMO_MODE,
        })


@app.post("/conjunction/{cdm_id}/brief", response_class=JSONResponse)
async def generate_brief(cdm_id: str):
    with get_db() as db:
        conj = db.query(Conjunction).filter(Conjunction.cdm_id == cdm_id).first()
        if not conj:
            raise HTTPException(status_code=404, detail="Conjunction not found")

        now = datetime.now(timezone.utc)
        track1 = generate_orbital_track(conj.sat1_tle1, conj.sat1_tle2, now, n_points=50, n_periods=1)
        track2 = generate_orbital_track(conj.sat2_tle1, conj.sat2_tle2, now, n_points=50, n_periods=1)

        try:
            sections = generate_sda_brief(conj, track1.get("altitude_km"), track2.get("altitude_km"))
        except BriefGenerationError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        conj.brief_json = brief_to_json(sections)
        db.commit()

    return {"status": "ok", "sections": sections}


@app.get("/conjunction/{cdm_id}/pdf")
async def download_pdf(cdm_id: str):
    with get_db() as db:
        conj = db.query(Conjunction).filter(Conjunction.cdm_id == cdm_id).first()
        if not conj:
            raise HTTPException(status_code=404, detail="Conjunction not found")
        if not conj.brief_json:
            raise HTTPException(status_code=400, detail="Generate the SDA brief first")

        sections = brief_from_json(conj.brief_json)
        pdf_bytes = generate_pdf(conj, sections)

    safe_name = conj.cdm_id.replace("/", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="SDA_Brief_{safe_name}.pdf"'},
    )


@app.post("/refresh", response_class=JSONResponse)
async def refresh_cdms():
    """Fetch fresh CDMs from Space-Track (live mode only)."""
    if DEMO_MODE:
        return {"status": "demo_mode", "message": "Live refresh disabled in demo mode"}

    from spacetrack_client import SpaceTrackError
    try:
        with get_db() as db:
            added, skipped = _ingest_cdms(db)
    except SpaceTrackError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"status": "ok", "added": added, "skipped": skipped}


@app.get("/api/stats", response_class=JSONResponse)
async def stats():
    with get_db() as db:
        total = db.query(Conjunction).count()
        high = db.query(Conjunction).filter(
            Conjunction.risk_level.in_(["HIGH", "CRITICAL"])
        ).count()
        demo = db.query(Conjunction).filter(Conjunction.is_demo == True).count()  # noqa: E712

    return {
        "status": "ok",
        "total_conjunctions": total,
        "high_risk": high,
        "demo_conjunctions": demo,
        "demo_mode": DEMO_MODE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
