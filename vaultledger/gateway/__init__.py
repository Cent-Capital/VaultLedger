"""LiteLLM model gateway: uniform completion interface + cost metering (Phase 11)."""
from .openai_compatible import OpenAICompatibleGenerator

__all__ = ["OpenAICompatibleGenerator"]
