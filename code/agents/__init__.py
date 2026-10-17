"""Kerbside's agents (plans/agents.md). The triage agent is the orchestrator.

  from agents import ORCHESTRATOR, Turn
  outcome = ORCHESTRATOR.handle(Turn(sender="+44...", text="pothole on lawn road", chat=chat_guid))
  outcome.reply    the text to send (None means stay silent)
  outcome.trace    which agent did what, and how long it took

One orchestrator per process: it registers the map page's and the dashboard's
callbacks when it is built.
"""

from .memory import CONTACTS, PENDING, PLACES  # noqa: F401
from .triage_agent import Outcome, TriageAgent, Turn  # noqa: F401

ORCHESTRATOR = TriageAgent()
