#!/usr/bin/env python3
"""QClaw App Lab Entry Point — Bootstrap and TUI launcher.

This is the main entry point for the QClaw Arduino App Lab application.
When App Lab runs this script, it:
  1. Bootstraps the QClaw workspace (~/.qclaw/) on first run
  2. Verifies the LLM model file is present
  3. Verifies the inference engine binary is available
  4. Launches the qclaw-launcher-tui binary (the interactive TUI)

The TUI provides:
  - Model configuration (provider, API keys, endpoints)
  - Channel configuration (Telegram, Discord, etc.)
  - Direct chat (pre-router + single LLM call, fast path)
  - Agentic chat (full tool loop with arduino, camera, LED, I²C tools)
  - Gateway management (start/stop Telegram bot)

No terminal interaction required — users interact entirely through the TUI.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# The App Lab app directory (where this script lives)
APP_DIR = Path(__file__).resolve().parent.parent

# QClaw home directory — where runtime config and workspace live
QCLAW_HOME = Path(os.environ.get("QCLAW_HOME", str(Path.home() / ".qclaw")))

# Workspace source (shipped with the app) and destination (runtime)
WORKSPACE_SRC = APP_DIR / "workspace"
WORKSPACE_DST = QCLAW_HOME / "workspace"

# Config source and destination
CONFIG_SRC = APP_DIR / "config" / "qclaw.config.json"
CONFIG_DST = QCLAW_HOME / "config.json"

# Pre-built binaries
BIN_DIR = APP_DIR / "bin"
TUI_BINARY = BIN_DIR / "qclaw-launcher-tui"
QCLAW_BINARY = BIN_DIR / "qclaw"

# LLM model
DEFAULT_MODEL_DIR = Path.home() / "models"
DEFAULT_MODEL_NAME = "Qwen_Qwen3.5-0.8B-Q4_0.gguf"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / DEFAULT_MODEL_NAME

MODEL_DOWNLOAD_URL = (
    "https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/"
    "Qwen3.5-0.8B-Q4_0.gguf"
)


# ── ANSI Colors ───────────────────────────────────────────────────────────────

class C:
    """ANSI color codes for terminal output."""
    BLUE = "\033[1;38;2;62;93;185m"
    RED = "\033[1;38;2;213;70;70m"
    GREEN = "\033[1;38;2;80;250;123m"
    YELLOW = "\033[1;38;2;241;250;140m"
    CYAN = "\033[1;38;2;139;233;253m"
    PURPLE = "\033[1;38;2;189;147;249m"
    RESET = "\033[0m"
    DIM = "\033[2m"


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = f"""
{C.BLUE}██╗   ██╗ ███╗   ██╗  ██████╗   ██████╗ {C.RED} ██████╗██╗      █████╗ ██╗    ██╗
{C.BLUE}██║   ██║ ████╗  ██║ ██╔═══██╗ ██╔═══██╗{C.RED}██╔════╝██║     ██╔══██╗██║    ██║
{C.BLUE}██║   ██║ ██╔██╗ ██║ ██║   ██║ ██║   ██║{C.RED}██║     ██║     ███████║██║ █╗ ██║
{C.BLUE}██║   ██║ ██║╚██╗██║ ██║   ██║ ██║▄▄ ██║{C.RED}██║     ██║     ██╔══██║██║███╗██║
{C.BLUE}╚██████╔╝ ██║ ╚████║ ╚██████╔╝ ╚██████╔╝{C.RED}╚██████╗███████╗██║  ██║╚███╔███╔╝
{C.BLUE} ╚═════╝  ╚═╝  ╚═══╝  ╚═════╝   ╚══▀▀═╝ {C.RED} ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
{C.RESET}
{C.PURPLE}  Arduino App Lab Edition{C.RESET}
"""


def info(msg: str) -> None:
    """Print an info message."""
    print(f"  {C.GREEN}✓{C.RESET} {msg}")


def warn(msg: str) -> None:
    """Print a warning message."""
    print(f"  {C.YELLOW}⚠{C.RESET} {msg}")


def fail(msg: str) -> None:
    """Print an error message."""
    print(f"  {C.RED}✗{C.RESET} {msg}", file=sys.stderr)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap_workspace() -> bool:
    """Copy workspace files to ~/.qclaw/ on first run. Returns True if setup ran."""
    first_run = False

    # Create QCLAW_HOME if needed
    if not QCLAW_HOME.exists():
        QCLAW_HOME.mkdir(parents=True, exist_ok=True)
        info(f"Created QClaw home: {QCLAW_HOME}")
        first_run = True

    # Copy config.json if not present
    if not CONFIG_DST.exists():
        if CONFIG_SRC.exists():
            shutil.copy2(CONFIG_SRC, CONFIG_DST)
            info(f"Installed config: {CONFIG_DST}")
            first_run = True
        else:
            warn(f"Default config not found at {CONFIG_SRC}")

    # Copy workspace directory if not present or if SOUL.md is missing
    soul_dst = WORKSPACE_DST / "SOUL.md"
    if not soul_dst.exists():
        if WORKSPACE_SRC.exists():
            if WORKSPACE_DST.exists():
                # Merge: copy files that don't exist yet
                _merge_tree(WORKSPACE_SRC, WORKSPACE_DST)
            else:
                shutil.copytree(WORKSPACE_SRC, WORKSPACE_DST)
            info(f"Installed workspace: {WORKSPACE_DST}")
            first_run = True
        else:
            warn(f"Workspace source not found at {WORKSPACE_SRC}")

    # Set up shared directories between App Lab and QClaw workspace
    setup_sketch_sharing()
    setup_python_sharing()

    return first_run


def _merge_tree(src: Path, dst: Path) -> None:
    """Recursively copy files from src to dst, skipping files that already exist."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _merge_tree(item, target)
        elif not target.exists():
            shutil.copy2(item, target)


