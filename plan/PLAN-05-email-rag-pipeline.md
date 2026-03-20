# PLAN-05: Email Retrieval Pipeline (RAG)

## Goal

Build a RAG-powered email retrieval pipeline that ingests user emails via a Gmail MCP Server, indexes them in a vector store, performs semantic search to find scheduling-relevant content, and extracts structured event data with confidence-based handling.

---

## Current State

- No email integration exists
- No vector store, no embeddings, no RAG pipeline
- No Gmail API credentials or OAuth2 setup
- The proposal requires both an Email MCP Server and a full RAG pipeline with ingestion, embedding, retrieval, and extraction stages

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Email RAG Pipeline                     │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ Email    │    │ Chunker  │    │ Vector Store     │   │
│  │ MCP      │───▸│ +        │───▸│ (ChromaDB)       │   │
│  │ Server   │    │ Embedder │    │                  │   │
│  └──────────┘    └──────────┘    └────────┬─────────┘   │
│       │                                    │             │
│       │          ┌──────────┐    ┌────────▼─────────┐   │
│       │          │ Event    │◂───│ Semantic Search   │   │
│       │          │ Extractor│    │ (query → top-k)   │   │
│       │          └────┬─────┘    └──────────────────┘   │
│       │               │                                  │
│       │          ┌────▼───────────────┐                  │
│       │          │ Confidence Scoring │                  │
│       │          │ + Event Proposals  │                  │
│       │          └────────────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Add dependencies

**File: `backend/requirements.txt`**

```
# Email RAG Pipeline
chromadb>=0.4.22
sentence-transformers>=2.2.2
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.1.1
beautifulsoup4>=4.12.0
```

### Step 2: Gmail OAuth2 setup

**New file: `backend/mcp_servers/email_auth.py`**

```python
"""Gmail OAuth2 authentication helper."""
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

async def get_gmail_credentials(user_id: int) -> Credentials:
    """
    Get or refresh Gmail credentials for a user.

    Credentials are stored per-user. On first use, the user must
    complete an OAuth2 consent flow. After that, refresh tokens
    handle re-authentication.

    Storage: credentials stored in the database (encrypted) or
    on filesystem during development.
    """
```

**Environment variables to add:**
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

**New file: `backend/controller/google_auth_controller.py`**

Add OAuth2 callback endpoint:
```python
@router.get("/auth/google/callback")
async def google_callback(code: str):
    """Handle Google OAuth2 callback, store credentials."""
```

### Step 3: Build the Email MCP Server

**New file: `backend/mcp_servers/email_server.py`**

```python
from fastmcp import FastMCP

mcp = FastMCP("Email")

@mcp.tool()
async def search_emails(
    query: str,
    user_id: int,
    date_range_start: str = None,
    date_range_end: str = None,
    sender: str = None,
    max_results: int = 20
) -> list[dict]:
    """
    Search user's Gmail inbox.

    Returns list of email summaries:
    [{"email_id": str, "subject": str, "sender": str,
      "date": str, "snippet": str}]
    """
    # Use Gmail API: service.users().messages().list(q=query)
    ...

@mcp.tool()
async def get_email_content(email_id: str, user_id: int) -> dict:
    """
    Get full content of a specific email.

    Returns: {"email_id": str, "subject": str, "sender": str,
              "date": str, "body": str, "attachments": list}
    """
    # Use Gmail API: service.users().messages().get()
    # Parse MIME parts, extract text, handle HTML with BeautifulSoup
    ...
```

### Step 4: Build the vector store and embedding pipeline

**New file: `backend/flow/email_pipeline/embeddings.py`**

```python
import chromadb
from sentence_transformers import SentenceTransformer

# Use a lightweight model for email embedding
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384 dimensions, fast

class EmailVectorStore:
    def __init__(self, user_id: int):
        self.client = chromadb.PersistentClient(
            path=f"./data/chroma/{user_id}"
        )
        self.collection = self.client.get_or_create_collection(
            name="emails",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)

    async def ingest_emails(self, emails: list[dict]):
        """
        Chunk, embed, and store emails.

        Chunking strategy:
        - Split long emails into ~500-token chunks with 50-token overlap
        - Keep subject line + sender as metadata on every chunk
        - Parse .ics attachments separately as structured data
        """
        ...

    async def search(self, query: str, top_k: int = 5,
                     filters: dict = None) -> list[dict]:
        """
        Semantic search over indexed emails.

        Returns: [{"chunk_text": str, "email_id": str,
                    "subject": str, "sender": str, "date": str,
                    "relevance_score": float}]
        """
        query_embedding = self.embedder.encode(query)
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=filters
        )
        return self._format_results(results)
```

### Step 5: Build the event extractor

