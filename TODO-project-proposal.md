# CALEN: AI CALENDAR ASSISTANT

**Arda Kabadayi** (akabaday@syr.edu)
**Brianna Gillfillian** (bsgillfi@syr.edu)
**Jaikrishna M Patil** (jpatil01@syr.edu)
**Naveen Ashok** (nashok@syr.edu)

---

## Background

Digital calendar systems such as Google Calendar and Microsoft Outlook are essential productivity tools, yet they rely primarily on manual, form-based interaction. Users must navigate structured interfaces, fill in event details field by field, and confirm each modification individually — a workflow that introduces friction when users need to perform scheduling tasks quickly or express complex intentions in natural language.

A key limitation is the inability to handle context-rich, multi-step requests. A request such as "Block out three hours for studying this week, but avoid mornings and don't overlap with anything mandatory" requires a user to manually check availability, identify feasible time slots, and create each event individually. Existing tools also lack proactive intelligence: they do not reason about event priorities, suggest optimal arrangements, or surface scheduling-relevant information buried in email inboxes. Flight confirmations, meeting requests in casual emails, and rescheduled exam announcements all contain structured scheduling data that users must manually identify and transcribe into their calendars.

Recent developments in Large Language Models (LLMs) and Natural Language Understanding (NLU) offer promising solutions. LLMs can interpret flexible or ambiguous instructions, extract structured event information from conversational input, and perform multi-step reasoning via chain-of-thought prompting (Wei et al., 2022). Retrieval-Augmented Generation (RAG) techniques (Lewis et al., 2020) further enable LLMs to access and reason over large external knowledge bases — such as a user's email inbox — by retrieving relevant documents at query time. However, a single LLM agent faces limitations when managing tasks that require fundamentally different reasoning strategies. Schedule optimization, conflict resolution under priority constraints, and email-based event extraction each demand distinct context, memory, and decision-making approaches. Multi-agent architectures address this by distributing specialized responsibilities across dedicated agents (Park et al., 2023).

A further architectural challenge is the integration layer between AI agents and external services. The Model Context Protocol (MCP), introduced by Anthropic in 2024 and now governed by the Agentic AI Foundation under the Linux Foundation, provides an open standard for connecting AI systems to external tools and data sources (Anthropic, 2024). By standardizing tool discovery, invocation, and data exchange, MCP enables multi-agent systems to achieve cleaner separation between reasoning logic and service connectivity.

By combining conversational AI, retrieval-augmented generation, a multi-agent architecture, and MCP-based tool integration, Calen aims to transform calendar management from a manual, reactive process into an intelligent, proactive, and context-aware experience.

---

## Research Question and Hypothesis

This project investigates whether a hybrid multi-agent architecture can outperform a single tool-using LLM agent on complex scheduling tasks that require decomposition, conflict resolution, and retrieval from unstructured email data.

We hypothesize that specialized agents — each operating with focused context, tailored prompts, and dedicated reasoning strategies — will improve task completion accuracy and schedule quality on multi-step scenarios, while maintaining comparable performance on simple single-step CRUD tasks. Specifically, we expect the multi-agent system to produce fewer unresolved conflicts, more accurately extract scheduling information from emails, and better satisfy user-defined constraints such as event priority and time preferences.

---

## System Description

Calen is an intelligent conversational calendar assistant that enables users to manage their schedules through natural language commands. The system goes beyond basic CRUD operations by offering schedule optimization, intelligent conflict resolution, and email-based schedule awareness. The architecture consists of specialized agents coordinated by a central Planner Agent, supported by a RAG-powered email retrieval pipeline, with all external service integrations handled through MCP servers.

### Project Scope

To ensure the project is implementable within a single semester while maintaining technical ambition, the system is divided into core and stretch deliverables.

**Core scope:**

- Planner Agent (orchestration, decomposition, optimization, memory)
- Scheduling Agent (CRUD execution via Calendar MCP Server)
- Conflict Resolution Agent (priority-aware conflict handling)
- Email Retrieval Pipeline (RAG-based extraction from inbox)
- Google Calendar MCP Server and Email MCP Server (built with FastMCP)
- Single-agent baseline for comparative evaluation

**Stretch scope:**

- Leisure Search Agent (external event discovery via Event Search MCP Server)
- Voice interface for natural language input
- Advanced optimization objective with formal utility function
- Demonstration of service portability (e.g., swapping Google Calendar for Outlook by deploying a new MCP server with no agent logic changes)

### MCP Integration Layer

A core architectural decision in Calen is the use of the Model Context Protocol as the standardized interface between agents and external services. Rather than implementing custom API wrappers within each agent, the system exposes external services through dedicated MCP servers. Each MCP server wraps a specific service and exposes a set of tools that any agent can discover and invoke through the standard MCP client protocol.

