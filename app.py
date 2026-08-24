#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FireXDecoder - Hosting Panel
Professional, production-ready deployment script.
All messages and comments are in English.
"""

import os
import re
import json
import time
import shutil
import zipfile
import hashlib
import random
import subprocess
import threading
import py_compile
import io
import logging
import sys
from datetime import datetime
from collections import defaultdict, deque

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash

# ===========================================================================
# Configuration
# ===========================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ADMIN_PASS = os.environ.get("ADMIN_PASS", "854191")
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
PORT = int(os.environ.get("PORT", 3522))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# FIX: Use a writable/executable location for virtual environments
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
VENV_FOLDER = os.environ.get(
    "VENV_BASE",
    os.path.join(os.path.expanduser("~"), ".cache", "firexdecoder_venvs")
)
LOG_FOLDER = os.path.join(BASE_DIR, "logs")
DB_FILE = os.path.join(BASE_DIR, "database.json")

DEFAULT_CONFIG = {
    "max_concurrent_per_user": 3,
    "max_concurrent_vip": 10,
    "max_concurrent_global": 25,
    "sleep_after_hours": 4,
    "auto_wake_after_minutes": 10,
    "request_baseline_per_min": 30
}

ADMIN_INTERNAL_ID = "__admin__"
ENTRY_FILES_PY = ["main.py", "bot.py", "app.py", "run.py", "start.py"]
ENTRY_FILES_JS = ["index.js", "server.js", "bot.js", "app.js", "main.js"]

DEVICE_POOL = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15", "platform": "Mac"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "platform": "Mac"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1", "platform": "iOS"},
    {"ua": "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1", "platform": "iOS"},
    {"ua": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36", "platform": "Android"},
    {"ua": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36", "platform": "Android"},
    {"ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36", "platform": "Android"},
    {"ua": "Mozilla/5.0 (Linux; Android 12; CPH2449) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36", "platform": "Android"},
    {"ua": "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B Build/UP1A.231005.007)", "platform": "Android-App"},
    {"ua": "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 7 Build/TQ3A.230901.001)", "platform": "Android-App"},
    {"ua": "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "platform": "Linux"},
    {"ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0", "platform": "Linux"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0", "platform": "Windows"},
    {"ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "platform": "iOS"},
    {"ua": "Mozilla/5.0 (Linux; Android 11; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36", "platform": "Android"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0", "platform": "Mac"},
    {"ua": "Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36", "platform": "Android"},
]

# ===========================================================================
# Logging
# ===========================================================================
logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("FireXDecoder")

# ===========================================================================
# Flask app
# ===========================================================================
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VENV_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# ===========================================================================
# Database
# ===========================================================================
DB_LOCK = threading.Lock()

def default_db():
    return {
        "users": {},
        "admin_device_tokens": {},
        "start_times": {},
        "app_settings": {},
        "public_tokens": {},
        "config": DEFAULT_CONFIG.copy()
    }

def load_db():
    with DB_LOCK:
        if not os.path.exists(DB_FILE):
            data = default_db()
            _write_db(data)
            return data
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = default_db()
            _write_db(data)
            return data

        defaults = default_db()
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
        for key, val in defaults["config"].items():
            if key not in data.get("config", {}):
                data["config"][key] = val

        for uname, val in list(data.get("users", {}).items()):
            if not isinstance(val, dict):
                pw = val
                if not (pw.startswith("pbkdf2:") or pw.startswith("scrypt:")):
                    pw = generate_password_hash(pw)
                data["users"][uname] = {"pw_hash": pw, "vip": False, "created": int(time.time()*1000)}
        return data

def _write_db(data):
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DB_FILE)

def save_db(data):
    with DB_LOCK:
        _write_db(data)

def get_config(db, key):
    return db.get("config", {}).get(key, DEFAULT_CONFIG.get(key))

def get_user_concurrency_limit(db, email):
    user = db.get("users", {}).get(email, {})
    if user.get("vip"):
        return get_config(db, "max_concurrent_vip")
    return get_config(db, "max_concurrent_per_user")

# ===========================================================================
# Security
# ===========================================================================
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9_.+\-]+@[A-Za-z0-9\-]+\.[A-Za-z0-9\-.]+$")

def is_safe_component(name):
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name and SAFE_NAME_RE.match(name)

def safe_join(base, *parts):
    base = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base, *parts))
    if not (target == base or target.startswith(base + os.sep)):
        raise ValueError("Path traversal detected")
    return target

def is_valid_email(email):
    return bool(email) and len(email) <= 120 and EMAIL_RE.match(email)

def user_folder_id(email):
    return hashlib.sha256(email.lower().encode()).hexdigest()[:24]

def generate_secret_token(nbytes=24):
    return os.urandom(nbytes).hex()

login_attempts = defaultdict(lambda: {"count": 0, "locked_until": 0})

def is_locked_out(username):
    return time.time() < login_attempts[username]["locked_until"]

def register_failed_login(username):
    rec = login_attempts[username]
    rec["count"] += 1
    if rec["count"] >= 5:
        rec["locked_until"] = time.time() + 60
        rec["count"] = 0

def reset_login_attempts(username):
    login_attempts[username] = {"count": 0, "locked_until": 0}

# ===========================================================================
# Process tracking
# ===========================================================================
processes = {}
proc_meta = {}
STATE_LOCK = threading.Lock()

# ===========================================================================
# Activity tracker
# ===========================================================================
class ActivityTracker:
    def __init__(self):
        self.windows = defaultdict(lambda: deque())
        self.crash_log = defaultdict(lambda: deque())
        self.paused_until = {}
        self.lock = threading.Lock()

    def ping(self, key):
        now = time.time()
        with self.lock:
            dq = self.windows[key]
            dq.append(now)
            cutoff = now - 60
            while dq and dq[0] < cutoff:
                dq.popleft()

    def current_rate(self, key):
        with self.lock:
            return len(self.windows[key])

    def suggested_delay(self, key, baseline_per_min=30):
        rate = self.current_rate(key)
        base_delay = random.uniform(0.4, 1.8)
        if baseline_per_min and rate > baseline_per_min * 3:
            return base_delay + random.uniform(1.5, 4.0)
        return base_delay

    def is_paused(self, key):
        return time.time() < self.paused_until.get(key, 0)

    def register_crash(self, key, cooldown_seconds=300):
        now = time.time()
        with self.lock:
            dq = self.crash_log[key]
            dq.append(now)
            cutoff = now - 600
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= 4:
                self.paused_until[key] = now + cooldown_seconds
                return True
        return False

    def clear_pause(self, key):
        self.paused_until.pop(key, None)
        self.crash_log[key].clear()

activity = ActivityTracker()

# ===========================================================================
# App settings
# ===========================================================================
def app_settings_key(user, name):
    return f"{user}_{name}"

def get_app_settings(db, user, name):
    key = app_settings_key(user, name)
    settings = db.setdefault("app_settings", {}).setdefault(key, {})
    settings.setdefault("auto_on", False)
    settings.setdefault("auto_restart", False)
    settings.setdefault("sleep_until", 0)
    settings.setdefault("offline_at", 0)
    settings.setdefault("device_ua", None)
    settings.setdefault("device_platform", None)
    settings.setdefault("manual_stop", False)
    settings.setdefault("unlimited", False)
    settings.setdefault("public_token", None)
    return settings

def ensure_public_token(db, user, name):
    settings = get_app_settings(db, user, name)
    if not settings.get("public_token"):
        token = generate_secret_token()
        settings["public_token"] = token
        db.setdefault("public_tokens", {})[token] = app_settings_key(user, name)
        save_db(db)
    return settings["public_token"]

def revoke_public_token(db, user, name):
    settings = get_app_settings(db, user, name)
    old = settings.get("public_token")
    if old:
        db.get("public_tokens", {}).pop(old, None)
    settings["public_token"] = None
    save_db(db)

def app_dirs(user, name):
    app_dir = safe_join(UPLOAD_FOLDER, user, name)
    extract_dir = os.path.join(app_dir, "extracted")
    log_path = os.path.join(app_dir, "logs.txt")
    return app_dir, extract_dir, log_path

def append_log(log_path, text):
    try:
        with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
            f.write(text + "\n")
    except Exception:
        pass

def trim_log_if_needed(log_path, max_bytes=500_000):
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > max_bytes:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(-max_bytes//2, os.SEEK_END)
                tail = f.read()
            with open(log_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write("...[log truncated]...\n" + tail)
    except Exception:
        pass

# ===========================================================================
# Device fingerprint
# ===========================================================================
def assign_device(seed_key):
    rnd = random.Random(seed_key)
    return rnd.choice(DEVICE_POOL)

def device_env_vars(device):
    return {
        "BOT_USER_AGENT": device["ua"],
        "BOT_DEVICE_PLATFORM": device["platform"],
    }

# ===========================================================================
# Validation
# ===========================================================================
def validate_python_file(path):
    try:
        py_compile.compile(path, doraise=True)
        return {"ok": True}
    except py_compile.PyCompileError as e:
        msg = str(e.exc_value) if hasattr(e, "exc_value") else str(e)
        line = None
        m = re.search(r"line (\d+)", msg)
        if m:
            line = int(m.group(1))
        return {"ok": False, "line": line, "error": msg.strip()}
    except SyntaxError as e:
        return {"ok": False, "line": e.lineno, "error": str(e.msg)}
    except Exception as e:
        return {"ok": False, "line": None, "error": str(e)}

def validate_js_file(path):
    node_bin = shutil.which("node")
    if not node_bin:
        return {"ok": True, "skipped": True, "note": "Node not available for validation"}
    try:
        result = subprocess.run([node_bin, "--check", path], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return {"ok": True}
        err = result.stderr.strip()
        line = None
        first_line = err.splitlines()[0] if err else ""
        m = re.search(re.escape(path) + r":(\d+)", first_line)
        if m:
            line = int(m.group(1))
        return {"ok": False, "line": line, "error": err}
    except Exception as e:
        return {"ok": False, "line": None, "error": str(e)}

def find_entry_file(extract_dir):
    for f in ENTRY_FILES_PY:
        if os.path.exists(os.path.join(extract_dir, f)):
            return f, "python"
    for f in ENTRY_FILES_JS:
        if os.path.exists(os.path.join(extract_dir, f)):
            return f, "node"
    return None, None

def validate_project(extract_dir):
    entry, kind = find_entry_file(extract_dir)
    if not entry:
        return {
            "ok": False,
            "error": f"No entry file found. Must be one of: {', '.join(ENTRY_FILES_PY + ENTRY_FILES_JS)}"
        }

    problems = []
    for root, dirs, files in os.walk(extract_dir):
        dirs[:] = [d for d in dirs if d not in ("venv", "node_modules", "__pycache__", ".git")]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, extract_dir)
            if fname.endswith(".py"):
                res = validate_python_file(fpath)
                if not res["ok"]:
                    problems.append({"file": rel, "line": res.get("line"), "error": res.get("error")})
            elif fname.endswith(".js") and kind == "node":
                res = validate_js_file(fpath)
                if not res.get("ok") and not res.get("skipped"):
                    problems.append({"file": rel, "line": res.get("line"), "error": res.get("error")})

    req_path = os.path.join(extract_dir, "requirements.txt")
    if os.path.exists(req_path):
        try:
            with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if not re.match(r"^[A-Za-z0-9_\-\.\[\]]+([=<>!~]=?[A-Za-z0-9_\-\.\*]+)?$", line):
                        problems.append({"file": "requirements.txt", "line": i, "error": f"Suspicious line: {line}"})
        except Exception as e:
            problems.append({"file": "requirements.txt", "line": None, "error": str(e)})

    if problems:
        return {"ok": False, "entry": entry, "kind": kind, "problems": problems}
    return {"ok": True, "entry": entry, "kind": kind}

# ===========================================================================
# Smart dependency installation
# ===========================================================================
def venv_path_for(user, app_name):
    return safe_join(VENV_FOLDER, f"{user}__{app_name}")

def file_hash(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def get_installed_packages(python_bin):
    try:
        result = subprocess.run(
            [python_bin, "-m", "pip", "list", "--format=freeze"],
            capture_output=True, text=True, timeout=30
        )
        installed = {}
        for line in result.stdout.splitlines():
            if "==" in line:
                name, ver = line.split("==", 1)
                installed[name.lower()] = ver
        return installed
    except Exception:
        return {}

def parse_requirements(req_path):
    reqs = []
    with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                reqs.append(line)
    return reqs

def ensure_venv(venv_dir):
    python_bin = os.path.join(venv_dir, "bin", "python")
    if os.path.exists(python_bin):
        return python_bin

    # FIX: Better error handling and fallback
    try:
        subprocess.run(
            ["python3", "-m", "venv", venv_dir],
            check=True, timeout=120, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        if shutil.which("virtualenv"):
            try:
                subprocess.run(
                    ["virtualenv", venv_dir],
                    check=True, timeout=120, capture_output=True
                )
            except Exception:
                raise RuntimeError(
                    f"Failed to create virtualenv at {venv_dir}. "
                    "Ensure the directory is writable and executable, "
                    "or set VENV_BASE to a suitable path."
                )
        else:
            raise RuntimeError(
                f"Failed to create virtualenv at {venv_dir}. "
                "Install 'virtualenv' (pip install virtualenv) and try again, "
                "or set VENV_BASE to a writable/executable location."
            )

    if not os.path.exists(python_bin):
        raise RuntimeError(f"Virtualenv creation succeeded but python binary not found at {python_bin}")
    return python_bin

def smart_install_python(extract_dir, venv_dir, log_callback):
    req_path = os.path.join(extract_dir, "requirements.txt")
    state_path = os.path.join(venv_dir, ".install_state.json")

    if not os.path.exists(req_path):
        log_callback("No requirements.txt found; skipping install.")
        return {"ok": True, "skipped": True}

    current_hash = file_hash(req_path)
    prev_state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                prev_state = json.load(f)
        except Exception:
            pass

    if prev_state.get("hash") == current_hash and prev_state.get("last_ok"):
        log_callback("requirements.txt unchanged; install skipped.")
        return {"ok": True, "skipped": True}

    try:
        python_bin = ensure_venv(venv_dir)
    except Exception as e:
        log_callback(f"Virtualenv creation failed: {e}")
        return {"ok": False, "error": str(e)}

    installed = get_installed_packages(python_bin)
    wanted = parse_requirements(req_path)

    to_install = []
    for spec in wanted:
        pkg_name = re.split(r"[=<>!~\[]", spec, 1)[0].strip().lower()
        if "==" in spec:
            _, ver = spec.split("==", 1)
            if installed.get(pkg_name) == ver.strip():
                continue
        else:
            if pkg_name in installed:
                continue
        to_install.append(spec)

    if not to_install:
        log_callback("All packages already installed.")
        with open(state_path, "w") as f:
            json.dump({"hash": current_hash, "last_ok": True}, f)
        return {"ok": True, "skipped": True}

    log_callback(f"Installing/updating {len(to_install)} packages: {', '.join(to_install)}")
    try:
        result = subprocess.run(
            [python_bin, "-m", "pip", "install", "--disable-pip-version-check"] + to_install,
            capture_output=True, text=True, timeout=600
        )
        log_callback(result.stdout[-3000:] + "\n")
        if result.returncode != 0:
            log_callback("PIP install had errors (some packages may have failed):\n" + result.stderr[-2000:])
            with open(state_path, "w") as f:
                json.dump({"hash": current_hash, "last_ok": False}, f)
            return {"ok": False, "partial": True, "error": result.stderr[-500:]}
        with open(state_path, "w") as f:
            json.dump({"hash": current_hash, "last_ok": True}, f)
        log_callback("Dependencies installed successfully.")
        return {"ok": True}
    except subprocess.TimeoutExpired:
        log_callback("Install timed out (>10 min). Continuing anyway.")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        log_callback(f"Install error: {e}")
        return {"ok": False, "error": str(e)}

def smart_install_node(extract_dir, log_callback):
    pkg_path = os.path.join(extract_dir, "package.json")
    if not os.path.exists(pkg_path):
        log_callback("No package.json; skipping npm install.")
        return {"ok": True, "skipped": True}
    npm_bin = shutil.which("npm")
    if not npm_bin:
        log_callback("npm not available; cannot install Node dependencies.")
        return {"ok": False, "error": "npm not found"}

    state_path = os.path.join(extract_dir, ".npm_install_state.json")
    current_hash = file_hash(pkg_path)
    prev_state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                prev_state = json.load(f)
        except Exception:
            pass

    if prev_state.get("hash") == current_hash and prev_state.get("last_ok"):
        log_callback("package.json unchanged; npm install skipped.")
        return {"ok": True, "skipped": True}

    log_callback("Running npm install...")
    try:
        result = subprocess.run(
            [npm_bin, "install", "--no-audit", "--no-fund"],
            cwd=extract_dir, capture_output=True, text=True, timeout=600
        )
        log_callback(result.stdout[-3000:] + "\n")
        ok = result.returncode == 0
        if not ok:
            log_callback("npm install had warnings:\n" + result.stderr[-2000:])
        with open(state_path, "w") as f:
            json.dump({"hash": current_hash, "last_ok": ok}, f)
        return {"ok": ok}
    except subprocess.TimeoutExpired:
        log_callback("npm install timed out.")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        log_callback(f"npm install error: {e}")
        return {"ok": False, "error": str(e)}

# ===========================================================================
# App lifecycle
# ===========================================================================
def count_running_for_user(user):
    return sum(1 for (u, _), p in processes.items() if u == user and p.poll() is None)

def count_running_global():
    return sum(1 for p in processes.values() if p.poll() is None)

def start_app_process(user, name, db):
    app_dir, extract_dir, log_path = app_dirs(user, name)
    key = (user, name)

    with STATE_LOCK:
        if key in processes and processes[key].poll() is None:
            return {"ok": True, "already_running": True}

        if activity.is_paused(f"{user}_{name}"):
            return {"ok": False, "error": "App is in cooldown due to repeated crashes. Please wait."}

        entry, kind = find_entry_file(extract_dir)
        if not entry:
            msg = f"No entry file found. Must be one of: {', '.join(ENTRY_FILES_PY + ENTRY_FILES_JS)}"
            append_log(log_path, f"[{datetime.now()}] START FAILED: {msg}")
            return {"ok": False, "error": msg}

        settings = get_app_settings(db, user, name)

        max_global = get_config(db, "max_concurrent_global")
        if user != ADMIN_INTERNAL_ID:
            max_user = get_user_concurrency_limit(db, user)
            if count_running_for_user(user) >= max_user:
                return {"ok": False, "error": f"User limit of {max_user} concurrent apps reached."}
        if count_running_global() >= max_global:
            return {"ok": False, "error": "Server is at global capacity. Please try later."}

        append_log(log_path, f"\n[{datetime.now()}] ===== Deployment started =====")

        def log_cb(text):
            append_log(log_path, text)

        if kind == "python":
            venv_dir = venv_path_for(user, name)
            install_res = smart_install_python(extract_dir, venv_dir, log_cb)
            try:
                python_bin = ensure_venv(venv_dir)
            except Exception as e:
                append_log(log_path, f"Virtualenv error: {e}")
                return {"ok": False, "error": f"Environment setup failed: {e}"}
            cmd = [python_bin, entry]
        else:
            install_res = smart_install_node(extract_dir, log_cb)
            node_bin = shutil.which("node") or "node"
            cmd = [node_bin, entry]

        seed_key = f"{user}_{name}_{int(time.time())}"
        device = assign_device(seed_key)
        settings["device_ua"] = device["ua"]
        settings["device_platform"] = device["platform"]
        settings["manual_stop"] = False

        env = os.environ.copy()
        env.update(device_env_vars(device))
        env["PYTHONUNBUFFERED"] = "1"

        trim_log_if_needed(log_path)
        log_file = open(log_path, "a", encoding="utf-8", errors="ignore")
        try:
            proc = subprocess.Popen(cmd, cwd=extract_dir, stdout=log_file, stderr=log_file,
                                    text=True, env=env)
        except Exception as e:
            append_log(log_path, f"Process start error: {e}")
            return {"ok": False, "error": str(e)}

        processes[key] = proc
        proc_meta[key] = {"device": device, "started": time.time(),
                          "restarts": proc_meta.get(key, {}).get("restarts", 0)}

        now_ms = int(time.time() * 1000)
        db["start_times"][app_settings_key(user, name)] = now_ms
        settings["offline_at"] = 0
        settings["sleep_until"] = 0
        save_db(db)

        append_log(log_path, f"[{datetime.now()}] Started with entry={entry}, device={device['platform']}")
        return {"ok": True, "install": install_res, "device": device["platform"]}

def stop_app_process(user, name, db, manual=True):
    key = (user, name)
    with STATE_LOCK:
        p = processes.get(key)
        if p and p.poll() is None:
            try:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
            except Exception:
                pass
        processes.pop(key, None)

        settings = get_app_settings(db, user, name)
        settings["manual_stop"] = manual
        tkey = app_settings_key(user, name)
        db["start_times"].pop(tkey, None)
        save_db(db)

# ===========================================================================
# Scheduler
# ===========================================================================
def scheduler_loop():
    while True:
        try:
            db = load_db()
            sleep_hours = get_config(db, "sleep_after_hours")
            wake_minutes = get_config(db, "auto_wake_after_minutes")
            now = time.time()
            changed = False

            for tkey, started_ms in list(db.get("start_times", {}).items()):
                if "_" not in tkey:
                    continue
                user, name = tkey.split("_", 1)
                key = (user, name)
                settings = get_app_settings(db, user, name)
                started_s = started_ms / 1000.0

                p = processes.get(key)
                is_running = bool(p and p.poll() is None)

                if is_running and not settings.get("unlimited") and (now - started_s) >= sleep_hours * 3600:
                    _, _, log_path = app_dirs(user, name)
                    append_log(log_path, f"[{datetime.now()}] Auto-sleep: {sleep_hours}h reached, stopping.")
                    stop_app_process(user, name, db, manual=False)
                    settings = get_app_settings(db, user, name)
                    settings["offline_at"] = now
                    changed = True

                if p and not is_running and key in processes:
                    tracker_key = f"{user}_{name}"
                    tripped = activity.register_crash(tracker_key)
                    processes.pop(key, None)
                    db["start_times"].pop(tkey, None)
                    settings["offline_at"] = now
                    changed = True
                    _, _, log_path = app_dirs(user, name)
                    if tripped:
                        append_log(log_path, f"[{datetime.now()}] Repeated crashes detected; cooling down for 5 minutes.")
                    elif settings.get("auto_restart") and not settings.get("manual_stop"):
                        append_log(log_path, f"[{datetime.now()}] Crash detected; auto-restart enabled, restarting.")
                        start_app_process(user, name, db)

                if not is_running and settings.get("offline_at") and settings.get("auto_on") and not settings.get("manual_stop"):
                    if (now - settings["offline_at"]) >= wake_minutes * 60 and not activity.is_paused(f"{user}_{name}"):
                        _, _, log_path = app_dirs(user, name)
                        append_log(log_path, f"[{datetime.now()}] Auto-on: {wake_minutes} min cooldown elapsed, restarting.")
                        start_app_process(user, name, db)
                        changed = True

            if changed:
                save_db(db)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(30)

def resume_apps_after_restart():
    db = load_db()
    changed = False
    for tkey in list(db.get("start_times", {}).keys()):
        if "_" not in tkey:
            continue
        user, name = tkey.split("_", 1)
        key = (user, name)
        if key not in processes or processes[key].poll() is not None:
            db["start_times"].pop(tkey, None)
            settings = get_app_settings(db, user, name)
            settings["offline_at"] = time.time()
            changed = True
    if changed:
        save_db(db)

_scheduler_started = False

def ensure_scheduler():
    global _scheduler_started
    if not _scheduler_started:
        _scheduler_started = True
        resume_apps_after_restart()
        t = threading.Thread(target=scheduler_loop, daemon=True)
        t.start()

# ===========================================================================
# Embedded HTML templates (all in English)
# ===========================================================================
LOGIN_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login | FireXDecoder</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg: #030508; --primary: #00ffff; --sec: #7000ff; --glass: rgba(255, 255, 255, 0.03); }
        body { background: var(--bg); color: white; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { position: relative; z-index: 10; background: var(--glass); padding: 40px 30px; border-radius: 25px; width: 340px; max-width: 90vw; text-align: center; border: 1px solid rgba(0, 255, 255, 0.15); backdrop-filter: blur(20px); box-shadow: 0 25px 45px rgba(0,0,0,0.5); }
        .lock-container { width: 80px; height: 80px; background: rgba(0, 255, 255, 0.1); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; border: 2px solid var(--primary); }
        .lock-icon { font-size: 35px; color: var(--primary); }
        h2 { font-size: 20px; margin-bottom: 10px; letter-spacing: 3px; text-transform: uppercase; background: linear-gradient(to right, #fff, var(--primary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .sub { font-size: 11px; opacity: 0.6; margin-bottom: 15px; }
        .err { background: rgba(255,60,60,0.15); border: 1px solid #ff4757; color: #ff9a9a; padding: 10px; border-radius: 10px; font-size: 13px; margin-bottom: 10px; }
        input, select { width: 100%; padding: 14px; margin: 8px 0; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.05); color: #fff; outline: none; font-size: 14px; box-sizing: border-box; }
        button { width: 100%; padding: 15px; border-radius: 12px; border: none; background: linear-gradient(45deg, var(--sec), var(--primary)); color: #fff; font-weight: bold; font-size: 15px; cursor: pointer; margin-top: 10px; text-transform: uppercase; letter-spacing: 2px; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="lock-container"><i class="fa-solid fa-user-shield lock-icon"></i></div>
        <h2>FireXDecoder</h2>
        <div class="sub">Login with email (new accounts are created automatically)</div>
        {% if error %}<div class="err">{{ error }}</div>{% endif %}
        <form method="post" action="/login">
            <input type="email" name="email" placeholder="Email address" required maxlength="120">
            <input type="password" name="password" placeholder="Password" required maxlength="100" minlength="4">
            <button type="submit">Login / Register</button>
        </form>
    </div>
</body>
</html>'''

ADMIN_LOGIN_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin | FireXDecoder</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg: #030508; --primary: #00ffff; --sec: #7000ff; --glass: rgba(255, 255, 255, 0.03); }
        body { background: var(--bg); color: white; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: var(--glass); padding: 40px 30px; border-radius: 25px; width: 320px; max-width: 90vw; text-align: center; border: 1px solid rgba(255,0,100,0.2); backdrop-filter: blur(20px); }
        .lock-container { width: 80px; height: 80px; background: rgba(255,0,100,0.1); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; border: 2px solid #ff0064; }
        .lock-icon { font-size: 35px; color: #ff0064; }
        h2 { font-size: 18px; letter-spacing: 3px; text-transform: uppercase; color: #fff; }
        .err { background: rgba(255,60,60,0.15); border: 1px solid #ff4757; color: #ff9a9a; padding: 10px; border-radius: 10px; font-size: 13px; margin-bottom: 10px; }
        input { width: 100%; padding: 14px; margin: 8px 0; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.05); color: #fff; outline: none; font-size: 14px; box-sizing: border-box; text-align: center; letter-spacing: 4px; }
        button { width: 100%; padding: 15px; border-radius: 12px; border: none; background: linear-gradient(45deg, #ff0064, #ff7a00); color: #fff; font-weight: bold; font-size: 15px; cursor: pointer; margin-top: 10px; text-transform: uppercase; letter-spacing: 2px; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="lock-container"><i class="fa-solid fa-shield-halved lock-icon"></i></div>
        <h2>Root Access</h2>
        {% if error %}<div class="err">{{ error }}</div>{% endif %}
        <form method="post" action="/admin">
            <input type="password" name="password" placeholder="••••••" required maxlength="50" autofocus>
            <button type="submit">Unlock</button>
        </form>
    </div>
</body>
</html>'''

ADMIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Root | FireXDecoder</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <style>
        :root { --bg: #030508; --card: rgba(22, 27, 34, 0.85); --accent: #00ffff; --text: #e6edf3; --glass: rgba(255, 255, 255, 0.05); }
        * { box-sizing: border-box; }
        body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding: 15px; min-height: 100vh; padding-bottom: 60px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 12px; background: var(--glass); border-radius: 15px; border: 1px solid rgba(0, 255, 255, 0.2); }
        .header h2 { font-size: 18px; color: var(--accent); margin: 0; }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 20px; }
        .stat-card { background: var(--card); padding: 12px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.05); text-align: center; }
        .stat-card p { font-size: 11px; margin: 4px 0; opacity: 0.7; }
        .stat-card div.val { font-size: 17px; font-weight: bold; color: var(--accent); }
        .card { background: var(--card); padding: 15px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.08); margin-bottom: 18px; }
        h3 { margin-top: 0; font-size: 15px; color: var(--accent); display: flex; align-items: center; gap: 8px; }
        .input-group { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
        input, select { width: 100%; padding: 10px; border-radius: 10px; border: 1px solid #333; background: rgba(0,0,0,0.3); color: white; outline: none; font-size: 13px; box-sizing: border-box; }
        .btn { padding: 10px; border-radius: 10px; border: none; font-weight: bold; cursor: pointer; text-align: center; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; }
        .btn-primary { background: linear-gradient(45deg, #00ffff, #7000ff); color: #000; }
        .btn-logout { background: #ff4757; color: white; padding: 8px 14px; }
        .btn-danger { background: #ff4757; color: white; }
        .btn-gold { background: linear-gradient(45deg, #ffd700, #ff9500); color: #000; }
        .btn-small { padding: 6px 10px; font-size: 11px; }
        .user-item, .proxy-item { background: rgba(255,255,255,0.03); border-radius: 12px; padding: 12px; margin-bottom: 8px; border: 1px solid rgba(255,255,255,0.05); }
        .row { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
        .username { font-weight: bold; color: var(--accent); font-size: 13px; word-break: break-all; }
        .tag { padding: 3px 8px; border-radius: 6px; font-size: 10px; border: 1px solid; }
        .tag-green { color: #2ecc71; border-color: #2ecc71; background: rgba(46,204,113,0.1); }
        .tag-red { color: #ff4757; border-color: #ff4757; background: rgba(255,71,87,0.1); }
        .tag-gold { color: #ffd700; border-color: #ffd700; background: rgba(255,215,0,0.1); }
        .action-row { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
        .toggle-switch { position: relative; width: 44px; height: 24px; flex-shrink: 0; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; inset: 0; background: #444; border-radius: 24px; transition: .3s; }
        .slider:before { content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .3s; }
        input:checked + .slider { background: #ffd700; }
        input:checked + .slider:before { transform: translateX(20px); }
        .small-text { font-size: 11px; opacity: 0.6; }
        .upload-mini { border: 2px dashed rgba(0,255,255,0.3); border-radius: 14px; padding: 15px; text-align: center; }
    </style>
</head>
<body>
    <div class="header"><h2><i class="fa-solid fa-shield-halved"></i> FireXDecoder ROOT</h2><a href="/logout" class="btn btn-logout"><i class="fa-solid fa-power-off"></i></a></div>

    <div class="stats-grid">
        <div class="stat-card"><p>Users</p><div class="val">{{ users|length }}</div></div>
        <div class="stat-card"><p>Running Apps</p><div class="val">{{ running_count }}</div></div>
        <div class="stat-card"><p>RAM Used</p><div class="val">{{ ram_percent }}%</div></div>
    </div>

    <div class="card">
        <h3><i class="fa-solid fa-infinity"></i> Admin Unlimited Apps (no 4h sleep)</h3>
        <div class="upload-mini">
            <input type="file" id="adminFileInput" accept=".zip" style="display:none;">
            <button class="btn btn-primary" onclick="document.getElementById('adminFileInput').click()"><i class="fa-solid fa-upload"></i> Upload Admin App</button>
            <div id="adminUploadStatus" class="small-text" style="margin-top:8px;"></div>
        </div>
        {% for a in admin_apps %}
        <div class="user-item" style="margin-top:10px;">
            <div class="row">
                <span><b>{{ a.name }}</b></span>
                {% if a.running %}<span class="tag tag-green">RUNNING</span>{% else %}<span class="tag tag-red">OFFLINE</span>{% endif %}
            </div>
            <div class="small-text">Device: {{ a.device or "—" }} | Unlimited runtime</div>
            <div class="action-row">
                {% if a.running %}
                <a href="/stop/{{ a.name }}" class="btn btn-danger btn-small">Stop</a>
                {% else %}
                <a href="/run/{{ a.name }}" class="btn btn-primary btn-small">Run</a>
                {% endif %}
                <button class="btn btn-primary btn-small" onclick="getAdminPublicLink('{{ a.name }}')"><i class="fa-solid fa-link"></i> Public Link</button>
                <a href="/delete/{{ a.name }}" class="btn btn-danger btn-small">Delete</a>
            </div>
        </div>
        {% endfor %}
        {% if not admin_apps %}<p class="small-text">No admin apps uploaded yet.</p>{% endif %}
    </div>

    <div class="card">
        <h3><i class="fa-solid fa-sliders"></i> Global Limits</h3>
        <form action="/admin/update_config" method="post" class="input-group">
            <label class="small-text">Max apps per normal user (concurrent)</label>
            <input type="number" name="max_concurrent_per_user" value="{{ config.max_concurrent_per_user }}">
            <label class="small-text">Max apps per VIP user (concurrent)</label>
            <input type="number" name="max_concurrent_vip" value="{{ config.max_concurrent_vip }}">
            <label class="small-text">Max apps server-wide (concurrent)</label>
            <input type="number" name="max_concurrent_global" value="{{ config.max_concurrent_global }}">
            <label class="small-text">Auto-sleep after (hours)</label>
            <input type="number" step="0.1" name="sleep_after_hours" value="{{ config.sleep_after_hours }}">
            <label class="small-text">Auto-wake after (minutes)</label>
            <input type="number" name="auto_wake_after_minutes" value="{{ config.auto_wake_after_minutes }}">
            <button type="submit" class="btn btn-primary">Save Config</button>
        </form>
    </div>

    <div class="card">
        <h3><i class="fa-solid fa-user-gear"></i> User Management</h3>
        {% for u in users %}
        <div class="user-item">
            <div class="row">
                <span class="username"><i class="fa-solid fa-circle-user"></i> {{ u.email }}</span>
                <label class="toggle-switch" title="VIP">
                    <input type="checkbox" {% if u.vip %}checked{% endif %} onchange="toggleVip('{{ u.email }}', this)">
                    <span class="slider"></span>
                </label>
            </div>
            {% if u.vip %}<span class="tag tag-gold">VIP</span>{% endif %}
            <div class="action-row">
                <a href="/admin/login_as/{{ u.email }}" class="btn btn-primary btn-small"><i class="fa-solid fa-sign-in"></i> Login as</a>
                <form action="/admin/change_pw" method="post" style="display:flex; gap:5px; flex:1;">
                    <input type="hidden" name="email" value="{{ u.email }}">
                    <input type="text" name="new_pw" placeholder="New password">
                    <button type="submit" class="btn btn-primary btn-small"><i class="fa-solid fa-save"></i></button>
                </form>
            </div>
        </div>
        {% endfor %}
        {% if not users %}<p class="small-text">No users created yet.</p>{% endif %}
    </div>

    <div class="card">
        <h3><i class="fa-solid fa-server"></i> All User Apps</h3>
        {% for a in all_apps %}
        <div class="user-item">
            <div class="row">
                <span style="font-size:12px;"><b>{{ a.user }}</b> / {{ a.name }}</span>
                {% if a.running %}<span class="tag tag-green">RUNNING</span>{% else %}<span class="tag tag-red">OFFLINE</span>{% endif %}
            </div>
            <div class="small-text">Device: {{ a.device or "—" }} | Auto-On: {{ "Yes" if a.auto_on else "No" }} | Auto-Restart: {{ "Yes" if a.auto_restart else "No" }}</div>
        </div>
        {% endfor %}
        {% if not all_apps %}<p class="small-text">No apps uploaded yet.</p>{% endif %}
    </div>

<script>
function toggleVip(email, checkbox) {
    const fd = new FormData();
    fd.append('email', email);
    fetch('/admin/toggle_vip', { method: 'POST', body: fd })
        .then(r => r.json()).then(res => {
            if (!res.ok) { checkbox.checked = !checkbox.checked; }
            else { setTimeout(() => location.reload(), 300); }
        });
}

document.getElementById('adminFileInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;
    const statusDiv = document.getElementById('adminUploadStatus');
    statusDiv.textContent = 'Uploading...';
    const fd = new FormData();
    fd.append('file', file, file.name);
    fetch('/admin/upload_admin_app', { method: 'POST', body: fd })
        .then(r => r.json()).then(res => {
            if (res.ok) { statusDiv.textContent = 'Deployed!'; setTimeout(() => location.reload(), 700); }
            else { statusDiv.textContent = ''; Swal.fire('Error', res.error || 'Upload failed', 'error'); }
        });
});

function getAdminPublicLink(name) {
    fetch('/admin/get_public_link/' + encodeURIComponent(name), { method: 'POST' })
        .then(r => r.json()).then(res => {
            if (res.ok) {
                Swal.fire({
                    title: 'Public Link',
                    html: '<input readonly style="width:100%;padding:8px;" value="' + res.url + '" onclick="this.select()">',
                    confirmButtonText: 'Close'
                });
            } else {
                Swal.fire('Error', res.error || 'Link could not be generated', 'error');
            }
        });
}
</script>
</body>
</html>'''

PUBLIC_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ name or "Not found" }} | FireXDecoder Public</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <style>
        :root { --bg: #030508; --primary: #00ffff; --card: rgba(22,27,34,0.85); --text: #e6edf3; }
        * { box-sizing: border-box; }
        body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding: 15px; }
        .card { background: var(--card); border-radius: 18px; padding: 20px; border: 1px solid rgba(255,255,255,0.08); max-width: 500px; margin: 20px auto; }
        h2 { color: var(--primary); font-size: 18px; margin-top: 0; }
        .status-pill { font-size: 11px; padding: 5px 12px; border-radius: 20px; border: 1px solid; }
        .status-run { color: #2ecc71; border-color: #2ecc71; background: rgba(46,204,113,0.1); }
        .status-off { color: #ff4757; border-color: #ff4757; background: rgba(255,71,87,0.1); }
        .btn { padding: 12px; border-radius: 10px; border: none; font-weight: bold; cursor: pointer; font-size: 14px; width: 100%; margin-top: 10px; color: #fff; }
        .btn-primary { background: linear-gradient(45deg, #00ffff, #7000ff); color: #000; }
        .btn-danger { background: #ff4757; }
        #logBox { background: #000; color: #0f0; font-family: monospace; font-size: 11px; padding: 10px; border-radius: 8px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; margin-top: 15px; }
        .small-text { font-size: 11px; opacity: 0.6; margin-top: 10px; }
    </style>
</head>
<body>
    {% if valid %}
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h2><i class="fa-solid fa-server"></i> {{ name }}</h2>
            <span class="status-pill {% if running %}status-run{% else %}status-off{% endif %}" id="statusPill">{% if running %}RUNNING{% else %}OFFLINE{% endif %}</span>
        </div>
        <p class="small-text">Public control link – view status, start/stop, and logs. File editing requires login.</p>
        <button class="btn btn-primary" id="startBtn" onclick="doAction('start')" {% if running %}style="display:none;"{% endif %}><i class="fa-solid fa-play"></i> Start</button>
        <button class="btn btn-danger" id="stopBtn" onclick="doAction('stop')" {% if not running %}style="display:none;"{% endif %}><i class="fa-solid fa-stop"></i> Stop</button>
        <div id="logBox">Loading logs...</div>
    </div>
    <script>
        const token = "{{ token }}";
        function refresh() {
            fetch('/public/' + token + '/status').then(r => r.json()).then(res => {
                if (!res.ok) return;
                document.getElementById('logBox').textContent = res.log || '(No logs yet)';
                const pill = document.getElementById('statusPill');
                pill.textContent = res.running ? 'RUNNING' : 'OFFLINE';
                pill.className = 'status-pill ' + (res.running ? 'status-run' : 'status-off');
                document.getElementById('startBtn').style.display = res.running ? 'none' : 'block';
                document.getElementById('stopBtn').style.display = res.running ? 'block' : 'none';
            });
        }
        function doAction(action) {
            fetch('/public/' + token + '/' + action, { method: 'POST' }).then(r => r.json()).then(res => {
                if (!res.ok) Swal.fire('Error', res.error || 'Action failed', 'error');
                setTimeout(refresh, 500);
            });
        }
        refresh();
        setInterval(refresh, 4000);
    </script>
    {% else %}
    <div class="card">
        <h2><i class="fa-solid fa-triangle-exclamation"></i> Invalid Link</h2>
        <p class="small-text">This public link has expired or was never valid.</p>
    </div>
    {% endif %}
</body>
</html>'''

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FireXDecoder - Hosting Panel</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
<style>
  :root {
    --bg: #030508; --primary: #00ffff; --card: rgba(22,27,34,0.85); --text: #e6edf3; --glass: rgba(255,255,255,0.05);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 12px; padding-bottom: 100px; min-height: 100vh; }
  .user-bar { background: rgba(0,0,0,0.8); padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; border-radius: 14px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.08); }
  .user-bar b { color: var(--primary); }
  .logout-btn { color: #ff4757; text-decoration: none; font-size: 18px; }
  .upload-card { background: var(--card); border: 2px dashed rgba(0,255,255,0.3); border-radius: 18px; padding: 20px; text-align: center; margin-bottom: 18px; }
  .upload-card i { font-size: 26px; color: var(--primary); }
  .upload-card p { margin: 8px 0; font-size: 13px; opacity: 0.75; }
  #fileInput { display: none; }
  .btn { padding: 10px 16px; border-radius: 10px; border: none; font-weight: bold; cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; text-decoration: none; color: #fff; }
  .btn-primary { background: linear-gradient(45deg, #00ffff, #7000ff); color: #000; }
  .btn-danger { background: #ff4757; }
  .btn-outline { background: transparent; border: 1px solid rgba(255,255,255,0.2); }
  .btn-small { padding: 7px 10px; font-size: 12px; }
  #progressWrap { display:none; margin-top: 12px; background: rgba(255,255,255,0.08); border-radius: 8px; overflow: hidden; height: 8px; }
  #progressBar { height: 100%; width: 0%; background: linear-gradient(90deg,#00ffff,#7000ff); transition: width .2s; }
  #deployStatus { font-size: 12px; margin-top: 8px; opacity: 0.85; min-height: 16px; }

  .app-card { background: var(--card); border-radius: 18px; padding: 15px; margin-bottom: 14px; border: 1px solid rgba(255,255,255,0.06); }
  .app-top { display: flex; justify-content: space-between; align-items: center; }
  .app-name { font-weight: bold; font-size: 15px; color: var(--primary); }
  .status-pill { font-size: 10px; padding: 4px 9px; border-radius: 20px; border: 1px solid; }
  .status-run { color: #2ecc71; border-color: #2ecc71; background: rgba(46,204,113,0.1); }
  .status-off { color: #ff4757; border-color: #ff4757; background: rgba(255,71,87,0.1); }
  .meta-row { font-size: 11px; opacity: 0.65; margin-top: 6px; display: flex; flex-wrap: wrap; gap: 10px; }
  .toggle-row { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; font-size: 12px; background: rgba(255,255,255,0.03); padding: 8px 10px; border-radius: 10px; }
  .toggle-switch { position: relative; width: 40px; height: 22px; }
  .toggle-switch input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; cursor: pointer; inset: 0; background: #444; border-radius: 22px; transition: .3s; }
  .slider:before { content: ""; position: absolute; height: 16px; width: 16px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .3s; }
  input:checked + .slider { background: #2ecc71; }
  input:checked + .slider:before { transform: translateX(18px); }
  .action-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 10px; }
  .action-grid a, .action-grid button { width: 100%; margin: 0; justify-content: center; }
  .action-grid2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-top: 6px; }

  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 999; align-items: center; justify-content: center; padding: 15px; }
  .modal-box { background: #10141a; border-radius: 16px; padding: 18px; width: 100%; max-width: 480px; max-height: 85vh; overflow-y: auto; border: 1px solid rgba(0,255,255,0.15); }
  .modal-box h3 { color: var(--primary); margin-top: 0; font-size: 15px; }
  .close-btn { float: right; cursor: pointer; color: #ff4757; font-size: 18px; }
  #logBox { background: #000; color: #0f0; font-family: monospace; font-size: 11px; padding: 10px; border-radius: 8px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
  .file-list { max-height: 200px; overflow-y: auto; margin: 10px 0; }
  .file-item { display: flex; justify-content: space-between; padding: 8px; background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 4px; font-size: 12px; cursor: pointer; }
  #fileEditor { width: 100%; min-height: 250px; background: #000; color: #0f0; font-family: monospace; font-size: 12px; border-radius: 8px; padding: 10px; border: 1px solid #333; }
  .validate-box { font-size: 12px; margin-top: 10px; padding: 10px; border-radius: 8px; }
  .validate-ok { background: rgba(46,204,113,0.1); border: 1px solid #2ecc71; color: #2ecc71; }
  .validate-bad { background: rgba(255,71,87,0.1); border: 1px solid #ff4757; color: #ff9a9a; }
  .empty-state { text-align: center; opacity: 0.5; padding: 30px 0; font-size: 13px; }
</style>
</head>
<body>

<div class="user-bar">
  <span><i class="fa-solid fa-circle-user"></i> <b>{{ username }}</b></span>
  <a href="/logout" class="logout-btn"><i class="fa-solid fa-power-off"></i></a>
</div>

<div class="upload-card" id="dropZone">
  <i class="fa-solid fa-cloud-arrow-up"></i>
  <p>Upload a ZIP file (any size, up to 200 MB)</p>
  <input type="file" id="fileInput" accept=".zip">
  <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()"><i class="fa-solid fa-upload"></i> Choose ZIP</button>
  <div id="progressWrap"><div id="progressBar"></div></div>
  <div id="deployStatus"></div>
</div>

<div id="appsList">
  {% for a in apps %}
  <div class="app-card" id="card_{{ a.name }}">
    <div class="app-top">
      <span class="app-name">{{ a.name }}</span>
      {% if a.running %}<span class="status-pill status-run">RUNNING</span>{% else %}<span class="status-pill status-off">OFFLINE</span>{% endif %}
    </div>
    <div class="meta-row">
      <span><i class="fa-solid fa-mobile-screen"></i> {{ a.device or "—" }}</span>
      {% if a.running %}<span><i class="fa-solid fa-clock"></i> {{ a.remaining_run_min }}m remaining</span>{% endif %}
      {% if not a.running and a.remaining_wake_min %}<span><i class="fa-solid fa-hourglass-half"></i> Auto‑on in {{ a.remaining_wake_min }}m</span>{% endif %}
    </div>

    <div class="toggle-row">
      <span>Auto‑On (restart after sleep)</span>
      <label class="toggle-switch"><input type="checkbox" {% if a.auto_on %}checked{% endif %} onchange="toggleSetting('{{ a.name }}','auto_on',this)"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>Auto‑Restart (on crash)</span>
      <label class="toggle-switch"><input type="checkbox" {% if a.auto_restart %}checked{% endif %} onchange="toggleSetting('{{ a.name }}','auto_restart',this)"><span class="slider"></span></label>
    </div>

    <div class="action-grid">
      {% if a.running %}
      <a href="/stop/{{ a.name }}" class="btn btn-danger btn-small"><i class="fa-solid fa-stop"></i> Stop</a>
      <a href="#" onclick="restartApp('{{ a.name }}');return false;" class="btn btn-outline btn-small"><i class="fa-solid fa-rotate"></i> Restart</a>
      {% else %}
      <a href="#" onclick="runApp('{{ a.name }}');return false;" class="btn btn-primary btn-small"><i class="fa-solid fa-play"></i> Run</a>
      <a href="#" onclick="validateApp('{{ a.name }}');return false;" class="btn btn-outline btn-small"><i class="fa-solid fa-check"></i> Validate</a>
      {% endif %}
      <a href="#" onclick="openLogs('{{ a.name }}');return false;" class="btn btn-outline btn-small"><i class="fa-solid fa-terminal"></i> Logs</a>
    </div>
    <div class="action-grid2">
      <a href="#" onclick="openFiles('{{ a.name }}');return false;" class="btn btn-outline btn-small"><i class="fa-solid fa-folder-open"></i> Files</a>
      <a href="/download/{{ a.name }}" class="btn btn-outline btn-small"><i class="fa-solid fa-download"></i> Download</a>
    </div>
    <div class="action-grid2">
      <button class="btn btn-outline btn-small" onclick="getPublicLink('{{ a.name }}')"><i class="fa-solid fa-link"></i> Public Link</button>
      <a href="#" onclick="confirmDelete('{{ a.name }}');return false;" class="btn btn-danger btn-small"><i class="fa-solid fa-trash"></i> Delete</a>
    </div>
  </div>
  {% endfor %}
  {% if not apps %}
  <div class="empty-state"><i class="fa-solid fa-box-open" style="font-size:30px;"></i><p>No apps uploaded yet. Upload a ZIP above.</p></div>
  {% endif %}
</div>

<!-- LOG MODAL -->
<div class="modal-overlay" id="logModal">
  <div class="modal-box">
    <span class="close-btn" onclick="closeModal('logModal')">&times;</span>
    <h3 id="logTitle">Logs</h3>
    <div id="logBox">Loading...</div>
  </div>
</div>

<!-- VALIDATE MODAL -->
<div class="modal-overlay" id="validateModal">
  <div class="modal-box">
    <span class="close-btn" onclick="closeModal('validateModal')">&times;</span>
    <h3>Validation Result</h3>
    <div id="validateBox">Checking...</div>
  </div>
</div>

<!-- FILE MANAGER MODAL -->
<div class="modal-overlay" id="fileModal">
  <div class="modal-box">
    <span class="close-btn" onclick="closeModal('fileModal')">&times;</span>
    <h3 id="fileModalTitle">Files</h3>
    <div id="fileListView" class="file-list"></div>
    <div id="fileEditView" style="display:none;">
      <p id="editingFileName" style="font-size:12px; color:#00ffff;"></p>
      <textarea id="fileEditor"></textarea>
      <div style="display:flex; gap:8px; margin-top:8px;">
        <button class="btn btn-primary btn-small" onclick="saveFile()"><i class="fa-solid fa-save"></i> Save</button>
        <button class="btn btn-danger btn-small" onclick="deleteFileFromEditor()"><i class="fa-solid fa-trash"></i> Delete</button>
        <button class="btn btn-outline btn-small" onclick="backToFileList()"><i class="fa-solid fa-arrow-left"></i> Back</button>
      </div>
    </div>
  </div>
</div>

<script>
let currentProject = null;
let currentFile = null;

function closeModal(id) { document.getElementById(id).style.display = 'none'; }

// ---------------- UPLOAD ----------------
document.getElementById('fileInput').addEventListener('change', function(e) {
  const file = e.target.files[0];
  if (!file) return;
  doUpload(file, false);
});

function doUpload(file, overwrite) {
  const progressWrap = document.getElementById('progressWrap');
  const progressBar = document.getElementById('progressBar');
  const statusDiv = document.getElementById('deployStatus');
  progressWrap.style.display = 'block';
  progressBar.style.width = '0%';
  statusDiv.textContent = 'Uploading...';

  const formData = new FormData();
  formData.append('file', file, file.name);
  if (overwrite) formData.append('overwrite', 'true');

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/upload', true);
  xhr.upload.onprogress = function(e) {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressBar.style.width = pct + '%';
      statusDiv.textContent = 'Uploading... ' + pct + '%';
    }
  };
  xhr.onload = function() {
    progressWrap.style.display = 'none';
    let res;
    try { res = JSON.parse(xhr.responseText); } catch(e) { res = {ok:false, error:'Invalid server response.'}; }

    if (res.needs_confirm) {
      Swal.fire({
        title: 'App already exists',
        text: res.error,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Overwrite',
        cancelButtonText: 'Cancel'
      }).then((result) => {
        if (result.isConfirmed) doUpload(file, true);
      });
      return;
    }

    if (!res.ok) {
      statusDiv.textContent = '';
      Swal.fire('Error', res.error || 'Upload failed.', 'error');
      return;
    }

    if (res.warning) {
      statusDiv.textContent = '';
      Swal.fire('Uploaded', res.warning, 'warning').then(() => location.reload());
      return;
    }

    statusDiv.textContent = 'Deployed! Reloading...';
    setTimeout(() => location.reload(), 700);
  };
  xhr.onerror = function() {
    progressWrap.style.display = 'none';
    statusDiv.textContent = '';
    Swal.fire('Error', 'Network error. Please try again.', 'error');
  };
  xhr.send(formData);
}

// drag & drop
const dz = document.getElementById('dropZone');
['dragover','dragenter'].forEach(evt => dz.addEventListener(evt, e => { e.preventDefault(); }));
dz.addEventListener('drop', e => {
  e.preventDefault();
  if (e.dataTransfer.files.length) doUpload(e.dataTransfer.files[0], false);
});

// ---------------- RUN / RESTART ----------------
function runApp(name) {
  Swal.fire({ title: 'Starting...', text: name, didOpen: () => Swal.showLoading(), allowOutsideClick: false });
  fetch('/run/' + encodeURIComponent(name) + '?json=1').then(r => r.json()).then(res => {
    if (res.ok) {
      Swal.fire('Started!', res.device ? ('Device: ' + res.device) : '', 'success').then(() => location.reload());
    } else {
      Swal.fire('Failed', res.error || 'Unknown error', 'error');
    }
  }).catch(() => Swal.fire('Error', 'Network issue', 'error'));
}

function restartApp(name) {
  Swal.fire({ title: 'Restarting...', didOpen: () => Swal.showLoading(), allowOutsideClick: false });
  fetch('/restart/' + encodeURIComponent(name) + '?json=1').then(r => r.json()).then(res => {
    if (res.ok) { Swal.fire('Restarted!', '', 'success').then(() => location.reload()); }
    else { Swal.fire('Failed', res.error || '', 'error'); }
  });
}

function getPublicLink(name) {
  fetch('/get_public_link/' + encodeURIComponent(name), { method: 'POST' })
    .then(r => r.json()).then(res => {
      if (res.ok) {
        Swal.fire({
          title: 'Public Link (no login)',
          html: '<input readonly style="width:100%;padding:8px;font-size:12px;" value="' + res.url + '" onclick="this.select()"><p style="font-size:11px;opacity:0.7;margin-top:8px;">Anyone with this link can start/stop and view logs. File editing requires login.</p>',
          confirmButtonText: 'Close'
        });
      } else {
        Swal.fire('Error', res.error || 'Link could not be generated', 'error');
      }
    });
}

function confirmDelete(name) {
  Swal.fire({
    title: 'Delete permanently?',
    text: name + ' will be removed.',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'Yes, delete',
    confirmButtonColor: '#ff4757'
  }).then((result) => {
    if (result.isConfirmed) window.location.href = '/delete/' + encodeURIComponent(name);
  });
}

// ---------------- TOGGLES ----------------
function toggleSetting(name, field, checkbox) {
  fetch('/toggle_' + field + '/' + encodeURIComponent(name), { method: 'POST' })
    .then(r => r.json()).then(res => {
      if (!res.ok) { checkbox.checked = !checkbox.checked; Swal.fire('Error', 'Setting not saved', 'error'); }
    }).catch(() => { checkbox.checked = !checkbox.checked; });
}

// ---------------- VALIDATE ----------------
function validateApp(name) {
  document.getElementById('validateModal').style.display = 'flex';
  const box = document.getElementById('validateBox');
  box.innerHTML = 'Checking code...';
  fetch('/validate/' + encodeURIComponent(name)).then(r => r.json()).then(res => {
    if (res.ok) {
      box.innerHTML = '<div class="validate-box validate-ok"><i class="fa-solid fa-circle-check"></i> All good! Entry file: ' + (res.entry || '') + '</div>';
    } else if (res.problems) {
      let html = '<div class="validate-box validate-bad">';
      res.problems.forEach(p => {
        html += '<b>' + p.file + '</b>' + (p.line ? (' (Line ' + p.line + ')') : '') + '<br>' + escapeHtml(p.error || '') + '<hr style="opacity:0.2;">';
      });
      html += '</div>';
      box.innerHTML = html;
    } else {
      box.innerHTML = '<div class="validate-box validate-bad">' + escapeHtml(res.error || 'Unknown issue') + '</div>';
    }
  }).catch(() => { box.innerHTML = '<div class="validate-box validate-bad">Error during validation.</div>'; });
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ---------------- LOGS ----------------
let logInterval = null;
function openLogs(name) {
  document.getElementById('logModal').style.display = 'flex';
  document.getElementById('logTitle').textContent = 'Logs — ' + name;
  fetchLogs(name);
  if (logInterval) clearInterval(logInterval);
  logInterval = setInterval(() => fetchLogs(name), 3000);
}
function fetchLogs(name) {
  fetch('/get_log/' + encodeURIComponent(name)).then(r => r.json()).then(res => {
    const box = document.getElementById('logBox');
    box.textContent = res.log || '(No logs yet)';
    box.scrollTop = box.scrollHeight;
  });
}
document.getElementById('logModal').addEventListener('click', function(e){
  if (e.target === this) { clearInterval(logInterval); closeModal('logModal'); }
});

// ---------------- FILE MANAGER ----------------
function openFiles(name) {
  currentProject = name;
  document.getElementById('fileModal').style.display = 'flex';
  document.getElementById('fileModalTitle').textContent = 'Files — ' + name;
  document.getElementById('fileListView').style.display = 'block';
  document.getElementById('fileEditView').style.display = 'none';
  loadFileList();
}
function loadFileList() {
  const view = document.getElementById('fileListView');
  view.innerHTML = 'Loading...';
  fetch('/list_files/' + encodeURIComponent(currentProject)).then(r => r.json()).then(res => {
    if (!res.files.length) { view.innerHTML = '<p style="font-size:12px;opacity:0.6;">No files found.</p>'; return; }
    view.innerHTML = '';
    res.files.forEach(f => {
      const div = document.createElement('div');
      div.className = 'file-item';
      div.innerHTML = '<span>' + escapeHtml(f) + '</span><i class="fa-solid fa-pen"></i>';
      div.onclick = () => openFileEditor(f);
      view.appendChild(div);
    });
  });
}
function openFileEditor(filename) {
  currentFile = filename;
  fetch('/read_file', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({project: currentProject, filename: filename}) })
    .then(r => r.json()).then(res => {
      document.getElementById('fileListView').style.display = 'none';
      document.getElementById('fileEditView').style.display = 'block';
      document.getElementById('editingFileName').textContent = filename;
      document.getElementById('fileEditor').value = res.content || '';
    });
}
function backToFileList() {
  document.getElementById('fileListView').style.display = 'block';
  document.getElementById('fileEditView').style.display = 'none';
  loadFileList();
}
function saveFile() {
  const content = document.getElementById('fileEditor').value;
  fetch('/save_file', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({project: currentProject, filename: currentFile, content: content}) })
    .then(r => r.json()).then(res => {
      if (res.status === 'success') Swal.fire({title:'Saved!', icon:'success', timer:1000, showConfirmButton:false});
      else Swal.fire('Error', res.error || 'Save failed', 'error');
    });
}
function deleteFileFromEditor() {
  Swal.fire({title:'Delete file?', icon:'warning', showCancelButton:true, confirmButtonColor:'#ff4757'}).then(result => {
    if (!result.isConfirmed) return;
    fetch('/delete_file', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({project: currentProject, filename: currentFile}) })
      .then(r => r.json()).then(res => { backToFileList(); });
  });
}
document.getElementById('fileModal').addEventListener('click', function(e){
  if (e.target === this) closeModal('fileModal');
});

// ---------------- AUTO REFRESH DASHBOARD ----------------
setInterval(() => { location.reload(); }, 60000);
</script>
</body>
</html>'''

# ===========================================================================
# Flask routes
# ===========================================================================

@app.before_request
def _boot():
    ensure_scheduler()

def require_login():
    if 'username' not in session:
        return redirect(url_for('login'))
    return None

def require_admin():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    return None

def current_user_key():
    if session.get('is_admin'):
        return ADMIN_INTERNAL_ID
    return session.get('user_folder') or user_folder_id(session.get('username', ''))

# -------------------- Authentication --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('password', '').strip()

        if not is_valid_email(email):
            error = 'Please enter a valid email address (e.g., you@example.com).'
        elif not pw or len(pw) < 4:
            error = 'Password must be at least 4 characters.'
        elif is_locked_out(email):
            error = 'Too many failed attempts. Please wait 1 minute.'

        if error:
            return render_template_string(LOGIN_HTML, error=error)

        db = load_db()
        if email not in db['users']:
            db['users'][email] = {'pw_hash': generate_password_hash(pw), 'vip': False, 'created': int(time.time()*1000)}
            save_db(db)
            session['is_admin'] = False
            session['username'] = email
            session['user_folder'] = user_folder_id(email)
            reset_login_attempts(email)
            return redirect(url_for('index'))

        if check_password_hash(db['users'][email]['pw_hash'], pw):
            session['is_admin'] = False
            session['username'] = email
            session['user_folder'] = user_folder_id(email)
            reset_login_attempts(email)
            return redirect(url_for('index'))

        register_failed_login(email)
        error = 'Incorrect password for this email.'

    return render_template_string(LOGIN_HTML, error=error)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'):
        return redirect(url_for('admin_panel'))

    db = load_db()
    trusted = request.cookies.get('admin_trust')
    if trusted and trusted in db.get('admin_device_tokens', {}):
        session['is_admin'] = True
        session['username'] = ADMIN_INTERNAL_ID
        return redirect(url_for('admin_panel'))

    error = None
    if request.method == 'POST':
        pw = request.form.get('password', '').strip()
        if is_locked_out('__admin_pw__'):
            error = 'Too many failed attempts. Please wait 1 minute.'
        elif pw == ADMIN_PASS:
            reset_login_attempts('__admin_pw__')
            session['is_admin'] = True
            session['username'] = ADMIN_INTERNAL_ID
            token = generate_secret_token()
            db.setdefault('admin_device_tokens', {})[token] = True
            save_db(db)
            resp = redirect(url_for('admin_panel'))
            resp.set_cookie('admin_trust', token, max_age=365*24*3600, httponly=True, samesite='Lax')
            return resp
        else:
            register_failed_login('__admin_pw__')
            error = 'Incorrect password.'
    return render_template_string(ADMIN_LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    was_admin = session.get('is_admin', False)
    session.clear()
    if was_admin:
        resp = redirect(url_for('login'))
        resp.delete_cookie('admin_trust')
        return resp
    return redirect(url_for('login'))

# -------------------- Dashboard --------------------
@app.route('/')
def index():
    login_resp = require_login()
    if login_resp:
        return login_resp

    user_name = current_user_key()
    user_dir = safe_join(UPLOAD_FOLDER, user_name)
    os.makedirs(user_dir, exist_ok=True)

    db = load_db()
    apps_list = []
    for name in sorted(os.listdir(user_dir)):
        if not os.path.isdir(os.path.join(user_dir, name)):
            continue
        p = processes.get((user_name, name))
        running = bool(p and p.poll() is None)
        settings = get_app_settings(db, user_name, name)
        start_ms = db['start_times'].get(app_settings_key(user_name, name), 0)
        elapsed = (time.time() - start_ms/1000.0) if start_ms else 0
        sleep_hours = get_config(db, 'sleep_after_hours')
        wake_minutes = get_config(db, 'auto_wake_after_minutes')
        remaining_run = max(0, sleep_hours*3600 - elapsed) if running else 0
        remaining_wake = 0
        if not running and settings.get('offline_at') and settings.get('auto_on') and not settings.get('manual_stop'):
            remaining_wake = max(0, wake_minutes*60 - (time.time() - settings['offline_at']))

        apps_list.append({
            'name': name,
            'running': running,
            'auto_on': settings.get('auto_on', False),
            'auto_restart': settings.get('auto_restart', False),
            'device': settings.get('device_platform'),
            'remaining_run_min': round(remaining_run/60, 1),
            'remaining_wake_min': round(remaining_wake/60, 1),
        })

    display_name = 'Admin' if session.get('is_admin') else session.get('username', user_name)
    return render_template_string(DASHBOARD_HTML, apps=apps_list, username=display_name)

# -------------------- Upload / Validation / Run / Stop / Delete --------------------
@app.route('/upload', methods=['POST'])
def upload():
    login_resp = require_login()
    if login_resp:
        return jsonify({'ok': False, 'error': 'Login required'}), 401
    return _do_upload(current_user_key())

def _do_upload(user_name, mark_unlimited=False):
    file = request.files.get('file')
    overwrite = request.form.get('overwrite') == 'true'

    if not file or not file.filename:
        return jsonify({'ok': False, 'error': 'No file provided.'}), 400
    if not file.filename.lower().endswith('.zip'):
        return jsonify({'ok': False, 'error': 'Only .zip files are allowed.'}), 400

    app_name = re.sub(r'[^A-Za-z0-9_\-]', '_', file.filename.rsplit('.', 1)[0])[:50]
    if not app_name:
        return jsonify({'ok': False, 'error': 'Invalid app name.'}), 400

    user_dir = safe_join(UPLOAD_FOLDER, user_name, app_name)
    already_exists = os.path.exists(user_dir)
    if already_exists and not overwrite:
        return jsonify({'ok': False, 'needs_confirm': True, 'error': f"'{app_name}' already exists. Overwrite?"}), 200

    tmp_zip = os.path.join(BASE_DIR, f'_tmp_{user_name}_{app_name}_{int(time.time())}.zip')
    file.save(tmp_zip)

    if not zipfile.is_zipfile(tmp_zip):
        os.remove(tmp_zip)
        return jsonify({'ok': False, 'error': 'Corrupt or invalid ZIP file.'}), 400

    db = load_db()
    key = (user_name, app_name)
    if key in processes and processes[key].poll() is None:
        stop_app_process(user_name, app_name, db, manual=True)

    if os.path.exists(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)
    os.makedirs(user_dir, exist_ok=True)
    extract_dir = os.path.join(user_dir, 'extracted')

    try:
        with zipfile.ZipFile(tmp_zip, 'r') as zip_ref:
            bad = zip_ref.testzip()
            if bad:
                raise zipfile.BadZipFile(f'Corrupt entry: {bad}')
            for member in zip_ref.namelist():
                member_path = os.path.abspath(os.path.join(extract_dir, member))
                if not member_path.startswith(os.path.abspath(extract_dir)):
                    raise ValueError('Suspicious path traversal in ZIP – blocked.')
            zip_ref.extractall(extract_dir)
    except (zipfile.BadZipFile, ValueError) as e:
        shutil.rmtree(user_dir, ignore_errors=True)
        os.remove(tmp_zip)
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        shutil.rmtree(user_dir, ignore_errors=True)
        os.remove(tmp_zip)
        return jsonify({'ok': False, 'error': f'Extraction error: {e}'}), 400
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)

    if not os.path.exists(extract_dir) or not os.listdir(extract_dir):
        shutil.rmtree(user_dir, ignore_errors=True)
        return jsonify({'ok': False, 'error': 'Extracted folder is empty.'}), 400

    if mark_unlimited:
        settings = get_app_settings(db, user_name, app_name)
        settings['unlimited'] = True
        save_db(db)

    entry, kind = find_entry_file(extract_dir)
    if not entry:
        return jsonify({
            'ok': True,
            'warning': f'Uploaded but no entry file found. Must be one of: {", ".join(ENTRY_FILES_PY + ENTRY_FILES_JS)}',
            'app_name': app_name
        })
    return jsonify({'ok': True, 'app_name': app_name, 'entry': entry, 'kind': kind})

@app.route('/validate/<name>')
def validate_app(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'ok': False, 'error': 'Login required'}), 401
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    try:
        _, extract_dir, _ = app_dirs(user_name, name)
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid path'}), 400
    if not os.path.exists(extract_dir):
        return jsonify({'ok': False, 'error': 'App not found'}), 404
    return jsonify(validate_project(extract_dir))

@app.route('/run/<name>')
def run_app_route(name):
    login_resp = require_login()
    if login_resp:
        return login_resp
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    db = load_db()
    result = start_app_process(user_name, name, db)
    if request.args.get('json') == '1':
        return jsonify(result)
    return redirect(url_for('index'))

@app.route('/stop/<name>')
def stop_app_route(name):
    login_resp = require_login()
    if login_resp:
        return login_resp
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    db = load_db()
    stop_app_process(user_name, name, db, manual=True)
    activity.clear_pause(f'{user_name}_{name}')
    if request.args.get('json') == '1':
        return jsonify({'ok': True})
    return redirect(url_for('index'))

@app.route('/restart/<name>')
def restart_app_route(name):
    login_resp = require_login()
    if login_resp:
        return login_resp
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    db = load_db()
    stop_app_process(user_name, name, db, manual=False)
    time.sleep(0.5)
    result = start_app_process(user_name, name, db)
    if request.args.get('json') == '1':
        return jsonify(result)
    return redirect(url_for('index'))

@app.route('/delete/<name>')
def delete_app_route(name):
    login_resp = require_login()
    if login_resp:
        return login_resp
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    db = load_db()
    stop_app_process(user_name, name, db, manual=True)
    app_dir, _, _ = app_dirs(user_name, name)
    if os.path.exists(app_dir):
        shutil.rmtree(app_dir, ignore_errors=True)
    venv_dir = venv_path_for(user_name, name)
    if os.path.exists(venv_dir):
        shutil.rmtree(venv_dir, ignore_errors=True)
    key = app_settings_key(user_name, name)
    db.get('app_settings', {}).pop(key, None)
    db.get('start_times', {}).pop(key, None)
    save_db(db)
    return redirect(url_for('index'))

@app.route('/toggle_auto_on/<name>', methods=['POST'])
def toggle_auto_on(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'ok': False}), 401
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    db = load_db()
    settings = get_app_settings(db, user_name, name)
    settings['auto_on'] = not settings.get('auto_on', False)
    save_db(db)
    return jsonify({'ok': True, 'auto_on': settings['auto_on']})

@app.route('/toggle_auto_restart/<name>', methods=['POST'])
def toggle_auto_restart(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'ok': False}), 401
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid app name'}), 400
    db = load_db()
    settings = get_app_settings(db, user_name, name)
    settings['auto_restart'] = not settings.get('auto_restart', False)
    save_db(db)
    return jsonify({'ok': True, 'auto_restart': settings['auto_restart']})

@app.route('/get_log/<name>')
def get_log(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'log': '', 'status': 'OFFLINE'}), 401
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'log': '', 'status': 'OFFLINE'}), 400
    _, _, log_path = app_dirs(user_name, name)
    log_content = ''
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            log_content = f.read()[-4000:]
    p = processes.get((user_name, name))
    db = load_db()
    is_running = bool(p and p.poll() is None)
    settings = get_app_settings(db, user_name, name)
    return jsonify({
        'log': log_content,
        'status': 'RUNNING' if is_running else 'OFFLINE',
        'start_time': db['start_times'].get(app_settings_key(user_name, name), 0),
        'device': settings.get('device_platform')
    })

@app.route('/download/<name>')
def download_app(name):
    login_resp = require_login()
    if login_resp:
        return login_resp
    user_name = current_user_key()
    if not is_safe_component(name):
        return 'Invalid app name', 400
    _, extract_dir, _ = app_dirs(user_name, name)
    if not os.path.exists(extract_dir):
        return 'App not found', 404
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(extract_dir):
            dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', 'node_modules')]
            for f in files:
                fpath = os.path.join(root, f)
                zf.write(fpath, os.path.relpath(fpath, extract_dir))
    memory_file.seek(0)
    return send_file(memory_file, download_name=f'{name}.zip', as_attachment=True)

# -------------------- Public share links --------------------
@app.route('/get_public_link/<name>', methods=['POST'])
def get_public_link(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'ok': False}), 401
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid name'}), 400
    user_name = current_user_key()
    _, extract_dir, _ = app_dirs(user_name, name)
    if not os.path.exists(extract_dir):
        return jsonify({'ok': False, 'error': 'App not found'}), 404
    db = load_db()
    token = ensure_public_token(db, user_name, name)
    return jsonify({'ok': True, 'token': token, 'url': url_for('public_view', token=token, _external=True)})

@app.route('/revoke_public_link/<name>', methods=['POST'])
def revoke_public_link_route(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'ok': False}), 401
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid name'}), 400
    db = load_db()
    revoke_public_token(db, current_user_key(), name)
    return jsonify({'ok': True})

def _lookup_public_token(token):
    db = load_db()
    tkey = db.get('public_tokens', {}).get(token)
    if not tkey or '_' not in tkey:
        return None, None, None
    user, name = tkey.split('_', 1)
    return db, user, name

@app.route('/public/<token>')
def public_view(token):
    db, user, name = _lookup_public_token(token)
    if not user:
        return render_template_string(PUBLIC_HTML, valid=False, name=None, running=False, token=token)
    p = processes.get((user, name))
    running = bool(p and p.poll() is None)
    return render_template_string(PUBLIC_HTML, valid=True, name=name, running=running, token=token)

@app.route('/public/<token>/status')
def public_status(token):
    db, user, name = _lookup_public_token(token)
    if not user:
        return jsonify({'ok': False, 'error': 'Invalid or revoked link'}), 404
    p = processes.get((user, name))
    running = bool(p and p.poll() is None)
    _, _, log_path = app_dirs(user, name)
    log_content = ''
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            log_content = f.read()[-3000:]
    return jsonify({'ok': True, 'running': running, 'log': log_content, 'name': name})

@app.route('/public/<token>/start', methods=['POST'])
def public_start(token):
    db, user, name = _lookup_public_token(token)
    if not user:
        return jsonify({'ok': False, 'error': 'Invalid or revoked link'}), 404
    result = start_app_process(user, name, db)
    return jsonify(result)

@app.route('/public/<token>/stop', methods=['POST'])
def public_stop(token):
    db, user, name = _lookup_public_token(token)
    if not user:
        return jsonify({'ok': False, 'error': 'Invalid or revoked link'}), 404
    stop_app_process(user, name, db, manual=True)
    return jsonify({'ok': True})

# -------------------- File manager --------------------
@app.route('/list_files/<name>')
def list_files(name):
    login_resp = require_login()
    if login_resp:
        return jsonify({'files': []}), 401
    user_name = current_user_key()
    if not is_safe_component(name):
        return jsonify({'files': []}), 400
    _, extract_dir, _ = app_dirs(user_name, name)
    files = []
    if os.path.exists(extract_dir):
        for root, dirs, filenames in os.walk(extract_dir):
            dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', 'node_modules', '.git')]
            for f in filenames:
                files.append(os.path.relpath(os.path.join(root, f), extract_dir))
    return jsonify({'files': sorted(files)})

def _resolve_project_file(user_name, project, filename):
    if not is_safe_component(project):
        raise ValueError('Invalid project name')
    _, extract_dir, _ = app_dirs(user_name, project)
    target = os.path.abspath(os.path.join(extract_dir, filename))
    if not target.startswith(os.path.abspath(extract_dir) + os.sep) and target != os.path.abspath(extract_dir):
        raise ValueError('Path traversal blocked')
    return target

@app.route('/read_file', methods=['POST'])
def read_content():
    login_resp = require_login()
    if login_resp:
        return jsonify({'content': ''}), 401
    data = request.json or {}
    try:
        path = _resolve_project_file(current_user_key(), data.get('project', ''), data.get('filename', ''))
    except ValueError as e:
        return jsonify({'content': '', 'error': str(e)}), 400
    if os.path.exists(path) and os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return jsonify({'content': f.read()})
        except Exception as e:
            return jsonify({'content': '', 'error': str(e)}), 500
    return jsonify({'content': '', 'error': 'File not found'}), 404

@app.route('/save_file', methods=['POST'])
def save_content():
    login_resp = require_login()
    if login_resp:
        return jsonify({'status': 'error'}), 401
    data = request.json or {}
    try:
        path = _resolve_project_file(current_user_key(), data.get('project', ''), data.get('filename', ''))
    except ValueError as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(data.get('content', ''))
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/delete_file', methods=['POST'])
def delete_file_api():
    login_resp = require_login()
    if login_resp:
        return jsonify({'status': 'error'}), 401
    data = request.json or {}
    try:
        path = _resolve_project_file(current_user_key(), data.get('project', ''), data.get('filename', ''))
    except ValueError as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    if os.path.exists(path):
        os.remove(path)
        return jsonify({'status': 'deleted'})
    return jsonify({'status': 'error', 'error': 'File not found'}), 404

# -------------------- Admin panel --------------------
@app.route('/admin/panel')
def admin_panel():
    admin_resp = require_admin()
    if admin_resp:
        return admin_resp

    db = load_db()
    running_count = count_running_global()
    try:
        import psutil
        ram_percent = psutil.virtual_memory().percent
    except Exception:
        ram_percent = 'N/A'

    all_apps = []
    admin_apps = []
    if os.path.exists(UPLOAD_FOLDER):
        for user in sorted(os.listdir(UPLOAD_FOLDER)):
            user_dir = os.path.join(UPLOAD_FOLDER, user)
            if not os.path.isdir(user_dir):
                continue
            for name in sorted(os.listdir(user_dir)):
                if not os.path.isdir(os.path.join(user_dir, name)):
                    continue
                p = processes.get((user, name))
                running = bool(p and p.poll() is None)
                settings = get_app_settings(db, user, name)
                entry = {
                    'user': user, 'name': name, 'running': running,
                    'device': settings.get('device_platform'),
                    'auto_on': settings.get('auto_on'),
                    'auto_restart': settings.get('auto_restart'),
                }
                if user == ADMIN_INTERNAL_ID:
                    admin_apps.append(entry)
                else:
                    all_apps.append(entry)

    users_list = [{'email': email, 'vip': rec.get('vip', False)} for email, rec in db.get('users', {}).items()]

    return render_template_string(
        ADMIN_HTML,
        users=users_list,
        config=db.get('config', DEFAULT_CONFIG),
        running_count=running_count,
        ram_percent=ram_percent,
        all_apps=all_apps,
        admin_apps=admin_apps
    )

@app.route('/admin/update_config', methods=['POST'])
def admin_update_config():
    admin_resp = require_admin()
    if admin_resp:
        return admin_resp
    db = load_db()
    cfg = db.setdefault('config', {})
    for field, cast in [
        ('max_concurrent_per_user', int),
        ('max_concurrent_vip', int),
        ('max_concurrent_global', int),
        ('sleep_after_hours', float),
        ('auto_wake_after_minutes', int)
    ]:
        val = request.form.get(field)
        if val is not None:
            try:
                cfg[field] = cast(val)
            except ValueError:
                pass
    save_db(db)
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_vip', methods=['POST'])
def admin_toggle_vip():
    admin_resp = require_admin()
    if admin_resp:
        return jsonify({'ok': False}), 401
    email = request.form.get('email', '').strip().lower()
    db = load_db()
    if email in db['users']:
        db['users'][email]['vip'] = not db['users'][email].get('vip', False)
        save_db(db)
        return jsonify({'ok': True, 'vip': db['users'][email]['vip']})
    return jsonify({'ok': False, 'error': 'User not found'}), 404

@app.route('/admin/change_pw', methods=['POST'])
def change_pw():
    admin_resp = require_admin()
    if admin_resp:
        return admin_resp
    email = request.form.get('email', '').strip().lower()
    new_pw = request.form.get('new_pw', '').strip()
    db = load_db()
    if email in db['users'] and new_pw:
        db['users'][email]['pw_hash'] = generate_password_hash(new_pw)
        save_db(db)
    return redirect(url_for('admin_panel'))

@app.route('/admin/login_as/<path:email>')
def login_as(email):
    admin_resp = require_admin()
    if admin_resp:
        return admin_resp
    db = load_db()
    email = email.strip().lower()
    if email not in db['users']:
        return redirect(url_for('admin_panel'))
    session['username'] = email
    session['is_admin'] = False
    session['user_folder'] = user_folder_id(email)
    return redirect(url_for('index'))

@app.route('/admin/upload_admin_app', methods=['POST'])
def admin_upload_app():
    admin_resp = require_admin()
    if admin_resp:
        return admin_resp
    return _do_upload(ADMIN_INTERNAL_ID, mark_unlimited=True)

@app.route('/admin/get_public_link/<name>', methods=['POST'])
def admin_get_public_link(name):
    admin_resp = require_admin()
    if admin_resp:
        return jsonify({'ok': False}), 401
    if not is_safe_component(name):
        return jsonify({'ok': False, 'error': 'Invalid name'}), 400
    db = load_db()
    token = ensure_public_token(db, ADMIN_INTERNAL_ID, name)
    return jsonify({'ok': True, 'token': token, 'url': url_for('public_view', token=token, _external=True)})

# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    ensure_scheduler()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=DEBUG)