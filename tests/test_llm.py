import tempfile
from pathlib import Path
from unittest import TestCase

from maildigest.llm import CATEGORIES, OllamaSession

from .helpers import config_for


class FakeSession(OllamaSession):
    def __init__(self, config, responses):
        super().__init__(config)
        self.responses = iter(responses)

    def chat_json(self, system, prompt, schema):
        return next(self.responses)


class LlmTests(TestCase):
    def test_invalid_labels_are_safely_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(
                config_for(Path(temporary) / "x.sqlite3"),
                [{"summary": "Summary", "category": "Hacked", "priority": "extreme", "action_items": ["Do X"]}],
            )
            result = session.summarize_email(
                {"sender": "a@example.com", "subject": "Hi", "received_at": None, "body": "hello"}
            )
        self.assertEqual(result["category"], "Other")
        self.assertEqual(result["priority"], "low")
        self.assertIn(result["category"], CATEGORIES)

    def test_empty_digest_needs_no_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(config_for(Path(temporary) / "x.sqlite3"), [])
            result = session.summarize_digest([])
        self.assertEqual(result["action_items"], [])
        self.assertIn("No email", result["overview"])