**New file: `backend/flow/email_pipeline/extractor.py`**

```python
from flow.llm import llm

EXTRACTION_PROMPT = """You are an event extraction assistant.
Given email content, extract any scheduling-relevant information.

Email content:
{email_text}

For each potential event found, return a JSON object:
{{
  "events": [
    {{
      "title": "descriptive event title",
      "start_date": "ISO 8601 datetime or null if ambiguous",
      "end_date": "ISO 8601 datetime or null",
      "location": "location or null",
      "confidence": "high" | "medium" | "low",
      "source_type": "confirmation" | "invitation" | "informal_mention",
      "evidence": "the exact text that indicates this event"
    }}
  ]
}}

Confidence guidelines:
- HIGH: Flight/hotel confirmations, formal calendar invites, registration confirmations
  (contain specific dates, times, confirmation numbers)
- MEDIUM: Meeting requests, rescheduling notices with specific proposed times
- LOW: Casual mentions ("let's grab coffee Tuesday"), vague references ("we should meet soon")

Return empty events array if no scheduling info found.
"""

async def extract_events_from_emails(email_chunks: list[dict]) -> list[dict]:
    """
    Use LLM to extract structured event data from email chunks.

    Groups results by confidence level:
    - HIGH: Ready for automatic creation (with user notification)
    - MEDIUM: Presented to user for confirmation before creation
    - LOW: Mentioned to user as possibilities, not auto-created
    """
    combined_text = "\n---\n".join([
        f"Subject: {c['subject']}\nFrom: {c['sender']}\n{c['chunk_text']}"
        for c in email_chunks
    ])

    response = await llm.ainvoke([
        SystemMessage(content=EXTRACTION_PROMPT.format(email_text=combined_text))
    ])

    # Parse JSON response, group by confidence
    ...
```

### Step 6: Create the email retrieval agent node

**New file: `backend/flow/email_pipeline/email_agent.py`**

```python
async def email_retrieval_agent(state: FlowState) -> dict:
    """
    LangGraph node that orchestrates the email RAG pipeline.

    Steps:
    1. Determine search query from user message context
    2. Fetch recent emails via Email MCP Server (if not already indexed)
    3. Perform semantic search on the vector store
    4. Extract events from top results
    5. Group by confidence and return proposals
    """
    user_id = state["user_id"]
    user_message = state["router_messages"][-1].content

    # Step 1: Generate search query
    search_query = await generate_email_search_query(user_message)

    # Step 2: Ensure recent emails are indexed
    store = EmailVectorStore(user_id)
    await refresh_email_index(store, user_id)  # Fetch & index new emails

    # Step 3: Semantic search
    relevant_chunks = await store.search(search_query, top_k=10)

    # Step 4: Extract events
    extracted = await extract_events_from_emails(relevant_chunks)

    # Step 5: Return proposals grouped by confidence
    return {
        "email_extracted_events": extracted,
        "email_search_results": relevant_chunks
    }
```

### Step 7: Integrate into the LangGraph flow

**File: `backend/flow/builder.py`**

Add the email retrieval agent as a node:

```python
from flow.email_pipeline.email_agent import email_retrieval_agent

graph.add_node("email_retrieval_agent", email_retrieval_agent)
```

This node is invoked in two ways:

**A. Explicit invocation via router:**
User says "Check my email for meetings" → Router classifies as `email_retrieval` → routes to this node.

Update `flow/router_agent/prompt.py`:
```
- "email" — user wants to check emails for scheduling information
```

**B. Proactive invocation via plan executor (PLAN-04):**
The plan executor can add an email retrieval task when it detects email-related triggers.

### Step 8: Update FlowState

**File: `backend/flow/state.py`**

```python
class FlowState(TypedDict):
    # ... existing fields ...
    email_extracted_events: list    # Events extracted from emails
    email_search_results: list      # Raw search results for context
    email_messages: list            # Message history for email agent
```

### Step 9: Build the user confirmation flow for extracted events

Extracted events need user confirmation before creation:

- **High confidence**: Show to user with "I found these events in your email — shall I add them?" + auto-select all
- **Medium confidence**: Show with details, user must explicitly select
- **Low confidence**: Mention in passing: "I also noticed a mention of coffee with Sarah, but the details are vague"

**File: `backend/services/assistant_service.py`**

```python
if state.get("email_extracted_events"):
    return {
        "type": "email_extraction",
        "message": "I found scheduling-relevant content in your emails:",
        "high_confidence": [e for e in events if e["confidence"] == "high"],
        "medium_confidence": [e for e in events if e["confidence"] == "medium"],
        "low_confidence": [e for e in events if e["confidence"] == "low"],
    }
```

**New file: `mobile/src/components/EmailExtractionComponent.tsx`**

