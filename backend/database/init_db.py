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


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
