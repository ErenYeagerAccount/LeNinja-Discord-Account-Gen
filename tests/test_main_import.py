import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_import_does_not_prompt_for_setup():
    env = os.environ.copy()
    env["LENINJA_SKIP_SETUP"] = "1"
    code = '''
import builtins
import sys
import types

sys.modules["truedriver"] = types.ModuleType("truedriver")

orig_input = builtins.input

def boom(*args, **kwargs):
    raise AssertionError("input should not be called during import")

builtins.input = boom

import main
print("OK")
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK" in proc.stdout


def test_hotmail007_uses_named_mail_type():
    env = os.environ.copy()
    env["LENINJA_SKIP_SETUP"] = "1"
    code = '''
import sys
import types

sys.modules["truedriver"] = types.ModuleType("truedriver")

import main

assert main.Hotmail007Provider("key", mail_type="8").mail_type == "hotmail"
assert main.Hotmail007Provider("key", mail_type="hotmail").mail_type == "hotmail"
print("OK")
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK" in proc.stdout


def test_hotmail007_accepts_three_field_mailbox_response():
    env = os.environ.copy()
    env["LENINJA_SKIP_SETUP"] = "1"
    code = '''
import asyncio
import sys
import types

sys.modules["truedriver"] = types.ModuleType("truedriver")

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
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK" in proc.stdout