This design provides several key advantages:

- **Standardized tool interfaces:** Agents interact with MCP tool endpoints rather than raw APIs, ensuring a uniform interaction pattern across all external services.
- **Service-agnostic agent logic:** Swapping the underlying service (e.g., replacing Google Calendar with Microsoft Outlook) requires only deploying a new MCP server — no changes to agent reasoning or orchestration logic.
- **Extensibility:** Adding new capabilities (e.g., Notion integration, Slack messaging) requires only building a new MCP server. Existing agents can immediately leverage new tools without modification.

The system implements the following MCP servers:

- **Calendar MCP Server:** Wraps the Google Calendar API and exposes tools for event creation, updating, deletion, listing, and conflict detection.
- **Email MCP Server:** Wraps the Gmail API and provides tools for email retrieval and search, supporting the RAG pipeline's ingestion and query stages.
- **Event Search MCP Server** *(stretch scope)*: Wraps external event APIs (e.g., Ticketmaster, SeatGeek) and exposes tools for event discovery and filtering.

All MCP servers are built using FastMCP (Python), which simplifies server development and ensures compliance with the MCP specification.

### Architecture Overview

#### 1. Planner Agent (Orchestrator)

The Planner Agent serves as the central orchestrator of the system. It receives all user input, interprets high-level intent, and delegates tasks to the appropriate specialized agents. Critically, the Planner Agent does more than simple routing — it performs multi-step task decomposition and schedule optimization.

**Key responsibilities:**

- **Intent interpretation and task decomposition:** When a user makes a complex request such as "Set up a weekly study schedule around my existing classes," the Planner Agent breaks this into sub-tasks: querying existing events, identifying recurring free slots, optimizing for user preferences (e.g., preferred study times, session length), and issuing a sequence of create operations.
- **Utility-based optimization:** The Planner Agent maintains an optimization objective that maximizes schedule utility. It considers factors such as event priority (mandatory vs. optional), user-defined preferences (e.g., "I prefer mornings for deep work"), buffer time between events, and balanced workload distribution across the week.
- **Focus slot management:** Users can define flexible "focus slots" — blocks of time reserved for specific activities like studying or personal projects. The Planner Agent can dynamically relocate these slots based on changing external circumstances, such as a new mandatory meeting being added.
- **Proactive email awareness:** The Planner Agent can invoke the Email Retrieval Pipeline to surface scheduling-relevant information from the user's inbox — either on explicit request ("Check my emails for anything I should add to my calendar") or when context suggests it would be helpful (e.g., the user mentions "that flight" without a corresponding calendar event).
- **Short-term memory and context compaction:** The Planner Agent maintains conversation history to resolve ambiguous references (e.g., "move *that* meeting to Friday" requires knowing which meeting was recently discussed). To manage token limits over extended interactions, the system uses context compaction — summarizing older conversation turns while preserving key entities and decisions.

#### 2. Scheduling Agent (Executor)

The Scheduling Agent is responsible for executing calendar operations through the Calendar MCP Server. It acts as the system's interface to the calendar backend, handling event creation, updates, listing, and deletion.

**Key responsibilities:**

- **CRUD operations:** Creating, reading, updating, and deleting events via the Calendar MCP Server's tool endpoints.
- **Intelligent querying:** When retrieving events, the Scheduling Agent uses LLM reasoning to craft appropriate queries — filtering by date range, event title, or other attributes based on the user's natural language description.
- **Bulk event creation:** For requests involving multiple events (e.g., "Schedule a 1-hour review session every weekday next week"), the Scheduling Agent executes a batch of operations as directed by the Planner Agent's decomposition plan.
- **Event classification:** Each event is tagged with metadata including priority level (mandatory or optional), flexibility (fixed or movable), and category (work, study, personal, leisure). This metadata is used by the Conflict Resolution Agent and Planner Agent for downstream reasoning.

**MCP Tools (via Calendar MCP Server):**
- `create_event(title, start, end, priority, flexibility, category, location, notes)`
- `update_event(event_id, fields_to_update)`
- `delete_event(event_id)`
- `list_events(date_range, filters)`
- `check_conflicts(start, end)`

#### 3. Conflict Resolution Agent

The Conflict Resolution Agent activates whenever the Scheduling Agent detects a time overlap during event creation or modification. Unlike simple conflict detection, this agent performs priority-aware reasoning to propose actionable solutions.

**Key responsibilities:**

