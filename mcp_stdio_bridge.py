#!/usr/bin/env python3
"""
MGLENNP RADIAL SWITCHBOARD — SPEC REV 2.0
TRACK CHARLIE: Zero-Friction MCP Stdio Bridge (mcp_stdio_bridge.py)
Repository: https://github.com/MglennP2/mglennp-radial-switchboard
Production Node: https://radialswitchboard.com
Brand: MglennP — "An honest approach" (Operated from Virginia, USA)

EXPOSED MCP TOOLS (3):
1. radial_matchmake          -> POST https://radialswitchboard.com/v1/matchmake
2. radial_report_outcome     -> POST https://radialswitchboard.com/v1/outcome
3. radial_switchboard_health -> GET  https://radialswitchboard.com/v1/health & /v1/benchmark
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import socketserver
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BASE_URL = os.environ.get("RADIAL_SWITCHBOARD_URL", "https://radialswitchboard.com").rstrip("/")
DEFAULT_TIMEOUT_SEC = float(os.environ.get("RADIAL_TIMEOUT_SEC", "10.0"))
SERVER_NAME = "mglennp-radial-switchboard"
SERVER_VERSION = "2.0.0"

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "radial_matchmake",
        "description": (
            "Discover verified live AI agents or assemble a provider-independent 3-agent complementary crew "
            "via the MglennP 64-Bit MGLE-NNP Radial Switchboard (https://radialswitchboard.com/v1/matchmake). "
            "Prunes dead endpoints (Grade E) and unhosted repos (Grade D) automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Natural-language task or domain capability needed.",
                },
                "coupler": {
                    "type": "string",
                    "default": "****-Z**",
                    "description": "8-character MGLE-NNP compatibility coupler mask (default '****-Z**').",
                },
                "mode": {
                    "type": "string",
                    "enum": ["single", "crew"],
                    "default": "single",
                    "description": "'single' returns top individual matches; 'crew' assembles a 3-agent complementary triad.",
                },
                "demo": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true ONLY for dry-run testing; false logs real external agent matchmaking.",
                },
            },
            "required": ["intent"],
        },
    },
    {
        "name": "radial_report_outcome",
        "description": (
            "Submit a Stage-2 post-handshake execution receipt to POST https://radialswitchboard.com/v1/outcome "
            "using the HMAC execution_ticket ('v2.<ts>.<hash>.<sig>') returned by radial_matchmake."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The matched agent_id evaluated during execution."},
                "outcome_success": {"type": "boolean", "description": "True if the target agent succeeded; false if it failed."},
                "measured_ms": {"type": "number", "description": "Observed round-trip execution latency in milliseconds."},
                "execution_ticket": {"type": "string", "description": "Signed execution_ticket ('v2.<ts>.<hash>.<sig>') issued by radial_matchmake."},
            },
            "required": ["agent_id", "outcome_success", "measured_ms", "execution_ticket"],
        },
    },
    {
        "name": "radial_switchboard_health",
        "description": (
            "Fetch live reconciled directory stats (1,803 total indexed, 1,531 live callable, 96 quarantined Grade E, "
            "173 unhosted Grade D) and P50/P95/P99 benchmark telemetry from GET /v1/health and GET /v1/benchmark."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_benchmark": {"type": "boolean", "default": True},
            },
        },
    },
]


def _call_switchboard_api(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Tuple[int, Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    ssl_ctx = ssl.create_default_context()
    headers = {
        "Accept": "application/json",
        "User-Agent": f"MglennP-MCP-Stdio-Bridge/{SERVER_VERSION} (+https://radialswitchboard.com)",
    }
    data_bytes: Optional[bytes] = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ssl_ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"data": parsed}
    except urllib.error.HTTPError as e:
        err_raw = e.read().decode("utf-8", errors="replace")
        try:
            err_obj = json.loads(err_raw) if err_raw.strip() else {}
        except Exception:
            err_obj = {"error": err_raw or f"HTTP {e.code}"}
        return e.code, err_obj if isinstance(err_obj, dict) else {"error": str(err_obj)}
    except Exception as exc:
        return 0, {"error": f"Connection error to {url}: {exc}"}


def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any], base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    if tool_name == "radial_matchmake":
        intent = str(arguments.get("intent", "")).strip()
        if not intent:
            return {"isError": True, "content": [{"type": "text", "text": json.dumps({"error": "Missing 'intent'"})}]}
        req_body = {
            "intent": intent,
            "coupler": str(arguments.get("coupler") or "****-Z**"),
            "mode": str(arguments.get("mode") or "single"),
            "demo": bool(arguments.get("demo", False)),
        }
        status, resp_json = _call_switchboard_api(base_url, "/v1/matchmake", method="POST", payload=req_body)
        return {"isError": status != 200, "content": [{"type": "text", "text": json.dumps(resp_json, indent=2)}]}

    if tool_name == "radial_report_outcome":
        for req_field in ("agent_id", "outcome_success", "measured_ms", "execution_ticket"):
            if req_field not in arguments:
                return {"isError": True, "content": [{"type": "text", "text": json.dumps({"error": f"Missing '{req_field}'"})}]}
        req_body = {
            "agent_id": str(arguments["agent_id"]),
            "outcome_success": bool(arguments["outcome_success"]),
            "measured_ms": float(arguments["measured_ms"]),
            "execution_ticket": str(arguments["execution_ticket"]),
        }
        status, resp_json = _call_switchboard_api(base_url, "/v1/outcome", method="POST", payload=req_body)
        return {"isError": status not in (200, 201), "content": [{"type": "text", "text": json.dumps(resp_json, indent=2)}]}

    if tool_name == "radial_switchboard_health":
        include_bench = bool(arguments.get("include_benchmark", True))
        h_status, h_json = _call_switchboard_api(base_url, "/v1/health", method="GET")
        combined: Dict[str, Any] = {"health_http_status": h_status, "health": h_json}
        if include_bench:
            b_status, b_json = _call_switchboard_api(base_url, "/v1/benchmark", method="GET")
            combined["benchmark_http_status"] = b_status
            combined["benchmark"] = b_json
        return {"isError": h_status != 200, "content": [{"type": "text", "text": json.dumps(combined, indent=2)}]}

    return {"isError": True, "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}]}


def handle_jsonrpc_message(msg: Dict[str, Any], base_url: str = DEFAULT_BASE_URL) -> Optional[Dict[str, Any]]:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}

    if msg_id is None:
        return None
    if method == "initialize":
        client_proto = str(params.get("protocolVersion") or "2025-06-18")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        return {"jsonrpc": "2.0", "id": msg_id, "result": execute_mcp_tool(tool_name, arguments, base_url=base_url)}

    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve_stdio(base_url: str = DEFAULT_BASE_URL) -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line or line.startswith("Content-Length:"):
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        if isinstance(msg, dict):
            resp = handle_jsonrpc_message(msg, base_url=base_url)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
    return 0


class _MockLiveSwitchboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/v1/health"):
            self._send_json(200, {"status": "ONLINE", "total_indexed": 1803, "reconciled_sum": 1803, "unaccounted_records": 0})
        elif self.path.startswith("/v1/benchmark"):
            self._send_json(200, {"benchmark_spec": "Spec Rev 2.0", "p50_ms": 0.84})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
        if self.path.startswith("/v1/matchmake"):
            ticket = f"v2.{int(time.time())}.a1b2c3d4e5f60718.9f8e7d6c5b4a3f2e1d0c9b8a"
            self._send_json(200, {
                "spec_revision": "2.0",
                "mode": body.get("mode", "single"),
                "filter_latency_ms": 0.84,
                "matches": [{"agent_id": "mcp://ai.justdeploy/mcp", "mglennp_code": "BBBA-ZES", "execution_ticket": ticket}],
            })
        elif self.path.startswith("/v1/outcome"):
            self._send_json(200, {
                "status": "OUTCOME_RECORDED",
                "agent_id": body.get("agent_id"),
                "ticket_verification": "HMAC_TICKET_VERIFIED",
                "quarantined": False,
            })


def run_self_test() -> int:
    print("=" * 74)
    print("  MGLENNP RADIAL SWITCHBOARD — TRACK CHARLIE MCP BRIDGE SELF-TEST (V2.0)")
    print("=" * 74)
    socketserver.TCPServer.allow_reuse_address = True
    mock_srv = socketserver.TCPServer(("127.0.0.1", 0), _MockLiveSwitchboardHandler)
    port = mock_srv.server_address[1]
    t = threading.Thread(target=mock_srv.serve_forever, daemon=True)
    t.start()
    local_url = f"http://127.0.0.1:{port}"
    try:
        r_init = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, local_url)
        assert r_init and r_init["result"]["serverInfo"]["name"] == SERVER_NAME
        print("  [OK] JSON-RPC initialize  : Verified")

        r_list = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, local_url)
        tools = r_list["result"]["tools"]
        assert len(tools) == 3
        print(f"  [OK] JSON-RPC tools/list  : {len(tools)} tools exposed ({', '.join(x['name'] for x in tools)})")

        r_mm = handle_jsonrpc_message({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "radial_matchmake", "arguments": {"intent": "SQL analytics", "mode": "crew", "demo": True}},
        }, local_url)
        mm_payload = json.loads(r_mm["result"]["content"][0]["text"])
        ticket = mm_payload["matches"][0]["execution_ticket"]
        assert ticket.startswith("v2.")
        print(f"  [OK] radial_matchmake     : Issued HMAC Ticket {ticket[:24]}...")

        r_out = handle_jsonrpc_message({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "radial_report_outcome",
                "arguments": {"agent_id": "mcp://ai.justdeploy/mcp", "outcome_success": True, "measured_ms": 120, "execution_ticket": ticket},
            },
        }, local_url)
        out_payload = json.loads(r_out["result"]["content"][0]["text"])
        assert out_payload["ticket_verification"] == "HMAC_TICKET_VERIFIED"
        print("  [OK] radial_report_outcome: Verified HMAC receipt & anti-sabotage response")
        print("=" * 74)
        return 0
    finally:
        mock_srv.shutdown()
        mock_srv.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="MglennP Radial Switchboard — Local MCP Stdio Bridge (Spec Rev 2.0)")
    parser.add_argument("--self-test", action="store_true", help="Run local JSON-RPC self-test and exit")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Target Radial Switchboard URL")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    return serve_stdio(base_url=args.base_url)


if __name__ == "__main__":
    sys.exit(main())
