"""
Integration tests — MessagesOnlyRedisSaver checkpointer.

Requires: pytest -m integration  (Redis must be running on localhost:6379)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

pytestmark = pytest.mark.integration

TEST_THREAD_ID = "test-thread-integration"


def _make_config(thread_id: str = TEST_THREAD_ID):
    return {"configurable": {"thread_id": thread_id}}


def _make_checkpoint(channel_values: dict, channel_versions: dict | None = None):
    return {
        "v": 1,
        "id": "chk-001",
        "ts": "2026-03-20T10:00:00Z",
        "channel_values": channel_values,
        "channel_versions": channel_versions or {},
        "versions_seen": {},
        "pending_sends": [],
    }


@pytest.fixture
async def checkpointer():
    """Real MessagesOnlyRedisSaver connected to local Redis."""
    from flow.redis_checkpointer import MessagesOnlyRedisSaver

    redis_url = "redis://localhost:6379/15"  # DB index 15 for tests
    async with MessagesOnlyRedisSaver.from_conn_string(redis_url) as saver:
        await saver.asetup()
        yield saver
        # Flush test keys
        await saver.redis.flushdb()


async def test_aput_filters_non_message_fields(checkpointer):
    """aput must strip non-message fields (e.g. events, route) before saving."""
    config = _make_config("filter-test")
    checkpoint = _make_checkpoint(
        channel_values={
            "router_messages": [HumanMessage(content="Hello")],
            "events": [{"id": "evt-1"}],        # should be stripped
            "route": {"route": "create"},        # should be stripped
            "is_success": True,                  # should be stripped
        },
        channel_versions={"router_messages": 1, "events": 1},
    )
    metadata = {"source": "loop", "step": 1, "writes": {}}
    new_versions = {"router_messages": 1, "events": 1}

    returned_config = await checkpointer.aput(config, checkpoint, metadata, new_versions)
    assert returned_config is not None

    # Retrieve and verify only message fields survived
    result = await checkpointer.aget(config)
    if result:
        channel_values = result.get("channel_values", {})
        assert "router_messages" in channel_values or len(channel_values) == 0
        assert "events" not in channel_values
        assert "route" not in channel_values


async def test_roundtrip_messages(checkpointer):
    """aput → aget preserves router_messages content."""
    config = _make_config("roundtrip-test")
    messages = [
        SystemMessage(content="You are a calendar assistant."),
        HumanMessage(content="Schedule a meeting"),
        AIMessage(content='{"route": "create"}'),
    ]
    checkpoint = _make_checkpoint(
        channel_values={"router_messages": messages},
        channel_versions={"router_messages": 3},
    )
    metadata = {"source": "loop", "step": 3, "writes": {}}

    await checkpointer.aput(config, checkpoint, metadata, {"router_messages": 3})

    result = await checkpointer.aget(config)
    assert result is not None
    saved_messages = result.get("channel_values", {}).get("router_messages", [])
    assert len(saved_messages) == 3


async def test_confirmation_state_persisted(checkpointer):
    """awaiting_confirmation and confirmation_type survive an aput/aget cycle."""
    config = _make_config("confirm-test")
    checkpoint = _make_checkpoint(
        channel_values={
            "router_messages": [],
            "awaiting_confirmation": True,
            "confirmation_type": "delete_safety",
            "confirmation_data": {"event_ids": ["evt-abc"]},
        },
        channel_versions={
            "router_messages": 1,
            "awaiting_confirmation": 1,
            "confirmation_type": 1,
            "confirmation_data": 1,
        },
    )
    metadata = {"source": "loop", "step": 2, "writes": {}}
    new_versions = {
        "router_messages": 1,
        "awaiting_confirmation": 1,
        "confirmation_type": 1,
        "confirmation_data": 1,
    }

    await checkpointer.aput(config, checkpoint, metadata, new_versions)

    result = await checkpointer.aget(config)
    assert result is not None
    cv = result.get("channel_values", {})
    assert cv.get("awaiting_confirmation") is True
    assert cv.get("confirmation_type") == "delete_safety"
