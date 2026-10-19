import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from sage.config import Settings
from sage.provider import ChatProvider, ProviderError


class ProviderTests(unittest.TestCase):
    def test_application_user_agent_and_tool_payload(self):
        provider = ChatProvider()
        provider.key = "test-only-placeholder"
        response = io.BytesIO(json.dumps({"choices": [{"message": {"role": "assistant", "content": "Ready"}}]}).encode())
        with patch("urllib.request.urlopen", return_value=response) as request:
            result = provider.complete([{"role": "user", "content": "Hello"}], Settings(), [])
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_header("User-agent"), "Sage/1.0")
        self.assertEqual(sent.get_header("Authorization"), "Bearer test-only-placeholder")
        self.assertEqual(result["content"], "Ready")
        self.assertEqual(json.loads(sent.data)["model"], Settings().model)

    def test_http_errors_do_not_expose_credentials(self):
        provider = ChatProvider()
        provider.key = "test-only-placeholder"
        failure = urllib.error.HTTPError(provider.base_url, 403, "Forbidden", {}, io.BytesIO(b"private error detail"))
        with patch("urllib.request.urlopen", side_effect=failure):
            with self.assertRaises(ProviderError) as raised:
                provider.complete([], Settings(), [])
        self.assertIn("403", str(raised.exception))
        self.assertNotIn(provider.key, str(raised.exception))
        self.assertNotIn("private error detail", str(raised.exception))
