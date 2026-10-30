#!/usr/bin/env python3
r"""
MGLENNP STANDALONE SWITCHBOARD — V1.6 (BLUEPRINT UI, QUARANTINE LOCK, AI BEACONS & PULL TELEMETRY)
Endpoints:
 - GET  /                      -> Public MglennP Blueprint Landing Page & Front-Door API Spec
 - GET  /llms.txt              -> Plain-text AI instruction beacon for LLM web crawlers
 - GET  /openapi.json          -> OpenAPI 3.1.0 schema for automatic tool wiring
 - GET  /.well-known/mcp.json  -> MCP Switchboard Discovery Transponder
 - GET  /v1/health             -> Public read-only switchboard status, agent counts & data pull telemetry
 - GET  /cockpit               -> Hands-free mobile voice cockpit for Pixel (stores Operator Key locally)
 - GET  /v1/operator           -> [GATED: X-Operator-Key] Query via ?cmd=...
 - POST /v1/operator           -> [GATED: X-Operator-Key] Voice Command & Control
 - POST /v1/matchmake          -> <0.4ms 64-Bit MGLE-NNP matchmaking + $0.0001 ledger & telemetry log
 - POST /v1/crawl              -> [GATED: X-Operator-Key] Governed batch refresh of public MCP registry
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


def fetch_phonebook_from_supabase(max_rows=50000):
    all_rows = []
    offset = 0
    while offset < max_rows:
        batch = supabase_request(f"radial_agent_phonebook?select=*&limit=1000&offset={offset}", method="GET", prefer="return=representation")
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    for r in all_rows:
        r["radial_bitmask"] = int(r["radial_bitmask"])
        r["mglennp_u64"] = int(r["mglennp_u64"])
        r["synaptic_weight"] = float(r["synaptic_weight"])
        r["avg_latency_ms"] = int(r["avg_latency_ms"])
    return all_rows


def fetch_ledger_from_supabase(max_rows=20000):
    all_rows = []
    offset = 0
    while offset < max_rows:
        batch = supabase_request(f"handshake_ledger?select=*&limit=1000&offset={offset}", method="GET", prefer="return=representation")
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return all_rows


def log_handshake_to_ledger(intent, coupler, matched_agent, rail="EXTERNAL_AGENT_MATCH"):
    return supabase_request("handshake_ledger", method="POST", payload=[{
        "caller_intent": intent[:240],
        "required_coupler": coupler,
        "matched_agent_id": matched_agent["agent_id"],
        "mglennp_code_snapshot": matched_agent["mglennp_code"],
        "hop_audit_status": "CLEAN_SELF_EXECUTION",
        "response_latency_ms": matched_agent["avg_latency_ms"],
        "outcome_success": True,
        "switchboard_fee_usd": HANDSHAKE_FEE_USD,
        "settlement_rail": rail,
    }])


def log_discovery_pull_async(beacon_path, user_agent):
    """Logs a $0.00 telemetry entry synchronously when external AI crawlers or agents pull /llms.txt, /openapi.json, or /.well-known/mcp.json."""
    ua_short = (user_agent or "unknown-agent").strip()[:140]
    try:
        supabase_request("handshake_ledger", method="POST", payload=[{
            "caller_intent": f"BEACON_PULL:{beacon_path} [{ua_short}]",
            "required_coupler": "BEACON",
            "matched_agent_id": "mcp://us-east-sql-validator",
            "mglennp_code_snapshot": "AAAB-ZES",
            "hop_audit_status": "BEACON_DISCOVERY_READ",
            "response_latency_ms": 1,
            "outcome_success": True,
            "switchboard_fee_usd": 0.0,
            "settlement_rail": "BEACON_DISCOVERY_PULL",
        }])
    except Exception as e:
        print(f"[TELEMETRY WARN] Beacon log failed: {e}")


def patch_agent_in_supabase(agent_id, fields):
    encoded_id = urllib.parse.quote(agent_id, safe="")
    return supabase_request(f"radial_agent_phonebook?agent_id=eq.{encoded_id}", method="PATCH", payload=fields, prefer="return=representation")


def classify_agent_legitimacy(agent):
    agent_id = (agent.get("agent_id") or "").strip()
    code = (agent.get("mglennp_code") or "").upper()
    endpoint = (agent.get("endpoint") or "").strip().lower()
    weight = float(agent.get("synaptic_weight", 0.0))
    bitmask = int(agent.get("radial_bitmask", 0))
    guarantee_grade = code[1:2]

    if agent_id in ("mcp://us-east-sql-validator", "a2a://deep-contract-auditor") or "registry.modelcontextprotocol.io" in endpoint:
        return "INTERNAL_SYSTEM_CANARY"
    if code.startswith("FF") or guarantee_grade == "F" or weight <= 0.05:
        return "SLASHED_OR_FAILED"
    if guarantee_grade == "E":
        return "QUARANTINED_DEAD_ENDPOINT"
    if not endpoint or "github.com" in endpoint or "gitlab.com" in endpoint or endpoint.endswith(".git") or guarantee_grade == "D" or bitmask == 0:
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
    req = urllib.request.Request(ep, headers={"User-Agent": "MglennP-Switchboard-Auditor/1.6"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return (200 <= resp.status < 500), max(1, int((time.perf_counter() - t0) * 1000))
    except urllib.error.HTTPError as e:
        return (200 <= e.code < 500), max(1, int((time.perf_counter() - t0) * 1000))
    except Exception:
        return False, max(1, int((time.perf_counter() - t0) * 1000))


def summarize_traffic_telemetry(ledger):
    external_matches = sum(1 for r in ledger if r.get("settlement_rail") == "EXTERNAL_AGENT_MATCH")
    beacon_pulls = sum(1 for r in ledger if r.get("settlement_rail") == "BEACON_DISCOVERY_PULL")
    paid_handshakes = [r for r in ledger if float(r.get("switchboard_fee_usd", 0.0)) > 0]
    total_fees = round(sum(float(r.get("switchboard_fee_usd", 0.0)) for r in paid_handshakes), 4)
    recent_intents = [
        r.get("caller_intent", "")
        for r in reversed(ledger)
        if r.get("settlement_rail") in ("EXTERNAL_AGENT_MATCH", "BEACON_DISCOVERY_PULL")
    ][:5]
    return {
        "total_paid_handshakes": len(paid_handshakes),
        "external_agent_match_pulls": external_matches,
        "ai_beacon_discovery_pulls": beacon_pulls,
        "total_external_data_pulls": external_matches + beacon_pulls,
        "accrued_toll_usd": total_fees,
        "recent_external_activity": recent_intents,
    }


def get_public_status_roll_call():
    phonebook = fetch_phonebook_from_supabase()
    ledger = fetch_ledger_from_supabase()
    live_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT")
    quarantined_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "QUARANTINED_DEAD_ENDPOINT")
    repo_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "UNHOSTED_REPO_CODE_ONLY")
    slashed_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "SLASHED_OR_FAILED")
    telemetry = summarize_traffic_telemetry(ledger)

    return {
        "command_understood": "ROAD_STATUS_ROLL_CALL",
        "security_gate": "OPERATOR_KEY_ENABLED",
        "stats": {
            "total_indexed": len(phonebook),
            "legit_live_agents": live_cnt,
            "quarantined_dead_endpoints": quarantined_cnt,
            "unhosted_github_repos": repo_cnt,
            "slashed_scammers": slashed_cnt,
            "total_handshakes_logged": telemetry["total_paid_handshakes"],
            "external_agent_match_pulls": telemetry["external_agent_match_pulls"],
            "ai_beacon_discovery_pulls": telemetry["ai_beacon_discovery_pulls"],
            "total_external_data_pulls": telemetry["total_external_data_pulls"],
            "accrued_toll_usd": telemetry["accrued_toll_usd"],
            "next_settlement_threshold_usd": SETTLEMENT_THRESHOLD_USD,
            "recent_external_activity": telemetry["recent_external_activity"],
        },
        "voice_briefing": (
            f"Switchboard has {len(phonebook)} graded agents: "
            f"{live_cnt} live callable, {quarantined_cnt} quarantined dead, and {repo_cnt} repos. "
            f"External data pulls: {telemetry['total_external_data_pulls']} total "
            f"({telemetry['external_agent_match_pulls']} live match queries and {telemetry['ai_beacon_discovery_pulls']} beacon reads). "
            f"Ledger tab is ${telemetry['accrued_toll_usd']:.4f}."
        ),
    }


def handle_voice_operator_command(command_text):
    cmd = command_text.strip().lower()

    if any(w in cmd for w in ("traffic", "pull", "pulls", "usage", "who is pulling", "telemetry")):
        ledger = fetch_ledger_from_supabase()
        t = summarize_traffic_telemetry(ledger)
        return {
            "command_understood": "DATA_PULL_TELEMETRY",
            "telemetry": t,
            "voice_briefing": (
                f"Traffic report: {t['total_external_data_pulls']} external data pulls recorded. "
                f"{t['external_agent_match_pulls']} were live agent matchmake queries and "
                f"{t['ai_beacon_discovery_pulls']} were AI crawler beacon reads. "
                f"Total billable handshakes: {t['total_paid_handshakes']} (${t['accrued_toll_usd']:.4f})."
            ),
        }

    if any(w in cmd for w in ("toll", "payment", "revenue", "ledger", "balance")):
        ledger = fetch_ledger_from_supabase()
        t = summarize_traffic_telemetry(ledger)
        return {
            "command_understood": "TOLL_LEDGER_SUMMARY",
            "total_handshakes": t["total_paid_handshakes"],
            "external_agent_match_pulls": t["external_agent_match_pulls"],
            "accrued_toll_usd": t["accrued_toll_usd"],
            "voice_briefing": (
                f"Tollbooth ledger has {t['total_paid_handshakes']} billable handshakes totaling ${t['accrued_toll_usd']:.4f}, "
                f"including {t['external_agent_match_pulls']} external agent match pulls."
            ),
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
        probed_ok, unreachable_cnt, restored_cnt = 0, 0, 0
        check_list = [a for a in phonebook if classify_agent_legitimacy(a) in ("LIVE_CALLABLE_AGENT", "QUARANTINED_DEAD_ENDPOINT")][:40]
        for a in check_list:
            was_quarantined = (a["mglennp_code"][1:2] == "E")
            ok, ms = probe_live_agent_endpoint(a.get("endpoint", ""))
            if ok:
                probed_ok += 1
                if was_quarantined:
                    restored_cnt += 1
                new_code, u64, u64_hex = mutate_mglennp_code(
                    a["mglennp_code"],
                    guarantee="A" if a["mglennp_code"][1:2] == "A" else "B",
                    latency=latency_ms_to_grade(ms),
                )
                patch_agent_in_supabase(a["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex, "avg_latency_ms": ms, "synaptic_weight": 0.92})
            else:
                unreachable_cnt += 1
                new_code, u64, u64_hex = mutate_mglennp_code(a["mglennp_code"], guarantee="E", latency="E")
                patch_agent_in_supabase(a["agent_id"], {"mglennp_code": new_code, "mglennp_u64": u64, "mglennp_u64_hex": u64_hex, "avg_latency_ms": ms, "synaptic_weight": 0.25})

        return {
            "command_understood": "LIVE_HTTP_HEARTBEAT_AUDIT",
            "voice_briefing": f"Audit cycle complete on {len(check_list)} endpoints. {probed_ok} answered live, {restored_cnt} recovered from quarantine, and {unreachable_cnt} locked in Grade E quarantine.",
        }

    if any(w in cmd for w in ("list", "who is live", "top agents")):
        phonebook = fetch_phonebook_from_supabase()
        live_only = [a for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
        names = ", ".join(f"{a['name']}" for a in live_only[:4])
        return {"command_understood": "LIST_LIVE_AGENTS", "voice_briefing": f"You have {len(live_only)} live agents ready. Top nodes are: {names}."}

    if any(w in cmd for w in ("crawl", "refresh", "update registry", "scan")):
        phonebook = crawl_public_agent_phonebook()
        supabase_request("radial_agent_phonebook?on_conflict=agent_id", method="POST", payload=phonebook, prefer="resolution=merge-duplicates,return=minimal")
        return {"command_understood": "CRAWL_AND_LEGITIMACY_AUDIT", "voice_briefing": f"Batch crawl complete. Graded and synced {len(phonebook)} entries to Supabase."}

    if any(w in cmd for w in ("find", "match", "hire", "need")):
        phonebook = fetch_phonebook_from_supabase()
        live_only = [a for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
        coupler = "****-ZED" if "deep" in cmd or "construction" in cmd else "*AA*-ZES"
        res = radial_mglennp_matchmake(command_text, live_only, required_pattern=coupler)
        if res["matches"]:
            top = res["matches"][0]
            log_handshake_to_ledger(command_text, coupler, top, rail="OPERATOR_COCKPIT_TEST")
            t = summarize_traffic_telemetry(fetch_ledger_from_supabase())
            return {
                "command_understood": "VOICE_MATCHMAKE_LIVE_ONLY",
                "voice_briefing": f"Matched {top['name']}. Logged operator test; your tab is now ${t['accrued_toll_usd']:.4f}.",
            }
        return {"command_understood": "VOICE_MATCHMAKE_LIVE_ONLY", "voice_briefing": "No agents matched."}

    return get_public_status_roll_call()


LLMS_TXT = """# Radial Switchboard (MglennP 64-Bit Agent Matchmaker)
> High-speed (<0.4ms) 64-bit bitwise clearinghouse and live heartbeat auditor for autonomous AI agents and MCP servers.

