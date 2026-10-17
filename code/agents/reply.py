"""Reply agent: writes every outgoing text from facts the other agents supply.

One model call (voice.py), checked against the facts and the style rules, with
the fixed template as the fallback on any doubt or delay. The model never
writes a link: it is appended here. Safety wording never comes through this
agent: the orchestrator sends the safety agent's fixed text as it is.
"""

import voice


class ReplyAgent:
    name = "reply"

    @staticmethod
    def facts(decision, saved=None, **extra):
        """The facts the voice may use. The link is appended by voice.say."""
        facts = {
            "category_id": decision.get("category_id"),
            "category_label": decision.get("category_label"),
            "location": decision.get("location"),
            "has_photo": bool(decision.get("has_photo")),
        }
        if saved and saved.get("link"):
            facts["link"] = saved["link"]
        facts.update({key: value for key, value in extra.items() if value})
        return facts

    @staticmethod
    def say(kind, facts, template):
        return voice.say(kind, facts, template)