Component that displays extracted events grouped by confidence:
- High: green cards, pre-selected checkboxes
- Medium: yellow cards, unchecked
- Low: grey text mentions, no checkboxes
- "Add Selected" button to create confirmed events

### Step 10: Email index management

**New file: `backend/flow/email_pipeline/index_manager.py`**

```python
async def refresh_email_index(store: EmailVectorStore, user_id: int):
    """
    Incrementally index new emails since last refresh.

    Strategy:
    - Track last-indexed email timestamp per user (store in Redis)
    - Only fetch and embed emails newer than that timestamp
    - Run at most once per 15 minutes per user (rate limit)
    """

async def full_reindex(store: EmailVectorStore, user_id: int,
                       days_back: int = 30):
    """
    Full reindex of recent emails. Used on first setup.
    Only indexes emails from the last N days to limit scope.
    """
```

---

## Directory Structure After Implementation

```
backend/
├── mcp_servers/
│   ├── email_server.py         # Gmail MCP Server
│   └── email_auth.py           # OAuth2 helper
├── flow/
│   └── email_pipeline/
│       ├── __init__.py
│       ├── email_agent.py      # LangGraph node
│       ├── embeddings.py       # Vector store + embedding
│       ├── extractor.py        # LLM event extraction
│       └── index_manager.py    # Incremental indexing
├── controller/
│   └── google_auth_controller.py  # OAuth2 callback
├── data/
│   └── chroma/                 # Persistent vector store (gitignored)
```

---

## Testing Strategy

### Unit Tests

1. **Chunking**: Verify long emails are split correctly with overlap
2. **Embedding + search**: Index 10 test emails, verify semantic search returns relevant ones
3. **Extraction**: Feed known email formats (flight confirmation, meeting invite, casual mention) to the extractor, verify correct extraction and confidence scoring
4. **Confidence classification**: Verify that formal confirmations get "high", meeting requests get "medium", casual mentions get "low"

### Integration Tests

5. **MCP Server**: Call `search_emails` and `get_email_content` against a test Gmail account
6. **End-to-end pipeline**: Index test emails → search → extract → verify proposals
7. **Flow integration**: Send "Check my email for meetings this week" to `/assistant/`, verify the response includes extracted events

### Mock Testing (for CI without Gmail access)

8. Create mock email data that mimics Gmail API responses
9. Test the full pipeline (chunking → embedding → search → extraction) against mock data
10. This allows testing without OAuth2 credentials

---

## Environment Variables

```
# Gmail OAuth2
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# ChromaDB (optional, defaults to local)
CHROMA_PERSIST_DIR=./data/chroma

# Embedding model (optional, defaults to all-MiniLM-L6-v2)
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Gmail OAuth2 complexity | Start with a service account or pre-generated refresh token for development; implement full OAuth2 flow later |
| Embedding model size / memory | `all-MiniLM-L6-v2` is only 80MB; runs on CPU fine |
| ChromaDB persistence across restarts | Use `PersistentClient` with a stable path; add to `.gitignore` |
| Rate limiting on Gmail API | Default quota is 250 requests/min — more than enough. Add exponential backoff |
| Privacy concerns with email indexing | Vector store is per-user, stored locally, never shared. Add clear consent in the mobile app |

---

## Dependencies

- **PLAN-02** (MCP Integration): Email MCP Server follows the same FastMCP pattern as the Calendar MCP Server
- **PLAN-04** (Planner Agent): Proactive email awareness is triggered by the plan executor
- Gmail API credentials must be set up before testing

---

## Files Modified/Created (Summary)

| File | Change |
|------|--------|
| `requirements.txt` | Add chromadb, sentence-transformers, google API packages |
| `mcp_servers/email_server.py` | **New** Email MCP Server |
| `mcp_servers/email_auth.py` | **New** OAuth2 helper |
| `flow/email_pipeline/__init__.py` | **New** |
| `flow/email_pipeline/email_agent.py` | **New** LangGraph node |
| `flow/email_pipeline/embeddings.py` | **New** vector store |
| `flow/email_pipeline/extractor.py` | **New** LLM extraction |
| `flow/email_pipeline/index_manager.py` | **New** index management |
| `flow/state.py` | Add email-related state fields |
| `flow/builder.py` | Add email_retrieval_agent node + route |
| `flow/router_agent/prompt.py` | Add "email" route |
| `controller/google_auth_controller.py` | **New** OAuth2 callback |
| `services/assistant_service.py` | Handle email_extraction response |
| `mobile/src/components/EmailExtractionComponent.tsx` | **New** UI |
| `mobile/src/screens/HomeScreen.tsx` | Handle email_extraction type |
| `config.py` | Add Google/ChromaDB settings |
