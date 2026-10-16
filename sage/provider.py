"""A small server-side chat-completions adapter, also usable with a local compatible server."""
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


class ChatProvider:
    def __init__(self):
        self.base_url = os.environ.get("SAGE_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        self.key = os.environ.get("SAGE_API_KEY") or os.environ.get("GroqAPIKey") or os.environ.get("GROQ_API_KEY", "")

    @property
    def available(self):
        return bool(self.key) or os.environ.get("SAGE_LOCAL_MODEL") == "1"

    def complete(self, messages, settings, tools):
        payload = {"model": settings.model, "messages": messages, "temperature": settings.temperature,
                   "max_tokens": settings.max_tokens}
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        request = urllib.request.Request(self.base_url + "/chat/completions", json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            message = data["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("Invalid message")
            if message.get("content") is not None and not isinstance(message["content"], str):
                raise ValueError("Invalid message content")
            return {"role": "assistant", **{k: message[k] for k in ("content", "tool_calls") if k in message}}
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Model service returned HTTP {exc.code}. Check the model, credentials, and quota.") from None
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, IndexError) as exc:
            raise ProviderError("Could not obtain a valid model response. Check your provider configuration and connection.") from exc
