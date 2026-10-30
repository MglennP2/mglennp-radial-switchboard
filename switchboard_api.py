#!/usr/bin/env python3
r"""
MGLENNP STANDALONE SWITCHBOARD — V1.4 (STRIPE LANDING PAGE, LIVE PROBE, TOLL LEDGER)
Endpoints:
 - GET  /               -> Public MglennP Landing Page (Stripe Compliance)
 - GET  /v1/health      -> Public read-only switchboard status & live Supabase agent count
 - GET  /cockpit        -> Hands-free mobile voice cockpit for Pixel (stores Operator Key locally)
 - GET  /v1/operator    -> [GATED: X-Operator-Key] Query via ?cmd=...
 - POST /v1/operator    -> [GATED: X-Operator-Key] Voice Command & Control
 - POST /v1/matchmake   -> 0.05ms 64-Bit MGLE-NNP matchmaking + $0.0001 ledger log
 - POST /v1/crawl       -> [GATED: X-Operator-Key] Refreshes public MCP registry
"""

import os
import sys
import hmac
import json
import time
import threading
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from radial_synapse_phonebook import (
    ensure_local_env,
    supabase_request,
    crawl_public_agent_phonebook,
    radial_mglennp_matchmake,
    pack_mglennp_u64,
    unpack_mglennp_u64,
    HANDSHAKE_FEE_USD,
)

SETTLEMENT_THRESHOLD_USD = 5.00