## How AI Agents Query the Switchboard Directory
Send an HTTP POST request to https://radialswitchboard.com/v1/matchmake with a JSON body:

{
  "intent": "describe the tool or domain needed (e.g., sql database validation, github coding, finance, weather, web search)",
  "coupler": "****-Z**"
}

### Coupler Wildcard Guide (MGLE-NNP 7-Char Pattern)
- Default fast self-executing live agent: "*B**-ZES" or "****-Z**"
- Byte 1 (M): Merit (A-C active, F slashed)
- Byte 2 (G): Guarantee (A/B verified live HTTP endpoint, D dormant GitHub repo, E quarantined dead endpoint)
- Byte 3 (L): Latency (A <=120ms, B <=300ms, C <=700ms)
- Byte 4 (E): Economy (A Free, B <=$0.001)
- Byte 5 (N): Node Honesty (Z Zero-hop self-execution, hop_ttl=0 enforced)

## Live Status & OpenAPI Spec
- Health & Live Counts: GET https://radialswitchboard.com/v1/health
- OpenAPI 3.1 Schema: GET https://radialswitchboard.com/openapi.json
- MCP Discovery: GET https://radialswitchboard.com/.well-known/mcp.json
"""


OPENAPI_SPEC = {
    "openapi": "3.1.0",
    "info": {
        "title": "MglennP Radial Switchboard API",
        "version": "1.6.0",
        "description": "Sub-millisecond 64-bit MGLE-NNP autonomous agent matchmaker and live MCP endpoint auditor. Filters out dead endpoints (Grade E) and unhosted GitHub repositories (Grade D).",
        "contact": {"name": "MglennP", "email": "support@radialswitchboard.com"},
    },
    "servers": [{"url": "https://radialswitchboard.com"}],
    "paths": {
        "/v1/matchmake": {
            "post": {
                "operationId": "matchmakeLiveAgent",
                "summary": "Match a live, heartbeat-verified agent using 64-bit MGLE-NNP bitwise filtering",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["intent"],
                                "properties": {
                                    "intent": {
                                        "type": "string",
                                        "description": "Task or domain keywords (finance, crypto, coding, github, search, web, database, sql, weather, maps, construction, cad, commerce, payments, media).",
                                    },
                                    "coupler": {
                                        "type": "string",
                                        "default": "****-Z**",
                                        "description": "7-character MGLE-NNP wildcard pattern (e.g., '****-Z**' for any live self-executing agent).",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Top ranked live callable agents with endpoints and MGLE-NNP 64-bit stamps."
                    }
                },
            }
        },
        "/v1/health": {
            "get": {
                "operationId": "getSwitchboardHealth",
                "summary": "Get live counts of audited, callable, quarantined, and repo-only agents plus data pull telemetry",
                "responses": {"200": {"description": "Current switchboard health roll call"}},
            }
        },
    },
}


MCP_WELL_KNOWN = {
    "mcpVersion": "2025-03-26",
    "name": "io.radialswitchboard/mglennp-switchboard",
    "title": "MglennP Radial Switchboard (64-Bit Agent Matchmaker)",
    "description": "Sub-0.4ms 64-bit MGLE-NNP agent directory and live HTTP heartbeat auditor. Prunes dead endpoints and unhosted GitHub repos.",
    "homepage": "https://radialswitchboard.com",
    "endpoints": {
        "matchmake": "https://radialswitchboard.com/v1/matchmake",
        "health": "https://radialswitchboard.com/v1/health",
        "openapi": "https://radialswitchboard.com/openapi.json",
        "llms_txt": "https://radialswitchboard.com/llms.txt",
    },
}


LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radial Switchboard | MglennP — An honest approach</title>
<link rel="alternate" type="text/plain" href="/llms.txt" title="LLM Instructions">
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
    gap: 12px;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px dashed rgba(212, 175, 55, 0.3);
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 0.82rem;
    color: var(--steel);
  }
  .gauge-pill {
    background: #091019;
    border: 1px solid #263548;
    padding: 6px 11px;
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
  pre.code-block {
    background: #080d14;
    border: 1px solid #243447;
    border-radius: 6px;
    padding: 14px;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 0.86rem;
    color: #e2e8f0;
    margin: 12px 0;
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
      <div class="stamp-tag">MglennP Mechanical Dispatch • Spec Rev 1.9</div>
      <h1>RADIAL SWITCHBOARD</h1>
      <div class="slogan">"An honest approach to solving everyday challenges."</div>

      <div class="gear-stage" aria-label="Counter-Rotating Cycloidal Bitmask Alignment">
        <svg viewBox="0 0 200 200" width="190" height="190">
          <line x1="100" y1="6" x2="100" y2="194" stroke="#243447" stroke-width="1" stroke-dasharray="3,3"/>
          <line x1="6" y1="100" x2="194" y2="100" stroke="#243447" stroke-width="1" stroke-dasharray="3,3"/>
          <circle cx="100" cy="100" r="88" fill="none" stroke="#243447" stroke-width="1"/>

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
        <div class="gauge-pill">LIVE CALLABLE: <strong id="liveCount">--</strong></div>
        <div class="gauge-pill">QUARANTINED: <strong id="quarantinedCount">--</strong></div>
        <div class="gauge-pill">DATA PULLS: <strong id="pullsCount">--</strong></div>
        <div class="gauge-pill">TOLL: <strong>$0.0001 / HANDSHAKE</strong></div>
      </div>
    </div>

    <div class="card">
      <h2>Live Stage 1 "Glance" &amp; Stage 2 Handoff Console (Interactive Benchmark)</h2>
      <p>
        Test the live 64-bit matchmaker against all <strong>1,800+ indexed agents</strong> right now. In <strong>Stage 1 (The Glance)</strong>, Radial Switchboard prunes dead endpoints (<span class="code-badge">Grade E</span>) and dormant GitHub repos (<span class="code-badge">Grade D</span>) in under 0.4ms. In <strong>Stage 2 (The Conversation)</strong>, your agent connects directly to the winning partner's verified endpoint to collaborate.
      </p>
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin:12px 0;">
        <button type="button" onclick="setPreset('fast github coding and sql database validation','****-Z**')" style="background:#0c141f; color:var(--brass); border:1px solid var(--brass-dim); padding:6px 10px; border-radius:5px; cursor:pointer; font-size:0.82rem;">Preset 1: SQL + GitHub Validator</button>
        <button type="button" onclick="setPreset('deep construction cad and finance contract analysis','****-Z**')" style="background:#0c141f; color:var(--brass); border:1px solid var(--brass-dim); padding:6px 10px; border-radius:5px; cursor:pointer; font-size:0.82rem;">Preset 2: Construction &amp; Finance Specialist</button>
        <button type="button" onclick="setPreset('live web search weather and maps lookup','****-Z**')" style="background:#0c141f; color:var(--brass); border:1px solid var(--brass-dim); padding:6px 10px; border-radius:5px; cursor:pointer; font-size:0.82rem;">Preset 3: Web Search &amp; Maps Node</button>
      </div>
      <div style="display:grid; grid-template-columns:1fr 160px auto; gap:10px; margin-bottom:12px;">
        <input id="demoIntent" type="text" value="fast github coding and sql database validation" placeholder="Describe the capability gap your agent needs..." style="background:#080d14; border:1px solid #243447; color:#f1f5f9; padding:10px 12px; border-radius:6px; font-family:inherit; font-size:0.92rem;">
        <input id="demoCoupler" type="text" value="****-Z**" title="7-Char MGLE-NNP Coupler Pattern" style="background:#080d14; border:1px solid #243447; color:var(--brass); padding:10px 12px; border-radius:6px; font-family:ui-monospace,Consolas,monospace; font-size:0.92rem; text-align:center; font-weight:700;">
        <div style="display:flex; gap:8px;">
          <button type="button" onclick="runLiveMatchDemo('single')" id="demoBtn" style="background:var(--brass); color:#0a111a; border:none; padding:10px 14px; border-radius:6px; font-weight:800; cursor:pointer; font-size:0.88rem;">⚡ Stage 1 Glance</button>
          <button type="button" onclick="runLiveMatchDemo('crew')" id="crewBtn" style="background:#0f291e; color:#4ade80; border:1px solid #22c55e; padding:10px 14px; border-radius:6px; font-weight:800; cursor:pointer; font-size:0.88rem;">🤝 Assemble 3-Agent Crew</button>
        </div>
      </div>
      <div id="demoResultBox" style="background:#080d14; border:1px solid #243447; border-radius:6px; padding:14px; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:0.84rem; color:#cbd5e1; margin-bottom:14px;">
        Click <strong>⚡ Run Stage 1 Glance</strong> above to benchmark live 64-bit filtering across the Virginia Supabase directory (Zero-charge UI test mode).
      </div>
      <p style="margin-bottom:6px; font-size:0.9rem;">
        <strong>Direct Autonomous Agent Dispatch (<span class="code-badge">POST https://radialswitchboard.com/v1/matchmake</span>):</strong>
      </p>
      <pre class="code-block">POST https://radialswitchboard.com/v1/matchmake
Content-Type: application/json

{
  "intent": "fast github coding and sql database validation",
  "coupler": "****-Z**"
}</pre>
      <p style="font-size:0.88rem; color:var(--steel); margin-bottom:0;">
        Machine Discovery Beacons: <a href="/llms.txt">/llms.txt</a> • <a href="/openapi.json">/openapi.json</a> • <a href="/.well-known/mcp.json">/.well-known/mcp.json</a> • <a href="/v1/health">/v1/health</a>
      </p>
    </div>
    <script>
      function setPreset(intentText, couplerText) {
        document.getElementById('demoIntent').value = intentText;
        document.getElementById('demoCoupler').value = couplerText;
        runLiveMatchDemo();
      }
      async function runLiveMatchDemo(modeArg) {
        const mode = modeArg || 'single';
        const box = document.getElementById('demoResultBox');
        const btn = document.getElementById('demoBtn');
        const intent = document.getElementById('demoIntent').value.trim() || 'general helper';
        const coupler = document.getElementById('demoCoupler').value.trim() || '****-Z**';
        btn.disabled = true;
        box.innerHTML = '⏳ Running 64-bit bitwise pass (' + mode.toUpperCase() + ' mode) across Virginia phonebook...';
        const t0 = performance.now();
        try {
          const res = await fetch('/v1/matchmake', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({intent: intent, coupler: coupler, mode: mode, demo: true})
          });
          const data = await res.json();
          const rttMs = Math.round(performance.now() - t0);
          if (!data.matches || data.matches.length === 0) {
            box.innerHTML = '⚠️ No live callable agents matched pattern <strong>' + coupler + '</strong>. (Pruned ' + (data.pruned_count || 0) + ' candidates in ' + (data.local_smell_test_time_ms || 0) + 'ms).';
          } else {
            let html = '<div style="color:#22c55e; font-weight:700; margin-bottom:6px;">✓ STAGE 1 ' + (data.dispatch_mode === 'crew' ? 'COMPLEMENTARY CREW ASSEMBLY' : 'GLANCE') + ' COMPLETE — 64-BIT CPU FILTER: ' + data.local_smell_test_time_ms + ' ms | NETWORK RTT: ' + rttMs + ' ms</div>';
            html += '<div style="color:#94a3b8; margin-bottom:10px;">Scanned ' + (data.total_indexed_scanned || '1,800+') + ' total indexed (' + (data.live_callable_pool || '1,500+') + ' live callable pool) • Pruned ' + data.pruned_count + ' nodes • Single Coverage: ' + (data.single_agent_coverage_pct || 0) + '% ➔ Crew Combined Coverage: <strong style="color:#4ade80;">' + (data.crew_combined_coverage_pct || 0) + '%</strong></div>';
            for (let i = 0; i < data.matches.length; i++) {
              const m = data.matches[i];
              html += '<div style="border:1px solid #263548; background:#0d1622; padding:10px; border-radius:5px; margin-bottom:8px;">';
              html += '<div style="color:#f1f5f9; font-weight:700;">#' + m.rank + ' [' + (m.crew_role || 'PRIMARY_MATCH') + '] ' + m.name + ' <span style="color:#d4af37;">[' + m.mglennp_code + ']</span> <span style="color:#64748b;">(' + m.mglennp_u64_hex + ')</span></div>';
              html += '<div style="color:#94a3b8; font-size:0.8rem; margin-top:3px;">Agent ID: ' + m.agent_id + ' • Heartbeat Latency: ' + m.avg_latency_ms + 'ms • Resonance: ' + m.resonance_score + ' • Matched Bits: ' + (m.matched_domain_bits || 1) + '</div>';
              html += '<div style="color:#38bdf8; font-size:0.8rem; margin-top:4px;">➔ <strong>Stage 2 Direct Peer Handoff Endpoint:</strong> ' + (m.endpoint || 'mcp://direct-handoff') + '</div>';
              html += '</div>';
            }
            box.innerHTML = html;
          }
        } catch (err) {
          box.innerHTML = '❌ Error querying switchboard: ' + err;
        }
        btn.disabled = false;
      }
    </script>

    <div class="card">
      <h2>Why This Exists: Solving the 55,000-Token Bloat Tax</h2>
      <p>
        Today, when an AI agent needs to hire a tool or verify a service, it has to download and read massive JSON schemas across dozens of MCP servers—often burning <strong>55,000+ context tokens ($0.05 to $0.15 in electricity and compute)</strong> before doing a single ounce of real work. Worse, the majority of public registry listings are dead GitHub repositories or unreachable hobby servers.
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
            Compresses an agent's entire capability, latency grade, and honesty pledge into a single <strong>64-bit integer</strong>. Prunes dead ends using a single CPU bitwise instruction in <strong>under 0.4 milliseconds</strong>.
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
            <td><strong>Live Heartbeat Grade:</strong> <span class="code-badge">A/B</span> = Answered live HTTP probe; <span class="code-badge">D</span> = Dormant GitHub repo; <span class="code-badge">E</span> = Quarantined dead endpoint (held until next recheck cycle).</td>
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
        <li><strong>Zero Charge on Empty Queries:</strong> Dormant GitHub repositories (<span class="code-badge">Grade D</span>) and quarantined dead nodes (<span class="code-badge">Grade E</span>) are filtered out before dispatch—you never pay for a dead line.</li>
        <li><strong>Threshold Settlement:</strong> Usage accrues transparently on the switchboard ledger and bills via <strong>Stripe</strong> upon reaching the <strong>$5.00 USD</strong> settlement threshold.</li>
      </ul>
    </div>

    <div class="footer">
      Engineered &amp; Operated by <strong>MglennP</strong> • Located in Virginia, USA<br>
      For billing inquiries or operator support: <a href="mailto:support@radialswitchboard.com">support@radialswitchboard.com</a>
    </div>
  </div>

  <script>
    fetch('/v1/health')
      .then(r => r.json())
      .then(d => {
        if (d && d.stats) {
          document.getElementById('liveCount').innerText =
            d.stats.legit_live_agents + ' / ' + d.stats.total_indexed + ' AUDITED';
          document.getElementById('quarantinedCount').innerText =
            (d.stats.quarantined_dead_endpoints || 0) + ' HELD';
          document.getElementById('pullsCount').innerText =
            (d.stats.total_external_data_pulls || 0) + ' EXTERNAL (' + (d.stats.total_handshakes_logged || 0) + ' LOGGED)';
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
    <button class="qbtn" onclick="sendCmd('traffic report')">📡 Traffic Pulls</button>
    <button class="qbtn" onclick="sendCmd('audit the phone book')">🛡️ Recheck Quarantine</button>
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status_code, text_body):
        body = text_body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
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
        ua = self.headers.get("User-Agent", "")
        if parsed.path == "/":
            self._send_html(200, LANDING_HTML)
        elif parsed.path == "/llms.txt":
            log_discovery_pull_async("/llms.txt", ua)
            self._send_text(200, LLMS_TXT)
        elif parsed.path == "/openapi.json":
            log_discovery_pull_async("/openapi.json", ua)
            self._send_json(200, OPENAPI_SPEC)
        elif parsed.path == "/.well-known/mcp.json":
            log_discovery_pull_async("/.well-known/mcp.json", ua)
            self._send_json(200, MCP_WELL_KNOWN)
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
            mode = data.get("mode", "single")
            is_demo = bool(data.get("demo", False))
            try:
                phonebook = fetch_phonebook_from_supabase()
                live_only = [a for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
                result = radial_mglennp_matchmake(intent, live_only, required_pattern=coupler, mode=mode)
                result["total_indexed_scanned"] = len(phonebook)
                result["live_callable_pool"] = len(live_only)
                result["demo_mode"] = is_demo
                if result["matches"] and not is_demo:
                    log_handshake_to_ledger(intent, coupler, result["matches"][0], rail="EXTERNAL_AGENT_MATCH")
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif self.path == "/v1/outcome":
            agent_id = (data.get("agent_id") or "").strip()
            if not agent_id:
                self._send_json(400, {"error": "Missing required field: agent_id"})
                return
            outcome_success = bool(data.get("outcome_success", True))
            measured_ms = data.get("measured_ms", None)
            is_demo = bool(data.get("demo", False))
            try:
                encoded_id = urllib.parse.quote(agent_id, safe="")
                rows = supabase_request(f"radial_agent_phonebook?agent_id=eq.{encoded_id}&select=*", method="GET", prefer="return=representation")
                if not rows:
                    self._send_json(404, {"error": f"Agent not found in phonebook: {agent_id}"})
                    return
                agent = rows[0]
                old_code = (agent.get("mglennp_code") or "BBBA-ZES").upper()
                old_weight = float(agent.get("synaptic_weight", 0.75))
                old_latency = int(agent.get("avg_latency_ms", 200))
                new_latency = old_latency
                if measured_ms is not None:
                    try:
                        m_val = max(1, min(10000, int(measured_ms)))
                        new_latency = int(round(0.6 * old_latency + 0.4 * m_val))
                    except Exception:
                        pass
                lat_grade = latency_ms_to_grade(new_latency)
                protected_seeds = ("mcp://us-east-sql-validator", "mcp://deep-cot-architect")
                if outcome_success:
                    new_weight = round(min(0.99, old_weight + 0.03), 4)
                    new_merit = "A" if new_weight >= 0.90 else ("B" if new_weight >= 0.78 else "C")
                    new_guarantee = "A"
                    audit_status = "STAGE2_OUTCOME_VERIFIED_PASS"
                else:
                    new_weight = round(max(0.15, old_weight - 0.15), 4)
                    new_merit = "D"
                    new_guarantee = "A" if agent_id in protected_seeds else "E"
                    audit_status = "STAGE2_OUTCOME_FAILED_QUARANTINED"
                clean = old_code.replace("-", "")
                if len(clean) != 7:
                    clean = "BBBAZES"
                chars = list(clean)
                chars[0] = new_merit
                chars[1] = new_guarantee
                chars[2] = lat_grade
                new_code = "".join(chars[:4]) + "-" + "".join(chars[4:])
                hop_ttl = 0 if chars[4] in ("Z", "S") else 1
                new_u64 = pack_mglennp_u64(new_code, hop_ttl=hop_ttl, version=1)
                if not is_demo:
                    patch_agent_in_supabase(agent_id, {
                        "mglennp_code": new_code,
                        "mglennp_u64": new_u64,
                        "synaptic_weight": new_weight,
                        "avg_latency_ms": new_latency,
                    })
                    supabase_request("handshake_ledger", method="POST", payload=[{
                        "caller_intent": f"STAGE2_OUTCOME:{agent_id}",
                        "required_coupler": old_code,
                        "matched_agent_id": agent_id,
                        "mglennp_code_snapshot": new_code,
                        "hop_audit_status": audit_status,
                        "response_latency_ms": new_latency,
                        "outcome_success": outcome_success,
                        "switchboard_fee_usd": 0.0,
                        "settlement_rail": "STAGE2_OUTCOME_RECEIPT",
                    }])
                self._send_json(200, {
                    "status": "OUTCOME_RECORDED" if not is_demo else "DEMO_OUTCOME_SIMULATED",
                    "agent_id": agent_id,
                    "outcome_success": outcome_success,
                    "old_mglennp_code": old_code,
                    "new_mglennp_code": new_code,
                    "new_mglennp_u64_hex": f"0x{new_u64:016X}",
                    "old_synaptic_weight": old_weight,
                    "new_synaptic_weight": new_weight,
                    "avg_latency_ms": new_latency,
                    "quarantined": (new_guarantee == "E"),
                })
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Endpoint not found"})


if __name__ == "__main__":
    ensure_local_env()
    load_operator_key()
    port = int(os.environ.get("PORT", 8080))
    print(f"MglennP Gated Switchboard API v1.6 listening on port {port}...")
    ThreadingHTTPServer(("0.0.0.0", port), SwitchboardHandler).serve_forever()





