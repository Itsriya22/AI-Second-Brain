"""Read runtime settings from the process environment or Streamlit secrets."""

from collections.abc import Mapping
import os

from dotenv import load_dotenv
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from config import ROOT_DIR


def _streamlit_secrets() -> Mapping[str, object]:
    return st.secrets


def get_runtime_setting(name: str) -> str | bool | None:
    """Return a setting from the environment first, then Streamlit secrets."""
    load_dotenv(ROOT_DIR / ".env")
    environment_value = os.environ.get(name)
    if environment_value is not None and environment_value.strip():
        return environment_value.strip()

    try:
        value = _streamlit_secrets().get(name)
    except (KeyError, StreamlitSecretNotFoundError):
        return None

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip() or None
    raise ValueError(f"Runtime setting {name} must be a string or boolean.")
