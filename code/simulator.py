"""Temporary web simulator for the resident conversation.

No BlueBubbles, no Mac. Every message goes through the same multi-agent
workflow as the real line (the triage agent orchestrates, see code/agents/),
saves to the same database, and makes believe the typing took a human amount
of time. Built for a phone first.

  python code/simulator.py          http://<this machine>:5007

It also serves the drop-a-pin map and the resident's report page on the same
address, and texts that arrive later (a pin confirmed on the map, a status the
council changed) appear in the chat. Set SITE_URL to this address so report
links open here too. "Use my current location" needs HTTPS on a phone.

The real number still runs on 5005; this is a second, separate app.
"""

import os
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, make_response, request

import blue_bubbles as bot
import messages  # noqa: F401
import pin_service
import triage  # noqa: F401  patched by tests; the orchestrator calls it
import voice  # noqa: F401
from agents import ORCHESTRATOR, Turn
from website import site

PORT = int(os.getenv("SIM_PORT") or "5007")

app = Flask(__name__)
app.register_blueprint(site)      # /r/<token>, the resident's own page
pin_service.mount(app)            # /p/<token>, the drop-a-pin map

# Texts that arrive after the turn: a pin confirmed on the map, a status change.
OUTBOX = defaultdict(list)
OUTBOX_LOCK = threading.Lock()


def _to_outbox(chat, text):
    with OUTBOX_LOCK:
        OUTBOX[chat].append(text)


ORCHESTRATOR.set_notifier(_to_outbox)
orchestrator = ORCHESTRATOR


def _sender(req):
    sid = req.cookies.get("sim_sid") or uuid.uuid4().hex[:12]
    return "sim:" + sid, sid


def run_turn(sender, text, image=None, link_base=None):
    """The same path as the webhook, minus the phone: the triage agent orchestrates."""
    started = time.time()
    outcome = orchestrator.handle(Turn(sender=sender, text=text, chat=sender, image=image,
                                       link_base=link_base))
    body, link = bot.split_reply(outcome.reply or "")
    decision = outcome.decision or {}
    debug = {
        "category": decision.get("category_id"),
        "label": decision.get("category_label"),
        "severity": decision.get("severity"),
        "confidence": decision.get("confidence"),
        "reason": decision.get("reason"),
        "is_report": decision.get("is_report"),
        "location": decision.get("location"),
        "photo": bool(image),
        "agents": outcome.trace,
        "category_agent": decision.get("agent"),
    }
    return body, link, debug, started


@app.get("/health")
def health():
    return jsonify({"ok": True, "port": PORT, "mode": "simulator"})


