#!/usr/bin/env python3
"""QClaw — Arduino App Lab entry point (v1.0.2).

Runs natively inside Arduino App Lab. Bootstraps the workspace, starts the
local llama-server (engines/yzma/lib/llama-server), and exposes a chat
interface via App Lab's arduino:web_ui brick (assets/index.html).

Chat protocol (same as App Lab's canonical cloud_llm examples):
  App Lab → Python:  { "prompt": "<user text>" }  (event: "prompt")
                     { "command": "clear_chat" }    (event: "commands")
                     { "command": "stop_stream" }   (event: "commands")
                     { "command": "get_models" }    (event: "commands")
                     { "command": "set_model",      (event: "commands")
                       "model_name": "..." }
                     { "command": "add_model",      (event: "commands")
                       "entry": {...} }
                     { "command": "delete_model",   (event: "commands")
                       "model_name": "..." }
  Python → App Lab:  token string                   (event: "response")
                     {}                             (event: "stream_end")
                     { "error": "..." }             (event: "llm_error")
                     { "model_name": "..." }        (event: "model_changed")

For SSH/standalone use run python/main_tui.py instead.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Runtime detection ────────────────────────────────────────────────────────

try:
    from arduino.app_bricks.web_ui import WebUI
    from arduino.app_utils import App, Bridge, Logger
    APP_LAB_RUNTIME = True
except ImportError:
    APP_LAB_RUNTIME = False
    App = Bridge = WebUI = None

    class Logger:
        def __init__(self, name: str) -> None:
            self.name = name
        def _emit(self, lvl: str, msg: str) -> None:
            print(f"[{self.name}] {lvl} {msg}", flush=True)
        def info(self, m: str)    -> None: self._emit("INFO",  m)
        def warning(self, m: str) -> None: self._emit("WARN",  m)
        def error(self, m: str)   -> None: self._emit("ERROR", m)
        def debug(self, m: str)   -> None: self._emit("DEBUG", m)

# ── Paths ────────────────────────────────────────────────────────────────────

APP_DIR      = Path(__file__).resolve().parent.parent
QCLAW_HOME   = Path(os.environ.get("QCLAW_HOME", str(Path.home() / ".qclaw")))
WORKSPACE_DST = QCLAW_HOME / "workspace"
CONFIG_SRC   = APP_DIR / "config" / "qclaw.config.json"
CONFIG_DST   = QCLAW_HOME / "config.json"
BIN_DIR      = APP_DIR / "bin"
QCLAW_BIN    = BIN_DIR / "qclaw"
ENGINE_DIR   = APP_DIR / "engines" / "yzma" / "lib"
ENGINE_BIN   = ENGINE_DIR / "llama-server"
# v1.0.2: the ENTIRE workspace tree is bind-mounted to the user's view via
# the agent/ directory — every file and folder under workspace/ (SOUL.md,
# IDENTITY.md, AGENTS.md, USER.md, memory/, skills/, sketches/, python/) is
# extracted from an embedded base64 blob into QCLAW_HOME/workspace at startup,
# then re-exposed at APP_DIR/agent/ as symlink targets visible on the host
# bind-mount. Nothing in workspace/ is obfuscated at runtime; the obfuscation
# applies only to the distribution zip layout.
AGENT_DIR         = APP_DIR / "agent"
AGENT_SKETCH_DIR  = AGENT_DIR / "sketches"
AGENT_PYTHON_DIR  = AGENT_DIR / "python"
AGENT_MEMORY_DIR  = AGENT_DIR / "memory"
AGENT_SKILLS_DIR  = AGENT_DIR / "skills"
AGENT_SOUL        = AGENT_DIR / "SOUL.md"
AGENT_IDENTITY    = AGENT_DIR / "IDENTITY.md"
AGENT_AGENTS      = AGENT_DIR / "AGENTS.md"
AGENT_USER        = AGENT_DIR / "USER.md"
# Container shims (arduino-cli + openocd) also live in an embedded blob.
# We extract them to a runtime path under /tmp and prepend that to PATH;
# the host-side daemon never sees this path, only the container does.
SHIM_RUNTIME_DIR  = Path("/tmp/qclaw-runtime/bin")
# Host-side installer + daemon source. Both files live in SCRIPTS_BLOB_B64
# and are extracted to APP_DIR/.scripts/ at startup (note the leading dot
# — Arduino App Lab's editor and most other editors hide dot-prefixed
# entries by default, so the obfuscation survives the bind-mount round
# trip). APP_DIR is bind-mounted from the host import directory, so after
# bootstrap the WebUI banner's `bash <host-repo>/.scripts/install.sh`
# command resolves to a file the user can paste-execute from a host
# terminal.
HOST_SCRIPTS_DIR  = APP_DIR / ".scripts"
# v2.2.3 arduino-cli proxy: shared cache dir for sketch temp files,
# and the UNIX socket the container shim talks to.
SKETCH_TMPDIR = APP_DIR / ".cache" / "sketches"
ARDUINO_DAEMON_SOCK = APP_DIR / ".cache" / "qclaw-arduino-daemon.sock"
ARDUINO_CLI_SHIM    = SHIM_RUNTIME_DIR / "arduino-cli"
MODEL_DIR    = Path(os.environ.get("QCLAW_MODEL_DIR", str(Path.home() / "models")))
MODEL_NAME   = "Qwen_Qwen3.5-0.8B-Q4_0.gguf"
MODEL_PATH   = MODEL_DIR / MODEL_NAME
# Candidate paths checked in order before attempting a download.
# Covers the App Lab sandbox (home=/home/app) and the host Arduino user.
_MODEL_SEARCH = [
    MODEL_PATH,
    Path("/home/arduino/models") / MODEL_NAME,
    Path("/home/arduino/models/Qwen3.5-0.8B-Q4_0.gguf"),
]
# ggml-org community mirror — public, no auth (the official Qwen/* repo is gated).
MODEL_URL    = ("https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF/resolve/main/"
                "Qwen3.5-0.8B-Q4_0.gguf?download=true")
LLAMA_HOST   = "127.0.0.1"
LLAMA_PORT   = 8083
LLAMA_URL    = f"http://{LLAMA_HOST}:{LLAMA_PORT}"

logger = Logger("qclaw")

# ── Bootstrap ────────────────────────────────────────────────────────────────

def bootstrap_workspace() -> None:
    """v3.0.6.3: extract the embedded workspace + shim blobs and wire up the
    bind-mounted agent/ leaves so user-editable files (sketches, python) live
    in the host-visible directory while the obfuscated content (SOUL, skills,
    IDENTITY, AGENTS, USER, memory) stays inside the container's home.

    Layout after this runs:

        QCLAW_HOME/workspace/                  ← extracted from WORKSPACE_BLOB_B64
            SOUL.md     → /app/agent/SOUL.md       ← symlink to bind-mounted
            IDENTITY.md → /app/agent/IDENTITY.md   ← symlink to bind-mounted
            AGENTS.md   → /app/agent/AGENTS.md     ← symlink to bind-mounted
            USER.md     → /app/agent/USER.md       ← symlink to bind-mounted
            memory      → /app/agent/memory        ← symlink to bind-mounted
            skills      → /app/agent/skills        ← symlink to bind-mounted
            sketches    → /app/agent/sketches      (empty by default)
            python      → /app/agent/python        (empty by default)
        /tmp/qclaw-runtime/bin/
            arduino-cli, openocd               ← extracted from SHIM_BLOB_B64
    """
    import base64, io, tarfile

    QCLAW_HOME.mkdir(parents=True, exist_ok=True)

    # Config: copy in only on first run; user edits at QCLAW_HOME/config.json
    # are preserved across container restarts.
    if not CONFIG_DST.exists() and CONFIG_SRC.exists():
        shutil.copy2(CONFIG_SRC, CONFIG_DST)
        logger.info(f"installed config → {CONFIG_DST}")

    # Workspace: extract on first run, or any time SOUL.md is missing (which
    # also covers user-deleted-by-mistake recovery). Extraction is into a
    # temp dir then atomically moved to avoid half-populated state.
    if not (WORKSPACE_DST / "SOUL.md").exists():
        logger.info(f"extracting embedded workspace → {WORKSPACE_DST}")
        try:
            blob = base64.b64decode(WORKSPACE_BLOB_B64)
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
                tmp_extract = QCLAW_HOME / "_workspace_extract"
                if tmp_extract.exists():
                    shutil.rmtree(tmp_extract)
                tmp_extract.mkdir(parents=True)
                tar.extractall(tmp_extract)
                # Tarball was created from staging/, contents under workspace/
                extracted = tmp_extract / "workspace"
                if WORKSPACE_DST.exists():
                    shutil.rmtree(WORKSPACE_DST)
                extracted.rename(WORKSPACE_DST)
                shutil.rmtree(tmp_extract, ignore_errors=True)
        except Exception as exc:
            logger.error(f"workspace extract failed: {exc}")
            raise

    # Container shims: extract on every start (cheap; ~3 KB tarball). Lives
    # under /tmp so it's container-private and never appears in the user's
    # App Lab editor view.
    try:
        SHIM_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        blob = base64.b64decode(SHIM_BLOB_B64)
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.isreg() and member.name.startswith("shims/"):
                    name = member.name[len("shims/"):]
                    target = SHIM_RUNTIME_DIR / name
                    target.write_bytes(tar.extractfile(member).read())
                    target.chmod(0o755)
        logger.info(f"extracted shims → {SHIM_RUNTIME_DIR}")
    except Exception as exc:
        logger.error(f"shim extract failed: {exc}")

    # Host-side installer + daemon source: extract on every start into
    # APP_DIR/.scripts/ (bind-mounted to ~/ArduinoApps/<import>/.scripts/
    # on the host). The WebUI's daemon-missing banner shows a paste-able
    # `bash <host-repo>/.scripts/install.sh` command that resolves to the
    # extracted file. Re-extracting on every boot is cheap (~24 KB tarball)
    # and ensures the host-side scripts track the embedded payload — if a
    # user edits them by hand we overwrite on next start, which matches the
    # "the binary is the source of truth" obfuscation pattern.
    try:
        HOST_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        blob = base64.b64decode(SCRIPTS_BLOB_B64)
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.isreg() and member.name.startswith("scripts/"):
                    name = member.name[len("scripts/"):]
                    target = HOST_SCRIPTS_DIR / name
                    target.write_bytes(tar.extractfile(member).read())
                    target.chmod(0o755)
        logger.info(f"extracted scripts → {HOST_SCRIPTS_DIR}")
        # Migration: a previous v1.0.2 boot extracted these files to
        # APP_DIR/scripts/ (visible in App Lab's editor). Remove the old
        # location so the dot-hidden version is the only copy on disk.
        legacy_visible = APP_DIR / "scripts"
        if legacy_visible.is_dir() and not legacy_visible.is_symlink():
            for fname in ("install.sh", "qclaw-arduino-daemon.py"):
                (legacy_visible / fname).unlink(missing_ok=True)
            try:
                legacy_visible.rmdir()  # only succeeds if empty
                logger.info(f"removed legacy visible scripts/ directory")
            except OSError:
                # Directory has unexpected content — leave it alone.
                pass
    except Exception as exc:
        logger.error(f"scripts extract failed: {exc}")

    # Agent visible leaves: ensure the dir-typed targets exist (sketches +
    # python are empty in the ZIP; memory/skills get populated from the
    # extracted workspace on first run via _link_to_agent_leaf's merge path).
    # All persist on the host bind-mount across container restarts.
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_SKETCH_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_PYTHON_DIR.mkdir(parents=True, exist_ok=True)

    # Symlink workspace/sketches → /app/agent/sketches and workspace/python
    # → /app/agent/python. Both directions are now bind-mounted-visible
    # from the host while keeping the rest of workspace/ inside the
    # container's home.
    # v1.0.2: expose EVERY workspace item via the agent/ bind-mount so the
    # host (and the App Lab UI) sees the full agent tree as editable.
    # Directories use _link_to_agent_leaf; files use _link_to_agent_file.
    _link_to_agent_leaf(WORKSPACE_DST / "sketches", AGENT_SKETCH_DIR, "sketches")
    _link_to_agent_leaf(WORKSPACE_DST / "python",   AGENT_PYTHON_DIR, "python")
    _link_to_agent_leaf(WORKSPACE_DST / "memory",   AGENT_MEMORY_DIR, "memory")
    _link_to_agent_leaf(WORKSPACE_DST / "skills",   AGENT_SKILLS_DIR, "skills")
    _link_to_agent_file(WORKSPACE_DST / "SOUL.md",     AGENT_SOUL,     "SOUL.md")
    _link_to_agent_file(WORKSPACE_DST / "IDENTITY.md", AGENT_IDENTITY, "IDENTITY.md")
    _link_to_agent_file(WORKSPACE_DST / "AGENTS.md",   AGENT_AGENTS,   "AGENTS.md")
    _link_to_agent_file(WORKSPACE_DST / "USER.md",     AGENT_USER,     "USER.md")

    # Redirect the Go agent binary's hardcoded new-sketch output path into
    # agent/sketches/ so anything the `arduino` tool writes appears on the
    # host bind-mount under agent/. The Go binary creates sketches at
    # APP_DIR/sketch/agent/<timestamp>_qclaw-sketch-NNN/<name>.ino, which
    # this redirect re-exposes as agent/sketches/<timestamp>_*/<name>.ino.
    _redirect_legacy_path(
        APP_DIR / "sketch" / "agent", AGENT_SKETCH_DIR, "sketch/agent", migrate=True,
    )
    # Migration: an earlier v1.0.2 boot symlinked APP_DIR/.cache/sketch into
    # agent/sketches/build/, which then broke arduino-cli's first compile
    # (`mkdir: file exists` because Linux mkdir() returns EEXIST against a
    # symlink-to-dir). Drop the symlink if present so arduino-cli can create
    # the directory natively on its next compile. The compiled binary lives
    # at APP_DIR/.cache/sketch/sketch.ino.elf-zsk.bin, which is on the host
    # bind-mount under ~/ArduinoApps/<import>/.cache/sketch/.
    legacy_cache_sketch = APP_DIR / ".cache" / "sketch"
    if legacy_cache_sketch.is_symlink():
        try:
            legacy_cache_sketch.unlink()
            logger.info(
                "removed stale .cache/sketch symlink — arduino-cli will recreate "
                "it as a real directory on the next compile"
            )
        except OSError as exc:
            logger.warning(f"could not unlink stale .cache/sketch symlink ({exc})")


def _redirect_legacy_path(legacy: Path, target: Path, label: str, migrate: bool = True) -> None:
    """Force `legacy` to be a symlink → `target`. Used to redirect paths the
    Go agent binary or arduino-cli hardcoded into v3.0.6.x layout positions
    into the v1.0.2 agent/ bind-mount, so user-visible artifacts land on the
    host where the App Lab editor sees them.

    If `legacy` is already a real dir on disk:
      * migrate=True  → copy any not-already-present children into `target`
                        first (preserves user sketches across the redirect).
      * migrate=False → drop the dir without copying (build caches; will
                        be regenerated by the next arduino-cli compile).
    """
    target.mkdir(parents=True, exist_ok=True)
    if legacy.is_symlink():
        if legacy.resolve() == target.resolve():
            return  # already pointing at the right target — no-op
        legacy.unlink()
    elif legacy.is_dir():
        if migrate:
            for item in legacy.iterdir():
                dst = target / item.name
                if not dst.exists():
                    try:
                        if item.is_dir():
                            shutil.copytree(item, dst)
                        else:
                            shutil.copy2(item, dst)
                    except OSError as exc:
                        logger.warning(f"{label}: failed to migrate {item.name} ({exc})")
        shutil.rmtree(legacy, ignore_errors=True)
    elif legacy.exists():
        logger.warning(f"{label}: unexpected non-dir at {legacy}, skipping redirect")
        return
    legacy.parent.mkdir(parents=True, exist_ok=True)
    try:
        legacy.symlink_to(target)
        logger.info(f"{label}: {legacy} → {target}")
    except OSError as exc:
        logger.warning(f"{label}: could not symlink ({exc})")


def _link_to_agent_leaf(link: Path, target: Path, label: str) -> None:
    """Force link → target as a symlink. If link is a real dir with content,
    merge it into target first so we don't lose user-written sketches when
    upgrading from a pre-v3.0.6.3 import."""
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    elif link.is_dir():
        # v1.0.2: ensure target exists before merging. Pre-v1.0.2 the only
        # leaves were sketches/ + python/ which were explicitly mkdir'd
        # ahead of the call; with workspace/{memory,skills} also routed
        # through here the target may legitimately not exist yet.
        target.mkdir(parents=True, exist_ok=True)
        for item in link.iterdir():
            dst = target / item.name
            if not dst.exists():
                if item.is_dir():
                    shutil.copytree(item, dst)
                else:
                    shutil.copy2(item, dst)
        shutil.rmtree(link)
    try:
        link.symlink_to(target)
        logger.info(f"{label}: workspace/{label}/ → {target}")
    except OSError as exc:
        logger.warning(f"could not symlink workspace/{label} ({exc})")


def _link_to_agent_file(link: Path, target: Path, label: str) -> None:
    """v3.0.6.4: file-level analogue of _link_to_agent_leaf for SOUL.md and
    IDENTITY.md. Migration semantics:
      - If `link` is the right symlink already: no-op.
      - If `link` is a symlink to elsewhere: replace.
      - If `link` is a real file (just-extracted embed copy, OR a pre-v3.0.6.4
        legacy edit): if `target` doesn't exist yet, move `link` → `target` to
        preserve any user edits as the seed. Otherwise discard `link`.
      - Finally ensure `target` exists (copy from embed extract as last resort)
        and create the symlink.
    """
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    elif link.is_file():
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(link), str(target))
        else:
            link.unlink()
    elif link.exists():
        logger.warning(f"{label}: workspace path is neither file nor symlink, skipping")
        return
    if not target.exists():
        logger.warning(f"{label}: agent target {target} missing, can't link")
        return
    try:
        link.symlink_to(target)
        logger.info(f"{label}: workspace/{link.name} → {target}")
    except OSError as exc:
        logger.warning(f"could not symlink workspace/{link.name} ({exc})")


def ensure_binary() -> None:
    if not QCLAW_BIN.exists():
        raise RuntimeError(f"qclaw binary missing at {QCLAW_BIN}")
    if not os.access(QCLAW_BIN, os.X_OK):
        QCLAW_BIN.chmod(0o755)
    if ARDUINO_CLI_SHIM.exists() and not os.access(ARDUINO_CLI_SHIM, os.X_OK):
        ARDUINO_CLI_SHIM.chmod(0o755)

# v3.0.6: GitHub's auto-generated source ZIPs (used by App Lab imports of
# any release-page download) flatten Git symlinks into small text files
# whose content is the literal symlink target name. v3.0.1 fixed this for
# bin/openocd by replacing the symlink with a real shell wrapper. The yzma
# engine still has ~10 SONAME symlinks under engines/yzma/lib/ that hit the
# same bug — and unlike bin/openocd those CAN'T be replaced with wrapper
# scripts because the dynamic linker reads ELF directly. So we detect the
# flattening at bootstrap and restore the symlinks in place.
#
# A flattened symlink looks like:
#   $ file libllama-common.so.0
#   libllama-common.so.0: ASCII text, with no line terminators
#   $ wc -c libllama-common.so.0
#   27 libllama-common.so.0
#   $ cat libllama-common.so.0
#   libllama-common.so.0.0.9127
#
# We treat any file <300 bytes whose entire content names a sibling file
# (and contains no shell metacharacters or path separators outside that
# sibling's name) as a flattened symlink, and `os.symlink` it back.

_MAX_FLATTENED_SYMLINK_SIZE = 300
_SAFE_SYMLINK_TARGET_RE = re.compile(r"^[A-Za-z0-9._+\-]+$")


def restore_flattened_symlinks(target_dir: Path, label: str) -> int:
    """Convert flattened-symlink text files in `target_dir` back to real symlinks.

    Returns the number of symlinks restored. No-op if everything is
    already a real symlink or a real file.
    """
    if not target_dir.is_dir():
        return 0
    restored = 0
    try:
        entries = list(target_dir.iterdir())
    except OSError:
        return 0
    for f in entries:
        try:
            if not f.is_file() or f.is_symlink():
                continue
            sz = f.stat().st_size
            if sz == 0 or sz > _MAX_FLATTENED_SYMLINK_SIZE:
                continue
            content = f.read_text(errors="replace").strip()
        except OSError:
            continue
        # Bail unless the content looks exactly like a single sibling filename.
        if not _SAFE_SYMLINK_TARGET_RE.match(content):
            continue
        target = target_dir / content
        if not target.exists() or target == f:
            continue
        try:
            f.unlink()
            os.symlink(content, f)
            restored += 1
        except OSError as exc:
            logger.warning(f"{label}: could not restore symlink {f.name} → {content}: {exc}")
    if restored:
        logger.info(f"{label}: restored {restored} flattened symlink(s) in {target_dir}")
    return restored

# v3.0.6: surface the daemon-missing state to the WebUI as well, not just the
# Python log. _emit_daemon_status pushes a {state, command, socket} payload
# to any connected WebUI; the frontend renders a banner with a Copy button
# until state flips to "ok".
_DAEMON_WATCHER_STARTED = False
_DAEMON_WATCHER_STOP = threading.Event()


def _daemon_status_payload() -> dict:
    """Build the daemon_status payload the WebUI consumes."""
    # APP_HOME is the host-side repo path App Lab injects via the compose
    # 'environment:' block. Use it (not /app, the container view) when
    # formatting the hint so users can copy-paste straight into a host
    # shell. Fall back to APP_DIR if APP_HOME is missing.
    host_repo = os.environ.get("APP_HOME") or str(APP_DIR)
    state = "ok" if ARDUINO_DAEMON_SOCK.exists() else "missing"
    return {
        "state":   state,
        "socket":  str(ARDUINO_DAEMON_SOCK),
        "command": f"bash {host_repo}/.scripts/install.sh",
    }


def _emit_daemon_status() -> None:
    """Push the current daemon_status to the WebUI (best-effort, no-op if no UI)."""
    try:
        ui = _ui_instance
        if ui is not None:
            ui.send_message("daemon_status", _daemon_status_payload())
    except Exception as exc:
        logger.debug(f"daemon_status emit failed: {exc}")


def _daemon_watcher() -> None:
    """Background thread: re-check the socket every 5 s and emit each tick.

    v3.0.6.1: emits on EVERY tick, not just on state-change. The change-only
    approach (v3.0.5 → v3.0.6) lost events when the browser connected after
    the initial emit and the state hadn't changed since, leaving the banner
    invisible despite the daemon being absent. Emitting every tick costs
    one ~120-byte socket.io frame per 5 s — trivial — and guarantees a
    late-connecting browser sees the current state within one scan interval.
    Still logs the state-flip line ONLY on transition so the Python log
    isn't spammed.
    """
    last_state: str | None = None
    while not _DAEMON_WATCHER_STOP.is_set():
        payload = _daemon_status_payload()
        try:
            ui = _ui_instance
            if ui is not None:
                ui.send_message("daemon_status", payload)
        except Exception:
            pass
        if payload["state"] != last_state:
            if payload["state"] == "ok" and last_state is not None:
                logger.info(f"arduino-cli host daemon: socket appeared at {ARDUINO_DAEMON_SOCK}")
            elif payload["state"] == "missing" and last_state == "ok":
                logger.warning(f"arduino-cli host daemon: socket disappeared from {ARDUINO_DAEMON_SOCK}")
            last_state = payload["state"]
        _DAEMON_WATCHER_STOP.wait(5.0)


def _start_daemon_watcher() -> None:
    """Spawn the background watcher exactly once."""
    global _DAEMON_WATCHER_STARTED
    if _DAEMON_WATCHER_STARTED:
        return
    _DAEMON_WATCHER_STARTED = True
    threading.Thread(target=_daemon_watcher, daemon=True, name="qclaw-daemon-watcher").start()


def _check_arduino_daemon() -> None:
    """Log a clear note about the v3.0.6 arduino-cli proxy daemon status.

    The Go arduino tool inside the sandbox shells out to ``arduino-cli``,
    which is intercepted by the container shim at bin/arduino-cli and
    forwarded over a UNIX socket to the host-side daemon. If the socket
    isn't there, the tool will still report a clean error to the agent —
    but logging the state up front makes the missing-host-daemon case
    obvious in the App Lab terminal.
    """
    if not ARDUINO_CLI_SHIM.exists():
        logger.warning(
            "arduino-cli shim missing at %s — `arduino` tool will fail. "
            "Re-run `make qclaw-install` or reinstall the QClaw App Lab package.",
            ARDUINO_CLI_SHIM,
        )
        return
    if ARDUINO_DAEMON_SOCK.exists():
        logger.info(f"arduino-cli host daemon: socket present at {ARDUINO_DAEMON_SOCK}")
    else:
        # APP_HOME is the host-side repo path App Lab injects via the
        # compose 'environment:' block. Use it (not /app, the container
        # view) when formatting the hint so users can copy-paste straight
        # into a host shell. Fall back to APP_DIR if APP_HOME is missing.
        host_repo = os.environ.get("APP_HOME") or str(APP_DIR)
        logger.warning(
            "arduino-cli host daemon socket NOT FOUND at %s — the `arduino` tool will "
            "fail with exit 127 until the daemon is installed. To fix this in one step, "
            "open a terminal on the Uno Q (outside this App Lab container) and run:\n"
            "    bash %s/.scripts/install.sh\n"
            "The installer drops the systemd --user unit, starts the daemon, and exits.",
            ARDUINO_DAEMON_SOCK,
            host_repo,
        )

def ensure_model() -> None:
    global MODEL_PATH
    for candidate in _MODEL_SEARCH:
        if candidate.exists():
            mb = candidate.stat().st_size / (1024 * 1024)
            logger.info(f"model present: {candidate} ({mb:.0f} MB)")
            MODEL_PATH = candidate
            return
    logger.info(f"downloading {MODEL_NAME} (~500 MB) from Hugging Face…")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL_PATH.with_suffix(".gguf.part")
    last_pct = -1
    def _progress(n: int, bs: int, total: int) -> None:
        nonlocal last_pct
        if total <= 0: return
        pct = min(100, int(n * bs * 100 / total))
        if pct >= last_pct + 10:
            logger.info(f"  download {pct}% ({n*bs/1e6:.0f}/{total/1e6:.0f} MB)")
            last_pct = pct
    try:
        urllib.request.urlretrieve(MODEL_URL, str(tmp), _progress)
    except (urllib.error.URLError, OSError) as exc:
        if tmp.exists(): tmp.unlink()
        raise RuntimeError(
            f"model download failed: {exc}\n"
            f"Place {MODEL_NAME} in ~/models/ or /home/arduino/models/ and retry."
        ) from exc
    tmp.rename(MODEL_PATH)
    logger.info(f"model downloaded: {MODEL_NAME}")

# ── llama-server ─────────────────────────────────────────────────────────────

_llama_proc: subprocess.Popen | None = None

def _llama_healthy(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{LLAMA_URL}/health", timeout=timeout) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:
        return False

def start_llama_server() -> None:
    """Spawn llama-server on port 8083, shared across Low/Medium/High modes.

    Medium/High invoke `qclaw direct/agent` which, via the patched llamaserver
    provider, detects this server and reuses it instead of spawning a duplicate.
    """
    global _llama_proc
    if _llama_healthy():
        logger.info(f"llama-server already running on port {LLAMA_PORT}")
        return
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{ENGINE_DIR}:{env.get('LD_LIBRARY_PATH', '')}"
    _llama_proc = subprocess.Popen(
        [
            str(ENGINE_BIN),
            "-m", str(MODEL_PATH),
            "--host", LLAMA_HOST,
            "--port", str(LLAMA_PORT),
            "-t", "4",
            "-c", "12000",      # v3.0.4: bumped from 8192 — agent conversations cross 8400 tokens after the first tool call (compile output + tool_done body)
            "-np", "1",
            "--reasoning", "off",        # Low-mode latency win; trade-off for Medium/High
            "--jinja",
            "--log-disable",
            "--mlock",                   # pin weights in RAM (no swap)
            "--flash-attn", "on",        # fused attention kernel (warm-state win)
            "--cache-type-k", "q8_0",    # quantize K cache → half KV RAM
            "--cache-type-v", "q8_0",    # quantize V cache → half KV RAM
        ],
        env=env,
        cwd=str(APP_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"llama-server starting (pid={_llama_proc.pid})…")
    for i in range(60):
        time.sleep(1)
        if _llama_healthy():
            logger.info("llama-server ready ✓")
            return
    logger.warning("llama-server did not respond after 60s — first message may be slow")

def stop_llama_server() -> None:
    global _llama_proc
    if _llama_proc and _llama_proc.poll() is None:
        logger.info("stopping llama-server")
        _llama_proc.terminate()
        try:
            _llama_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _llama_proc.kill()
        _llama_proc = None

# ── Config management ─────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load runtime config; fall back to repo template if missing."""
    for src in (CONFIG_DST, CONFIG_SRC):
        if src.exists():
            try:
                with open(src) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

