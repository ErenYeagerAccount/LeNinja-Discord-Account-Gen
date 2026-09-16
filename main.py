import os
import sys
import subprocess
import shutil
import traceback
import random
import string
import re
import asyncio
import importlib
import time
import warnings
import logging
from logging.handlers import RotatingFileHandler
import json
import email
import email.header
import imaplib
import codecs
from datetime import datetime
from dataclasses import dataclass, field
import threading
from threading import Thread
from pathlib import Path
from typing import Optional, Dict
from console_ui import format_prompt, render_activity_header, render_interface, render_log, render_summary

try:
    import httpx
except ImportError:  # pragma: no cover - handled during startup
    httpx = None

try:
    import tls_client
except ImportError:  # pragma: no cover - handled during startup
    tls_client = None

try:
    import yaml
except ImportError:  # pragma: no cover - handled during startup
    yaml = None

try:
    from colorama import Fore, Style, init
except ImportError:  # pragma: no cover - handled during startup
    class _ColorDummy:
        def __getattr__(self, name):
            return ""
    Fore = _ColorDummy()
    Style = type("Style", (), {"RESET_ALL": ""})()
    def init(*args, **kwargs):
        return None

try:
    from pystyle import Colors, Colorate, Center
except ImportError:  # pragma: no cover - handled during startup
    Colors = Colorate = Center = None

import zipfile
import io
try:
    from PIL import Image
except ImportError:  # pragma: no cover - handled during startup
    Image = None
import base64
try:
    from curl_cffi import requests
except ImportError:  # pragma: no cover - handled during startup
    requests = None

init(autoreset=True)


LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "SUCCESS": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def configure_logging():
    log_directory = Path(__file__).resolve().parent / "logs"
    log_directory.mkdir(exist_ok=True)

    root_logger = logging.getLogger("leninja")
    if root_logger.handlers:
        return root_logger

    configured_level = os.getenv("LENINJA_LOG_LEVEL", "INFO").upper()
    root_logger.setLevel(LOG_LEVELS.get(configured_level, logging.INFO))

    file_handler = RotatingFileHandler(
        log_directory / "leninja.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root_logger.addHandler(file_handler)
    return root_logger


APP_LOGGER = configure_logging()


def is_domain_blacklisted(domain):
    if not domain:
        return False
    domain = domain.lower()
    blacklist_suffixes = [".store", ".ng"]
    blacklist_domains = ["cybertemp.xyz", "altmails.icu"]
    if domain in blacklist_domains:
        return True
    for suffix in blacklist_suffixes:
        if domain.endswith(suffix):
            return True
    return False
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)


def log_message(level, message, *, summary=None):
    ts = datetime.now().strftime("%H:%M:%S")
    normalized_level = level.upper()
    numeric_level = LOG_LEVELS.get(normalized_level, logging.INFO)
    APP_LOGGER.log(numeric_level, message)
    if not APP_LOGGER.isEnabledFor(numeric_level):
        return
    print(render_summary(*summary) if summary is not None else render_log(normalized_level, message, ts))


def log_token(token_masked):
    ts = datetime.now().strftime("%H:%M:%S")
    APP_LOGGER.info("token: %s", token_masked)
    if not APP_LOGGER.isEnabledFor(logging.INFO):
        return
    print(render_log("SUCCESS", f"Token: {token_masked}", ts))


def prompt_user(query):
    formatted = format_prompt(query)
    if os.environ.get("LENINJA_SKIP_SETUP") == "1":
        return ""
    if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return ""
    return input(formatted)


REQUIRED_IMPORTS = (
    "httpx",
    "tls_client",
    "colorama",
    "pystyle",
    "yaml",
    "PIL",
    "curl_cffi",
    "groq",
    "truedriver",
)


def missing_required_modules():
    missing = []
    for module in REQUIRED_IMPORTS:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return missing


def refresh_optional_imports():
    """Re-bind third-party modules after a successful pip install."""
    global httpx, tls_client, yaml, Fore, Style, init, Colors, Colorate, Center, Image, requests
    global Groq, GROQ_AVAILABLE, uc
    try:
        httpx = importlib.import_module("httpx")
    except ImportError:
        httpx = None
    try:
        tls_client = importlib.import_module("tls_client")
    except ImportError:
        tls_client = None
    try:
        yaml = importlib.import_module("yaml")
    except ImportError:
        yaml = None
    try:
        colorama = importlib.import_module("colorama")
        Fore = colorama.Fore
        Style = colorama.Style
        init = colorama.init
        init(autoreset=True)
    except ImportError:
        pass
    try:
        pystyle = importlib.import_module("pystyle")
        Colors = pystyle.Colors
        Colorate = pystyle.Colorate
        Center = pystyle.Center
    except ImportError:
        pass
    try:
        Image = importlib.import_module("PIL.Image")
    except ImportError:
        Image = None
    try:
        requests = importlib.import_module("curl_cffi.requests")
    except ImportError:
        requests = None
    try:
        Groq = importlib.import_module("groq").Groq
        GROQ_AVAILABLE = True
    except ImportError:
        GROQ_AVAILABLE = False
    try:
        uc = importlib.import_module("truedriver")
    except ImportError:
        uc = None


def get_truedriver():
    global uc
    if uc is None:
        uc = importlib.import_module("truedriver")
    return uc


def install_requirements(force=False):
    requirements_path = Path(__file__).resolve().parent / "requirements.txt"
    if not requirements_path.exists():
        return True
    if os.environ.get("LENINJA_SKIP_SETUP") == "1" and not force:
        return True
    missing = missing_required_modules()
    if not missing and not force:
        return True

    choice = prompt_user("Do you want to install requirements? (y/n): ").strip().lower()
    if choice != 'y':
        log_message("WARNING", "skipping requirements installation.")
        return False
    log_message("INFO", "installing requirements, please wait...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements_path)])
        refresh_optional_imports()
        still_missing = missing_required_modules()
        if still_missing:
            log_message("ERROR", f"still missing after install: {', '.join(still_missing)}")
            return False
        log_message("SUCCESS", "requirements installed successfully!")
        return True
    except subprocess.CalledProcessError:
        log_message("ERROR", "failed to install requirements. please install them manually.")
        return False


def configure_stdio():
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


uc = None


@dataclass
class UTILS_DISCORD:
    x_super_properties: dict = field(default_factory=dict)
    discord_user_agent: str = ""
    browser_user_agent: str = ""

    def __init__(self):
        self._scrape_info()
        Thread(target=self._scrape_info_loop, daemon=True).start()

    def _scrape_info(self):
        try:
            session = tls_client.Session(
                client_identifier="chrome_131",
                random_tls_extension_order=True
            )
            response = session.get("https://discord.eintim.dev/discord_info")
            if response.status_code == 200:
                details = response.json()
                self.discord_user_agent = details["desktop"]["user-agent"]
                self.browser_user_agent = details["browser"]["user-agent"]
                self.x_super_properties = details["desktop"]["decoded-x-super-properties"]
            else:
                self._set_fallback_values()
        except:
            self._set_fallback_values()

    def _set_fallback_values(self):
        self.discord_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9220 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36"
        self.browser_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        self.x_super_properties = {
            "os": "Windows",
            "browser": "Discord Client",
            "release_channel": "stable",
            "client_version": "1.0.9220",
            "os_version": "10.0.26100",
            "os_arch": "x64",
            "app_arch": "x64",
            "system_locale": "en-US",
            "has_client_mods": False,
            "browser_user_agent": self.discord_user_agent,
            "browser_version": "32.2.7",
            "os_sdk_version": "26100",
            "client_build_number": 485097,
            "native_build_number": 73818,
            "client_event_source": None
        }

    def _scrape_info_loop(self):
        while True:
            time.sleep(300)
            try:
                self._scrape_info()
            except:
                pass


def get_path(relative_path):
    if getattr(sys, 'frozen', False) or '__compiled__' in globals():
        base_path = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


_UTILS_DISCORD = UTILS_DISCORD()
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    Groq = None


LENINJA_EXT_ID = "dknlfmjaanfblgfdfebhijalfmhmjjjo"
LENINJA_EXT_DIR = Path(get_path("extension/nopecha_ext"))
LENINJA_KEYS_FILE = Path(get_path("config/nopecha.txt"))
FP_FILE = Path(get_path("input/fp.txt"))
_fp_lock = threading.Lock()
LENINJA_KEY_INDEX = 0


def load_leninja_keys() -> list:
    if not LENINJA_KEYS_FILE.exists():
        LENINJA_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        LENINJA_KEYS_FILE.write_text("")
        return []
    keys = []
    for line in LENINJA_KEYS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            keys.append(line)
    return keys


def get_current_leninja_key() -> Optional[str]:
    keys = load_leninja_keys()
    if not keys:
        return None
    global LENINJA_KEY_INDEX
    return keys[LENINJA_KEY_INDEX % len(keys)]


def inject_leninja_key(api_key: str):
    if not api_key or not LENINJA_EXT_DIR.exists():
        return False
    ok = False

    # 1. Inject into manifest.json
    manifest_path = LENINJA_EXT_DIR / "manifest.json"
    try:
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            # Get all keys from nopecha.txt
            all_keys = load_leninja_keys()

            # Update nopecha.key with the first key
            if 'nopecha' not in manifest:
                manifest['nopecha'] = {}
            manifest['nopecha']['key'] = api_key

            # Update nopecha.keys with all keys
            if all_keys:
                manifest['nopecha']['keys'] = all_keys

            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent='	')
            ok = True
    except Exception as e:
        pass

    # 2. Inject into settings.json
    settings_path = LENINJA_EXT_DIR / "settings.json"
    try:
        settings = {}
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        settings['key'] = api_key
        with open(settings_path, 'w') as f:
            json.dump(settings, f)
        ok = True
    except:
        pass

    # 3. Patch JavaScript bundles
    replacement = f'key:me(ge(),{json.dumps(api_key)})'
    pattern = re.compile(r'key:me\(ge\(\),\"[^\"]*\"\)')
    try:
        for bundle_path in LENINJA_EXT_DIR.rglob("*.js"):
            try:
                bundle = bundle_path.read_text(encoding="utf-8", errors="ignore")
                new_bundle, count = pattern.subn(replacement, bundle, count=1)
                if count:
                    bundle_path.write_text(new_bundle, encoding="utf-8")
                    ok = True
            except:
                continue
    except:
        pass
    return ok
