"""
E2E tests — Full calendar assistant flow via POST /assistant/.

Each test sends natural language and validates the response shape.
Requires: pytest -m e2e  (live OpenAI API key needed)
"""

import pytest

pytestmark = pytest.mark.e2e

# Shared state between sequential tests (within the same session)
_created_event_title: str | None = None


async def test_create_event_via_assistant(client, auth_headers, assistant_payload):
    """
    Input: 'Schedule a team meeting tomorrow at 2pm for 1 hour'
    Assert: response.type == 'create', response.events non-empty,
            events[0].title contains 'meeting'
    """
    global _created_event_title

    resp = await client.post(
        "/assistant/",
        json=assistant_payload("Schedule a team meeting tomorrow at 2pm for 1 hour"),
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("type") == "create"
    events = data.get("events", [])
    assert len(events) > 0

    title = events[0].get("title", "")
    assert "meeting" in title.lower() or "team" in title.lower()
    _created_event_title = title


async def test_list_events_via_assistant(client, auth_headers, assistant_payload):
    """
    Prereq: event created in test_create_event_via_assistant.
    Input: 'What's on my calendar tomorrow?'
    Assert: response.type == 'list', response.events is non-empty
    """
    resp = await client.post(
        "/assistant/",
        json=assistant_payload("What's on my calendar tomorrow?"),
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("type") == "list"
    events = data.get("events", [])
    assert isinstance(events, list)
    # There should be at least the event we created
    assert len(events) >= 1


async def test_update_event_via_assistant(client, auth_headers, assistant_payload):
    """
    Input: 'Move the team meeting to 4pm'
    Assert: response.type in ('update', 'confirmation_required')
    If confirmation_required: send 'yes', verify follow-up succeeds.
    """
    resp = await client.post(
        "/assistant/",
        json=assistant_payload("Move the team meeting to 4pm"),
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("type") in ("update", "confirmation_required")

    if data.get("type") == "confirmation_required":
        # Confirm the update
        confirm_resp = await client.post(
            "/assistant/",
            json=assistant_payload("yes"),
            headers=auth_headers,
        )
        assert confirm_resp.status_code == 200
        confirm_data = confirm_resp.json()
        # After confirming, should be an update success or a message
        assert confirm_data.get("type") in ("update", "message")


async def test_delete_event_via_assistant(client, auth_headers, assistant_payload):
    """
    Input: 'Cancel the team meeting tomorrow'
    Assert: response.type == 'confirmation_required' (safety gate)
    Then: send 'yes', verify deletion confirmed.
    """
    resp = await client.post(
        "/assistant/",
        json=assistant_payload("Cancel the team meeting tomorrow"),
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    # Safety gate should fire for delete
    assert data.get("type") == "confirmation_required"
    assert data.get("confirmation_type") in ("delete_safety", None)

    # Confirm the deletion
    confirm_resp = await client.post(
        "/assistant/",
        json=assistant_payload("yes"),
        headers=auth_headers,
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data.get("type") in ("delete", "message")


async def test_general_message_via_assistant(client, auth_headers, assistant_payload):
    """
    Input: 'Hello, how are you?'
    Assert: response has a message field, type is 'message', no events/actions.
    """
    resp = await client.post(
        "/assistant/",
        json=assistant_payload("Hello, how are you?"),
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    # Should be a general message response
    assert data.get("type") == "message" or "message" in data
    # Should not contain calendar events
    assert not data.get("events")
