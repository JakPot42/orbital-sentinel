"""
Space-Track.org CDM client.

Authentication is cookie-based (session). Every API session:
  1. POST /ajaxauth/login with identity + password
  2. Session cookie is retained automatically by httpx
  3. GET /basicspacedata/query/class/cdm_public/...
  4. GET /basicspacedata/query/class/gp/... (TLE fetch by NORAD ID)
  5. POST /ajaxauth/logout

Real cdm_public field names (confirmed via live API):
  CDM_ID, TCA (ISO format), MIN_RNG (meters), PC,
  SAT_1_ID, SAT_1_NAME, SAT1_OBJECT_TYPE,
  SAT_2_ID, SAT_2_NAME, SAT2_OBJECT_TYPE
  NOTE: TLE lines are NOT embedded in cdm_public — fetched separately via gp class.

Space-Track query syntax:
  Path segments: /FIELD/OPERATOR+VALUE/
  URL-encode operators: %3E = >, %3C = <, %20 = space
  Example: /MIN_RNG/%3C5000/TCA/%3Enow/format/json
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import (
    SPACETRACK_BASE,
    SPACETRACK_USER,
    SPACETRACK_PASS,
    SPACETRACK_CDM_URL,
    MISS_DISTANCE_THRESHOLD_KM,
    CONJUNCTION_WINDOW_HOURS,
)

_GP_URL = f"{SPACETRACK_BASE}/basicspacedata/query/class/gp"


class SpaceTrackError(Exception):
    pass


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _build_cdm_url(now: datetime) -> str:
    window_end = now + timedelta(hours=CONJUNCTION_WINDOW_HOURS)
    now_str = _fmt_dt(now).replace(" ", "%20")
    end_str = _fmt_dt(window_end).replace(" ", "%20")
    threshold_m = int(MISS_DISTANCE_THRESHOLD_KM * 1000)  # config is km; API expects meters
    return (
        f"{SPACETRACK_CDM_URL}"
        f"/TCA/%3E{now_str}"
        f"/TCA/%3C{end_str}"
        f"/MIN_RNG/%3C{threshold_m}"
        f"/orderby/MIN_RNG%20asc"
        f"/limit/50"
        f"/format/json"
    )


def fetch_cdms(now: datetime | None = None) -> list[dict[str, Any]]:
    """
    Fetch raw CDMs from Space-Track for the next 72 hours.
    Returns list of raw dicts. TLE fields are NOT present in cdm_public.
    Raises SpaceTrackError on failure.
    """
    if not SPACETRACK_USER or not SPACETRACK_PASS:
        raise SpaceTrackError("SPACETRACK_USER or SPACETRACK_PASS not configured")

    if now is None:
        now = datetime.now(timezone.utc)

    url = _build_cdm_url(now)

    with httpx.Client(base_url=SPACETRACK_BASE, follow_redirects=True, timeout=30.0) as client:
        resp = client.post(
            "/ajaxauth/login",
            data={"identity": SPACETRACK_USER, "password": SPACETRACK_PASS},
        )
        if resp.status_code != 200:
            raise SpaceTrackError(f"Space-Track login failed: HTTP {resp.status_code}")

        login_body = resp.text.strip()
        if "Failed" in login_body or "Invalid" in login_body:
            raise SpaceTrackError(f"Space-Track authentication rejected: {login_body[:200]}")

        cdm_resp = client.get(url)
        if cdm_resp.status_code != 200:
            raise SpaceTrackError(f"CDM query failed: HTTP {cdm_resp.status_code}")

        try:
            data = cdm_resp.json()
        except Exception as exc:
            raise SpaceTrackError(f"Failed to parse CDM JSON: {exc}") from exc

        try:
            client.get("/ajaxauth/logout")
        except Exception:
            pass

    if not isinstance(data, list):
        raise SpaceTrackError(f"Unexpected CDM response format: {type(data)}")

    # Space-Track returns [{"error":"..."}] on query errors — detect and raise
    if data and isinstance(data[0], dict) and "error" in data[0]:
        raise SpaceTrackError(f"Space-Track query error: {data[0]['error']}")

    return data


def parse_cdm(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert a raw cdm_public dict to internal format.
    TLE fields (sat1_tle1/2, sat2_tle1/2) are empty strings here;
    they are injected by fetch_and_parse_cdms() after a GP lookup.
    Returns None if required fields are missing or malformed.
    """
    try:
        tca_str = raw.get("TCA", "")
        # cdm_public TCA is ISO format: "2026-06-17T20:47:03.722000"
        tca = datetime.fromisoformat(tca_str).replace(tzinfo=timezone.utc)

        miss_raw = raw.get("MIN_RNG")
        if miss_raw is None:
            return None
        miss_km = float(miss_raw) / 1000.0  # API returns meters

        pc_raw = raw.get("PC")
        pc = float(pc_raw) if pc_raw not in (None, "", "N/A") else None

        return {
            "cdm_id": str(raw.get("CDM_ID", "")),
            "tca": tca,
            "miss_distance_km": miss_km,
            "relative_speed_km_s": 0.0,  # not available in cdm_public
            "pc": pc,
            "sat1_norad": str(raw.get("SAT_1_ID", "")).strip(),
            "sat1_name": (raw.get("SAT_1_NAME") or "UNKNOWN").strip(),
            "sat1_type": (raw.get("SAT1_OBJECT_TYPE") or "UNKNOWN").upper().strip(),
            "sat1_tle1": "",
            "sat1_tle2": "",
            "sat2_norad": str(raw.get("SAT_2_ID", "")).strip(),
            "sat2_name": (raw.get("SAT_2_NAME") or "UNKNOWN").strip(),
            "sat2_type": (raw.get("SAT2_OBJECT_TYPE") or "UNKNOWN").upper().strip(),
            "sat2_tle1": "",
            "sat2_tle2": "",
        }
    except (ValueError, TypeError, KeyError):
        return None