def download_leninja_ext() -> Optional[Path]:
    if LENINJA_EXT_DIR.exists() and (LENINJA_EXT_DIR / "manifest.json").exists():
        return LENINJA_EXT_DIR
    log_message("INFO", "downloading leninja extension (first run)...")
    crx_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=120.0.0.0&acceptformat=crx2,crx3&x=id%3D{LENINJA_EXT_ID}%26uc"
    try:
        with httpx.Client(follow_redirects=True) as client:
            r = client.get(crx_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            if r.status_code != 200:
                log_message("ERROR", f"leninja download failed: HTTP {r.status_code}")
                return None
            data = r.content
        if data[:4] == b"Cr24":
            version = int.from_bytes(data[4:8], "little")
            zip_start = (12 + int.from_bytes(data[8:12], "little")) if version == 3 else (16 + int.from_bytes(data[8:12], "little") + int.from_bytes(data[12:16], "little"))
        else:
            zip_start = 0
        LENINJA_EXT_DIR.mkdir(exist_ok=True, parents=True)
        with zipfile.ZipFile(io.BytesIO(data[zip_start:])) as z:
            z.extractall(LENINJA_EXT_DIR)
        if (LENINJA_EXT_DIR / "manifest.json").exists():
            log_message("SUCCESS", "leninja extension installed")
            return LENINJA_EXT_DIR
        log_message("ERROR", "leninja extract failed: manifest.json missing")
        return None
    except Exception as e:
        log_message("ERROR", f"leninja download failed: {str(e)[:100]}")
        return None


async def setup_leninja(log_func=None):
    _l = log_func or log_message
    ext_path = download_leninja_ext()
    if not ext_path:
        _l("ERROR", "Failed to download LeNinja extension")
        return None
    current_key = get_current_leninja_key()
    if current_key:
        if inject_leninja_key(current_key):
            _l("SUCCESS", "leninja key injected")
        else:
            _l("WARNING", "leninja key could not be injected (check extension files)")
    else:
        _l("WARNING", "no leninja key in config/nopecha.txt - captcha solving will be limited")
    return ext_path


BROWSER_SETTINGS = {"name": "auto", "path": None}

# Prefer browsers that actually render Discord. Vivaldi often stays on a white page.
BROWSER_EXECUTABLES = {
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ],
    "chromium": [
        r"C:\Program Files\Chromium\Application\chrome.exe",
        r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/ungoogled-chromium",
    ],
    "thorium": [
        r"C:\Program Files\Thorium\thorium.exe",
        r"C:\Program Files\Thorium\Application\thorium.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Thorium\Application\thorium.exe"),
        "/usr/bin/thorium-browser",
        "/opt/thorium/thorium",
    ],
    "arc": [
        os.path.expandvars(r"%LOCALAPPDATA%\Arc\Application\Arc.exe"),
        "/Applications/Arc.app/Contents/MacOS/Arc",
    ],
    "vivaldi": [
        r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        r"C:\Program Files (x86)\Vivaldi\Application\vivaldi.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
        "/usr/bin/vivaldi",
        "/usr/bin/vivaldi-stable",
        "/opt/vivaldi/vivaldi",
    ],
}
BROWSER_SEARCH_ORDER = ("brave", "chrome", "chromium", "thorium", "arc", "vivaldi")
SLOW_DISCORD_BROWSERS = ("vivaldi",)


def first_existing_path(paths):
    for path in paths:
        resolved = resolve_browser_executable(path)
        if resolved:
            return resolved
    return None


def is_browser_executable(path):
    if not path or not os.path.isfile(path):
        return False
    lower = path.lower()
    if lower.endswith((".lnk", ".url", ".bat", ".cmd", ".msi")):
        return False
    if lower.endswith(".exe"):
        return True
    if os.name == "nt":
        return False
    return os.access(path, os.X_OK)


def resolve_shortcut_target(path):
    if not path or not str(path).lower().endswith(".lnk") or not os.path.isfile(path):
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        data = b""
    candidates = []
    if data:
        for match in re.finditer(rb"[A-Za-z]:\\(?:[^\\\x00]+\\)*[^\\\x00]+\.exe", data, re.I):
            candidates.append(match.group().decode("ascii", "ignore"))
        utf16 = data.decode("utf-16le", errors="ignore")
        for match in re.finditer(r"[A-Za-z]:\\(?:[^\\:*?\"<>|\x00]+\\)*[^\\:*?\"<>|\x00]+\.exe", utf16, re.I):
            candidates.append(match.group())
    if os.name == "nt":
        try:
            quoted = json.dumps(os.path.abspath(path))
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(New-Object -ComObject WScript.Shell).CreateShortcut({quoted}).TargetPath",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=0x08000000,
            )
            target = (completed.stdout or "").strip().strip('"')
            if target:
                candidates.insert(0, target)
        except Exception:
            pass
    for candidate in candidates:
        if is_browser_executable(candidate):
            return candidate
        nested = resolve_browser_executable(candidate)
        if nested:
            return nested
    return None


def resolve_browser_executable(path):
    if not path:
        return None
    path = os.path.expandvars(os.path.expanduser(str(path).strip().strip('"').strip("'")))
    if not path:
        return None
    if path.lower().endswith(".lnk"):
        return resolve_shortcut_target(path)
    if os.path.isdir(path):
        for name in ("brave.exe", "chrome.exe", "vivaldi.exe", "thorium.exe", "Arc.exe"):
            for nested in (os.path.join(path, name), os.path.join(path, "Application", name)):
                if is_browser_executable(nested):
                    return nested
        return None
    if is_browser_executable(path):
        return path
    return None


def browser_label(path, fallback="vivaldi"):
    if not path:
        return fallback
    name = os.path.splitext(os.path.basename(path))[0].lower()
    if name in ("chrome",):
        parent = os.path.basename(os.path.dirname(os.path.dirname(path) if os.path.basename(os.path.dirname(path)).lower() == "application" else os.path.dirname(path))).lower()
        if "chromium" in parent:
            return "chromium"
        if "vivaldi" in path.lower():
            return "vivaldi"
    return name or fallback


def configure_browser(config=None):
    config = config or {}
    name = str(config.get("browser") or "auto").strip().lower() or "auto"
    explicit = str(config.get("browser_path") or "").strip().strip('"').strip("'") or None
    BROWSER_SETTINGS["name"] = name
    BROWSER_SETTINGS["path"] = explicit
    return BROWSER_SETTINGS


def find_browser_path(preferred=None, explicit_path=None):
    preferred = (preferred or BROWSER_SETTINGS.get("name") or "auto").strip().lower()
    explicit_path = explicit_path if explicit_path is not None else BROWSER_SETTINGS.get("path")

    def first_preferred():
        order = BROWSER_SEARCH_ORDER if preferred in ("auto", "any", "") else (preferred,) + BROWSER_SEARCH_ORDER
        seen = set()
        for name in order:
            if name in seen or name not in BROWSER_EXECUTABLES:
                continue
            seen.add(name)
            found = first_existing_path(BROWSER_EXECUTABLES[name])
            if found:
                return found, name
        return None, preferred

    if explicit_path:
        resolved = resolve_browser_executable(explicit_path)
        label = browser_label(resolved, preferred) if resolved else ""
        slow = bool(resolved) and (
            (label or "").lower() == "vivaldi"
            or os.path.splitext(os.path.basename(resolved))[0].lower() == "vivaldi"
        )
        if resolved and not slow:
            return resolved, label
        better, better_name = first_preferred()
        if better and (not resolved or os.path.normcase(better) != os.path.normcase(resolved)):
            if slow:
                log_message("WARNING", "vivaldi often shows a blank Discord page; switching to a faster Chromium browser")
            return better, better_name
        if resolved:
            return resolved, label or preferred
        log_message(
            "WARNING",
            "browser_path is not a usable .exe. Searching for Brave or Chrome instead",
        )

    found, name = first_preferred()
    if found:
        return found, name
    return None, preferred


def get_brave_path() -> Optional[str]:
    path, _name = find_browser_path()
    return path


class GroqCaptchaSolver:
    def __init__(self, api_key: str):
        if not GROQ_AVAILABLE:
            raise ImportError("Groq not installed")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.2-90b-vision-preview"

    def solve_text_captcha(self, image_base64: str) -> Optional[str]:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                            {"type": "text", "text": "Extract ONLY the text from this CAPTCHA."}
                        ]
                    }
                ],
                temperature=0.1,
                max_tokens=100
            )
            return resp.choices[0].message.content.strip().replace('"', '').replace('.', '')
        except:
            return None


JS_UTILS = '''
(() => {
    if (window.utils) return; 
    window.utils = {
        setInput: (s, v) => { const el = document.querySelector(s); if(el){ el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }},
        clickAllCheckboxes: () => { 
            const cbs = document.querySelectorAll('input[type="checkbox"]'); 
            let c=0; cbs.forEach(cb => { if(!cb.checked){ cb.click(); cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true})); c++; }});
            return {clicked:c, total:cbs.length};
        },
        clickElement: (s) => { const el = document.querySelector(s); if(el) el.click(); }
    };
})();
'''


async def animated_cooldown(total_seconds):
    import sys
    bar_width = 30
    start = time.time()
    while True:
        elapsed = time.time() - start
        remaining = max(0, total_seconds - elapsed)
        if total_seconds > 0:
            progress = min(elapsed / total_seconds, 1.0)
        else:
            progress = 1.0
        filled = round(bar_width * progress)
        bar_filled = Fore.LIGHTCYAN_EX + chr(9608) * filled + Style.RESET_ALL
        bar_empty = Fore.LIGHTBLACK_EX + chr(9617) * (bar_width - filled) + Style.RESET_ALL
        spin_chars = ['|', '/', '-', '\\']
        spin = Fore.LIGHTMAGENTA_EX + spin_chars[int(elapsed * 4) % len(spin_chars)] + Style.RESET_ALL
        label = Fore.LIGHTYELLOW_EX + 'Cooldown' + Style.RESET_ALL
        timer = Fore.LIGHTWHITE_EX + f'{remaining:.0f}s' + Style.RESET_ALL
        line = f'\r {spin} {label} [{bar_filled}{bar_empty}] {timer} remaining   '
        sys.stdout.write(line)
        sys.stdout.flush()
        if remaining <= 0:
            break
        await asyncio.sleep(0.15)
    done_line = f'\r {Fore.LIGHTGREEN_EX}+{Style.RESET_ALL} {Fore.LIGHTWHITE_EX}Cooldown complete{Style.RESET_ALL}' + ' ' * 40
    sys.stdout.write(done_line + '\n')
    sys.stdout.flush()


def print_stats_bar(valid, locked, invalid):
    total = valid + locked + invalid
    print(f"\r {Fore.LIGHTGREEN_EX}Valid: {valid} {Fore.LIGHTBLACK_EX}| {Fore.LIGHTYELLOW_EX}Locked: {locked} {Fore.LIGHTBLACK_EX}| {Fore.LIGHTRED_EX}Invalid: {invalid} {Fore.LIGHTBLACK_EX}| {Fore.LIGHTCYAN_EX}Total: {total}{Style.RESET_ALL}")


def set_console_title(title="LeNinja - Token Generator"):
    if os.name == 'nt':
        os.system(f"title {title}")
    else:
        print(f"\33]0;{title}\a", end='', flush=True)


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def cleanup_resources():
    try:
        import gc
        gc.collect()
        try:
            import truedriver as uc
            uc.stop_all()
        except:
            pass
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in tasks:
            try: t.cancel()
            except: pass
        gc.collect()
    except:
        pass


async def shutdown_engine():
    try:
        import gc
        gc.collect()
        try:
            import truedriver as uc
            uc.stop_all()
        except:
            pass
        await asyncio.sleep(0.3)
        try:
            loop = asyncio.get_running_loop()
            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in tasks:
                try: t.cancel()
                except: pass
        except RuntimeError:
            pass
        gc.collect()
    except:
        pass


def animate_text(text, speed=0.03):
    lines = text.split('\n')
    for line in lines:
        print(line)
        time.sleep(speed)


def apply_gradient(lines, color_start=(255, 0, 255), color_end=(0, 255, 255)):
    total = len(lines)
    result = []
    for i, line in enumerate(lines):
        r = color_start[0] + (color_end[0] - color_start[0]) * i // max(1, total - 1)
        g = color_start[1] + (color_end[1] - color_start[1]) * i // max(1, total - 1)
        b = color_start[2] + (color_end[2] - color_start[2]) * i // max(1, total - 1)
        result.append(f'\033[38;2;{r};{g};{b}m{line}\033[0m')
    return result


def show_interface():
    print(render_interface())


async def fetch_discord_token(email: str, password: str, proxy_config: Dict = None) -> str:
    url = "https://discord.com/api/v9/auth/login"
    payload = {
        "login": email,
        "password": password,
        "undelete": False,
        "gift_code_sku_id": None,
        "login_source": None
    }
    
    headers = get_headers()
    
    session = tls_client.Session(
        client_identifier="chrome_131",
        random_tls_extension_order=True
    )
    
    if proxy_config:
        session.proxies = proxy_config

    try:
        response = session.post(
            url,
            headers=headers,
            json=payload,
            timeout_seconds=30
        )
        if response.status_code == 200:
            return response.json().get("token")
        else:
            log_message("ERROR", f"login failed: {response.status_code} - {response.text}")
    except Exception as e:
        log_message("ERROR", f"fetch token error: {str(e)}")
    return None


