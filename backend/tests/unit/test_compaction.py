"""Unit tests for conversation memory compaction."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from flow.memory.compaction import compact_if_needed, COMPACTION_THRESHOLD, MESSAGES_TO_KEEP


def make_messages(n: int):
    msgs = []
    for i in range(n):
        msgs.append(HumanMessage(content=f"User msg {i}"))
        msgs.append(AIMessage(content=f"AI msg {i}"))
    return msgs[:n]


@pytest.mark.asyncio
async def test_below_threshold_unchanged():
    msgs = make_messages(COMPACTION_THRESHOLD - 1)
    result = await compact_if_needed(msgs)
    assert result == msgs


@pytest.mark.asyncio
async def test_at_threshold_unchanged():
    msgs = make_messages(COMPACTION_THRESHOLD)
    result = await compact_if_needed(msgs)
    assert result == msgs


@pytest.mark.asyncio
async def test_above_threshold_compacts():
    msgs = make_messages(COMPACTION_THRESHOLD + 5)
    summary_msg = MagicMock()
    summary_msg.content = "Summary of earlier conversation."
    with patch("flow.memory.compaction.model") as mock_model:
        mock_model.ainvoke = AsyncMock(return_value=summary_msg)
        result = await compact_if_needed(msgs)
    # Result should be shorter than input
    assert len(result) < len(msgs)


@pytest.mark.asyncio
async def test_compacted_result_starts_with_system_message():
    msgs = make_messages(COMPACTION_THRESHOLD + 5)
    summary_msg = MagicMock()
    summary_msg.content = "Earlier conversation summary."
    with patch("flow.memory.compaction.model") as mock_model:
        mock_model.ainvoke = AsyncMock(return_value=summary_msg)
        result = await compact_if_needed(msgs)
    assert isinstance(result[0], SystemMessage)
    assert "summary" in result[0].content.lower() or "Earlier" in result[0].content


@pytest.mark.asyncio
async def test_keeps_last_n_messages_verbatim():
    msgs = make_messages(COMPACTION_THRESHOLD + 5)
    last_n = msgs[-MESSAGES_TO_KEEP:]
    summary_msg = MagicMock()
    summary_msg.content = "Summary."
    with patch("flow.memory.compaction.model") as mock_model:
        mock_model.ainvoke = AsyncMock(return_value=summary_msg)
        result = await compact_if_needed(msgs)
    # The last MESSAGES_TO_KEEP messages should appear at the end
    assert result[-MESSAGES_TO_KEEP:] == last_n
