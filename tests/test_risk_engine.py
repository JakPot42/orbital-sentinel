import pytest
from risk_engine import (
    categorize_pc,
    compute_risk_score,
    format_pc,
    superscript,
    risk_css_class,
    object_type_label,
)
from config import PC_CRITICAL, PC_HIGH, PC_MEDIUM


# ---------------------------------------------------------------------------
# categorize_pc — with Pc available
# ---------------------------------------------------------------------------

class TestCategorizePc:
    def test_critical_at_threshold(self):
        assert categorize_pc(PC_CRITICAL, 0.1) == "CRITICAL"

    def test_critical_above_threshold(self):
        assert categorize_pc(1e-2, 0.1) == "CRITICAL"

    def test_high_at_threshold(self):
        assert categorize_pc(PC_HIGH, 0.1) == "HIGH"

    def test_high_below_critical(self):
        assert categorize_pc(5e-4, 0.5) == "HIGH"

    def test_medium_at_threshold(self):
        assert categorize_pc(PC_MEDIUM, 0.1) == "MEDIUM"

    def test_medium_below_high(self):
        assert categorize_pc(4.1e-5, 1.2) == "MEDIUM"

    def test_low_below_medium(self):
        assert categorize_pc(1e-6, 3.0) == "LOW"

    def test_zero_pc_is_low(self):
        assert categorize_pc(0.0, 4.9) == "LOW"

    # Boundary: exactly at threshold
    def test_exactly_1e_minus_4(self):
        assert categorize_pc(1e-4, 0.5) == "HIGH"

    def test_just_below_1e_minus_4(self):
        assert categorize_pc(9.99e-5, 0.5) == "MEDIUM"


# ---------------------------------------------------------------------------
# categorize_pc — Pc is None (miss-distance fallback)
# ---------------------------------------------------------------------------

class TestCategorizePcFallback:
    def test_none_pc_close_miss_is_high(self):
        assert categorize_pc(None, 0.3) == "HIGH"

    def test_none_pc_medium_miss(self):
        assert categorize_pc(None, 1.5) == "MEDIUM"

    def test_none_pc_far_miss_is_low(self):
        assert categorize_pc(None, 4.0) == "LOW"

    def test_none_pc_at_high_boundary(self):
        # MISS_HIGH_KM = 0.5 — exactly at threshold → HIGH
        assert categorize_pc(None, 0.5) == "MEDIUM"  # 0.5 is NOT < 0.5

    def test_none_pc_just_inside_high(self):
        assert categorize_pc(None, 0.499) == "HIGH"


# ---------------------------------------------------------------------------
# compute_risk_score
# ---------------------------------------------------------------------------

class TestComputeRiskScore:
    def test_returns_float(self):
        score = compute_risk_score(1e-4, 0.3, 7.0)
        assert isinstance(score, float)

    def test_high_pc_high_score(self):
        score = compute_risk_score(1e-3, 0.1, 12.0)
        assert score > 80

    def test_low_everything_low_score(self):
        score = compute_risk_score(1e-7, 4.5, 0.5)
        assert score < 20

    def test_score_bounded_0_100(self):
        score = compute_risk_score(1.0, 0.0, 15.0)
        assert 0 <= score <= 100

    def test_none_pc_high_miss_still_scores(self):
        score = compute_risk_score(None, 0.2, 10.0)
        assert score > 0

    def test_none_pc_far_miss_low_speed_low_score(self):
        score = compute_risk_score(None, 4.8, 0.1)
        assert score < 30


# ---------------------------------------------------------------------------
# format_pc
# ---------------------------------------------------------------------------

class TestFormatPc:
    def test_none_returns_na(self):
        assert format_pc(None) == "N/A"

    def test_zero_returns_placeholder(self):
        result = format_pc(0.0)
        assert "10" in result

    def test_high_pc_contains_exponent(self):
        result = format_pc(2.3e-4)
        assert "10" in result
        assert "⁻" in result

    def test_format_pc_low(self):
        result = format_pc(8.7e-7)
        assert "10" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_superscript_negative(self):
        result = superscript(-4)
        assert "⁻" in result and "⁴" in result

    def test_risk_css_critical(self):
        assert risk_css_class("CRITICAL") == "risk-critical"

    def test_risk_css_unknown_defaults_low(self):
        assert risk_css_class("UNKNOWN") == "risk-low"

    def test_object_type_label_payload(self):
        assert object_type_label("PAYLOAD") == "Active Payload"

    def test_object_type_label_debris(self):
        assert object_type_label("DEBRIS") == "Debris"

    def test_object_type_label_unknown_passthrough(self):
        assert object_type_label("MYSTERY") == "MYSTERY"
