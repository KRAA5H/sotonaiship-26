"""Category agents: the specialists triage hands a report to. Code, never a model call.

One shared base class reads each category's "agent" block in categories.json:

  location_mode     pin      a map link, a typed street or a shared location
                    address  a house number and street (bins, housing), never a pin
                    handoff  the council's own form, nothing saved (neighbour problems,
                             so we never log someone's home)
  dup_window_days   how long an open report blocks a repeat at the same place
  severity_keywords words that raise (or, when triage could not tell, lower) severity

Three are deeper, because they are what residents send most: fly-tipping
(hazardous waste, private land), potholes (road or pavement, harm) and
graffiti (offensive content jumps the queue).

What every agent returns to the orchestrator, as decision["agent"]: the
location mode, the follow-up question, the duplicate window, the owning team
(dashboard only, never said to a resident) and the form link.
"""

import re
from functools import lru_cache

import tools

DEFAULT_SEVERITY = "medium"   # a council report never goes out with no severity (TODO 1.5)


def _words(text):
    return " " + " ".join(re.findall(r"[a-z0-9']+", (text or "").lower())) + " "


def _has(flat, phrase):
    return f" {' '.join(re.findall(r'[a-z0-9]+', phrase.lower()))} " in flat.replace("'", "")


class CategoryAgent:
    deep = False

    def __init__(self, category):
        self.category = category
        self.id = category["id"]
        self.config = category.get("agent") or {}

    # -- what the orchestrator asks of every specialist ----------------------
    @property
    def location_mode(self):
        return self.config.get("location_mode") or "pin"

    @property
    def follow_up(self):
        questions = self.category.get("follow_up_questions") or []
        return questions[0] if questions else "Where exactly is it?"

    @property
    def form_url(self):
        return self.category.get("official_form_url") or ""

    def review(self, decision, text=""):
        """The decision with this category's rules applied, plus the agent's notes."""
        decision = dict(decision)
        flat = _words(" ".join([text or "", decision.get("description") or ""]))
        severity, why = self.severity(decision.get("severity"), flat)
        if decision.get("outcome") == "council_report":
            decision["severity"] = severity
        notes = self.notes(flat)
        decision["agent"] = {
            "category": self.id,
            "deep": self.deep,
            "location_mode": self.location_mode,
            "handoff": self.location_mode == "handoff",
            "follow_up": self.follow_up,
            "dup_window_days": tools.duplicate_window_days(self.id),
            "team": self.category.get("team"),           # dashboard only
            "form_url": self.form_url,
            "severity_reason": why,
            "notes": notes,
        }
        return decision

    # -- the parts a specialist can sharpen ----------------------------------
    def severity(self, current, flat):
        """(severity, reason). Keywords only ever raise; 'low' words only fill a gap."""
        words = self.config.get("severity_keywords") or {}
        high = next((w for w in words.get("high") or [] if _has(flat, w)), None)
        if high:
            return "high", f"mentions {high}"
        if current in tools.SEVERITIES:
            return current, "triage"
        low = next((w for w in words.get("low") or [] if _has(flat, w)), None)
        if low:
            return "low", f"mentions {low}"
        return DEFAULT_SEVERITY, "default"

    def notes(self, flat):
        """Details the council will want, said in plain words for the dashboard."""
        notes = []
        detail_words = self.config.get("detail_words") or []
        if detail_words and not any(_has(flat, w) for w in detail_words):
            notes.append("missing: " + (self.config.get("detail_question") or "detail"))
        pattern = self.config.get("detail_pattern")
        if pattern and not re.search(pattern, flat.upper()):
            notes.append("missing: " + (self.config.get("detail_question") or "detail"))
        return notes


class FlyTippingAgent(CategoryAgent):
    deep = True
    HAZARDS = ("asbestos", "needle", "needles", "syringe", "chemical", "chemicals", "paint", "oil",
               "gas bottle", "gas canister", "batteries", "clinical waste")
    PRIVATE = ("my garden", "front garden", "back garden", "driveway", "private land", "my property")

    def notes(self, flat):
        notes = super().notes(flat)
        hazards = [h for h in self.HAZARDS if _has(flat, h)]
        if hazards:
            notes.append("hazardous: " + ", ".join(hazards))
        if any(_has(flat, p) for p in self.PRIVATE):
            notes.append("may be private land: owner or occupier clears it")
        return notes


class PotholeAgent(CategoryAgent):
    deep = True

    def notes(self, flat):
        notes = super().notes(flat)
        if any(_has(flat, w) for w in ("pavement", "footpath", "path")):
            notes.append("surface: pavement")
        elif any(_has(flat, w) for w in ("cycle lane", "bike lane", "cycle path")):
            notes.append("surface: cycle lane")
        elif any(_has(flat, w) for w in ("road", "lane", "street", "junction", "carriageway")):
            notes.append("surface: road")
        if any(_has(flat, w) for w in ("school", "bus route", "main road", "crossing")):
            notes.append("busy place: raised")
        if any(_has(flat, w) for w in ("burst", "tyre", "wheel", "damaged", "fell", "injured", "claim")):
            notes.append("possible damage or injury claim")
        return notes


class GraffitiAgent(CategoryAgent):
    deep = True

    def notes(self, flat):
        notes = super().notes(flat)
        words = (self.config.get("severity_keywords") or {}).get("high") or []
        if any(_has(flat, w) for w in words):
            notes.append("offensive: council aims to remove within 1 working day")
        if any(_has(flat, w) for w in ("house", "shop", "private", "my wall", "my fence")):
            notes.append("may be private property: owner or police (criminal damage)")
        return notes


SPECIALISTS = {"fly_tipping": FlyTippingAgent, "pothole": PotholeAgent,
               "graffiti_flyposting": GraffitiAgent}


@lru_cache(maxsize=None)
def agent_for(category_id):
    """The specialist for this category, or None for an unknown id."""
    category = tools._rulebook()[0].get(category_id)
    if not category:
        return None
    return SPECIALISTS.get(category_id, CategoryAgent)(category)