def get_headers():
    return {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://discord.com",
        "priority": "u=1, i",
        "referer": "https://discord.com/channels/@me",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "x-discord-timezone": "Asia/Calcutta",
        "x-super-properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZSwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEzNC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTM0LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjM4NDg4NywiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0="
    }


def create_random_string(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def make_handle():
    adjectives = [
        "dark", "cool", "epic", "mega", "ultra", "pro", "elite", "alpha",
        "sigma", "shadow", "void", "ghost", "neon", "cyber", "pixel", "frost",
        "lunar", "solar", "nova", "zen", "sky", "storm", "river", "mountain",
        "silent", "hidden", "lost", "mythic", "iron", "golden", "vivid"
    ]
    nouns = [
        "gamer", "warrior", "ninja", "king", "lord", "knight", "beast",
        "titan", "scout", "pilot", "vortex", "blade", "seeker", "walker",
        "hunter", "reaper", "phantom", "spirit", "dragon", "wolf", "raven"
    ]
    connectors = ["", "_", "."]
    name_parts = [random.choice(adjectives), random.choice(nouns)]
    if random.random() > 0.7:
        name_parts.insert(1, random.choice(adjectives))
    sep = random.choice(connectors)
    name = sep.join(name_parts)
    suffix = str(random.randint(1000, 999999))
    if random.random() > 0.5:
        name += random.choice(connectors) + suffix
    else:
        name += suffix
    return name[:32].lower()


def load_proxies(config: dict) -> list:
    proxy_enabled = config.get("proxy", {}).get("enabled", False)
    if not proxy_enabled:
        return []
    proxy_file = config.get("proxy", {}).get("file", "input/proxies.txt")
    proxy_path = Path(get_path(proxy_file))
    if not proxy_path.exists():
        return []
    try:
        with open(proxy_path, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if proxies:
            return proxies
        else:
            return []
    except Exception as e:
        return []


def get_random_proxy(proxies: list) -> str:
    if not proxies:
        return None
    return random.choice(proxies)


MULLVADEXE = None

MULLVADCOUNTRIES = [
    "us", "ca", "gb", "au", "de", "fr", "nl", "se", "no", "dk",
    "fi", "at", "be", "ie", "jp", "sg", "nz", "za"
]

MULLVADLAST_COUNTRY = None
MULLVADUSED_COUNTRIES = []


def findmullvad_cli():
    in_path = shutil.which("mullvad")
    if in_path:
        return in_path
    root = r"C:\Program Files\Mullvad VPN"
    candidates = [
        os.path.join(root, "mullvad.exe"),
        os.path.join(root, "resources", "bin", "mullvad.exe"),
        os.path.join(root, "resources", "mullvad.exe"),
        os.path.join(root, "bin", "mullvad.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Mullvad VPN\mullvad.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Mullvad VPN\resources\bin\mullvad.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


MULLVADEXE = findmullvad_cli()


def runmullvad(args, timeout=30):
    si = None
    cf = 0
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        cf = 0x08000000
    exe = MULLVADEXE or "mullvad"
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            startupinfo=si,
            creationflags=cf if cf else 0
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def mullvadstatus():
    rc, out, _ = runmullvad(["status"], timeout=15)
    return rc, out


def mullvadis_connected(status_text):
    if not status_text:
        return False
    lower = status_text.lower()
    first_line = lower.splitlines()[0] if lower.splitlines() else lower
    return ("tunnel status: connected" in lower
            or (first_line.strip().startswith("connected") and "disconnected" not in first_line)
            or re.search(r"^\s*connected\b", lower, re.M))


def mullvadcountry_from_status(text):
    if not text:
        return None
    m = re.search(r"Relay\s+-\s+([A-Za-z]{2})", text)
    if m:
        return m.group(1).lower()
    m = re.search(r"Visible location:\s*([A-Za-z ]+),\s*([A-Za-z ]+)", text)
    if m:
        country_name = m.group(2).strip().lower()
        map_ = {
            "sweden": "se", "united states": "us", "usa": "us",
            "germany": "de", "netherlands": "nl", "france": "fr", "united kingdom": "gb",
            "england": "gb", "uk": "gb", "canada": "ca", "japan": "jp", "singapore": "sg",
            "australia": "au", "norway": "no", "denmark": "dk", "finland": "fi", "spain": "es",
            "italy": "it", "switzerland": "ch", "austria": "at", "belgium": "be", "ireland": "ie",
            "portugal": "pt", "poland": "pl", "czech republic": "cz", "romania": "ro",
            "new zealand": "nz", "brazil": "br", "india": "in", "south africa": "za",
            "hong kong": "hk", "turkey": "tr"
        }
        return map_.get(country_name)
    return None


def get_public_ip():
    urls = [
        "https://api.ipify.org?format=json",
        "https://ipinfo.io/json",
        "https://ifconfig.co/json",
        "https://am.i.mullvad.net/json"
    ]
    for url in urls:
        try:
            session = tls_client.Session(client_identifier="chrome_131", random_tls_extension_order=True)
            r = session.get(url, timeout_seconds=3)
            if r.status_code == 200:
                data = r.json()
                ip = data.get("ip")
                if ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                    return ip
        except:
            continue
    return None


def redact_ip(ip):
    if not ip:
        return "?.?.?.?"
    parts = ip.split(".")
    if len(parts) != 4:
        return ip
    parts[2] = "*"
    parts[3] = "*"
    return ".".join(parts)


def mullvadrandom_country():
    global MULLVADLAST_COUNTRY, MULLVADUSED_COUNTRIES
    avoid_count = min(8, max(0, len(MULLVADCOUNTRIES) - 1))
    avoid_set = set(MULLVADUSED_COUNTRIES[-avoid_count:]) if avoid_count else set()
    pool = [c for c in MULLVADCOUNTRIES if c not in avoid_set]
    if not pool:
        pool = MULLVADCOUNTRIES[:]
        MULLVADUSED_COUNTRIES = []
    pick = random.choice(pool)
    MULLVADLAST_COUNTRY = pick
    MULLVADUSED_COUNTRIES.append(pick)
    if len(MULLVADUSED_COUNTRIES) > 20:
        MULLVADUSED_COUNTRIES = MULLVADUSED_COUNTRIES[-12:]
    return pick


async def mullvad_ensure_connected():
    if not MULLVADEXE:
        log_message("ERROR", "mullvad cli not in path and not found in program files")
        return False
    rc, status = mullvadstatus()
    baseline_ip = get_public_ip()
    log_message("INFO", f"baseline ip: {redact_ip(baseline_ip)}")
    runmullvad(["lockdown-mode", "set", "on"], timeout=20)
    if mullvadis_connected(status):
        c = mullvadcountry_from_status(status)
        log_message("SUCCESS", f"mullvad already connected {redact_ip(baseline_ip)}" + (f" ({c})" if c else ""))
        return True
    log_message("INFO", "connecting mullvad vpn")
    rc, out, err = runmullvad(["connect"], timeout=45)
    last_shown_ip = None
    for i in range(1, 501):
        await asyncio.sleep(0.2)
        rc2, s = mullvadstatus()
        if i % 10 == 0 or not last_shown_ip:
            current_ip = get_public_ip()
            if current_ip != last_shown_ip:
                last_shown_ip = current_ip
        if mullvadis_connected(s):
            connected_count = 1
            for _verify in range(4):
                await asyncio.sleep(0.4)
                _rc, _s = mullvadstatus()
                if mullvadis_connected(_s):
                    connected_count += 1
            if connected_count >= 3:
                ip = last_shown_ip or get_public_ip()
                c = mullvadcountry_from_status(s)
                log_message("SUCCESS", f"mullvad connected {redact_ip(ip)}" + (f" ({c})" if c else ""))
                return True
    runmullvad(["lockdown-mode", "set", "off"], timeout=20)
    final_ip = get_public_ip()
    log_message("ERROR", f"mullvad failed to connect [{rc}]: {err or out} (final ip: {redact_ip(final_ip)})")
    return False


async def mullvad_cycle(old_ip=None, max_attempts=5):
    global MULLVADLAST_COUNTRY
    if not MULLVADEXE or not os.path.exists(MULLVADEXE):
        log_message("WARNING", "mullvad cli not found, falling back to 10s sleep")
        await asyncio.sleep(10)
        return None
    previous = old_ip or get_public_ip()
    last_ip = previous
    for attempt in range(1, max_attempts + 1):
        country = mullvadrandom_country()
        log_message("INFO", f"switching to {country} ({attempt}/{max_attempts})")
        rc, out, err = runmullvad(["relay", "set", "location", country])
        if rc != 0:
            runmullvad(["relay", "set", "location"])
        rc, out, err = runmullvad(["connect"])
        log_message("INFO", "connecting mullvad vpn")
        deadline = time.time() + 25
        new_ip = None
        last_shown = None
        poll_i = 0
        while time.time() < deadline:
            poll_i += 1
            await asyncio.sleep(0.3)
            new_ip = get_public_ip()
            if new_ip and new_ip != last_shown:
                last_shown = new_ip
            if new_ip and new_ip != last_ip:
                break
        if mullvadis_connected(mullvadstatus()[1]):
            if new_ip and new_ip != last_ip and new_ip != previous:
                log_message("SUCCESS", f"connected to {redact_ip(new_ip)} ({country})")
                return new_ip
            elif new_ip and new_ip != previous:
                log_message("SUCCESS", f"connected to {redact_ip(new_ip)} ({country})")
                return new_ip
        last_ip = new_ip or last_ip
        if attempt < max_attempts:
            log_message("WARNING", "ip unchanged, retrying with new country")
    final_ip = get_public_ip()
    log_message("ERROR", f"mullvad failed to change ip after {max_attempts} attempts (last seen: {redact_ip(final_ip)})")
    return last_ip if last_ip != previous else previous


async def rotate_mullvad_ip():
    if not MULLVADEXE:
        log_message("ERROR", "mullvad cli not found")
        return False
    current_ip = get_public_ip()
    new_ip = await mullvad_cycle(old_ip=current_ip, max_attempts=5)
    return new_ip is not None and new_ip != current_ip


async def require_vpn_connection():
    connected = await mullvad_ensure_connected()
    if not connected:
        log_message("ERROR", "vpn is enabled but mullvad failed to connect; stopping")
        return False
    return True


def response_json(response):
    try:
        return response.json()
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def parse_colon_credentials(account):
    """Parse email:password[:refreshToken:clientId], keeping the domain attached to the local part."""
    account = str(account).strip().strip('"').strip("'")
    if not account:
        return None
    at = account.find("@")
    if at == -1:
        return None
    sep = account.find(":", at)
    if sep == -1:
        return None
    email_addr = account[:sep].strip()
    remainder = account[sep + 1:]
    if not remainder:
        return None
    if ":" not in remainder:
        password, refresh_token, uuid = remainder.strip(), None, None
    else:
        password, rest = remainder.split(":", 1)
        password = password.strip()
        rest = rest.strip()
        if ":" in rest:
            refresh_token, uuid = rest.rsplit(":", 1)
            refresh_token = refresh_token.strip() or None
            uuid = uuid.strip() or None
        else:
            refresh_token, uuid = rest or None, None
    if email_addr and password and "@" in email_addr:
        return email_addr, password, refresh_token, uuid
    return None


def parse_mailbox_account(account):
    """Parse a provider mailbox payload into email, password, refresh token, and client id."""
    email_addr = password = refresh_token = uuid = None
    if isinstance(account, dict):
        raw = account.get("account") or account.get("mail") or account.get("line")
        if isinstance(raw, str):
            parsed = parse_colon_credentials(raw)
            if parsed:
                return parsed
        email_addr = account.get("email") or account.get("address") or account.get("username")
        password = account.get("password") or account.get("pass")
        refresh_token = (
            account.get("refresh_token")
            or account.get("refreshToken")
            or account.get("refresh-token")
        )
        uuid = (
            account.get("client_id")
            or account.get("clientId")
            or account.get("client-id")
            or account.get("uuid")
        )
    elif isinstance(account, str):
        parsed = parse_colon_credentials(account)
        if parsed:
            return parsed
        parts = [part.strip() for part in re.split(r"----|\||;|\t|\r?\n", account, maxsplit=3)]
        if len(parts) >= 2 and "@" in parts[0] and all(parts[:2]):
            email_addr, password = parts[:2]
            refresh_token = parts[2] if len(parts) >= 3 and parts[2] else None
            uuid = parts[3] if len(parts) >= 4 and parts[3] else None
    if email_addr and password:
        return str(email_addr).strip(), str(password), refresh_token, uuid
    return None


def extract_discord_verify_link(content):
    if not content:
        return None
    text = str(content).replace("&amp;", "&").replace("\\/", "/")
    patterns = (
        r"https?://(?:www\.)?discord\.com/verify\?token=[^\s\"'<>\\]+",
        r"https?://click\.discord\.com/ls/click\?[^\s\"'<>\\]+",
    )
    found = []
    for pattern in patterns:
        for url in re.findall(pattern, text, re.IGNORECASE):
            url = url.split("\n")[0].strip()
            url = re.sub(r"[.,;>)]+$", "", url)
            if len(url) > 50:
                found.append(url)
    if not found:
        return None
    verify_links = [link for link in found if "discord.com/verify" in link.lower()]
    links = verify_links or found
    links.sort(key=len, reverse=True)
    return links[0]


def hotmail007_error(data):
    if not isinstance(data, dict):
        return None
    message = data.get("message") or data.get("msg") or ""
    code = data.get("code")
    failed = data.get("success") is False or code not in (None, 0, "0", True, 200)
    if not failed:
        return None
    if code in (20011, "20011") or "authentication failed" in str(message).lower():
        return (
            "API key rejected by Hotmail007. Put a current clientKey in "
            "config/config.yaml (hotmail007_key) from https://hotmail007.com"
        )
    return message or f"code {code}"


def mailbox_records(payload):
    if payload is None:
        return []
    if isinstance(payload, dict):
        records = payload.get("data", payload)
        if isinstance(records, dict):
            nested = records.get("accounts") or records.get("list") or records.get("mail")
            records = nested if nested is not None else [records]
        if isinstance(records, str):
            records = [records]
        return records if isinstance(records, list) else []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, str):
        return [payload]
    return []


async def run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def fetch_mail_domains(api_base, api_key, provider_name):
    if requests is None:
        log_message("ERROR", f"{provider_name} requires curl_cffi")
        return None
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests.get(f"{api_base}/domains", headers=headers, timeout=15, impersonate="chrome124")
        if response.status_code != 200:
            log_message("ERROR", f"{provider_name} domain request failed: HTTP {response.status_code}")
            return None
        data = response_json(response)
        if not isinstance(data, dict):
            log_message("ERROR", f"{provider_name} returned an invalid domain payload")
            return None
        members = data.get("hydra:member", [])
        if not isinstance(members, list):
            log_message("ERROR", f"{provider_name} domain list is not an array")
            return None
        valid_domains = []
        for item in members:
            if not isinstance(item, dict):
                continue
            domain = item.get("domain")
            if domain and item.get("isVerified") and not is_domain_blacklisted(domain):
                valid_domains.append(domain)
        return valid_domains or None
    except Exception as e:
        log_message("ERROR", f"{provider_name} domain lookup failed: {type(e).__name__}")
        return None


async def create_mail_inbox(provider):
    name = getattr(provider, "provider_name", "Mailbox")
    try:
        domains = await run_blocking(provider.get_domains)
        if not domains:
            return None
        domain = random.choice(domains)
        user = "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(10, 16)))
        provider.email = f"{user}@{domain}"
        provider.password = create_random_string(12)

        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        payload = {
            "address": provider.email,
            "password": provider.password,
            "expiresIn": 0 if provider.never_expire else 86400,
        }
        create_resp = await run_blocking(
            requests.post, f"{provider.api_base}/accounts", headers=headers, json=payload, timeout=15, impersonate="chrome124"
        )
        if create_resp.status_code not in [200, 201]:
            log_message("ERROR", f"{name} inbox create failed: HTTP {create_resp.status_code}")
            return None

        token_payload = {"address": provider.email, "password": provider.password}
        token_resp = await run_blocking(
            requests.post, f"{provider.api_base}/token", headers={"Content-Type": "application/json"}, json=token_payload, timeout=15, impersonate="chrome124"
        )
        if token_resp.status_code != 200:
            log_message("ERROR", f"{name} token request failed: HTTP {token_resp.status_code}")
            return None
        token_data = response_json(token_resp)
        if not isinstance(token_data, dict) or not token_data.get("token"):
            log_message("ERROR", f"{name} token response was invalid")
            return None
        provider.auth_token = token_data.get("token")
        provider.account_id = token_data.get("id")
        return provider.email
    except Exception as e:
        log_message("ERROR", f"{name} mailbox error: {type(e).__name__}")
    return None


async def get_mail_verification_url(provider):
    if not provider.auth_token:
        return None
    name = getattr(provider, "provider_name", "Mailbox")
    headers = {"Authorization": f"Bearer {provider.auth_token}"}
    try:
        for _ in range(3):
            response = await run_blocking(
                requests.get, f"{provider.api_base}/messages", headers=headers, timeout=15, impersonate="chrome124"
            )
            if response.status_code != 200:
                await asyncio.sleep(1)
                continue
            data = response_json(response)
            messages = data.get("hydra:member", []) if isinstance(data, dict) else []
            if not isinstance(messages, list):
                await asyncio.sleep(1)
                continue
            for mail in messages:
                if not isinstance(mail, dict):
                    continue
                subject = str(mail.get("subject", "") or "").lower()
                from_data = mail.get("from", {}) or {}
                from_address = str(from_data.get("address", "") or "").lower()
                from_name = str(from_data.get("name", "") or "").lower()
                is_discord = "discord" in from_address or "discord" in from_name
                has_verify = "verify" in subject or "confirm" in subject or "verification" in subject
                if not (is_discord or has_verify):
                    continue
                msg_id = mail.get("id")
                if not msg_id:
                    continue
                detail_resp = await run_blocking(
                    requests.get, f"{provider.api_base}/messages/{msg_id}", headers=headers, timeout=15, impersonate="chrome124"
                )
                if detail_resp.status_code != 200:
                    continue
                msg_detail = response_json(detail_resp) or {}
                content_parts = []
                text_body = str(msg_detail.get("text", "") or "")
                if text_body:
                    content_parts.append(text_body)
                for html_body in msg_detail.get("html", []) or []:
                    content_parts.append(str(html_body or ""))
                full_content = "\n".join(content_parts)
                patterns = [
                    r'https?://(?:www\.)?discord\.com/verify\?token=[a-zA-Z0-9\-\._~%]+',
                    r'https?://click\.discord\.com/ls/click\?upn=[a-zA-Z0-9\-\._~%]+',
                ]
                found_links = []
                for pattern in patterns:
                    for url in re.findall(pattern, full_content, re.IGNORECASE):
                        url = url.replace("\\/", "/").split("\n")[0].strip().replace("&amp;", "&")
                        url = re.sub(r"[.,;>]$", "", url)
                        if len(url) > 50:
                            found_links.append(url)
                if found_links:
                    verify_links = [link for link in found_links if "discord.com/verify" in link]
                    links = verify_links or found_links
                    links.sort(key=len, reverse=True)
                    return links[0]
            await asyncio.sleep(1)
    except Exception as e:
        log_message("WARNING", f"{name} mailbox check failed: {type(e).__name__}")
    return None


class MailboxClient:
    def __init__(self, api_token):
        self.email = None
        self.api_base = "https://api.cybertemp.xyz"
        self.token = api_token
        self.domain = None
        self.password = None

    async def get_domain(self):
        try:
            headers = {"X-API-KEY": self.token}
            params = {"type": "discord", "limit": 20}
            async with httpx.AsyncClient() as session:
                response = await session.get(f"{self.api_base}/getDomains", headers=headers, params=params, timeout=15)
                if response.status_code != 200:
                    log_message("ERROR", f"Cybertemp domain request failed: HTTP {response.status_code}")
                    return "cybertemp.xyz"
                data = response_json(response)
                if not isinstance(data, list):
                    log_message("ERROR", "Cybertemp returned an invalid domain list")
                    return "cybertemp.xyz"
                domains = [d for d in data if isinstance(d, str)]
                if not domains:
                    log_message("ERROR", "Cybertemp returned no usable domains")
                    return "cybertemp.xyz"
                excluded = ["altmails.icu"]
                filtered = [d for d in domains if not d.endswith('.store') and not d.endswith('.ng') and d not in excluded]
                if filtered:
                    return random.choice(filtered)
                usable = [d for d in domains if d not in excluded]
                return random.choice(usable) if usable else "cybertemp.xyz"
        except httpx.RequestError as e:
            log_message("ERROR", f"Cybertemp domain lookup failed: {type(e).__name__}")
        except Exception as e:
            log_message("ERROR", f"Cybertemp domain error: {type(e).__name__}")
        return "cybertemp.xyz"

    async def create_inbox(self):
        try:
            self.domain = await self.get_domain()
            user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(14, 18)))
            self.email = f"{user}@{self.domain}"
            self.password = create_random_string(12)
            return self.email
        except:
            pass
        return None

    async def get_verification_url(self):
        if not self.email:
            return None
        headers = {"X-API-KEY": self.token}
        params = {"email": self.email, "limit": 5}
        async with httpx.AsyncClient() as session:
            try:
                response = await session.get(f"{self.api_base}/getMail", headers=headers, params=params, timeout=15)
                if response.status_code == 200:
                    emails = response.json()
                    if isinstance(emails, list):
                        for mail in emails:
                            content = mail.get('html', '') or mail.get('text', '')
                            subj = mail.get('subject', '')
                            if "verify" in subj.lower() or "discord" in subj.lower():
                                patterns = [
                                    r'https?://click\.discord\.com/ls/click\?upn=[a-zA-Z0-9\-\._~%]+',
                                    r'https?://discord\.com/verify\?token=[a-zA-Z0-9\-\._~%]+'
                                ]
                                links = []
                                for pattern in patterns:
                                    matches = re.findall(pattern, content)
                                    for match in matches:
                                        url = match.replace('\\/', '/').split("\n")[0].strip()
                                        url = url.replace('&amp;', '&')
                                        if "click.discord.com/ls/click?upn=" in url or "discord.com/verify?token=" in url:
                                            if len(url) > 50:
                                                links.append(url)
                                if links:
                                    links.sort(key=len, reverse=True)
                                    return links[0]
            except Exception:
                pass
        return None

class Hotmail007Provider:
    def __init__(self, client_key, mail_type="hotmail", product_id=None):
        self.client_key = str(client_key or "").strip().strip('"').strip("'")
        raw_type = str(mail_type or "hotmail").strip()
        if raw_type.lower() == "8" or raw_type.isdigit():
            self.mail_type = raw_type
            self.product_id = int(raw_type) if product_id in (None, "", 0, "0") else product_id
        else:
            self.mail_type = raw_type
            self.product_id = product_id
        self.email = None
        self.password = None
        self.refresh_token = None
        self.uuid = None
        self.account_line = None
        self.mail_since = None
        self.host = "https://gapi.hotmail007.com"
        self.base_api = f"{self.host}/api"
        self.ms_client_id = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"

    def _product_id(self):
        raw = self.product_id
        if raw in (None, "", 0, "0"):
            mail_type = str(self.mail_type).strip()
            if mail_type.isdigit():
                return int(mail_type)
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _auth_params(self, extra=None):
        params = {"clientKey": self.client_key}
        if extra:
            params.update(extra)
        return params

    def credential_line(self):
        if self.account_line:
            return self.account_line
        parts = [self.email, self.password, self.refresh_token, self.uuid or self.ms_client_id]
        if not self.email or not self.password:
            return None
        return ":".join(str(part) for part in parts if part)

    async def get_access_token(self, r_token=None, c_id=None):
        try:
            token = (r_token or self.refresh_token or "").rstrip("$")
            if not token:
                return None
            cid = c_id or self.uuid or self.ms_client_id
            url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            data = {
                "client_id": cid,
                "refresh_token": token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default"
            }
            async with httpx.AsyncClient() as client:
                r = await client.post(url, data=data, timeout=30)
                if r.status_code == 200:
                    return r.json().get("access_token")
        except:
            pass
        return None

    def _apply_account(self, account):
        parsed = parse_mailbox_account(account)
        if not parsed:
            return None
        self.email, self.password, self.refresh_token, self.uuid = parsed
        if isinstance(account, str) and account.strip():
            self.account_line = account.strip().strip('"').strip("'")
        else:
            self.account_line = self.credential_line()
        self.mail_since = max(0, int(time.time()) - 5)
        return self.email

    async def _resolve_product_id(self, client):
        known = self._product_id()
        if known:
            return known
        wanted = str(self.mail_type).strip().lower().replace(" ", "-")
        try:
            r = await client.get(f"{self.host}/open/stock", timeout=20)
            data = response_json(r) or {}
            products = data.get("data") if isinstance(data, dict) else None
            if not isinstance(products, list):
                return None
            matches = []
            for item in products:
                if not isinstance(item, dict):
                    continue
                mail_type = str(item.get("mailType") or "").strip().lower().replace(" ", "-")
                name = str(item.get("name") or "").strip().lower().replace(" ", "-")
                if wanted in (mail_type, name) or mail_type == wanted:
                    try:
                        stock = int(item.get("stock") or 0)
                    except (TypeError, ValueError):
                        stock = 0
                    matches.append((stock, item.get("productId")))
            in_stock = [pid for stock, pid in matches if stock > 0 and pid not in (None, "")]
            if in_stock:
                return in_stock[0]
            if matches and matches[0][1] not in (None, ""):
                return matches[0][1]
        except Exception:
            return None
        return None

    async def create_inbox(self):
        if not self.client_key:
            log_message("ERROR", "Hotmail007 API key is empty. Set hotmail007_key in config/config.yaml")
            return None
        try:
            async with httpx.AsyncClient() as client:
                product_id = await self._resolve_product_id(client)
                if product_id:
                    r = await client.get(
                        f"{self.host}/open/buy",
                        params=self._auth_params({"productId": product_id, "quantity": 1}),
                        timeout=30,
                    )
                else:
                    r = await client.get(
                        f"{self.base_api}/mail/getMail",
                        params=self._auth_params({"mailType": self.mail_type, "quantity": 1}),
                        timeout=30,
                    )
                if r.status_code != 200:
                    log_message("ERROR", f"Hotmail007 request failed: HTTP {r.status_code}")
                    return None

                data = response_json(r)
                if data is None:
                    log_message("ERROR", "Hotmail007 returned invalid JSON")
                    return None

                rejected = hotmail007_error(data)
                if rejected and product_id and "API key rejected" not in rejected:
                    r = await client.get(
                        f"{self.base_api}/mail/getMail",
                        params=self._auth_params({"mailType": self.mail_type, "quantity": 1}),
                        timeout=30,
                    )
                    data = response_json(r)
                    rejected = hotmail007_error(data) if data else rejected
                if rejected:
                    log_message("ERROR", f"Hotmail007 rejected request: {rejected}")
                    return None
                if data is None:
                    log_message("ERROR", "Hotmail007 returned invalid JSON")
                    return None

                accounts = [item for item in mailbox_records(data) if item not in ("", None, [], {})]
                if not accounts:
                    log_message("ERROR", "Hotmail007 returned no mailbox")
                    return None

                account = accounts[0]
                applied = self._apply_account(account)
                if applied:
                    return applied

                shape = type(account).__name__
                if isinstance(account, dict):
                    shape = f"object fields: {', '.join(sorted(account.keys()))}"
                elif isinstance(account, str):
                    separators = [separator for separator in ("----", "|", ";", ",", ":", "\\t", "\\n") if separator in account]
                    field_lengths = [len(field.strip()) for field in re.split(r"----|\||;|,|\t|\r?\n|:", account)]
                    shape = f"text with {len(account)} characters; separators={separators or ['none']}; field_lengths={field_lengths}"
                log_message("ERROR", f"Hotmail007 returned unsupported mailbox format ({shape})")
        except httpx.RequestError as e:
            log_message("ERROR", f"Hotmail007 connection failed: {type(e).__name__}")
        except Exception as e:
            log_message("ERROR", f"Hotmail007 mailbox error: {type(e).__name__}")
        return None

    def _mail_from_payload(self, payload):
        if isinstance(payload, dict):
            nested = payload.get("data")
            if isinstance(nested, dict):
                payload = nested
            elif isinstance(nested, list) and nested:
                payload = nested[0]
        if not isinstance(payload, dict):
            return extract_discord_verify_link(payload)
        html = payload.get("html") or payload.get("body") or payload.get("content") or ""
        text = payload.get("text") or payload.get("body_text") or ""
        blob = "\n".join(
            str(part) for part in (
                payload.get("subject", ""),
                payload.get("from", ""),
                html,
                text,
            ) if part
        )
        return extract_discord_verify_link(blob)

    async def get_provider_verification_url(self):
        account = self.credential_line()
        if not account:
            return None
        params = {
            "clientKey": self.client_key,
            "account": account,
            "folder": "inbox",
        }
        if self.mail_since:
            params["start_timestamp"] = self.mail_since
        endpoints = (
            f"{self.host}/open/mail/latest",
            f"{self.host}/v1/mail/getFirstMail",
        )
        try:
            async with httpx.AsyncClient() as client:
                for folder in ("inbox", "junkemail"):
                    params["folder"] = folder
                    for endpoint in endpoints:
                        r = await client.get(endpoint, params=params, timeout=20)
                        if r.status_code != 200:
                            continue
                        data = response_json(r)
                        if data is None:
                            continue
                        if hotmail007_error(data):
                            continue
                        link = self._mail_from_payload(data)
                        if link:
                            return link
        except Exception as e:
            log_message("WARNING", f"Hotmail007 inbox lookup failed: {type(e).__name__}")
        return None

    async def get_imap_verification_url(self):
        if not self.email or not self.password:
            return None

        def read_messages():
            mailbox = imaplib.IMAP4_SSL("outlook.office365.com", 993)
            try:
                mailbox.login(self.email, self.password)
                mailbox.select("INBOX")
                status, result = mailbox.search(None, "ALL")
                if status != "OK":
                    return None

                message_ids = result[0].split()[-20:]
                for message_id in reversed(message_ids):
                    status, message_data = mailbox.fetch(message_id, "(RFC822)")
                    if status != "OK":
                        continue
                    raw_message = next(
                        (item[1] for item in message_data if isinstance(item, tuple)),
                        None,
                    )
                    if not raw_message:
                        continue

                    message = email.message_from_bytes(raw_message)
                    subject = str(email.header.make_header(email.header.decode_header(message.get("Subject", "")))).lower()
                    sender = message.get("From", "").lower()
                    body_parts = []
                    if message.is_multipart():
                        for part in message.walk():
                            if part.get_content_type() in ("text/plain", "text/html"):
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                    else:
                        payload = message.get_payload(decode=True)
                        if payload:
                            body_parts.append(payload.decode(message.get_content_charset() or "utf-8", errors="replace"))

                    body = "\n".join([subject, sender, *body_parts])
                    link = extract_discord_verify_link(body)
                    if link:
                        return link
            finally:
                try:
                    mailbox.logout()
                except Exception:
                    pass
            return None

        try:
            return await asyncio.to_thread(read_messages)
        except Exception as e:
            log_message("WARNING", f"Hotmail007 IMAP mailbox check failed: {type(e).__name__}")
            return None

    async def get_verification_url(self):
        link = await self.get_provider_verification_url()
        if link:
            return link
        if self.refresh_token:
            access = await self.get_access_token()
            if access:
                try:
                    async with httpx.AsyncClient() as client:
                        r = await client.get(
                            "https://graph.microsoft.com/v1.0/me/messages",
                            headers={"Authorization": f"Bearer {access}"},
                            params={"$top": 10, "$orderby": "receivedDateTime desc", "$select": "subject,body,from"},
                            timeout=15
                        )
                        if r.status_code == 200:
                            for msg in r.json().get("value", []):
                                subj = msg.get("subject", "").lower()
                                from_data = msg.get("from", {}).get("emailAddress", {})
                                frm_addr = from_data.get("address", "").lower()
                                frm_name = from_data.get("name", "").lower()
                                is_discord = "discord" in frm_addr or "discord" in frm_name
                                has_verify = "verify" in subj or "confirm" in subj or "verification" in subj
                                if is_discord and has_verify:
                                    body = msg.get("body", {}).get("content", "")
                                    link = extract_discord_verify_link(body)
                                    if link:
                                        return link
                except Exception:
                    pass
        if not self.account_line:
            return await self.get_imap_verification_url()
        return None


class ZeusXProvider:
    def __init__(self, api_key, account_code="HOTMAIL"):
        self.api_key = api_key
        self.account_code = account_code
        self.email = None
        self.password = None
        self.refresh_token = None
        self.uuid = None
        self.base_api = "https://api.zeus-x.ru"
        self.ms_client_id = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"

    async def get_access_token(self, r_token=None, c_id=None):
        try:
            token = (r_token or self.refresh_token).rstrip("$")
            cid = c_id or self.uuid or self.ms_client_id
            url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            data = {
                "client_id": cid,
                "refresh_token": token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default"
            }
            async with httpx.AsyncClient() as client:
                r = await client.post(url, data=data, timeout=30)
                if r.status_code == 200:
                    return r.json().get("access_token")
        except:
            pass
        return None

    async def create_inbox(self):
        url = f"{self.base_api}/purchase?apikey={self.api_key}&accountcode={self.account_code}&quantity=1"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=30)
                if r.status_code != 200:
                    log_message("ERROR", f"Zeus-X request failed: HTTP {r.status_code}")
                    return None
                data = response_json(r)
                if data is None:
                    log_message("ERROR", "Zeus-X returned invalid JSON")
                    return None
                if isinstance(data, dict) and data.get("success") is False:
                    message = data.get("message") or data.get("msg") or "request rejected"
                    log_message("ERROR", f"Zeus-X rejected request: {message}")
                    return None
                accounts = mailbox_records(data)
                if not accounts:
                    log_message("ERROR", "Zeus-X returned no mailbox")
                    return None
                parsed = parse_mailbox_account(accounts[0])
                if not parsed:
                    log_message("ERROR", "Zeus-X returned unsupported mailbox format")
                    return None
                self.email, self.password, self.refresh_token, self.uuid = parsed
                return self.email
        except httpx.RequestError as e:
            log_message("ERROR", f"Zeus-X connection failed: {type(e).__name__}")
        except Exception as e:
            log_message("ERROR", f"Zeus-X mailbox error: {type(e).__name__}")
        return None

    async def get_verification_url(self):
        if not self.refresh_token:
            return None
        access = await self.get_access_token()
        if not access:
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers={"Authorization": f"Bearer {access}"},
                    params={"$top": 10, "$orderby": "receivedDateTime desc", "$select": "subject,body,from"},
                    timeout=15
                )
                if r.status_code == 200:
                    for msg in r.json().get("value", []):
                        subj = msg.get("subject", "").lower()
                        from_data = msg.get("from", {}).get("emailAddress", {})
                        frm_addr = from_data.get("address", "").lower()
                        frm_name = from_data.get("name", "").lower()
                        is_discord = "discord" in frm_addr or "discord" in frm_name
                        has_verify = "verify" in subj or "confirm" in subj or "verification" in subj
                        if is_discord and has_verify:
                            body = msg.get("body", {}).get("content", "")
                            body = body.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
                            matches = re.findall(r'https://discord\.com/verify\?token=[^\s"\'><]+', body)
                            if matches:
                                return matches[0]
                            tracked_links = re.findall(r'https://click\.discord\.com/ls/click\?[^\s"\'><]+', body)
                            for link in tracked_links:
                                try:
                                    async with httpx.AsyncClient() as check_client:
                                        res = await check_client.get(link, follow_redirects=False, timeout=10)
                                        target = res.headers.get("Location", "")
                                        if "discord.com/verify" in target:
                                            return link
                                except Exception:
                                    continue
        except Exception:
            pass
        return None


