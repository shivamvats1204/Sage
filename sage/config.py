from dataclasses import asdict, dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = {
    "everyday": "Help with everyday questions and tasks. Use plain language.",
    "research": "Compare evidence, cite sources, distinguish findings from assumptions.",
    "study": "Explain concepts step by step, use examples, and suggest practice questions.",
    "developer": "Explain technical tradeoffs, produce maintainable code, and state verification limits.",
    "business": "Focus on decisions, concise briefs, explicit assumptions, and actionable next steps.",
}


def load_environment():
    # Optional dependency; never overwrite environment injected by the host.
    try:
        from dotenv import load_dotenv, dotenv_values
        load_dotenv(ROOT / ".env", override=False)
        # Windows already defines USERNAME case-insensitively; keep Sage's chosen name separate.
        chosen_name = dotenv_values(ROOT / ".env").get("Username")
        if chosen_name:
            os.environ.setdefault("SAGE_PROFILE_NAME", chosen_name)
    except ImportError:
        pass


@dataclass(frozen=True)
class Settings:
    workspace: str = "everyday"
    model: str = "qwen/qwen3.8-27b"
    temperature: float = 0.3
    max_tokens: int = 1800
    max_steps: int = 4
    retrieval_k: int = 4
    remember: bool = True
    allow_drafts: bool = True
    instructions: str = ""
    display_name: str = ""
    personalize: bool = True
    allow_web: bool = True
    allow_images: bool = True
    image_model: str = "black-forest-labs/FLUX.1-schnell"
    voice_language: str = "en-IN"

    @classmethod
    def parse(cls, value=None):
        value = {} if value is None else value
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError("Unknown settings fields")
        result = cls(**value)
        if not isinstance(result.workspace, str) or result.workspace not in WORKSPACES:
            raise ValueError("Choose a known workspace")
        if not isinstance(result.model, str) or not 1 <= len(result.model) <= 120:
            raise ValueError("Model must contain 1–120 characters")
        for key, low, high in [("temperature", 0, 1), ("max_tokens", 128, 4096),
                               ("max_steps", 1, 6), ("retrieval_k", 1, 8)]:
            v = getattr(result, key)
            expected = (float, int) if key == "temperature" else (int,)
            if type(v) not in expected or not low <= v <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
        if any(type(getattr(result, name)) is not bool for name in ("remember", "allow_drafts", "personalize", "allow_web", "allow_images")):
            raise ValueError("Permission and memory controls must be booleans")
        if not isinstance(result.instructions, str) or len(result.instructions) > 3000:
            raise ValueError("Instructions must be at most 3000 characters")
        if not isinstance(result.display_name, str) or len(result.display_name) > 80 or any(ord(c) < 32 for c in result.display_name):
            raise ValueError("Name must contain at most 80 printable characters")
        if not isinstance(result.image_model, str) or not 1 <= len(result.image_model) <= 160:
            raise ValueError("Image model must contain 1–160 characters")
        if result.voice_language not in {"en-IN", "en-US", "hi-IN", "ar-SA"}:
            raise ValueError("Choose a supported voice language")
        return result

    def to_dict(self):
        return asdict(self)


def data_directory():
    return Path(os.environ.get("SAGE_DATA_DIR", str(ROOT / ".sage")))


def profile_name(settings):
    if not settings.personalize:
        return ""
    return (settings.display_name or os.environ.get("SAGE_PROFILE_NAME") or os.environ.get("Username", "")).strip()[:80]
