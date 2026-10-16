"""Jarvis settings (API key, names). Stored as JSON in the app's private data dir."""
import json
import os

def _path():
    return os.path.join(os.environ.get("JARVIS_HOME", "."), "config.json")

def _load():
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _patch(**kw):
    d = _load()
    d.update(kw)
    os.makedirs(os.path.dirname(_path()) or ".", exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)

def get_key() -> str:
    return (_load().get("gemini_api_key") or "").strip()

def set_key(k: str):
    _patch(gemini_api_key=k.strip())

def get_user_name() -> str:
    return (_load().get("user_name") or "").strip()

def set_user_name(n: str):
    _patch(user_name=n.strip())

def get_assistant_name() -> str:
    return (_load().get("assistant_name") or "Jarvis").strip() or "Jarvis"

def get_lang() -> str:
    """Speech-recognition language: 'ar-EG' (Egyptian Arabic) or 'en-US'."""
    return _load().get("voice_lang") or "ar-EG"

def set_lang(l: str):
    _patch(voice_lang=l)

def get_model_name() -> str:
    """Returns the active Gemini model name, defaulting to gemini-3.8-flash."""
    return _load().get("model_name") or "gemini-3.8-flash"

def set_model_name(m: str):
    _patch(model_name=m.strip())