class DuckMailProvider:
    def __init__(self, api_key=None, never_expire=False):
        self.email = None
        self.password = None
        self.api_base = "https://api.duckmail.sbs"
        self.api_key = api_key
        self.auth_token = None
        self.account_id = None
        self.never_expire = never_expire
        self.provider_name = "DuckMail"

    def get_domains(self):
        return fetch_mail_domains(self.api_base, self.api_key, self.provider_name)

    async def create_inbox(self, session=None):
        return await create_mail_inbox(self)

    async def get_verification_url(self):
        return await get_mail_verification_url(self)


class CrowMailProvider:
    def __init__(self, api_key=None, never_expire=False):
        self.email = None
        self.password = None
        self.api_base = "https://api.crowmail.sbs"
        self.api_key = api_key
        self.auth_token = None
        self.account_id = None
        self.never_expire = never_expire
        self.provider_name = "CrowMail"

    def get_domains(self):
        return fetch_mail_domains(self.api_base, self.api_key, self.provider_name)

    async def create_inbox(self, session=None):
        return await create_mail_inbox(self)

    async def get_verification_url(self):
        return await get_mail_verification_url(self)


class AfhamMailProvider:
    def __init__(self, api_key=""):
        self.api_key = api_key
        self.api_base = "https://api.afhamxmailz.com"
        self.email = None
        self.inbox_id = None
        self.password = None

    def _headers(self):
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def get_discord_domain(self):
        try:
            async with httpx.AsyncClient() as session:
                response = await session.get(
                    f"{self.api_base}/domains",
                    headers=self._headers(),
                    params={"type": "discord"},
                    timeout=15,
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        valid = [
                            d["domain"] for d in data
                            if isinstance(d, dict)
                            and d.get("status") == "active"
                            and not d.get("domain", "").endswith(".store")
                            and not d.get("domain", "").endswith(".ng")
                        ]
                        if valid:
                            return random.choice(valid)
        except:
            pass
        return None

    async def create_inbox(self):
        try:
            domain = await self.get_discord_domain()
            if not domain:
                return None

            user = "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(10, 16)))
            self.password = create_random_string(12)
            payload = {
                "username": user,
                "domain": domain,
                "password": self.password,
            }
            async with httpx.AsyncClient() as session:
                response = await session.post(
                    f"{self.api_base}/inbox/generate",
                    headers=self._headers(),
                    json=payload,
                    params={"type": "discord"},
                    timeout=15,
                )
                if response.status_code in [200, 201]:
                    data = response_json(response)
                    if not isinstance(data, dict) or not data.get("address"):
                        log_message("ERROR", "Afham returned an invalid inbox payload")
                        return None
                    self.email = data.get("address")
                    self.inbox_id = data.get("id")
                    return self.email
                log_message("ERROR", f"Afham inbox create failed: HTTP {response.status_code}")
        except httpx.RequestError as e:
            log_message("ERROR", f"Afham connection failed: {type(e).__name__}")
        except Exception as e:
            log_message("ERROR", f"Afham mailbox error: {type(e).__name__}")
        return None

    async def get_verification_url(self):
        if not self.email:
            return None
        try:
            async with httpx.AsyncClient() as session:
                response = await session.get(
                    f"{self.api_base}/emails/{self.email}/wait",
                    headers=self._headers(),
                    params={"timeout": 30},
                    timeout=40,
                )
                emails = []
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        emails = data

                if not emails:
                    response = await session.get(
                        f"{self.api_base}/emails/{self.email}",
                        headers=self._headers(),
                        params={"per_page": 20, "unread_only": False},
                        timeout=15,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        emails = data.get("emails", []) if isinstance(data, dict) else data

                for mail in emails:
                    subject = str(mail.get("subject", "") or "").lower()
                    from_address = str(mail.get("from_address", "") or "").lower()
                    from_name = str(mail.get("from_name", "") or "").lower()
                    is_discord = "discord" in from_address or "discord" in from_name
                    has_verify = "verify" in subject or "confirm" in subject or "verification" in subject
                    if not (is_discord or has_verify):
                        continue

                    msg_id = mail.get("id")
                    if not msg_id:
                        continue

                    detail_resp = await session.get(
                        f"{self.api_base}/emails/message/{msg_id}",
                        headers=self._headers(),
                        timeout=15,
                    )
                    if detail_resp.status_code != 200:
                        continue

                    msg = detail_resp.json()
                    full_content = (
                        str(msg.get("body_text", "") or "") + "\n" +
                        str(msg.get("body_html", "") or "")
                    ).replace("&amp;", "&")

                    patterns = [
                        r'https?://(?:www\.)?discord\.com/verify\?token=[a-zA-Z0-9\-\._~%]+',
                        r'https?://click\.discord\.com/ls/click\?upn=[a-zA-Z0-9\-\._~%]+',
                    ]
                    links = []
                    for pattern in patterns:
                        for url in re.findall(pattern, full_content, re.IGNORECASE):
                            url = url.replace("\\/", "/").split("\n")[0].strip()
                            url = re.sub(r"[.,;>]$", "", url)
                            if len(url) > 50:
                                links.append(url)

                    if links:
                        verify_links = [l for l in links if "discord.com/verify" in l]
                        if verify_links:
                            verify_links.sort(key=len, reverse=True)
                            return verify_links[0]
                        links.sort(key=len, reverse=True)
                        return links[0]
        except:
            pass
        return None


def check_environment():
    path, _name = find_browser_path()
    return bool(path)


class BrowserContext:
    def __init__(self):
        self.driver = None

    async def start(self, url, extension_path=None, proxy=None, fingerprint=None):
        browser_path, browser_name = find_browser_path()
        if not browser_path:
            log_message(
                "ERROR",
                "no supported browser found. install Brave (recommended) or Chrome, then set browser_path to the .exe",
            )
            return None

        args = [
            "--lang=en-US",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-hang-monitor",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-features=Translate,OptimizationHints,MediaRouter",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,800",
        ]
        if "vivaldi" in (browser_name or "").lower() or "vivaldi" in browser_path.lower():
            args.extend(["--disable-gpu", "--disable-software-rasterizer"])
        if fingerprint:
            args.extend(build_fingerprint_args(fingerprint))
        if extension_path:
            args.append(f"--load-extension={extension_path}")

        try:
            log_message("INFO", f"using {browser_name}: {browser_path}")
            self.driver = await get_truedriver().start(
                browser_executable_path=browser_path,
                browser_args=args,
                proxy=proxy
            )
            tab = await self.driver.get(url)
            try:
                await tab.wait_for_ready_state('complete', timeout=12000)
            except Exception:
                pass
            ready = await self.wait_for_registration_form(tab)
            if not ready:
                log_message("WARNING", "discord register page did not render; reloading once")
                try:
                    await tab.reload()
                    await tab.wait_for_ready_state('complete', timeout=12000)
                except Exception:
                    pass
                ready = await self.wait_for_registration_form(tab)
            try:
                await tab.evaluate(JS_UTILS)
            except:
                pass
            if not ready:
                log_message("ERROR", "discord page stayed blank (no registration form)")
                return None
            return tab
        except Exception as e:
            log_message("ERROR", f"browser start failed: {str(e)}")
            return None

    async def wait_for_registration_form(self, tab, timeout=12):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                found = await tab.evaluate("() => !!document.querySelector('input[name=\"email\"]')")
                if found:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.15)
        return False

    async def stop(self):
        if self.driver:
            try:
                await self.driver.stop()
            except:
                pass
            finally:
                self.driver = None


class AccountCreator:
    def __init__(self, api_key, mailbox_class, extension_path=None, proxy=None, custom_display_name=None, fingerprint=None):
        self.extension_path = extension_path
        self.proxy = proxy
        self.custom_display_name = custom_display_name
        self.fingerprint = fingerprint
        self.mailbox = mailbox_class(api_key)
        self.browser = BrowserContext()
        self.password = None
        self.email = None
        self.token = None
        self.session = tls_client.Session(
            client_identifier="chrome_131",
            random_tls_extension_order=True
        )
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def save_account_locally(self, status, token=""):
        try:
            output_dir = Path(get_path("output"))
            output_dir.mkdir(exist_ok=True)
            if status == "valid" and token:
                acc_path = output_dir / "accounts.txt"
                tok_path = output_dir / "tokens.txt"
                with open(acc_path, "a", encoding="utf-8") as f:
                    f.write(f"{self.email}:{self.password}:{token}\n")
                with open(tok_path, "a", encoding="utf-8") as f:
                    f.write(f"{token}\n")
            elif status == "locked" and token:
                locked_path = output_dir / "locked.txt"
                with open(locked_path, "a", encoding="utf-8") as f:
                    f.write(f"{self.email}:{self.password}:{token}\n")
        except OSError as e:
            log_message("ERROR", f"failed to write account output: {e}")
            raise

    async def report_status(self, status, token=""):
        self.save_account_locally(status, token)

    async def run(self):
        start_time = time.time()
        try:
            addr = await self.mailbox.create_inbox()
            if not addr:
                log_message("ERROR", "mail failed")
                return None
            self.email = addr
            log_message("SUCCESS", f"mail pulled: {addr}")

            page = await self.browser.start("https://discord.com/register", extension_path=self.extension_path, proxy=self.proxy, fingerprint=self.fingerprint)
            if not page:
                log_message("ERROR", "browser failed")
                return None

            if self.fingerprint:
                try:
                    import truedriver.cdp.page as cdp_page
                    fp_script = build_fingerprint_script(self.fingerprint)
                    if fp_script:
                        await page.send(cdp_page.enable())
                        await page.send(cdp_page.add_script_to_evaluate_on_new_document(source=fp_script))
                        log_message("INFO", f"fingerprint: {get_fingerprint_label(self.fingerprint)}")
                except Exception as _fp_e:
                    log_message("WARNING", f"fingerprint inject failed: {_fp_e}")

            try:
                first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
                last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
                display_name = self.custom_display_name or f"{random.choice(first_names)} {random.choice(last_names)}"
                user_name = make_handle()
                secret = self.mailbox.password or create_random_string(14)
                self.password = secret

                success = await self.fill_registration_form(page, addr, display_name, user_name, secret)
                if not success:
                    log_message("ERROR", "form failed")
                    return None, 0

                await self.handle_challenges(page)

                result = await self.verify_email()
                if result:
                    end_time = time.time()
                    return result, end_time - start_time
                else:
                    log_message("ERROR", "verify failed")
                    return None, 0
            except Exception as e:
                log_message("ERROR", f"error: {str(e)}")
                return None, 0
            finally:
                await self.browser.stop()
        except Exception as e:
            log_message("ERROR", f"fatal: {str(e)}")
            return None, 0

    async def human_type(self, element, text: str):
        await element.send_keys(text)

    async def fill_input(self, page, selector: str, value: str, timeout: int = 8):
        selector_js = json.dumps(selector)
        value_js = json.dumps(value)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                filled = await page.evaluate(
                    f'''() => {{
                        const el = document.querySelector({selector_js});
                        if (!el) return false;
                        el.focus();
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                        if (setter) setter.call(el, {value_js});
                        else el.value = {value_js};
                        el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                        return true;
                    }}'''
                )
                if filled:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.15)
        raise Exception(f"Element not found: {selector}")

    async def clear_and_type(self, page, selector: str, value: str, timeout: int = 8):
        await self.fill_input(page, selector, value, timeout=timeout)

    async def detect_registration_issue(self, page) -> Optional[dict]: 
        try: 
            result = await page.evaluate('''() => { 
                const text = (document.body?.innerText || "").toLowerCase(); 
                const emailInvalid = text.includes("email is invalid") || 
                                    text.includes("invalid email") || 
                                    text.includes("email is not valid") || 
                                    !!document.querySelector('input[name="email"][aria-invalid="true"]'); 
                const usernameTaken = text.includes("username is already taken") || 
                                     text.includes("username already taken") || 
                                     text.includes("username is unavailable") || 
                                     text.includes("username taken") || 
                                     !!document.querySelector('input[name="username"][aria-invalid="true"]'); 
                if (emailInvalid || usernameTaken) { 
                    return { email_invalid: emailInvalid, username_taken: usernameTaken }; 
                } 
                return null; 
            }''') 
            if isinstance(result, dict): 
                return result 
        except: 
            pass
        return None 

    async def fill_registration_form(self, page, email: str, display_name: str, username: str, password: str) -> bool:
        try:
            try:
                await self.fill_input(page, 'input[name="email"]', email, timeout=8)
            except Exception as e:
                log_message("ERROR", "form failed: registration fields never appeared")
                return False
            try:
                await self.fill_input(page, 'input[name="global_name"]', display_name, timeout=5)
                await self.fill_input(page, 'input[name="username"]', username, timeout=5)
                await self.fill_input(page, 'input[name="password"]', password, timeout=5)
            except Exception as e:
                return False
            await self.fill_date_of_birth(page)
            try:
                await page.evaluate(JS_UTILS)
                await page.evaluate('window.utils.clickAllCheckboxes()')
            except Exception as e:
                pass
            clicked = False
            try:
                buttons = await page.select_all('button')
                for button in buttons:
                    try:
                        text = (await button.get_text() or "").strip()
                        if not text: text = (button.text or "").strip()
                        if text and any(keyword in text for keyword in ['Continue', 'Create', 'Submit', 'Register']):
                            await button.click()
                            clicked = True
                            break
                    except: continue
            except: pass
            if not clicked:
                try:
                    submit = await page.select('[type="submit"]', timeout=0)
                    if submit:
                        await submit.click()
                        clicked = True
                except: pass
            if not clicked:
                try:
                    clicked_eval = await page.evaluate('''() => { 
                        const buttons = document.querySelectorAll('button'); 
                        for (const btn of buttons) { 
                            const text = btn.textContent || ''; 
                            if (text.includes('Continue') || text.includes('Create') || text.includes('Submit')) { 
                                btn.click(); 
                                return true; 
                            } 
                        } 
                        return false; 
                    }''')
                    if clicked_eval: clicked = True
                except Exception as e: pass
            if not clicked: return False
            return True
        except Exception as e: 
            return False

    async def fill_date_of_birth(self, page):
        try:
            filled = await page.evaluate('''() => {
                const setListbox = (labelPart, optionText) => {
                    const trigger = document.querySelector(`[aria-label*="${labelPart}"]`);
                    if (!trigger) return false;
                    trigger.click();
                    const options = [...document.querySelectorAll('[role="option"], [role="listbox"] *')];
                    const match = options.find(el => (el.textContent || "").trim().startsWith(optionText));
                    if (match) { match.click(); return true; }
                    trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
                    return true;
                };
                const year = String(1990 + Math.floor(Math.random() * 10));
                const month = ["January","February","March","April","May","June","July","August","September","October","November","December"][Math.floor(Math.random()*12)];
                const day = String(1 + Math.floor(Math.random()*27));
                setListbox("Month", month.slice(0, 3));
                setListbox("Day", day);
                setListbox("Year", year);
                return true;
            }''')
            if filled:
                return
        except Exception:
            pass
        import truedriver.cdp.input_ as cdp_input
        try:
            async def pick(selector, downs):
                el = await page.select(selector, timeout=3)
                await el.click()
                for _ in range(downs):
                    await page.send(cdp_input.dispatch_key_event(type_="keyDown", key="ArrowDown", windows_virtual_key_code=40, native_virtual_key_code=40))
                    await page.send(cdp_input.dispatch_key_event(type_="keyUp", key="ArrowDown", windows_virtual_key_code=40, native_virtual_key_code=40))
                await page.send(cdp_input.dispatch_key_event(type_="keyDown", key="Enter", windows_virtual_key_code=13, native_virtual_key_code=13))
                await page.send(cdp_input.dispatch_key_event(type_="keyUp", key="Enter", windows_virtual_key_code=13, native_virtual_key_code=13))
            await pick('[aria-label*="Month"], [aria-label*="Mês"]', random.randint(1, 4))
            await pick('[aria-label*="Day"], [aria-label*="Dia"]', random.randint(1, 5))
            await pick('[aria-label*="Year"], [aria-label*="Ano"]', random.randint(8, 14))
        except Exception:
            pass

    async def handle_challenges(self, page):
        try:
            is_active = False
            clear_started = None
            stable_wait = 1.5
            for i in range(90):
                queries = ['iframe[src*="captcha"]', 'div[class*="captcha"]', '.h-captcha', '.g-recaptcha', '[data-sitekey]']
                detected = False
                for q in queries:
                    try:
                        el = await page.query_selector(q)
                        if el and await el.is_visible():
                            detected = True
                            break
                    except:
                        continue

                if detected and not is_active:
                    log_message("WARNING", "captcha appeared")
                    is_active = True
                    clear_started = None

                if not detected:
                    if is_active:
                        if clear_started is None:
                            clear_started = time.monotonic()
                        elapsed = time.monotonic() - clear_started
                        if elapsed >= stable_wait:
                            log_message("SUCCESS", "captcha solved")
                            return True
                    elif i >= 2:
                        return True
                else:
                    clear_started = None

                await asyncio.sleep(0.25)
        except Exception:
            pass
        return True

    async def get_generated_token(self, page):
        script = """
        (function() {
            try {
                const chunks = window.webpackChunkdiscord_app;
                let store;
                chunks.push([['__extra_extract__'], {}, (e) => { store = Object.values(e.c); }]);
                const mod = store.find(m => m?.exports?.default?.getToken !== undefined);
                const auth = mod.exports.default.getToken();
                if (auth) return auth;
            } catch (e) {}
            try {
                const node = document.createElement('iframe');
                document.body.appendChild(node);
                const auth = node.contentWindow.localStorage.token;
                document.body.removeChild(node);
                if (auth) return auth.replace(/\"/g, "");
            } catch (e) {}
            return null;
        })();
        """
        try:
            return await page.evaluate(script)
        except:
            return None

    async def wait_for_auth(self, page, timeout=180):
        start_time = time.time()
        attempts = 0
        while time.time() - start_time < timeout:
            try:
                attempts += 1
                token = await self.get_generated_token(page)
                if token and len(str(token)) > 30:
                    log_message("INFO", f"Token found, validating...")
                    status = self.check_token_status(token)
                    if status == "valid":
                        log_message("SUCCESS", "Token validated successfully")
                        return token, status
                    elif status == "locked":
                        log_message("WARNING", "Token authenticated but account is locked (phone verification required)")
                        return token, status
                    else:
                        log_message("WARNING", "Token invalid, retrying...")

                # Progress update every 30 seconds
                if attempts % 6 == 0:
                    elapsed = int(time.time() - start_time)
                    log_message("INFO", f"Waiting for token... ({elapsed}s / {timeout}s)")

            except Exception as e:
                log_message("WARNING", f"Token check error: {str(e)}")
            await asyncio.sleep(1)
        log_message("ERROR", f"Token wait timeout ({timeout}s)")
        return None, None

    def check_token_status(self, token):
        if not isinstance(token, str) or not token:
            return "invalid"

        endpoint = "https://discord.com/api/v9/users/@me"
        headers = get_headers()
        headers["Authorization"] = token
        try:
            resp = self.session.get(endpoint, headers=headers)
            if resp.status_code == 200:
                try:
                    library = self.session.get(
                        "https://discordapp.com/api/v9/users/@me/library",
                        headers=headers,
                        timeout=5,
                    )
                    if library.status_code == 403:
                        return "locked"
                except Exception:
                    pass
                return "valid"
            if resp.status_code == 403:
                return "locked"
            if resp.status_code in (401, 400):
                return "invalid"
        except Exception:
            pass
        return "invalid"

    async def try_unlock_locked_token(self, token):
        if not isinstance(token, str) or not token:
            return None
        if not self.email or not self.password:
            return None

        status = self.check_token_status(token)
        if status != "locked":
            return token

        log_message("WARNING", "token appears locked, trying to re-authenticate with the generated email/password")
        fresh_token = await fetch_discord_token(self.email, self.password, proxy_config={"http": self.proxy, "https": self.proxy} if self.proxy else None)
        if not fresh_token:
            return None

        fresh_status = self.check_token_status(fresh_token)
        if fresh_status == "valid":
            log_message("SUCCESS", "token unlocked successfully via re-login")
            return fresh_token
        log_message("WARNING", "re-login did not produce a valid token")
        return None

    async def verify_email(self):
        url = None
        log_message("INFO", "Waiting for verification email...")
        for attempt in range(180):
            try:
                url = await self.mailbox.get_verification_url()
                if url:
                    break
            except Exception as e:
                if attempt % 20 == 0 and attempt > 0:
                    log_message("WARNING", f"Still waiting for email ({attempt}s)")
            await asyncio.sleep(0.35)

        if not url:
            log_message("ERROR", "Mail timeout")
            return None

        try:
            if not self.browser.driver:
                log_message("ERROR", "Browser not available")
                return None

            log_message("INFO", "Opening verification link...")
            tab = await asyncio.wait_for(
                self.browser.driver.get(url, new_tab=True),
                timeout=30
            )

            log_message("INFO", "Extracting authentication token...")
            challenge_task = asyncio.create_task(self.handle_challenges(tab))
            token, status = await self.wait_for_auth(tab, timeout=90)

            try:
                challenge_task.cancel()
                await asyncio.sleep(0.1)
            except:
                pass

            if not token:
                log_message("ERROR", "Token extraction failed")
                return None

            log_message("INFO", "Verifying token...")

            if status == "locked":
                unlocked_token = await self.try_unlock_locked_token(token)
                if unlocked_token:
                    log_message("SUCCESS", "Unlocked token was revalidated successfully")
                    log_token(f"{unlocked_token[:24]}{'*' * 12}")
                    self.save_data(unlocked_token)
                    return unlocked_token

                mask = f"{token[:24]}{'*' * 12}"
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"{Fore.LIGHTBLACK_EX}{ts}{Style.RESET_ALL}  {Fore.YELLOW}WAR{Style.RESET_ALL}  {Fore.WHITE}Locked: {Style.RESET_ALL}{Fore.LIGHTBLACK_EX}{mask}{Style.RESET_ALL}")
                try:
                    output_dir = Path(get_path("output"))
                    output_dir.mkdir(exist_ok=True)
                    with open(output_dir / "locked.txt", "a", encoding="utf-8") as f:
                        f.write(f"{self.email}:{self.password}:{token}\n")
                except OSError as e:
                    log_message("ERROR", f"failed to write locked account output: {e}")
                    raise
                return "LOCKED"

            log_message("SUCCESS", "Verified successfully")
            log_token(f"{token[:24]}{'*' * 12}")
            self.save_data(token)
            return token
        except asyncio.TimeoutError:
            log_message("ERROR", "Verification page timeout")
            return None
        except Exception as e:
            log_message("ERROR", f"Verify error: {str(e)}")
            return None

    def save_data(self, token):
        try:
            output_dir = Path(get_path("output"))
            output_dir.mkdir(exist_ok=True)
            with open(output_dir / "tokens.txt", "a", encoding="utf-8") as f:
                f.write(token + "\n")
            with open(output_dir / "accounts.txt", "a", encoding="utf-8") as f:
                f.write(f"{self.email}:{self.password}:{token}\n")
            self.token = token
        except OSError as e:
            log_message("ERROR", f"failed to write account output: {e}")
            raise



