"""Database session/dependency management.

Creates a SQLAlchemy engine bound to either PostgreSQL (with pgvector, when a
reachable server is configured) or SQLite (zero-infrastructure fallback). The
rest of the application is written against this abstraction and never cares
which backend is active.
"""
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

logger = logging.getLogger("revenova.db")

Base = declarative_base()

_is_postgres = False


def _probe_postgres() -> bool:
    """Return True if we should (and can) use PostgreSQL."""
    if not settings.use_postgres:
        logger.info("USE_POSTGRES not set -> using SQLite fallback")
        return False
    try:
        engine = create_engine(
            settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3}
        )
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        engine.dispose()
        logger.info("PostgreSQL reachable -> PostgreSQL backend")
        return True
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("PostgreSQL unavailable (%s) -> using SQLite fallback", exc)
        return False


def _build_engine():
    global _is_postgres
    if _probe_postgres():
        _is_postgres = True
        connect_args = {}
        return create_engine(settings.database_url, pool_pre_ping=True)
    _is_postgres = False
    engine = create_engine(f"sqlite:///{settings.sqlite_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_sqlite_pragma(dbapi_conn, record):  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def is_postgres() -> bool:
    return _is_postgres


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (and pgvector extension when on PostgreSQL)."""
    if _is_postgres:
        try:
            import pgvector.sqlalchemy
            from sqlalchemy import text

            with engine.connect() as conn:
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
        except Exception as exc:  # pragma: no cover
            logger.warning("pgvector unavailable (%s); continuing without vector ops", exc)
    from app import models  # noqa: F401  ensure models are imported/registered
    Base.metadata.create_all(bind=engine)
