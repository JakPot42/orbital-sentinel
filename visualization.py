"""
3D orbital visualization using Plotly.

Generates a Plotly figure (serialized to JSON) showing:
  - Earth as a textured sphere
  - Orbital track for Object 1 (blue)
  - Orbital track for Object 2 (red/orange)
  - TCA position markers (pulsing spheres at closest-approach points)
  - Conjunction line (dashed) between the two objects at TCA
  - Legend + annotations

The figure JSON is rendered client-side via the plotly.js CDN in the template.
No kaleido dependency — PDF reports use text/tables only.
"""

import json
from datetime import datetime, timezone

import numpy as np
import plotly.graph_objects as go

from sgp4_propagator import generate_orbital_track, position_at
from config import EARTH_RADIUS_KM, ORBITAL_TRACK_POINTS, ORBITAL_TRACKS_PERIODS


# ---------------------------------------------------------------------------
# Earth sphere
# ---------------------------------------------------------------------------

def _earth_sphere() -> go.Surface:
    u = np.linspace(0, 2 * np.pi, 80)
    v = np.linspace(0, np.pi, 40)
    R = EARTH_RADIUS_KM
    x = R * np.outer(np.cos(u), np.sin(v))
    y = R * np.outer(np.sin(u), np.sin(v))
    z = R * np.outer(np.ones(len(u)), np.cos(v))
    return go.Surface(
        x=x, y=y, z=z,
        colorscale=[[0, "#0d2137"], [0.4, "#1a3c5e"], [1, "#2d6a9f"]],
        showscale=False,
        opacity=0.85,
        hoverinfo="skip",
        name="Earth",
    )


# ---------------------------------------------------------------------------
# Orbital track
# ---------------------------------------------------------------------------

def _orbit_trace(track: dict, name: str, color: str) -> go.Scatter3d | None:
    if track.get("error"):
        return None
    return go.Scatter3d(
        x=track["x"], y=track["y"], z=track["z"],
        mode="lines",
        name=name,
        line=dict(color=color, width=2),
        hovertemplate=(
            f"<b>{name}</b><br>"
            f"Alt: {track['altitude_km']:.0f} km<br>"
            f"Period: {track['period_min']:.1f} min<extra></extra>"
        ),
    )


# ---------------------------------------------------------------------------
# TCA marker
# ---------------------------------------------------------------------------

def _tca_marker(pos: np.ndarray | None, name: str, color: str, symbol: str = "diamond") -> go.Scatter3d | None:
    if pos is None:
        return None
    return go.Scatter3d(
        x=[float(pos[0])], y=[float(pos[1])], z=[float(pos[2])],
        mode="markers",
        name=f"{name} @ TCA",
        marker=dict(size=8, color=color, symbol=symbol,
                    line=dict(color="white", width=1)),
        hovertemplate=f"<b>{name}</b><br>Position at TCA<extra></extra>",
    )


# ---------------------------------------------------------------------------
# Conjunction line
# ---------------------------------------------------------------------------

def _conjunction_line(pos1: np.ndarray | None, pos2: np.ndarray | None,
                      miss_km: float) -> go.Scatter3d | None:
    if pos1 is None or pos2 is None:
        return None
    return go.Scatter3d(
        x=[float(pos1[0]), float(pos2[0])],
        y=[float(pos1[1]), float(pos2[1])],
        z=[float(pos1[2]), float(pos2[2])],
        mode="lines+text",
        name=f"Miss distance: {miss_km*1000:.0f} m",
        line=dict(color="yellow", width=3, dash="dash"),
        text=["", f"{miss_km*1000:.0f} m"],
        textposition="top center",
        textfont=dict(color="yellow", size=12),
        hovertemplate=f"Miss distance: {miss_km*1000:.0f} m<extra></extra>",
    )


# ---------------------------------------------------------------------------
# Main figure builder
# ---------------------------------------------------------------------------