def _fetch_tles(client: httpx.Client, norad_ids: set[str]) -> dict[str, tuple[str, str]]:
    """
    Fetch current TLEs for a set of NORAD catalog IDs via the gp class.
    Returns {norad_id_str: (tle_line1, tle_line2)}.
    """
    if not norad_ids:
        return {}
    ids_str = ",".join(sorted(norad_ids))
    url = f"{_GP_URL}/NORAD_CAT_ID/{ids_str}/format/json"
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            return {}
        records = resp.json()
        if not isinstance(records, list):
            return {}
        result: dict[str, tuple[str, str]] = {}
        for rec in records:
            norad = str(rec.get("NORAD_CAT_ID", "")).strip()
            tle1 = (rec.get("TLE_LINE1") or "").strip()
            tle2 = (rec.get("TLE_LINE2") or "").strip()
            if norad and tle1 and tle2:
                result[norad] = (tle1, tle2)
        return result
    except Exception:
        return {}


def fetch_and_parse_cdms(now: datetime | None = None) -> list[dict[str, Any]]:
    """
    Fetch CDMs and inject TLEs in a single authenticated session.
    Returns parsed conjunction dicts with TLE lines populated where available.
    """
    if not SPACETRACK_USER or not SPACETRACK_PASS:
        raise SpaceTrackError("SPACETRACK_USER or SPACETRACK_PASS not configured")

    if now is None:
        now = datetime.now(timezone.utc)

    url = _build_cdm_url(now)

    with httpx.Client(base_url=SPACETRACK_BASE, follow_redirects=True, timeout=30.0) as client:
        resp = client.post(
            "/ajaxauth/login",
            data={"identity": SPACETRACK_USER, "password": SPACETRACK_PASS},
        )
        if resp.status_code != 200:
            raise SpaceTrackError(f"Space-Track login failed: HTTP {resp.status_code}")
        login_body = resp.text.strip()
        if "Failed" in login_body or "Invalid" in login_body:
            raise SpaceTrackError(f"Space-Track authentication rejected: {login_body[:200]}")

        cdm_resp = client.get(url)
        if cdm_resp.status_code != 200:
            raise SpaceTrackError(f"CDM query failed: HTTP {cdm_resp.status_code}")

        try:
            raw_list = cdm_resp.json()
        except Exception as exc:
            raise SpaceTrackError(f"Failed to parse CDM JSON: {exc}") from exc

        if not isinstance(raw_list, list):
            raise SpaceTrackError(f"Unexpected CDM response format: {type(raw_list)}")

        if raw_list and isinstance(raw_list[0], dict) and "error" in raw_list[0]:
            raise SpaceTrackError(f"Space-Track query error: {raw_list[0]['error']}")

        parsed = [parse_cdm(r) for r in raw_list]
        parsed = [p for p in parsed if p is not None]

        # Fetch TLEs for all unique NORAD IDs in one GP query
        if parsed:
            norad_ids = {p["sat1_norad"] for p in parsed if p["sat1_norad"]}
            norad_ids |= {p["sat2_norad"] for p in parsed if p["sat2_norad"]}
            tle_map = _fetch_tles(client, norad_ids)
            for p in parsed:
                if p["sat1_norad"] in tle_map:
                    p["sat1_tle1"], p["sat1_tle2"] = tle_map[p["sat1_norad"]]
                if p["sat2_norad"] in tle_map:
                    p["sat2_tle1"], p["sat2_tle2"] = tle_map[p["sat2_norad"]]

        try:
            client.get("/ajaxauth/logout")
        except Exception:
            pass

    return parsed
