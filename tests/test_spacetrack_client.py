"""
Tests for the Space-Track client.

No real HTTP calls — all API responses are mocked.
Field names reflect actual cdm_public schema (confirmed 2026-06-17):
  MIN_RNG (meters), PC, SAT_1_ID, SAT_1_NAME, SAT_2_ID, SAT_2_NAME.
  TCA is ISO format: "2026-06-17T20:47:03.722000"
  No TLE lines in cdm_public — injected separately via gp class.
"""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from spacetrack_client import (
    parse_cdm,
    _fmt_dt,
    _build_cdm_url,
    SpaceTrackError,
    fetch_cdms,
)


# ---------------------------------------------------------------------------
# _fmt_dt
# ---------------------------------------------------------------------------

class TestFmtDt:
    def test_format_matches_spacetrack(self):
        dt = datetime(2024, 6, 15, 12, 30, 45)
        result = _fmt_dt(dt)
        assert result == "2024-06-15 12:30:45"


# ---------------------------------------------------------------------------
# _build_cdm_url
# ---------------------------------------------------------------------------

class TestBuildCdmUrl:
    def test_contains_tca_filter(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        assert "cdm_public" in url
        assert "TCA" in url

    def test_contains_min_rng_filter(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        assert "MIN_RNG" in url

    def test_threshold_in_meters(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        # MISS_DISTANCE_THRESHOLD_KM=5.0 → 5000 metres in the URL
        assert "5000" in url

    def test_contains_json_format(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        assert "json" in url.lower()

    def test_no_miss_distance_column(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        assert "MISS_DISTANCE" not in url


# ---------------------------------------------------------------------------
# parse_cdm — valid input
# ---------------------------------------------------------------------------

class TestParseCdm:
    def _raw(self, **overrides):
        base = {
            "CDM_ID": "12345678",
            "TCA": "2024-01-02T12:00:00.000000",  # ISO format as returned by Space-Track
            "MIN_RNG": "287",                       # metres (not km)
            "PC": "2.3e-4",
            "SAT_1_ID": "44935",
            "SAT_1_NAME": "STARLINK-1547",
            "SAT1_OBJECT_TYPE": "PAYLOAD",
            "SAT_2_ID": "33801",
            "SAT_2_NAME": "COSMOS 2251 DEB",
            "SAT2_OBJECT_TYPE": "DEBRIS",
        }
        base.update(overrides)
        return base

    def test_returns_dict_on_valid_input(self):
        result = parse_cdm(self._raw())
        assert result is not None
        assert isinstance(result, dict)

    def test_cdm_id_parsed(self):
        result = parse_cdm(self._raw())
        assert result["cdm_id"] == "12345678"

    def test_miss_distance_converted_to_km(self):
        result = parse_cdm(self._raw(MIN_RNG="287"))
        assert isinstance(result["miss_distance_km"], float)
        assert abs(result["miss_distance_km"] - 0.287) < 1e-9

    def test_pc_parsed_as_float(self):
        result = parse_cdm(self._raw())
        assert result["pc"] is not None
        assert abs(result["pc"] - 2.3e-4) < 1e-10

    def test_pc_null_becomes_none(self):
        result = parse_cdm(self._raw(PC=None))
        assert result["pc"] is None

    def test_pc_empty_string_becomes_none(self):
        result = parse_cdm(self._raw(PC=""))
        assert result["pc"] is None

    def test_tca_is_datetime(self):
        result = parse_cdm(self._raw())
        assert isinstance(result["tca"], datetime)

    def test_tca_is_utc_aware(self):
        result = parse_cdm(self._raw())
        assert result["tca"].tzinfo is not None

    def test_tca_iso_format_with_microseconds(self):
        result = parse_cdm(self._raw(TCA="2026-06-17T20:47:03.722000"))
        assert result is not None
        assert result["tca"].hour == 20
        assert result["tca"].minute == 47

    def test_sat1_norad_from_sat_1_id(self):
        result = parse_cdm(self._raw())
        assert result["sat1_norad"] == "44935"

    def test_sat2_norad_from_sat_2_id(self):
        result = parse_cdm(self._raw())
        assert result["sat2_norad"] == "33801"

    def test_sat_names_stripped(self):
        result = parse_cdm(self._raw(**{"SAT_1_NAME": "  STARLINK-1547  "}))
        assert result["sat1_name"] == "STARLINK-1547"

    def test_sat2_name(self):
        result = parse_cdm(self._raw())
        assert result["sat2_name"] == "COSMOS 2251 DEB"

    def test_object_type_uppercased(self):
        result = parse_cdm(self._raw(SAT1_OBJECT_TYPE="payload"))
        assert result["sat1_type"] == "PAYLOAD"

    def test_tle_fields_empty_strings(self):
        result = parse_cdm(self._raw())
        assert result["sat1_tle1"] == ""
        assert result["sat1_tle2"] == ""
        assert result["sat2_tle1"] == ""
        assert result["sat2_tle2"] == ""

    def test_missing_min_rng_returns_none(self):
        result = parse_cdm(self._raw(MIN_RNG=None))
        assert result is None

    def test_invalid_tca_returns_none(self):
        result = parse_cdm(self._raw(TCA="not-a-date"))
        assert result is None

    def test_relative_speed_always_zero(self):
        result = parse_cdm(self._raw())
        assert result is not None
        assert result["relative_speed_km_s"] == 0.0


# ---------------------------------------------------------------------------
# fetch_cdms — missing credentials
# ---------------------------------------------------------------------------

class TestFetchCdmsMissingCreds:
    def test_raises_if_no_user(self):
        with patch("spacetrack_client.SPACETRACK_USER", ""), \
             patch("spacetrack_client.SPACETRACK_PASS", "secret"):
            with pytest.raises(SpaceTrackError, match="SPACETRACK_USER"):
                fetch_cdms()

    def test_raises_if_no_pass(self):
        with patch("spacetrack_client.SPACETRACK_USER", "user@test.com"), \
             patch("spacetrack_client.SPACETRACK_PASS", ""):
            with pytest.raises(SpaceTrackError, match="SPACETRACK_PASS"):
                fetch_cdms()


# ---------------------------------------------------------------------------
# fetch_cdms — mocked HTTP (login failure)
# ---------------------------------------------------------------------------

class TestFetchCdmsMockedHttp:
    def test_login_failure_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("spacetrack_client.SPACETRACK_USER", "u"), \
             patch("spacetrack_client.SPACETRACK_PASS", "p"), \
             patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = lambda s: mock_ctx
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.post.return_value = mock_resp

            with pytest.raises(SpaceTrackError, match="login failed"):
                fetch_cdms()

    def test_space_track_error_response_raises(self):
        """Space-Track returns [{"error":"..."}] for bad column names."""
        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.text = ""

        cdm_resp = MagicMock()
        cdm_resp.status_code = 200
        cdm_resp.json.return_value = [{"error": "COLUMN [miss_distance] DOES NOT EXIST"}]

        with patch("spacetrack_client.SPACETRACK_USER", "u"), \
             patch("spacetrack_client.SPACETRACK_PASS", "p"), \
             patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = lambda s: mock_ctx
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.post.return_value = login_resp
            mock_ctx.get.return_value = cdm_resp

            with pytest.raises(SpaceTrackError, match="query error"):
                fetch_cdms()