def save_config(cfg: dict) -> None:
    """Atomic write to runtime config."""
    CONFIG_DST.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_DST.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    tmp.replace(CONFIG_DST)

def _get_active_model_name() -> str:
    cfg = load_config()
    return cfg.get("agents", {}).get("defaults", {}).get("model_name", "yzma")

def _is_local_model(name: str) -> bool:
    """Return True if model uses the local llama-server (not a cloud API)."""
    cfg = load_config()
    for m in cfg.get("model_list", []):
        if m.get("model_name") == name:
            proto = m.get("model", "")
            return proto.startswith(("llama-server/", "llamaserver/"))
    return True  # unknown → treat as local

def _mask_api_key(key: str) -> str:
    if not key or key in ("local", ""):
        return key
    return key[:6] + "••••••••" if len(key) > 6 else "••••••••"

# ── Chat ─────────────────────────────────────────────────────────────────────

_history: list[dict] = []
_stop_stream = threading.Event()
_mode: str = "low"          # "low" | "medium" | "high"
_active_model: str = "yzma"  # set from config at startup; updated by set_model command

def _soul() -> str:
    p = WORKSPACE_DST / "SOUL.md"
    return p.read_text() if p.exists() else "You are QClaw, an on-device AI assistant for the Arduino Uno Q."

