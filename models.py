from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Conjunction(Base):
    __tablename__ = "conjunctions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source identifier (CDM_ID from Space-Track, or "DEMO-xxx")
    cdm_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Object 1
    sat1_norad: Mapped[str] = mapped_column(String(10))
    sat1_name: Mapped[str] = mapped_column(String(128))
    sat1_type: Mapped[str] = mapped_column(String(32))  # PAYLOAD / DEBRIS / ROCKET BODY
    sat1_tle1: Mapped[str] = mapped_column(String(70))
    sat1_tle2: Mapped[str] = mapped_column(String(70))

    # Object 2
    sat2_norad: Mapped[str] = mapped_column(String(10))
    sat2_name: Mapped[str] = mapped_column(String(128))
    sat2_type: Mapped[str] = mapped_column(String(32))
    sat2_tle1: Mapped[str] = mapped_column(String(70))
    sat2_tle2: Mapped[str] = mapped_column(String(70))

    # Conjunction geometry
    tca: Mapped[datetime] = mapped_column(DateTime)           # Time of Closest Approach (UTC)
    miss_distance_km: Mapped[float] = mapped_column(Float)    # km
    relative_speed_km_s: Mapped[float] = mapped_column(Float) # km/s
    pc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Probability of Collision

    # Risk assessment (computed by risk_engine.py)
    risk_level: Mapped[str] = mapped_column(String(16))  # LOW / MEDIUM / HIGH / CRITICAL
    risk_score: Mapped[float] = mapped_column(Float)     # 0–100

    # Cached Plotly figure JSON (generated on first conjunction view)
    orbital_plot_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Generated SDA brief (JSON)
    brief_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