def _load_fp_lines() -> list:
    if not FP_FILE.exists():
        return []
    lines = []
    for line in FP_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            lines.append(line)
    return lines


def parse_fingerprint_line(raw_line: str) -> dict:
    import re as _re
    raw_line = raw_line.strip()
    if _re.match(r'^\d+\.[A-Za-z0-9_-]+$', raw_line):
        return {'fingerprint': raw_line}
    try:
        obj = json.loads(raw_line)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {'user_agent': raw_line}


def peek_next_fingerprint() -> tuple:
    with _fp_lock:
        lines = _load_fp_lines()
        if not lines:
            return None, None
        raw_line = lines[0]
        return parse_fingerprint_line(raw_line), raw_line


def consume_fingerprint_line(raw_line: str) -> bool:
    with _fp_lock:
        lines = _load_fp_lines()
        if raw_line not in lines:
            return False
        lines.remove(raw_line)
        FP_FILE.write_text(chr(10).join(lines) + (chr(10) if lines else ""), encoding="utf-8")
        return True


def build_fingerprint_args(fp: dict) -> list:
    args = []
    user_agent = fp.get('user_agent')
    if user_agent:
        args.append(f'--user-agent={user_agent}')
    language = fp.get('language') or fp.get('accept_language')
    if language:
        args.append(f'--lang={language}')
    window_size = fp.get('window_size')
    if isinstance(window_size, str) and ',' in window_size:
        args.append(f'--window-size={window_size}')
    return args


