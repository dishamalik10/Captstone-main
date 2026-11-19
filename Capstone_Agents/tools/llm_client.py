"""Compatibility import for the older agent modules; all text uses local inference."""
from services.local_llm import generate_response


def call_llm(prompt: str) -> str:
    return generate_response(prompt)
