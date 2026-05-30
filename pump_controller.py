#!/usr/bin/env python3
"""
pump_controller.py — Runs on the Raspberry Pi
Activates the pump relay on GPIO pin 17 for exactly 10 minutes.
Called remotely by the scheduler on your main computer.

Wiring:
  GPIO 17 (Pin 11) → Relay IN
  5V (Pin 2)       → Relay VCC
  GND (Pin 6)      → Relay GND

Usage:
  python3 pump_controller.py [--pin 17] [--duration 600] [--dry-run]

NOTE: pump.log and pump_state.json are runtime files — they are gitignored
and will never be committed to version control.
"""

import time
import argparse
import logging
import sys
import json
from datetime import datetime
from pathlib import Path

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "pump.log"   # gitignored
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pump")

# ── State file (gitignored — for dashboard to read) ───────────────────────────
STATE_FILE = Path(__file__).parent / "pump_state.json"   # gitignored


def write_state(running: bool, reason: str = "", started: str = ""):
    STATE_FILE.write_text(
        json.dumps({
            "running": running,
            "reason":  reason,
            "started": started,
            "updated": datetime.now().isoformat(),
        }, indent=2)
    )


def run_pump(pin: int, duration: int, dry_run: bool):
    """Activate pump relay for `duration` seconds."""
    reason  = "dry-run" if dry_run else "scheduled"
    started = datetime.now().isoformat()
    log.info(f"▶  Pump START — pin={pin}, duration={duration}s, mode={reason}")
    write_state(True, reason, started)

    try:
        if not dry_run:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)   # Energise relay → pump ON
            log.info(f"   GPIO {pin} HIGH (relay closed, pump running)")

        remaining = duration
        interval  = 30
        while remaining > 0:
            sleep_for = min(interval, remaining)
            time.sleep(sleep_for)
            remaining -= sleep_for
            if remaining > 0:
                log.info(f"   ⏱  {remaining}s remaining …")

    except KeyboardInterrupt:
        log.warning("   Interrupted by user — shutting pump off immediately.")

    finally:
        if not dry_run:
            try:
                import RPi.GPIO as GPIO
                GPIO.output(pin, GPIO.LOW)   # De-energise relay → pump OFF
                GPIO.cleanup()
                log.info(f"   GPIO {pin} LOW (relay open, pump stopped)")
            except Exception as e:
                log.error(f"   GPIO cleanup error: {e}")

        log.info("■  Pump STOP")
        write_state(False, reason, started)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hydroponic pump controller")
    parser.add_argument("--pin",      type=int,  default=17,  help="BCM GPIO pin (default: 17)")
    parser.add_argument("--duration", type=int,  default=600, help="Run duration in seconds (default: 600)")
    parser.add_argument("--dry-run",  action="store_true",    help="Simulate without touching GPIO")
    args = parser.parse_args()

    run_pump(args.pin, args.duration, args.dry_run)
