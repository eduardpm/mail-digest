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
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class LlmTests(TestCase):
    def test_invalid_labels_are_safely_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(
                config_for(Path(temporary) / "x.sqlite3"),
                [{
                    "summary": "Acme released a new compiler that cuts build times in half for large Rust projects, according to its published benchmarks.",
                    "category": "Hacked",
                    "priority": "extreme",
                    "action_items": [
                        "Acme compiler launches — it targets substantially faster Rust builds.",
                        "Published benchmarks claim a 50% reduction in compilation time.",
                    ],
                }],
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

    def test_email_placeholder_response_is_retried(self) -> None:
        valid = {
            "summary": "OpenCompute introduced a new inference engine that reduces memory use for local language models while retaining model accuracy.",
            "category": "AI & ML",
            "priority": "high",
            "action_items": [
                "OpenCompute inference engine launches — local models require less memory.",
                "The published tests retain accuracy — smaller machines can run useful models.",
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(
                config_for(Path(temporary) / "x.sqlite3"),
                [{"summary": "1-2 sentences", "category": "Other", "priority": "low", "action_items": []}, valid],
            )
            result = session.summarize_email(
                {"sender": "news@example.com", "subject": "News", "received_at": None, "body": "body"}
            )
        self.assertEqual(result["summary"], valid["summary"])

    def test_digest_placeholder_response_is_retried(self) -> None:
        invalid = {
            "overview": "2-3 crisp sentences",
            "highlights": ["5-10 most important stories", "each story is a string"],
            "action_items": [],
            "categories": [{"name": "string", "count": 1, "summary": "1-2 sentences"}],
        }
        valid = {
            "overview": "Acme launched a faster Rust compiler, while OpenCompute reduced the memory needed for local AI inference. Both releases focus on making developer workloads more efficient.",
            "highlights": [
                "Acme launches a compiler designed to halve Rust build times.",
                "OpenCompute lowers memory requirements for local AI inference.",
                "Published benchmarks focus on developer productivity and efficient hardware use.",
            ],
            "action_items": [],
            "categories": [{"name": "Developer Tools", "count": 2, "summary": "New compiler and inference tooling target faster, leaner local development workflows."}],
        }
        entries = [{
            "sender": "news@example.com", "subject": "News", "category": "Developer Tools",
            "priority": "high", "summary": valid["overview"], "action_items": valid["highlights"],
        }]
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(config_for(Path(temporary) / "x.sqlite3"), [invalid, valid])
            result = session.summarize_digest(entries)
        self.assertEqual(result["overview"], valid["overview"])

    def test_email_meta_summary_is_rebuilt_from_concrete_points(self) -> None:
        invalid = {
            "summary": "This email contains untrusted data and I need to summarize it.",
            "category": "Developer Tools",
            "priority": "high",
            "action_items": [
                "Acme launches its Rust compiler — published tests show faster builds.",
                "Linux support ships at launch — teams can test it in existing pipelines.",
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(config_for(Path(temporary) / "x.sqlite3"), [invalid] * 3)
            result = session.summarize_email(
                {"sender": "news@example.com", "subject": "News", "received_at": None, "body": "body"}
            )
        self.assertIn("Acme launches", result["summary"])
        self.assertNotIn("untrusted data", result["summary"])

    def test_malformed_digest_response_is_retried(self) -> None:
        valid = {
            "overview": "Acme launched a faster Rust compiler, while OpenCompute reduced the memory needed for local AI inference. Both releases focus on making developer workloads more efficient.",
            "highlights": [
                "Acme launches a compiler designed to halve Rust build times.",
                "OpenCompute lowers memory requirements for local AI inference.",
                "Published benchmarks focus on developer productivity and efficient hardware use.",
            ],
            "action_items": [],
            "categories": [{"name": "Developer Tools", "count": 2, "summary": "New compiler and inference tooling target faster, leaner local development workflows."}],
        }
        entries = [{
            "sender": "news@example.com", "subject": "News", "category": "Developer Tools",
            "priority": "high", "summary": valid["overview"], "action_items": valid["highlights"],
        }]
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(
                config_for(Path(temporary) / "x.sqlite3"),
                [RuntimeError("invalid structured response"), valid],
            )
            result = session.summarize_digest(entries)
        self.assertEqual(result["overview"], valid["overview"])

    def test_generic_digest_falls_back_to_concrete_source_points(self) -> None:
        invalid = {
            "overview": "2-3 crisp sentences",
            "highlights": ["5-10 most important stories"],
            "action_items": [],
            "categories": [{"name": "string", "count": 1, "summary": "1-2 sentences"}],
        }
        entries = [{
            "sender": "news@example.com", "subject": "News", "category": "Developer Tools",
            "priority": "high",
            "summary": "Acme released compiler and inference tools aimed at making local development faster and more efficient.",
            "action_items": [
                "Story — Acme launches a compiler designed to halve Rust build times.",
                "OpenCompute lowers memory requirements for local AI inference.",
                "Published benchmarks focus on developer productivity and efficient hardware use.",
            ],
        }]
        with tempfile.TemporaryDirectory() as temporary:
            session = FakeSession(config_for(Path(temporary) / "x.sqlite3"), [invalid, invalid])
            result = session.summarize_digest(entries)
        self.assertIn("Acme launches", result["overview"])
        self.assertEqual(len(result["highlights"]), 3)
        self.assertFalse(result["highlights"][0].startswith("Story"))