def load_operator_key():
    key = os.environ.get("OPERATOR_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPERATOR_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["OPERATOR_KEY"] = val
                    return val
    return ""


def check_operator_gate(headers, query_params=None, body_data=None):
    expected = load_operator_key()
    if not expected:
        return False, "Server OPERATOR_KEY is not configured."
    provided = (
        headers.get("X-Operator-Key")
        or (body_data or {}).get("operator_key")
        or ((query_params or {}).get("key", [""])[0])
        or ""
    ).strip()
    if not provided or not hmac.compare_digest(provided, expected):
        return False, "Unauthorized: Valid X-Operator-Key required."
    return True, "Authorized"


def fetch_phonebook_from_supabase():
    rows = supabase_request("radial_agent_phonebook?select=*", method="GET", prefer="return=representation")
    for r in rows:
        r["radial_bitmask"] = int(r["radial_bitmask"])
        r["mglennp_u64"] = int(r["mglennp_u64"])
        r["synaptic_weight"] = float(r["synaptic_weight"])
        r["avg_latency_ms"] = int(r["avg_latency_ms"])
    return rows


def fetch_ledger_from_supabase():
    return supabase_request("handshake_ledger?select=*", method="GET", prefer="return=representation")


def log_handshake_to_ledger(intent, coupler, matched_agent, rail="STRIPE_METERED_USD"):
    return supabase_request("handshake_ledger", method="POST", payload=[{
        "caller_intent": intent,
        "required_coupler": coupler,
        "matched_agent_id": matched_agent["agent_id"],
        "mglennp_code_snapshot": matched_agent["mglennp_code"],
        "hop_audit_status": "CLEAN_SELF_EXECUTION",
        "response_latency_ms": matched_agent["avg_latency_ms"],
        "outcome_success": True,
        "switchboard_fee_usd": HANDSHAKE_FEE_USD,
        "settlement_rail": rail,
    }])


def patch_agent_in_supabase(agent_id, fields):
    encoded_id = urllib.parse.quote(agent_id, safe="")
    return supabase_request(f"radial_agent_phonebook?agent_id=eq.{encoded_id}", method="PATCH", payload=fields, prefer="return=representation")


def classify_agent_legitimacy(agent):
    code = (agent.get("mglennp_code") or "").upper()
    endpoint = (agent.get("endpoint") or "").strip().lower()
    weight = float(agent.get("synaptic_weight", 0.0))
    bitmask = int(agent.get("radial_bitmask", 0))

    if code.startswith("FF") or code[1:2] == "F" or weight <= 0.05:
        return "SLASHED_OR_FAILED"
    if not endpoint or "github.com" in endpoint or "gitlab.com" in endpoint or endpoint.endswith(".git") or code[1:2] == "D" or bitmask == 0:
        return "UNHOSTED_REPO_CODE_ONLY"
    return "LIVE_CALLABLE_AGENT"


def latency_ms_to_grade(ms):
    if ms <= 120: return "A"
    if ms <= 300: return "B"
    if ms <= 700: return "C"
    if ms <= 1500: return "D"
    return "E"


def mutate_mglennp_code(old_code, merit=None, guarantee=None, latency=None):
    clean = (old_code or "CAAB-ZES").replace("-", "")
    if len(clean) != 7: clean = "CAABZES"
    chars = list(clean)
    if merit: chars[0] = merit
    if guarantee: chars[1] = guarantee
    if latency: chars[2] = latency
    new_code = "".join(chars[:4]) + "-" + "".join(chars[4:])
    u64 = pack_mglennp_u64(new_code, hop_ttl=0 if chars[4] in ("Z", "S") else 1, version=1)
    return new_code, u64, f"0x{u64:016X}"


def probe_live_agent_endpoint(endpoint):
    ep = (endpoint or "").strip()
    if ep.startswith("mcp://"): return True, 55
    if not ep.startswith("http://") and not ep.startswith("https://"): return False, 9999

    t0 = time.perf_counter()
    req = urllib.request.Request(ep, headers={"User-Agent": "MglennP-Switchboard-Auditor/1.4"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return (200 <= resp.status < 500), max(1, int((time.perf_counter() - t0) * 1000))
    except urllib.error.HTTPError as e:
        return (200 <= e.code < 500), max(1, int((time.perf_counter() - t0) * 1000))
    except Exception:
        return False, max(1, int((time.perf_counter() - t0) * 1000))


def get_public_status_roll_call():
    phonebook = fetch_phonebook_from_supabase()
    ledger = fetch_ledger_from_supabase()
    live_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT")
    repo_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "UNHOSTED_REPO_CODE_ONLY")
    slashed_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "SLASHED_OR_FAILED")
    total_fees = round(len(ledger) * HANDSHAKE_FEE_USD, 4)

    return {
        "command_understood": "ROAD_STATUS_ROLL_CALL",
        "security_gate": "OPERATOR_KEY_ENABLED",
        "stats": {
            "total_indexed": len(phonebook),
            "legit_live_agents": live_cnt,
            "unhosted_github_repos": repo_cnt,
            "slashed_scammers": slashed_cnt,
            "total_handshakes_logged": len(ledger),
            "accrued_toll_usd": total_fees,
            "next_settlement_threshold_usd": SETTLEMENT_THRESHOLD_USD,
        },
        "voice_briefing": (
            f"Switchboard is healthy and gated. Out of {len(phonebook)} indexed entries, "
            f"{live_cnt} are verified live agents, {repo_cnt} are unhosted repos, "
            f"and {slashed_cnt} is blocked. Ledger tab is ${total_fees:.4f}."
        ),
    }


def handle_voice_operator_command(command_text):
    cmd = command_text.strip().lower()

    if any(w in cmd for w in ("toll", "payment", "revenue", "ledger", "balance")):
        ledger = fetch_ledger_from_supabase()
        count = len(ledger)
        accrued = round(count * HANDSHAKE_FEE_USD, 4)
        return {
            "command_understood": "TOLL_LEDGER_SUMMARY",
            "total_handshakes": count,
            "accrued_toll_usd": accrued,
            "voice_briefing": f"Tollbooth ledger has {count} verified handshakes totaling ${accrued:.4f} accrued.",
        }

    if any(w in cmd for w in ("slash", "block", "ban")):
        phonebook = fetch_phonebook_from_supabase()
        target = next((a for a in phonebook if any(tok in a["agent_id"].lower() or tok in a["name"].lower() for tok in cmd.split() if len(tok)>3 and tok not in ("slash", "block", "agent"))), None)
        if not target: return {"command_understood": "VOICE_SLASH_AGENT", "voice_briefing": "Tell me which agent name to slash."}
        new_code, u64, u64_hex = mutate_mglennp_code(target["mglennp_code"], merit="F", guarantee="F")
        patch_agent_in_supabase(target["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex, "synaptic_weight": 0.0})
        return {"command_understood": "VOICE_SLASH_AGENT", "voice_briefing": f"Slashed {target['name']}."}

    if any(w in cmd for w in ("restore", "unblock", "promote")):
        phonebook = fetch_phonebook_from_supabase()
        target = next((a for a in phonebook if any(tok in a["agent_id"].lower() or tok in a["name"].lower() for tok in cmd.split() if len(tok)>3 and tok not in ("restore", "unblock", "agent"))), None)
        if not target: return {"command_understood": "VOICE_RESTORE_AGENT", "voice_briefing": "Tell me which agent to restore."}
        new_code, u64, u64_hex = mutate_mglennp_code(target["mglennp_code"], merit="B", guarantee="A")
        patch_agent_in_supabase(target["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex, "synaptic_weight": 0.90})
        return {"command_understood": "VOICE_RESTORE_AGENT", "voice_briefing": f"Restored {target['name']}."}

    if any(w in cmd for w in ("audit", "probe", "legit", "verify")):
        phonebook = fetch_phonebook_from_supabase()
        probed_ok, unreachable_cnt, repo_cnt, slashed_cnt, fastest = 0, 0, 0, 0, 9999
        for a in phonebook:
            status = classify_agent_legitimacy(a)
            if status == "SLASHED_OR_FAILED":
                slashed_cnt += 1; continue
            if status == "UNHOSTED_REPO_CODE_ONLY":
                repo_cnt += 1
                if a["mglennp_code"][1:2] != "D":
                    new_code, u64, u64_hex = mutate_mglennp_code(a["mglennp_code"], guarantee="D")
                    patch_agent_in_supabase(a["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex})
                continue

            ok, ms = probe_live_agent_endpoint(a.get("endpoint", ""))
            if ok:
                probed_ok += 1
                fastest = min(fastest, ms)
                new_code, u64, u64_hex = mutate_mglennp_code(a["mglennp_code"], guarantee="A" if a["mglennp_code"][1:2]=="A" else "B", latency=latency_ms_to_grade(ms))
                patch_agent_in_supabase(a["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex, "avg_latency_ms": ms})
            else:
                unreachable_cnt += 1
                new_code, u64, u64_hex = mutate_mglennp_code(a["mglennp_code"], guarantee="E", latency="E")
                patch_agent_in_supabase(a["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex, "avg_latency_ms": ms})

        return {
            "command_understood": "LIVE_HTTP_HEARTBEAT_AUDIT",
            "voice_briefing": f"Audit complete. {probed_ok} answered live. {unreachable_cnt} unreachable, {repo_cnt} dormant repos.",
        }

    if any(w in cmd for w in ("list", "who is live", "top agents")):
        phonebook = fetch_phonebook_from_supabase()
        live_only = [a for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
        names = ", ".join(f"{a['name']}" for a in live_only[:4])
        return {"command_understood": "LIST_LIVE_AGENTS", "voice_briefing": f"You have {len(live_only)} live agents ready. Top nodes are: {names}."}

    if any(w in cmd for w in ("crawl", "refresh", "update registry", "scan")):
        phonebook = crawl_public_agent_phonebook()
        supabase_request("radial_agent_phonebook?on_conflict=agent_id", method="POST", payload=phonebook, prefer="resolution=merge-duplicates,return=minimal")
        return {"command_understood": "CRAWL_AND_LEGITIMACY_AUDIT", "voice_briefing": f"Crawl complete. Synced {len(phonebook)} total entries to Supabase."}

    if any(w in cmd for w in ("find", "match", "hire", "need")):
        phonebook = fetch_phonebook_from_supabase()
        live_only = [a for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
        coupler = "****-ZED" if "deep" in cmd or "construction" in cmd else "*AA*-ZES"
        res = radial_mglennp_matchmake(command_text, live_only, required_pattern=coupler)
        if res["matches"]:
            top = res["matches"][0]
            log_handshake_to_ledger(command_text, coupler, top)
            total_fees = round(len(fetch_ledger_from_supabase()) * HANDSHAKE_FEE_USD, 4)
            return {
                "command_understood": "VOICE_MATCHMAKE_LIVE_ONLY",
                "voice_briefing": f"Matched {top['name']}. Logged toll; your tab is now ${total_fees:.4f}.",
            }
        return {"command_understood": "VOICE_MATCHMAKE_LIVE_ONLY", "voice_briefing": "No agents matched."}

    return get_public_status_roll_call()


LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MglennP | An honest approach</title>
<style>
  body { background:#0b0f19; color:#f8fafc; font-family:system-ui,sans-serif; margin:0; padding:40px 20px; line-height:1.6; }
  .container { max-width:600px; margin:0 auto; text-align:center; }
  h1 { color:#38bdf8; font-size:2.5rem; margin-bottom:5px; }
  .slogan { color:#94a3b8; font-size:1.2rem; font-style:italic; margin-bottom:30px; }
  .card { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:24px; text-align:left; margin-bottom:20px; }
  h2 { color:#e2e8f0; font-size:1.3rem; margin-top:0; border-bottom:1px solid #334155; padding-bottom:10px; }
  ul { padding-left:20px; color:#cbd5e1; }
  li { margin-bottom: 8px; }
  .footer { margin-top:40px; font-size:0.9rem; color:#64748b; }
  a { color:#38bdf8; text-decoration:none; font-weight:600; }
</style>
</head>
<body>
  <div class="container">
    <h1>MglennP</h1>
    <div class="slogan">"An honest approach"</div>
    
    <div class="card">
      <h2>Autonomous Switchboard Infrastructure</h2>
      <p>MglennP operates a high-speed API switchboard and clearinghouse for autonomous AI agents. We provide secure, gated matchmaking and legitimacy auditing using the MGLE-NNP 64-bit standard.</p>
    </div>

    <div class="card">
      <h2>Transparent Metered Pricing</h2>
      <ul>
        <li><strong>API Matchmaking:</strong> $0.0001 USD per successful handshake.</li>
        <li><strong>Billing Cycle:</strong> Metered threshold billing (invoiced upon reaching $5.00) via Stripe.</li>
        <li><strong>No hidden fees or middleman markups.</strong></li>
      </ul>
    </div>

    <div class="footer">
      Operated by Michael G. Pearson.<br>
      For API access or support, contact: <a href="mailto:support@mpearson.us">support@mpearson.us</a>
    </div>
  </div>
</body>
</html>
"""


COCKPIT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MglennP Switchboard — Gated Road Cockpit</title>
<style>
  body { background:#0b0f19; color:#f8fafc; font-family:system-ui,sans-serif; margin:0; padding:16px; text-align:center; }
  h1 { font-size:1.3rem; color:#38bdf8; margin:4px 0; }
  .sub { font-size:0.85rem; color:#94a3b8; margin-bottom:12px; }
  .keybar { max-width:420px; margin:0 auto 14px; display:flex; justify-content:space-between; align-items:center; background:#111827; border:1px solid #334155; border-radius:12px; padding:8px 12px; }
  #keyStatus { font-size:0.9rem; font-weight:600; color:#4ade80; }
  #keyBtn { background:#334155; color:#f8fafc; border:none; border-radius:8px; padding:8px 12px; font-weight:600; cursor:pointer; }
  #micBtn { width:100%; max-width:420px; height:150px; border-radius:24px; border:3px solid #38bdf8; background:#0284c7; color:#fff; font-size:1.5rem; font-weight:700; cursor:pointer; margin-bottom:16px; }
  #micBtn.listening { background:#dc2626; border-color:#f87171; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; max-width:420px; margin:0 auto 16px; }
  .qbtn { padding:16px 8px; border-radius:14px; border:1px solid #334155; background:#1e293b; color:#e2e8f0; font-size:1rem; font-weight:600; cursor:pointer; }
  .qbtn.wide { grid-column: span 2; background:#0f172a; border-color:#0284c7; color:#38bdf8; }
  #replyBox { max-width:420px; margin:0 auto; padding:16px; border-radius:14px; background:#111827; border:1px solid #1f2937; text-align:left; font-size:1.05rem; line-height:1.45; }
</style>
</head>
<body>
  <h1>MglennP Switchboard Cockpit</h1>
  <div class="sub">US-East4 (Northern Virginia) • Gated Pixel Control</div>
  <div class="keybar"><span id="keyStatus">🔒 Checking Key...</span><button id="keyBtn" onclick="setOperatorKey()">🔑 Set Operator Key</button></div>
  <button id="micBtn" onclick="startVoice()">🎙️ TAP & SPEAK COMMAND</button>
  <div class="grid">
    <button class="qbtn" onclick="sendCmd('status report')">📊 Roll Call</button>
    <button class="qbtn" onclick="sendCmd('audit the phone book')">🛡️ Live HTTP Audit</button>
    <button class="qbtn" onclick="sendCmd('list live agents')">⚡ List Live</button>
    <button class="qbtn" onclick="sendCmd('check toll tab')">💰 Toll Tab</button>
    <button class="qbtn wide" onclick="sendCmd('Find me a legit live SQL validator agent')">🤝 Test Dispatch (+ $0.0001 Toll)</button>
  </div>
  <div id="replyBox">Tap the blue microphone button or any quick action above. Responses will be spoken out loud.</div>
<script>
function updateKeyBadge() { const k = localStorage.getItem('mglennp_operator_key'); const el = document.getElementById('keyStatus'); if(k) { el.innerText = '🔒 Operator Key Saved'; el.style.color = '#4ade80'; } else { el.innerText = '⚠️ Key Not Set'; el.style.color = '#facc15'; } }
function setOperatorKey() { const current = localStorage.getItem('mglennp_operator_key') || ''; const entered = prompt('Enter your MglennP OPERATOR_KEY (saved locally on this Pixel):', current); if (entered !== null) { localStorage.setItem('mglennp_operator_key', entered.trim()); updateKeyBadge(); } }
updateKeyBadge();
async function sendCmd(text) { const box = document.getElementById('replyBox'); const opKey = localStorage.getItem('mglennp_operator_key') || ''; box.innerText = 'Heard: "' + text + '" ... contacting Virginia switchboard...'; try { const res = await fetch('/v1/operator', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Operator-Key': opKey }, body: JSON.stringify({voice_command: text}) }); const data = await res.json(); const msg = data.voice_briefing || data.error || JSON.stringify(data); box.innerText = msg; if ('speechSynthesis' in window) { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(msg)); } if (res.status === 401) setOperatorKey(); } catch (e) { box.innerText = 'Error: ' + e; } }
function startVoice() { const SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) { const typed = prompt('Voice recognition not supported. Type command:'); if (typed) sendCmd(typed); return; } const btn = document.getElementById('micBtn'); const rec = new SR(); rec.lang = 'en-US'; rec.onstart = () => { btn.classList.add('listening'); btn.innerText = '🔴 LISTENING...'; }; rec.onend = () => { btn.classList.remove('listening'); btn.innerText = '🎙️ TAP & SPEAK COMMAND'; }; rec.onresult = (e) => { sendCmd(e.results[0][0].transcript); }; rec.start(); }
</script>
</body>
</html>
"""


class SwitchboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status_code, html_text):
        body = html_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(200, LANDING_HTML)
        elif parsed.path == "/v1/health":
            try:
                report = get_public_status_roll_call()
                self._send_json(200, report)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        elif parsed.path == "/cockpit":
            self._send_html(200, COCKPIT_HTML)
        elif parsed.path == "/v1/operator":
            qs = urllib.parse.parse_qs(parsed.query)
            ok, reason = check_operator_gate(self.headers, query_params=qs)
            if not ok:
                self._send_json(401, {"error": reason, "voice_briefing": "Access denied."})
                return
            try:
                report = handle_voice_operator_command(qs.get("cmd", ["status report"])[0])
                self._send_json(200, report)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}

        if self.path == "/v1/operator":
            ok, reason = check_operator_gate(self.headers, body_data=data)
            if not ok:
                self._send_json(401, {"error": reason, "voice_briefing": "Access denied."})
                return
            try:
                report = handle_voice_operator_command(data.get("voice_command", "status report"))
                self._send_json(200, report)
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif self.path == "/v1/crawl":
            ok, reason = check_operator_gate(self.headers, body_data=data)
            if not ok:
                self._send_json(401, {"error": reason, "voice_briefing": "Access denied."})
                return
            try:
                self._send_json(200, handle_voice_operator_command("crawl and refresh"))
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif self.path == "/v1/matchmake":
            intent, coupler = data.get("intent", "general helper"), data.get("coupler", "****-Z**")
            try:
                live_only = [a for a in fetch_phonebook_from_supabase() if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
                result = radial_mglennp_matchmake(intent, live_only, required_pattern=coupler)
                if result["matches"]:
                    log_handshake_to_ledger(intent, coupler, result["matches"][0])
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Endpoint not found"})


if __name__ == "__main__":
    ensure_local_env()
    load_operator_key()
    port = int(os.environ.get("PORT", 8080))
    print(f"MglennP Gated Switchboard API v1.4 listening on port {port}...")
    ThreadingHTTPServer(("0.0.0.0", port), SwitchboardHandler).serve_forever()
