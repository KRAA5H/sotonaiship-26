"""Four small specialists over the checked council catalogue.

They do not talk to the resident. They return required fields, eligibility and
evidence. Eligibility is a rule lookup, not a model guess. Nothing is invented.
"""

from .store import CouncilStore

SPECIALISTS = {
    "permit": {
        "name": "highways_parking",
        "group": "highways",
        "service_id": "permit",
        "required": ("name", "address", "vehicle"),
    },
    "council_tax": {
        "name": "housing_money",
        "group": "housing",
        "service_id": "council_tax",
        "required": ("name", "address"),
    },
    "bins": {
        "name": "waste_bins",
        "group": "waste",
        "service_id": "bins",
        "required": ("address",),
    },
}

GROUP_SPECIALISTS = {
    "cleansing": "street_scene",
    "highways": "highways_parking",
    "waste": "waste_bins",
    "housing": "housing_money",
}


def prepare(kind, fields, store=None):
    """Return the specialist result for a task kind and the fields collected so far."""
    spec = SPECIALISTS.get(kind)
    if not spec:
        return {
            "specialist": "unknown",
            "service_id": kind,
            "fit": "uncertain",
            "required_fields": [],
            "missing": [],
            "eligibility": {"status": "unknown", "reasons": ["no specialist for this kind"]},
            "evidence": [],
            "form_url": None,
            "suggested_question": None,
            "routing_status": "needs_review",
            "reason_codes": ["specialist.unknown"],
        }
    store = store or CouncilStore()
    service_id = spec["service_id"]
    fields = {key: str(value).strip() for key, value in (fields or {}).items()
              if value is not None and str(value).strip()}
    missing = [field for field in spec["required"] if not fields.get(field)]
    evidence = store.evidence(service_id) if hasattr(store, "evidence") else []
    rules = store.rules(service_id) if hasattr(store, "rules") else []
    service = store.service(service_id) if hasattr(store, "service") else None
    form = store.form(service_id) if hasattr(store, "form") else None

    reasons = []
    status = "unknown"
    if missing:
        reasons.append("Missing required fields: " + ", ".join(missing))
    elif kind == "permit":
        reasons.append("The property register and permit entitlement are not exposed. "
                       "Eligibility cannot be confirmed from the public page.")
    elif kind == "council_tax":
        reasons.append("The household composition that decides the discount is not "
                       "checked yet. Eligibility cannot be confirmed.")
    elif kind == "bins":
        reasons.append("The collection day needs an address lookup or an approved "
                       "schedule. The public page is a search, not an API.")

    if rules:
        for rule in rules:
            reasons.append(rule.get("explanation") or rule.get("condition") or "")
    reasons = [reason for reason in reasons if reason]

    return {
        "specialist": spec["name"],
        "group": spec["group"],
        "service_id": service_id,
        "fit": "uncertain" if status == "unknown" else "supported",
        "required_fields": list(spec["required"]),
        "missing": missing,
        "eligibility": {
            "status": "fail" if status == "fail" else status,
            "reasons": reasons,
        },
        "evidence": [
            {"evidence_id": row.get("evidence_id"), "fact": row.get("fact"),
             "url": row.get("url"), "date": row.get("checked_date"),
             "caveat": row.get("caveat")}
            for row in evidence
        ],
        "form_url": (form or {}).get("url") or (service or {}).get("form_url")
                    or (service or {}).get("page_url"),
        "suggested_question": (f"What is your {missing[0]}?" if missing else None),
        "routing_status": "needs_review" if status == "unknown" else "verified",
        "reason_codes": ["specialist.unknown"] if status == "unknown" else [],
    }


def for_group(group, store=None):
    name = GROUP_SPECIALISTS.get(group, "street_scene")
    services = [s for s in (store.services() if store else []) if s.get("group_name") == group]
    return {"specialist": name, "group": group, "services": services}
