"""Execute one checked plan, then say what actually happened.

One write path (`tools.save_report`), one token, no invented receipt. The copy is
deterministic templates here; a model writer can rephrase later only through the
same lint gate.
"""

import copy
import re

import messages
import reports_db
import tools

from . import policy, prompts, schemas


def _place(draft):
    location = draft.get("location") or {}
    for key in ("text", "street", "postcode"):
        value = location.get(key)
        if isinstance(value, str) and value.strip() \
                and value.strip().lower() != schemas.LOCATION_UNKNOWN.lower():
            return value.strip()
    return None


def _has_place(draft):
    return bool(_place(draft))


def _has_text(draft):
    return bool((draft.get("description") or "").strip()) or bool(draft.get("attachments"))


def context(deps, state):
    index = deps.playbooks or {}
    draft = state.get("incident_draft") or {}
    candidates = state.get("candidate_services") or []
    category = draft.get("category_id") or (candidates[0] if candidates else None) \
        or "unclear_other"
    book = prompts.playbook(category)
    required = frozenset(book.get("required_local") or ())
    missing = set()
    for field in required:
        if field in ("description", "photo"):
            if not _has_text(draft):
                missing.add("description")
        elif field in ("location", "address"):
            if not _has_place(draft):
                missing.add("location")
    allowed_questions = frozenset(
        book.get("allowed_question_fields")
        or (index.get("allowed_questions_by_category") or {}).get(category)
        or index.get("allowed_questions") or ())
    destinations = set(index.get("numbers") or ())
    destinations.update((index.get("known_facts") or {}).keys())
    for item in (index.get("guidance") or {}).values():
        for key in ("url", "contact"):
            if item.get(key):
                destinations.add(item[key])
    for name in (index.get("categories") or {}):
        form = prompts.playbook(name).get("form_url")
        if form:
            destinations.add(form)
    return policy.PolicyContext(
        known_categories=frozenset((index.get("categories") or {}).keys()),
        category_outcomes=index.get("categories") or {},
        known_facts=index.get("known_facts") or {},
        allowed_destinations=frozenset(destinations),
        allowed_questions=allowed_questions,
        allowed_numbers=frozenset(index.get("numbers") or ()),
        forbidden_team_names=frozenset(index.get("forbidden_team_names") or ()),
        missing_fields=frozenset(missing),
        required_local=required,
        location_mode=book.get("location_mode"),
        handoff_categories=frozenset(index.get("handoff_categories") or
                                     {"noise_nuisance", "other_nuisance", "property_concern"}),
        never_saved=frozenset(index.get("never_saved") or
                              {"outside_southampton", "not_council_trunk_road",
                               "not_council_utility"}),
    )


def _apply_patch(draft, plan):
    patch = plan.get("incident_patch") or {}
    if not patch:
        return draft
    effective, problems = schemas.apply_patch(
        draft, patch, draft.get("version", 0), plan.get("reason_codes"))
    if not problems or problems == ["patch.no_change"]:
        return effective
    return draft


def _link(outcome):
    token = outcome.get("link_token")
    return f"{tools.SITE_URL}/r/{token}" if token else None


def _now(state, deps):
    value = deps.now()
    return value.isoformat(timespec="seconds")


