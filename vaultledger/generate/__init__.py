"""Grounded generation: prompts, local generation, and answer assembly."""

from .ollama import GenerationError, OllamaGenerator, ollama_model_name
from .rag import answer_question, build_prompt

__all__ = [
    "GenerationError",
    "OllamaGenerator",
    "ollama_model_name",
    "answer_question",
    "build_prompt",
]
