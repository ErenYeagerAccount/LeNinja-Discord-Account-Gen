import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
STUBS = '''
import sys
import types

sys.modules.setdefault("truedriver", types.ModuleType("truedriver"))
if "httpx" not in sys.modules:
    httpx_mod = types.ModuleType("httpx")
    class RequestError(Exception):
        pass
    httpx_mod.RequestError = RequestError
    httpx_mod.AsyncClient = object
    httpx_mod.Client = object
    sys.modules["httpx"] = httpx_mod
'''


def _run_main_snippet(code):
    env = os.environ.copy()
    env["LENINJA_SKIP_SETUP"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", STUBS + "\n" + code],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK" in proc.stdout


def test_import_does_not_prompt_for_setup():
    _run_main_snippet('''
import builtins

def boom(*args, **kwargs):
    raise AssertionError("input should not be called during import")

builtins.input = boom
import main
print("OK")
''')


def test_hotmail007_uses_named_mail_type():
    _run_main_snippet('''
import main
assert main.Hotmail007Provider("key", mail_type="8").product_id == 8
assert main.Hotmail007Provider("key", mail_type="hotmail").mail_type == "hotmail"
print("OK")
''')


def test_hotmail007_accepts_three_field_mailbox_response():
    _run_main_snippet('''
import asyncio
import main

class Response:
    status_code = 200
    def json(self):
        return {"success": True, "data": ["mail@example.com:password"]}

class Client:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return None
    async def get(self, *args, **kwargs):
        return Response()

main.httpx.AsyncClient = Client

async def run():
    provider = main.Hotmail007Provider("key")
    assert await provider.create_inbox() == "mail@example.com"
    assert provider.refresh_token is None
    assert provider.uuid is None

asyncio.run(run())
print("OK")
''')


def test_hotmail007_accepts_four_field_credentials_and_reads_provider_inbox():
    _run_main_snippet('''
import asyncio
import main

line = "mail@example.com:password:refresh-token:9e5f94bc-e8a4-4e73-b8be-63364c29d753"
verify = "https://discord.com/verify?token=" + ("a" * 40)

class Response:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload

class Client:
    calls = []
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return None
    async def get(self, url, params=None, **kwargs):
        Client.calls.append((url, params or {}))
        if "stock" in url:
            return Response({"success": True, "code": 0, "data": [
                {"productId": "5", "mailType": "hotmail-trusted", "name": "Hotmail Trusted", "stock": 3},
            ]})
        if "getMail" in url or "open/buy" in url:
            return Response({"success": True, "code": 0, "data": [line]})
        if "mail/latest" in url or "getFirstMail" in url:
            assert params["account"] == line
            assert params["folder"] in ("inbox", "junkemail")
            return Response({
                "success": True,
                "code": 0,
                "data": {"from": "noreply@discord.com", "subject": "Verify", "html": f"<a href='{verify}'>x</a>", "text": ""},
            })
        raise AssertionError(url)

main.httpx.AsyncClient = Client

async def run():
    provider = main.Hotmail007Provider("key", mail_type="hotmail Trusted")
    assert provider.mail_type == "hotmail Trusted"
    assert await provider.create_inbox() == "mail@example.com"
    assert provider.refresh_token == "refresh-token"
    assert provider.uuid == "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
    assert await provider.get_verification_url() == verify
    assert any("open/mail/latest" in url for url, _ in Client.calls)

asyncio.run(run())
print("OK")
''')


def test_zeusx_rejects_invalid_payload_and_parses_records():
    _run_main_snippet('''
import asyncio
import main

class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload

class Client:
    payload = {"success": False, "message": "no stock"}
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return None
    async def get(self, *args, **kwargs):
        return Response(200, Client.payload)

main.httpx.AsyncClient = Client

async def run():
    provider = main.ZeusXProvider("key")
    assert await provider.create_inbox() is None
    Client.payload = {"data": [{"email": "zeus@example.com", "password": "secret"}]}
    assert await provider.create_inbox() == "zeus@example.com"
    assert provider.password == "secret"

asyncio.run(run())
print("OK")
''')


def test_duckmail_requires_token_and_uses_worker_thread():
    _run_main_snippet('''
import asyncio
import threading
import types
import main

class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload

calls = []
main_thread = threading.get_ident()

def fake_get(url, **kwargs):
    calls.append(("get", url, threading.get_ident() != main_thread))
    return Response(200, {"hydra:member": [{"domain": "duckmail.sbs", "isVerified": True}]})

def fake_post(url, **kwargs):
    calls.append(("post", url, threading.get_ident() != main_thread))
    if url.endswith("/accounts"):
        return Response(201, {"id": "acct"})
    return Response(200, {"token": None})

main.requests = types.SimpleNamespace(get=fake_get, post=fake_post)

async def run():
    provider = main.DuckMailProvider("key")
    assert await provider.create_inbox() is None
    assert any(item[0] == "post" and item[2] for item in calls)

asyncio.run(run())
print("OK")
''')


def test_save_data_reports_write_errors():
    _run_main_snippet('''
import builtins
import main

creator = main.AccountCreator.__new__(main.AccountCreator)
creator.email = "user@example.com"
creator.password = "secret"
original_open = builtins.open

def fake_open(path, *args, **kwargs):
    if str(path).endswith("tokens.txt") or str(path).endswith("accounts.txt"):
        raise OSError("disk full")
    return original_open(path, *args, **kwargs)

builtins.open = fake_open
try:
    try:
        creator.save_data("token-value")
        ok = False
    except OSError:
        ok = True
finally:
    builtins.open = original_open
assert ok
print("OK")
''')


def test_vpn_failure_stops_startup():
    _run_main_snippet('''
import asyncio
import main

async def fail_connect():
    return False

main.mullvad_ensure_connected = fail_connect

async def run():
    assert await main.require_vpn_connection() is False

asyncio.run(run())
print("OK")
''')


def test_fingerprint_line_is_consumed():
    _run_main_snippet('''
from pathlib import Path
import main

fp = Path(main.get_path("input")) / "fp-test.txt"
fp.write_text("one\\ntwo\\n", encoding="utf-8")
main.FP_FILE = fp
assert main.consume_fingerprint_line("one") is True
assert fp.read_text(encoding="utf-8") == "two\\n"
fp.unlink()
print("OK")
''')


def test_browser_uses_explicit_config_path():
    _run_main_snippet('''
from pathlib import Path
import main

fake = Path(main.get_path("input")) / "fake-vivaldi.exe"
fake.write_text("stub", encoding="utf-8")
main.configure_browser({"browser": "vivaldi", "browser_path": str(fake)})
path, name = main.find_browser_path()
assert path == str(fake)
assert name
fake.unlink()
print("OK")
''')


def test_setup_files_is_defined():
    _run_main_snippet('''
import main
assert callable(main.setup_files)
print("OK")
''')


def test_config_accepts_double_quoted_windows_path():
    _run_main_snippet('''
from pathlib import Path
import main

path = Path(main.get_path("config")) / "windows-path.yaml"
path.write_text('browser: vivaldi\\nbrowser_path: "C:\\\\Users\\\\TUSHAR\\\\Desktop\\\\vivaldi.exe"\\nvpn: false\\n', encoding="utf-8")
cfg = main.load_yaml_config(path)
assert cfg["browser"] == "vivaldi"
assert "Users" in cfg["browser_path"]
assert cfg["browser_path"].endswith("vivaldi.exe")
path.unlink()
print("OK")
''')