- **Priority-based conflict assessment:** The agent evaluates each conflicting event's priority and flexibility. Mandatory, fixed events (e.g., a dentist appointment) are protected, while optional or flexible events (e.g., a gym session) can be rescheduled.
- **Alternative time suggestion:** When a conflict is detected, the agent queries available time slots through the Calendar MCP Server and proposes ranked alternatives based on the Planner Agent's optimization criteria (proximity to original time, user preference patterns, impact on surrounding events).
- **Bulk and recursive conflict resolution:** For bulk scheduling operations (e.g., creating a recurring weekly event), the agent resolves conflicts across the entire series rather than one instance at a time, ensuring global schedule consistency.
- **User confirmation workflow:** For high-impact changes (e.g., moving a meeting with other participants), the agent presents options to the user with clear explanations of tradeoffs before executing changes.

#### 4. Email Retrieval Pipeline (RAG)

The Email Retrieval Pipeline provides Calen with schedule awareness beyond explicit user input by enabling the system to retrieve and reason over the user's email inbox using Retrieval-Augmented Generation.

**Pipeline architecture:**

- **Ingestion:** Emails are fetched via the Email MCP Server (wrapping the Gmail API) and preprocessed to extract relevant text content (subject line, body, sender, date). Attachments such as calendar invites (.ics files) are parsed for structured event data.
- **Chunking and embedding:** Email content is chunked and embedded into a vector store (ChromaDB or FAISS) using a sentence embedding model. Each chunk retains metadata including sender, date, and email thread ID for filtering during retrieval.
- **Retrieval:** When the Planner Agent invokes the email retrieval tool, the system performs a semantic search over the vector store using the user's query or contextual scheduling intent as the search query. The top-k most relevant email chunks are returned.
- **Extraction and reasoning:** Retrieved email chunks are passed to the LLM, which extracts structured scheduling information — event titles, dates, times, locations, and participants. The Planner then routes extracted events to the Scheduling Agent for creation, running through the normal conflict-checking flow.

**Supported use cases:**

- **Explicit retrieval:** User asks "Do I have any meetings this week that aren't on my calendar? Check my email." The system retrieves relevant emails and suggests events to add.
- **Contextual retrieval:** User mentions "my flight on Thursday" but no flight event exists on the calendar. The Planner queries the email index for flight confirmation emails and extracts the relevant details.
- **Structured email parsing:** Confirmation emails (flights, hotels, event registrations) contain highly structured data and are prioritized as high-confidence extraction targets. Informal scheduling requests ("Let's grab coffee Tuesday") are extracted with lower confidence and presented to the user for confirmation before creation.

**MCP Tools (via Email MCP Server):**
- `search_emails(query, date_range, sender, top_k)`
- `get_email_content(email_id)`

**RAG-specific Tools:**
- `embed_and_store(email_chunks)`
- `semantic_search(query, top_k, filters)`
- `extract_events_from_text(text_chunks)`

#### 5. Leisure Search Agent *(Stretch Scope)*

The Leisure Search Agent extends Calen beyond schedule management into schedule enrichment. It serves primarily as a demonstration of the system's extensibility through MCP: because the Event Search MCP Server exposes a standardized tool interface, existing agents can immediately leverage it without modification.

**Key responsibilities:**

- **External event discovery:** The agent queries the Event Search MCP Server to find sports events, concerts, and community activities from APIs such as Ticketmaster or SeatGeek.
- **Personalized recommendations:** Results are filtered and ranked based on user preferences, available free time (queried via the Calendar MCP Server), location proximity, and date.
- **Calendar integration:** When a user selects a discovered event, the Leisure Search Agent passes it to the Scheduling Agent for creation, triggering the normal conflict-checking pipeline.

**MCP Tools (via Event Search MCP Server):**
- `search_events(query, date_range, location, category)`
- `get_event_details(event_id)`

#### 6. Failure Handling and Safety Policy

Since Calen operates on real calendar data with the ability to create, modify, and delete events, the system implements a confirmation-first policy for operations that carry risk of unintended consequences. For low-confidence email extraction, ambiguous event references (e.g., "delete that meeting" when multiple meetings exist), or high-impact modifications (e.g., rescheduling a mandatory event), Calen defaults to presenting the user with its interpretation and requesting explicit confirmation before executing calendar changes. This policy applies across all agents and is enforced by the Planner Agent before delegating destructive or ambiguous operations.

#### 7. Conversational Feedback and Change Summaries

Rather than relying on external notification services, Calen delivers all feedback, confirmations, and change summaries directly within the conversation. When agents perform actions — especially multi-step operations involving conflict resolution or bulk scheduling — the Planner Agent compiles a clear, natural language summary of what changed and presents it to the user in context. For example, after resolving a set of conflicts the system might respond: "I moved your gym session from 2 PM to 4 PM to make room for the team meeting. Your study block stays at 10 AM as planned. Here's your updated Thursday."

