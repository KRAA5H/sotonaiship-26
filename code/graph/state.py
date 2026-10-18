"""Graph state. Plain TypedDicts, JSON-serialisable, no imports from the rest of the repo.

These shapes are the contract every later node trusts. Constructors set the honest
defaults: a captured incident, an unreviewed route, and an empty location.
"""

from typing import TypedDict

MAX_RECENT_MESSAGES = 12


class Location(TypedDict, total=False):
    text: str
    street: str | None
    area: str | None
    postcode: str | None
    provenance: str        # text | pin | gps | postcode | none
    ambiguous: bool


class Attachment(TypedDict, total=False):
    kind: str              # photo
    ref: str               # "guid:..."
    features: dict | None


class CategoryCandidate(TypedDict, total=False):
    id: str
    confidence: float


class IncidentDraft(TypedDict, total=False):
    id: str | None
    capture_state: str
    routing_status: str
    category_candidates: list[CategoryCandidate]
    category_id: str | None
    description: str
    location: Location
    attachments: list[Attachment]
    severity: str | None
    evidence: list[dict]
    retracted: list[dict]
    version: int


class InboundMessage(TypedDict, total=False):
    sender: str
    chat: str
    text: str
    message_guid: str
    image_ref: str | None
    photo_ref: str | None
    card: str


class Message(TypedDict, total=False):
    role: str              # resident | agent
    text: str
    at: str


class PendingQuestion(TypedDict, total=False):
    field: str
    text: str
    asked_at: str
    turn_id: str


class ExecutedOutcome(TypedDict, total=False):
    action: str
    report_id: str | None
    link_token: str | None
    submitted: bool
    duplicate_of: str | None
    locally_actionable: bool
    missing: list[str]
    facts: list[dict]      # {"fact", "url", "date"}
    review_queued: bool
    transport: str         # queued | sent | failed | ambiguous
    degraded: list[str]
    saved: bool
    refused_reason: str | None
    playbook_version: str | None
    destination: str | None
    status: dict | None
    location_url: str | None
    task_url: str | None


class ThreadState(TypedDict, total=False):
    thread_id: str
    turn_id: str
    inbound: InboundMessage
    recent_messages: list[Message]
    conversation: list[Message]
    task: dict | None
    active_incident_id: str | None
    incident_draft: IncidentDraft
    pending_question: PendingQuestion | None
    profile: dict
    last_claims_sent: list[str]
    last_executed_outcome: ExecutedOutcome | None
    candidate_services: list[str]
    selected_specialist: str | None
    specialist_results: list[dict]
    plan: dict | None
    violations: list[dict]
    executed_outcome: ExecutedOutcome | None
    bubble_plan: dict | None
    review_queued: bool
    repair_count: int
    specialist_call_count: int
    delivery_outbox_ids: list[str]
    degraded: list[str]
    short_circuit: bool
    emergency: bool
    suppressed: bool
    model_calls: int


_LOCATION_DEFAULTS = {
    "text": "",
    "street": None,
    "area": None,
    "postcode": None,
    "provenance": "none",
    "ambiguous": False,
}


def empty_location() -> Location:
    return dict(_LOCATION_DEFAULTS)


def new_incident_draft(description: str = "", location: dict | None = None) -> IncidentDraft:
    place = empty_location()
    if isinstance(location, dict):
        place.update({key: value for key, value in location.items() if key in place})
    return {
        "id": None,
        "capture_state": "captured",
        "routing_status": "needs_review",
        "category_candidates": [],
        "category_id": None,
        "description": description,
        "location": place,
        "attachments": [],
        "severity": None,
        "evidence": [],
        "retracted": [],
        "version": 0,
    }


def new_thread_state(thread_id: str, turn_id: str,
                     inbound: dict | None = None) -> ThreadState:
    return {
        "thread_id": thread_id,
        "turn_id": turn_id,
        "inbound": inbound or {},
        "recent_messages": [],
        "conversation": [],
        "task": None,
        "active_incident_id": None,
        "incident_draft": new_incident_draft(),
        "pending_question": None,
        "profile": {},
        "last_claims_sent": [],
        "last_executed_outcome": None,
        "candidate_services": [],
        "selected_specialist": None,
        "specialist_results": [],
        "plan": None,
        "violations": [],
        "executed_outcome": None,
        "bubble_plan": None,
        "review_queued": False,
        "repair_count": 0,
        "specialist_call_count": 0,
        "delivery_outbox_ids": [],
        "degraded": [],
        "short_circuit": False,
        "emergency": False,
        "suppressed": False,
        "model_calls": 0,
    }


def new_executed_outcome(action: str, saved: bool = False,
                         refused_reason: str | None = None) -> ExecutedOutcome:
    return {
        "action": action,
        "report_id": None,
        "link_token": None,
        "submitted": False,
        "duplicate_of": None,
        "locally_actionable": False,
        "missing": [],
        "facts": [],
        "review_queued": False,
        "transport": "queued",
        "degraded": [],
        "saved": saved,
        "refused_reason": refused_reason,
        "playbook_version": None,
    }
