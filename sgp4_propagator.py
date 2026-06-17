"""
Orbital propagation using the sgp4 library.

Coordinate frames used:
  TEME  — True Equator, Mean Equinox (sgp4 native output)
  ECEF  — Earth-Centered, Earth-Fixed (what Plotly renders against Earth sphere)

The TEME→ECEF rotation is a single rotation about the Z-axis by the
Greenwich Mean Sidereal Time (GMST). This is accurate to ~1 km for
visualization purposes (we skip the small equation-of-equinoxes correction).
"""

import math
from datetime import datetime, timezone, timedelta

import numpy as np
from sgp4.api import Satrec, jday

from config import EARTH_RADIUS_KM, ORBITAL_TRACK_POINTS, ORBITAL_TRACKS_PERIODS


# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------

def datetime_to_jd(dt: datetime) -> tuple[float, float]:
    """Convert UTC datetime to (jd, fr) Julian date pair for sgp4."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    jd, fr = jday(dt.year, dt.month, dt.day,
                  dt.hour, dt.minute,
                  dt.second + dt.microsecond / 1e6)
    return jd, fr


def gmst_radians(jd: float, fr: float = 0.0) -> float:
    """Greenwich Mean Sidereal Time in radians (IAU 1982 model)."""
    T = (jd + fr - 2451545.0) / 36525.0
    # GMST in seconds of time
    gmst_s = (67310.54841
              + (876600 * 3600 + 8640184.812866) * T
              + 0.093104 * T * T
              - 6.2e-6 * T * T * T)
    return math.radians((gmst_s / 240.0) % 360.0)


# ---------------------------------------------------------------------------
# Coordinate transforms
# ---------------------------------------------------------------------------

def teme_to_ecef(r_teme: np.ndarray, jd: float, fr: float = 0.0) -> np.ndarray:
    """Rotate a TEME position vector (km) to ECEF."""
    theta = gmst_radians(jd, fr)
    c, s = math.cos(theta), math.sin(theta)
    return np.array([
        c * r_teme[0] + s * r_teme[1],
        -s * r_teme[0] + c * r_teme[1],
        r_teme[2],
    ])


def ecef_to_geodetic(r_ecef: np.ndarray) -> tuple[float, float, float]:
    """
    Approximate ECEF → geodetic (lat°, lon°, alt km).
    Uses spherical Earth approximation (sufficient for display).
    """
    x, y, z = r_ecef
    lon = math.degrees(math.atan2(y, x))
    lat = math.degrees(math.asin(z / np.linalg.norm(r_ecef)))
    alt = np.linalg.norm(r_ecef) - EARTH_RADIUS_KM
    return lat, lon, alt


# ---------------------------------------------------------------------------
# TLE parsing
# ---------------------------------------------------------------------------

class PropagationError(Exception):
    pass


def parse_tle(line1: str, line2: str) -> Satrec:
    sat = Satrec.twoline2rv(line1.strip(), line2.strip())
    return sat


def orbital_period_minutes(mean_motion_rev_per_day: float) -> float:
    """Convert mean motion (rev/day) to period (minutes)."""
    if mean_motion_rev_per_day <= 0:
        raise PropagationError("Invalid mean motion")
    return 1440.0 / mean_motion_rev_per_day


def mean_motion_from_tle(line2: str) -> float:
    """Parse mean motion (rev/day) from TLE line 2 columns 53–63."""
    return float(line2[52:63])


# ---------------------------------------------------------------------------
# Orbital track generation
# ---------------------------------------------------------------------------

def generate_orbital_track(
    line1: str,
    line2: str,
    start_time: datetime,
    n_points: int = ORBITAL_TRACK_POINTS,
    n_periods: float = ORBITAL_TRACKS_PERIODS,
) -> dict:
    """
    Propagate a satellite over n_periods orbital periods starting at start_time.

    Returns dict with keys:
      x, y, z  — ECEF position arrays (km), lists of floats
      lat, lon, alt — geodetic arrays, lists of floats
      altitude_km — mean orbital altitude (km)
      period_min  — orbital period (minutes)
      error       — None on success, error string on failure
    """
    sat = parse_tle(line1, line2)
    try:
        mm = mean_motion_from_tle(line2)
        period_min = orbital_period_minutes(mm)
    except (ValueError, PropagationError) as exc:
        return {"error": str(exc)}

    duration_min = n_periods * period_min
    times = [start_time + timedelta(minutes=duration_min * i / (n_points - 1))
             for i in range(n_points)]

    xs, ys, zs = [], [], []
    lats, lons, alts = [], [], []

    for dt in times:
        jd, fr = datetime_to_jd(dt)
        e, r, _ = sat.sgp4(jd, fr)
        if e != 0:
            # Skip bad points (atmosphere re-entry, etc.)
            continue
        r_ecef = teme_to_ecef(np.array(r), jd, fr)
        xs.append(float(r_ecef[0]))
        ys.append(float(r_ecef[1]))
        zs.append(float(r_ecef[2]))
        lat, lon, alt = ecef_to_geodetic(r_ecef)
        lats.append(float(lat))
        lons.append(float(lon))
        alts.append(float(alt))

    if not xs:
        return {"error": "sgp4 propagation produced no valid points"}

    return {
        "x": xs, "y": ys, "z": zs,
        "lat": lats, "lon": lons, "alt": alts,
        "altitude_km": round(sum(alts) / len(alts), 1),
        "period_min": round(period_min, 2),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Position at a specific epoch
# ---------------------------------------------------------------------------

def position_at(line1: str, line2: str, dt: datetime):
    """
    Return ECEF position (km) of satellite at dt, or None on error.
    Used to mark TCA positions on the 3D plot.
    """
    sat = parse_tle(line1, line2)
    jd, fr = datetime_to_jd(dt)
    e, r, _ = sat.sgp4(jd, fr)
    if e != 0:
        return None
    return teme_to_ecef(np.array(r), jd, fr)


# ---------------------------------------------------------------------------
# Miss distance verification (independent cross-check)
# ---------------------------------------------------------------------------

def compute_miss_distance_km(
    line1_a: str, line2_a: str,
    line1_b: str, line2_b: str,
    tca: datetime,
):
    """
    Compute centre-to-centre separation at TCA using sgp4.
    Returns separation in km, or None on propagation error.
    Used to cross-check CDM miss distance values.
    """
    sat_a = parse_tle(line1_a, line2_a)
    sat_b = parse_tle(line1_b, line2_b)
    jd, fr = datetime_to_jd(tca)

    e_a, r_a, _ = sat_a.sgp4(jd, fr)
    e_b, r_b, _ = sat_b.sgp4(jd, fr)

    if e_a != 0 or e_b != 0:
        return None

    r_a_ecef = teme_to_ecef(np.array(r_a), jd, fr)
    r_b_ecef = teme_to_ecef(np.array(r_b), jd, fr)
    return float(np.linalg.norm(r_a_ecef - r_b_ecef))
