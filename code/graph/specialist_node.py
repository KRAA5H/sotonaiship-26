"""The specialist step between the director plan and execution.

It reads the task request, asks the council catalogue for required fields, rules
and evidence, and writes the result into the state. It never speaks to the
resident and never invents a rule.
"""

from council import specialists


def make_specialist_node(deps):
    def specialist(state):
        plan = state.get("plan") or {}
        request = plan.get("task_request")
        if not request:
            return {}
        store = getattr(deps, "council", None)
        if store is None:
            return {}
        kind = request.get("kind") or "permit"
        result = specialists.prepare(kind, request.get("fields") or {}, store)
        plan = dict(plan)
        task_request = dict(request)
        task_request["fields"] = dict(request.get("fields") or {})
        plan["task_request"] = task_request
        if result.get("missing"):
            field = result["missing"][0]
            plan["action"] = "ask"
            plan["clarification"] = {
                "field": field,
                "reason": result.get("suggested_question") or f"What is your {field}?",
            }
        if (result.get("eligibility") or {}).get("status") == "fail":
            plan["task_request"] = None
            plan["action"] = "answer"
            plan["clarification"] = None
            plan["fact_request"] = {"question": "eligibility", "category_id": "general"}
        return {"plan": plan, "specialist_results": [result]}
    return specialist
