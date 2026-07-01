# Upstream Changes

Changes pulled from community forks into pwnagotchi-ng. All changes are on the `dev` branch.

---

## From jayofelony/pwnagotchi

Source: https://github.com/jayofelony/pwnagotchi  
Tip commit at time of import: `6cdc8922`  
Import date: 2026-07-01

### Why jayofelony?
Most actively maintained pwnagotchi fork (v2.9.5.4, January 2026). Tracks modern Raspberry Pi OS (Bookworm), bettercap 2.40.x, and Python 3.9+. Diverged from evilsocket/master in 2021 and has ~750 commits of improvements.

---

### 1. Requirements modernization

**File:** `requirements.txt`

Removed the entire TF1.x AI stack (tensorflow 1.13.1, stable-baselines 2.7.0, scipy 1.3.1, gym 0.14.0, gast 0.2.2) — these don't build on any modern system. Replaced old pinned versions with unpinned modern equivalents. Added Pi hardware packages missing from evilsocket: `rpi-lgpio`, `rpi_hardware_pwm`, `gpiozero`, `smbus`, `pydrive2`.

Removed AI packages: `tensorflow`, `tensorflow-estimator`, `stable-baselines`, `gym`, `scipy`, `gast`  
Added: `rpi-lgpio`, `rpi_hardware_pwm`, `gpiozero`, `smbus`, `pydrive2`, `setuptools`

---

### 2. New plugins

**Directory:** `pwnagotchi/plugins/default/`

| Plugin | What it does |
|--------|-------------|
| `fix_services.py` | Fixes conflicting system services that interfere with external WiFi adapters on boot |
| `gdrivesync.py` | Google Drive sync for handshakes and session data |
| `pisugar3.py` | PiSugar3 battery monitor and management |

---

### 3. Updated plugins

All existing plugins taken from jayofelony master (`6cdc8922`): `auto-update`, `bt-tether` (major NetworkManager overhaul), `gps`, `grid`, `gpio_buttons`, `logtail`, `memtemp`, `onlinehashcrack`, `session-stats`, `switcher`, `ups_lite`, `watchdog`, `webcfg`, `webgpsmap`, `wigle`, `wpa-sec`, plus `plugins/__init__.py` and `plugins/cmd.py`.

Key improvements in `bt-tether`: full NetworkManager integration, DNS config, persistent IP settings.

---

### 4. Bettercap websocket & API compatibility

**File:** `pwnagotchi/bettercap.py`

The original used bettercap 2.28 APIs. jayofelony targets bettercap 2.40.x. Changes:
- Robust websocket reconnection with ping/pong (configurable `ping_timeout=180`, `ping_interval=15`)
- Exponential backoff on connection failure
- `ConnectionRefusedError` handling (bettercap not yet ready)
- `session()` now accepts sub-path argument (`"session/wifi"`, `"session/ble"`)
- Increased retry count on HTTP requests

---

### 5. Agent fixes

**File:** `pwnagotchi/agent.py`

- Bettercap config defaults (no longer crashes if `hostname`/`port` etc. absent from config)
- Fixed AP whitelist filtering logic (was inverted; also checks first 13 chars of MAC)
- `_thread.start_new_thread` → `threading.Thread(daemon=True)` for session fetcher
- Added `_restart()` method (restarts pwnagotchi process instead of hard reboot)
- Fixed typo: "acces points" → "access points"
- Removed 20-char truncation of last pwned AP name in display

---

### 6. Automata fix

**File:** `pwnagotchi/automata.py`

Blind epoch recovery now calls `_restart()` (graceful) instead of `_reboot()` (hard reboot).

---

### 7. Display hardware drivers

**Directory:** `pwnagotchi/ui/hw/`

104 display driver files (up from ~12 in evilsocket). Added support for:
- Waveshare e-ink displays: 1in02, 1in54 V2, 2in13 V2/V3/V4, 2in13b V3/V4, 2in66, 2in7 V2, 2in9 V2, 3in52, 3in7, 4in01f, 4in2, 4in2 V2, 4in26, 5in65f, 5in79, 5in83 V2, 7in3f, 7in5 V2, 7in5 HD, and many more
- Waveshare LCD modules: 0.96", 1.14", 1.28", 1.3", 1.47", 1.54", 1.69", 1.8", 1.9", 2.0", 2.4"
- Waveshare OLED LCD variants
- WeAct 2.9" e-ink
- DFRobot v1/v2 variants
- Adafruit SSD1306 I2C OLED, 2in13 V3
- InkyV2 support

---

## Deferred (for UI milestone)

The following jayofelony changes were reviewed but NOT imported yet:

| File | Reason deferred |
|------|----------------|
| `pwnagotchi/ui/view.py` | Large color mode refactor (adds RGB/grayscale/16-bit support). Needs dedicated review as part of UI redesign work. |
| `pwnagotchi/utils.py` | 500-line diff touching config handling, backup, and NetworkManager integration. Review separately. |
| `bin/pwnagotchi` | 330-line diff (full launcher rewrite). Review with OS/builder milestone. |
| `builder/` | New 32-bit/64-bit image build system. Separate milestone. |
| `pwnagotchi/ai/` | AI code kept as-is from evilsocket (disabled by removing deps). Future milestone if AI is reimplemented. |
