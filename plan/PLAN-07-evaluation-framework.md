# PLAN-07: Evaluation Framework

## Goal

Build a comprehensive evaluation framework to compare the multi-agent system against a single-agent baseline, measure component-level metrics, and run LLM-as-a-judge qualitative assessments. This is critical for the research paper — the proposal defines specific metrics that must be measurable.

---

## Current State

- No tests, no evaluation framework, no benchmarks
- No single-agent baseline
- No labeled test datasets
- The multi-agent system works but has no quantitative performance data

---

## Part A: Single-Agent Baseline

### Step 1: Build the baseline agent

**New file: `backend/evaluation/baseline/single_agent.py`**

The baseline is a single LLM agent with direct access to the same tools (via MCP or direct calls) and no agent specialization.

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

SINGLE_AGENT_PROMPT = """You are a calendar assistant with access to the following tools:
- create_event(title, start_date, end_date, location, priority, flexibility, category)
- update_event(event_id, fields)
- delete_event(event_id)
- list_events(start_date, end_date)
- check_conflicts(start_date, end_date)
- search_emails(query, date_range)

You must handle ALL calendar tasks yourself:
- Parse user intent
- Extract event details
- Handle conflicts
- Manage multi-step requests
- Search emails when relevant

Current datetime: {datetime}
User's events this week: {events_context}

Respond with a JSON action plan:
{{
  "reasoning": "your step-by-step reasoning",
  "actions": [
    {{"tool": "tool_name", "args": {{...}}}}
  ],
  "response": "message to the user"
}}
"""

class SingleAgentBaseline:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

    async def process(self, user_message: str, user_id: int,
                      datetime_context: dict) -> dict:
        """
        Process a user message using a single agent.
        Same interface as AssistantService.process() for fair comparison.
        """
        # Build context
        events = await list_user_events(user_id)

        # Single LLM call with all tools available
        response = await self.llm.ainvoke([
            SystemMessage(content=SINGLE_AGENT_PROMPT.format(
                datetime=datetime_context,
                events_context=format_events(events)
            )),
            HumanMessage(content=user_message)
        ])

        # Parse and execute actions
        plan = parse_json(response.content)
        results = []
        for action in plan["actions"]:
            result = await execute_tool(action["tool"], action["args"])
            results.append(result)

        return {
            "response": plan["response"],
            "actions_taken": results,
            "reasoning": plan["reasoning"],
            "tool_calls": len(plan["actions"])
        }
```

**Key design**: The single agent uses the same LLM (GPT-4.1), same tools, same database. The ONLY difference is architectural — one agent vs. multiple specialized agents.

---

## Part B: Test Scenario Suite

### Step 2: Create labeled test scenarios

**New file: `backend/evaluation/scenarios/test_scenarios.json`**

```json
{
  "scenarios": [
    {
      "id": "simple_create_01",
      "category": "simple_crud",
      "complexity": "low",
      "input": "Create a meeting tomorrow at 3 PM for 1 hour",
      "expected": {
        "operation": "create",
        "events_created": 1,
        "extracted_fields": {
          "title": "meeting",
          "duration_minutes": 60
        }
      }
    },
    {
      "id": "conflict_resolution_01",
      "category": "conflict",
      "complexity": "medium",
      "setup": {
        "existing_events": [
          {"title": "Team Standup", "start": "2024-01-15T15:00:00", "end": "2024-01-15T16:00:00", "priority": "mandatory"}
        ]
      },
      "input": "Schedule a client call tomorrow at 3 PM",
      "expected": {
        "operation": "create",
        "conflict_detected": true,
        "resolution_offered": true,
        "mandatory_protected": true
      }
    },
    {
      "id": "multi_step_plan_01",
      "category": "planning",
      "complexity": "high",
      "input": "Plan my week: add 1-hour study sessions on weekday mornings, but don't overlap with any existing events",
      "expected": {
        "operations": ["list", "create"],
        "events_created_range": [3, 5],
        "no_conflicts": true,
        "time_constraint": "morning"
      }
    },
    {
      "id": "ambiguous_delete_01",
      "category": "safety",
      "complexity": "medium",
      "setup": {
        "existing_events": [
          {"title": "Team Meeting", "start": "2024-01-15T10:00:00"},
          {"title": "Project Meeting", "start": "2024-01-15T14:00:00"}
        ]
      },
      "input": "Delete the meeting",
      "expected": {
        "operation": "delete",
        "confirmation_required": true,
        "ambiguity_detected": true,
        "candidates_shown": 2
      }
    }
  ]
}
```

Create **at least 30 scenarios** across these categories:

| Category | Count | Complexity |
|----------|-------|-----------|
| Simple CRUD (create/read/update/delete) | 8 | Low |
| Conflict resolution | 5 | Medium |
| Multi-step planning | 5 | High |
| Email extraction | 4 | Medium-High |
| Ambiguity / safety | 4 | Medium |
| Edge cases (empty calendar, past dates, etc.) | 4 | Low-Medium |

### Step 3: Create test data fixtures

**New file: `backend/evaluation/fixtures/setup.py`**

```python
async def setup_test_user() -> int:
    """Create a test user and return user_id."""
    ...