def setup_sketch_sharing() -> None:
    """Link the App Lab sketch/ dir and ~/.qclaw/workspace/sketches/ together.

    Both the App Lab editor and QClaw's agentic path need to see the same
    sketch files. We make ~/.qclaw/workspace/sketches/ a symlink pointing
    to the app's sketch/ directory. If the workspace sketches dir already
    exists as a real directory, we merge its contents into sketch/ first.
    """
    app_sketch_dir = APP_DIR / "sketch"
    workspace_sketches = WORKSPACE_DST / "sketches"

    app_sketch_dir.mkdir(parents=True, exist_ok=True)

    # Already a symlink pointing to the right place — nothing to do
    if workspace_sketches.is_symlink():
        if workspace_sketches.resolve() == app_sketch_dir.resolve():
            return
        # Stale symlink — remove and re-create
        workspace_sketches.unlink()

    # Real directory exists — merge contents into app sketch/ then replace
    if workspace_sketches.is_dir():
        for item in workspace_sketches.iterdir():
            target = app_sketch_dir / item.name
            if item.is_dir() and not target.exists():
                shutil.copytree(item, target)
            elif item.is_file() and not target.exists():
                shutil.copy2(item, target)
        shutil.rmtree(workspace_sketches)

    # Create the symlink: workspace/sketches/ → app sketch/
    try:
        workspace_sketches.symlink_to(app_sketch_dir)
        info(f"Sketch sharing: workspace/sketches/ → {app_sketch_dir}")
    except OSError as exc:
        # Symlink creation may fail without privileges on some systems;
        # fall back to copying on each launch
        warn(f"Could not create sketch symlink ({exc}); copying instead")
        if not workspace_sketches.exists():
            shutil.copytree(app_sketch_dir, workspace_sketches)


def setup_python_sharing() -> None:
    """Link the App Lab python/ dir and ~/.qclaw/workspace/python/ together.

    Similar to sketches, this ensures any python scripts generated by QClaw's
    agentic path are visible and editable in the App Lab IDE.
    We make ~/.qclaw/workspace/python/ a symlink pointing to the app's python/ directory.
    """
    app_python_dir = APP_DIR / "python"
    workspace_python = WORKSPACE_DST / "python"

    app_python_dir.mkdir(parents=True, exist_ok=True)

    # Already a symlink pointing to the right place — nothing to do
    if workspace_python.is_symlink():
        if workspace_python.resolve() == app_python_dir.resolve():
            return
        # Stale symlink — remove and re-create
        workspace_python.unlink()

    # Real directory exists — merge contents into app python/ then replace
    if workspace_python.is_dir():
        for item in workspace_python.iterdir():
            target = app_python_dir / item.name
            if item.is_dir() and not target.exists():
                shutil.copytree(item, target)
            elif item.is_file() and not target.exists():
                shutil.copy2(item, target)
        shutil.rmtree(workspace_python)

    # Create the symlink: workspace/python/ → app python/
    try:
        workspace_python.symlink_to(app_python_dir)
        info(f"Python sharing: workspace/python/ → {app_python_dir}")
    except OSError as exc:
        # Symlink creation may fail without privileges on some systems;
        # fall back to copying on each launch
        warn(f"Could not create python symlink ({exc}); copying instead")
        if not workspace_python.exists():
            shutil.copytree(app_python_dir, workspace_python)


# ── Model Download ────────────────────────────────────────────────────────────

def _download_progress(block_num: int, block_size: int, total_size: int) -> None:
    """Callback for urllib.request.urlretrieve — prints a progress bar."""
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        mb_done = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(
            f"\r  {C.CYAN}⬇{C.RESET} [{bar}] {pct}%  ({mb_done:.0f}/{mb_total:.0f} MB)",
            end="", flush=True,
        )
    else:
        mb_done = downloaded / (1024 * 1024)
        print(f"\r  {C.CYAN}⬇{C.RESET} Downloaded {mb_done:.0f} MB...", end="", flush=True)


