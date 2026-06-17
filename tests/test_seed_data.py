"""
Tests for seed data integrity — TLE format, checksum correctness,
and idempotent database loading.
"""

import pytest
from sgp4.api import Satrec

from seed_data import DEMO_CONJUNCTIONS, _tle_checksum, _tle, load_seed_data
from models import Conjunction


class TestTleChecksum:
    def test_checksum_function_returns_single_digit(self):
        line = "1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999"
        result = _tle_checksum(line)
        assert 0 <= result <= 9

    def test_tle_appends_checksum(self):
        base = "1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999"
        result = _tle(base)
        assert len(result) == 69
        assert result[-1].isdigit()

    def test_tle_checksum_valid(self):
        base = "1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999"
        result = _tle(base)
        # Verify: compute checksum of first 68 chars, compare to last char
        expected = _tle_checksum(result[:-1])
        assert int(result[-1]) == expected


class TestDemoConjunctions:
    def test_three_demo_conjunctions_defined(self):
        assert len(DEMO_CONJUNCTIONS) == 3

    def test_all_have_required_fields(self):
        required = {
            "cdm_id", "sat1_norad", "sat1_name", "sat1_type",
            "sat1_tle1", "sat1_tle2", "sat2_norad", "sat2_name",
            "sat2_type", "sat2_tle1", "sat2_tle2",
            "tca_hours", "miss_distance_km", "relative_speed_km_s", "pc",
        }
        for c in DEMO_CONJUNCTIONS:
            missing = required - set(c.keys())
            assert not missing, f"{c['cdm_id']} missing: {missing}"

    def test_unique_cdm_ids(self):
        ids = [c["cdm_id"] for c in DEMO_CONJUNCTIONS]
        assert len(ids) == len(set(ids))

    def test_tca_within_72h_window(self):
        for c in DEMO_CONJUNCTIONS:
            assert 0 < c["tca_hours"] <= 72

    def test_miss_distances_positive(self):
        for c in DEMO_CONJUNCTIONS:
            assert c["miss_distance_km"] > 0

    def test_pc_values_in_valid_range(self):
        for c in DEMO_CONJUNCTIONS:
            assert 0 < c["pc"] <= 1.0

    @pytest.mark.parametrize("idx,expected_level", [
        (0, "HIGH"),    # DEMO-001: Pc=2.3e-4 → HIGH
        (1, "MEDIUM"),  # DEMO-002: Pc=4.1e-5 → MEDIUM
        (2, "LOW"),     # DEMO-003: Pc=8.7e-7 → LOW
    ])
    def test_risk_levels_as_expected(self, idx, expected_level):
        from risk_engine import categorize_pc
        c = DEMO_CONJUNCTIONS[idx]
        level = categorize_pc(c["pc"], c["miss_distance_km"])
        assert level == expected_level


class TestTleValidity:
    """Verify seed TLEs can be parsed by sgp4 without error."""

    @pytest.mark.parametrize("conj", DEMO_CONJUNCTIONS)
    def test_sat1_tle_parseable(self, conj):
        sat = Satrec.twoline2rv(conj["sat1_tle1"].strip(), conj["sat1_tle2"].strip())
        assert sat is not None

    @pytest.mark.parametrize("conj", DEMO_CONJUNCTIONS)
    def test_sat2_tle_parseable(self, conj):
        sat = Satrec.twoline2rv(conj["sat2_tle1"].strip(), conj["sat2_tle2"].strip())
        assert sat is not None

    @pytest.mark.parametrize("conj", DEMO_CONJUNCTIONS)
    def test_sat1_propagates_without_error(self, conj):
        from datetime import datetime, timezone
        from sgp4.api import jday
        sat = Satrec.twoline2rv(conj["sat1_tle1"], conj["sat1_tle2"])
        dt = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        e, r, v = sat.sgp4(jd, fr)
        assert e == 0, f"sgp4 error code {e} for {conj['cdm_id']} sat1"

    @pytest.mark.parametrize("conj", DEMO_CONJUNCTIONS)
    def test_sat2_propagates_without_error(self, conj):
        from datetime import datetime, timezone
        from sgp4.api import jday
        sat = Satrec.twoline2rv(conj["sat2_tle1"], conj["sat2_tle2"])
        dt = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        e, r, v = sat.sgp4(jd, fr)
        assert e == 0, f"sgp4 error code {e} for {conj['cdm_id']} sat2"


class TestLoadSeedData:
    def test_seed_idempotent(self, db):
        """Calling load_seed_data twice should not duplicate records."""
        load_seed_data(db)
        load_seed_data(db)
        count = db.query(Conjunction).filter(Conjunction.cdm_id.like("DEMO-%")).count()
        assert count == 3

    def test_seed_creates_demo_conjunctions(self, db):
        load_seed_data(db)
        demo_001 = db.query(Conjunction).filter(Conjunction.cdm_id == "DEMO-001").first()
        assert demo_001 is not None

    def test_seed_sets_risk_level(self, db):
        load_seed_data(db)
        demo_001 = db.query(Conjunction).filter(Conjunction.cdm_id == "DEMO-001").first()
        assert demo_001.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_seed_marks_is_demo_true(self, db):
        load_seed_data(db)
        for cdm_id in ("DEMO-001", "DEMO-002", "DEMO-003"):
            c = db.query(Conjunction).filter(Conjunction.cdm_id == cdm_id).first()
            assert c.is_demo is True