def build_orbital_figure(
    sat1_name: str, sat1_tle1: str, sat1_tle2: str,
    sat2_name: str, sat2_tle1: str, sat2_tle2: str,
    tca: datetime,
    miss_distance_km: float,
    risk_level: str,
) -> str:
    """
    Build the 3D orbital visualization and return Plotly figure JSON.
    Gracefully degrades if sgp4 propagation fails for either object.
    """
    now = datetime.now(timezone.utc)

    # Generate orbital tracks (1.5 periods each, starting from now)
    track1 = generate_orbital_track(sat1_tle1, sat1_tle2, now,
                                    n_points=ORBITAL_TRACK_POINTS,
                                    n_periods=ORBITAL_TRACKS_PERIODS)
    track2 = generate_orbital_track(sat2_tle1, sat2_tle2, now,
                                    n_points=ORBITAL_TRACK_POINTS,
                                    n_periods=ORBITAL_TRACKS_PERIODS)

    # Position at TCA for conjunction geometry
    pos1_tca = position_at(sat1_tle1, sat1_tle2, tca)
    pos2_tca = position_at(sat2_tle1, sat2_tle2, tca)

    # Assemble traces
    traces: list = [_earth_sphere()]

    color1 = "#4fc3f7"   # light blue for Object 1
    color2 = {
        "CRITICAL": "#ff1744",
        "HIGH": "#ff5722",
        "MEDIUM": "#ffc107",
        "LOW": "#66bb6a",
    }.get(risk_level, "#ff5722")

    t1 = _orbit_trace(track1, sat1_name, color1)
    t2 = _orbit_trace(track2, sat2_name, color2)
    m1 = _tca_marker(pos1_tca, sat1_name, color1)
    m2 = _tca_marker(pos2_tca, sat2_name, color2, symbol="diamond")
    cline = _conjunction_line(pos1_tca, pos2_tca, miss_distance_km)

    for trace in [t1, t2, m1, m2, cline]:
        if trace is not None:
            traces.append(trace)

    # TCA annotation
    tca_str = tca.strftime("%Y-%m-%d %H:%M UTC") if tca.tzinfo else tca.strftime("%Y-%m-%d %H:%M UTC")
    risk_color = {"CRITICAL": "#ff1744", "HIGH": "#ff5722",
                  "MEDIUM": "#ffc107", "LOW": "#66bb6a"}.get(risk_level, "#ff5722")

    fig = go.Figure(data=traces)
    fig.update_layout(
        paper_bgcolor="#0a1628",
        plot_bgcolor="#0a1628",
        scene=dict(
            bgcolor="#0a1628",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            zaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            aspectmode="data",
            camera=dict(eye=dict(x=1.4, y=1.4, z=0.8)),
        ),
        legend=dict(
            bgcolor="rgba(10,22,40,0.85)",
            bordercolor="#2d6a9f",
            borderwidth=1,
            font=dict(color="white", size=11),
            x=0.01, y=0.99,
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        title=dict(
            text=(
                f"<b>{sat1_name}</b> × <b>{sat2_name}</b>"
                f"  |  TCA: {tca_str}"
                f"  |  Miss: {miss_distance_km*1000:.0f} m"
                f"  |  <span style='color:{risk_color}'>{risk_level}</span>"
            ),
            font=dict(color="white", size=14),
            x=0.5, xanchor="center",
        ),
        height=600,
    )

    return fig.to_json()


def build_orbital_figure_for_conjunction(conjunction) -> str:
    """Convenience wrapper that takes a Conjunction ORM object."""
    return build_orbital_figure(
        sat1_name=conjunction.sat1_name,
        sat1_tle1=conjunction.sat1_tle1,
        sat1_tle2=conjunction.sat1_tle2,
        sat2_name=conjunction.sat2_name,
        sat2_tle1=conjunction.sat2_tle1,
        sat2_tle2=conjunction.sat2_tle2,
        tca=conjunction.tca,
        miss_distance_km=conjunction.miss_distance_km,
        risk_level=conjunction.risk_level,
    )
