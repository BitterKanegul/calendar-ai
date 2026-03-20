"""
Migration: Add priority, flexibility, and category columns to the events table.

Run with:
    cd backend && python -m database.migrate_add_event_metadata
"""
import asyncio
import logging
from sqlalchemy import text
from database.config import async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    async with async_engine.begin() as conn:
        logger.info("Adding priority column...")
        await conn.execute(text("""
            ALTER TABLE events
            ADD COLUMN IF NOT EXISTS priority VARCHAR(20)
                NOT NULL DEFAULT 'optional'
                CHECK (priority IN ('mandatory', 'optional'));
        """))

        logger.info("Adding flexibility column...")
        await conn.execute(text("""
            ALTER TABLE events
            ADD COLUMN IF NOT EXISTS flexibility VARCHAR(20)
                NOT NULL DEFAULT 'movable'
                CHECK (flexibility IN ('fixed', 'movable'));
        """))

        logger.info("Adding category column...")
        await conn.execute(text("""
            ALTER TABLE events
            ADD COLUMN IF NOT EXISTS category VARCHAR(20)
                NOT NULL DEFAULT 'personal'
                CHECK (category IN ('work', 'study', 'personal', 'leisure'));
        """))

        logger.info("Backfilling existing rows with defaults...")
        await conn.execute(text("""
            UPDATE events
            SET
                priority   = 'optional',
                flexibility = 'movable',
                category   = 'personal'
            WHERE priority IS NULL OR flexibility IS NULL OR category IS NULL;
        """))

    logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