def check_model() -> bool:
    """Verify the LLM model file exists; auto-download from Hugging Face if missing."""
    model_path = Path(os.environ.get("QCLAW_MODEL", str(DEFAULT_MODEL_PATH)))

    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        info(f"Model found: {model_path.name} ({size_mb:.0f} MB)")
        return True

    # Auto-download from Hugging Face
    print(f"  {C.YELLOW}⬇{C.RESET} Model not found — downloading from Hugging Face...")
    print(f"  {C.DIM}{MODEL_DOWNLOAD_URL}{C.RESET}")
    print()

    model_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = model_path.with_suffix(".gguf.part")

    try:
        urllib.request.urlretrieve(MODEL_DOWNLOAD_URL, str(tmp_path), _download_progress)
        print()  # newline after progress bar
        tmp_path.rename(model_path)
        size_mb = model_path.stat().st_size / (1024 * 1024)
        info(f"Model downloaded: {model_path.name} ({size_mb:.0f} MB)")
        return True
    except (urllib.error.URLError, OSError) as exc:
        print()  # newline after progress bar
        fail(f"Download failed: {exc}")
        # Clean up partial download
        if tmp_path.exists():
            tmp_path.unlink()
        print()
        print(f"  {C.CYAN}Download manually:{C.RESET}")
        print(f"    mkdir -p {DEFAULT_MODEL_DIR}")
        print(f"    wget -O {DEFAULT_MODEL_PATH} \\")
        print(f"      '{MODEL_DOWNLOAD_URL}'")
        print()
        return False


def check_binary() -> bool:
    """Verify the TUI and qclaw binaries exist and are executable. Returns True if ready."""
    ok = True

    for binary, name in [(TUI_BINARY, "qclaw-launcher-tui"), (QCLAW_BINARY, "qclaw")]:
        if not binary.exists():
            fail(f"Binary not found: {binary}")
            ok = False
        elif not os.access(binary, os.X_OK):
            # Try to make it executable
            try:
                binary.chmod(0o755)
                info(f"Made executable: {name}")
            except OSError:
                fail(f"Cannot make executable: {binary}")
                ok = False
        else:
            info(f"Binary ready: {name}")

    if not ok:
        print()
        print(f"  {C.CYAN}Build binaries from the QClaw-v2 branch:{C.RESET}")
        print(f"    git checkout QClaw-v2")
        print(f"    make build-linux-arm64")
        print(f"    # Then copy build/qclaw-linux-arm64 → bin/qclaw")
        print(f"    # And build the TUI: go build -o bin/qclaw-launcher-tui ./cmd/qclaw-launcher-tui")
        print()

    return ok


def check_platform() -> bool:
    """Warn if not running on ARM64 Linux (the Uno Q's platform)."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux" and machine in ("aarch64", "arm64", "armv8l"):
        info(f"Platform: {system}/{machine}")
        return True

    warn(f"Platform: {system}/{machine} — QClaw binaries are built for linux/arm64 (Uno Q)")
    warn("The TUI may not launch on this platform.")
    return False


# ── Launch ────────────────────────────────────────────────────────────────────

def launch_tui() -> int:
    """Replace this process with the TUI binary."""
    env = os.environ.copy()
    env["QCLAW_HOME"] = str(QCLAW_HOME)

    # Ensure the qclaw binary is on PATH so the TUI can find it for gateway commands
    current_path = env.get("PATH", "")
    bin_path = str(BIN_DIR)
    if bin_path not in current_path:
        env["PATH"] = f"{bin_path}:{current_path}"

    tui_path = str(TUI_BINARY)

    # On Linux, replace the current process entirely with execv
    # This gives the TUI full terminal control
    try:
        os.execve(tui_path, [tui_path], env)
    except OSError as exc:
        fail(f"Failed to launch TUI: {exc}")
        print()
        print(f"  {C.CYAN}Try running directly:{C.RESET}")
        print(f"    {tui_path}")
        return 1

    # execve never returns on success; this line is only reached on failure
    return 1


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    """Bootstrap, verify, and launch QClaw TUI."""
    print(BANNER)
    print(f"  {C.DIM}Initializing QClaw for Arduino App Lab...{C.RESET}")
    print()

    # Step 1: Bootstrap workspace
    first_run = bootstrap_workspace()
    if first_run:
        print()

    # Step 2: Check platform
    check_platform()

    # Step 3: Check model
    model_ok = check_model()

    # Step 4: Check binaries
    binary_ok = check_binary()

    print()

    if not model_ok:
        fail("Cannot start: LLM model not found. See download instructions above.")
        return 1

    if not binary_ok:
        fail("Cannot start: Pre-built binaries not found. See build instructions above.")
        return 1

    print(f"  {C.GREEN}All checks passed — launching QClaw TUI...{C.RESET}")
    print()

    return launch_tui()


if __name__ == "__main__":
    sys.exit(main())
