"""Jarvis brain: Gemini over REST, with persona, long-term memory and a save_memory tool."""
import time, requests
from datetime import datetime
from . import config, memory, phone

# Tried in order. A model that is retired/unknown (404) is skipped, so one dead name never breaks the app.
MODELS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
BUSY = (404, 429, 500, 503, 504)

PERSONA = (
    "You are {name}, Tony Stark's AI assistant. Be concise, direct and quietly witty. "
    "Never simulate or guess results. Reply in the language the user writes in; if they "
    "write Arabic, use natural Egyptian Arabic. Keep answers short unless asked for detail; "
    "no markdown symbols like ** or #. Use an emoji only when it genuinely fits.\n"
    "MEMORY: when the user tells you a lasting personal fact or preference, call "
    "save_memory silently (never announce it). Use value DELETE to forget something. "
    "Before saying you don't know something personal, check the memory below.\n"
    "PHONE: you can open apps, URLs, searches, timers, alarms and settings with your tools "
    "when the user asks; after using a tool, confirm in one short sentence."
)

def _fn(name, desc, props=None, req=None):
    d = {"name": name, "description": desc}
    if props:
        d["parameters"] = {"type": "OBJECT", "properties": {k: {"type": t, "description": x} for k, (t, x) in props.items()},
                           "required": req or list(props)}
    return d

TOOLS = [{"function_declarations": [
    _fn("save_memory", "Save an important personal fact about the user to long-term memory.",
        {"category": ("STRING", "identity, preferences or notes"), "key": ("STRING", "short snake_case label"),
         "value": ("STRING", "the fact, or DELETE to remove it")}),
    _fn("open_app", "Open an app on the user's phone. Use the app's English name, e.g. whatsapp, youtube, camera.",
        {"name": ("STRING", "app name")}),
    _fn("open_url", "Open a web address in the phone's browser.", {"url": ("STRING", "full https URL")}),
    _fn("web_search", "Search Google on the phone.", {"query": ("STRING", "search text")}),
    _fn("call_number", "Open the dialer with a number (the user presses call).", {"number": ("STRING", "phone number")}),
    _fn("set_timer", "Start a countdown timer on the phone.",
        {"seconds": ("INTEGER", "duration in seconds"), "label": ("STRING", "label")}, ["seconds"]),
    _fn("set_alarm", "Set an alarm on the phone (24-hour time).",
        {"hour": ("INTEGER", "0-23"), "minute": ("INTEGER", "0-59"), "label": ("STRING", "label")}, ["hour", "minute"]),
    _fn("open_settings", "Open phone settings page: bluetooth, wifi or main.", {"page": ("STRING", "bluetooth, wifi or main")}),
]}]


class Jarvis:
    def __init__(self):
        self.history = []  # plain text turns only

    def _system(self) -> str:
        mem = memory.load()
        user = config.get_user_name() or mem.get("identity", {}).get("name", {}).get("value", "")
        addr = (f"ADDRESS: Always call the user '{user}'." if user else
                "ADDRESS: Use the ordinary respectful form for a superior in the language "
                "being spoken (\"sir\" in English).")
        name = config.get_assistant_name()
        now = datetime.now().strftime("%A, %B %d, %Y — %I:%M %p")
        return (f"[CURRENT DATE & TIME]\n{now}\n\n[IDENTITY]\nYour name is {name}. "
                f"Always refer to yourself as {name}.\n{addr}\n\n{memory.for_prompt(mem)}\n"
                + PERSONA.format(name=name))

    def _post(self, contents):
        key = config.get_key()
        if not key:
            raise RuntimeError("No Gemini API key set. Open Settings and add it.")
        body = {"system_instruction": {"parts": [{"text": self._system()}]},
                "contents": contents, "tools": TOOLS}
        last = ""
        for rnd in range(3):
            for model in MODELS:
                try:
                    r = requests.post(URL % model, headers={"x-goog-api-key": key}, timeout=45, json=body)
                except requests.RequestException as e:
                    last = "Network problem: %s" % e
                    continue
                if r.status_code == 200:
                    return r.json()
                try:
                    msg = r.json()["error"]["message"]
                except Exception:
                    msg = r.text[:200]
                last = "Gemini error %s: %s" % (r.status_code, msg)
                if r.status_code not in BUSY:
                    raise RuntimeError(last)
            time.sleep(1.5 * (rnd + 1))
        raise RuntimeError("Google's servers are busy right now - try again in a minute. (%s)" % last)

    def ask(self, text: str) -> str:
        contents = self.history + [{"role": "user", "parts": [{"text": text}]}]
        reply = ""
        for _ in range(4):
            data = self._post(contents)
            cands = data.get("candidates") or []
            if not cands:
                raise RuntimeError("Empty reply (blocked or no candidates).")
            content = cands[0].get("content") or {"role": "model", "parts": []}
            parts = content.get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            reply = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            if not calls:
                break
            contents.append({"role": "model", "parts": parts})
            results = []
            for c in calls:
                a = c.get("args") or {}
                out = (memory.remember(a.get("category"), a.get("key"), a.get("value"))
                       if c.get("name") == "save_memory" else phone.run(c.get("name"), a))
                results.append({"functionResponse": {"name": c.get("name"), "response": {"result": out}}})
            contents.append({"role": "user", "parts": results})
        reply = reply or "Done."
        self.history += [{"role": "user", "parts": [{"text": text}]},
                         {"role": "model", "parts": [{"text": reply}]}]
        self.history = self.history[-24:]
        return reply


MarkLV = Jarvis  # backwards compatibility with desktop.py