### System Architecture Diagram

```
┌──────────┐
│   User   │
└────┬─────┘
     │ Natural Language / Voice
     ▼
┌──────────────────────────────────────────────────────────┐
│                PLANNER AGENT (Orchestrator)               │
│  • Intent interpretation & multi-step task decomposition  │
│  • Utility-based optimization & focus slot management     │
│  • Proactive email awareness via RAG                      │
│  • Short-term memory + context compaction                 │
│  • Confirmation-first safety policy                       │
│  • Conversational feedback & change summaries             │
└──┬──────────┬──────────────┬──────────────┬──────────────┘
   │          │              │              │
   ▼          ▼              ▼              ▼
┌─────────┐┌───────────┐┌──────────┐┌───────────────┐
│Scheduling││  Conflict  ││  Leisure  ││    Email       │
│  Agent   ││ Resolution ││  Search   ││  Retrieval    │
│(Executor)││   Agent    ││  Agent *  ││  Pipeline     │
│          ││            ││           ││   (RAG)       │
└────┬─────┘└─────┬──────┘└─────┬─────┘└───────┬───────┘
     │            │             │               │
     │      ┌─────┘             │               │
     ▼      ▼                   ▼               ▼
┌─────────────────┐    ┌──────────────┐  ┌─────────────┐
│   MCP Clients   │    │  MCP Client  │  │ MCP Client  │
└────────┬────────┘    └──────┬───────┘  └──────┬──────┘
         │                    │                  │
═══════════════════════════════════════════════════════════
         MCP Protocol Layer (JSON-RPC 2.0)
═══════════════════════════════════════════════════════════
         │                    │                  │
         ▼                    ▼                  ▼
┌──────────────┐     ┌──────────────┐   ┌─────────────┐
│  Calendar    │     │ Event Search │   │   Email     │
│  MCP Server  │     │  MCP Server* │   │  MCP Server │
│  (FastMCP)   │     │  (FastMCP)   │   │  (FastMCP)  │
└──────┬───────┘     └──────┬───────┘   └──────┬──────┘
       │                    │                   │
       ▼                    ▼                   ▼
┌──────────────┐     ┌──────────────┐   ┌─────────────┐
│   Google     │     │ Ticketmaster │   │  Gmail API  │
│  Calendar    │     │  / SeatGeek  │   │      +      │
│    API       │     │    APIs      │   │Vector Store │
└──────────────┘     └──────────────┘   │(ChromaDB/   │
                                        │  FAISS)     │
                                        └─────────────┘

                    * = stretch scope
```

---

## Justification for Multi-Agent Architecture

A single LLM agent with tool selection is sufficient for straightforward CRUD calendar operations. Calen's architecture acknowledges this — the Scheduling Agent functions as a tool-calling executor. However, the system's value lies in capabilities that extend beyond simple event management:

- **Schedule optimization** requires holistic reasoning over an entire week's events, user preferences, and priority constraints. This is a planning problem distinct from executing individual API calls.
- **Conflict resolution under priority constraints** involves tradeoff analysis, alternative generation, and user preference modeling — a reasoning task with different context requirements than event execution.
- **Email-based schedule awareness** demands a retrieval pipeline and extraction reasoning that operates over an entirely different data source (the inbox) with its own retrieval strategy, confidence assessment, and structured output requirements.

Each of these responsibilities demands its own context window, memory, prompt engineering strategy, and reasoning approach. Bundling them into a single agent would create an overloaded prompt, increase reasoning errors, and make the system harder to debug and extend. The multi-agent design ensures each agent operates with focused context and clear responsibilities, while the Planner Agent coordinates their collaboration.

The adoption of MCP as the integration layer further strengthens this architecture. By decoupling agent reasoning from service-specific API logic, MCP allows each agent to focus purely on its decision-making responsibilities while interacting with external services through a uniform protocol. This separation also makes the system inherently extensible — adding support for new platforms requires only deploying a new MCP server, with no modifications to agent logic.

To validate this architectural choice empirically, the evaluation includes a direct comparison against a single-agent baseline (see Evaluation Metrics).

---

## Objectives

### Architecture and Design

1. Design a multi-agent system with a Planner Agent (orchestration, decomposition, optimization), a Scheduling Agent (CRUD execution), and a Conflict Resolution Agent (priority-aware conflict handling), coordinated through structured task delegation.

2. Build MCP servers for Google Calendar and Gmail using FastMCP, providing standardized tool interfaces that enable service-agnostic agent logic and support future extensibility.

