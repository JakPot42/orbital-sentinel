"""
Tests for the sgp4 propagator module.

These tests verify:
- GMST calculation (known reference values)
- TEME→ECEF transform (rotation properties)
- TLE parsing + track generation (correct structure, reasonable values)
- Position-at-epoch (returns plausible coordinates)
- Coordinate range checks (lat/lon/alt within physical bounds)
"""

import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pytest

from sgp4_propagator import (
    datetime_to_jd,
    gmst_radians,
    teme_to_ecef,
    ecef_to_geodetic,
    parse_tle,
    mean_motion_from_tle,
    orbital_period_minutes,
    generate_orbital_track,
    position_at,
    compute_miss_distance_km,
    PropagationError,
)
from config import EARTH_RADIUS_KM


def _tle_checksum(line68: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10

def _tle(base: str) -> str:
    return base + str(_tle_checksum(base))

ISS_L1 = _tle("1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999")
ISS_L2 = _tle("2 25544  51.6421 283.3014 0001200  71.3516 329.6482 15.49557865 4285")

DEB_L1 = _tle("1 22285U 92093B   24001.50000000  .00000213  00000-0  48900-4 0  999")
DEB_L2 = _tle("2 22285  51.6150 281.1240 0012340  85.2120 274.9810 15.49124231 1672")


# ---------------------------------------------------------------------------
# datetime_to_jd
# ---------------------------------------------------------------------------

class TestDatetimeToJd:
    def test_j2000_epoch(self):
        # J2000.0 = 2000-01-01 12:00:00 UTC = JD 2451545.0
        dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        jd, fr = datetime_to_jd(dt)
        assert abs(jd + fr - 2451545.0) < 1e-6

    def test_returns_tuple_of_two(self):
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = datetime_to_jd(dt)
        assert len(result) == 2

    def test_naive_datetime_treated_as_utc(self):
        dt_naive = datetime(2024, 1, 1, 0, 0, 0)
        dt_aware = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        jd1, fr1 = datetime_to_jd(dt_naive)
        jd2, fr2 = datetime_to_jd(dt_aware)
        assert abs((jd1 + fr1) - (jd2 + fr2)) < 1e-9


# ---------------------------------------------------------------------------
# gmst_radians
# ---------------------------------------------------------------------------

class TestGmst:
    def test_returns_float_in_0_2pi(self):
        jd, fr = datetime_to_jd(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
        g = gmst_radians(jd, fr)
        assert isinstance(g, float)
        assert 0 <= g < 2 * math.pi

    def test_advances_one_sidereal_day(self):
        # After exactly one sidereal day (~23h 56m 4s ≈ 86164.1s), GMST should advance 2π
        dt1 = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        dt2 = dt1 + timedelta(seconds=86164.1)
        jd1, fr1 = datetime_to_jd(dt1)
        jd2, fr2 = datetime_to_jd(dt2)
        g1 = gmst_radians(jd1, fr1)
        g2 = gmst_radians(jd2, fr2)
        diff = (g2 - g1) % (2 * math.pi)
        assert abs(diff) < 0.01  # within ~0.6 degrees tolerance


# ---------------------------------------------------------------------------
# teme_to_ecef
# ---------------------------------------------------------------------------

class TestTemeToEcef:
    def test_returns_array_of_3(self):
        r = np.array([7000.0, 0.0, 0.0])
        jd, fr = datetime_to_jd(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        result = teme_to_ecef(r, jd, fr)
        assert result.shape == (3,)

    def test_preserves_norm(self):
        # Rotation must not change vector magnitude
        r = np.array([5000.0, 3000.0, 2000.0])
        jd, fr = datetime_to_jd(datetime(2024, 3, 20, 12, 0, 0, tzinfo=timezone.utc))
        r_ecef = teme_to_ecef(r, jd, fr)
        assert abs(np.linalg.norm(r) - np.linalg.norm(r_ecef)) < 1e-6

    def test_z_component_unchanged(self):
        # The TEME→ECEF rotation is about the Z-axis, so z is invariant
        r = np.array([5000.0, 2000.0, 4000.0])
        jd, fr = datetime_to_jd(datetime(2024, 6, 15, 6, 0, 0, tzinfo=timezone.utc))
        r_ecef = teme_to_ecef(r, jd, fr)
        assert abs(r[2] - r_ecef[2]) < 1e-6


# ---------------------------------------------------------------------------
# ecef_to_geodetic
# ---------------------------------------------------------------------------

class TestEcefToGeodetic:
    def test_north_pole(self):
        # North pole: ECEF [0, 0, 6371+500] → lat ≈ 90°
        r = np.array([0.0, 0.0, EARTH_RADIUS_KM + 500])
        lat, lon, alt = ecef_to_geodetic(r)
        assert abs(lat - 90.0) < 0.1

    def test_equator_prime_meridian(self):
        # [R, 0, 0] → lat=0, lon=0
        r = np.array([EARTH_RADIUS_KM + 500, 0.0, 0.0])
        lat, lon, alt = ecef_to_geodetic(r)
        assert abs(lat) < 0.1
        assert abs(lon) < 0.1

    def test_altitude_reasonable(self):
        r = np.array([6371.0 + 400, 0.0, 0.0])
        _, _, alt = ecef_to_geodetic(r)
        assert abs(alt - 400.0) < 1.0

    def test_latitude_bounds(self):
        for x, y, z in [(6871, 0, 0), (0, 6871, 0), (4000, 4000, 3000)]:
            lat, lon, alt = ecef_to_geodetic(np.array([float(x), float(y), float(z)]))
            assert -90 <= lat <= 90
            assert -180 <= lon <= 180


# ---------------------------------------------------------------------------
# mean_motion_from_tle / orbital_period_minutes
# ---------------------------------------------------------------------------

class TestOrbitalPeriod:
    def test_iss_period_approx_92min(self):
        mm = mean_motion_from_tle(ISS_L2)
        period = orbital_period_minutes(mm)
        # ISS orbits ~15.5 times/day → period ~93 min
        assert 85 < period < 100

    def test_zero_mean_motion_raises(self):
        with pytest.raises(PropagationError):
            orbital_period_minutes(0.0)

    def test_negative_mean_motion_raises(self):
        with pytest.raises(PropagationError):
            orbital_period_minutes(-1.0)


# ---------------------------------------------------------------------------
# generate_orbital_track
# ---------------------------------------------------------------------------

class TestGenerateOrbitalTrack:
    def test_returns_dict_with_expected_keys(self, iss_tle):
        l1, l2 = iss_tle
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_orbital_track(l1, l2, now, n_points=20, n_periods=1.0)
        assert result.get("error") is None
        for key in ("x", "y", "z", "lat", "lon", "alt", "altitude_km", "period_min"):
            assert key in result

    def test_track_length(self, iss_tle):
        l1, l2 = iss_tle
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_orbital_track(l1, l2, now, n_points=50, n_periods=1.0)
        assert len(result["x"]) == 50

    def test_altitude_plausible_iss(self, iss_tle):
        l1, l2 = iss_tle
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_orbital_track(l1, l2, now, n_points=20, n_periods=1.0)
        # ISS at ~408 km altitude
        assert 380 < result["altitude_km"] < 450

    def test_lat_lon_bounds(self, iss_tle):
        l1, l2 = iss_tle
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_orbital_track(l1, l2, now, n_points=40, n_periods=1.0)
        for lat in result["lat"]:
            assert -90 <= lat <= 90
        for lon in result["lon"]:
            assert -180 <= lon <= 180

    def test_ecef_norm_above_earth(self, iss_tle):
        l1, l2 = iss_tle
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_orbital_track(l1, l2, now, n_points=20, n_periods=1.0)
        for x, y, z in zip(result["x"], result["y"], result["z"]):
            r = math.sqrt(x**2 + y**2 + z**2)
            assert r > EARTH_RADIUS_KM


# ---------------------------------------------------------------------------
# position_at
# ---------------------------------------------------------------------------

class TestPositionAt:
    def test_returns_array(self, iss_tle):
        l1, l2 = iss_tle
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        pos = position_at(l1, l2, dt)
        assert pos is not None
        assert len(pos) == 3

    def test_position_above_earth(self, iss_tle):
        l1, l2 = iss_tle
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        pos = position_at(l1, l2, dt)
        assert np.linalg.norm(pos) > EARTH_RADIUS_KM


# ---------------------------------------------------------------------------
# compute_miss_distance_km
# ---------------------------------------------------------------------------

class TestComputeMissDistance:
    def test_same_tle_same_time_zero_miss(self, iss_tle):
        l1, l2 = iss_tle
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dist = compute_miss_distance_km(l1, l2, l1, l2, dt)
        assert dist is not None
        assert dist < 0.001  # same object at same time

    def test_different_objects_nonzero_miss(self, iss_tle, debris_tle):
        l1_a, l2_a = iss_tle
        l1_b, l2_b = debris_tle
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dist = compute_miss_distance_km(l1_a, l2_a, l1_b, l2_b, dt)
        assert dist is not None
        assert dist > 0
