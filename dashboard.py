#!/usr/bin/env python3
"""
dashboard.py — Local web dashboard for the hydroponic scheduler.
Run alongside scheduler.py on your computer.

  pip install flask
  python3 dashboard.py
  → Open http://localhost:5050

NOTE: This file reads schedule_state.json and pump_state.json at runtime.
Both are listed in .gitignore and are never committed to version control.
"""

from flask import Flask, jsonify, render_template_string
from pathlib import Path
from datetime import datetime
import json

# Runtime state files — both gitignored
BASE     = Path(__file__).parent.parent / "scheduler"
STATE    = BASE / "schedule_state.json"       # gitignored
TRIGGER  = BASE / "manual_trigger.flag"       # gitignored
PI_STATE = Path(__file__).parent.parent / "pi_scripts" / "pump_state.json"  # gitignored

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hydro Garden Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Playfair+Display:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root {
    --green:    #00ff88;
    --green-dim:#00cc66;
    --teal:     #00e5cc;
    --amber:    #ffb347;
    --red:      #ff4e4e;
    --bg:       #060e09;
    --panel:    #0a180d;
    --border:   #1a3320;
    --text:     #c8e6c9;
    --muted:    #4a7a52;
    --font-mono:"Share Tech Mono", monospace;
    --font-disp:"Playfair Display", serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg); color: var(--text);
    font-family: var(--font-mono); min-height: 100vh; overflow-x: hidden;
  }
  body::before {
    content: ""; position: fixed; inset: 0;
    background-image:
      linear-gradient(var(--border) 1px, transparent 1px),
      linear-gradient(90deg, var(--border) 1px, transparent 1px);
    background-size: 40px 40px; opacity: .35;
    pointer-events: none; z-index: 0;
  }
  header {
    position: relative; z-index: 1;
    padding: 2rem 2.5rem 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: flex-end; gap: 1.5rem; flex-wrap: wrap;
  }
  .logo-icon { font-size: 2.8rem; line-height: 1; }
  .title-block h1 {
    font-family: var(--font-disp); font-size: 2rem; font-weight: 700;
    color: var(--green); letter-spacing: .02em;
    text-shadow: 0 0 24px rgba(0,255,136,.35);
  }
  .title-block .sub {
    font-size: .75rem; color: var(--muted);
    letter-spacing: .15em; text-transform: uppercase; margin-top: .25rem;
  }
  .live-clock {
    margin-left: auto; text-align: right; font-size: 1.6rem;
    color: var(--teal); text-shadow: 0 0 14px rgba(0,229,204,.4);
  }
  .live-clock .date-str { font-size: .72rem; color: var(--muted); margin-top: .15rem; }
  main {
    position: relative; z-index: 1;
    max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem;
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.4rem;
  }
  .panel {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.4rem 1.6rem;
    position: relative; overflow: hidden;
  }
  .panel::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, var(--green), transparent);
  }
  .panel-title {
    font-size: .68rem; color: var(--muted);
    letter-spacing: .18em; text-transform: uppercase; margin-bottom: 1rem;
    display: flex; align-items: center; gap: .5rem;
  }
  .panel-title::after { content: ""; flex: 1; height: 1px; background: var(--border); }
  .status-wrap { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.2rem; }
  .ring {
    width: 56px; height: 56px; border-radius: 50%;
    border: 3px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem; transition: border-color .4s, box-shadow .4s;
  }
  .ring.active { border-color: var(--green); box-shadow: 0 0 20px rgba(0,255,136,.5); animation: pulse 1.8s ease-in-out infinite; }
  @keyframes pulse {
    0%,100% { box-shadow: 0 0 12px rgba(0,255,136,.4); }
    50%      { box-shadow: 0 0 28px rgba(0,255,136,.8); }
  }
  .status-text .big { font-size: 1.1rem; color: var(--green); }
  .status-text .sm  { font-size: .72rem; color: var(--muted); margin-top: .2rem; }
  .sched-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: .65rem .9rem; border: 1px solid var(--border);
    border-radius: 7px; margin-bottom: .7rem; transition: background .2s;
  }
  .sched-row:hover { background: rgba(0,255,136,.04); }
  .sched-row .label { font-size: .78rem; color: var(--muted); }
  .sched-row .value { font-size: 1rem; color: var(--teal); }
  .badge { font-size: .62rem; padding: .2rem .55rem; border-radius: 99px; letter-spacing: .08em; }
  .badge-ok       { background: rgba(0,255,136,.12); color: var(--green); border: 1px solid rgba(0,255,136,.3); }
  .badge-upcoming { background: rgba(255,179,71,.1);  color: var(--amber); border: 1px solid rgba(255,179,71,.3); }
  .badge-done     { background: rgba(74,122,82,.1);   color: var(--muted); border: 1px solid var(--border); }
  .trigger-btn {
    width: 100%; padding: .85rem;
    background: linear-gradient(135deg, #0d2e18, #143d20);
    border: 1px solid var(--green-dim); border-radius: 8px;
    color: var(--green); font-family: var(--font-mono); font-size: .9rem;
    letter-spacing: .1em; cursor: pointer; transition: all .2s;
    margin-top: .7rem; text-transform: uppercase;
  }
  .trigger-btn:hover { background: linear-gradient(135deg, #143d20, #1a5228); box-shadow: 0 0 16px rgba(0,255,136,.2); }
  .trigger-btn:active { transform: scale(.98); }
  .trigger-btn:disabled { opacity: .4; cursor: not-allowed; }
  .log-list { max-height: 260px; overflow-y: auto; }
  .log-list::-webkit-scrollbar { width: 4px; }
  .log-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
  .log-entry {
    display: flex; gap: .8rem; align-items: flex-start;
    padding: .5rem 0; border-bottom: 1px solid rgba(26,51,32,.6); font-size: .75rem;
  }
  .log-entry:last-child { border-bottom: none; }
  .log-time   { color: var(--muted); white-space: nowrap; min-width: 5rem; }
  .log-label  { color: var(--teal); }
  .log-status { color: var(--green-dim); margin-left: auto; white-space: nowrap; }
  .log-status.err { color: var(--red); }
  .countdown {
    font-size: 2rem; color: var(--amber); text-align: center;
    padding: .8rem 0 .4rem; text-shadow: 0 0 16px rgba(255,179,71,.4); letter-spacing: .05em;
  }
  .countdown-label { text-align: center; font-size: .68rem; color: var(--muted); letter-spacing: .15em; text-transform: uppercase; }
  .span2 { grid-column: span 2; }
  #toast {
    position: fixed; bottom: 1.8rem; left: 50%; transform: translateX(-50%) translateY(4rem);
    background: var(--panel); border: 1px solid var(--green);
    color: var(--green); padding: .7rem 1.8rem; border-radius: 8px;
    font-size: .85rem; transition: transform .3s ease; z-index: 999;
    box-shadow: 0 0 24px rgba(0,255,136,.25); pointer-events: none;
  }
  #toast.show { transform: translateX(-50%) translateY(0); }
  @media (max-width: 640px) { .span2 { grid-column: span 1; } }
</style>
</head>
<body>
<header>
  <div class="logo-icon">🌿</div>
  <div class="title-block">
    <h1>Hydro Garden Control</h1>
    <div class="sub">Automated Hydroponic Scheduler — Raspberry Pi</div>
  </div>
  <div class="live-clock">
    <div id="clock">--:--:--</div>
    <div class="date-str" id="dateStr">---</div>
  </div>
</header>
<main>
  <div class="panel">
    <div class="panel-title">⚡ Pump Status</div>
    <div class="status-wrap">
      <div class="ring" id="statusRing">💧</div>
      <div class="status-text">
        <div class="big" id="statusText">IDLE</div>
        <div class="sm"  id="statusSub">Waiting for next cycle</div>
      </div>
    </div>
    <button class="trigger-btn" id="triggerBtn" onclick="manualTrigger()">
      ▶  Run Pump Now (Manual)
    </button>
  </div>
  <div class="panel">
    <div class="panel-title">📅 Today's Schedule</div>
    <div class="sched-row">
      <div><div class="label">☀ Morning (Sunrise)</div><div class="value" id="morningTime">--:--</div></div>
      <span class="badge" id="morningBadge">—</span>
    </div>
    <div class="sched-row">
      <div><div class="label">🌆 Evening (Pre-Sunset)</div><div class="value" id="eveningTime">--:--</div></div>
      <span class="badge" id="eveningBadge">—</span>
    </div>
  </div>
  <div class="panel">
    <div class="panel-title">⏳ Next Cycle In</div>
    <div class="countdown" id="countdown">--:--:--</div>
    <div class="countdown-label" id="countdownLabel">calculating…</div>
  </div>
  <div class="panel span2">
    <div class="panel-title">📋 Event Log</div>
    <div class="log-list" id="logList">
      <div class="log-entry"><span class="log-time">—</span><span class="log-label">Waiting for data…</span></div>
    </div>
  </div>
</main>
<div id="toast">Command sent ✓</div>
<script>
function tickClock() {
  const now = new Date();
  document.getElementById("clock").textContent = now.toLocaleTimeString("en-US",{hour12:false});
  document.getElementById("dateStr").textContent = now.toLocaleDateString("en-US",{weekday:"long",month:"long",day:"numeric",year:"numeric"});
}
setInterval(tickClock,1000); tickClock();

async function fetchState() {
  try { const r = await fetch("/api/state"); renderState(await r.json()); }
  catch(e) { console.warn("State fetch error",e); }
}

function fmt(iso) {
  if (!iso) return "--:--";
  return new Date(iso).toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit",hour12:true});
}

function renderState(d) {
  const running = d.pump_running;
  document.getElementById("statusRing").classList.toggle("active", running);
  document.getElementById("statusText").textContent = running ? "RUNNING" : "IDLE";
  document.getElementById("statusSub").textContent  = running ? "Pump active — "+(d.pump_reason||"") : "Waiting for next cycle";

  const now = Date.now();
  const mMs = d.next_morning ? new Date(d.next_morning).getTime() : 0;
  const eMs = d.next_evening ? new Date(d.next_evening).getTime() : 0;

  document.getElementById("morningTime").textContent = fmt(d.next_morning);
  document.getElementById("eveningTime").textContent = fmt(d.next_evening);

  function badge(ms) {
    if (!ms) return ["—",""];
    if (ms < now) return ["Done","badge-done"];
    if (ms - now < 3_600_000) return ["Soon","badge-upcoming"];
    return ["Scheduled","badge-ok"];
  }
  const [ml,mc]=badge(mMs), [el,ec]=badge(eMs);
  const mb=document.getElementById("morningBadge"), eb=document.getElementById("eveningBadge");
  mb.textContent=ml; mb.className="badge "+mc;
  eb.textContent=el; eb.className="badge "+ec;

  const nexts=[mMs,eMs].filter(ms=>ms>now).sort();
  if (nexts.length) {
    const diff=nexts[0]-now, h=Math.floor(diff/3.6e6), m=Math.floor((diff%3.6e6)/60000), s=Math.floor((diff%60000)/1000);
    document.getElementById("countdown").textContent=String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0");
    document.getElementById("countdownLabel").textContent=nexts[0]===mMs?"Until morning watering":"Until evening watering";
  } else {
    document.getElementById("countdown").textContent="— Cycles Done —";
    document.getElementById("countdownLabel").textContent="Schedule rebuilds at midnight";
  }

  const events=d.events||[];
  if (!events.length) return;
  document.getElementById("logList").innerHTML=events.map(e=>{
    const t=new Date(e.time).toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
    const isErr=e.status&&(e.status.includes("error")||e.status.includes("fail"));
    return `<div class="log-entry"><span class="log-time">${t}</span><span class="log-label">${e.label}</span><span class="log-status${isErr?" err":""}">${e.status}</span></div>`;
  }).join("");
}

async function manualTrigger() {
  const btn=document.getElementById("triggerBtn");
  btn.disabled=true; btn.textContent="Sending…";
  try { await fetch("/api/trigger",{method:"POST"}); showToast(); setTimeout(fetchState,2000); }
  catch(e) { alert("Error: "+e); }
  setTimeout(()=>{ btn.disabled=false; btn.textContent="▶  Run Pump Now (Manual)"; },4000);
}

function showToast() {
  const t=document.getElementById("toast");
  t.classList.add("show"); setTimeout(()=>t.classList.remove("show"),3200);
}

fetchState(); setInterval(fetchState,1000);
</script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/state")
def api_state():
    state = {}
    if STATE.exists():
        try: state = json.loads(STATE.read_text())
        except Exception: pass
    if PI_STATE.exists():
        try:
            ps = json.loads(PI_STATE.read_text())
            state["pump_running"] = ps.get("running", False)
            state["pump_reason"]  = ps.get("reason", "")
        except Exception: pass
    return jsonify(state)

@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    TRIGGER.write_text("MANUAL-DASHBOARD")
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("  Dashboard → http://localhost:5050")
    print("  State files are gitignored and will not be committed.")
    app.run(host="0.0.0.0", port=5050, debug=False)
