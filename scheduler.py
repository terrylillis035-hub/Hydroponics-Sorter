#!/usr/bin/env python3
"""
scheduler.py — Runs on YOUR COMPUTER (not the Pi)
Fetches today's sunrise/sunset, calculates the two watering windows,
then SSH's into the Raspberry Pi to trigger pump_controller.py.

SETUP:
  1. pip install requests paramiko astral schedule
  2. Copy scheduler/config.example.json → scheduler/config.json
  3. Fill in your coordinates and Pi connection details
  4. python3 scheduler.py

IMPORTANT: config.json is listed in .gitignore and will never be committed.
           It contains your location and device credentials.
           Never commit config.json — use config.example.json as the template.
"""

import json
import logging
import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import paramiko          # pip install paramiko
import schedule          # pip install schedule
from astral import LocationInfo
from astral.sun import sun   # pip install astral

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG  — loaded from config.json (gitignored, never committed)
#  Copy config.example.json → config.json and fill in your values.
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_FILE  = Path(__file__).parent / "config.json"          # gitignored
EXAMPLE_FILE = Path(__file__).parent / "config.example.json"

DEFAULT_CONFIG = {
    "latitude":   0.0000,
    "longitude":  0.0000,
    "timezone":   "America/Chicago",
    "elevation":  0,

    "pi_host":     "raspberrypi.local",
    "pi_port":     22,
    "pi_user":     "pi",
    "pi_password": "",
    "pi_key_path": "~/.ssh/id_rsa",
    "pi_script":   "/home/pi/hydro/pump_controller.py",

    "gpio_pin":       17,
    "pump_duration":  600,

    "sunrise_offset": 0,
    "sunset_offset":  -60,

    "log_file":   "scheduler.log",   # gitignored
    "state_file": "schedule_state.json",  # gitignored
}


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception as e:
            print(f"Warning: could not read config.json ({e}), using defaults.")
    else:
        print(f"\n⚠  config.json not found.")
        print(f"   Copy config.example.json → config.json and fill in your values.")
        print(f"   config.json is gitignored and will never be committed.\n")
        # Write a blank config so the user has something to edit
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        print(f"   A blank config.json has been created for you at:\n   {CONFIG_FILE}\n")
    return cfg


CFG = load_config()

# ── Logging (log file is gitignored) ─────────────────────────────────────────
log_path = Path(__file__).parent / CFG["log_file"]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("hydro.scheduler")

STATE_FILE   = Path(__file__).parent / CFG["state_file"]   # gitignored
TRIGGER_FILE = Path(__file__).parent / "manual_trigger.flag"  # gitignored


# ─────────────────────────────────────────────────────────────────────────────
#  SUN TIMES
# ─────────────────────────────────────────────────────────────────────────────

def get_sun_times(date=None) -> dict:
    tz  = ZoneInfo(CFG["timezone"])
    loc = LocationInfo(
        name="Garden", region="",
        timezone=CFG["timezone"],
        latitude=CFG["latitude"],
        longitude=CFG["longitude"],
    )
    s = sun(loc.observer, date=date or datetime.now(tz).date(), tzinfo=tz)
    return {"sunrise": s["sunrise"], "sunset": s["sunset"]}


def watering_times(date=None) -> tuple:
    times   = get_sun_times(date)
    morning = times["sunrise"] + timedelta(minutes=CFG["sunrise_offset"])
    evening = times["sunset"]  + timedelta(minutes=CFG["sunset_offset"])
    return morning, evening


# ─────────────────────────────────────────────────────────────────────────────
#  SSH TRIGGER
# ─────────────────────────────────────────────────────────────────────────────

