"""Android-only helpers: voice input, spoken replies, and phone actions.
Everything fails soft (returns a message) when not running on Android."""
import os, re
from urllib.parse import quote

ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ
_AR = re.compile("[\u0600-\u06FF]")
_RC = 7001
_cb = None
_bound = False
_tts = None
_tts_ready = False

def _act():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity

def _start(intent):
    from jnius import autoclass
    intent.addFlags(autoclass("android.content.Intent").FLAG_ACTIVITY_NEW_TASK)
    _act().startActivity(intent)

# ---------------- voice input (Google speech dialog) ----------------
def listen(lang, callback) -> bool:
    """Open the system speech dialog. callback(text or None) runs on the Kivy thread."""
    global _cb, _bound
    if not ANDROID:
        return False
    try:
        from jnius import autoclass
        from android import activity
        Intent = autoclass("android.content.Intent")
        RI = autoclass("android.speech.RecognizerIntent")
        _cb = callback
        if not _bound:
            activity.bind(on_activity_result=_result)
            _bound = True
        i = Intent(RI.ACTION_RECOGNIZE_SPEECH)
        i.putExtra(RI.EXTRA_LANGUAGE_MODEL, RI.LANGUAGE_MODEL_FREE_FORM)
        i.putExtra(RI.EXTRA_LANGUAGE, lang)
        i.putExtra(RI.EXTRA_PROMPT, "Jarvis is listening")
        _act().startActivityForResult(i, _RC)
        return True
    except Exception:
        return False

def _result(request, result, intent):
    global _cb
    if request != _RC:
        return
    text = None
    try:
        if result == -1 and intent is not None:
            from jnius import autoclass
            RI = autoclass("android.speech.RecognizerIntent")
            lst = intent.getStringArrayListExtra(RI.EXTRA_RESULTS)
            if lst is not None and lst.size() > 0:
                text = str(lst.get(0))
    except Exception:
        text = None
    cb, _cb = _cb, None
    if cb:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: cb(text))

# ---------------- spoken replies (native TextToSpeech) ----------------
def init_tts():
    global _tts
    if not ANDROID or _tts is not None:
        return
    try:
        from jnius import autoclass, PythonJavaClass, java_method

        class _Init(PythonJavaClass):
            __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
            __javacontext__ = "app"

            @java_method("(I)V")
            def onInit(self, status):
                global _tts_ready
                _tts_ready = (status == 0)

        TTS = autoclass("android.speech.tts.TextToSpeech")
        init = _Init()
        _tts = TTS(_act(), init)
        _tts._keep = init  # keep the listener alive
    except Exception:
        _tts = None

def speak(text) -> bool:
    """Speak with the phone's TTS in Arabic or English. False = caller should fall back."""
    if not (ANDROID and _tts is not None and _tts_ready):
        return False
    try:
        from jnius import autoclass
        Locale = autoclass("java.util.Locale")
        _tts.setLanguage(Locale("ar", "EG") if _AR.search(text) else Locale.US)
        _tts.speak(text[:3500], 0, None, "jarvis")
        return True
    except Exception:
        return False

def is_speaking() -> bool:
    try:
        return bool(_tts.isSpeaking())
    except Exception:
        return False

def stop():
    try:
        _tts.stop()
    except Exception:
        pass

# ---------------- phone actions (called by Gemini tools) ----------------
APPS = {"whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube",
        "spotify": "com.spotify.music", "chrome": "com.android.chrome",
        "maps": "com.google.android.apps.maps", "gmail": "com.google.android.gm",
        "telegram": "org.telegram.messenger", "messenger": "com.facebook.orca",
        "facebook": "com.facebook.katana", "instagram": "com.instagram.android",
        "netflix": "com.netflix.mediaclient", "settings": "com.android.settings"}

def _launch_pkg(pm, pkg):
    it = pm.getLaunchIntentForPackage(pkg)
    if it is None:
        return False
    _start(it)
    return True

def open_app(name):
    from jnius import autoclass
    name = (name or "").strip().lower()
    pm = _act().getPackageManager()
    if name in APPS and _launch_pkg(pm, APPS[name]):
        return "opened " + name
    apps = pm.getInstalledApplications(0)
    for k in range(apps.size()):
        ai = apps.get(k)
        if name and name in str(pm.getApplicationLabel(ai)).lower():
            if _launch_pkg(pm, str(ai.packageName)):
                return "opened " + name
    return "could not find an app called " + name

def open_url(url):
    from jnius import autoclass
    Intent, Uri = autoclass("android.content.Intent"), autoclass("android.net.Uri")
    _start(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    return "opened"

def run(name, a) -> str:
    if not ANDROID:
        return "Phone actions only work in the Android app."
    from jnius import autoclass
    Intent, Uri = autoclass("android.content.Intent"), autoclass("android.net.Uri")
    try:
        if name == "open_app":
            return open_app(a.get("name"))
        if name == "open_url":
            return open_url(a.get("url", ""))
        if name == "web_search":
            return open_url("https://www.google.com/search?q=" + quote(a.get("query", "")))
        if name == "call_number":
            _start(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + str(a.get("number", "")))))
            return "dialer opened (user must press call)"
        if name == "set_timer":
            i = Intent("android.intent.action.SET_TIMER")
            i.putExtra("android.intent.extra.alarm.LENGTH", int(a.get("seconds", 60)))
            i.putExtra("android.intent.extra.alarm.MESSAGE", str(a.get("label", "Jarvis")))
            i.putExtra("android.intent.extra.alarm.SKIP_UI", True)
            _start(i)
            return "timer set"
        if name == "set_alarm":
            i = Intent("android.intent.action.SET_ALARM")
            i.putExtra("android.intent.extra.alarm.HOUR", int(a.get("hour", 0)))
            i.putExtra("android.intent.extra.alarm.MINUTES", int(a.get("minute", 0)))
            i.putExtra("android.intent.extra.alarm.MESSAGE", str(a.get("label", "Jarvis")))
            i.putExtra("android.intent.extra.alarm.SKIP_UI", True)
            _start(i)
            return "alarm set"
        if name == "open_settings":
            page = {"bluetooth": "android.settings.BLUETOOTH_SETTINGS",
                    "wifi": "android.settings.WIFI_SETTINGS"}.get(
                        str(a.get("page", "")).lower(), "android.settings.SETTINGS")
            _start(Intent(page))
            return "settings opened"
    except Exception as e:
        return "failed: %s" % e
    return "unknown action"

# ---------------- stats for the HUD ----------------
def battery():
    """Battery percent, or None."""
    if not ANDROID:
        return None
    try:
        from jnius import autoclass
        IF, It = autoclass("android.content.IntentFilter"), autoclass("android.content.Intent")
        i = _act().registerReceiver(None, IF(It.ACTION_BATTERY_CHANGED))
        lv, sc = i.getIntExtra("level", -1), i.getIntExtra("scale", 100)
        return int(100 * lv / sc) if lv >= 0 and sc > 0 else None
    except Exception:
        return None

def net_bytes():
    """Total rx+tx bytes since boot, or None."""
    if not ANDROID:
        return None
    try:
        from jnius import autoclass
        TS = autoclass("android.net.TrafficStats")
        a, b = TS.getTotalRxBytes(), TS.getTotalTxBytes()
        return a + b if a >= 0 and b >= 0 else None
    except Exception:
        return None
