#!/usr/bin/env python3
"""
pmbootstrap_init.py — Drive `pmbootstrap init` non-interactively.

The device is fixed to xiaomi-polaris (per user requirement).
All other init choices are read from environment variables, which
are populated from GitHub Actions workflow_dispatch inputs.

Chinese font packages are ALWAYS added to the extra packages list.

Implementation note
-------------------
Previous versions used pexpect's native expect(), which had a
buffering issue where the "pmaports path [...]" prompt was in the
buffer but expect() didn't match it (likely a pexpect internal
buffer state quirk when combined with logfile=sys.stdout).

This version uses a simpler, bulletproof approach:
  - Spawn pmbootstrap in a PTY (via pexpect.spawn, but only for PTY)
  - Read ALL available output into a single string buffer
  - After each sendline(), read until the NEXT expected prompt appears
    in the buffer (using re.search against the full accumulated text)
  - Strip ANSI codes before matching (belt + suspenders with NO_COLOR)

This eliminates pexpect's internal buffer state as a variable.
"""

import os
import re
import sys
import subprocess
import time
import select

# ---------------------------------------------------------------------
# Make sure pexpect is available (we use it for PTY spawning).
# ---------------------------------------------------------------------
try:
    import pexpect
except ImportError:
    print("[init] pexpect not found, installing via pip...", file=sys.stderr, flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pexpect"])
    import pexpect


# ---------------------------------------------------------------------
# Read configuration from environment.
# ---------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


channel        = _env("PMOS_CHANNEL",     "edge")
audio          = _env("PMOS_AUDIO",       "pipewire")
wifi           = _env("PMOS_WIFI",        "iwd")
usb_mode       = _env("PMOS_USB",         "developer")
ui             = _env("PMOS_UI",          "plasma-mobile")
systemd        = _env("PMOS_SYSTEMD",     "always")
ui_extra_raw   = _env("PMOS_UI_EXTRA",    "true").lower()
ui_extra       = "y" if ui_extra_raw in ("true", "1", "yes", "y") else "n"
extra_packages = _env("PMOS_EXTRA_PACKAGES", "")

VENDOR = "xiaomi"
DEVICE = "polaris"

LOCALE   = "zh_CN"
TIMEZONE = "Asia/Shanghai"
HOSTNAME = ""

CHINESE_FONTS = [
    "font-noto-cjk",
    "font-wqy-zenhei",
    "font-wqy-microhei",
]


def build_extra_packages() -> str:
    extras: list[str] = []
    if extra_packages and extra_packages.lower() != "none":
        for p in extra_packages.split(","):
            p = p.strip()
            if p and p not in extras:
                extras.append(p)
    for font in CHINESE_FONTS:
        if font not in extras:
            extras.append(font)
    return ",".join(extras) if extras else "none"


extras_str = build_extra_packages()

print("=" * 60, flush=True)
print("pmbootstrap init — non-interactive driver", flush=True)
print("=" * 60, flush=True)
print(f"  Vendor:           {VENDOR}  (FIXED)")
print(f"  Device:           {DEVICE}  (FIXED)")
print(f"  Channel:          {channel}")
print(f"  Audio backend:    {audio}")
print(f"  WiFi backend:     {wifi}")
print(f"  USB mode:         {usb_mode}")
print(f"  User interface:   {ui}")
print(f"  UI extra pkgs:    {ui_extra}")
print(f"  systemd:          {systemd}")
print(f"  Extra packages:   {extras_str}")
print(f"  Locale:           {LOCALE}.UTF-8")
print(f"  Timezone:         {TIMEZONE}")
print(f"  Hostname:         (default = xiaomi-polaris)")
print(f"  NO_COLOR:         1 (disables pmbootstrap ANSI codes)")
print("=" * 60, flush=True)


# ---------------------------------------------------------------------
# ANSI escape stripper (belt + suspenders with NO_COLOR).
# ---------------------------------------------------------------------
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b[()][AB012]|\x1b[=>]")

def strip_ansi(s: str) -> str:
    return _ANSI_ESCAPE.sub("", s)


# ---------------------------------------------------------------------
# Spawn pmbootstrap init in a PTY.
# We use pexpect.spawn ONLY to get a PTY; we do NOT use expect().
# Instead, we manually read from child's PTY fd using select().
# ---------------------------------------------------------------------
print("\n[init] spawning: pmbootstrap init (with NO_COLOR=1)\n", flush=True)

spawn_env = os.environ.copy()
spawn_env["NO_COLOR"] = "1"
spawn_env["PYTHONUNBUFFERED"] = "1"

child = pexpect.spawn(
    "pmbootstrap init",
    timeout=300,
    encoding="utf-8",
    maxread=65536,           # large reads to get full prompts at once
    env=spawn_env,
)
# Do NOT set child.logfile — we manage output ourselves.


# ---------------------------------------------------------------------
# Read-all-available helper.
# Reads everything currently available from the PTY without blocking.
# Returns the raw string read (may be "" if nothing available).
# ---------------------------------------------------------------------
def read_available(timeout=0.5) -> str:
    """Read all currently-available data from the child PTY."""
    chunks = []
    fd = child.child_fd
    end_time = time.time() + timeout
    while time.time() < end_time:
        remaining = end_time - time.time()
        ready, _, _ = select.select([fd], [], [], min(remaining, 0.1))
        if not ready:
            break
        try:
            data = os.read(fd, 65536)
            if not data:
                # EOF
                break
            chunks.append(data.decode("utf-8", errors="replace"))
        except OSError:
            break
        # Reset timeout to drain quickly once we start getting data
        end_time = time.time() + 0.2
    return "".join(chunks)


# ---------------------------------------------------------------------
# The core: wait for a prompt, then send a reply.
#
# We accumulate ALL output into `buffer`, strip ANSI, and search for
# the pattern. If found, we send the reply and clear the buffer up to
# the match. If not found within timeout, we fail with a clear error.
# ---------------------------------------------------------------------
buffer = ""

def wait_and_send(pattern, send_text="", timeout=120, step=""):
    """Wait for `pattern` (regex) to appear in the stripped output, then send `send_text`."""
    global buffer
    if step:
        print(f"\n[init] {step}", flush=True)
    print(f"[init]   -> waiting for: {pattern!r}", flush=True)

    compiled = re.compile(pattern)
    deadline = time.time() + timeout

    while time.time() < deadline:
        # Read whatever is available (blocks up to 0.5s)
        chunk = read_available(timeout=0.5)
        if chunk:
            # Print raw chunk to stdout so it appears in the Actions log
            sys.stdout.write(chunk)
            sys.stdout.flush()
            buffer += chunk

        # Check for EOF
        if child.eof():
            print(f"\n[init] ERROR: pmbootstrap exited unexpectedly", file=sys.stderr, flush=True)
            print(f"[init] pattern not matched: {pattern}", file=sys.stderr, flush=True)
            print(f"[init] last 2000 chars of stripped buffer:", file=sys.stderr, flush=True)
            print(f"{strip_ansi(buffer)[-2000:]}", file=sys.stderr, flush=True)
            sys.exit(1)

        # Search for the pattern in the stripped buffer
        stripped = strip_ansi(buffer)
        m = compiled.search(stripped)
        if m:
            print(f"[init]   -> MATCHED!", flush=True)
            if send_text:
                print(f"[init]   -> sending: {send_text!r}", flush=True)
                child.sendline(send_text)
            else:
                print(f"[init]   -> sending: <empty> (use default)", flush=True)
                child.sendline("")
            # Clear the buffer up to and including the match (in stripped space)
            # Simplest: just clear the whole buffer, since each prompt is consumed.
            buffer = ""
            return

    # Timeout
    print(f"\n[init] ERROR: timeout ({timeout}s) waiting for: {pattern}", file=sys.stderr, flush=True)
    print(f"[init] last 2000 chars of RAW buffer:", file=sys.stderr, flush=True)
    print(f"{buffer[-2000:]!r}", file=sys.stderr, flush=True)
    print(f"[init] last 2000 chars of STRIPPED buffer:", file=sys.stderr, flush=True)
    print(f"{strip_ansi(buffer)[-2000:]}", file=sys.stderr, flush=True)
    sys.exit(1)


def wait_for_either(patterns, timeout=120, step=""):
    """Wait for one of several patterns. Returns the index of the matched pattern."""
    global buffer
    if step:
        print(f"\n[init] {step}", flush=True)
    print(f"[init]   -> waiting for one of: {patterns}", flush=True)

    compiled = [re.compile(p) for p in patterns]
    deadline = time.time() + timeout

    while time.time() < deadline:
        chunk = read_available(timeout=0.5)
        if chunk:
            sys.stdout.write(chunk)
            sys.stdout.flush()
            buffer += chunk

        if child.eof():
            print(f"\n[init] ERROR: pmbootstrap exited unexpectedly", file=sys.stderr, flush=True)
            print(f"[init] last 2000 chars: {strip_ansi(buffer)[-2000:]}", file=sys.stderr, flush=True)
            sys.exit(1)

        stripped = strip_ansi(buffer)
        for i, regex in enumerate(compiled):
            m = regex.search(stripped)
            if m:
                print(f"[init]   -> MATCHED pattern {i}: {patterns[i]!r}", flush=True)
                buffer = ""
                return i

    print(f"\n[init] ERROR: timeout ({timeout}s) waiting for: {patterns}", file=sys.stderr, flush=True)
    print(f"[init] last 2000 chars of STRIPPED buffer:", file=sys.stderr, flush=True)
    print(f"{strip_ansi(buffer)[-2000:]}", file=sys.stderr, flush=True)
    sys.exit(1)


# ---------------------------------------------------------------------
# Steps 1-10: simple sequential prompts.
# ---------------------------------------------------------------------

# 1. Work path (default)
wait_and_send(
    r"Work path \[[^\]]*\]:",
    send_text="",
    step="Step 1/14: Work path (default)",
)

# 2. pmaports path (default)
wait_and_send(
    r"pmaports path \[[^\]]*\]:",
    send_text="",
    step="Step 2/14: pmaports path (default)",
)

# 3. Channel
wait_and_send(
    r"Channel \[[^\]]*\]:",
    send_text=channel,
    step=f"Step 3/14: Channel = {channel}",
)

# 4. Vendor (xiaomi, FIXED)
wait_and_send(
    r"Vendor \[[^\]]*\]:",
    send_text=VENDOR,
    step=f"Step 4/14: Vendor = {VENDOR}",
)

# 5. Device codename (polaris, FIXED)
wait_and_send(
    r"Device codename:",
    send_text=DEVICE,
    step=f"Step 5/14: Device = {DEVICE}",
)

# 6. Username (default 'user')
wait_and_send(
    r"Username \[[^\]]*\]:",
    send_text="",
    step="Step 6/14: Username (default: user)",
)

# 7. Audio backend provider
wait_and_send(
    r"Provider \[default\]:",
    send_text=audio,
    step=f"Step 7/14: Audio backend = {audio}",
)

# 8. WiFi backend provider
wait_and_send(
    r"Provider \[default\]:",
    send_text=wifi,
    step=f"Step 8/14: WiFi backend = {wifi}",
)

# 9. USB-moded default profile
wait_and_send(
    r"Provider \[default\]:",
    send_text=usb_mode,
    step=f"Step 9/14: USB mode = {usb_mode}",
)

# 10. User interface
wait_and_send(
    r"User interface \[[^\]]*\]:",
    send_text=ui,
    step=f"Step 10/14: User interface = {ui}",
)

# ---------------------------------------------------------------------
# Step 11 & 12: UI extra package (CONDITIONAL) + systemd install.
# ---------------------------------------------------------------------
print(f"\n[init] Step 11-12/14: UI extra package (if any) + systemd", flush=True)

index = wait_for_either([
    r"Enable this package\? \(y/n\) \[n\]:",
    r"Install systemd\? \(default/always/never\) \[default\]:",
], timeout=300)

if index == 0:
    # UI extra package prompt appeared → answer it, then expect systemd.
    print(f"[init]   -> UI extra package prompt found, sending: {ui_extra!r}", flush=True)
    child.sendline(ui_extra)
    wait_and_send(
        r"Install systemd\? \(default/always/never\) \[default\]:",
        send_text=systemd,
        step=f"Step 12/14: systemd = {systemd}",
    )
else:
    # No extra-package prompt → systemd prompt appeared directly.
    print(f"[init]   -> no UI extra package prompt (UI has none)", flush=True)
    print(f"[init]   -> sending systemd choice: {systemd!r}", flush=True)
    child.sendline(systemd)

# ---------------------------------------------------------------------
# Steps 13-17: more sequential prompts.
# ---------------------------------------------------------------------

# 13. "Change additional options?" → no (default)
wait_and_send(
    r"Change them\? \(y/n\) \[n\]:",
    send_text="",
    step="Step 13/14: Change additional options? (no)",
)

# 14. Extra packages
wait_and_send(
    r"Extra packages \[none\]:",
    send_text=extras_str,
    step=f"Step 14/14: Extra packages = {extras_str}",
)

# 15. Timezone
wait_and_send(
    r"Use this timezone instead of GMT\? \(y/n\) \[y\]:",
    send_text="",
    step=f"Step 15/17: Timezone (default = host = {TIMEZONE})",
)

# ---------------------------------------------------------------------
# Step 16: Locale — may prompt ONCE or TWICE.
# ---------------------------------------------------------------------
print(f"\n[init] Step 16/17: Locale = {LOCALE} (loop until hostname)", flush=True)
locale_attempts = 0
while True:
    idx = wait_for_either([
        r"Locale \[[^\]]*\]:",
        r"Device hostname[^:]*\[[^\]]*\]:",
    ], timeout=300)
    if idx == 0:
        locale_attempts += 1
        if locale_attempts > 6:
            print(f"[init] ERROR: too many locale prompts ({locale_attempts})", file=sys.stderr, flush=True)
            sys.exit(1)
        print(f"[init]   -> Locale prompt #{locale_attempts}, sending: {LOCALE!r}", flush=True)
        child.sendline(LOCALE)
    else:
        # Hostname prompt matched.
        print(f"[init]   -> Hostname prompt found (locale done after {locale_attempts} attempt(s))", flush=True)
        print(f"[init]   -> sending: <empty> (default hostname)", flush=True)
        child.sendline("")
        break

# 17. Build outdated packages
wait_and_send(
    r"Build outdated packages.*\(y/n\) \[y\]:",
    send_text="y",
    step="Step 17/17: Build outdated packages? (yes)",
)

# ---------------------------------------------------------------------
# Wait for pmbootstrap init to finish (EOF).
# ---------------------------------------------------------------------
print("\n[init] Waiting for pmbootstrap init to finish...", flush=True)
deadline = time.time() + 1800
finished = False
while time.time() < deadline:
    chunk = read_available(timeout=1.0)
    if chunk:
        sys.stdout.write(chunk)
        sys.stdout.flush()
    # Check for EOF: pexpect's eof() returns True if the child has exited
    # AND we've read all remaining data. But we also need to handle the
    # case where os.read returns empty (EOF on the fd).
    try:
        if child.eof():
            finished = True
            break
    except Exception:
        pass
    # Also check if the process is still alive
    if not child.isalive():
        # Drain any remaining output
        remaining = read_available(timeout=0.5)
        if remaining:
            sys.stdout.write(remaining)
            sys.stdout.flush()
        finished = True
        break

if not finished:
    print(f"\n[init] ERROR: pmbootstrap init did not finish within 1800s", file=sys.stderr, flush=True)
    sys.exit(1)

# Drain any final output
try:
    child.expect(pexpect.EOF, timeout=10)
except Exception:
    pass

print("\n[init] ===========================================", flush=True)
print("[init] pmbootstrap init completed successfully!", flush=True)
print("[init] ===========================================\n", flush=True)