def ssh_run_pump(label: str):
    host     = CFG["pi_host"]
    port     = CFG["pi_port"]
    user     = CFG["pi_user"]
    password = CFG.get("pi_password", "")
    key_path = Path(CFG["pi_key_path"]).expanduser()
    script   = CFG["pi_script"]
    pin      = CFG["gpio_pin"]
    duration = CFG["pump_duration"]

    cmd = f"python3 {script} --pin {pin} --duration {duration}"
    log.info(f"[{label}] Connecting to {user}@{host}:{port}")

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = dict(hostname=host, port=port, username=user, timeout=15)
        if password:
            connect_kwargs["password"] = password
        elif key_path.exists():
            connect_kwargs["key_filename"] = str(key_path)

        client.connect(**connect_kwargs)
        log.info(f"[{label}] SSH connected ✓")

        bg_cmd = f"nohup {cmd} > /tmp/pump_last.log 2>&1 &"
        stdin, stdout, stderr = client.exec_command(bg_cmd)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            log.info(f"[{label}] Pump command dispatched ✓")
        else:
            err = stderr.read().decode().strip()
            log.error(f"[{label}] Command failed (exit {exit_status}): {err}")

        client.close()
        write_event(label, "success")

    except paramiko.AuthenticationException:
        log.error(f"[{label}] SSH auth failed — check config.json credentials")
        write_event(label, "auth_error")
    except Exception as e:
        log.error(f"[{label}] SSH error: {e}")
        write_event(label, f"error: {e}")


def write_event(label: str, status: str):
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    events = state.get("events", [])
    events.insert(0, {"time": datetime.now().isoformat(), "label": label, "status": status})
    state["events"]        = events[:50]
    state["next_morning"]  = watering_times()[0].isoformat()
    state["next_evening"]  = watering_times()[1].isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
#  DAILY SCHEDULE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def schedule_today():
    schedule.clear()
    morning, evening = watering_times()
    now = datetime.now(ZoneInfo(CFG["timezone"]))

    log.info("=" * 60)
    log.info(f"  Today's schedule  ({now.strftime('%A %B %d, %Y')})")
    log.info(f"  ☀  Morning water:  {morning.strftime('%H:%M:%S %Z')}")
    log.info(f"  🌆 Evening water:  {evening.strftime('%H:%M:%S %Z')}")
    log.info("=" * 60)

    def _run_if_future(run_time, label):
        if run_time > now:
            tag = run_time.strftime("%H:%M")
            schedule.every().day.at(tag, CFG["timezone"]).do(
                lambda l=label: ssh_run_pump(l)
            ).tag(label)
            log.info(f"  Scheduled [{label}] at {tag}")
        else:
            log.info(f"  Skipped   [{label}] — already passed today")

    _run_if_future(morning, "SUNRISE")
    _run_if_future(evening, "PRE-SUNSET")
    schedule.every().day.at("00:00", CFG["timezone"]).do(schedule_today).tag("daily-rebuild")
    write_event("schedule_rebuilt", "ok")


# ─────────────────────────────────────────────────────────────────────────────
#  MANUAL TRIGGER WATCHER
# ─────────────────────────────────────────────────────────────────────────────

def watch_manual_trigger():
    """Background thread: watches for manual_trigger.flag from the dashboard."""
    while True:
        if TRIGGER_FILE.exists():
            try:
                label = TRIGGER_FILE.read_text().strip() or "MANUAL"
                TRIGGER_FILE.unlink()
                log.info(f"Manual trigger: {label}")
                threading.Thread(target=ssh_run_pump, args=(label,), daemon=True).start()
            except Exception as e:
                log.error(f"Manual trigger error: {e}")
        time.sleep(2)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("╔══════════════════════════════════════╗")
    log.info("║  Hydroponic Garden Scheduler  v1.0   ║")
    log.info("╚══════════════════════════════════════╝")
    log.info("Config loaded from: config.json (gitignored)")

    schedule_today()

    t = threading.Thread(target=watch_manual_trigger, daemon=True)
    t.start()
    log.info("Running… (Ctrl+C to stop)\n")

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Scheduler stopped.")
