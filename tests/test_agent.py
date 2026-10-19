import tempfile
import unittest
from pathlib import Path

from sage.agent import Agent, calculate
from sage.config import Settings
from sage.provider import ProviderError
from sage.store import Store


class FakeProvider:
    available = True

    def __init__(self, messages):
        self.messages = iter(messages)
        self.requests = []
        self.tool_requests = []

    def complete(self, messages, settings, tools):
        self.requests.append(list(messages))
        self.tool_requests.append(list(tools))
        value = next(self.messages)
        if isinstance(value, Exception):
            raise value
        return value


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.store = Store(Path(self.tmp.name) / "test.db")
        self.session = self.store.session()

    def tearDown(self):
        self.tmp.cleanup()

    def test_multi_step_draft_and_history(self):
        provider = FakeProvider([
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "calculate", "arguments": '{"expression":"12 * 3"}'}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "2", "type": "function", "function": {"name": "save_draft", "arguments": '{"title":"Budget", "content":"Total: 36"}'}}]},
            {"role": "assistant", "content": "Saved the budget."},
        ])
        result = Agent(self.store, provider).respond(self.session, "Calculate and save a budget")
        self.assertEqual([t["tool"] for t in result["steps"]], ["calculate", "save_draft"])
        self.assertEqual(self.store.drafts(self.session)[0]["content"], "Total: 36")
        self.assertEqual(provider.requests[1][-1]["role"], "tool")
        self.assertEqual(len(self.store.history(self.session)), 2)

    def test_sessions_are_isolated(self):
        other = self.store.session()
        self.store.add_document(other, "private.txt", "Secret zoning data")
        self.store.save_draft(other, "private", "secret")
        self.assertEqual(self.store.documents(self.session), [])
        self.assertEqual(self.store.drafts(self.session), [])

    def test_read_document_is_scoped_and_citable(self):
        agent = Agent(self.store)
        doc_id = self.store.add_document(self.session, "notes.md", "A" * 1100 + "Budget 250")
        result = agent.execute(self.session, "read_document", {"document_id": doc_id, "section": 2}, Settings())
        self.assertEqual(result["passages"][0]["source"], doc_id + ":2")
        self.assertIn("Budget 250", result["passages"][0]["text"])
        other = self.store.session()
        with self.assertRaises(ValueError):
            agent.execute(other, "read_document", {"document_id": doc_id}, Settings())

    def test_permissions_enforced_by_executor(self):
        agent = Agent(self.store)
        with self.assertRaises(ValueError):
            agent.execute(self.session, "save_draft", {"title": "x", "content": "x"}, Settings(allow_drafts=False))
        with self.assertRaises(ValueError):
            agent.execute(self.session, "shell", {"command": "echo bad"}, Settings())

    def test_offline_retrieval_has_real_sources(self):
        doc_id = self.store.add_document(self.session, "notes.txt", "The research budget is 250 dollars.")
        provider = type("Offline", (), {"available": False})()
        result = Agent(self.store, provider).respond(self.session, "research budget")
        self.assertEqual(result["mode"], "local-search")
        self.assertIn(doc_id, result["answer"])

    def test_provider_failure_preserves_history(self):
        self.store.append(self.session, "user", "Previous work")
        response = Agent(self.store, FakeProvider([ProviderError("Unavailable")])).respond(self.session, "Hello")
        self.assertEqual(response["mode"], "error")
        self.assertEqual(self.store.history(self.session)[0]["content"], "Previous work")

    def test_memory_opt_out(self):
        self.store.append(self.session, "user", "Private old context")
        provider = FakeProvider([{"role": "assistant", "content": "Hello"}])
        Agent(self.store, provider).respond(self.session, "Hello", {"remember": False})
        self.assertEqual(len(self.store.history(self.session)), 1)
        self.assertNotIn("Private old context", str(provider.requests))

    def test_calculator_rejects_code_and_large_values(self):
        self.assertEqual(calculate("(12 + 3) / 5"), 3)
        for expression in ["__import__('os')", "2 ** 100000", "True + 1", "1 / 0", "1e309"]:
            with self.assertRaises((ValueError, ZeroDivisionError)):
                calculate(expression)

    def test_settings_validation(self):
        for value in [{"max_steps": 100}, {"remember": "false"}, {"max_steps": 2.5}, {"base_url": "http://bad"}]:
            with self.assertRaises(ValueError):
                Settings.parse(value)

    def test_step_budget(self):
        provider = FakeProvider([{"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "calculate", "arguments": '{"expression":"1+1"}'}}]}])
        result = Agent(self.store, provider).respond(self.session, "Calculate", {"max_steps": 1})
        self.assertIn("step limit", result["answer"])
        self.assertEqual(len(provider.requests), 1)


if __name__ == "__main__":
    unittest.main()
