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
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass


@dataclass(frozen=True)
class Settings:
    workspace: str = "everyday"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.3
    max_tokens: int = 1800
    max_steps: int = 4
    retrieval_k: int = 4
    remember: bool = True
    allow_drafts: bool = True
    instructions: str = ""

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
        if type(result.remember) is not bool or type(result.allow_drafts) is not bool:
            raise ValueError("Memory and draft controls must be booleans")
        if not isinstance(result.instructions, str) or len(result.instructions) > 3000:
            raise ValueError("Instructions must be at most 3000 characters")
        return result

    def to_dict(self):
        return asdict(self)


def data_directory():
    return Path(os.environ.get("SAGE_DATA_DIR", str(ROOT / ".sage")))
