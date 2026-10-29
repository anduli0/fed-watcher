import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.database.models import Base


def _build_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres://"):          # Railway gives postgres://, SQLAlchemy needs postgresql+asyncpg://
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url or "sqlite+aiosqlite:///fed_watcher.db"


DATABASE_URL = _build_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    **({} if _is_sqlite else {"pool_size": 5, "max_overflow": 10}),
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


_HORIZON_FORECAST_NEW_COLS = {
    "meeting_date": "VARCHAR(10)",
    "horizon_kind": "VARCHAR(8)",
    "is_primary": "BOOLEAN DEFAULT 0" ,
}


async def _migrate(conn):
    """Additive schema changes create_all cannot apply to an existing table."""
    from sqlalchemy import text, inspect

    def existing_cols(sync_conn):
        insp = inspect(sync_conn)
        if "horizon_forecast" not in insp.get_table_names():
            return None
        return {c["name"] for c in insp.get_columns("horizon_forecast")}

    cols = await conn.run_sync(existing_cols)
    if cols is None:
        return
    added = False
    for name, ddl in _HORIZON_FORECAST_NEW_COLS.items():
        if name in cols:
            continue
        if not _is_sqlite:
            ddl = ddl.replace("DEFAULT 0", "DEFAULT FALSE")
        await conn.execute(text(f"ALTER TABLE horizon_forecast ADD COLUMN {name} {ddl}"))
        added = True
    if not _is_sqlite and added:
        # legacy column was VARCHAR(5); FOMC keys are ISO dates
        await conn.execute(text("ALTER TABLE horizon_forecast ALTER COLUMN horizon TYPE VARCHAR(12)"))
    if added:
        # Legacy fixed-offset rows: the old 12m call was the headline → keep the
        # track record continuous; tag the rest so the active set ignores them.
        await conn.execute(text(
            "UPDATE horizon_forecast SET horizon_kind = 'legacy' WHERE horizon_kind IS NULL "
            "AND horizon IN ('6m','12m','3y','10y')"))
        true_lit = "1" if _is_sqlite else "TRUE"
        await conn.execute(text(
            f"UPDATE horizon_forecast SET is_primary = {true_lit} WHERE horizon = '12m'"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
