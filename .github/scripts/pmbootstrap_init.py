#!/usr/bin/env python3
"""
pmbootstrap_init.py — Drive `pmbootstrap init` non-interactively.

The device is fixed to xiaomi-polaris (per user requirement).
All other init choices are read from environment variables, which
are populated from GitHub Actions workflow_dispatch inputs.

Reference: the interactive prompt sequence observed in
"pmbootstrap --init.txt" (uploaded by the user).

Chinese font packages are ALWAYS added to the extra packages list,
regardless of what the user supplies in PMOS_EXTRA_PACKAGES.
"""

import os
import sys
import subprocess

# ---------------------------------------------------------------------
# Make sure pexpect is available (python3-pexpect should be installed
# by the workflow, but fall back to pip if not).
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

# Vendor / device are FIXED per user requirement — NOT configurable.
VENDOR = "xiaomi"
DEVICE = "polaris"

# Locale / timezone / hostname are fixed for a CN-oriented build.
LOCALE   = "zh_CN"
TIMEZONE = "Asia/Shanghai"   # must also be set on the host via timedatectl
HOSTNAME = ""                # empty = default (xiaomi-polaris)

# Chinese font packages — ALWAYS installed, no matter what.
CHINESE_FONTS = [
    "font-noto-cjk",         # Noto CJK (most comprehensive)
    "font-wqy-zenhei",       # 文泉驿正黑
    "font-wqy-microhei",     # 文泉驿微米黑
]

# ---------------------------------------------------------------------
# Build the extra-packages list (user extras + Chinese fonts, deduped).
# ---------------------------------------------------------------------
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
print("=" * 60, flush=True)


# ---------------------------------------------------------------------
# Helper: expect a prompt and optionally send a line.
# ---------------------------------------------------------------------
def expect_send(child, pattern, send_text="", timeout=1800, step=""):
    """Wait for `pattern`, then send `send_text` + newline."""
    if step:
        print(f"\n[init] {step}", flush=True)
    try:
        child.expect(pattern, timeout=timeout)
    except pexpect.exceptions.TIMEOUT:
        print(f"\n[init] ERROR: timeout waiting for: {pattern}", file=sys.stderr, flush=True)
        print(f"[init] last output:\n{child.before}", file=sys.stderr, flush=True)
        sys.exit(1)
    except pexpect.exceptions.EOF:
        print(f"\n[init] ERROR: pmbootstrap exited unexpectedly", file=sys.stderr, flush=True)
        print(f"[init] pattern not matched: {pattern}", file=sys.stderr, flush=True)
        print(f"[init] last output:\n{child.before}", file=sys.stderr, flush=True)
        sys.exit(1)
    if send_text:
        print(f"[init]   -> sending: {send_text!r}", flush=True)
        child.sendline(send_text)
    else:
        print(f"[init]   -> sending: <empty> (use default)", flush=True)
        child.sendline("")


# ---------------------------------------------------------------------
# Spawn pmbootstrap init.
# ---------------------------------------------------------------------
print("\n[init] spawning: pmbootstrap init\n", flush=True)
child = pexpect.spawn(
    "pmbootstrap init",
    timeout=1800,
    encoding="utf-8",
    maxread=20000,
)
# Echo all output to stdout so it shows up in the Actions log.
child.logfile = sys.stdout


# 1. Work path (default)
expect_send(child,
    r"Work path \[[^\]]*\]:",
    send_text="",
    step="Step 1/14: Work path (default)")

# 2. pmaports path (default)
expect_send(child,
    r"pmaports path \[[^\]]*\]:",
    send_text="",
    step="Step 2/14: pmaports path (default)")

# 3. Channel
expect_send(child,
    r"Channel \[[^\]]*\]:",
    send_text=channel,
    step=f"Step 3/14: Channel = {channel}")

# 4. Vendor (xiaomi, FIXED)
expect_send(child,
    r"Vendor \[[^\]]*\]:",
    send_text=VENDOR,
    step=f"Step 4/14: Vendor = {VENDOR}")

# 5. Device codename (polaris, FIXED)
expect_send(child,
    r"Device codename:",
    send_text=DEVICE,
    step=f"Step 5/14: Device = {DEVICE}")

# 6. Username (default 'user')
expect_send(child,
    r"Username \[[^\]]*\]:",
    send_text="",
    step="Step 6/14: Username (default: user)")

# 7. Audio backend provider
expect_send(child,
    r"Provider \[default\]:",
    send_text=audio,
    step=f"Step 7/14: Audio backend = {audio}")

