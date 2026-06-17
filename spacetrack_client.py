"""
Space-Track.org CDM client.

Authentication is cookie-based (session). Every API session:
  1. POST /ajaxauth/login with identity + password
  2. Session cookie is retained automatically by httpx
  3. GET /basicspacedata/query/class/cdm_public/...
  4. POST /ajaxauth/logout  (best practice — Space-Track rate-limits sessions)

CDM fields used:
  CDM_ID, TCA, MISS_DISTANCE (km), RELATIVE_SPEED (km/s),
  COLLISION_PROBABILITY (can be null), COLLISION_PROBABILITY_METHOD,
  SAT1_OBJECT_DESIGNATOR, SAT1_OBJECT_NAME, SAT1_OBJECT_TYPE,
  SAT1_TLE_LINE1, SAT1_TLE_LINE2,
  SAT2_OBJECT_DESIGNATOR, SAT2_OBJECT_NAME, SAT2_OBJECT_TYPE,
  SAT2_TLE_LINE1, SAT2_TLE_LINE2

Space-Track query syntax:
  Path segments: /FIELD/OPERATOR+VALUE/
  Operators embedded in value string: > < >= <=
  Example: /TCA/>2024-01-01 00:00:00/MISS_DISTANCE/<5/
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import (
    SPACETRACK_BASE,
    SPACETRACK_LOGIN_URL,
    SPACETRACK_CDM_URL,
    SPACETRACK_USER,
    SPACETRACK_PASS,
    MISS_DISTANCE_THRESHOLD_KM,
    CONJUNCTION_WINDOW_HOURS,
)


class SpaceTrackError(Exception):
    pass


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _build_cdm_url(now: datetime) -> str:
    window_end = now + timedelta(hours=CONJUNCTION_WINDOW_HOURS)
    now_str = _fmt_dt(now)
    end_str = _fmt_dt(window_end)
    return (
        f"{SPACETRACK_CDM_URL}"
        f"/TCA/%3E{now_str}"          # TCA > now (URL-encoded >)
        f"/TCA/%3C{end_str}"          # TCA < now+72h
        f"/MISS_DISTANCE/%3C{MISS_DISTANCE_THRESHOLD_KM}"
        f"/orderby/MISS_DISTANCE%20asc"
        f"/limit/50"
        f"/format/json"
    )


def fetch_cdms(now: datetime | None = None) -> list[dict[str, Any]]:
    """
    Fetch active CDMs from Space-Track for the next 72 hours.
    Returns a list of raw CDM dicts. Raises SpaceTrackError on failure.
    """
    if not SPACETRACK_USER or not SPACETRACK_PASS:
        raise SpaceTrackError("SPACETRACK_USER or SPACETRACK_PASS not configured")

    if now is None:
        now = datetime.now(timezone.utc)

    url = _build_cdm_url(now)

    with httpx.Client(base_url=SPACETRACK_BASE, follow_redirects=True, timeout=30.0) as client:
        # Authenticate
        resp = client.post(
            "/ajaxauth/login",
            data={"identity": SPACETRACK_USER, "password": SPACETRACK_PASS},
        )
        if resp.status_code != 200:
            raise SpaceTrackError(f"Space-Track login failed: HTTP {resp.status_code}")

        login_body = resp.text.strip()
        if "Failed" in login_body or "Invalid" in login_body:
            raise SpaceTrackError(f"Space-Track authentication rejected: {login_body[:200]}")

        # Fetch CDMs
        cdm_resp = client.get(url)
        if cdm_resp.status_code != 200:
            raise SpaceTrackError(f"CDM query failed: HTTP {cdm_resp.status_code}")

        try:
            data = cdm_resp.json()
        except Exception as exc:
            raise SpaceTrackError(f"Failed to parse CDM JSON: {exc}") from exc

        # Logout (best practice)
        try:
            client.get("/ajaxauth/logout")
        except Exception:
            pass

    if not isinstance(data, list):
        raise SpaceTrackError(f"Unexpected CDM response format: {type(data)}")

    return data


def parse_cdm(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert a raw Space-Track CDM dict to our internal format.
    Returns None if required fields are missing or malformed.
    """
    try:
        tca_str = raw.get("TCA", "")
        tca = datetime.strptime(tca_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

        miss_raw = raw.get("MISS_DISTANCE")
        if miss_raw is None:
            return None
        miss_km = float(miss_raw)

        speed_raw = raw.get("RELATIVE_SPEED")
        relative_speed = float(speed_raw) if speed_raw not in (None, "") else 0.0

        pc_raw = raw.get("COLLISION_PROBABILITY")
        pc = float(pc_raw) if pc_raw not in (None, "", "N/A") else None

        return {
            "cdm_id": str(raw.get("CDM_ID", "")),
            "tca": tca,
            "miss_distance_km": miss_km,
            "relative_speed_km_s": relative_speed,
            "pc": pc,
            "sat1_norad": str(raw.get("SAT1_OBJECT_DESIGNATOR", "")).strip(),
            "sat1_name": (raw.get("SAT1_OBJECT_NAME") or "UNKNOWN").strip(),
            "sat1_type": (raw.get("SAT1_OBJECT_TYPE") or "UNKNOWN").upper().strip(),
            "sat1_tle1": (raw.get("SAT1_TLE_LINE1") or "").strip(),
            "sat1_tle2": (raw.get("SAT1_TLE_LINE2") or "").strip(),
            "sat2_norad": str(raw.get("SAT2_OBJECT_DESIGNATOR", "")).strip(),
            "sat2_name": (raw.get("SAT2_OBJECT_NAME") or "UNKNOWN").strip(),
            "sat2_type": (raw.get("SAT2_OBJECT_TYPE") or "UNKNOWN").upper().strip(),
            "sat2_tle1": (raw.get("SAT2_TLE_LINE1") or "").strip(),
            "sat2_tle2": (raw.get("SAT2_TLE_LINE2") or "").strip(),
        }
    except (ValueError, TypeError, KeyError):
        return None


def fetch_and_parse_cdms(now: datetime | None = None) -> list[dict[str, Any]]:
    """Fetch CDMs and parse to internal format. Skips malformed records."""
    raw_list = fetch_cdms(now)
    parsed = [parse_cdm(r) for r in raw_list]
    return [p for p in parsed if p is not None]
