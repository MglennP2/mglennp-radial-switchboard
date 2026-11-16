#!/usr/bin/env python3
"""
MglennP Radial Switchboard -- Zero-Dependency MCP Stdio Bridge (Spec Rev 3.2.0)
Usage: python3 mcp_stdio_bridge.py | Contact: support@radialswitchboard.com
"""
import json, os, sys, urllib.request
MCP_URL = os.environ.get("RADIAL_MCP_URL", "https://radialswitchboard.com/mcp")
PASS_TOKEN = os.environ.get("RADIAL_PASS_TOKEN", "").strip()
for incoming in sys.stdin:
    raw = incoming.strip()
    if not raw:
        continue
    try:
        hdrs = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "mcp-protocol-version": "2026-07-28",
            "User-Agent": "MglennP-RadialStdioBridge/3.2.0",
        }
        if PASS_TOKEN:
            hdrs["X-Radial-Pass"] = PASS_TOKEN
        req = urllib.request.Request(MCP_URL, data=raw.encode("utf-8"), headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            if body:
                sys.stdout.write(body + "\n")
                sys.stdout.flush()
    except Exception as exc:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(exc)}}) + "\n")
        sys.stdout.flush()
