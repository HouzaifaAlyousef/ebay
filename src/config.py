"""Konfiguration laden (config.yaml + .env)."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import yaml
from dotenv import load_dotenv


def _to_ns(obj):
    """Dict rekursiv in SimpleNamespace umwandeln -> cfg.search.url statt cfg['search']['url']."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_ns(v) for v in obj]
    return obj


def load_config(path: str = "config.yaml") -> SimpleNamespace:
    load_dotenv()  # lädt .env in os.environ
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"'{path}' nicht gefunden. Kopiere config.example.yaml -> config.yaml und passe sie an."
        )
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _to_ns(raw)


def get_api_key(provider: str) -> str:
    env_var = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider)
    if not env_var:
        raise ValueError(f"Unbekannter LLM-Provider: {provider}")
    key = os.getenv(env_var, "").strip()
    if not key:
        raise RuntimeError(f"{env_var} ist nicht gesetzt (siehe .env).")
    return key