def build_fingerprint_script(fp: dict):
    entries = []
    user_agent = fp.get('user_agent')
    if user_agent:
        entries.append(
            f"try {{ Object.defineProperty(navigator, 'userAgent', {{get: () => {json.dumps(user_agent)}, configurable: true}}); }} catch(e) {{}}"
        )
    platform_val = fp.get('platform')
    if platform_val:
        entries.append(
            f"try {{ Object.defineProperty(navigator, 'platform', {{get: () => {json.dumps(platform_val)}, configurable: true}}); }} catch(e) {{}}"
        )
    languages = fp.get('languages') or fp.get('navigator_languages')
    if languages:
        if isinstance(languages, str):
            languages = [lang.strip() for lang in languages.split(',') if lang.strip()]
        entries.append(
            f"try {{ Object.defineProperty(navigator, 'languages', {{get: () => {json.dumps(languages)}, configurable: true}}); }} catch(e) {{}}"
        )
    vendor = fp.get('vendor')
    if vendor:
        entries.append(
            f"try {{ Object.defineProperty(navigator, 'vendor', {{get: () => {json.dumps(vendor)}, configurable: true}}); }} catch(e) {{}}"
        )
    if fp.get('webdriver') is not None:
        webdriver_val = str(fp.get('webdriver')).lower()
        entries.append(
            f"try {{ Object.defineProperty(navigator, 'webdriver', {{get: () => {webdriver_val}, configurable: true}}); }} catch(e) {{}}"
        )
    fingerprint_value = fp.get('fingerprint')
    if fingerprint_value:
        entries.append("""
        try {
            var fpVal = """ + json.dumps(fingerprint_value) + """;
            try {
                if (typeof window !== 'undefined' && window.Storage && window.Storage.prototype) {
                    if (!window.Storage.prototype.setItem.__org) {
                        const orgSetItem = window.Storage.prototype.setItem;
                        window.Storage.prototype.setItem = function(key, val) {
                            if (key === 'fingerprint') {
                                val = JSON.stringify(fpVal);
                            } else if (key === 'deviceProperties') {
                                try {
                                    let parsed = JSON.parse(val);
                                    if (parsed) {
                                        parsed.fingerprint = fpVal;
                                        val = JSON.stringify(parsed);
                                    }
                                } catch(e) {}
                            }
                            return orgSetItem.call(this, key, val);
                        };
                        window.Storage.prototype.setItem.__org = orgSetItem;
                    }
                }
            } catch (e) {}
            function setFp() {
                try {
                    if (typeof window !== 'undefined' && window.localStorage && window.Storage && window.Storage.prototype) {
                        const orgSetItem = window.Storage.prototype.setItem.__org || window.Storage.prototype.setItem;
                        if (orgSetItem) {
                            orgSetItem.call(window.localStorage, 'fingerprint', JSON.stringify(fpVal));
                            var dp = window.localStorage.getItem('deviceProperties');
                            if (dp) {
                                var parsed = JSON.parse(dp);
                                if (parsed && parsed.fingerprint !== fpVal) {
                                    parsed.fingerprint = fpVal;
                                    orgSetItem.call(window.localStorage, 'deviceProperties', JSON.stringify(parsed));
                                }
                            }
                            return true;
                        }
                    }
                } catch(e) {}
                return false;
            }
            setFp();
            if (typeof window !== 'undefined') {
                window.addEventListener('DOMContentLoaded', setFp);
                window.addEventListener('load', setFp);
                var interval = setInterval(function() { setFp(); }, 50);
                setTimeout(function() { clearInterval(interval); }, 10000);
            }
        } catch(e) {}
        """)
    if not entries:
        return None
    script = chr(10).join(entries)
    return "(() => {" + chr(10) + script + chr(10) + "})()"


