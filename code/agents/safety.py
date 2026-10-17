"""Safety agent: runs first on every message, and its words are never reworded.

Rules first, no model: an emergency gets "Call 999 now" before anything else
happens, a threat gets a short fixed boundary, and obvious spam gets silence.
After triage it is the second net: a high-severity report that describes
someone hurt is turned into the emergency reply too.
"""

import re

import messages
import triage

EMERGENCY = triage.EMERGENCY_WORDS
# Someone hurt, as triage describes it. Only checked when triage says "high".
HURT = re.compile(
    r"\b(injured|injury to (a|the) (person|child|man|woman)|bleeding|unconscious|collapsed|"
    r"not breathing|trapped|electrocuted|hit by a car|knocked (down|over|off))\b",
    re.IGNORECASE,
)
THREAT = re.compile(
    r"\b(i('ll| will| am going to|'m going to|m gonna| gonna)\s+(kill|hurt|stab|shoot|attack)|"
    r"bomb (the|your)|burn (the|your) \w+( \w+)? down)\b",
    re.IGNORECASE,
)
URL = re.compile(r"https?://\S+", re.IGNORECASE)
MAPS = re.compile(r"maps\.apple\.com|google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/maps|geo:", re.IGNORECASE)
SPAM_URLS = 3
SPAM_CHARS = 3000


class SafetyAgent:
    name = "safety"

    def check(self, text):
        """{"kind", "reply"} when the message must stop here, else None. reply None means silence."""
        text = text or ""
        if EMERGENCY.search(text):
            return {"kind": "emergency", "reply": messages.emergency()}
        if THREAT.search(text):
            return {"kind": "threat", "reply": messages.threat()}
        links = [url for url in URL.findall(text) if not MAPS.search(url)]
        if len(links) >= SPAM_URLS or len(text) > SPAM_CHARS:
            return {"kind": "spam", "reply": None}
        return None

    def second_net(self, decision, text):
        """Triage marked it high and the words describe someone hurt: 999 first."""
        if decision.get("severity") != "high":
            return None
        if HURT.search(" ".join([text or "", decision.get("description") or ""])):
            return {"kind": "emergency", "reply": messages.emergency()}
        return None