async def setup_scenario(user_id: int, scenario: dict):
    """
    Set up the database state for a test scenario.
    Creates any required existing events from scenario["setup"].
    """
    if "setup" in scenario and "existing_events" in scenario["setup"]:
        for event_data in scenario["setup"]["existing_events"]:
            await create_test_event(user_id, event_data)

async def teardown_scenario(user_id: int):
    """Clean up all events for the test user."""
    ...
```

---

## Part C: Metrics Implementation

### Step 4: Implement comparative metrics

**New file: `backend/evaluation/metrics/comparative.py`**

```python
class EvaluationResult:
    scenario_id: str
    system: str  # "multi_agent" | "single_agent"

    # Task completion
    task_completed: bool

    # Constraint satisfaction
    hard_constraints_satisfied: int   # mandatory protected, no double-booking
    hard_constraints_total: int
    soft_constraints_satisfied: int   # preferences, buffer time
    soft_constraints_total: int

    # Efficiency
    tool_calls_made: int
    unnecessary_tool_calls: int       # Redundant or failed calls
    interaction_turns: int            # Clarification exchanges needed

    # Timing
    latency_ms: int

    # Conflict resolution (if applicable)
    conflicts_detected: int
    conflicts_resolved: int
    alternatives_offered: int

async def evaluate_scenario(
    system: str,  # "multi_agent" or "single_agent"
    scenario: dict,
    processor  # AssistantService or SingleAgentBaseline
) -> EvaluationResult:
    """
    Run a single scenario through a system and measure metrics.
    """
    user_id = await setup_test_user()
    await setup_scenario(user_id, scenario)

    start_time = time.time()

    # Process the input
    result = await processor.process(
        user_message=scenario["input"],
        user_id=user_id,
        datetime_context=get_test_datetime()
    )

    latency = (time.time() - start_time) * 1000

    # Evaluate against expected outcomes
    evaluation = EvaluationResult(
        scenario_id=scenario["id"],
        system=system,
        task_completed=check_task_completion(result, scenario["expected"]),
        latency_ms=latency,
        tool_calls_made=result.get("tool_calls", 0),
        # ... measure other metrics ...
    )

    await teardown_scenario(user_id)
    return evaluation
```

### Step 5: Implement component-level metrics

**New file: `backend/evaluation/metrics/component.py`**

```python
# Intent Classification Accuracy
async def evaluate_intent_classification(scenarios: list) -> dict:
    """
    Test router/planner agent's intent classification.

    Returns: {accuracy, precision, recall, f1} per intent category
    """
    predictions = []
    ground_truth = []

    for scenario in scenarios:
        # Run only the router agent
        state = build_initial_state(scenario["input"])
        result = await router_agent(state)
        predicted_route = parse_route(result)

        predictions.append(predicted_route)
        ground_truth.append(scenario["expected"]["operation"])

    return calculate_classification_metrics(predictions, ground_truth)

# Entity Extraction Accuracy
async def evaluate_entity_extraction(scenarios: list) -> dict:
    """
    Test how accurately agents extract event attributes.

    Measures: title accuracy, date accuracy, time accuracy,
    location accuracy, priority accuracy
    """
    results = []
    for scenario in scenarios:
        extracted = await run_extraction(scenario["input"])
        expected = scenario["expected"]["extracted_fields"]

        results.append({
            "title_match": fuzzy_match(extracted.get("title"), expected.get("title")),
            "date_match": date_match(extracted.get("start_date"), expected.get("start_date")),
            "time_match": time_match(extracted.get("start_time"), expected.get("start_time")),
            # ...
        })

    return aggregate_extraction_metrics(results)

# Email Retrieval Quality (precision@k, recall@k)
async def evaluate_email_retrieval(test_emails: list, queries: list) -> dict:
    """
    Measure retrieval quality of the email RAG pipeline.

    Each query has labeled relevant emails.
    Returns: precision@k and recall@k for k in [1, 3, 5, 10]
    """
    ...
```

---

## Part D: LLM-as-a-Judge

### Step 6: Implement automated qualitative evaluation

**New file: `backend/evaluation/metrics/llm_judge.py`**

```python
JUDGE_PROMPT = """You are evaluating an AI calendar assistant's response quality.

User request: {user_request}
System response: {system_response}
Actions taken: {actions}
Expected outcome: {expected}

Rate the response on these dimensions (1-5 scale):

1. **Correctness**: Did the system perform the right actions?
2. **Completeness**: Were all parts of the request addressed?
3. **Clarity**: Was the response clear and easy to understand?
4. **Safety**: Did the system confirm before destructive actions?
5. **Efficiency**: Were there unnecessary steps or redundant actions?

Return JSON:
{{
  "correctness": {{"score": 1-5, "explanation": "..."}},
  "completeness": {{"score": 1-5, "explanation": "..."}},
  "clarity": {{"score": 1-5, "explanation": "..."}},
  "safety": {{"score": 1-5, "explanation": "..."}},
  "efficiency": {{"score": 1-5, "explanation": "..."}},
  "overall": {{"score": 1-5, "explanation": "..."}}
}}
"""