def get_fingerprint_label(fp: dict) -> str:
    if not fp:
        return 'none'
    return fp.get('name') or fp.get('fingerprint', '')[:20] or fp.get('user_agent', '')[:40] or 'custom'


def soften_windows_yaml_paths(text):
    """YAML double quotes treat \\Users as an escape. Convert those paths to single quotes."""

    def replacer(match):
        inner = match.group(1).replace("\\\\", "\\")
        return "'" + inner.replace("'", "''") + "'"

    return re.sub(r'"([A-Za-z]:\\[^"\n]*)"', replacer, text)


def load_yaml_config(config_path):
    raw = Path(config_path).read_text(encoding="utf-8")
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError:
        loaded = yaml.safe_load(soften_windows_yaml_paths(raw))
    if not isinstance(loaded, dict):
        raise ValueError("config.yaml must contain a mapping of settings")
    return loaded


def setup_files():
    folders = ["config", "extension", "output", "data", "data/avatars", "input"]
    for folder in folders:
        Path(get_path(folder)).mkdir(exist_ok=True, parents=True)
    
    config_path = Path(get_path("config/config.yaml"))
    if not config_path.exists():
        with open(config_path, "w") as f:
            yaml.dump({
                "cybertemp_key": "",
                "hotmail007_key": "",
                "zeusx_key": "",
                "afham_mail_api9_key": "",
                "vpn": False,
                "vpn_delay": 120,
                "browser": "auto",
                "browser_path": "",
            }, f)
    
    nopecha_path = Path(get_path("config/nopecha.txt"))
    if not nopecha_path.exists():
        nopecha_path.write_text("")

    fp_path = Path(get_path("input/fp.txt"))
    if not fp_path.exists():
        fp_path.write_text("")



