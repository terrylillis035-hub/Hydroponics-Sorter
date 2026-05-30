# 🌿 Hydroponic Garden Scheduler

Automated two-cycle daily watering — **at sunrise** and **1 hour before sunset**, 10 minutes each.

```
YOUR COMPUTER  ──SSH──►  RASPBERRY PI
  scheduler.py              pump_controller.py
  dashboard.py              GPIO 17 → Relay → Pump
```

---

## ⚠ Security & Git Notes

The following files are listed in `.gitignore` and will **never** be committed:

| File | Why |
|---|---|
| `config.json` | Contains your GPS coordinates and device credentials |
| `*.log` | Runtime logs |
| `*_state.json` | Runtime state |
| `manual_trigger.flag` | Runtime trigger flag |

**Always use `config.example.json` as the template.** Copy it to `config.json` and fill in your real values locally.

---

## Directory Layout

```
hydro/
├── .gitignore                    ← Protects sensitive files
├── README.md
├── scheduler/
│   ├── scheduler.py              ← Runs on YOUR computer
│   ├── config.example.json       ← Safe template (committed)
│   └── config.json               ← YOUR real values (gitignored, never committed)
├── pi_scripts/
│   └── pump_controller.py        ← Deploy to Raspberry Pi
└── dashboard/
    └── dashboard.py              ← Web UI at localhost:5050
```

---

## Step 1 — Set Up the Raspberry Pi

### 1a. Copy the script to the Pi

```bash
scp pi_scripts/pump_controller.py pi@raspberrypi.local:/home/pi/hydro/
```

### 1b. Install RPi.GPIO on the Pi

```bash
ssh pi@raspberrypi.local
pip3 install RPi.GPIO
```

### 1c. Test the pump on the Pi

```bash
# Dry run first (no GPIO touched)
python3 /home/pi/hydro/pump_controller.py --dry-run

# Real run for 10 seconds to verify wiring
python3 /home/pi/hydro/pump_controller.py --duration 10
```

### 1d. Wiring

```
Raspberry Pi                  5V Relay Module
──────────────                ───────────────
GPIO 17 (Pin 11)  ──────────► IN
5V      (Pin 2)   ──────────► VCC
GND     (Pin 6)   ──────────► GND

Relay COM/NO ────────────────► Pump power circuit
```

> ⚠ Use a relay rated for your pump's voltage/current. For mains-voltage pumps, use an optoisolated relay and consult an electrician.

---

## Step 2 — Configure Your Computer

### 2a. Install Python dependencies

```bash
pip install requests paramiko astral schedule flask
```

### 2b. Set up SSH key auth (no stored passwords)

```bash
ssh-keygen -t rsa -b 4096     # skip if you already have a key
ssh-copy-id pi@raspberrypi.local
```

### 2c. Create your local config

```bash
cp scheduler/config.example.json scheduler/config.json
# Now edit config.json with your real values — it is gitignored
```

Key fields to update:

```json
{
  "latitude":  39.0997,
  "longitude": -94.5786,
  "timezone":  "America/Chicago",

  "pi_host":   "raspberrypi.local",
  "pi_user":   "pi",
  "pi_key_path": "~/.ssh/id_rsa"
}
```

Find your coordinates: https://www.latlong.net

---

## Step 3 — Run

### Terminal 1 — Scheduler

```bash
cd hydro/scheduler
python3 scheduler.py
```

### Terminal 2 — Dashboard

```bash
cd hydro/dashboard
python3 dashboard.py
# Open http://localhost:5050
```

---

## Step 4 — Auto-start on Boot (optional)

Create `/etc/systemd/system/hydro-scheduler.service`:

```ini
[Unit]
Description=Hydroponic Garden Scheduler
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/hydro/scheduler
ExecStart=/usr/bin/python3 scheduler.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable hydro-scheduler
sudo systemctl start  hydro-scheduler
```

---

## Adjusting the Schedule

Edit `config.json` and restart the scheduler:

```json
"sunrise_offset": 0,    // 0 = exactly at sunrise
"sunset_offset":  -60,  // -60 = 1 hour before sunset
"pump_duration":  600   // seconds (600 = 10 minutes)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| SSH auth fails | Verify `pi_host`, `pi_user`, `pi_key_path` in config.json |
| Pump doesn't activate | Run `--dry-run` on Pi first to isolate wiring vs software |
| Wrong sunrise/sunset times | Check `latitude`, `longitude`, `timezone` in config.json |
| `paramiko` not found | `pip install paramiko` on YOUR computer |
| `RPi.GPIO` not found | `pip3 install RPi.GPIO` ON THE PI |
