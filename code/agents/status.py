"""Status agent: texts the resident when the council changes their report's status.

Triggered by the council dashboard (website.STATUS_HOOKS), never by a resident
message. "In review" and "resolved" are worth a text; going back to "new" is
not. It looks the resident up in the short-term contact memory by their hashed
reference: if they have not messaged since the last restart, nothing is sent.
The words come from the reply agent, the link is their own report page.
"""

import messages
import tools

from . import memory
from .photo import POOL
from .records import RecordsAgent
from .reply import ReplyAgent

WORTH_A_TEXT = ("in_review", "resolved")


class StatusAgent:
    name = "status"

    def __init__(self, records=None, reply=None):
        self.records = records or RecordsAgent()
        self.reply = reply or ReplyAgent()
        self.notify = None          # set by the channel: notify(chat, text)
        self._last = {}             # report id -> the status we last texted about

    def on_status_change(self, report_id, status):
        """Called after the council saves a status. Never blocks the dashboard."""
        if status not in WORTH_A_TEXT or self._last.get(report_id) == status:
            return
        self._last[report_id] = status
        POOL.submit(self._send, report_id, status)

    def message_for(self, report_id, status):
        """(chat, text) for this change, or None when there is no one to tell."""
        report = self.records.report(report_id)
        if not report:
            return None
        chat = memory.chat_for(report["reporter_ref"])
        if not chat:
            return None
        report["link"] = f"{tools.SITE_URL}/r/{report['link_token']}"
        report["status_text"] = tools.STATUS_TEXT.get(status, status)
        facts = {"category_id": report["category_id"], "location": report["location"],
                 "status_text": report["status_text"], "link": report["link"]}
        return chat, self.reply.say("status", facts, messages.status(report))

    def _send(self, report_id, status):
        try:
            found = self.message_for(report_id, status)
            if found and self.notify:
                chat, text = found
                print(f"[status] {report_id} -> {status}, texting the resident")
                self.notify(chat, text)
        except Exception as error:  # noqa: BLE001 - a dashboard click must never fail on this
            print(f"[status] could not text about {report_id}: {error}")
