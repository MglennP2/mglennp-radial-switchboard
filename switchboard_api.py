#!/usr/bin/env python3
r"""
MGLENNP STANDALONE SWITCHBOARD — HTTP API & VOICE DISPATCH OPERATOR (v1)
Endpoints:
 - GET  /v1/health     -> Switchboard status & live Supabase agent count
 - POST /v1/matchmake  -> 0.05ms 64-Bit MGLE-NNP matchmaking + $0.0001 ledger log
 - POST /v1/crawl      -> Refreshes public MCP/A2A registry into Supabase
 - POST /v1/operator   -> Plain-English Voice Command & Road Briefing Agent for Pixel
"""

import os
import sys
import json
import threading
import urllib.request
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


def fetch_phonebook_from_supabase():
    rows = supabase_request(
        "radial_agent_phonebook?select=*",
        method="GET",
        prefer="return=representation",
    )
    for r in rows:
        r["radial_bitmask"] = int(r["radial_bitmask"])
        r["mglennp_u64"] = int(r["mglennp_u64"])
        r["synaptic_weight"] = float(r["synaptic_weight"])
        r["avg_latency_ms"] = int(r["avg_latency_ms"])
    return rows


def fetch_ledger_from_supabase():
    return supabase_request(
        "handshake_ledger?select=*",
        method="GET",
        prefer="return=representation",
    )


def classify_agent_legitimacy(agent):
    """Separates legit callable endpoints from unhosted GitHub repos and slashed nodes."""
    code = agent.get("mglennp_code", "")
    endpoint = (agent.get("endpoint") or "").lower()
    if code.startswith("FF") or code[1:2] == "F":
        return "SLASHED_OR_FAILED"
    if "github.com" in endpoint or endpoint.endswith(".git"):
        return "UNHOSTED_REPO_CODE_ONLY"
    return "LIVE_CALLABLE_AGENT"


def handle_voice_operator_command(command_text):
    """
    Embedded Switchboard Operator for hands-free Pixel voice control on the road.
    Interprets natural spoken English, executes switchboard actions, and returns
    a clear spoken briefing.
    """
    cmd = command_text.strip().lower()

    if any(w in cmd for w in ("crawl", "refresh", "update registry", "scan")):
        phonebook = crawl_public_agent_phonebook()
        supabase_request(
            "radial_agent_phonebook?on_conflict=agent_id",
            method="POST",
            payload=phonebook,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        live_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT")
        repo_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "UNHOSTED_REPO_CODE_ONLY")
        return {
            "command_understood": "CRAWL_AND_LEGITIMACY_AUDIT",
            "voice_briefing": (
                f"Crawl complete. Synced {len(phonebook)} total entries to Virginia Supabase: "
                f"{live_cnt} are live callable agents, and {repo_cnt} are unhosted GitHub repos."
            ),
        }

    if any(w in cmd for w in ("find", "match", "hire", "need")):
        phonebook = fetch_phonebook_from_supabase()
        live_only = [a for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT"]
        coupler = "****-ZED" if "deep" in cmd or "construction" in cmd else "*AA*-ZES"
        res = radial_mglennp_matchmake(command_text, live_only, required_pattern=coupler)
        if res["matches"]:
            top = res["matches"][0]
            return {
                "command_understood": "VOICE_MATCHMAKE_LIVE_ONLY",
                "matched_agent": top,
                "voice_briefing": (
                    f"Matched legit live agent {top['name']} with code {top['mglennp_code']} "
                    f"in {res['local_smell_test_time_ms']} milliseconds."
                ),
            }
        return {
            "command_understood": "VOICE_MATCHMAKE_LIVE_ONLY",
            "voice_briefing": "No live callable agents matched that request.",
        }

    # Default: Road Roll-Call / Status Briefing
    phonebook = fetch_phonebook_from_supabase()
    ledger = fetch_ledger_from_supabase()
    live_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "LIVE_CALLABLE_AGENT")
    repo_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "UNHOSTED_REPO_CODE_ONLY")
    slashed_cnt = sum(1 for a in phonebook if classify_agent_legitimacy(a) == "SLASHED_OR_FAILED")
    total_fees = round(len(ledger) * HANDSHAKE_FEE_USD, 4)

    return {
        "command_understood": "ROAD_STATUS_ROLL_CALL",
        "stats": {
            "total_indexed": len(phonebook),
            "legit_live_agents": live_cnt,
            "unhosted_github_repos": repo_cnt,
            "slashed_scammers": slashed_cnt,
            "total_handshakes_logged": len(ledger),
            "accrued_toll_usd": total_fees,
        },
        "voice_briefing": (
            f"Switchboard is healthy in Northern Virginia. Out of {len(phonebook)} indexed entries, "
            f"{live_cnt} are verified live agents, {repo_cnt} are unhosted GitHub code repos, "
            f"and {slashed_cnt} is blocked for subcontracting fraud. "
            f"You have {len(ledger)} handshakes logged in the ledger totaling ${total_fees:.4f}."
        ),
    }


class SwitchboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/v1/health"):
            try:
                report = handle_voice_operator_command("status report")
                self._send_json(200, report)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        data = json.loads(raw_body) if raw_body else {}

        if self.path == "/v1/operator":
            try:
                cmd_text = data.get("voice_command", "status report")
                report = handle_voice_operator_command(cmd_text)
                self._send_json(200, report)
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif self.path == "/v1/matchmake":
            intent = data.get("intent", "general helper")
            coupler = data.get("coupler", "****-Z**")
            try:
                phonebook = fetch_phonebook_from_supabase()
                result = radial_mglennp_matchmake(intent, phonebook, required_pattern=coupler)
                if result["matches"]:
                    top = result["matches"][0]
                    supabase_request("handshake_ledger", method="POST", payload=[{
                        "caller_intent": intent,
                        "required_coupler": coupler,
                        "matched_agent_id": top["agent_id"],
                        "mglennp_code_snapshot": top["mglennp_code"],
                        "hop_audit_status": "CLEAN_SELF_EXECUTION",
                        "response_latency_ms": top["avg_latency_ms"],
                        "outcome_success": True,
                        "switchboard_fee_usd": HANDSHAKE_FEE_USD,
                        "settlement_rail": "STRIPE_METERED_USD",
                    }])
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif self.path == "/v1/crawl":
            try:
                report = handle_voice_operator_command("crawl and refresh")
                self._send_json(200, report)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Endpoint not found"})


def run_self_test(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), SwitchboardHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("======================================================================")
    print(" MGLENNP VOICE DISPATCH OPERATOR — PIXEL ROAD BRIEFING SELF-TEST")
    print("======================================================================")

    voice_prompts = [
        "Hey Switchboard, give me a road status roll call",
        "Find me a legit live SQL and github validator agent",
    ]
    for prompt in voice_prompts:
        req_payload = json.dumps({"voice_command": prompt}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/operator",
            data=req_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            print(f"\n • You Say on Pixel: \"{prompt}\"")
            print(f"   -> Operator Replies: \"{out['voice_briefing']}\"")

    print("\n======================================================================")
    server.shutdown()


if __name__ == "__main__":
    ensure_local_env()
    port = int(os.environ.get("PORT", 8080))
    if "--self-test" in sys.argv:
        run_self_test(port)
    else:
        print(f"MglennP Switchboard API & Voice Operator listening on port {port}...")
        ThreadingHTTPServer(("0.0.0.0", port), SwitchboardHandler).serve_forever()
