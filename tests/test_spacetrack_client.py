"""
Tests for the Space-Track client.

No real HTTP calls — all API responses are mocked.
"""

from datetime import datetime, timedelta, timezone
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
        assert "MISS_DISTANCE" in url

    def test_contains_miss_distance_filter(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        assert "MISS_DISTANCE" in url

    def test_contains_json_format(self):
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = _build_cdm_url(now)
        assert "json" in url.lower()


# ---------------------------------------------------------------------------
# parse_cdm — valid input
# ---------------------------------------------------------------------------

class TestParseCdm:
    def _raw(self, **overrides):
        base = {
            "CDM_ID": "12345678",
            "TCA": "2024-01-02 12:00:00",
            "MISS_DISTANCE": "0.287",
            "RELATIVE_SPEED": "11.42",
            "COLLISION_PROBABILITY": "2.3e-4",
            "SAT1_OBJECT_DESIGNATOR": "44935",
            "SAT1_OBJECT_NAME": "STARLINK-1547",
            "SAT1_OBJECT_TYPE": "PAYLOAD",
            "SAT1_TLE_LINE1": "1 44935U 19074AV  24001.5 .00003103 00000-0 25440-3 0  9993",
            "SAT1_TLE_LINE2": "2 44935  53.0534 283.5720 0001430  88.9780 271.1580 15.063986141215",
            "SAT2_OBJECT_DESIGNATOR": "33801",
            "SAT2_OBJECT_NAME": "COSMOS 2251 DEB",
            "SAT2_OBJECT_TYPE": "DEBRIS",
            "SAT2_TLE_LINE1": "1 33801U 93036AH  24001.5 .00001234 00000-0 12500-3 0  9994",
            "SAT2_TLE_LINE2": "2 33801  74.0200  45.0120 0050000  90.0000 270.0120 14.289000002345",
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

    def test_miss_distance_float(self):
        result = parse_cdm(self._raw())
        assert isinstance(result["miss_distance_km"], float)
        assert abs(result["miss_distance_km"] - 0.287) < 1e-9

    def test_pc_parsed_as_float(self):
        result = parse_cdm(self._raw())
        assert result["pc"] is not None
        assert abs(result["pc"] - 2.3e-4) < 1e-10

    def test_pc_null_becomes_none(self):
        result = parse_cdm(self._raw(COLLISION_PROBABILITY=None))
        assert result["pc"] is None

    def test_pc_empty_string_becomes_none(self):
        result = parse_cdm(self._raw(COLLISION_PROBABILITY=""))
        assert result["pc"] is None

    def test_tca_is_datetime(self):
        result = parse_cdm(self._raw())
        assert isinstance(result["tca"], datetime)

    def test_tca_is_utc_aware(self):
        result = parse_cdm(self._raw())
        assert result["tca"].tzinfo is not None

    def test_sat_names_stripped(self):
        result = parse_cdm(self._raw(SAT1_OBJECT_NAME="  STARLINK-1547  "))
        assert result["sat1_name"] == "STARLINK-1547"

    def test_object_type_uppercased(self):
        result = parse_cdm(self._raw(SAT1_OBJECT_TYPE="payload"))
        assert result["sat1_type"] == "PAYLOAD"

    def test_missing_miss_distance_returns_none(self):
        result = parse_cdm(self._raw(MISS_DISTANCE=None))
        assert result is None

    def test_invalid_tca_returns_none(self):
        result = parse_cdm(self._raw(TCA="not-a-date"))
        assert result is None

    def test_relative_speed_default_zero(self):
        result = parse_cdm(self._raw(RELATIVE_SPEED=None))
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