def execute(state, deps):
    plan = state.get("plan") or {}
    draft = copy.deepcopy(state.get("incident_draft") or {})
    draft = _apply_patch(draft, plan)
    index = deps.playbooks or {}
    categories = index.get("categories") or {}
    candidates = plan.get("service_candidates") or state.get("candidate_services") or []
    category = draft.get("category_id") or (candidates[0] if candidates else None) \
        or "unclear_other"
    action = plan.get("action") or "ask"

    if category not in categories and category != "unclear_other":
        category = "unclear_other"
    clarification = plan.get("clarification") or {}
    if action == "ask" and _has_text(draft) \
            and clarification.get("field") in ("location", "address") \
            and categories.get(category) != "not_council" \
            and category not in (index.get("never_saved") or ()):
        # Capture-first: a described problem is saved before we ask where it is.
        action = "log"
    if action == "log" and (categories.get(category) in ("info_only", "not_council")
                            or category in (index.get("never_saved") or ())):
        category = "unclear_other"
    draft["category_id"] = category
    draft["routing_status"] = ("needs_review" if category == "unclear_other"
                               else "verified")
    draft["capture_state"] = ("captured" if category == "unclear_other"
                              or not _has_place(draft) else "locally_actionable")
    draft["version"] = int(draft.get("version") or 0) + 1

    ctx = context(deps, state)
    missing = []
    for field in ctx.required_local:
        if field in ("description", "photo") and not _has_text(draft):
            missing.append("description")
        elif field in ("location", "address") and not _has_place(draft):
            missing.append("location")
    missing = list(dict.fromkeys(missing))

    outcome = {
        "action": action,
        "report_id": None,
        "link_token": None,
        "submitted": False,
        "duplicate_of": None,
        "locally_actionable": False,
        "missing": missing,
        "facts": [],
        "review_queued": category == "unclear_other",
        "transport": "queued",
        "degraded": [],
        "saved": False,
        "refused_reason": None,
        "playbook_version": prompts.playbook(category).get("version"),
        "destination": None,
        "status": None,
    }
    pending = None
    active = state.get("active_incident_id")
    is_detail = bool(action == "log" and active and (
        plan.get("dialogue_act") == "detail"
        or prompts.is_detail((state.get("inbound") or {}).get("text") or "", state)))

    if action == "log" and not is_detail:
        description = (draft.get("description") or "").strip()
        if not description and draft.get("attachments"):
            description = "Photo of a problem"
            draft["description"] = description
        if not description:
            action = "ask"
            outcome["action"] = "ask"
            outcome["missing"] = ["description"]
            pending = {"field": "description", "text": "What is the problem?",
                       "asked_at": _now(state, deps), "turn_id": state.get("turn_id")}
        elif category in (index.get("never_saved") or ()) \
                or categories.get(category) == "not_council":
            outcome["refused_reason"] = "not_council"
            outcome["missing"] = []
            action = "escalate"
            outcome["action"] = "escalate"
        else:
            cached = deps.ops.get(state.get("turn_id"), "commit") if deps.ops else None
            saved = cached
            if saved is None:
                conn = reports_db.connect(deps.reports) if deps.reports else None
                try:
                    saved = tools.save_report(
                        category, _place(draft), description,
                        severity=draft.get("severity"),
                        has_photo=bool(draft.get("attachments")),
                        reporter=(state.get("inbound") or {}).get("sender"),
                        conn=conn,
                        capture_state=draft["capture_state"],
                        routing_status=draft["routing_status"],
                    )
                    if saved.get("ok") and draft.get("attachments"):
                        photo = next((item for item in draft["attachments"]
                                      if item.get("ref")), None)
                        if photo:
                            mime = (photo.get("features") or {}).get("mime") or "image/jpeg"
                            tools.attach_photo_to_report(saved.get("report_id"),
                                                         photo.get("ref"), mime, conn=conn)
                finally:
                    if conn is not None:
                        conn.close()
                if deps.ops and saved.get("ok"):
                    deps.ops.record(state.get("turn_id"), "commit", saved)
            if saved.get("ok"):
                outcome.update({
                    "saved": True,
                    "report_id": saved.get("report_id"),
                    "link_token": saved.get("link_token"),
                    "duplicate_of": saved.get("duplicate_of"),
                    "locally_actionable": not missing,
                    "review_queued": category == "unclear_other",
                })
                active = saved.get("report_id") or active
            else:
                outcome["refused_reason"] = saved.get("error") or "save_failed"
                outcome["degraded"].append("save_failed")
            if "location" in missing and action == "log":
                pending = {"field": "location", "text": "Where is it?",
                           "asked_at": _now(state, deps), "turn_id": state.get("turn_id")}
            if action == "log":
                draft["capture_state"] = "captured" if missing else "locally_actionable"
                outcome["locally_actionable"] = not missing and outcome["saved"]

    elif is_detail:
        place = _place(draft)
        photo = next((item for item in draft.get("attachments") or []
                      if item.get("ref")), None)
        conn = reports_db.connect(deps.reports) if deps.reports else None
        try:
            link_data = tools.report_link(active, conn=conn)
            if link_data.get("ok") and photo:
                mime = (photo.get("features") or {}).get("mime") or "image/jpeg"
                tools.attach_photo_to_report(active, photo.get("ref"), mime, conn=conn)
            if link_data.get("ok") and place:
                link_data = tools.update_report_location(active, place, conn=conn)
        finally:
            if conn is not None:
                conn.close()
        if link_data.get("ok"):
            outcome.update({
                "action": "log", "saved": True, "report_id": active,
                "link_token": link_data.get("link_token"), "duplicate_of": None,
                "missing": [] if place or not draft.get("attachments") else ["location"],
                "locally_actionable": bool(place),
                "review_queued": category == "unclear_other",
            })
            draft["capture_state"] = "locally_actionable" if place else "captured"
            if not place and draft.get("attachments"):
                pending = {"field": "location", "text": "Where is it?",
                           "asked_at": _now(state, deps), "turn_id": state.get("turn_id")}
        else:
            outcome["refused_reason"] = link_data.get("error") or "update_failed"
            outcome["degraded"].append("update_failed")

    elif action == "ask":
        field = (plan.get("clarification") or {}).get("field") or "description"
        text = (plan.get("clarification") or {}).get("reason") or "Tell me a bit more."
        if "?" not in text:
            text = text.rstrip(".") + "?"
        pending = {"field": field, "text": text,
                   "asked_at": _now(state, deps), "turn_id": state.get("turn_id")}
        outcome["missing"] = [field]

    elif action == "answer":
        text = (state.get("inbound") or {}).get("text") or ""
        answer_conn = reports_db.connect(deps.reports) if deps.reports else None
        try:
            if active and prompts.is_status(text):
                link_data = tools.report_link(active, conn=answer_conn)
                if link_data.get("ok"):
                    report = tools.get_report_status(link_data.get("link_token"),
                                                     conn=answer_conn)
                    if report.get("ok"):
                        report["link"] = link_data.get("link")
                        report["category_id"] = category
                        outcome["status"] = report
                        outcome["report_id"] = active
                        outcome["link_token"] = link_data.get("link_token")
            if active and not outcome.get("status"):
                link_data = tools.report_link(active, conn=answer_conn)
                if link_data.get("ok"):
                    outcome["link_token"] = link_data.get("link_token")
        finally:
            if answer_conn is not None:
                answer_conn.close()
        question = (plan.get("fact_request") or {}).get("category_id") or "general"
        found = tools.find_category_facts(question)
        if found.get("ok"):
            outcome["facts"] = [
                {"fact": row.get("fact"), "url": row.get("url"),
                 "date": row.get("date_checked")}
                for row in found.get("facts") or []
            ][:4]
        if not outcome["facts"]:
            outcome["degraded"].append("no_facts")
        outcome["missing"] = [] if outcome["facts"] else ["description"]

    elif action == "escalate":
        escalation = plan.get("escalation") or {}
        outcome["refused_reason"] = escalation.get("kind") or "not_council"
        outcome["destination"] = escalation.get("destination")
        outcome["transport"] = "queued"

    violations = policy.check_outcome(outcome, draft, ctx)
    if violations:
        outcome["degraded"].extend(item["code"] for item in violations)
        if any(item["code"] in ("capture.lost", "capture.no_location") for item in violations):
            outcome["locally_actionable"] = False
        if any(item["code"] == "policy.answer_ungrounded" for item in violations):
            outcome["facts"] = []
    outcome["degraded"] = list(dict.fromkeys(outcome["degraded"]))
    return {
        "incident_draft": draft,
        "executed_outcome": outcome,
        "last_executed_outcome": outcome,
        "pending_question": pending,
        "active_incident_id": active,
    }