def _stream_chat(prompt: str, ui: "WebUI") -> str:
    """Call llama-server with SSE streaming; forward each token to the UI."""
    messages = [{"role": "system", "content": _soul()}]
    for turn in _history[-20:]:   # keep last 10 user+assistant pairs
        messages.append(turn)
    messages.append({"role": "user", "content": prompt})

    req = urllib.request.Request(
        f"{LLAMA_URL}/v1/chat/completions",
        data=json.dumps({
            "model":      "qwen",
            "messages":   messages,
            "stream":     True,
            "max_tokens": 2048,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )

    full_response = ""
    with urllib.request.urlopen(req, timeout=1200) as resp:
        for raw in resp:
            if _stop_stream.is_set():
                break
            line = raw.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            delta = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
            if delta:
                ui.send_message("response", delta)
                full_response += delta
    return full_response

# v3.0.4: ANSI escape codes used by zerolog to colour the agent's stderr.
# Strip them so the lines we surface into the App Lab log are plain text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

def _forward_agent_log_line(raw: str, subcommand: str) -> None:
    """Send one (possibly ANSI-coloured) line of agent log to the qclaw logger.

    Used for two streams in v3.0.4:
      - non-JSON lines on stdout (agent zerolog interleaved with NDJSON),
      - all lines on stderr (compile output, openocd progress, etc.).
    """
    line = _ANSI_RE.sub("", raw).rstrip()
    if not line:
        return
    lower = line.lower()
    if " err " in lower or "error" in lower:
        logger.error(f"qclaw[{subcommand}]: {line}")
    elif " warn " in lower or "warning" in lower:
        logger.warning(f"qclaw[{subcommand}]: {line}")
    else:
        logger.info(f"qclaw[{subcommand}]: {line}")

def _pump_agent_stderr(stream, subcommand: str) -> None:
    """Forward the Go agent's stderr to the qclaw logger one line at a time.

    Pre-v3.0.4 main.py used stderr=DEVNULL, so the agent's zerolog INFO/ERR
    lines (including arduino tool output, openocd progress, routing errors)
    were silently dropped.
    """
    try:
        for raw in stream:
            _forward_agent_log_line(raw, subcommand)
    except Exception as exc:
        logger.warning(f"qclaw[{subcommand}] stderr pump error: {exc}")
    finally:
        try:
            stream.close()
        except Exception:
            pass

def _stream_qclaw_subprocess(subcommand: str, prompt: str, ui: "WebUI") -> str:
    """Run `bin/qclaw <subcommand> --stream-json -m <prompt>`; forward NDJSON
    events to the WebUI as they arrive.

    Event protocol (Go binary → Python stdout, one JSON object per line):
      { "type":"token",       "content":"..." }
      { "type":"tool_start",  "iter":N, "name":"...", "arguments":"..." }   (agent only)
      { "type":"tool_done",   "iter":N, "elapsed_ms":N, "message":"..." }   (agent only)
      { "type":"tool_error",  "iter":N, "elapsed_ms":N, "message":"..." }   (agent only)
      { "type":"error",       "content":"..." }
      { "type":"done",        "elapsed_ms":N }

    Tokens forward to the WebUI as `response` events (same channel as Low mode).
    Tool events forward as `tool_event` events for the frontend to render.
    """
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{ENGINE_DIR}:{env.get('LD_LIBRARY_PATH', '')}"
    # v3.0.6.3: shims live under /tmp/qclaw-runtime/bin (extracted from the
    # embedded blob at startup), not in /app/bin. The Go agent searches PATH
    # for arduino-cli + openocd, so we prepend the runtime dir; the host
    # bin/ directory (which only contains qclaw + qclaw-launcher-tui in the
    # v3.0.6.3 layout) is appended for any other tools.
    env["PATH"]   = f"{SHIM_RUNTIME_DIR}:{BIN_DIR}:{env.get('PATH', '')}"
    env["TMPDIR"] = str(SKETCH_TMPDIR)
    SKETCH_TMPDIR.mkdir(parents=True, exist_ok=True)
    session_key = f"webui:{subcommand}"
    cmd = [str(QCLAW_BIN), subcommand, "--model", _active_model,
           "--session", session_key, "--stream-json", "-m", prompt]
    # v3.0.4: capture stderr instead of discarding it. The Go agent emits
    # zerolog INFO/ERR/DEBUG lines + tool subprocess stderr there; in v3.0.3
    # they were silently dropped, so users couldn't see compile output,
    # openocd progress, or routing errors. The pump thread strips ANSI
    # colour codes and forwards each line to the qclaw logger (which the
    # App Lab Python terminal surfaces).
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(APP_DIR),
        bufsize=1,  # line-buffered: deliver each NDJSON record promptly
        text=True,
    )
    stderr_thread = threading.Thread(
        target=_pump_agent_stderr,
        args=(proc.stderr, subcommand),
        daemon=True,
    )
    stderr_thread.start()

    full_response = ""
    error_text = ""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if _stop_stream.is_set():
                proc.terminate()
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                # v3.0.4: the Go agent interleaves zerolog lines into stdout
                # alongside NDJSON events. Pre-v3.0.4 we logged each one as
                # "dropped non-JSON line" truncated to 120 chars — useful but
                # noisy and lossy. Now we forward them full-length through
                # the same pump that handles stderr.
                _forward_agent_log_line(line, subcommand)
                continue
            etype = ev.get("type", "")
            if etype == "token":
                tok = ev.get("content", "")
                if tok:
                    ui.send_message("response", tok)
                    full_response += tok
            elif etype in ("tool_start", "tool_done", "tool_error"):
                ui.send_message("tool_event", ev)
            elif etype == "error":
                error_text = ev.get("content", "unknown error")
            elif etype == "done":
                pass  # caller emits stream_end
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        # v3.0.4: drain the stderr pump after the process exits so the last
        # few lines of log don't get cut off.
        stderr_thread.join(timeout=2.0)

    if error_text and not _stop_stream.is_set():
        raise RuntimeError(f"qclaw {subcommand}: {error_text}")
    return full_response


def _on_prompt(_, data: dict) -> None:
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return
    _stop_stream.clear()
    ui = _get_ui()
    try:
        if _mode == "low" and _is_local_model(_active_model):
            # Fast path: stream directly from llama-server with rolling history
            response = _stream_chat(prompt, ui)
            if response:
                _history.append({"role": "user",      "content": prompt})
                _history.append({"role": "assistant",  "content": response})
        elif _mode in ("low", "medium"):
            # Cloud model in Low mode routes here, or explicit Medium mode
            _stream_qclaw_subprocess("direct", prompt, ui)
        else:  # high
            _stream_qclaw_subprocess("agent", prompt, ui)
    except Exception as exc:
        logger.error(f"chat error: {exc}")
        ui.send_message("llm_error", {"error": str(exc)})
    finally:
        ui.send_message("stream_end", {})

def _set_mode(mode: str, ui: "WebUI") -> None:
    global _mode
    if mode not in ("low", "medium", "high"):
        ui.send_message("command_error", {"command": "set_mode", "error": f"Unknown mode: {mode}"})
        return
    _mode = mode
    logger.info(f"chat mode → {mode}")
    ui.send_message("mode_changed", {"mode": mode})


def _on_commands(_, data: dict) -> None:
    global _history, _active_model
    cmd = data.get("command", "")
    ui = _get_ui()
    if cmd == "stop_stream":
        _stop_stream.set()
        ui.send_message("command_ok", {"command": cmd})
    elif cmd == "clear_chat":
        _history = []
        ui.send_message("command_ok", {"command": cmd})
    elif cmd == "set_mode":
        _set_mode(data.get("value", "low"), ui)

    elif cmd == "recheck_daemon":
        # v3.0.6: user clicked "I did it — retry" in the WebUI banner.
        # Re-check the socket immediately and emit the result.
        ui.send_message("daemon_status", _daemon_status_payload())

    elif cmd == "get_models":
        cfg = load_config()
        models = cfg.get("model_list", [])
        safe = []
        for m in models:
            entry = dict(m)
            entry["api_key"] = _mask_api_key(entry.get("api_key", ""))
            safe.append(entry)
        ui.send_message("command_ok", {
            "command": cmd,
            "models": safe,
            "active_model": _active_model,
        })

    elif cmd == "set_model":
        name = data.get("model_name", "").strip()
        cfg = load_config()
        known = [m.get("model_name") for m in cfg.get("model_list", [])]
        if name not in known:
            ui.send_message("command_error", {"command": cmd, "error": f"Unknown model: {name}"})
        else:
            cfg.setdefault("agents", {}).setdefault("defaults", {})["model_name"] = name
            save_config(cfg)
            _active_model = name
            logger.info(f"active model → {name}")
            ui.send_message("command_ok", {"command": cmd, "model_name": name})
            ui.send_message("model_changed", {"model_name": name})

    elif cmd == "add_model":
        entry = data.get("entry", {})
        m_name = entry.get("model_name", "").strip()
        m_model = entry.get("model", "").strip()
        if not m_name or not m_model:
            ui.send_message("command_error", {"command": cmd, "error": "model_name and model are required"})
        else:
            cfg = load_config()
            model_list = [m for m in cfg.get("model_list", []) if m.get("model_name") != m_name]
            model_list.append(entry)
            cfg["model_list"] = model_list
            save_config(cfg)
            logger.info(f"model added: {m_name}")
            ui.send_message("command_ok", {"command": cmd, "model_name": m_name})

    elif cmd == "delete_model":
        name = data.get("model_name", "").strip()
        cfg = load_config()
        cfg["model_list"] = [m for m in cfg.get("model_list", []) if m.get("model_name") != name]
        # If active model was deleted, fall back to first available
        if cfg.get("agents", {}).get("defaults", {}).get("model_name") == name:
            fallback = cfg["model_list"][0]["model_name"] if cfg["model_list"] else "yzma"
            cfg.setdefault("agents", {}).setdefault("defaults", {})["model_name"] = fallback
            _active_model = fallback
            ui.send_message("model_changed", {"model_name": fallback})
        save_config(cfg)
        logger.info(f"model deleted: {name}")
        ui.send_message("command_ok", {"command": cmd, "model_name": name})

    else:
        ui.send_message("command_error", {"command": cmd, "error": "Unknown command"})

# lazy UI singleton — created only when APP_LAB_RUNTIME is True
_ui_instance: "WebUI | None" = None

def _get_ui() -> "WebUI":
    global _ui_instance
    if _ui_instance is None:
        raise RuntimeError("WebUI not initialised")
    return _ui_instance

# ── MCU heartbeat ─────────────────────────────────────────────────────────────

_tick = 0

def heartbeat() -> None:
    global _tick
    _tick += 1
    time.sleep(30)
    if Bridge is not None:
        try:
            Bridge.call("ping", timeout=3)
            logger.debug(f"heartbeat #{_tick}: MCU ok")
        except Exception as exc:
            logger.warning(f"heartbeat #{_tick}: MCU ping failed — {exc}")

# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    global _active_model
    logger.info("=== QClaw — App Lab Edition v1.0.2 ===")
    logger.info(f"app dir:    {APP_DIR}")
    logger.info(f"home:       {QCLAW_HOME}")
    logger.info(f"runtime:    {'arduino.app_utils' if APP_LAB_RUNTIME else 'stdlib fallback'}")

    bootstrap_workspace()
    _active_model = _get_active_model_name()
    logger.info(f"active model: {_active_model}")
    ensure_binary()
    _check_arduino_daemon()

    # v3.0.6: repair flattened SONAME symlinks under engines/yzma/lib/ that
    # GitHub source ZIPs corrupt during archive generation. Without this,
    # llama-server fails to dlopen its companion .so files with
    # "file too short" and yzma inference is unusable on a fresh import.
    restore_flattened_symlinks(ENGINE_DIR, "yzma engine")

    try:
        ensure_model()
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    start_llama_server()

    if APP_LAB_RUNTIME:
        global _ui_instance
        _ui_instance = WebUI()
        _ui_instance.on_message("prompt",   _on_prompt)
        _ui_instance.on_message("commands", _on_commands)
        # v3.0.6: start the daemon watcher so the WebUI shows/hides the
        # banner without waiting for the next user prompt. Also push the
        # initial status so the banner appears immediately on first load.
        _start_daemon_watcher()
        _emit_daemon_status()
        logger.info("chat ready — waiting for messages via App Lab UI")
        try:
            App.run(user_loop=heartbeat)
        finally:
            _DAEMON_WATCHER_STOP.set()
            stop_llama_server()
    else:
        # SSH / dev fallback: simple stdin loop
        logger.info("App Lab not detected — entering stdin chat loop (Ctrl-C to quit)")

        class _StubUI:
            def send_message(self, event: str, data) -> None:
                if event == "response":
                    print(data, end="", flush=True)
                elif event == "stream_end":
                    print()

        _ui_instance = _StubUI()  # type: ignore[assignment]
        try:
            while True:
                try:
                    prompt = input("\nYou: ").strip()
                except EOFError:
                    break
                if not prompt:
                    continue
                print("QClaw: ", end="", flush=True)
                _on_prompt(None, {"prompt": prompt})
        except KeyboardInterrupt:
            logger.info("interrupted")
        finally:
            stop_llama_server()

    return 0


# ── Embedded blobs (v1.0.2) ────────────────────────────────────────────────
#
# WORKSPACE_BLOB_B64 — base64-encoded tar.gz of the full workspace tree
# (SOUL.md, IDENTITY.md, AGENTS.md, USER.md, memory/, skills/). Extracted
# to QCLAW_HOME/workspace at startup. Every entry is then symlinked into
# APP_DIR/agent/ so the user sees the entire tree as editable on the host
# bind-mount (sketches/ + python/ are seeded empty for user content).
#
# SHIM_BLOB_B64 — base64-encoded tar.gz of bin/arduino-cli (the Python
# shim) and bin/openocd (the v3.0.1 wrapper). They are extracted to
# SHIM_RUNTIME_DIR at startup so the Go agent finds them via PATH.
#
# The blobs are NOT encrypted — this is the "casual reader" obfuscation
# from the distribution plan. The casual user opening the App Lab ZIP
# sees only agent/{sketches,python}/.gitkeep + python/main.py + the
# engine binary; they don't see the workspace tree or the shim source.

WORKSPACE_BLOB_B64 = "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"

SHIM_BLOB_B64 = "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"
SCRIPTS_BLOB_B64 = "H4sIAAAAAAAAA+Rb63LbyHL2bz7FLHxcAtYkKMmWvZEtnZIlea2sLGkleS+RFQgEBiRWuC0GEMUoSp1f+Z1KnWfIg+2TpLtnBjeStpzdU6dOhWWLJDDo6enr1z1D4eVhVojho7/haxVeL19u4Pvay43V5rt+PVrbWF9bX9vY2Hj28tHq2vrz52uP2Mbfkin9KkXh5ow9cnO/DJN06bjP3f8HfQml/1+9yJ0O1CIHvsvjNLGz2R8yB+l/Y5n+X8C/9Y7+X66uv3zEVv+Q2T/z+n+u/8dfDUuRD0dhMuTJDctmxSRNnvUMw1hkEey3v/yVTVJRDEToc1akaeRN3DBhWZ7ezliQ5uz7XXiM3TyzV+1nT+1e77RMBIMniwlnO5IY+wD/v18R7P3JB2amZSGJ4YAsY4fuiO2l3jXPmXATf5TeWgzee/w2SwUXrJimxAIDnt08hCvI1JVm1IvCKxzPrtKMJ6nnX9H99AbofTg6+KknkHYhWBa5HvdZmNDsX3MYMPtasa/5COMszQvg9OrK9lxvwodXVz0/zLlXpPkMVsfYzbq9bj9jv/3nf8tFr7MRn7g3YVrmm7QmJblRWgJTRQqy4CwIb2HqnGcpy9xiAmTG4Q1PmFsgP4UbRawIY26zg4BolAK4l8zAcy5L+FQLmuciBPJhUqRAxmV+GAQ850nBKj6Zye2xLdlba3Bq9ZsMXvOsYNM8LMJkDJSAU7x5fLhHfIIMpOBItngHefDSpAD183xFwCNXV0M3y4ZKUgsjCtK4umJTVzAeZ4USIRnLErkJz01Q/n/6fvdw50dn5+TkzNk7OAUips8Dt4wKmvk/hsq4QHXi6spipE8Q9A1nggOfvugzUHRShAHajJQerkyw0QxIZDkXPPE4SwMgh/5AC4B5nsJ3IBCEY3nJll/sX0SaXF31SSAic6cJygC1G4Wi4CAUWEbOXZ9l8BFnstkRyEyqUTA358wtCxBNKDw0T9DsNCwmYaLI4MpRrzy/caNXQCGGUX71PAiLnCbMmTZpL+JuAkPKzAYaO2BFmhXQ3gQnJMGGwG3hTYZANvTdAs0nSseh94px0BzN7bk5uhZQCYFuOk1ABuh0Dq4DZCJSrW34gibMihz0FElqOUc7Ql8lIwIqXpqjMUrHbTrQG+65YN2Vx4Hg/UEMvgLTEjcwBz6AriFnhAmVzyrWepUVSntWdhoK4AMouKMIHC5PY3BB4BOfBOEXm2h5TDIEr032Gpe2/VnrpadUYIKnHmTxvd458FWxKYOnmIQxM6WpNYMXWBSagTJCHcQgpgHXPeXDaCXgqzA3zy0Mu1OgoAQWJjepJ/VA4gc5KFdyMRDz3j+fHR8NwNRTn2LQryUX0quzMEOdAavgC1magFpMUfgQoNmQwQee5/CB34ZFDx+22Mj1rnESVIQHQQvsHGNt7F5DDIEF8Fvu2btpHAN102gs0ujDwP+xIJhSpO4MVGuuBml9k3KV5MFMwLRhmjIUpOIeqdiVClVBFOzrR7A1zE5F6qURMyFoRaCCAThVDOkDoymKQ0pO2iUIzlLGcbr/PaN4eWd4sW9sss4a4Ov4Bi5fGF4aZ2HE8dpgEPw6SvCTbdv41jQRAZYJ72IYpKlxeb9klloA+KpnGfjrNIMgsmlWDOuRxiDAv+qCM87C1Le9YEy3PPwbJmHxCkX6igWRKyYU7LkTxu6YM567oO5lrNpgimz19ps1QmzopESoXsHZCazgv2AF0l5wEWr10m4aF9B+HLQfuLZ63+uddKLHJtjijOGaGY94jJkMIRrqWjuGDjzk4rgKiHE9lbDeHZ+d15kVozlebYRkCCSgZh5iLJW2Th7Qh7jRIzNoJDWYKxX2+2uwjHPIVyrWQTAtQgiu4CVpBEF4OuES36Dt9XIEPPitRkcS/sRgjmflyJNmzsA+0ynyhUGgFQAI78B/EsIAZgRrTerxPRhfhQUL8jbPwO7RAsEDQgHL8qK09Af4NUPwgowM0D+ZKPMAUE+PwAgnOKJNF9KctAqXSc0b5MuA1Op1AN9hVko19eFWz81HIagOEu25F4HX/SL9B+8xmSVZ4cYQpEB5sPoDhW0wlDExA5XEvsQ28P8mhOSLCu5dXX2qKhlo5xYTQGWIVKXrO05QFmXOHUelSJBgkhbErOj11DVM2vpzKvSnnOtPMnlU38oRSNHjohoJXOuPMrsjWtIXALJJXtBKolDjR4Ym3us9Zr/99S/wj+2SZMpcBml58R/lX6+nERjbonWZ4CBQOYQ55LoxL0wKCEYbrIHbiyI3cbg9SWNuWpBHjAZgM6yeZdnKn0wLZXXIx643g3SdjCM+IIdGkJRjIjDnQLdFUFlwcOMpJ2sC6Hp0+DMQIo9HTEM0CKxdh1kbes1s9kHwoIyohAHkgsgipy9ongLITCcpwNakINdOI7+Gq3bvcP/bnd2fHQw9zun+ybGzf/QDiKcjGSWUahQsund2vPvd/rlztPN+H+W2xRaWXQQijN7Z7s6Rc3B0vn/6w84hDg6i1C26ClDTtAZj3N2wVw3L6u0eH53vHBztnzonb3+iGTGaGqDX070PB0fHzu7hgWRlMd3GMMpPrZRo9Y5P9o+Od/ecNwdHn6KihqkMx9rZbNgAPkDy/OD9/vGHc+dMDt1CTLxk0Zo59Qgu+8UqLfv9zk8OJVpNZO0F+5qtra4/12/sMV57H75BjBEWM0A0WcNpG8tshO4hg5JiJqN4mUCUTMYQVikGSBu1vsC/Wzpwdg4Pj3/c33POPrzZfb93BizfSd+qsIb8WmZgBRorwCJcz4NKDrgYldJYv5UhHGNylAJ/ZNNCIkNTxnx0JCVwS1IdpbBgPQWgd16pCqYYE3AKyhzI51A+sSbfe/tHB5LtH/ZP35xJChAMawL/Jwqq0K1Zwhhar/rLCaosp+iBl4VQksDX+7YaOs9WajBrFghZGVBNN6/5AF4K3r0KEQouzRGQtV13sOv7zcGkA0NlPz1WXiyT+nJnfJlBicchafr8tvNQNs5dn9ePKCW1p9AXF0xR3Zqbor5TTXHf8CVlahLkNXDQ7/agz/mXjk6Vb73bOd2nGNgE03PDdt9+e4Yx424BvL6fG72zt3dKdmJUiBnFvXq7qr+BLJyTnfN3Dk2ec1u5tJkb/3qxM/gXd/Bvq4N/sp3hx8HTy6cfEX3/CbOFDpvO28Ods/mnSS1AAjsZCLEJf4kcqvY0iWbyU5Kip8jPWSkm8AcAGYxNALo5roBsVzh49xUzFD1ZNxDRV2ziRoWuH8IkSNlqPXBZVWH++eQ1IqLtJWuzKgo4Eqw+3wZh/VlJy5Llhh5CfDAA2a+ggi6h2piCbHpWw7re8SjDjsffHSv9bnP1ecCcKB2bsRhvIoSy2GCbHQGY2SRpZDmmwsC4WAQaLtkdPHYPphdEoOit87zklqKpyy1uggsS5T6r2jubhOtoKrghZwKUfSqbOqr8uhhCOXcJBZEqu3SBBeUGVeBVBWYjQEcSYYD+zra2WBuCAMaC6zbVeALxv9m+/xS807AkG2QCHFB+QoCyYtmCUUDkIuJJ+2lr87LXeAjGKAmEwiGh0eOm31jzCHJlteh3vMyxz+ARFlyR3ZSqrxpiHbOwY1ytushnNesgAqhImG/D7EDFbKyqweRbNxK8u1yzNdL0EUCDXxj4TgsxLKQaYBywWmMR8crxKrNUjzQbmQsfl5/4LQIKdny2n+dpPqcIya6UquoockeZogNoCU3sZpMM5AKUdqkNi/17w5KVZGhodwKjBb0wZYSqeyxFDEUaxEG8cbF6qanhRaQIVesnQNXcXEFrMlFX6yt38OV+BadGshn2jwpCWbNGt7qydDRE5Mhi21tsXeoACPQlm2sghA5jHZixgLGVJmfEDbtT1CRfgETDLkMsS6PQU4JSpFDqXX3pvIYEpal1tDYXH3qkxwLQJ7+oRimd9hv6vWwEEGnJVfCR0/VpmIVNEgld+xgSTEmHo8k5EMfofs6xwdCMKLWcv9piL+ekJokERgtwxCVuHnH2EmLXNU/EKzYGjd5VpO6b8QptCmlT7+1z9DdZmfDbDHgEPQBgHaUCCwnIi2Olq9XLr/IO/TVFXywjX1OPQ4H1MBuodv4AG+NIvU1xnSguxDqfXwHQ1gK6W0hibgHP1AKCL1hAoNpDA4w4C5bw/FJ77yIs9oBVBNUqsPRPA/AY2jwzF9HrqnxDrcj7ghV5EhQNVMAQalH0/Cj1ZzpEvZAhKobvc3DOjnFfxsThVjMsxp9lA6anSfyUywBFlCgQEL5GSE3orIDAib6nOQsTh/qkWyy2x3laZqaB3w05P2IxmrZxG68ZFXs0YomqCAh/Xleq7QiEuBDgJ/ABbEwT1exj5dRTKbWKH9iW3mrCGb2eRrhqSVLDbiXpNql5kDHHK+05z2Rr+a79NPKsWscC4oBwA86gnMldiAa5ULwnfOooa8A3GxjEbegG322ifbZmNWN3ew9goX/qrQDlR7r9r2e+7DcTAHYwHdUBN7EK2FQdUFu+UZD3Q69oZetRGeACZgV389ydKcQwnaAvI8ys5ehNyuQaxiJpWKx3Y77Y2Hj2ooYYSi80ro2GRsDbdXUFprT5LUBM36SxLQoYumEAJFum+jwLgRWtW19LIlwCUA2gbjVHxsfEaHMVYQwYrLUpteBchzzCKBt7McJE0Qhk6WIziS6tNiBTeIqG4+bTHsfdkA64WsZ6i4FPTGxZuAhUFAd4Vj//oMnngYIAwTt6V3CRofRpz3CTbKVbpbgzZA7EbdK0fhlnwsThkN8TgS17V3hhuEVIEqE8KcOWW5SmURbB4BulnNbyyaiQM4gRppqlBVnf5JjgT8Ksu8AMCt1GxXhGrSDwGG8S4jkRk5rKz/+4zsMfUw8+Bo5PIOtL7vq6uadwoWzyybaTT1uywsspC8hOl9xFDyAYMRcIidLDfQ3qeWMAxv0v2exmJsLVKQQ+n4/K8RjSmwWyLiM/WSkgDuOGlwsum8otWaAFpX5SsAnoGIJdCdqYMbUrp06dPGcicTMxSXFXnw5mKJ4oQeHTQEW1MQSdZWGvqwC+rbYihzRw+LoQ287rkQuKd2O+PcSTAUgmTmmvUHKkN7X09vYE5dGAxbi1NeJQ0/FWi3SMpyhcDNt4EqRIkRKeqWBlRo+gYGS3S+D+nAHLBYMxmJjFUQiBDiir5XWki5uLj5V48ViHG03dmVDCDGsdAYz3yhyP74AM1amp97sfbNL9WSXDCI+14BZevkhOfUUTiNXHKeiokzqP8bje40Tp0Xbq/LOqpIWKXvdKGfexSQruk3CbnaW0LQIEplx2fdiE53iwIZ0KlFiYtA51Hezt240e1puDo2VNsKWNpGUNJIgOztl3++e773C7CXdTkCrr0pVtErmYwUf/KT62c7r77uCHfefgaG//J+fwePc7fKza27MPIbyZ3XEyzl1Q3wSLoUts991jH1oSx+re0SZK3XVt/3inOynkLOJ1YxUpeG6GTRX3Jg3B2BK9VQvoawqgw/XyFFASNvLBeoSQm5sySKv45Sge0sTRS+/UbhCs3amzqC6nzfhmqodaS5sdKdPGSPOUxbxwH+Sn0kdtdZ6C8op0RC0QCktyqz7RbkMVIPKAOWzK6+CDuRqiF9JqBLVQ7pSrY27gXc3tdH1C7opOqMgTBLAE+bhl60XS+2NJB2qrjNO8dEYLNFBssosVJcyVPrNtu89W5GEJ2x62zOro6Gjlsgk5tahxTfqzLir1Vs7i1FsvE60GDKS6is0olD8Mx+VBWaMpW61uk9tsq7XbaPgi1Sn4T3u5zcZgE0K3AQwQrp6sWlkUG+edUAHtejwahDWPc1rrrEbPDatBIfZ46mcgXNU2OwdhpG7fhurkItkwhvNSyGT1uqa0PWx8IWa3cbicMkmpQyaARXQbszFyHKUj0/gaxxpWq+Sonlqu5BhCsYNMbdWjsZclIQ9OR6dBwUsD/GAaT35+Ej/xz5+8e/L+yZmCRpVDbdWKw1afjt3wkRwTPwXGXSHunbvOUu8X9Cw1WTvGUzAAszA5Ceom9/EsGO4uXKvmsn4GzROXEyaLVo8vs+J2iEOkVdgy4ksMi1epOpFfGyZIsUdvw+mXUa3Z2Oz0hvvtgfWa1cj6QneojuAwsGmhxG1nqPJk33Hx8FMhOrfpSNim+uZAIYNloYNXa8/tPoJJkPvyKYLGiwY4VI5vykq1un9ffWoK2kDJ6W6vlHUBrDRROY7o4+E6UPLWekPotA0RGCpxsYu7Sr7Sci5r+5uzKkqARtuXA6OVLO4qM6Mnhsai1jOeG4Irm8uYertzcLiIszmGNtkd0LlvFHxz4YLyxAJw0Ji8dfOiMwciAr2m6pHHUB2HMZ4eQUwK66bj65TjVgDQYYpPsDaRqRaAgF09KotrLHTb82LNOw8n2s7Wvm9naWYmqHcwgLxLzmq1G6oVKITRMtyH9PXrti+u6MaNSmrGyTOSlLgT1m3vV9m/avRSPOnLjMeTMgY0KLeuuukOd5f0AUxKSCFglTX2uu4TL2wMUEqmoZfLs6cku9XNoZqELbIoLExjy8CezcVaa99J2pWUYezm144sHBpIjZxZdt4fAtYo9MpjlJuIw3qdmhskd5zgIbu6DtE9cFXtyTJmOXyTHCrgti/1rpCbBDqYdiuIS/v1lFuxJUeQQqF/1ZmUsSlK02tZGtABeIKrlZGBgiOB5wazUB1D1kFVUq3KF6RURZuqapWn5QV231VVgscMO/Wo3q6EmTPJEh18TsNELW5FrnulKunwJxlFGyaCaVTSRxi3igaLFlaFcrC4uc2IZie4woGLusGNwsgWHKX0gI5w1c2tKrtuX1c1EnHMp3DfPI02EFRgSrVMtAFsMsLe7Qrr2frq8/Vn68+/eSnlhgMd2ZjeWgQV1WIxJ7e4bOOpmspiGWiT3GqMVCJYtR4a3BtgqhM98bSZnqPiqxqucCgaBPJaZbX5DV+du3bPl+RTLFI02YB+PIRh8E7Pfd+nc4wZbj4oW53LZ1pZu2k2+4RDtTwQCsvqsD2i2bovpIjR707keWNsNYEbFzwAr8HOR6IaTLozRX0h6qCIVkcKs+Q81MSGZVPv9Y70cvDYfmAeRrbvzwPKByKMpVqi0lS2sFHIKNcaXSiJfZChtkJf0v5QRrLRAfUlSJNLieAo7ZuLsdu84BQibvSBKypyyQTzOhD6okKYl3hpizr3i0ZIiImAps7/1fVGaJojjFj48mHFS2vlX4JNlf5MpcD+ws621e38Sr2c8lEZRv6yuJ/GIbYMZlIv8v5DiivdFZzXUxFnuA0oMysagSPKIAhvTcOGW+39B7iA9q/YgfoaDybDNSq5RNcl8E6ZyJENuHnK8bA+/k4Msg2nZEn+rtYoyvwG7hIExeuyuGOqoKafm9UINBW2ZqYF1vs4udUcpje14HpfrXa+kFjqUQtQiPx1TLtE+LIKYflsShSBi3Gx4bodwNs2+PowVhfwxrLnqFJZbnwcmc2zbB/xXGTtMgoe1ikaNRE3tmwamxQnPB/odvY0zfH3sX/3LYkHHWCbAMSKlmwaLTp0VguzWNXRI04hxKZJ6Cnz9mLcT1J4bAE+hpsXl0t3jAqkCVHXrI6WNzPnrxjp5jZGW86JgzqpPhR0PjYBu4e7fbkR1qnD5nfR+p02Br4av6Fq/4AqdiOAAHH9q72PSfcHVS+et5sE9+3OXRMW1GIEavIQPf78rN890V89q/uYjQfol2l9EPXchm5THOrBPqnH0gLDTbvGKLcvfapubc53NP8IIbaOALnEElakMDcgKfFRHzBv0fodEgZxkJC32mLt1pC//C97z7aduLLcu7+C5ZmcscPYEhIgmB0nQSAuAiEhxHX2xBt04aYbQghLPs5jfiAPecnX5UvSrQtIIDwzZ+/kJGsdPcwYqbu6u7qqurq6qhrSXKr33BEN5yZYUOnSjBrKO56iqaqQJu8STmQRbGgQAeDiBpGfRPd7KIejC850z4g1hxUvkf122YeYdh89H8JzxS8nHem0Nc2QVJ3lKegkrEP1OD7mUAN+PIMmxA4BD35sn5Z5sJRzpTVUb/3V4JcggmK1OwNl7K3TAWIQVm45J306iDCKYvph8Gy4Z4W7LyvZr1Rvgx855jnZDFJdDyj/v1UQEpxYL4+NJC1r1LiaalgDdaE72P1ZryMPFiiFrx0pXDL6t7OuyuJzIJ++xhwlvwFSOjVw4jNZjXFa5Mh/7rsRVft8wXEJ/8eTwDpzIoqev5j7IhvM/2POi89LzGIB5yXmTgWFPFwVYvOzk/9QQa7c7vWNDg2msDOv4B9Aib97QQxnkBpT1wg+GP1xdwefCzaFMaNw+3aMHn0EoujuYmgRsMupCMb8FAPAtTgqtRzAxvfLhfrO01HfuSwiLmVx85RyznCOsJ15cfgCn9M8BeN/DH4/SnLci8ePdfJ3B7f3KQvtcXZPMMDvn4MRn30fSDDH8M0ZKZyIMxCLdSBDu4Zdh8aW9O3ED2LgNk2JiFEupNbAwTEw7ABBDEkt3H18XwfJYcR3hhKjCCGYe+rFXFlgh/M/MxZIYBI0ZIQr5OuR0t5+QKfKYedcemIuyU7ZA2QewN7gWAQKUjRuVUW/+SI6Ulj97dSnf/p0zuU1tptu09Gkp2BYsJNPrxBLXz8dO/zp2xvo1dOrZH95zClvu6D9J9/BG00IhpOWYrxvjPcN0AlT3KddDEqaUTqm7hzkzBoqtAfLsOXIws1UB75tG5qlYqB+wAp4MqlHKWYyoMtqDMjR5He3A9qOCHMHhI6xgWfI/VHJiVQwZWVph5kV07t+YLlOU37eOz1JUX8Ct8SvMWr79js1osCS8F2F6ERracsc/BmW+W4HoiWJ51n+fWq9VMd+YI29vr6GrnJ+CEZMNCVZl0Bjp85BwwogBVWNm73OZ9LfhouqsYsHG10LM4LPmb9mYAoxjVNaj6yfLUn/P2ITubkRAUHuMjzoYyfsYuxc7piiKMgJFvrxJdIPffbDFoJ4GHhqZgYvdrZh+oEF/tGoD9E3sTzDGM3n57udrCqfM1ftKfCBRR595D35BZMfYMci63Nk4wy6BC2bsWwFZ9Vgv+Jec5Qj63Zscv1Sz8H3L7FyQpAhK7CgRR5Ox3H5x6/+oK4N5Njfx8B2+TNeKhdkCQ9ykkAjYytUZ88+xW2zKe5MycIXptnvE/sJkgVdkp+SlrO78Fel/gyT2n2OvsIZeu4LPFVh3hloABNKf8k/bUv29v5aN1NlYyiewBagFjlgHEns5ICRaCDF/wI+Z5uNi14bu0dxqRnSWXc/Z1CjWER/ArdnaAiEyF3p/vxDzFCYe0RjMh3SJmTKuxSyjOEkAAyXvx/AyRkyAn8P/wwxYjCf5MDUp5Bb6loJn0DiP0PyCcYUiJS7y61epDgGdBSO+ypQe6XHDovSMX91KY2hqFKtUpxwnXBSyCR6kvEhR0yciZbLXZdfyj8OeQpN036szO4pXB6Pnbj/HHqLPyVOxqLnPvAOuTs3fqTMRIj78xXvEmWXVRME+04D74ubv6ilcIog6ZlAWcykTFBc0YmL+MRaEE5EiPNgMYsh9rN/Tv+khL4D523cpi8iR+QfF4vQJv4M+/v+mgF5yWekm2ih7gfKQ8xnCdCC6Lt6xhNFBiv1MQHSbAFjvezoaDC+2u/eXaBnpun7A7y/SEel4JFh+GeywDG5Y+iOHngLxbsR+KWf+hHlOzrhB+DBr/ft1Ljv7nx874uOOJWHBv5EF98PaAcAr0v1yAsucqlNggV7SR/uj0n3lPbgRkQK/Mb8di5W/PNMACnSFZoxZpJ0J50yVF14DsI2Y6QYks81OoSJpHzzqD/c46wkto59qFOd8nfCgQRU6Ce0AnVg9keg50iJsfpKGxjuCZlHEPcXY/cLh3GWQZeu7nv2OtQWgrUsLqHvTlmFZjFeuU8R2snefIXFvj0muPayjiSrqfWSiAKS4Dqm3kVT2qjPEHPGatcQFKHnAj/HVL1B/jE7439/S8PQcTvzlODiu0sLdLx06jp0DeEhn8E3MXrd69coNVoEwt3VAZ6EwGG+Jhj1LQx7ek1kHQvMI7FxpkWIHjt6YpqzFdX3HlFl2bxLQI+nfGFgdsK/+rbvjz03h0EBgYK50kNFLJyM1MzcYRLlKFVmiPWwRuwE7Esm8xo7T3lLFjwGOvvPa8zAf1YwUhDDgjFzX6QTADZKy4v3Jca5l7mz4+n+oJlqZq/mKxUmUQCKf8x6FG5gfefFtFbiyQTPSFm9TCyo+W60Z+n5ngI+vb1Y+c5WDJ85U/X/UYXvtrqNLyHHn4LzoRssYMONnJCZviw9Jp7OZDPXkk7HRcePiYyrouJDhlSB2ghlIuRgPyomkS/Vz2YKrYRhGuhQ+7q+nl/j8TNWxovo5ZatLbt+3rkWTHpt7U07Ba23MOuTnwwWpn6ChtV+qwFkwpk4PY74nQUmXLrRgF4jEfcUaYN3kaKXEnocFvbPdRKOSO8M4Ue7D9enI/5X+rGtoyR/9P3oL3zAvjfk43CTY4c60LPvKvvsW2Ofn/1wpOfQHLtzd9AMYt8F8uj+5q99Y8Hfnj/yiTLtnpLq/vFtfOf+j1yRKJzd/5HPF/G/3f/xv/Gc3f8xn+2WQK0KFqXkZR8hhQC9Ecaih6mcg6CJ39I0kt+OGZ4fHnxflz3YAkcx7f4NIADMHTQT6W6mJs9Xs+AU9D7yUo3ixhP5uMM2fgtcdYBkBECCy0fO81iHUhD20DL2i2V0MAbb+OTfDaDGPYMAnGyGBeoP0HcefX+g6AKK4IhL9R1lgfr+nRtzAJww8mUHoxBOyeJmYcrVIx6DoP7BbrYAS+WHjB+6sMz8Q5BB7sGPRb3kzpi8/3C8KyQbqH1wq/PjgB4eQLeDenFY4ahhxsifgXVMDwphBelMQ1A/A2Upq6aPlRHcufnZGEIPXLBbvgMT+K/IY4B3OIvIZ1+bcla7FbzjIUR7mHMbhnMGaA0nyjRVQExXHj9noTqDCUghgZ/VejiOLfmA3gDtaaYiR60taiY8GohDOieUBCRtr9qrQBlNkN1VAA9nJJHGa0mOrfgH8+G7ADMPPp2fVU3dXUT52WHmPR1etyBFRAddxANYLTuZVDtK9ZGWIDE0pSVubUEiQDByDciEIJ17xlenAEnNDbgfD9sA2r0fmpdeJWgxbOkOfgiTANxDAOZKDILQoltswpzvH3xEBlewZAo7/y/o0WCBXUJ4jH3OwDAV6YO8N/yrM6AL+c1Nv8q3OAGqjU+3H+9EKQP+BbTohyTdfnwlYaavPjvgq9RX9BvYXdxm/vSnjHmQ7m9v/M0Lz7LCseYJGPL4GCsZbFIGXbjtAoVf41uX4O2Xh49NlqHi7PJ2e3PDsDVQIcrke6MEyTch69x+/OfbX4BS6it9Isy2cfsRfLrNrE5HMieRcQ9+JWA9QIFxm/nll1jho0y4jwqfkggnSi7/HLB+Uj2HNxk86JlP2GccNT+B7qC3mT/7bz/tkH/5kPn1Ff2c+/UNQT4lqkFlNYPG4f/9mSFcXBqZ4DwdJuwLnMjAUPcwf8yXDBw1dGVzQ3kEZugf/4RdNoFFTci7mXgj+QeXMNRKBYy7AwsbTLnr3wwRXqHiJwsN7x1R76Ha/TXzYGdymW/Qk1QOsEyyndrT7a8ojn/NaWA+ai0m/InBnw2eorrhC9x/M6Fg7q/oFa4FHvE8FUHBfTDVSeVYrQhf8FSfEsI3KKgkRylHgw5ELZ+ajDXlVw8KBXBP8ABFrW5uDBiuksm8BvlplcxtJvPx1Yfz9vW//vPfv3189Yu/Zf4O+gaBic0BCG83QArBE7VkNdgCqPVv/3GtFuS6i1qgf7Cp1EpwNmHFm6jCrzpgSzDst/BGrZxviYiUnxO7R7AAoGPdj68AT2+ZUNZ8yYB2YsXA9yNPX9YBQgVuiL8k6gS14px8G7NzhXG4GVmbyxLMCnNSz8L1NHDnidf/XXaxQNKQHZZ8Jov5p9tmfteqRE/2ZT7ClTlvdjAGL9Qb5Rm9GC4qbUFzp0W9tyNoCitseXowGuSx3rDW21QFvsVXq9V8n20BdY3VFanosVll53oeV0MYB5tliw1Pbm/MF3q67kzHU5xqGc19cb/dYzlpaI20wXSLNpVyVunqRZkrZxc45nDdspXDS2NuQYy65fkoVx6PmBHu9MaqTTjOvFSRnDyLMKritFDxpdNorle0ithLid3ns2UC6etZjeYQB2eqhV23x3ZEZLlzVyhCVnTqwGOsg5mz8sFGiDGXM0uO6yCFUlGc13JrolBeLxQBQV6yY6TYoCyhwI3cSnnO1V70litLMwOZcD2L5BzvMC3OsjvNazdGGq8qhjwtDcQuQpI0Wly5niaUCprAGLJa8oQ1k0fU9qA0QdYIPh4VrLVXw5C2Ltlm1gUQ1+ON2BtKXLXYahXk3gRDuv2up2t9xigghazbmQs12t63J4SwWReAotVm1Ap9KJU3daIw0W2niOQWRaR64MrrKTdqN15KEtvUhJ1QRG233wLa9NTrGeVlqUAsOuMOJ1OT+QEtVFaCs1epwVIpHFysNNRxrS3reAVfFdoFb0KQE0ubowxSaVf2K7HVqVMeoVV7Zam2tZZNWuhrHSeLNZUX2ihMiAYvaBjWZQ5e19QLsyY72Day0lTXqzm10JtqTM54wfMDbVXxKmMRzNaqz3hZsc6+yNnuBnXXbM82W6Uau+nq0+Jq1R+tTJrUmxWF7dMENuCJtj3r9mp1uXmwiSXiZg/5udwkCuslVn7RjCq6aaMz81AuLk2e7Ykz5iAibo/OTrZtqjGYk6JIj4sNS8maU5nLYXQWzdUauT677OgTzO42qCFNMjJfITZGf2Yzy3zRONTQVau+0unKfNQvsK6Y3TB0PzvmlmSPUvasVhewKqZ2X2yzrQzrxmDPy55b23Q2zbbaafYbBoa5BObabZM7sPy6MzyYoHyj5OCkbFE1WtHNlwlRfsFf1OHqMFUpeboxDImvV7tbbZ6t1fMHV9K9mvwyQCcNgymO25V1vYHsSHdqk/sVYVrCat4WhJbo4JQ3RouG1/AstuzqqL01KXEyrNm8vD9Q1bFcYsec6NVK+hYTmpQyyR4KhjS1xE03q5bRXquz6DuFoexthzLJoIt8dscZltLgyp2WMRdIUhB3TY3QDrlRtlBBFMFjqUJe23UOPWOnV5WeuF9aOjaaemVCKGi5PVFSmH1hWG2zQ2diWpWpuhnv1hw7IQd5ubdhqzO65XazJDtr2KhGzrmJNM3WSGRNFqwR7hEzTjhoTpkbDg/eeIIsxvqqi06XB8XKFfZlqcRkF4qztqYEncWFWRkfYH1Z2XHrKoOP7W1TyjO1RZGtLfbT3JwaWVOpgah7hZAm+f3WAlprjZhw5SGxd0isxOLOpJhbWOX23nP2WqMy288sfI7K5nI6INZ8Zyw506KFljGyJCoGatITG58ZPcnDR7bYQahJmVnWXW9EcN1Zjug5+B7H1pa9ptFVoexMF+TLYStJjRwjCxZNdvtSE1fHyLBb2AxmrpjLDdbm0Ol2XoSVQ22nQr1eL22wvkezkiNaFdS0pfpGtMbuYphXsm2d3tf2Xa2bJ9i1kS9uKo73Uh32tJauI9Sh6FULSMvmcmtx6uSFtsUrgixv85ohLgxNMxlPYiRj3OO77oEgymO+rox2tGrVBKuQF0tIvobk8wzdaNfbhklk24jX69r61F2scV6UtzsMG+daHlrG+31C3XSqolCVOIpkkG0RVTjTVd1CNss2nL15cKSu1a2YrbXR0xeVgzHIUttevp+fzblc3c1yuiXUmo0Bw5rkqjpd0+ucuTC3bqWzH6FmUeE3W5KuNa1GtsRiZrXbqXbFqlSo1QsquZ0cxojZZUqlGVPaNtz6dg1E1azS5JflQ3/Am8K4S4+rG47XhKHXWaNy74WVmY1T3NTtdW0wJTiqVtrro07eXnHLFpKbdzZlY16357I3ljo158ApbKPXnsuFeVZT+wfTGHCmQHZwYrRYVDBh6NA8JcgM1RR7qoe2S/qguuNqW7c7pzajhr0skeTuRTN3zaE8KMxmZHeqKB0aw8qd4bJhTiv2MjerrKSqpzkDui5N0HFvYBbaB8vs4yIprG3V6/Um5K7JdbrMfMUOyU2W62e96eTQHFXoVm1UK2HdNV3CKDNrVIStPm7pNLdQlkR+ril8tV5wR3mvovNLd0bqlWatwXUoijEna3zpoeuDOJgOvIo7btRJ1ujx/dzGHDK6ui2Z+GRdYkhOpknWo/SS6/FTqp+j3dJBOHCVXZvr1NodZ7nONwgX9Sb0sKMbc2xNVDvrntkb4RUK3eIoUWEtNrvwDs5e2ulCd5sDkrfQXiDuSCuz1tDRarzRmSI9fvBS2gurIkdgXQ3HSVvRLLrn6sucisl2mxBUXpp2W+psoK+cwdxTWNtS8DEizQaeO8Co+YbtLHNOY97ASWW66PSN3pZRivsZjbiE3panOjVcCDOeI5r18k5qtZso6zALd8rj2pTod6Z7epy3lmaNbjRHe158oUtEe6sMco0aUwGUzwwq/DLv9md1uWznvLFK6f3BzmMqPDavWy16Kzu5ZaM/QQmlZuU9qbenZSJ7aBHD/27vPZvdxrJswe/5KzRZ/SYzA5UJSxKomuoX8N4Qnqiu6YYHCG8J4nXPbx/wXkmpNDVdPfOhYyK0FSGJ5ME5+7i91+aV1pqSDBFCSlcH1b9AZCMfaQmdZaUIniUMxh0B9hcOvgHY0vQtCKQpmNf+jRYlLwnvc9zcz9ZZvqgnYLA6TTpyzMpfe6Tw3Fl0vbZoMD/Mh6oQzBsGUdxoK+pk35cZzs2hEgHy4cVzT8IPXU8ASO/uMLMA81WNeNI3B9q5TdPFHyPP4y51Tz9xUm7kEs5lHCNpNHTWw6sMWe7ornEschZveLfLJBNBAjofCfdyhjbYmFPqskf5oJPnk8s0x/GZZT2EA9SeO5MjjtQRYEX+oO9bqALJZYoGPxRoGDjJ9wPuYIaHzJHKoHpnb5gyxxecDzOrELemNRBzI7TTbaxNJz9Ji7hApcs/23vdPkmKOiHiwNZjDzix2cseLVzEB0b7VUb3oB3duetpw7GSiuZTvKWjvUdtBt4EGgcuAYrrZww478lWV72+oy56nwppPMcJ7G4DU+hOcdJI2UdpT4wHwKCetaxTRn+3zzYKhDFSNQ5pxSGmlzTIAs6iL5f6SEDzqVFzgBZPdtlm5jGdFUWD3iJRe1COw5faC+TJoUPCpX8gign3N8xPz4QvMCh4Gi9TbUWUWtfuMG3F5YLYC8eT6tNn3Z63hpmFagV2VAuYsdpk7hbJ5BorYXZB1lfo8nAov+xpFQlCxTmwIJClAIbC0JY1igyzpYuIvjKq9HQBrBqrykcJIF3htlwbxkNRzSM0RPGcU5yGPZec4jXlZOXL1Zpz5G5B8eyjUHBi7/0BBAovG5PuSdMTIvPhTPm0scfPa1DQoX+taVQ5veZzuUySc7bJZOGvRabvUwI7k7uUB6yVL+0QWYx7G++y6V/6FR/B+kREQLuhRnbG4MtyAUXrBnow2IE7fEHaCwCCCJjhtnE9QEFwtcKxJOCGVCQ3RoADo9AJ0F/PEAsBQ8HKO5Lv6jlDpB6pxQTVTvVyeYIUeIBGWekc3x40Hw9Mq0GMEirpZGUmiTmnLGcw/HDL6JbE7ryYmgOGcjouQYxBLjIAictTjLra1wQM4Pz23kNTcmCMhKk9P9jvzlCcc2pIoDU/xWBvEoCRgbV0XBHIOkqUGGg54H63WoYvHs12e24Z3hDH4otqYbD7iRm4xo245EDgLSCW9PmGJRZErzUXJ/RTx4qet+tHgbaAx1yz6dz7z+u22MguofWgOagO7wsZYIPboRbX5JuI9UEspPtC26cnFdaYe7eMsvN20HCwLbDv+CBcbrGaL6yenRT14rDxEEKZtHc7lrYZQUO5U5rO7I/a3hEkIvTLCN+vFdmbG54u1cCFyBUSCekAR7xQMIJAW13tXGdvO8D67TJdvQd53ncqIXyREwnHxX1A61Aac2lYbIxWHK67qFe8MVI3WRourgxZNMsjrJGdzKBW9aqk+bVqJHZxSUJgREYu80dzEu/5+RFGQ4m2dUY9PZXqQDngHNe/NYVy5RSrv+WZ1cwyiXkUGJP9Al+1CDXVk1wlM6rhi66B8lawD8WViyMFIDoW0GpUMZeHVJFtWfcYtnZOc5VOlCmGebV6vUmXDsnJJt53+ICEjwiqxkmflQVa5K5uqn6ZyCNNafpVRiQqiHRZC1HnMbvnavMeGs3K4l29UkFgUsypl1Z30U89yYliAQr27XSxYA5M0PjpPDgRk6b9vJDnzXyEfeXsvRGW4n499yHq11QHmZo1Yn2rFVdfAq/1gUfqifImOzBsQb5wZzpnpoexPzX/WbGxgZ+LpaOoe3jPiCuIVHZ6qawEr+inWJmSTcIGHScFLYjOtTxxjdD4DyUl8fszloyC5CGkfD6dUE+hUKloKvZCp/H3ed8MhMUCKovnLK07p7ueidmpQe6hHFFSjmjniauuMC3U5j+5SXKPuhXOvf7eJJtR3HLYc3SbLJEzFIyIMPY8dFSVKF3kVL95JMXdVLkLHnlycvZOh7PYT6saVQLzKRgecFOlzF/aZdfUS8SzBsB0pw1QbfQGN6pJbkakHxE2vR9bGswVAp7LwbrejU0/6tQOysE1OtV12pFnOQm3TPG269CL1Mp54RQO7nwH6pjg2a00QGlK9oc5wvsZhtLnAtXCMrV8Hmj6yUa03MYZjD9yox0NUbiHDut767prTUVNgWzRjuIxYMkhOAXe8uTqI50drokVIblhtQ+hZ05neNz9OVa5S6LfdUZxvX2rDJ1y90A8UfLgqB1K4o/J7DmQ2pq8v7kGsojlkdnQPozxSvcDd1scAHD14TyJlAuQsDaw7Dzw/AE2/MwZW5g3OBmwOwzC9mG70JYskvZakU8XPjNQIdKGYc3XKrbA6YD6K4y7lNl0AWhSGcfZR1IkdWuW2AyqccBkEO5iuaUG7zSQkEuzSlnuKNWBWS772QyZYyNPASH4jUoqqiebWSRCNh5AJmSRbNCAXDgoKp3Cj4az8HF4BBYNhwWYIxixy2Fw1EJyHOgmk5AltCEYOYCzh+QAcdsleZqewcOpqVQrCMeiQcIKb6xyBCfhUrmmnquVPEDrVSDR+hLeqatoii3Phk+pn4em7flrtGKC7HM9dvVbxH7ICliLp2f5JLSnpOSLMY2d3ZR9SjKi1FZHOGlx8o4/nfWIdl4dtewzteiMKInUzBrbHKLNgjf/ojZk7lNBerm2BqOzV27ub6oxQdbjiFQVcOftRN0onqDmAnJ2TfOIxr4lUnDJeAnDMXOcNOnBu2jFUta1E8iF5M9BGD9OZgPj3RUho3G5oJB2nZQjYakin8tTm9Ubi45aFI2AimNMFYvkYtJPS736zkQ4nOzcH1pw1Yrw/pDXfBjQmXBPa+QTiZZg/JpBa2w/FOli3NpJbzS3lvllW9cUNRffX4da68EUmcFYWMBWWM/qMhtmhzOl2HqbRXrDbWuMfSlm1LNdIzLm/IC3Y3LZII2pCUJyb1V07plx6L11RFAZrgN7jBFbtVqzyqH5ZjDoeqGI/ALz6bnsuvCAMGkIhZtL7lg+3EY0v2AxUrpqpi4NB4zErMNtFAnzDM8Z41i5cisnw9OzafQRoMk4BQzFdkRhf1P4ozbLWqVoZsNLndQ7e49Hv7nbOY664NRd7XHuT06VaQIiZIxZqfMaIcx8QZM8IpIngKLABXpksjsfeSnEy3XqOavVr/fTmC/qvTk/T4ES+NDs+/ejZukWvCnooosgwDPF80TVJ1f1oyApaW+81bJCs4VKtWpwIldRQn26xy+ojRCAGwlgoKNjUG92ztATnW0qV6eFp0isMfoRgT2aQZaz7hH3eE/bWDpDzgNXYiff+O0mke59eJ6zbk+vcItbFc5Rl0SkqX3Bfeq+ZC71mILayAqYu58mpb8nnoYLpcFhjzIURiJuKNNgp+wOm9e612/WFqu1dbLWqNzM1Wr8gSMezrlrri6mUSBc0ZfRWPNxdbXRa87IvV1pKrEp4kbckYFICLyofQtgYOKGmt4+XUxIMghK3CCURxVi5bTTzuU09mRUu6Sj1LXMRQK71FbSNRP0xYjSObuwr8p/lc6BttICsjrKtUP1KIfNUyK6SKyEwOPs41cmkalHTfT58CDoTj+BlMkHdPuMT8/WAR/MVQw3MWSiB1uZl+iI8AlcLYPY4o+ASiRNay1yxPMYFNh08q8IroTTI2tXTLf4krtk036U/hBbdFkm0gXoRok7NDaTymKkXOgTTXjJufIIFp7OQRKh+dXB/TuHJ7IB14lhn5r8SYe8okFQyYqBrYxUMgmN3ogQltt0595B7xqETFG7pwJhEieiNgoi9ru0hHXHLZWnITSdr+Ig49NFuAnjxkmY6Mb086gNTRNxsx6BKvWciCVnhW5q3mghYakaI26xvtQXZAXu52jMlKagWH9Z4JPnAo+V4HEQsj05OUrzbvFUmcIrlZLZxbNvD7oKdLLA0SBYEmeAUJoXHDq7d9fiGTY8fJr3p8E+W8WO0DJ1JJTi3PtjCp9NLbjuuX0s41b6C3620tg53zty4dAKcfPY7S7hyPf62sri6KJzp7G3UMi5DhFdfcVdPpH0Dmqd5IE8VSm+jtt5FZ3q3HO77Nv3xIUwiKTstSOAUgevMGUJUT2EgywWeOeaD1IJeLn1UzbvNzKUU+42Cmt4Gia7uqm+u5ERRK500RwlwnnMWhXIC6DintkMYWJoWJb85MaV5BwULjqUq5YxMtCNi06x8Twt3eQ6Bt49ATNm3Mg7w4JpmboiBjRwjjhUJknTk4J51MUrtxVBvhUKz7eZQzHZZNW8nZG8BHTTUaDncnYg+pqWYQU53zXAdTfGKWXOna9eh4Ki2pyknMoy2Y57yzp7vbYOMUw9RXjxr0A81q4aPyuxa9hxWCs23yQT3ILtQQG2sh24wbmdi3OtL6ngZxG+DbUkNjpB2kWTWuPi24Bw2cf7LRolqWc612mHZTmvlpyK81ASqJNm4F0mfTx6yjlJnp+FfGBr0pcenRe5hvC8KYQWO2B2XJbCh5uAsIzpMbnxGR0YSoelyYEfR3517y1YIGTScqQLzRKq3Unn4lH4Dbw9uNItntu2gkzD3bGLEm4ob0aXAyapTxi+ngtAu9l8mXq3qbvEHZ4jsAgmwkUt3U4tLKbU3GZTdvPEogq8OyrQlMFaACR+CVRgVHjGjkdl5ZAInm5Cs5VUsp1DkpVSVqQUrLFo9OpdI8GKAj/WQ4GE2fYSyYHhNKXBBEcNeVGIa6OUnjuOQBP4o9ia86OUc569nFJXvi80a0AbvLlELmKuSa6I7BuWy+YzeE3dPpphnTOmHggXvkyCB3+CoQq2NEjgGffE7Wi1WPjs70nLTs8ugSDYPM4GUbTXJk5JrartTVhlJU9EHmiOas/rGRgsFraG6xCJkmRPLiS7zhOSczIzDc8V5J5DOhJXiuTiJzV0ZFQfq+6SvlOPAFuBCa4hM3uGWaDPUVUFsIrOYLdC82FEIGuXdx0K0AYzD6jU1BN8h9C2gSdDgL3r9VFzO7+Ut4DHdGTKRLGOfEwq9Sq4NU+GHOuFYelHEI76tJm30of8HZfJOaeHRGhVXm+zQhjsAaPwXPGP02yR8WOtaCcKsIbwGXsIay4/n2/2UTpXbED2RpkKTqaNBUzCAcml6JScckw8c3agItebXOrwxQVFIgTp4GoJwiM/i+PCbqZb+cZEa1Bgc0qcRiXZND5/3ErlBHKDIzBnj7g4zzHQz+0IwAglka1MI8Jtqtz+LFTI3J7vhWbc1pocsPwBPGp61GhmfGJXGpTZTEGwhzlI0fqIB6viH7yQDdAOmdfNcg1wPck5Dtr7Scyg7XIclnVxp7lsJ5kDT0ZKZB4ah2argSf5ebvLOTUdMUOyEozhfamiRzE4A/LV1R+EROrMxtLsPZi2K8Gqdx9VBbxg/FUZ8Wq2fNiFbTCJRfWOjL1INIKGKNfTeWhAN0mXcylxxs5izNrLmrJlKhXblhRlnSBcdQlYMaBQUL45CvNc4MEgvi0bhxh5sZQGqXXdOs4IIK2J240hKORIVWMu0/CnuzPZNb6g+CpyLli2dEaaGyWllBgBvnMGTIplwQsOFkPd3/PMhGz1WeB7JFSRGopIENeA9rBwOjlzUcswfgzYgNiuMb4Co72BTgsFaswC0HaguLgTj5jvLceSIGOln8YyXKaSny6OFMs3SwPp8iwaUw4bFX/lLYPurzSZGZNAl4qjqKlVNRGThdudnU/GVpJH5ZVEfeDe/Bpb0eNcFvDMZihorjcYVZ2oFyQ1bB9HLNQy/4mJCFtsYKSZOzM6XsleR28IsQd9AC174hd7GQwstmfkeUdAJR2gXuIj5FlfbYusAkvfd3Ogpnhfi1tBMqnpCQg9IDm1YVFw5FeXhyCiP1+YgECaG26c8ZVyG5OfYIlygooszzN5AYfgEq8kPPbzo3nI3dUMl4atK7VD9keYYRe9NR9JKoDEOAvRUUSuCEAACvywM2zXLrPm4tc0nBvk0SQ64l3owCri0/1SjxRDo1RH7AjTNVuigaXhX+SEncBysk8TGUt19jjfrRVMItFm2SUc6sFa+U08A32q8E4tqfrVJiZr83lMrtzoDB+lzS7fCBX01EsVsUsL2jKhKEdCSoPMq8KtgTAcnvJZwvnqWfYK6OmBsyO1CdLLbWymlrqSblAN63mwK2QkuZLRqUKDOTnT7ubyJMIMGh2zleyxOS2JMh7Zxr6LWcwcZYNIPTjtap98G5XvjobZOiXZqaqlDmulIZlaSUuFUOxNsKg1E1wZ8iJOkLcvKX+Hz7M3PsdqjPuh3vpdXTHYCsOjIKzrVa/gnLH4Y5hlw6U7Si7XRhp9/iqfTvAQAiEc7btXYKk+O6CeXnwtfhyh6LrmFJPriA/3NjczHEhz/tWeJ0b0+pN+BKYeQZLwdJOLiNl6Db8uTr9pZUY/NQwQzm0rLurjadSwou4DvtlWtaEts10mdrd8ZYj3uWc4jb3GzXm08QXGkprVDEiIJj3sBSM8YgSSsnS73Fw6mRl38izl2TErQg2urU9XcFgEwiCADKWAGDXAMzitl+3ZhcjVcC071vv7iVmOYipjmG1EOKzGbQWt4WaYJro5OxQCWPl1k/eHtJVzeWSD68IjmJfBSjGtOXe+3Yd7mAgT7tpzKGRXU6FL2TSzgCvxIIVZsDWvFd8Yy+2220f5ICi3fV74M7rTyXSkcB+xIj7vdcaF1FPCNc3SS8Jqn2PhJGPTblwoxYNH4tyrBamkexH5/XM6ASTt3Bjg1nPYWeSNo6pCznKPzIBP1OBy7ZKb7hlzHbl6SJeLK2JeYt998RYsO1xDa3e7FdMR9mf1slzOtJ7GPbh4j7Ko87ME1rc038p9UYJ15+y6qNIuylgF7usHOgCJwXCQc38+kE5IHmYre3dc90Uq0yVyEchzsl9w27ap55VWn9nlaaPWvYrtVCRIaXBPEzid8Usu076Z467RSZM0WCbVIRXBLbewPIOx0trxaq+lsGcAoQfg66dpk/4USDFfllNfRRdycx4reU025JI1I7Ld9pSIMz8SH7YA1Q2qqXlInFFUw8O0b1JY9O/IjTHCnL9g2PV+7hiJ4Wt2mvoFF+pBemIQw1DKaYjaU7LZDyF8GkfuDtVox62yL3roqvWr7adgamWUDLeM5YO7wx41Z5XYmCqudWbCxd1p1oXjEfGWzIFvLt7Y+s5+D3p/EKcbP85lMthKiwV3sVajcrkosxyVSpfrcMgG2Xo+NeijtAWxc2UQGQJOO0qECQbY2SOFlAp8xRXNYsLvC4vqFNDzF7EYcsUdSoAM5EaD3ZHztnMAF4prrf1mFzgMn3wHh59HSLsYT2oq/CP0oIU3HjVaJYICZ7KitoDdFYN70uPpm5R6bBy1rx9AW5Huk2KzPLoth4/6eZzFgEO4fh+90J/To7I0udmdaiI1S0CU73Qt9SpDyhB5ConsCo/ZGYRvPHEkSj4zeg2+4nrKy7eLGcqlXdxwxFxqBQJqRxz9h0xVG9L0FkEPo7PGgscO1x0tIi86T7r+3F3ngPtSPkrheLIInEnxs063RX+URgxXSHSuPlM+O/tzFNxPvC09m+W0lgESPhkk244zIjztkuzr43NhlqawSKwbtaHieuFbvhRl/gr1nMo88cRhnJ1XJxcRo/CoOE4cXT+eCjLSN71dUrS7+xaGAwVYbc4dJC4buYQhe+RVZZQGmTYX5S64Wn+dk8lO6HBAISkrBc2UGApo/FkaQjBv5l2rpnpGn/Q5tiZPFeaaOrLF3gSO3TnPuWgX7agbUNS0YHYTTbICJRAgsMK2W7ISfQOGtXSVarDknwMAZy4TPnxvDEYvXtaLOpuJwBJ8Dspn4zSpnSJhXISYN6OHYXq5c8f1gUApEE/jVeenqyilGQPF9/bcFxV6fkYE2FEZmW2Qfk6Shy0H6CgoHGLplH8+t9AsmhqGl7o+3e3uYXsA2eFo6+tx5JdoBoXI9oxuxZM7F7RitbSimAHKWAx+s2H9PqxLjKq9GRIjME841rPnWzVUrFjpU+Cz9km9Pu+rHSQ0OQ9Jd5rMVECOt5FtypXV5J/6c+q8IxFwx7RrHdOyQOgrl9lUzzaR2yLFiF36nEY8q3LT/N2MROaCdDAhjcd5TiqnhMd7BQ138WxtyS6b9aAmlVmaiFbAidz2mX3gvd6Qbrm/qcbpnNYEdpOC4dY3ffKEUR2w1c5PTyXMLHEomQUR6rcjy7eFccwdhpbHXTp7BnZsB7bdAGq7DXeclHspgx7lg7Y05L5EQa4Pwh193I+MgaJKW+b+EeJF6OhQALiKOBPcuu4uYusxc6+eIwQr7REYk1NCGufLg9AiLV8Uc/dWf4yHwIKQKO3WWlBkpSVnuxUd9t5HJ6nqRuMu6icKmNGRIWfqSTw3GPRG8nISUXqBhFVXKsOj2Ck7xUhnLYC+rGBs2HnftWnKnhqKuali7quaWAAYKi+eoOi2TkDqtFwWI+5W4i6CVJWeNQxsRH+/2o137IejrcvjSLzocZ8eS+BnupyzqEpQesvO5J4jgi3Tys0NOjfjvSXm7nZC3gKIOaqhrKdCma0tMO0zGTKpMmgEjN3Po04v8IjdgBHS5rz1lhTmg+tZGK+nDFAl2r5hpxRhCeAJryjQafTDnEH6COceH/nbjWRdZZytJwVCOL5dO3xJITmxN1h4HqV7f7FIIiCEI3e2fGWD44KwwJHw9FbPwIaSpzulm6l/2c+2ijQGKEg4mHB4cmwdvKFyTZ5U1m0NROp2wKlIgqkwJ8gvzR18aiqoQarjpw8ARVBG52qiDi+Pk3rpuzw4ptt0UBqZ4jAs4VFrGs1cMTUqkEwmHNW64m3CAApAUo5rIj8PyAPSjY9dqCw+ikRPOV1ahdv33phavAElNN7ok39/xGfcDq9uPt4UE0lg9UYYqfDwKbTFBFFYNI0qXOtEWU9A2rqzPAd4sfN1I8G3CXJpcWFpMtnzEFYkYlrVHjeHoUVwHwsCIVsn8ADCMS+yRHu5lOAO3USoVcAXEsjJLX/WrJF6zhaNJWdf0lNtI/V5IQMpv2JXjc3RiYVJi1sWN3LhvbRDWn4eJZcHDLxpAJHhj1g/671GmeeQu/rRMrFDy9lr/lwby5y9E/+059NyevDOCgp+9IjahhUD1wqGRcNf/5q12rY6KSmnsZxkspLmecfYqzIzVjq60po+MRWtlhnTRgK+ynBBOZt2LiPOZilGuM/kqDYr3+tQjLUxmXY3+YQVmrVWPMVNOter0dopJnAKcxjyaRsYowqXN4rYrH2DJx3FE6hnb0c5OUK0g9Wd2eB6hiwhQe7kRMct7SLa6BdblOOph8MJXKfqlRFjCHAydDoF+/n5SJhH5W7NUbJIfmK5EaPg6Y6QECLn0/7ojeMa796JXNDQhoCTt0kQiN+1np9HZ6afTI51dx6AaPZMoCJiBkJFcSpolCDhSCjDldeUGpMmRiuzQ0iZzFcs7K/F1DV1sd01f8BDE9AKwyrhHqCO5HRb/S6OgDuR39ToHPHPWC3Nm9bDExW0hkpf/PB8uSh91+xL8BxOlyMlRGHrlLyi8Dl/xVv9CQDZ4kq1g7L3owqZp8nAXUXqLGeJ22e+zbkc29FeIUuk+FSLF2trK8ZqgjcHysXlaaJZfIDa9YQBlyff+wmKlwU6CAEeJwEA+Axn5td2MAAm0loAmiOp4GaJlxygIu+PnSlyb3NFgZEBhlxxxaDqWtyzwUue+CqNKtUftXJneBftKJbydIq8W1CIhQPCtgIu5I1u00i5pQ25J5ssT1yoN1N5JXkAnu+2LStihqWZmHRMUd4FHibIqHPxqsOvK3e5UkBQnWgnrC+uisl3TBL0ZTM7te/ONeRzMgzKVg/Vads/IANFemrb6JlhDeGElxxy4NVWCmE0LgeC0ZshPNVlsMjGBF3PpVsnK347oSoSpk1bCq5i8HdMTiDFN+Jxx6vFAQmTQsxrOj5jeD1XDUrLOSoh7CZree4S1GZFu0Cj13uiIlxjV4oHJBdgOl2za/rMbjZnq9dlbRwvLIz1Fj3H9BrpbAFUSqx3d8jFYuHp0VS8IIlv2+a1b7WuueoDaIabfxsw3vewbETsK5g1MXjlPBVpbbpOeaACwNxBl0G/dFiJVkxl4NCsbY2wCefsgCcrhZ6Qtr3opwndjT5WuJjJ9pTlYmGmDDIe+mXVadU6Q0bdmlLxEhe1wI7BRvFq7Pwi4fGGEw1Zlvl4p+4EmTLnktEcyd8F1sqYshuA3i6wK+QLC133aRv6GeeYz7NeA9G6sVeW3puCu/UJFLGV7mX5Hnic1vfL0ueeSUNogpynOLg9e04mTmgnhw6HNc5SDEjtddFpd5uOM7Up260mbO2UcE4rGBS0Rl/AnXuMNQf1frg4Ty6GztNOBx18lKd8cIqX+e6ARy0wshWmAb5pzRUcNHqCDcf6LxByGa7MyZkXCdtXQXgQfh8WQ8PTYXEU3ZoEui6uXhN48DgjgS+eavOGbqhTWdAwCUGGfQvv0xqLcgE7Rloszz71n+wFgxIPMMAoFViWEhta78tBPHs3J1giT1K7xg3DZWkvBSrScA4w+uIQAZDDc8eoYIKdKYMwrrR4DyFGQPmgIe81Z/rjE4lRZV8iI0kE/OGAng3Fbnenr7Jk5Be41NybVp+mMPe1U51TvS8AsUWzaHjf3cioWjU83YusaIwHZj0dEIF6GeMdajkq9yDUxXhMFuVKzdq1aXMMYOLBsseluu2I5TjdcMnd7F7VE8WiLB2FbloeVWNzk+Uz3+Ru1A+nZ1af0G3nhDQjbHlA9sxU0jgBsKsV4j4M6tWNq5lAQMtAoUTwajPnVShc6Gqri+3sbc7lsOChpoRrlrXczjYV1mMu24kdxTuq99gd6rp+ZGYcp9MLOOj9JZ4tvIwuUJrgDw1DA3tOMuB8zf1xkuf5HiLPdQM40bB9YRvjbacpyU0LM3K1IwKCQ5zOYCzX9wq+oAyw3ZMMMbihBwK9Bw1hh3CNb8Apy7CpdcDLvdvguHILp6AMnX94Mh8csGQhYWDSEiuTfKg+Qc0U2EDDsyV0I5tSN2TEfd6es7nBiixAxBRtIqzcmcWfHwsuL2UnP8H6cUmJPGqgywnzbole8rIOHIUBmoVmj2A9qZn99LiHedAV19gZns2mTFHE1vp+QatOwy1N4blgq0GiKDEaSNe2hnHB8YW9dx8aQhXw1NoYAJz7C2ZGtyOMKQ7CXtAb0oYOsUKPx87Owrgou0mqWOBuvjGj995HVlHwqefCAnYbPWJ9EBV5qk7aEzUrLAkw/m6XWHKNSr4yo6nq/JkEHkLi+xcVb+xQaFoKB7PbDPK34LzbTzqRYo7modcPx7XZkq/ghAm50W9jCp/6m8MhxIE6BSVIZo83cPZCSBtUAhnM7tIFwuPFCjIkXV1FbCdHa9SauqHrzV95LsYYW8sME1JPDJ2nFZv3j61NfEEqHLsfwbos6lLip1O0JfB1z1GhIUTdfcAqURnPOlGvepMt5mgb8yo8FfpBXV2jtZYUFy/dLOHlteRGWUOQ3UHKUPdTCDW0hwib+EhnAgjichbuDYguM5jBXrHiIKKtDgiOkaGDLXhqQv8UefwWGwaI98/VFYHB9vrdLc4JkcTXRz1cABF9Cqkq0rPgbdi81ZB+9RyTwz3vHqjdNZ/FppDzYJXPpMpzbF71eORRmr+aU+WiEsdbNqypnUUL+YhToABTV13GjgA4Mvxt9YIHRGbEfCDLkBWtxnnY7FYz0dKDk+oYqHVFg/KB5KPUu1C0NI0ytrK+GEjVCCVc3t2+pRfvctYVTTQLBtjVs8zCwJrgqj/qd1pMYWhI7uSt3arbgSSpSQM6oBKIq5YLxr4nngoLyqYCcijLxs1lr1kcIA0djitUKUYOIw5LjZxImJrTLmS986JbPkJm41Z5C6zRTRvCISbFc/YIMeCrACOo4t0ukQmYW/AcvTNrJpcOsCQ6u3m3o/hynNkKj8RPx5NwqrVwZEVpGrgC2x3DFYcDHyKSzcWifg3Icymz2JUYnFBwelEJc93zK//mrDG76UMcI0Sic4+joprIcrNmpSQsqY+Fx/nG5qpJyxFh3RpX8hnHiqayvw5DYqhxPw2bsAMzQ4XKFeQqX028JMttwosX0pYG9yoqmE3L3O1ZtweOYbq7bJBPpZNo/Rlo9JlVg+p+qvDnYgfnBxA9RJq8iv5YLQXbYFLsPbMDdFCCNohpVFj1gD7Up6ZBXBul641uvBI8VVmgzGggPyzZipx8PbUQtdXqecfkZ+yCQWKxV3/fnp0aGRieruh5Ey79mUS1ftYsGiOz9d4BaTaWZsjTjh82FzXtyvnIH25eEv42OSAbd81lojUi0miY7c1KL1jc5UGd16hJCdXKAiduslVpv0syXhqBYFq32Y8DaRn9FL7c+WeFXkUZuseaFygwAKbaTdqh3NETJCnF/XIx6HqdW1uD8SSJlpXQkMOntlV6aW3G7AKsYRfizMyjuZChp8FAT1WzwXc3O24+cQnS8fFsa5JngyG9EnMkMwhL3x2oYhWv90KReyC0DlVXA7Pj1UcFVQpbEDQyEG2ALM60GheI8qL2hNwmuMA/UFKB+wdI7ARJZZmTgbCPwA4MqjFMSKkWt+uJQdyEJJLN1+hYnRRyPIs7piroUan2WIpDPQhEBJVmOZgeOXsjnltmPI8VXCTEDEnZx3HWX7d0We/3mdmHG1DLNsZK0VEpACVlLuJQ+sOZiYiAcU2DVdwQ3FYSjREGg2m5gslCdiWkmGQZXA4k3CxyyPQKuR4H7QArEXbEGV/gZz2f6iyLcGjU1OCIu48hOus5u4A4ckHzi3xy0R2OLsvmABq6dLpE3biZfALowF5wpWO3vNsv52VdKgvR6yFvNr+Ab42YXgKAftb3PlcgnUm9xBaHHkL7W/l0lEp17IQeZ69nvJvlFT3p7Rlkcwm19GhqEzryuD+9WnSXey14iTkExB0zoUyt7XIEl/0S3ZIaam4sux21WQ71cdYnvbhdWLdVsFtun1qVyWuupq+EZdAZGORG2HL3CgEqtTaDgRENaZExbYNcJqUyJGLt6lycUn337wAertyUtSd9ZW6X2qvO8kDQywb29yqYSjhtIUmmlPJ0OtD5LU+3DizcDhhWvbgTT0F5UrHpPdiiigxuJ8xSsttLfyfkdDZXG4T2EOibPbyhPArsAEERSMCPvFJt+tNlrVjOVefyYJAqy6tYc8pJeSE3YPbvQ3Llfe3YFZ1lSm9BbkxKDPo8uedJiotnj+MjGUigbaOJ2VXZjscjglT14+z3Nh0Km125GCcE4HTXRXSBVedIohe8Ai8HjkPwRbLdpT1VbKzWTk7T+TPjI4jCYzqYMkFkMyS5N9xwGguZP3ehBnfgAZnLXoJGix4KxmR1YlctPgat6+2UE4dD8rqcwKijkBNAHQjoGZ+qtOWaCsGcPb4vvFfQNGeXDdlgylQ/aCNVjxqvi1opu8jG7G8XXvOIA8o/Jp58NqOX8G6gsT1wMjbngOvCNFRkR7OQnC+YTAdqMVTbxUpozNIqu1XUJ4kpJZSs5N3y42rdmwsa5TqqQxRB1OMpops6dsKQuCNSyuBB3j6BsiMTb7LARq/VkvJu520au7lqKdiJ9v4hKlcbJJvBGqQJJskaIxUrk+d4ejQdvqioLhL7ID/8TEiEYjTtp7Ov8/bM2Xx7nhBrVmupd9zrKiCwd7MbfCA7cyPTjWsVMMuvq2mIarfiRxAEag16UFvAhpd7PwrWvrcPRXUFxHrEgTnrIYV4xKn2OGS1+vmAlxMbEtmNOfGSMXa3qZDp2K+qE2jofk3zV0MZlgMYK8KkncJAcyq79Cn0AXMABDFjcwCL8wvJVJ4uL8+Th9Ro2jT1gB1gjKzPs7xKyXVTeGkB0EIpVSqQ0tsJWXgYwhKqQirD6vbxwRRtAB4oL+kHRUOqR+CkWaiKPUCbLoqSzv3qwp5+5PX42i7QmaR67oaM5QF/Cmu0J0jtbJeQWPqo10sk2Z2AVe8MbNsNpnlmp5+bqeEldlYKacXlVm/PZhMYjS3d54XnHU17irdEKzk5rPhG0YoWafQAMplitEUe4J66ytw6mpPqmjBI0+b8orlequZaJbBeV8gFPrOsa569pO/TFc4qZDEJPD3N8Z7SD3b3+Ui7J1Yb9yKABHewcYGr6vFHYbfP1RH3a64olXSsbozugmdnVKjao2kVm4P1EezCDAFTifDR0N71rsD9NEV6t8n16oDvcEPBGYlETRd0JTpitt0BYMsOR3UlYYY5K6F7JDOHz4m4DM8lDze94VyIou5gxzsSIUWmHVOjNukB3ebrQmLoAJxIGxPjPe93+20WmP0qH9HRJmWVytxz3/EU2yd6D7PP26KnRm1WrVASeGGVzCVc7rHF6fOdTusFNpNiIZCuOkPXVi8UQ5muDgzxN1uZV84HnQYuHgJLOv4OQ3F15rubyIHkSFh39sFRae7i5YndSvPSjkrJ3Ms6xRpbv1G8OEc6x1/nfU/3uE9VltoztxXQpeSASAVo3tdPcHI96ToeZNAFkqnhdkUlZYG3DlrHPtJGjEDyAmjMx3PAjNP+9HFhsY0VezDdCVq9zQQMu6TIWrrbfHjm6Ewni4mGdmuY2tnXFE22igvjyPcle0isCCy6py9NakVX2KBud5PQANUbGzd2iGWnHuuRzkafNmMBHVdBWqaohTbzJHi7c3O6fJnxiFe8ZsM5CL3DBUJTdwKRueDONn3h78qwu21h0Nrg3/Y0Ss+Z3hmUqjbnxVyEEmyCnUPhDaVU28WDUi6GY5XwLc7rUlRyME+17tlo8bQ53jBznSjMLiwR+U14bM4Oi9xivP5TsuYkMmiKhdkBfDh2Jm32GZeR8QOVeZo6cKW7t4WXp6oE70DmtxOHLZmtcUWW7MDjnk6UEfqoBcNqMvBL4oRJ7LBnIufqI1azDJSegm67o3TYzEEounfaxdsZo3vptCBJGx9oLCSAqNsbGywaxNZu3sREcIWp5EnjTC1rzccNbS4zU980W1UeD+DpTs/dMxSpdMjLdpTBeXEDVa4TjOaxplRQGOsGhiPCPKMA1KZ2QvbUjozTXOENku2RdNEmtEJ2IAoMaW5x5JnukXbSJvAY/xmdEBUHH1O6RutAqjlJkn/5y7fffPPNJ73Xd5WVd4KOF7vIGzfKm7bEhx/73xB0vD78w4d3weE3VqHP/BxR3UXvlBzhi3T+p3z/MKdN/1K1/uMb68snfqt3Rs03NqmXnu6/Ho3fWSff//5iBGqq16MfwOMt8GdWnx/9N/vpvfcf3p35SDXy3f+Yvvvk7CcOjxeHzktD/Ix9+DH58M/Hxx+H+DSNFyXUy+3vpg9z1/9Yp2taf5IE/vaNduvbP3/y+o0W9MXP9lLb+Mh1Vj8/dvRbJpKpe2kVJV373fwhfSmf9O9S2F82At+G+Omnj/rg4bHg25594eaHH+lfb8CHH3986Xf2P7444Lr2TfoDfqe5bD78mP16jm8qEh+A7dfd/JLC619+RV/6/9T4M0HYP/jQ36XyQv4ZTNIVbJejr3//9w/zS3jgP74ggHE+06y9ibT8t1MV/9fIZF6cR3891uRFBvXtG9noF4RQf/uSB+nFBfSSeWu69V3g/j+nKHtRnn37ibL0aH2cxE/tX2TpL4a4F3/V4/f52D4RnP3eBnx5kN5JtT4y8350C3wN8vt8gB+7/fYf7CM50NFSzz+9ayX89GIn/ztEg7/o+LcTfj9YY/pSg/+7c/rVIr+xHX2MeS+iw98Jch9VUX8v/nXVF7uZJt9+8zMX1xsp1OcjLP7/9wB/PMbv6/YxBL5W7nO4/3gUP1NGfQA+kwq+6Cd/tWy/l2y+ea3jZ87DP334p+/r6Tfh7rWHH777l/a7D8evH94Ior4grPw8+hHB2S2N3/jxX3JOWTqmbZy+c3Z+bPwiInxlo58+WGX7xjf40q/9PerLd8a+X3jyYqyef8HV+c6D9cMfj36OSP9iARxf5FS/otb+xPD5xlL4Gv3w9HUcXlJ6L5Grt8saxmM3TUdHH0n93ruefvq4/B9n+Q9Gh2+PfvSP3vzpTerkbZ6/mEz45cK8MYT23Zeefvdy5vOCvmv2TZ+k+H6mqfxiYb9/FOVLn+8t4X1WbPhQZt/84WcJ4CSt0/njpnzBXfnTN+/SNW88gL8HN97y9PLSr0k+k3e+k4AdzrwUhV/5+23v3kmk3+k2P4QvtYY3xrBjwI9d/ezyn1/b9vNcjibNi051/m0y/+mDWjZl/EUvn4eow+cb4d1nR376JXz62PDtzb9++DH9zyhVP/ztFbbq9sOPU/bhp5/+brP/jJn1Hxrvy2z8D4z7ZfN/sNs3P94IUX+5seA/+PwL7gxLmc7f/PAWLX517b9g5vz2m99Jub8kbPxF1v0NIx5zgKmfPnPovRPXMe/DvWjgj+PyFgC65V0U4mMU+OkXdHZ/NxEw4+tsfoocx934yGL73x7gfx+5HNiyeQlq/rh+pg0+fH4TFf8ivyL//L/DX6zoHz4YYxelH+JlfCnSvWY4L9NLDnOafwGHD/iav4mo/LLrjzKgfzjWuZyeH/7tr2+0lX97W7Vv/W8/iNMH852b9N+Oq96m74yTr1DyWs8X5WT9tlEH1H6/hP96vP+v7158rmte9uspvR5/EcofZy3rxuaIAC/lgV9AiV9i3X//0D/nomvRDz/GH7795mMkez30x1eA/uPHouObd2jz4S8fvntFvz999zqtz+mnN91W+G/fJOEcHh++nvvpBV6+f304zUnZ/vDOVvqaVvvh1eyno5/vv3tJkHz3x5fY9J8+6pm8qrCXts77gD9FZ+yjfvDR9P2ZMjme+O67H46xv/vLX7774ZPA8A+fhCs+d/KXj1JhPzPtv92Rn7t6X8pXdx+ZRL/74Yc//0yaD/3wTvv4/c8ff/MiePz+5dxHTtifKSJ/+PbXWO2Nq/Tjo28u/McnF1+X+vsvdvN49rjcH4lqv/0FqegnePblVft0Lj498H5LP7GA/owOP+mJ/OKevsDhF8SWn544vPq9Y/R+q7+c59steaGYsDwg6+lXrv6eu58D2qcGb3rv/8U1eL9JZhinf/p8ReLXHhx1aJTOj/Tj1enH9Mc3Oew3Ad03Ku+3KcSv+PtfdXP6pXLci670w7d/f5len3/Zwefgif6sD1F+88Uff/hIWPqnYwrT/GOaZa97F43d4wUu3siSX6IuP31gDpTxBgqKj5zK370w0PymQfqxJ9H4sJbhW4sqHduj7h+PFm/Ex2+Q7PvmJf9zYJWPcz56eEtgx3NHNfOS/HxxLH+CA+/IyTGVAwCN1bsuU9QdoP/9W47X2lqW8GM2ds2PryJkPtY5nV40zdNPH7gXufzHnqLw2IoDfrxw8tud+VH87lMMbY/U+JKUe7X549ur5MXmPP4YHVAvP/Y4ScZ0+tTTcWb+rezfZpW+6MX/7QiRr+gbrseyv6b4vr0fJ/X60uVo/SP24cfu52c+wD+9/frlVf0QPqoP3/2vY47fl3+B/1z+H3/RuD+XAPDDMeb3/1T+5S/fTmP87Q/v4eNA9SUA//Af3338uuadC3j/hAdE47dn9wuXvliG/5IP/9v/Bf6f38PI5V9++nf4gvzLT3+Fkb/9FfqR+NunN9C/QvDx4gfwSAwf/Sz//Hb6/uOzqx9PncdSjvivx97+5dtinvs/geA//a+PLv7px7f9fWOc/tMFgqBffCX1M7YwX/Hn1+DCSyNH/NNvWHQ/D/ftZ22hL9LxluRvZ/zXefjFl/3XF4X0G+WuZSjk7U8//sdv1/Y90r16eB31T1fnpUr05cCfWn//ebgv/frt2D/8otZ+i1df+Pz3/T12eHlt73swY8LxUbb/n33+f+HvF4HrDx+07kM+hv1RzoT1p1v6goBx8RYYXnf4nRx9KtIjSB6o53V8wg9HcIurV5Mv+npTMJ/eVZfG9jMl9vRSc/hYLn+ujo57/h4tPs7w5/D7Jd3z6+S8xJN+62LyFvTS5M/vnryiyGspfvjT53P37W96fJFi/w3/85//x/QvEHR5/f7++vXq18fxl2fziwvy83H/glz794P/C0Jnb0rQL87pVwV8lE9vivHth4/0+O96Gf/zCyyNvLD0f7d4yFf7al/tq321r/bVvtpX+2pf7at9ta/21b7aV/tqX+2rfbWv9tW+2lf7al/tq321r/bVvtpX+2pf7b/V/m9z0wh3APAAAA=="

if __name__ == "__main__":
    sys.exit(main())