# 8. WiFi backend provider
expect_send(child,
    r"Provider \[default\]:",
    send_text=wifi,
    step=f"Step 8/14: WiFi backend = {wifi}")

# 9. USB-moded default profile
expect_send(child,
    r"Provider \[default\]:",
    send_text=usb_mode,
    step=f"Step 9/14: USB mode = {usb_mode}")

# 10. User interface
expect_send(child,
    r"User interface \[[^\]]*\]:",
    send_text=ui,
    step=f"Step 10/14: User interface = {ui}")

# ---------------------------------------------------------------------
# Step 11 & 12: UI extra package (CONDITIONAL) + systemd install.
#
#   * Some UIs (plasma-mobile, plasma-desktop, plasma-bigscreen, etc.)
#     prompt: "Enable this package? (y/n) [n]:"
#   * ALL UIs prompt:  "Install systemd? (default/always/never) [default]:"
#
# We don't know in advance whether the extra-package prompt will
# appear, so we wait for either pattern and dispatch accordingly.
# ---------------------------------------------------------------------
print(f"\n[init] Step 11-12/14: UI extra package (if any) + systemd", flush=True)
index = child.expect([
    r"Enable this package\? \(y/n\) \[n\]:",
    r"Install systemd\? \(default/always/never\) \[default\]:",
], timeout=1800)

if index == 0:
    # UI extra package prompt appeared → answer it, then expect systemd.
    print(f"[init]   -> UI extra package prompt found, sending: {ui_extra!r}", flush=True)
    child.sendline(ui_extra)
    expect_send(child,
        r"Install systemd\? \(default/always/never\) \[default\]:",
        send_text=systemd,
        step=f"Step 12/14: systemd = {systemd}")
else:
    # No extra-package prompt → systemd prompt appeared directly.
    print(f"[init]   -> no UI extra package prompt (UI has none)", flush=True)
    print(f"[init]   -> sending systemd choice: {systemd!r}", flush=True)
    child.sendline(systemd)

# 13. "Change additional options?" → no (default)
expect_send(child,
    r"Change them\? \(y/n\) \[n\]:",
    send_text="",
    step="Step 13/14: Change additional options? (no)")

# 14. Extra packages
expect_send(child,
    r"Extra packages \[none\]:",
    send_text=extras_str,
    step=f"Step 14/14: Extra packages = {extras_str}")

# ---------------------------------------------------------------------
# Step 15: Timezone — "Use this timezone instead of GMT? (y/n) [y]:"
# (We pre-set the host TZ to Asia/Shanghai, so the default is correct.)
# ---------------------------------------------------------------------
expect_send(child,
    r"Use this timezone instead of GMT\? \(y/n\) \[y\]:",
    send_text="",
    step=f"Step 15/17: Timezone (default = host = {TIMEZONE})")

# ---------------------------------------------------------------------
# Step 16: Locale — may prompt ONCE or TWICE depending on readline
# tab-completion quirks. We loop and send "zh_CN" until we see the
# hostname prompt.
# ---------------------------------------------------------------------
print(f"\n[init] Step 16/17: Locale = {LOCALE} (loop until hostname)", flush=True)
locale_attempts = 0
while True:
    idx = child.expect([
        rf"Locale \[[^\]]*\]:",
        r"Device hostname[^:]*\[[^\]]*\]:",
    ], timeout=300)
    if idx == 0:
        locale_attempts += 1
        if locale_attempts > 4:
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

# ---------------------------------------------------------------------
# Step 17: "Build outdated packages during 'pmbootstrap install'? (y/n) [y]:"
# We always answer "y" — this is what the user picked in the file.
# ---------------------------------------------------------------------
expect_send(child,
    r"Build outdated packages.*\(y/n\) \[y\]:",
    send_text="y",
    step="Step 17/17: Build outdated packages? (yes)")

# ---------------------------------------------------------------------
# Wait for pmbootstrap init to finish.
# ---------------------------------------------------------------------
print("\n[init] Waiting for pmbootstrap init to finish...", flush=True)
try:
    child.expect(pexpect.EOF, timeout=1800)
except pexpect.exceptions.TIMEOUT:
    print(f"\n[init] ERROR: pmbootstrap init did not finish within timeout", file=sys.stderr, flush=True)
    print(f"[init] last output:\n{child.before}", file=sys.stderr, flush=True)
    sys.exit(1)

print("\n[init] ===========================================", flush=True)
print("[init] pmbootstrap init completed successfully!", flush=True)
print("[init] ===========================================\n", flush=True)
