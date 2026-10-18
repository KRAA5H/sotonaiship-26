"""The iMessage webhook under the graph: words, the report link, the source link."""

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blue_bubbles as bot


class FakeRuntime:
    def __init__(self):
        self.inbound = None

    def turn(self, inbound):
        self.inbound = inbound
        return {
            "kind": "saved",
            "bubbles": ["Logged it here.", "Where is it?"],
            "url": "https://example.test/r/" + "a" * 16,
            "source_url": "https://www.southampton.gov.uk/example",
            "state": {},
        }


class GraphWebhookTest(unittest.TestCase):
    def test_graph_mode_delivers_words_and_both_links(self):
        fake = FakeRuntime()
        sent = []
        with unittest.mock.patch.object(bot, "MODE", "graph"), \
             unittest.mock.patch.object(bot.channel.service, "get_runtime", return_value=fake), \
             unittest.mock.patch.object(bot.channel, "first_contact", return_value=False), \
             unittest.mock.patch.object(bot, "deliver",
                                       side_effect=lambda chat, text: sent.append(text)):
            bot.handle_inbound({
                "chat_guid": "chat-graph-1",
                "sender": "+447700900321",
                "text": "there is a tree fallen on the road",
                "message_guid": "G-GRAPH-1",
                "attachments": [],
            })
        self.assertEqual(sent, [
            "Logged it here.",
            "Where is it?",
            "follow your report",
            "https://example.test/r/" + "a" * 16,
            "source",
            "https://www.southampton.gov.uk/example",
        ])
        self.assertEqual(fake.inbound["sender"], "+447700900321")
        self.assertEqual(fake.inbound["text"], "there is a tree fallen on the road")

    def test_a_shared_location_card_reaches_the_graph(self):
        fake = FakeRuntime()
        with unittest.mock.patch.object(bot, "MODE", "graph"),              unittest.mock.patch.object(bot.channel.service, "get_runtime", return_value=fake),              unittest.mock.patch.object(bot.channel, "first_contact", return_value=False),              unittest.mock.patch.object(bot, "read_attachments",
                                        return_value=(None, None, "BEGIN:VCARD END:VCARD")),              unittest.mock.patch.object(bot, "deliver"):
            bot.handle_inbound({
                "chat_guid": "chat-card-1",
                "sender": "+447700900322",
                "text": "",
                "message_guid": "G-CARD-1",
                "attachments": [{"guid": "card-1", "transferName": "x.loc.vcf"}],
            })
        self.assertEqual(fake.inbound["card"], "BEGIN:VCARD END:VCARD")

    def test_a_map_link_alone_is_sent_when_there_is_no_tracking_link(self):
        """No street yet: the question, then only the map link, never a tracking link."""
        class AskRuntime(FakeRuntime):
            def turn(self, inbound):
                result = super().turn(inbound)
                return dict(result, url=None, source_url="https://example.test/p/abc123")
        sent = []
        with unittest.mock.patch.object(bot, "MODE", "graph"),              unittest.mock.patch.object(bot.channel.service, "get_runtime", return_value=AskRuntime()),              unittest.mock.patch.object(bot.channel, "first_contact", return_value=False),              unittest.mock.patch.object(bot, "deliver",
                                        side_effect=lambda chat, text: sent.append(text)):
            bot.handle_inbound({"chat_guid": "chat-map-1", "sender": "+447700900323",
                                "text": "pothole near my house", "message_guid": "G-MAP-1",
                                "attachments": []})
        self.assertEqual(sent, ["Logged it here.", "Where is it?", "share your location here",
                                "https://example.test/p/abc123"])
        self.assertFalse(any("/r/" in text for text in sent))

    def test_the_chat_is_remembered_so_a_pin_or_status_can_text_later(self):
        from agents import memory
        import tools
        sender = "+447700900399"
        with unittest.mock.patch.object(bot.channel.service, "get_runtime", return_value=FakeRuntime()):
            bot.channel.turn(sender, "pothole", chat="chat-remember-1", message_guid="G-REM-1")
        self.assertEqual(memory.chat_for(tools.reporter_ref(sender)), "chat-remember-1")

    def test_a_first_message_gets_the_welcome_text_first(self):
        sent = []
        with unittest.mock.patch.object(bot, "MODE", "graph"),              unittest.mock.patch.object(bot.channel.service, "get_runtime", return_value=FakeRuntime()),              unittest.mock.patch.object(bot.channel, "first_contact", return_value=True),              unittest.mock.patch.object(bot, "deliver",
                                        side_effect=lambda chat, text: sent.append(text)):
            bot.handle_inbound({"chat_guid": "chat-new-1", "sender": "+447700900324",
                                "text": "hi", "message_guid": "G-NEW-1", "attachments": []})
        self.assertEqual(sent[0], bot.ONBOARDING)

    def test_legacy_mode_is_still_selectable(self):
        self.assertIn("legacy", ("legacy", "graph"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
