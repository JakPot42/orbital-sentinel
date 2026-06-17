"""
Tests for the 3D orbital visualization module.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from visualization import build_orbital_figure


def _tle_checksum(line68: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10

def _tle(base: str) -> str:
    return base + str(_tle_checksum(base))

ISS_L1 = _tle("1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999")
ISS_L2 = _tle("2 25544  51.6421 283.3014 0001200  71.3516 329.6482 15.49557865 4285")
DEB_L1 = _tle("1 22285U 92093B   24001.50000000  .00000213  00000-0  48900-4 0  999")
DEB_L2 = _tle("2 22285  51.6150 281.1240 0012340  85.2120 274.9810 15.49124231 1672")


@pytest.fixture
def tca():
    return datetime.now(timezone.utc) + timedelta(hours=24)


@pytest.fixture
def figure_json(tca):
    return build_orbital_figure(
        sat1_name="ISS (ZARYA)", sat1_tle1=ISS_L1, sat1_tle2=ISS_L2,
        sat2_name="SL-16 R/B DEB", sat2_tle1=DEB_L1, sat2_tle2=DEB_L2,
        tca=tca, miss_distance_km=0.287, risk_level="HIGH",
    )


class TestBuildOrbitalFigure:
    def test_returns_string(self, figure_json):
        assert isinstance(figure_json, str)

    def test_valid_json(self, figure_json):
        parsed = json.loads(figure_json)
        assert isinstance(parsed, dict)

    def test_has_data_key(self, figure_json):
        parsed = json.loads(figure_json)
        assert "data" in parsed

    def test_has_layout_key(self, figure_json):
        parsed = json.loads(figure_json)
        assert "layout" in parsed

    def test_has_multiple_traces(self, figure_json):
        parsed = json.loads(figure_json)
        # Earth + at least 2 orbit traces
        assert len(parsed["data"]) >= 3

    def test_earth_surface_present(self, figure_json):
        parsed = json.loads(figure_json)
        types = [t.get("type") for t in parsed["data"]]
        assert "surface" in types

    def test_scatter3d_traces_present(self, figure_json):
        parsed = json.loads(figure_json)
        types = [t.get("type") for t in parsed["data"]]
        assert "scatter3d" in types

    def test_title_contains_sat_names(self, figure_json):
        assert "ISS" in figure_json
        assert "SL-16" in figure_json

    def test_risk_level_in_title(self, figure_json):
        assert "HIGH" in figure_json

    def test_scene_has_3d_axes(self, figure_json):
        parsed = json.loads(figure_json)
        scene = parsed["layout"].get("scene", {})
        assert "xaxis" in scene
        assert "yaxis" in scene
        assert "zaxis" in scene

    def test_critical_risk_uses_red_color(self, tca):
        fig_json = build_orbital_figure(
            sat1_name="A", sat1_tle1=ISS_L1, sat1_tle2=ISS_L2,
            sat2_name="B", sat2_tle1=DEB_L1, sat2_tle2=DEB_L2,
            tca=tca, miss_distance_km=0.1, risk_level="CRITICAL",
        )
        assert "#ff1744" in fig_json

    def test_low_risk_uses_green_color(self, tca):
        fig_json = build_orbital_figure(
            sat1_name="A", sat1_tle1=ISS_L1, sat1_tle2=ISS_L2,
            sat2_name="B", sat2_tle1=DEB_L1, sat2_tle2=DEB_L2,
            tca=tca, miss_distance_km=4.0, risk_level="LOW",
        )
        assert "#66bb6a" in fig_json

    def test_miss_distance_shown_in_meters(self, figure_json):
        # 0.287 km = 287 m — should appear in conjunction line label
        assert "287" in figure_json
