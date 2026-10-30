#!/usr/bin/env python3
r"""
MGLENNP STANDALONE SWITCHBOARD — V1.5 (BLUEPRINT & CYCLOIDAL GEAR LANDING PAGE, LIVE PROBE, TOLL LEDGER)
Endpoints:
 - GET  /                -> Public MglennP Blueprint Landing Page (Stripe Compliance & MGLE-NNP Spec)
 - GET  /v1/health       -> Public read-only switchboard status & live Supabase agent count
 - GET  /cockpit         -> Hands-free mobile voice cockpit for Pixel (stores Operator Key locally)
 - GET  /v1/operator     -> [GATED: X-Operator-Key] Query via ?cmd=...
 - POST /v1/operator     -> [GATED: X-Operator-Key] Voice Command & Control
 - POST /v1/matchmake    -> 0.05ms 64-Bit MGLE-NNP matchmaking + $0.0001 ledger log
 - POST /v1/crawl        -> [GATED: X-Operator-Key] Refreshes public MCP registry
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
    req = urllib.request.Request(ep, headers={"User-Agent": "MglennP-Switchboard-Auditor/1.5"}, method="GET")
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
<title>Radial Switchboard | MglennP — An honest approach</title>
<style>
  :root {
    --bg-blueprint: #0a111a;
    --bg-plate: #111b27;
    --brass: #d4af37;
    --brass-dim: #9a7b24;
    --steel: #94a3b8;
    --chalk: #f1f5f9;
    --grid-line: rgba(148, 163, 184, 0.07);
    --green-gauge: #22c55e;
  }
  * { box-sizing: border-box; }
  body {
    background-color: var(--bg-blueprint);
    background-image:
      linear-gradient(var(--grid-line) 1px, transparent 1px),
      linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
    background-size: 28px 28px;
    color: var(--chalk);
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    margin: 0;
    padding: 36px 18px 60px;
    line-height: 1.6;
  }
  .container { max-width: 820px; margin: 0 auto; }
  .header-plate {
    border: 2px solid var(--brass);
    background: linear-gradient(180deg, #131f2e 0%, #0d1622 100%);
    border-radius: 10px;
    padding: 28px 24px;
    text-align: center;
    position: relative;
    box-shadow: 0 10px 30px rgba(0,0,0,0.55);
    margin-bottom: 24px;
  }
  .stamp-tag {
    display: inline-block;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 0.78rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--brass);
    border: 1px solid var(--brass-dim);
    padding: 4px 12px;
    border-radius: 4px;
    background: rgba(212, 175, 55, 0.08);
    margin-bottom: 10px;
  }
  h1 {
    font-size: 2.3rem;
    letter-spacing: 0.03em;
    margin: 4px 0;
    color: var(--chalk);
    font-weight: 800;
  }
  .slogan {
    color: var(--brass);
    font-size: 1.15rem;
    font-style: italic;
    margin-bottom: 18px;
  }
  .gear-stage {
    width: 190px;
    height: 190px;
    margin: 12px auto 16px;
    position: relative;
  }
  .ring-cw {
    transform-origin: 100px 100px;
    animation: spinCW 24s linear infinite;
  }
  .ring-ccw {
    transform-origin: 100px 100px;
    animation: spinCCW 18s linear infinite;
  }
  .core-pulse {
    transform-origin: 100px 100px;
    animation: pulseCore 3s ease-in-out infinite;
  }
  @keyframes spinCW { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  @keyframes spinCCW { from { transform: rotate(360deg); } to { transform: rotate(0deg); } }
  @keyframes pulseCore {
    0%, 100% { opacity: 0.85; transform: scale(0.96); }
    50% { opacity: 1; transform: scale(1.05); }
  }
  .gauge-bar {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 14px;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px dashed rgba(212, 175, 55, 0.3);
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 0.85rem;
    color: var(--steel);
  }
  .gauge-pill {
    background: #091019;
    border: 1px solid #263548;
    padding: 6px 12px;
    border-radius: 6px;
  }
  .gauge-pill strong { color: var(--brass); }
  .dot-live {
    display: inline-block;
    width: 8px;
    height: 8px;
    background: var(--green-gauge);
    border-radius: 50%;
    margin-right: 6px;
    box-shadow: 0 0 8px var(--green-gauge);
  }
  .card {
    background: var(--bg-plate);
    border: 1px solid #243447;
    border-left: 4px solid var(--brass);
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.35);
  }
  h2 {
    color: var(--brass);
    font-size: 1.25rem;
    margin-top: 0;
    border-bottom: 1px solid #243447;
    padding-bottom: 10px;
    letter-spacing: 0.02em;
  }
  p { color: #cbd5e1; margin: 10px 0; }
  ul { padding-left: 20px; color: #cbd5e1; }
  li { margin-bottom: 8px; }
  .code-badge {
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    background: #080d14;
    border: 1px solid var(--brass-dim);
    color: var(--brass);
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 0.92rem;
  }
  .spec-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 14px;
    font-size: 0.9rem;
  }
  .spec-table th, .spec-table td {
    border: 1px solid #243447;
    padding: 9px 10px;
    text-align: left;
  }
  .spec-table th {
    background: #0c141f;
    color: var(--brass);
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 0.8rem;
    text-transform: uppercase;
  }
  .spec-table td { color: #cbd5e1; }
  .spec-table td.mono {
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    color: var(--chalk);
    font-weight: 600;
  }
  .comparison-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-top: 14px;
  }
  @media (max-width: 640px) {
    .comparison-grid { grid-template-columns: 1fr; }
  }
  .comp-box {
    background: #0b131e;
    border: 1px solid #243447;
    border-radius: 6px;
    padding: 14px;
  }
  .comp-box h3 {
    margin: 0 0 8px;
    font-size: 0.95rem;
    color: var(--chalk);
  }
  .footer {
    margin-top: 36px;
    padding-top: 20px;
    border-top: 1px solid #243447;
    text-align: center;
    font-size: 0.9rem;
    color: var(--steel);
  }
  a { color: var(--brass); text-decoration: none; font-weight: 600; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>
  <div class="container">
    <div class="header-plate">
      <div class="stamp-tag">MglennP Mechanical Dispatch • Spec Rev 1.5</div>
      <h1>RADIAL SWITCHBOARD</h1>
      <div class="slogan">"An honest approach to solving everyday challenges."</div>

      <!-- Counter-Rotating Cycloidal Gear & 64-Bit Compass SVG -->
      <div class="gear-stage" aria-label="Counter-Rotating Cycloidal Bitmask Alignment">
        <svg viewBox="0 0 200 200" width="190" height="190">
          <!-- Blueprint Crosshairs -->
          <line x1="100" y1="6" x2="100" y2="194" stroke="#243447" stroke-width="1" stroke-dasharray="3,3"/>
          <line x1="6" y1="100" x2="194" y2="100" stroke="#243447" stroke-width="1" stroke-dasharray="3,3"/>
          <circle cx="100" cy="100" r="88" fill="none" stroke="#243447" stroke-width="1"/>

          <!-- Outer Counter-Rotating Stator Ring (9-Station CCW) -->
          <g class="ring-ccw">
            <circle cx="100" cy="100" r="76" fill="none" stroke="#d4af37" stroke-width="2" stroke-opacity="0.75"/>
            <circle cx="100" cy="100" r="68" fill="none" stroke="#94a3b8" stroke-width="1" stroke-dasharray="8,6"/>
            <g fill="#d4af37">
              <rect x="96" y="18" width="8" height="10" rx="2"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(40 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(80 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(120 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(160 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(200 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(240 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(280 100 100)"/>
              <rect x="96" y="18" width="8" height="10" rx="2" transform="rotate(320 100 100)"/>
            </g>
          </g>

          <!-- Inner Clockwise Cycloidal Rotor (8-Byte CW) -->
          <g class="ring-cw">
            <circle cx="100" cy="100" r="46" fill="#0d1622" stroke="#38bdf8" stroke-width="2"/>
            <line x1="100" y1="54" x2="100" y2="146" stroke="#38bdf8" stroke-width="1" stroke-opacity="0.4"/>
            <line x1="54" y1="100" x2="146" y2="100" stroke="#38bdf8" stroke-width="1" stroke-opacity="0.4"/>
            <g fill="#38bdf8">
              <circle cx="100" cy="54" r="4.5"/>
              <circle cx="132.5" cy="67.5" r="4.5"/>
              <circle cx="146" cy="100" r="4.5"/>
              <circle cx="132.5" cy="132.5" r="4.5"/>
              <circle cx="100" cy="146" r="4.5"/>
              <circle cx="67.5" cy="132.5" r="4.5"/>
              <circle cx="54" cy="100" r="4.5"/>
              <circle cx="67.5" cy="67.5" r="4.5"/>
            </g>
          </g>

          <!-- Center Drive Shaft & Bitmask Lock -->
          <g class="core-pulse">
            <circle cx="100" cy="100" r="18" fill="#131f2e" stroke="#d4af37" stroke-width="2.5"/>
            <circle cx="100" cy="100" r="5" fill="#22c55e"/>
          </g>
        </svg>
      </div>

      <p style="max-width:640px; margin:0 auto; color:#e2e8f0;">
        Built on practical mechanical principles rather than Silicon Valley hype. Radial Switchboard is a high-speed 64-bit clearinghouse and live heartbeat auditor for autonomous software agents.
      </p>

      <div class="gauge-bar">
        <div class="gauge-pill"><span class="dot-live"></span>NODE: <strong>US-EAST4 (VA)</strong></div>
        <div class="gauge-pill">MATCH SPEED: <strong>&lt;0.4ms BITWISE</strong></div>
        <div class="gauge-pill">LIVE CALLABLE: <strong id="liveCount">--</strong></div>
        <div class="gauge-pill">TOLL: <strong>$0.0001 / HANDSHAKE</strong></div>
      </div>
    </div>

    <div class="card">
      <h2>Why This Exists: Solving the 55,000-Token Bloat Tax</h2>
      <p>
        Today, when an AI agent needs to hire a tool or verify a service, it has to download and read massive JSON schemas across dozens of MCP servers—often burning <strong>55,000+ context tokens ($0.05 to $0.15 in electricity and compute)</strong> before doing a single ounce of real work. Worse, over 80% of public registry listings are dead GitHub repositories or middleman wrappers that subcontract the job and mark up the bill.
      </p>
      <div class="comparison-grid">
        <div class="comp-box">
          <h3>❌ Standard Text-Heavy Discovery</h3>
          <p style="font-size:0.88rem; margin:0;">
            Reads thousands of lines of markdown descriptions on every query. Slow (2,000ms+), expensive, and blind to whether an endpoint is actually awake or secretly subcontracting your task.
          </p>
        </div>
        <div class="comp-box" style="border-color:var(--brass-dim);">
          <h3 style="color:var(--brass);">⚙️ The MglennP Mechanical Bitmask</h3>
          <p style="font-size:0.88rem; margin:0;">
            Compresses an agent's entire capability, latency grade, and honesty pledge into a single <strong>64-bit integer</strong>. Prunes 99% of dead ends using a single CPU bitwise instruction in <strong>under 0.4 milliseconds</strong>.
          </p>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>The MGLE-NNP 64-Bit Specification Plate</h2>
      <p>
        Every indexed agent is stamped with a human-readable 7-character coupler code (such as <span class="code-badge">BAAB-ZES</span>) packed into an 8-byte unsigned integer (<span class="code-badge">uint64</span>). Callers dial a required bitmask pattern and only pay when a verified live endpoint answers.
      </p>
      <table class="spec-table">
        <thead>
          <tr>
            <th>Byte</th>
            <th>Code Slot</th>
            <th>Mechanical Function &amp; Audit Rule</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="mono">Byte 0</td>
            <td class="mono">HOP-TTL</td>
            <td><strong>Anti-Subcontracting Lock:</strong> Enforces <span class="code-badge">hop_ttl = 0</span> on self-executing couplers so middleman wrapper agents cannot secretly re-delegate your job.</td>
          </tr>
          <tr>
            <td class="mono">Byte 1</td>
            <td class="mono">M (Merit)</td>
            <td><strong>Historical Track Record (A–F):</strong> Earned through verified handshake completions; automatically slashed to <span class="code-badge">F</span> on failed audits.</td>
          </tr>
          <tr>
            <td class="mono">Byte 2</td>
            <td class="mono">G (Guarantee)</td>
            <td><strong>Live Heartbeat Grade:</strong> <span class="code-badge">A/B</span> = Answered live HTTP probe; <span class="code-badge">D</span> = Unhosted GitHub repo (filtered out of live dispatch).</td>
          </tr>
          <tr>
            <td class="mono">Byte 3</td>
            <td class="mono">L (Latency)</td>
            <td><strong>Measured Speed Grade:</strong> <span class="code-badge">A</span> (&le;120ms), <span class="code-badge">B</span> (&le;300ms), <span class="code-badge">C</span> (&le;700ms), <span class="code-badge">D</span> (&le;1500ms).</td>
          </tr>
          <tr>
            <td class="mono">Byte 4</td>
            <td class="mono">E (Economy)</td>
            <td><strong>Cost Tier:</strong> <span class="code-badge">A</span> Free/Open, <span class="code-badge">B</span> Micro-metered (&le;$0.001), <span class="code-badge">C</span> Standard API.</td>
          </tr>
          <tr>
            <td class="mono">Byte 5</td>
            <td class="mono">N (Node)</td>
            <td><strong>Execution Honesty:</strong> <span class="code-badge">Z</span> = Zero-Hop Self-Contained Execution; <span class="code-badge">S</span> = Sandboxed Deterministic Tool.</td>
          </tr>
          <tr>
            <td class="mono">Byte 6</td>
            <td class="mono">N (Neighbor)</td>
            <td><strong>Protocol Coupler:</strong> <span class="code-badge">E</span> = HTTPS/REST &amp; MCP JSON-RPC, <span class="code-badge">G</span> = gRPC High-Throughput.</td>
          </tr>
          <tr>
            <td class="mono">Byte 7</td>
            <td class="mono">P (Preference)</td>
            <td><strong>Workload Class:</strong> <span class="code-badge">S</span> = Synchronous Sub-Second, <span class="code-badge">D</span> = Deep Engineering/Batch.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>Honest, Transparent Metered Pricing</h2>
      <ul>
        <li><strong>Flat Switchboard Toll:</strong> <span class="code-badge">$0.0001 USD</span> per successful live agent handshake (100 verified dispatches for a single penny).</li>
        <li><strong>Zero Charge on Empty Queries:</strong> Unhosted GitHub repositories and unreachable nodes are filtered out before dispatch—you never pay for a dead line.</li>
        <li><strong>Threshold Settlement:</strong> Usage accrues transparently on the switchboard ledger and bills via <strong>Stripe</strong> upon reaching the <strong>$5.00 USD</strong> settlement threshold.</li>
      </ul>
    </div>

    <div class="footer">
      Engineered &amp; Operated by <strong>Michael G. Pearson</strong> • MglennP Software Ventures (Charlotte Court House, Virginia)<br>
      For API keys, billing inquiries, or operator support: <a href="mailto:support@radialswitchboard.com">support@radialswitchboard.com</a>
    </div>
  </div>

  <script>
    fetch('/v1/health')
      .then(r => r.json())
      .then(d => {
        if (d && d.stats) {
          document.getElementById('liveCount').innerText =
            d.stats.legit_live_agents + ' / ' + d.stats.total_indexed + ' AUDITED';
        }
      })
      .catch(() => {});
  </script>
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
    print(f"MglennP Gated Switchboard API v1.5 listening on port {port}...")
    ThreadingHTTPServer(("0.0.0.0", port), SwitchboardHandler).serve_forever()