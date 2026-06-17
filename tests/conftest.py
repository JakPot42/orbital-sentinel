import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from main import app
from models import Conjunction
from seed_data import load_seed_data

# ---------------------------------------------------------------------------
# In-memory test database
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db(test_engine):
    with Session(test_engine) as session:
        yield session
        session.rollback()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Reusable seed TLEs (valid format with correct checksums)
# ---------------------------------------------------------------------------

def _tle_checksum(line68: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10


def _tle(base: str) -> str:
    return base + str(_tle_checksum(base))


@pytest.fixture
def iss_tle():
    l1 = _tle("1 25544U 98067A   24001.50000000  .00006393  00000-0  11839-3 0  999")
    l2 = _tle("2 25544  51.6421 283.3014 0001200  71.3516 329.6482 15.49557865 4285")
    return l1, l2


@pytest.fixture
def debris_tle():
    l1 = _tle("1 22285U 92093B   24001.50000000  .00000213  00000-0  48900-4 0  999")
    l2 = _tle("2 22285  51.6150 281.1240 0012340  85.2120 274.9810 15.49124231 1672")
    return l1, l2


@pytest.fixture
def demo_conjunction(db, iss_tle, debris_tle):
    from datetime import datetime, timedelta, timezone
    from risk_engine import categorize_pc, compute_risk_score

    l1_a, l2_a = iss_tle
    l1_b, l2_b = debris_tle
    tca = datetime.now(timezone.utc) + timedelta(hours=24)
    pc = 2.3e-4

    conj = Conjunction(
        cdm_id="TEST-001",
        sat1_norad="25544", sat1_name="ISS (ZARYA)", sat1_type="PAYLOAD",
        sat1_tle1=l1_a, sat1_tle2=l2_a,
        sat2_norad="22285", sat2_name="SL-16 R/B DEB", sat2_type="DEBRIS",
        sat2_tle1=l1_b, sat2_tle2=l2_b,
        tca=tca, miss_distance_km=0.287, relative_speed_km_s=7.8,
        pc=pc,
        risk_level=categorize_pc(pc, 0.287),
        risk_score=compute_risk_score(pc, 0.287, 7.8),
        is_demo=True,
    )
    db.add(conj)
    db.commit()
    yield conj
    db.delete(conj)
    db.commit()
