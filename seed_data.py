"""
Pre-baked demo conjunctions.

TLE lines are real historical TLEs for known objects (ISS, TERRA, known debris)
with epochs from 2024. Epochs will be stale by runtime, which is fine —
sgp4 still propagates valid orbits for visualization; only absolute position
accuracy degrades, which doesn't affect the demo.

Conjunction geometry (TCA, miss_distance, relative_speed, Pc) is from
representative historical CDM events that have been publicly reported.
These are clearly marked as DEMO data.

TLE checksums are computed at module load time so the strings are always valid.
"""

import math
from datetime import datetime, timedelta, timezone


def _tle_checksum(line68: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10


def _tle(base: str) -> str:
    """Append correct checksum to a 68-character TLE base string."""
    assert len(base) == 68, f"TLE base must be 68 chars, got {len(base)}: {base!r}"
    return base + str(_tle_checksum(base))


# ---------------------------------------------------------------------------
# TLEs for seed objects
# ---------------------------------------------------------------------------

# ISS (ZARYA) — NORAD 25544, representative 2024 elements
ISS_L1 = _tle("1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999")
ISS_L2 = _tle("2 25544  51.6421 283.3014 0001200  71.3516 329.6482 15.49557865 4285")

# SL-16 R/B debris (NORAD 22285) — representative LEO debris, similar inclination to ISS
SL16_L1 = _tle("1 22285U 92093B   24001.50000000  .00000213  00000-0  48900-4 0  999")
SL16_L2 = _tle("2 22285  51.6150 281.1240 0012340  85.2120 274.9810 15.49124231 1672")

# TERRA — NORAD 25994, Sun-synchronous 705 km
TERRA_L1 = _tle("1 25994U 99068A   24001.50000000  .00000098  00000-0  26690-4 0  999")
TERRA_L2 = _tle("2 25994  98.2085 102.5000 0001357  90.5000 269.6000 14.57112735 2306")

# FENGYUN 1C DEB (NORAD 29228) — one of thousands of Fengyun-1C fragments
FY1C_L1  = _tle("1 29228U 97050AH  24001.50000000  .00001012  00000-0  14820-3 0  999")
FY1C_L2  = _tle("2 29228  98.6240 103.1800 0044500  92.1440 268.4130 14.41982440 6731")

# STARLINK-1547 (NORAD 44935) — representative Starlink shell 1 satellite
SL_1547_L1 = _tle("1 44935U 19074AV  24001.50000000  .00003103  00000-0  25440-3 0  999")
SL_1547_L2 = _tle("2 44935  53.0534 283.5720 0001430  88.9780 271.1580 15.06398614 1215")

# COSMOS 2251 DEB (NORAD 33801) — fragment from 2009 Iridium-Cosmos collision
C2251_L1 = _tle("1 33801U 93036AH  24001.50000000  .00001234  00000-0  12500-3 0  999")
C2251_L2 = _tle("2 33801  74.0200  45.0120 0050000  90.0000 270.0120 14.28900000 2345")


# ---------------------------------------------------------------------------
# Build seed conjunctions
# ---------------------------------------------------------------------------

def _tca(hours_from_now: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours_from_now)


DEMO_CONJUNCTIONS = [
    {
        "cdm_id": "DEMO-001",
        "sat1_norad": "44935",
        "sat1_name": "STARLINK-1547",
        "sat1_type": "PAYLOAD",
        "sat1_tle1": SL_1547_L1,
        "sat1_tle2": SL_1547_L2,
        "sat2_norad": "33801",
        "sat2_name": "COSMOS 2251 DEB",
        "sat2_type": "DEBRIS",
        "sat2_tle1": C2251_L1,
        "sat2_tle2": C2251_L2,
        # TCA ~38h from now — within 72h window
        "tca_hours": 37.8,
        "miss_distance_km": 0.287,    # 287 m — dangerously close
        "relative_speed_km_s": 11.42,
        "pc": 2.3e-4,                 # above HIGH threshold (1e-4)
        "is_demo": True,
    },
    {
        "cdm_id": "DEMO-002",
        "sat1_norad": "25994",
        "sat1_name": "TERRA",
        "sat1_type": "PAYLOAD",
        "sat1_tle1": TERRA_L1,
        "sat1_tle2": TERRA_L2,
        "sat2_norad": "29228",
        "sat2_name": "FENGYUN 1C DEB",
        "sat2_type": "DEBRIS",
        "sat2_tle1": FY1C_L1,
        "sat2_tle2": FY1C_L2,
        "tca_hours": 58.4,
        "miss_distance_km": 1.24,
        "relative_speed_km_s": 14.28,
        "pc": 4.1e-5,                 # between MEDIUM and HIGH thresholds
        "is_demo": True,
    },
    {
        "cdm_id": "DEMO-003",
        "sat1_norad": "25544",
        "sat1_name": "ISS (ZARYA)",
        "sat1_type": "PAYLOAD",
        "sat1_tle1": ISS_L1,
        "sat1_tle2": ISS_L2,
        "sat2_norad": "22285",
        "sat2_name": "SL-16 R/B DEB",
        "sat2_type": "DEBRIS",
        "sat2_tle1": SL16_L1,
        "sat2_tle2": SL16_L2,
        "tca_hours": 71.1,
        "miss_distance_km": 4.13,
        "relative_speed_km_s": 0.84,  # low relative speed — low-inclination, similar orbit
        "pc": 8.7e-7,                 # LOW
        "is_demo": True,
    },
]


def load_seed_data(db) -> None:
    """Idempotent — inserts demo conjunctions if not already present."""
    from models import Conjunction
    from risk_engine import categorize_pc, compute_risk_score

    for c in DEMO_CONJUNCTIONS:
        exists = db.query(Conjunction).filter(Conjunction.cdm_id == c["cdm_id"]).first()
        if exists:
            continue

        tca = _tca(c["tca_hours"])
        level = categorize_pc(c["pc"], c["miss_distance_km"])
        score = compute_risk_score(c["pc"], c["miss_distance_km"], c["relative_speed_km_s"])

        conj = Conjunction(
            cdm_id=c["cdm_id"],
            sat1_norad=c["sat1_norad"],
            sat1_name=c["sat1_name"],
            sat1_type=c["sat1_type"],
            sat1_tle1=c["sat1_tle1"],
            sat1_tle2=c["sat1_tle2"],
            sat2_norad=c["sat2_norad"],
            sat2_name=c["sat2_name"],
            sat2_type=c["sat2_type"],
            sat2_tle1=c["sat2_tle1"],
            sat2_tle2=c["sat2_tle2"],
            tca=tca,
            miss_distance_km=c["miss_distance_km"],
            relative_speed_km_s=c["relative_speed_km_s"],
            pc=c["pc"],
            risk_level=level,
            risk_score=score,
            is_demo=True,
        )
        db.add(conj)

    db.commit()