### Implementation

3. Implement Natural Language Understanding within the Planner Agent to extract structured event attributes (titles, dates, times, locations, priorities) from conversational input and decompose multi-step requests into agent-executable sub-tasks.

4. Implement a RAG-powered Email Retrieval Pipeline that ingests user emails via the Email MCP Server, indexes them in a vector store, retrieves scheduling-relevant messages on demand, and extracts structured event data with confidence-based handling (high-confidence for structured emails, confirmation-required for informal mentions).

5. Develop a short-term memory system with context compaction to support multi-turn conversations, enabling the system to resolve ambiguous references and maintain coherent interaction across extended scheduling sessions.

### Evaluation

6. Construct a single-agent baseline system using one LLM with direct tool access to the same MCP servers, and compare it against the multi-agent system on task completion accuracy, conflict resolution quality, and email extraction performance.

7. Evaluate the system on complex, multi-step scheduling scenarios that require cross-agent collaboration, using both objective metrics (constraint satisfaction, conflict resolution rate, extraction accuracy) and LLM-as-a-judge assessment for conversational quality.

---

## Evaluation Metrics

The system will be evaluated through a comparative study between the proposed multi-agent architecture and a single-agent baseline, supplemented by component-level metrics.

### Baseline Comparison

- **Baseline A (Single-Agent):** A single LLM agent equipped with direct access to the same MCP tools (calendar CRUD, email retrieval, event extraction). All reasoning — decomposition, conflict handling, retrieval — is performed within a single prompt/context.
- **Proposed System (Multi-Agent):** The full Calen architecture with Planner, Scheduling, Conflict Resolution, and Email Retrieval agents.

Both systems will be tested on an identical set of scheduling scenarios ranging from simple single-step tasks ("Create a meeting at 3 PM tomorrow") to complex multi-step tasks ("Plan my week — check my email for anything I'm missing, keep my mandatory meetings, and add study time around my classes").

### Comparative Metrics

- **Task completion rate:** Percentage of scenarios where all requested operations are successfully executed.
- **Constraint satisfaction score:** Percentage of hard constraints (mandatory event protection, no double-booking) and soft constraints (user preferences, buffer time) satisfied in the final schedule.
- **Conflict resolution quality:** Number of unresolved conflicts remaining after execution; appropriateness of proposed alternatives (measured via annotator agreement).
- **Number of interaction turns:** How many clarification exchanges are needed before the system completes the task.
- **Unnecessary tool calls:** Number of redundant or incorrect MCP tool invocations, measuring efficiency of agent delegation.

### Component-Level Metrics

**Intent Classification and Routing Accuracy:** A labeled test set of calendar-related queries will evaluate whether the Planner Agent correctly identifies user intent and routes to the appropriate agent. Metrics: accuracy, precision, recall, and F1-score.

**Entity Extraction Accuracy:** Extracted event attributes (title, date, time, location, priority) will be compared against reference annotations across both simple and complex requests.

**Email Retrieval and Extraction Quality:** Retrieval quality measured using precision@k and recall@k against a labeled set of test emails. Extraction accuracy measured by comparing extracted event attributes against ground truth, with separate reporting for high-confidence structured emails (confirmations, invitations) and low-confidence informal mentions.

### Qualitative Assessment

**LLM-as-a-judge:** An LLM judge will evaluate conversational quality, response clarity, and logical consistency across complex multi-step scenarios. This supplements, but does not replace, the objective metrics above.

**End-to-end scenario walkthroughs:** A set of representative user scenarios will be used to assess overall system coherence and practical usefulness.

---

## References

Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all you need. *Advances in Neural Information Processing Systems, 30.*

Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., ... & Amodei, D. (2020). Language models are few-shot learners. *Advances in Neural Information Processing Systems, 33.*

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33.*

Wei, J., Wang, X., Schuurmans, D., Bosma, M., Xia, F., Chi, E., Le, Q. V., & Zhou, D. (2022). Chain-of-thought prompting elicits reasoning in large language models. *Advances in Neural Information Processing Systems, 35.*

Anthropic. (2024). Introducing the Model Context Protocol. *Anthropic Blog.* https://www.anthropic.com/news/model-context-protocol

Budzianowski, P., Wen, T.-H., Tseng, B.-H., Casanueva, I., Ultes, S., Ramadan, O., & Gasic, M. (2018). MultiWOZ – A large-scale multi-domain wizard-of-oz dataset for task-oriented dialogue modelling. *Proceedings of the 2018 Conference on Empirical Methods in Natural Language Processing (EMNLP).*

Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology (UIST).*