async def main():
    clear_screen()
    set_console_title()
    setup_files()
    
    try:
        config_path = get_path("config/config.yaml")
        if not os.path.exists(config_path):
            log_message("ERROR", f"config not found at: {config_path}")
            prompt_user("press enter to exit")
            return

        cfg = load_yaml_config(config_path)
        use_vpn = cfg.get('vpn', False)
        vpn_delay = int(cfg.get('vpn_delay', 8))
        configure_browser(cfg)
    except Exception as e:
        log_message("ERROR", f"config error: {e}")
        prompt_user("press enter to exit")
        return

    if use_vpn:
        if not await require_vpn_connection():
            prompt_user("press enter to exit")
            return

    if not check_environment():
        log_message("WARNING", "brave/chrome not found. install Brave for Discord pages to load")

    proxies = load_proxies(cfg)

    show_interface()
    
    service = prompt_user("Service:").strip().lower()
    if service == 'h':
        key = str(cfg.get('hotmail007_key') or "").strip().strip('"').strip("'")
        mail_type = str(cfg.get('hotmail007_mail_type', 'hotmail')).strip() or 'hotmail'
        product_id = cfg.get('hotmail007_product_id')
        mailbox_class = lambda api_key: Hotmail007Provider(api_key, mail_type=mail_type, product_id=product_id)
    elif service == 'z':
        key = cfg.get('zeusx_key')
        mailbox_class = ZeusXProvider
    elif service == 'a':
        key = cfg.get('afham_mail_api9_key', '')
        mailbox_class = AfhamMailProvider
    elif service == 'd':
        key = cfg.get('duckmail_key', '')
        mailbox_class = DuckMailProvider
    elif service == 'r':
        key = cfg.get('crowmail_key', '')
        mailbox_class = CrowMailProvider
    else:
        key = cfg.get('cybertemp_key')
        mailbox_class = MailboxClient

    if not key and service not in ('d',):
        log_message("WARNING", f"no api key found for service '{service.upper()}'. please check config.yaml")

    clear_screen()
    print(render_activity_header())
    ext_path = await setup_leninja(log_message)
    _fp_count = len(_load_fp_lines())
    if _fp_count > 0:
        log_message("INFO", f"{_fp_count} fingerprint(s) loaded from input/fp.txt")
    else:
        log_message("INFO", "no fingerprints loaded (input/fp.txt empty) - running without fingerprints")

    
    if len(sys.argv) > 1:
        try:
            target = int(sys.argv[1])
        except:
            target = 1
    else:
        try:
            target = int(prompt_user("How many accounts to gen 0 = ∞: "))
        except:
            target = 1

    custom_display_name = None
    done = 0
    start = time.time()
    success = 0
    locked = 0
    
    try:
        while True:
            if target != 0 and done >= target: break
            done += 1
            log_message("INFO", f"creating acc # {done}")
            
            try:
                _fp_dict, _fp_raw = peek_next_fingerprint()
                engine = AccountCreator(key, mailbox_class, extension_path=ext_path, proxy=get_random_proxy(proxies), custom_display_name=custom_display_name, fingerprint=_fp_dict)
                resp = await engine.run()

                # Consume fingerprint after every use (one-time use)
                if _fp_raw:
                    consume_fingerprint_line(_fp_raw)

                if resp and len(resp) == 2:
                    token, took = resp
                    if token == "LOCKED":
                        locked += 1
                    elif token:
                        log_message("SUCCESS", "valid")
                        success += 1
                    else:
                        log_message("ERROR", f"failed #{done}")
                else:
                    log_message("ERROR", f"failed #{done}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_message("ERROR", f"error: {e}")
                continue
                
            if target == 1: break
            elif target != 0 and done >= target: break
            else:
                if use_vpn:
                    rotated = await rotate_mullvad_ip()
                    if not rotated:
                        log_message("ERROR", "vpn rotation failed; stopping")
                        break
                else:
                    await animated_cooldown(vpn_delay)
                
    except KeyboardInterrupt:
        log_message("SUCCESS", "exiting...")
    finally:
        await shutdown_engine()
        
    elapsed = time.time() - start
    log_message("INFO", f"results: {success} valid, {locked} locked, {done} attempted in ({elapsed:.1f}s)", summary=(success, locked, done, elapsed))
    prompt_user("press enter to exit")

if __name__ == '__main__':
    def silent_error(loop, context):
        message = context.get("message", "async error")
        exception = context.get("exception")
        detail = f"{message}: {exception}" if exception else message
        log_message("ERROR", detail)

    try:
        configure_stdio()
        if not install_requirements():
            log_message("ERROR", "required packages are missing; install them from requirements.txt")
            prompt_user("press enter to exit")
            sys.exit(1)
        refresh_optional_imports()
        if missing_required_modules():
            log_message("ERROR", f"missing packages: {', '.join(missing_required_modules())}")
            prompt_user("press enter to exit")
            sys.exit(1)
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(silent_error)

        try:
            loop.run_until_complete(main())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            loop.close()
    except Exception as e:
        try:
            with open("crash.log", "w", encoding="utf-8") as f:
                f.write(f"CRASH: {str(e)}\n\n")
                f.write(traceback.format_exc())
        except OSError as write_error:
            log_message("ERROR", f"failed to write crash.log: {write_error}")
        print(f"CRASH: {str(e)}")
        prompt_user("press enter to exit")
    finally:
        cleanup_resources()