def _decision(draft, state):
    category = draft.get("category_id") or "unclear_other"
    book = prompts.playbook(category)
    return {
        "category_id": category,
        "category_label": book.get("label") or "report",
        "location": _place(draft) or "",
        "description": draft.get("description") or "",
        "severity": draft.get("severity"),
        "has_photo": bool(draft.get("attachments")),
        "capture_state": draft.get("capture_state"),
        "routing_status": draft.get("routing_status"),
        "location_mode": book.get("location_mode"),
    }


def _split(text, url):
    """Split a template into at most three bubbles, one report link and one source link."""
    bubbles = []
    source_url = None
    for line in [part.strip() for part in (text or "").splitlines() if part.strip()]:
        lowered = line.lower()
        if lowered.startswith("follow it:") or lowered.startswith("details:") \
                or "http://" in lowered or "https://" in lowered:
            match = re.search(r"https?://\S+", line)
            if match:
                candidate = match.group(0).rstrip(".,)")
                if "/r/" in candidate:
                    url = url or candidate
                else:
                    source_url = source_url or candidate
            continue
        bubbles.append(line)
    if len(bubbles) > 3:
        bubbles = bubbles[:2] + [bubbles[-1]]
    plan = []
    for index, line in enumerate(bubbles):
        purpose = "question" if "?" in line else ("action" if index == 0 else "tracking")
        plan.append({"purpose": purpose, "text": line[:300]})
    return plan, url, source_url


