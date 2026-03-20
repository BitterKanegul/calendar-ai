"""
Email Index Manager

Handles incremental and full reindexing of emails into the vector store.

Incremental refresh:
  - Tracks last-indexed timestamp in Redis (key: gmail_last_indexed:{user_id})
  - Skips emails whose email_id is already in the vector store
  - Rate-limited: at most once per EMAIL_INDEX_REFRESH_MINUTES per user

Full reindex:
  - Fetches emails from the last N days
  - Used on first-time setup or after a reset
"""
import logging
from datetime import datetime, timedelta, timezone

import redis as redis_sync

from config import settings
from .embeddings import EmailVectorStore

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "gmail_last_indexed"


def _get_redis() -> redis_sync.Redis:
    return redis_sync.from_url(settings.REDIS_URL, decode_responses=True)


def _last_indexed_key(user_id: int) -> str:
    return f"{REDIS_KEY_PREFIX}:{user_id}"


def _get_last_indexed(user_id: int) -> datetime | None:
    try:
        r = _get_redis()
        val = r.get(_last_indexed_key(user_id))
        if val:
            return datetime.fromisoformat(val)
    except Exception:
        pass
    return None


def _set_last_indexed(user_id: int, dt: datetime) -> None:
    try:
        r = _get_redis()
        r.set(_last_indexed_key(user_id), dt.isoformat())
    except Exception as e:
        logger.warning(f"Failed to update last-indexed time for user {user_id}: {e}")


def _should_refresh(user_id: int) -> bool:
    """Return True if enough time has passed since the last refresh."""
    last = _get_last_indexed(user_id)
    if last is None:
        return True
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=settings.EMAIL_INDEX_REFRESH_MINUTES)
    return last.replace(tzinfo=timezone.utc) < cutoff


async def refresh_email_index(
    store: EmailVectorStore,
    user_id: int,
    call_email_tool,           # injected to avoid circular imports
    force: bool = False,
) -> int:
    """
    Incrementally index emails newer than the last refresh.

    Only runs if enough time has passed (rate limiting), unless force=True.
    Returns number of new chunks added.
    """
    if not force and not _should_refresh(user_id):
        logger.debug(f"Skipping email refresh for user {user_id} — too recent")
        return 0

    already_indexed = store.get_indexed_email_ids()

    # Fetch recent emails (last 7 days as a rolling window)
    since = (datetime.now(tz=timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        summaries = await call_email_tool("search_emails", {
            "user_id":          user_id,
            "query":            "",
            "date_range_start": since,
            "max_results":      50,
        }) or []
    except Exception as e:
        logger.warning(f"Email search failed during index refresh for user {user_id}: {e}")
        return 0

    # Only fetch full content for emails not yet indexed
    new_emails: list[dict] = []
    for summary in summaries:
        email_id = summary.get("email_id", "")
        if email_id and email_id not in already_indexed:
            try:
                full = await call_email_tool("get_email_content", {
                    "email_id": email_id,
                    "user_id":  user_id,
                })
                if full:
                    new_emails.append(full)
            except Exception as e:
                logger.warning(f"Failed to fetch email {email_id}: {e}")

    if not new_emails:
        _set_last_indexed(user_id, datetime.now(tz=timezone.utc))
        return 0

    chunks_added = store.ingest_emails(new_emails)
    _set_last_indexed(user_id, datetime.now(tz=timezone.utc))
    logger.info(f"Email index refreshed for user {user_id}: {chunks_added} new chunks from {len(new_emails)} emails")
    return chunks_added


async def full_reindex(
    store: EmailVectorStore,
    user_id: int,
    call_email_tool,
    days_back: int = 30,
) -> int:
    """
    Full reindex from scratch for the last `days_back` days.
    Used on first-time setup.
    """
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        summaries = await call_email_tool("search_emails", {
            "user_id":          user_id,
            "query":            "",
            "date_range_start": since,
            "max_results":      200,
        }) or []
    except Exception as e:
        logger.error(f"Full reindex search failed for user {user_id}: {e}")
        return 0

    full_emails: list[dict] = []
    for summary in summaries:
        email_id = summary.get("email_id", "")
        if not email_id:
            continue
        try:
            full = await call_email_tool("get_email_content", {
                "email_id": email_id,
                "user_id":  user_id,
            })
            if full:
                full_emails.append(full)
        except Exception as e:
            logger.warning(f"Failed to fetch email {email_id}: {e}")

    chunks_added = store.ingest_emails(full_emails)
    _set_last_indexed(user_id, datetime.now(tz=timezone.utc))
    logger.info(f"Full reindex complete for user {user_id}: {chunks_added} chunks from {len(full_emails)} emails")
    return chunks_added
