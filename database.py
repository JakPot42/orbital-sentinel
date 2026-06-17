from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session

DATABASE_URL = "sqlite:///./orbital_sentinel.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from models import Conjunction  # noqa: F401 — needed for metadata
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    return Session(engine)