def compose(state, deps):
    plan = state.get("plan") or {}
    outcome = state.get("executed_outcome") or {}
    draft = state.get("incident_draft") or {}
    decision = _decision(draft, state)
    url = _link(outcome)
    text = ""
    challenge = bool(plan.get("retracted_claims")) or "challenge" in (plan.get("reason_codes") or [])
    inbound_text = ((state.get("inbound") or {}).get("text") or "").lower()

    if challenge:
        text = messages.challenge(decision, url,
                                  "flooding" if "flooding" in inbound_text else None)
    elif outcome.get("saved"):
        if outcome.get("duplicate_of"):
            text = messages.duplicate(decision, {"link": url})
        elif decision["category_id"] == "unclear_other":
            text = messages.captured(decision, {"link": url})
        elif "location" in (outcome.get("missing") or []):
            text = messages.need_location(decision, None,
                                          decision.get("location_mode") or "pin")
            if url:
                text = text + f"\nFollow it: {url}"
        else:
            text = messages.logged(decision, {"link": url})
    elif outcome.get("action") == "ask":
        field = (plan.get("clarification") or {}).get("field")
        if field == "location" or (field is None and "location" in (outcome.get("missing") or [])):
            text = messages.need_location(decision, None,
                                          decision.get("location_mode") or "pin")
            if url:
                text = text + f"\nFollow it: {url}"
        else:
            text = messages.unclear()
    elif outcome.get("status"):
        text = messages.status(outcome["status"])
    elif outcome.get("action") == "answer":
        if outcome.get("facts"):
            fact = outcome["facts"][0]
            text = messages.answered(fact.get("fact") or "")
        else:
            text = messages.no_answer(decision)
    elif outcome.get("action") == "escalate":
        if decision["category_id"] in ("not_council_trunk_road", "not_council_utility",
                                       "outside_southampton"):
            text = messages.not_council(decision)
        else:
            text = messages.handoff(decision, outcome.get("destination")
                                    or messages.contact_for(decision["category_id"]).get("page") or "")
    else:
        text = messages.sorry()

    bubbles, url, source_url = _split(text, url)
    destination = outcome.get("destination")
    if outcome.get("action") == "escalate" and isinstance(destination, str) \
            and destination.startswith(("http://", "https://")):
        source_url = destination
    if outcome.get("action") == "answer" and outcome.get("facts") \
            and not outcome.get("status"):
        fact = outcome["facts"][0]
        source_url = source_url or fact.get("url")
        checked = fact.get("date") or ""
        if source_url and len(bubbles) < 3:
            bubbles.append({"purpose": "tracking",
                            "text": f"Source: checked {checked}.".strip()})
    if not bubbles:
        bubbles = [{"purpose": "action", "text": messages.sorry()}]
    return {"bubble_plan": {"bubbles": bubbles, "url": url,
                             "source_url": source_url, "suppressed": False}}


def lint(state, deps):
    plan = state.get("bubble_plan") or {}
    outcome = state.get("executed_outcome") or {}
    ctx = context(deps, state)
    checked, problems = schemas.validate_bubble_plan(plan)
    if checked and checked.get("source_url") \
            and ctx.allowed_destinations \
            and checked["source_url"] not in ctx.allowed_destinations:
        plan = dict(plan)
        plan["source_url"] = None
        checked, problems = schemas.validate_bubble_plan(plan)
    texts = [item.get("text") for item in (checked or {}).get("bubbles") or []]
    claims = policy.check_bubbles(texts, outcome, ctx) if checked else []
    if problems or claims:
        safe = ("I've saved that here. It hasn't gone to the council yet."
                if outcome.get("saved") else messages.sorry())
        plan = {"bubbles": [{"purpose": "action", "text": safe}],
                "url": plan.get("url"), "source_url": plan.get("source_url"),
                "suppressed": False}
        state = dict(state)
        state["bubble_plan"] = plan
        checked, problems = schemas.validate_bubble_plan(plan)
        if problems:
            plan = {"bubbles": [{"purpose": "action", "text": messages.sorry()}],
                    "url": None, "source_url": None, "suppressed": False}
    return {"bubble_plan": plan,
            "degraded": list(dict.fromkeys((state.get("degraded") or [])
                                           + (["lint_fallback"] if problems else [])))}


def enqueue(state, deps):
    plan = state.get("bubble_plan") or {}
    if plan.get("suppressed"):
        return {"delivery_outbox_ids": [], "last_claims_sent": []}
    ids = []
    texts = []
    for index, bubble in enumerate(plan.get("bubbles") or []):
        text = bubble.get("text") or ""
        texts.append(text)
        if deps.outbox is not None:
            row = deps.outbox.enqueue(state.get("thread_id"), index, text,
                                      f"{state.get('turn_id')}:bubble:{index}")
            if row:
                ids.append(row)
        if deps.claims is not None:
            deps.claims.record(state.get("thread_id"), state.get("turn_id"), text)
    source = plan.get("source_url")
    if source and deps.outbox is not None:
        row = deps.outbox.enqueue(state.get("thread_id"), len(texts), source,
                                  f"{state.get('turn_id')}:source")
        if row:
            ids.append(row)
    return {"delivery_outbox_ids": ids, "last_claims_sent": texts}
