"""Read council online forms in a real (headless) browser, read-only.

For each form URL: load it, wait for the Verint form to render, and record the
visible step's fields (label, type, required, options) and any notice text.
It never types, never signs in, never clicks Next/Submit/Send: only the first
visible step is read. Output: reference/.page_cache/forms/<slug>.json.

Needs Microsoft Edge and `websocket-client`.
Run: python reference/read_forms.py <form url> [...]
"""

import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

OUT = Path(__file__).resolve().parent / ".page_cache" / "forms"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9351
USER_AGENT = "KerbsideResearch/0.1 (SotonShip 2026 hackathon; +https://github.com/KRAA5H/sotonaiship-26)"
DELAY = 1.1

# Runs in the page. Reads only; changes nothing.
READ_STEP = r"""
(() => {
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) &&
                        getComputedStyle(el).visibility !== 'hidden';
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return clean(l.innerText); }
    const w = el.closest('.dform_widget, .form-group, fieldset, .dform_field');
    if (w) { const l = w.querySelector('legend, label, .dform_label, h3, h4'); if (l) return clean(l.innerText); }
    return clean(el.getAttribute('aria-label') || el.name || '');
  };
  const required = el => {
    const w = el.closest('.dform_widget, .form-group, fieldset');
    return !!(el.required || el.getAttribute('aria-required') === 'true' ||
              (w && /required|mandatory/i.test(w.className)) ||
              (w && /\*\s*$|\(required\)/i.test(clean((w.querySelector('label, legend') || {}).innerText))));
  };
  const fields = [], seen = new Set();
  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (!visible(el) || ['hidden', 'submit', 'button'].includes(el.type)) continue;
    const label = labelFor(el);
    if (el.type === 'radio' || el.type === 'checkbox') {
      const group = el.closest('fieldset, .dform_widget') || el.parentElement;
      const key = 'g:' + (el.name || label);
      if (seen.has(key)) continue; seen.add(key);
      const opts = [...group.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`)].map(r => {
        const l = r.id && document.querySelector(`label[for="${CSS.escape(r.id)}"]`);
        return clean(l ? l.innerText : r.value);
      });
      const legend = group.querySelector('legend, .dform_label, label');
      fields.push({label: clean(legend ? legend.innerText : label), type: el.type, required: required(el), options: opts});
    } else {
      const key = 'f:' + (el.id || el.name || label);
      if (seen.has(key)) continue; seen.add(key);
      fields.push({label, type: el.tagName === 'SELECT' ? 'dropdown' : (el.tagName === 'TEXTAREA' ? 'textarea' : el.type),
                   required: required(el),
                   options: el.tagName === 'SELECT' ? [...el.options].map(o => clean(o.text)).filter(Boolean) : []});
    }
  }
  const notices = [...document.querySelectorAll('.dform_section p, .dform_section .dform_html, .alert, .notice, [role=alert], .dform_widget_type_html')]
    .filter(visible).map(e => clean(e.innerText)).filter(t => t && t.length < 600);
  const buttons = [...document.querySelectorAll('button, input[type=submit], input[type=button], a.btn')]
    .filter(visible).map(b => clean(b.innerText || b.value)).filter(Boolean);
  const section = [...document.querySelectorAll('.dform_section, .dform_page')].find(visible);
  return {title: document.title, heading: clean((document.querySelector('h1, h2') || {}).innerText),
          section: section ? clean((section.querySelector('h2, h3, legend') || {}).innerText) : '',
          fields, notices: [...new Set(notices)], buttons: [...new Set(buttons)],
          signin: /sign in|log in|create an account/i.test(document.body.innerText),
          captcha: !!document.querySelector('iframe[src*=captcha], .g-recaptcha, [data-sitekey]')};
})()
"""


def slug(url):
    return re.sub(r"[^a-z0-9]+", "-", url.split("/request/")[-1].lower()).strip("-")[:80]


def main(urls):
    OUT.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="edge-forms-")
    edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
                             f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                             f"--user-agent={USER_AGENT}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2))
                            if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.3)
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        n = [0]

        def send(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == n[0]:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get("result", {})

        def js(expr):
            return send("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")

        send("Page.enable")
        send("Runtime.enable")
        for url in urls:
            path = OUT / f"{slug(url)}.json"
            if path.exists():
                print("cached", path.name)
                continue
            time.sleep(DELAY)
            send("Page.navigate", url=url)
            data, status, steps = None, "unverified: form did not render", []
            for attempt in range(40):      # up to ~20 s for the form scripts
                time.sleep(0.5)
                data = js(READ_STEP)
                if data and data["fields"]:
                    status = "read_step_with_fields"
                    time.sleep(1.5)        # let late widgets appear, then read once more
                    data = js(READ_STEP)
                    break
                # A step with no fields at all (the privacy statement) may be passed with
                # "Next": no data is entered and nothing is sent. Any other button is never clicked.
                if data and not data["fields"] and data["buttons"].count("Next") and len(steps) < 2 and attempt > 3:
                    steps.append({"section": data["section"], "notices": data["notices"]})
                    clicked = js("""(() => { const b = [...document.querySelectorAll('button, input[type=button]')]
                        .find(b => (b.innerText || b.value || '').trim() === 'Next' && b.offsetParent);
                        if (!b || /submit|send|finish|confirm/i.test(b.innerText || b.value)) return false;
                        b.click(); return true; })()""")
                    if not clicked:
                        break
            if data is not None:
                data["earlier_steps"] = steps
            text = js("document.body.innerText.slice(0, 400)") or ""
            if re.search(r"\b(403|429)\b|access denied|too many requests", text, re.I):
                raise SystemExit(f"Blocked on {url}: {text[:120]!r}")
            record = {"url": url, "status": status, "read_at": time.strftime("%Y-%m-%d"), **(data or {})}
            path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
            print(status, len((data or {}).get("fields", [])), "fields", path.name)
        ws.close()
    finally:
        edge.terminate()


if __name__ == "__main__":
    main(sys.argv[1:])
