import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]

CODE = f"""
import sys
sys.path.insert(0, r"{REPO}")
from app import config
config.validate_security_config()
"""


def _run(extra_env: dict):
    env = dict(os.environ)
    env.update({"JWT_SECRET_KEY": "", "API_TOKEN": "", "SAI_ALLOW_DEV_MODE": ""})
    env.update(extra_env)
    return subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True,
                          cwd=str(REPO), timeout=60, env=env)


def test_boot_fails_without_auth():
    """Secure by default: tanpa JWT_SECRET_KEY server menolak jalan."""
    r = _run({})
    assert r.returncode != 0
    assert "JWT_SECRET_KEY" in (r.stderr + r.stdout)


def test_boot_allows_dev_mode_only_when_explicit():
    r = _run({"SAI_ALLOW_DEV_MODE": "1"})
    assert r.returncode == 0


def test_short_jwt_secret_rejected():
    r = _run({"JWT_SECRET_KEY": "pendek"})
    assert r.returncode != 0
