"""Adapters migrated from the original Sage capabilities without legacy import side effects."""
from datetime import datetime, timezone
import io
import math
import os
from urllib.parse import urlencode, urlsplit


class IntegrationError(ValueError):
    pass


def capabilities():
    import importlib.util
    return {
        "web_search": bool(importlib.util.find_spec("ddgs")),
        "image_generation": bool(image_key()) and bool(importlib.util.find_spec("huggingface_hub")),
        "image_setup": "Set HuggingFaceAPIKey or SAGE_IMAGE_API_KEY in .env to enable image generation.",
    }


def image_key():
    return os.environ.get("SAGE_IMAGE_API_KEY") or os.environ.get("HuggingFaceAPIKey") or os.environ.get("HF_TOKEN", "")


def public_url(url):
    import ipaddress
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        if parsed.hostname.lower() in {"localhost", "localhost.localdomain"} or parsed.hostname.lower().endswith((".local", ".internal")):
            return False
        try:
            return ipaddress.ip_address(parsed.hostname).is_global
        except ValueError:
            return "." in parsed.hostname
    except ValueError:
        return False


def search_web(query, limit=4):
    if not query.strip() or len(query) > 500:
        raise IntegrationError("Search query must contain 1–500 characters")
    try:
        from ddgs import DDGS
        results = DDGS(timeout=15).text(query, max_results=limit)
    except ImportError as exc:
        raise IntegrationError("Install requirements-core.txt to enable web search") from exc
    except Exception as exc:
        raise IntegrationError("Search could not complete. The search service may be unavailable or rate-limited; try again later.") from exc
    output = []
    for result in results:
        url = result.get("href") or result.get("url", "")
        if public_url(url) and not any(item["url"] == url for item in output):
            output.append({"title": str(result.get("title", url))[:250], "url": url,
                           "text": str(result.get("body", ""))[:900], "kind": "web",
                           "retrieved_at": datetime.now(timezone.utc).isoformat()})
        if len(output) >= limit:
            break
    return output


def generate_image(prompt, model):
    """Modern replacement for Backend/ImageGeneration.py's retired inference endpoint."""
    key = image_key()
    if not key:
        raise IntegrationError("Image generation needs a Hugging Face token. Set HuggingFaceAPIKey or SAGE_IMAGE_API_KEY in .env, then restart Sage. Your Groq text key cannot generate images.")
    if not 1 <= len(prompt.strip()) <= 2000:
        raise IntegrationError("Image prompt must contain 1–2,000 characters")
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(provider="auto", api_key=key, timeout=90)
        image = client.text_to_image(prompt, model=model)
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        if len(buffer.getvalue()) > 10_000_000:
            raise IntegrationError("Generated image exceeds the 10 MB workspace limit")
        return buffer.getvalue()
    except IntegrationError:
        raise
    except ImportError as exc:
        raise IntegrationError("Install requirements-core.txt to enable the image provider") from exc
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise IntegrationError(f"Image provider could not complete the request{f' (HTTP {status})' if status else ''}. Check token permissions, model access, credits, or try a different image model.") from exc


def validate_chart(spec):
    if not isinstance(spec, dict) or set(spec) - {"title", "type", "labels", "values", "unit", "source_ids"}:
        raise ValueError("Unsupported chart fields")
    if not isinstance(spec.get("type"), str) or spec.get("type") not in {"bar", "line", "pie"}:
        raise ValueError("Choose a bar, line, or pie chart")
    labels, values = spec.get("labels"), spec.get("values")
    if not isinstance(labels, list) or not isinstance(values, list) or not 1 <= len(labels) == len(values) <= 24:
        raise ValueError("Charts need 1–24 matching labels and values")
    if any(not isinstance(label, str) or not 1 <= len(label) <= 80 for label in labels):
        raise ValueError("Chart labels must contain 1–80 characters")
    if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12 for value in values):
        raise ValueError("Chart values must be finite numbers within the supported range")
    if spec["type"] == "pie" and (any(v < 0 for v in values) or sum(values) <= 0):
        raise ValueError("Pie charts need non-negative values with a positive total")
    if not isinstance(spec.get("title"), str) or not 1 <= len(spec["title"]) <= 160:
        raise ValueError("Chart title must contain 1–160 characters")
    if not isinstance(spec.get("unit", ""), str) or len(spec.get("unit", "")) > 40:
        raise ValueError("Chart unit must be short text")
    if not isinstance(spec.get("source_ids", []), list) or any(not isinstance(s, str) or len(s) > 100 for s in spec.get("source_ids", [])):
        raise ValueError("Invalid chart source IDs")
    return spec


def action_link(kind, query):
    if not query.strip() or len(query) > 500:
        raise ValueError("Action query must contain 1–500 characters")
    if kind == "youtube":
        return "https://www.youtube.com/results?" + urlencode({"search_query": query})
    if kind == "google":
        return "https://www.google.com/search?" + urlencode({"q": query})
    raise ValueError("Choose a Google or YouTube action")