@app.post("/api/turn")
def turn():
    sender, sid = _sender(request)
    if "photo" in request.files:
        upload = request.files["photo"]
        data = upload.read()
        image = (data, upload.mimetype or "image/jpeg") if data else None
        text = (request.form.get("text") or "").strip()
        simulate = request.form.get("simulate", "1") == "1"
    else:
        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or "").strip()
        image = None
        simulate = bool(payload.get("simulate", True))

    if not text and not image:
        return jsonify({"ok": False, "error": "send a message or a photo"}), 400

    try:
        body, link, debug, started = run_turn(sender, text, image, link_base=request.host_url.rstrip("/"))
    except Exception as error:  # noqa: BLE001 - show the failure, do not crash
        return jsonify({"ok": False, "error": f"{type(error).__name__}: {error}"}), 500

    model_ms = round((time.time() - started) * 1000)
    typing_ms = min(3500, 350 + 9 * len(body)) if simulate and body else 0

    response = make_response(jsonify({
        "ok": True,
        "body": body,
        "link": link,
        "debug": debug,
        "model_ms": model_ms,
        "typing_ms": typing_ms,
        "link_delay_ms": 800 if link else 0,
    }))
    if request.cookies.get("sim_sid") != sid:
        response.set_cookie("sim_sid", sid, max_age=86400, samesite="Lax")
    return response


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Kerbside simulator</title>
<style>
  :root { --blue:#0b84ff; --grey:#e9e9eb; --ink:#111; --muted:#6b7280; }
  * { box-sizing:border-box; }
  html, body { height:100%; margin:0; }
  body {
    font:16px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background:#f2f2f7; color:var(--ink);
    display:flex; justify-content:center;
  }
  .app {
    width:100%; max-width:560px; height:100dvh;
    display:flex; flex-direction:column;
    background:#fff;
  }
  header {
    padding:14px 16px calc(10px + env(safe-area-inset-top)) 16px;
    border-bottom:1px solid #e5e7eb; display:flex; align-items:center; gap:8px;
  }
  header h1 { font-size:15px; margin:0; font-weight:600; }
  header .dot { width:8px; height:8px; border-radius:50%; background:#22c55e; }
  header .sub { margin-left:auto; font-size:12px; color:var(--muted); }
  #chat { flex:1; overflow-y:auto; padding:16px 12px; display:flex; flex-direction:column; gap:6px; }
  .row { display:flex; }
  .row.me { justify-content:flex-end; }
  .bubble {
    max-width:82%; padding:9px 13px; border-radius:18px; white-space:pre-wrap;
    word-wrap:break-word; font-size:15px;
  }
  .bot .bubble { background:var(--grey); border-bottom-left-radius:6px; }
  .me .bubble { background:var(--blue); color:#fff; border-bottom-right-radius:6px; }
  .link .bubble { background:#dbeafe; color:#0b4f9e; text-decoration:underline; }
  .meta { font-size:11px; color:var(--muted); margin:2px 4px 10px; }
  .typing { display:flex; gap:4px; padding:12px 14px; }
  .typing span {
    width:7px; height:7px; border-radius:50%; background:#9ca3af;
    animation:blink 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay:.2s; }
  .typing span:nth-child(3) { animation-delay:.4s; }
  @keyframes blink { 0%,80%,100% { opacity:.25; } 40% { opacity:1; } }
  form {
    display:flex; gap:8px; padding:10px 12px calc(12px + env(safe-area-inset-bottom)) 12px;
    border-top:1px solid #e5e7eb; background:#fff;
  }
  input[type=text] {
    flex:1; font-size:16px; padding:12px 14px; border:1px solid #d1d5db;
    border-radius:22px; outline:none; min-width:0;
  }
  input[type=text]:focus { border-color:var(--blue); }
  button, .attach {
    border:0; background:var(--blue); color:#fff; font-size:15px; font-weight:600;
    padding:12px 16px; border-radius:22px; cursor:pointer; white-space:nowrap;
  }
  .attach { background:#eef2ff; color:#1e3a8a; font-weight:500; padding:12px; }
  .attach input { display:none; }
  .tools { display:flex; align-items:center; gap:10px; padding:0 14px 8px; font-size:12px; color:var(--muted); }
  .tools label { display:flex; align-items:center; gap:6px; }
  #debug {
    font:12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
    background:#0f172a; color:#cbd5e1; padding:10px 14px; display:none;
    max-height:34vh; overflow:auto;
  }
  #debug.open { display:block; }
  .err { color:#b91c1c; font-size:13px; padding:0 16px 8px; }
</style>
</head>
<body>
<div class="app">
  <header>
    <span class="dot"></span>
    <h1>Southampton street line</h1>
    <span class="sub">simulator</span>
  </header>
  <div id="chat">
    <div class="row bot"><div class="bubble">Hi. Send a street problem and I will log it with the council.
Pothole, dumped rubbish, missed bin, broken glass.</div></div>
  </div>
  <div class="tools">
    <label><input type="checkbox" id="simulate" checked> simulate typing</label>
    <label><input type="checkbox" id="showdebug"> debug</label>
    <span id="timing"></span>
  </div>
  <div class="err" id="err"></div>
  <form id="form">
    <label class="attach" for="photo">Photo</label>
    <input type="file" id="photo" accept="image/*">
    <input type="text" id="text" placeholder="Message" autocomplete="off" enterkeyhint="send">
    <button type="submit">Send</button>
  </form>
  <div id="debug"></div>
</div>
<script>
  var chat = document.getElementById('chat');
  var form = document.getElementById('form');
  var text = document.getElementById('text');
  var photo = document.getElementById('photo');
  var simulate = document.getElementById('simulate');
  var showdebug = document.getElementById('showdebug');
  var debug = document.getElementById('debug');
  var timing = document.getElementById('timing');
  var err = document.getElementById('err');

  function add(role, body, extra) {
    var row = document.createElement('div');
    row.className = 'row ' + role + (extra ? ' ' + extra : '');
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = body;
    row.appendChild(bubble);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
    return row;
  }

  function typing() {
    var row = document.createElement('div');
    row.className = 'row bot';
    row.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
    return row;
  }

  function wait(ms) { return new Promise(function (done) { setTimeout(done, ms); }); }

  showdebug.onchange = function () { debug.classList.toggle('open', showdebug.checked); };
  simulate.onchange = function () { localStorage.setItem('simulate', simulate.checked ? '1' : '0'); };
  if (localStorage.getItem('simulate') === '0') simulate.checked = false;

  function linkBubble(url) {
    var row = add('bot', '', 'link');
    var a = document.createElement('a');
    a.href = url; a.textContent = url; a.target = '_blank'; a.rel = 'noopener';
    row.firstChild.textContent = '';
    row.firstChild.appendChild(a);
  }

  // Texts that arrive later: a pin confirmed on the map, a status change.
  async function poll() {
    try {
      var response = await fetch('/api/outbox', { cache: 'no-store' });
      var result = await response.json();
      for (var i = 0; i < (result.texts || []).length; i++) {
        var t = result.texts[i];
        if (t.body) add('bot', t.body);
        if (t.link) { await wait(500); linkBubble(t.link); }
      }
    } catch (ignored) {}
  }
  setInterval(poll, 3000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });

  form.onsubmit = async function (event) {
    event.preventDefault();
    var message = text.value.trim();
    var file = photo.files[0];
    if (!message && !file) return;
    err.textContent = '';
    add('me', message || '(photo)');
    text.value = '';
    photo.value = '';
    var dots = typing();
    var options = { method: 'POST' };
    if (file) {
      var data = new FormData();
      data.append('text', message);
      data.append('photo', file);
      data.append('simulate', simulate.checked ? '1' : '0');
      options.body = data;
    } else {
      data = { text: message, simulate: simulate.checked };
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(data);
    }
    try {
      var response = await fetch('/api/turn', options);
      var result = await response.json();
      dots.remove();
      if (!result.ok) { err.textContent = result.error || 'Something went wrong.'; return; }
      await wait(result.typing_ms || 0);
      if (result.body) add('bot', result.body);
      if (result.link) {
        await wait(result.link_delay_ms || 800);
        linkBubble(result.link);
      }
      timing.textContent = 'agents ' + result.model_ms + 'ms, typed ' + (result.typing_ms || 0) + 'ms';
      debug.textContent = JSON.stringify(result.debug, null, 2);
    } catch (failure) {
      dots.remove();
      err.textContent = 'Request failed: ' + failure;
    }
  };
</script>
</body>
</html>
"""


@app.get("/api/outbox")
def outbox():
    """Texts the agents sent this resident since the last look."""
    sender, _ = _sender(request)
    with OUTBOX_LOCK:
        waiting = OUTBOX.pop(sender, [])
    texts = []
    for text in waiting:
        body, link = bot.split_reply(text)
        texts.append({"body": body, "link": link})
    return jsonify({"ok": True, "texts": texts})


@app.get("/")
def page():
    return PAGE


if __name__ == "__main__":
    print(f"[simulator] http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
