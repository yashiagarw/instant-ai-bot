"""Database engine, session factory and the declarative base for models."""

from collections.abc import Iterator
from datetime import datetime
from enum import StrEnum

from fastapi import Request
from sqlalchemy import DateTime, Engine, Enum, MetaData, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

# Deterministic constraint names, so Alembic migrations are stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Text column limited to the enum's values by a CHECK constraint named ck_<table>_<name>."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=max(len(m.value) for m in enum_cls),
        values_callable=lambda e: [m.value for m in e],
    )


def make_engine(database_url: str, connect_timeout: int = 3) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": connect_timeout},
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with request.app.state.session_factory() as session:
        yield session


def database_is_up(engine: Engine) -> bool:
    """True when a trivial query succeeds. Never raises."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