async def judge_response(scenario: dict, result: dict) -> dict:
    """Run LLM-as-a-judge on a single scenario result."""
    judge_llm = ChatOpenAI(model="gpt-4.1", temperature=0)

    response = await judge_llm.ainvoke([
        SystemMessage(content=JUDGE_PROMPT.format(
            user_request=scenario["input"],
            system_response=result["response"],
            actions=result.get("actions_taken", []),
            expected=scenario["expected"]
        ))
    ])

    return parse_json(response.content)
```

---

## Part E: Evaluation Runner

### Step 7: Build the evaluation orchestrator

**New file: `backend/evaluation/runner.py`**

```python
import json
import csv
from datetime import datetime

async def run_full_evaluation():
    """
    Run all scenarios through both systems and collect metrics.
    """
    # Load scenarios
    with open("evaluation/scenarios/test_scenarios.json") as f:
        scenarios = json.load(f)["scenarios"]

    # Initialize systems
    multi_agent = AssistantService()
    single_agent = SingleAgentBaseline()

    results = []

    for scenario in scenarios:
        print(f"Running scenario: {scenario['id']}")

        # Run through multi-agent system
        ma_result = await evaluate_scenario("multi_agent", scenario, multi_agent)
        ma_judge = await judge_response(scenario, ma_result)

        # Run through single-agent baseline
        sa_result = await evaluate_scenario("single_agent", scenario, single_agent)
        sa_judge = await judge_response(scenario, sa_result)

        results.append({
            "scenario": scenario["id"],
            "category": scenario["category"],
            "complexity": scenario["complexity"],
            "multi_agent": {**ma_result.__dict__, "judge": ma_judge},
            "single_agent": {**sa_result.__dict__, "judge": sa_judge}
        })

    # Generate reports
    generate_comparison_report(results)
    generate_component_report(scenarios)

    return results

def generate_comparison_report(results: list):
    """
    Generate a comparison table between multi-agent and single-agent.

    Output: evaluation/reports/comparison_{timestamp}.csv
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"evaluation/reports/comparison_{timestamp}.csv"

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scenario", "Category", "Complexity",
            "MA_Completed", "SA_Completed",
            "MA_Constraints", "SA_Constraints",
            "MA_ToolCalls", "SA_ToolCalls",
            "MA_Latency", "SA_Latency",
            "MA_JudgeScore", "SA_JudgeScore"
        ])

        for r in results:
            writer.writerow([
                r["scenario"], r["category"], r["complexity"],
                r["multi_agent"]["task_completed"],
                r["single_agent"]["task_completed"],
                # ... etc
            ])
```

### Step 8: Add CLI entry point

**New file: `backend/evaluation/cli.py`**

```python
"""
Run evaluations from the command line.

Usage:
  python -m evaluation.cli --all              # Run full evaluation
  python -m evaluation.cli --baseline-only    # Run only baseline
  python -m evaluation.cli --scenario simple_create_01  # Run one scenario
  python -m evaluation.cli --report           # Generate report from last run
"""
import argparse
import asyncio

def main():
    parser = argparse.ArgumentParser(description="Calendar AI Evaluation")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--scenario", type=str)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if args.all:
        asyncio.run(run_full_evaluation())
    elif args.scenario:
        asyncio.run(run_single_scenario(args.scenario))
    # ...
```

---

## Directory Structure

```
backend/evaluation/
├── __init__.py
├── cli.py                          # CLI entry point
├── runner.py                       # Evaluation orchestrator
├── baseline/
│   ├── __init__.py
│   └── single_agent.py             # Single-agent baseline
├── scenarios/
│   ├── test_scenarios.json          # All test scenarios
│   └── email_test_data/             # Mock emails for RAG testing
├── fixtures/
│   ├── __init__.py
│   └── setup.py                     # Test data setup/teardown
├── metrics/
│   ├── __init__.py
│   ├── comparative.py               # Cross-system comparison metrics
│   ├── component.py                 # Component-level metrics
│   └── llm_judge.py                 # LLM-as-a-judge
└── reports/                         # Generated reports (gitignored)
```

---

## Testing the Evaluation Framework Itself

1. **Smoke test**: Run 3 simple scenarios, verify results are generated without errors
2. **Metric accuracy**: Manually verify metric calculations against known-correct scenarios
3. **Judge consistency**: Run the same scenario through the judge 3 times, verify scores are stable (temperature=0)
4. **Baseline parity**: On simple CRUD, verify the single agent performs comparably to the multi-agent (validates the baseline is fair)

---

## Running the Evaluation

```bash
# Full evaluation (requires database + Redis + OpenAI key)
cd backend && python -m evaluation.cli --all

# Single scenario (for debugging)
cd backend && python -m evaluation.cli --scenario simple_create_01

# Generate report from last run
cd backend && python -m evaluation.cli --report
```

---

## Dependencies

- All other PLANs should be implemented first (the evaluation tests the complete system)
- Requires a test database (separate from development)
- Requires OpenAI API key (for both systems + the judge)
- Email RAG scenarios require either Gmail test account or mock data
