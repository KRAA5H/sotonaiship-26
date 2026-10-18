# LLM freeze

The LLM side is locked. Do not edit these files or change the model behaviour without an explicit instruction from the operator.

Frozen at tag `llm-locked-v1`:

- `code/graph/prompts.py`: director prompt, plan shape, evidence brief.
- `code/graph/writer.py`: model writer, register matching, grounding, one-question gate.
- `code/graph/execution.py`: the parts that execute outcomes and choose writer input.
- `code/graph/nodes.py`: director and conversation flow.
- `code/graph/schemas.py`: TurnPlan, profile and task contract.
- `code/graph/evidence.py` and `agent/evidence.csv`: the checked evidence used for answers.

Rules:

1. No edits without the operator asking for a specific change.
2. Any approved change is made on a branch, not straight on this frozen point.
3. Run the graph trajectory and runtime tests before merging an approved change.
4. Never replace the model with a new classifier.
5. Never remove the 999 guard, the truth check, or the source citation.
6. A model failure may use the checked template fallback, nothing else.

The rest of the app, the dashboard, the task pages and the channel wiring may still be maintained without touching the frozen LLM files.
