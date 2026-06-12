# Installation

Complete install guide for Keyward across every supported platform. If you just want the fastest path, do the [marketplace quick start](#marketplace-quick-start) and jump to the per-platform **deps + permissions** note for your OS. If you'd rather read the code before trusting it with your prompts, use the [manual clone + symlink](#manual-install-clone--symlink) method — it produces an identical install, just explicit.

See also: [[Home]] · [[Configuration]] · [[Troubleshooting]] · [[Security-Model]] · [[FAQ]]

---

## Contents

- [Requirements](#requirements)
- [How the install is wired](#how-the-install-is-wired)
- [Marketplace quick start](#marketplace-quick-start)
- [Manual install (clone + symlink)](#manual-install-clone--symlink)
  - [macOS](#macos)
  - [Linux (X11)](#linux-x11)
  - [Linux (Wayland)](#linux-wayland)
  - [Windows (native)](#windows-native)
  - [Windows + WSL](#windows--wsl)
- [Verifying the install](#verifying-the-install)
- [What "installed but no auto-paste" means](#what-installed-but-no-auto-paste-means)
- [Updating](#updating)
- [Uninstall](#uninstall)

---

## Requirements

| Requirement | Notes |
|---|---|
| **Python 3.9+** | Must be on `PATH` as `python3`. The whole runtime is stdlib — no `pip install`. Check with `python3 --version`. |
| **Claude Code** | With plugin + hooks support. Verify hooks load with `/hooks`. |
| **Per-platform automation tools** | The clipboard + keystroke backends. These are what differ per OS — see each section below. |

Keyward has **no third-party Python dependencies** and makes **no network calls**. Everything is Python standard library plus the OS clipboard/keystroke tools.

---

## How the install is wired

Whichever method you use, the end state is the same: Claude Code finds the plugin directory and registers one hook. The hook entry in `hooks/hooks.json` is literally:

```json
{
  "type": "command",
  "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/intercept.py",
  "timeout": 15
}
```

`${CLAUDE_PLUGIN_ROOT}` is set by Claude Code to wherever the plugin lives. The hook fires on every `UserPromptSubmit`. When it detects a secret it saves the value, blocks the original prompt, and spawns `scripts/automate_paste.py` (detached) to paste a sanitized version back in. The auto-paste step is the only part that needs the per-platform tools; **detection and saving work everywhere, including headless** (see [[Configuration]] and [what "installed but no auto-paste" means](#what-installed-but-no-auto-paste-means)).

---

## Marketplace quick start

The fastest path. In a Claude Code session:

```text
/plugin marketplace add AlbeMiglio/keyward
/plugin install keyward@keyward
```

Then **restart Claude Code** (hooks load at session start; they will not appear in a session that was already running). After restart:

1. **macOS** — grant Accessibility permission to your terminal app, or auto-paste fails silently. See the [macOS](#macos) deps note.
2. **Linux** — install the per-platform tools (`xdotool`+`xclip` on X11, `wtype`+`wl-clipboard` on Wayland). See [Linux X11](#linux-x11) / [Linux Wayland](#linux-wayland).
3. **Windows** — PowerShell ships with the OS; nothing extra unless group policy blocks `SendKeys`.

Then [verify with `/hooks`](#verifying-the-install).

> The marketplace install and the manual install are functionally identical. Pick manual if you want the source checked out somewhere you control and readable before first use.

---

## Manual install (clone + symlink)

The pattern is the same on every platform — **clone the repo, symlink it into `~/.claude/plugins/keyward`, install the OS tools, grant any permission, restart, verify** — but the exact commands and the deps differ. Each section below is self-contained; follow the one for your OS.

The symlink approach (rather than copying) means a `git pull` in the clone updates the installed plugin in place. If your platform can't make symlinks, copy instead and re-copy on update.

---

### macOS

**1. Install platform deps.** macOS ships with everything Keyward needs on this platform — `osascript`, `pbcopy`, and `pbpaste` are all built in. Nothing to install.

**2. Clone the repo:**

```bash
git clone https://github.com/AlbeMiglio/keyward.git ~/keyward
```

**3. Symlink into the plugin directory:**

```bash
mkdir -p ~/.claude/plugins
ln -s ~/keyward ~/.claude/plugins/keyward
```

**4. Grant Accessibility permission to your terminal app.** This is the step people miss. The auto-paste uses `osascript` → System Events to send `Cmd+V` + Return, and macOS blocks synthetic keystrokes from apps that lack Accessibility.

- Open **System Settings → Privacy & Security → Accessibility**
- Click **+** and add the app you run Claude Code in: **Terminal.app**, **iTerm**, **Ghostty**, **Warp**, **Alacritty**, **kitty**, **WezTerm**, VS Code's integrated terminal (add **Visual Studio Code**), etc.
- Toggle it **on**
- **Fully quit and reopen** that terminal app — the permission is read at process start

Without this grant, Keyward still saves the secret and puts the sanitized text on your clipboard; you just paste it manually (`Cmd+V` + Return). See [[Troubleshooting]] for confirming the permission with a one-liner.

**5. Restart Claude Code.** Quit the current session, then:

```bash
claude
```

**6. Verify** — see [Verifying the install](#verifying-the-install).

---

### Linux (X11)

Auto-paste on X11 uses `xdotool` (keystrokes) plus `xclip` or `xsel` (clipboard). X11 permits synthetic input by default, so **no permission grant is needed**.

**1. Install platform deps:**

```bash
# Debian / Ubuntu
sudo apt install python3 xdotool xclip

# Fedora / RHEL
sudo dnf install python3 xdotool xclip

# Arch
sudo pacman -S python xdotool xclip
```

`xsel` is an accepted substitute for `xclip` — Keyward auto-detects whichever is present (`xclip` is preferred). You need **one** clipboard tool plus `xdotool`.

**2. Clone the repo:**

```bash
git clone https://github.com/AlbeMiglio/keyward.git ~/keyward
```

**3. Symlink into the plugin directory:**

```bash
mkdir -p ~/.claude/plugins
ln -s ~/keyward ~/.claude/plugins/keyward
```

**4. Restart Claude Code**, then [verify](#verifying-the-install).

> **Are you actually on X11?** Run `echo $XDG_SESSION_TYPE`. If it prints `wayland`, follow the [Wayland](#linux-wayland) section instead — Keyward picks its backend from `WAYLAND_DISPLAY` / `XDG_SESSION_TYPE` at runtime, and the X11 tools won't be used under a Wayland session.

---

### Linux (Wayland)

> **⚠️ Wayland auto-paste is compositor-dependent.** Synthetic keystroke injection via `wtype` requires the compositor to implement the `virtual-keyboard-v1` protocol.
>
> | Compositor | Auto-paste |
> |---|---|
> | **Sway** | ✅ works |
> | **Hyprland** | ✅ works |
> | **KDE Plasma (KWin)** | ⚠️ version-dependent |
> | **GNOME (Mutter)** | ❌ blocked by default, no fix without an extension |
>
> If your compositor blocks `wtype`, Keyward still saves the secret and sets the clipboard — you finish with `Ctrl+V` + Enter manually. Consider exporting `KEYWARD_DISABLE_PASTE=1` (see [[Configuration]]) so it doesn't even attempt the keystroke.

**1. Install platform deps:**

```bash
# Debian / Ubuntu
sudo apt install python3 wtype wl-clipboard

# Fedora
sudo dnf install python3 wtype wl-clipboard

# Arch
sudo pacman -S python wtype wl-clipboard
```

`wl-clipboard` provides `wl-copy` / `wl-paste`.

**2. Clone the repo:**

```bash
git clone https://github.com/AlbeMiglio/keyward.git ~/keyward
```

**3. Symlink into the plugin directory:**

```bash
mkdir -p ~/.claude/plugins
ln -s ~/keyward ~/.claude/plugins/keyward
```

**4. Test whether your compositor supports `wtype` _before_ relying on auto-paste:**

```bash
echo "keyward wtype test" | wl-copy
sleep 2 && wtype -M ctrl v -m ctrl
# focus a text editor during the 2s window; if the text appears, you're good
```

If `wtype` prints `Compositor does not support virtual_keyboard_v1` (or nothing pastes), you're on an unsupported compositor. Auto-paste will degrade to "save + clipboard set, paste manually." Set `KEYWARD_DISABLE_PASTE=1` in your shell rc to skip the failing keystroke attempt entirely.

**5. Restart Claude Code**, then [verify](#verifying-the-install).

---

### Windows (native)

Auto-paste on Windows uses PowerShell: `Set-Clipboard` / `Get-Clipboard` for the clipboard and `System.Windows.Forms.SendKeys` for `Ctrl+V` + `{ENTER}`. PowerShell ships with Windows — **no extra install** beyond Python.

**1. Install Python 3.9+** if you don't have it:

```powershell
winget install Python.Python.3.12
```

…or download from [python.org](https://www.python.org/downloads/). During the installer, tick **"Add python.exe to PATH"**. Confirm `python3` resolves:

```powershell
python3 --version
```

(If only `python` works and not `python3`, see the note in [[Troubleshooting]] about the Windows `python3` alias / App Execution Aliases.)

**2. Clone the repo:**

```powershell
git clone https://github.com/AlbeMiglio/keyward.git "$env:USERPROFILE\keyward"
```

**3. Link or copy into the plugins directory:**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\plugins"

# Preferred — symlink (needs Administrator OR Developer Mode enabled):
New-Item -ItemType SymbolicLink `
    -Path "$env:USERPROFILE\.claude\plugins\keyward" `
    -Target "$env:USERPROFILE\keyward"

# Fallback — copy (use this if symlinks aren't available):
Copy-Item -Recurse "$env:USERPROFILE\keyward" "$env:USERPROFILE\.claude\plugins\keyward"
```

To enable Developer Mode (lets non-admin users create symlinks): **Settings → Privacy & security → For developers → Developer Mode → On**.

**4. Restart Claude Code**, then [verify](#verifying-the-install).

No permission grant is required — `SendKeys` targets the foreground window by default. Some enterprise group policies disable `SendKeys`; if yours does, Keyward falls back to clipboard-only mode (secret saved, sanitized text on clipboard, paste manually). See [[Troubleshooting]].

---

### Windows + WSL

If you run Claude Code **inside WSL**, the hook executes inside the Linux VM, but the window with focus is hosted by Windows. Crossing that boundary with synthetic keystrokes is fragile and not reliable. Two supported approaches:

**Recommended — install on the WSL (Linux) side, accept manual paste:**

```bash
# inside WSL
git clone https://github.com/AlbeMiglio/keyward.git ~/keyward
mkdir -p ~/.claude/plugins
ln -s ~/keyward ~/.claude/plugins/keyward
```

Then put this in your shell rc (`~/.bashrc` / `~/.zshrc`) so Claude Code inherits it:

```bash
export KEYWARD_DISABLE_PASTE=1
```

Detection and saving work normally; auto-paste is skipped (it wouldn't cross to the Windows host reliably anyway). You copy the sanitized text and paste it yourself. If you run an X server (VcXsrv / X410 / GWSL) and Claude Code in an X11 app inside WSL, you _can_ install the [Linux X11](#linux-x11) tools and get auto-paste **within that X session** — but the common Windows-host-terminal → WSL setup should use `KEYWARD_DISABLE_PASTE=1`.

**Alternative — run Claude Code natively on Windows** instead of in WSL, and follow [Windows (native)](#windows-native). Then auto-paste works against the foreground Windows window.

---

## Verifying the install

In a Claude Code session, run:

```text
/hooks
```

You should see a `UserPromptSubmit` entry pointing at `intercept.py`, e.g.:

```text
UserPromptSubmit  →  python3 /Users/you/.claude/plugins/keyward/hooks/intercept.py
```

(The path reflects wherever the plugin is installed.)

Then exercise the **detection layer** directly — this needs no display server and works on every platform, so it's the cleanest proof the engine runs:

```bash
echo '{"user_prompt": "deploy with ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  | python3 ~/.claude/plugins/keyward/scripts/detect.py
```

Expected output (a `github_pat_classic` slot, `source: "regex"`):

```json
{"secrets": [{"name": "github_pat_classic", "value": "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "span": [12, 52], "source": "regex"}], "raw_mode": false}
```

To do a live end-to-end check, type a message with a throwaway/example key in chat and watch the original get blocked and a sanitized version come back. For the most realistic test, use a real-format-but-dead token. More standalone diagnostics (including how to run the orchestrator) are in [[Troubleshooting]].

---

## What "installed but no auto-paste" means

Keyward is **two layers**, and they have different requirements:

1. **Detect + save + sanitize** (`detect.py` + `intercept.py`) — pure Python stdlib. Works on every platform, including SSH, headless, Docker, and unsupported Wayland compositors. If this layer runs, your secret is saved to `~/.claude/secrets/<name>.txt` (chmod 600) and the raw value is kept out of the blocked prompt.
2. **Auto-paste** (`automate_paste.py`) — needs the OS clipboard/keystroke tools and a display server. This is the layer that's platform-sensitive (macOS Accessibility, X11 tools, Wayland compositor support, Windows SendKeys policy).

So "Keyward saved my key but didn't paste the clean prompt" is a **layer-2** condition, not a broken install — the security part worked, only the convenience automation didn't. The sanitized text is on your clipboard; paste it with `Cmd/Ctrl+V` + Enter, or set `KEYWARD_DISABLE_PASTE=1` to make manual-paste the explicit default. Diagnosing _why_ layer 2 didn't fire is covered in [[Troubleshooting]].

---

## Updating

**Marketplace install:**

```text
/plugin marketplace update keyward
```

then restart Claude Code.

**Manual (symlinked) install** — pull the clone; the symlink picks it up:

```bash
git -C ~/keyward pull
```

Restart Claude Code so the reloaded hook is registered.

**Manual (copied) install** — re-copy over the old directory, then restart:

```bash
# macOS / Linux
git -C ~/keyward pull
rm -rf ~/.claude/plugins/keyward
cp -R ~/keyward ~/.claude/plugins/keyward
```

```powershell
# Windows (copied install)
git -C "$env:USERPROFILE\keyward" pull
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\plugins\keyward"
Copy-Item -Recurse "$env:USERPROFILE\keyward" "$env:USERPROFILE\.claude\plugins\keyward"
```

---

## Uninstall

**1. Remove the plugin from Claude Code.**

Marketplace install:

```text
/plugin uninstall keyward@keyward
```

Manual install — delete the symlink or copied directory:

```bash
# macOS / Linux
rm ~/.claude/plugins/keyward          # symlink: removes only the link, not your clone
# if you copied instead of symlinking:
rm -rf ~/.claude/plugins/keyward
```

```powershell
# Windows
Remove-Item "$env:USERPROFILE\.claude\plugins\keyward"            # symlink
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\plugins\keyward"  # copied
```

**2. Restart Claude Code** and confirm with `/hooks` that the `UserPromptSubmit` → `intercept.py` entry is gone.

**3. (Optional) Remove saved secrets and logs.** Uninstalling the plugin does **not** delete your vault. To wipe it:

```bash
# macOS / Linux — review first, then remove
ls -la ~/.claude/secrets/
rm -rf ~/.claude/secrets/
```

```powershell
# Windows
Get-ChildItem "$env:USERPROFILE\.claude\secrets"
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\secrets"
```

This also removes the error log at `~/.claude/secrets/.last-error`. Prefer per-slot deletion? Use `/key-rm <name>` while the plugin is still installed (it zero-overwrites before unlinking — best-effort, not guaranteed on SSD/COW filesystems; see [[Security-Model]]).

**4. (Optional) Remove the clone and any env var.** Delete `~/keyward` if you cloned manually, and remove any `KEYWARD_DISABLE_PASTE` / `KEYWARD_USE_GITLEAKS` lines you added to your shell rc.

**5. (Optional) Revoke the macOS Accessibility grant** for your terminal app in **System Settings → Privacy & Security → Accessibility** if you added it only for Keyward.
