#!/usr/bin/env python3
"""
MGLENNP RADIAL SWITCHBOARD — SPEC REV 2.0
TRACK ALPHA: 4-Point Mechanical JSON-RPC Auditor (parallel_scorecard_auditor.py)
Repository: https://github.com/MglennP2/mglennp-radial-switchboard
Production Node: https://radialswitchboard.com
Brand: MglennP — "An honest approach" (Operated from Virginia, USA)

STRICT FILE-LOCK COMPLIANCE:
- Standalone zero-dependency Python 3 standard-library module.
- Does NOT modify switchboard_api.py or radial_synapse_phonebook.py.
- Maps directly to radial_agent_phonebook columns (mglennp_code, mglennp_u64,
  mglennp_u64_hex, radial_bitmask, synaptic_weight, avg_latency_ms) while
  protecting internal system canaries.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_WORKERS = 100
DEFAULT_HTTP_TIMEOUT_SEC = 4.5
SUPABASE_FETCH_PAGE_SIZE = 1000
SUPABASE_UPSERT_BATCH_SIZE = 500

PROTECTED_CANARIES = {
    "mcp://us-east-sql-validator",
    "a2a://deep-contract-auditor",
    "mcp://suspicious-wrapper-bot",
}

DOMAIN_BITS: Dict[str, int] = {
    "finance": 1 << 0,
    "crypto": 1 << 1,
    "coding": 1 << 2,
    "github": 1 << 3,
    "search": 1 << 4,
    "web": 1 << 5,
    "database": 1 << 6,
    "sql": 1 << 7,
    "weather": 1 << 8,
    "maps": 1 << 9,
    "construction": 1 << 10,
    "cad": 1 << 11,
    "commerce": 1 << 12,
    "payments": 1 << 13,
    "media": 1 << 14,
    "general": 1 << 15,
}

DOMAIN_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "finance": ("finance", "stock", "equity", "market", "portfolio", "sec", "trading", "accounting", "tax"),
    "crypto": ("crypto", "blockchain", "web3", "defi", "token", "wallet", "ethereum", "bitcoin", "solana", "base"),
    "coding": ("code", "coding", "python", "typescript", "javascript", "compiler", "lint", "debug", "ide", "sandbox"),
    "github": ("github", "git", "repo", "repository", "pull_request", "commit", "gitlab"),
    "search": ("search", "query", "lookup", "index", "rag", "retrieve", "arxiv", "scholar"),
    "web": ("web", "browser", "scrape", "crawl", "http", "fetch", "url", "playwright", "puppeteer"),
    "database": ("database", "db", "redis", "mongo", "supabase", "firestore", "vector", "storage", "kv"),
    "sql": ("sql", "postgres", "postgresql", "mysql", "sqlite", "snowflake", "bigquery", "duckdb"),
    "weather": ("weather", "forecast", "climate", "meteorolog", "temperature", "noaa"),
    "maps": ("map", "maps", "geo", "location", "route", "navigation", "places", "address", "zip"),
    "construction": ("construction", "building", "contractor", "lumber", "deck", "roof", "inspection", "hvac", "plumbing"),
    "cad": ("cad", "3d", "mesh", "stl", "step", "dxf", "geometry", "render", "bim", "blender"),
    "commerce": ("commerce", "shop", "product", "inventory", "order", "shopify", "amazon", "catalog"),
    "payments": ("payment", "stripe", "invoice", "billing", "checkout", "ledger", "usdc", "x402", "payout"),
    "media": ("media", "video", "audio", "image", "youtube", "tts", "speech", "podcast", "thumbnail"),
}


def load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def compute_latency_grade(latency_ms: Optional[float], is_live: bool) -> str:
    if not is_live or latency_ms is None or latency_ms <= 0:
        return "E"
    if latency_ms <= 120.0:
        return "A"
    if latency_ms <= 300.0:
        return "B"
    if latency_ms <= 700.0:
        return "C"
    if latency_ms <= 1500.0:
        return "D"
    return "E"


def compute_domain_mask(text_blob: str, wired_tools: List[Dict[str, Any]]) -> int:
    parts = [text_blob or ""]
    for tool in wired_tools:
        if isinstance(tool, dict):
            parts.append(str(tool.get("name", "")))
            parts.append(str(tool.get("description", "")))
            schema = tool.get("inputSchema")
            if isinstance(schema, dict):
                props = schema.get("properties")
                if isinstance(props, dict):
                    parts.extend(str(k) for k in props.keys())
    combined = " ".join(parts).lower()

    mask = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            mask |= DOMAIN_BITS[domain]

    if mask == 0:
        mask = DOMAIN_BITS["general"]
    return mask & 0xFFFFFFFF


def compute_tool_schema_hash_16(wired_tools: List[Dict[str, Any]]) -> str:
    if not wired_tools:
        return "0000000000000000"

    canonical_tools = []
    for tool in sorted(wired_tools, key=lambda t: str(t.get("name", "") if isinstance(t, dict) else "")):
        if not isinstance(tool, dict):
            continue
        t_name = str(tool.get("name", "")).strip()
        schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        req_fields = schema.get("required") if isinstance(schema.get("required"), list) else []
        canonical_tools.append({
            "name": t_name,
            "props": sorted(str(k) for k in props.keys()),
            "required": sorted(str(r) for r in req_fields),
        })

    canonical_json = json.dumps(canonical_tools, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]


def pack_mgle_nnp_64bit(
    merit: str,
    guarantee: str,
    latency: str,
    economy: str,
    node_honesty: str,
    neighbor_proto: str,
    preference: str,
    hop_ttl: int = 0,
    version: int = 1,
) -> Tuple[str, str, int]:
    """
    Returns (stamp_7char, hyphenated_mglennp_code, packed_u64) matching the
    exact ASCII byte layout used by radial_synapse_phonebook.py and switchboard_api.py.
    """
    raw7 = f"{merit}{guarantee}{latency}{economy}{node_honesty}{neighbor_proto}{preference}".upper()
    code_hyphen = f"{raw7[:4]}-{raw7[4:]}"
    header_byte = ((version & 0x0F) << 4) | (hop_ttl & 0x0F)
    val = header_byte
    for ch in raw7[:7]:
        val = (val << 8) | (ord(ch) & 0xFF)
    return raw7, code_hyphen, val


def _parse_json_or_sse_payload(raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            return json.loads(text)
        except Exception:
            pass
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str.startswith("{"):
                try:
                    return json.loads(data_str)
                except Exception:
                    continue
    return None


def interrogate_agent_endpoint(
    agent_row: Dict[str, Any],
    timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC,
) -> Dict[str, Any]:
    agent_id = str(agent_row.get("agent_id") or agent_row.get("id") or "")
    name = str(agent_row.get("name") or agent_id)
    description = str(agent_row.get("description") or name)
    endpoint = str(agent_row.get("endpoint") or "").strip()
    prev_hash = str(agent_row.get("tool_schema_hash_16") or "")
    existing_code = str(agent_row.get("mglennp_code") or "CAAB-ZES").upper().replace("-", "")
    prev_merit = existing_code[0:1] if existing_code else "C"
    prev_weight = float(agent_row.get("synaptic_weight") or 0.80)
    prev_mask = int(agent_row.get("radial_bitmask") or 0)

    if agent_id in PROTECTED_CANARIES:
        code_str = str(agent_row.get("mglennp_code") or "AAAZ-ZES")
        u64_val = int(agent_row.get("mglennp_u64") or 0)
        return dict(
            agent_row,
            mgle_nnp_stamp=code_str.replace("-", ""),
            mglennp_code=code_str,
            mglennp_u64=u64_val,
            mglennp_u64_hex=f"0x{u64_val:016X}",
            guarantee_grade=code_str[1:2],
            node_honesty="Z",
            schema_drift_detected=False,
            audit_status="PROTECTED_CANARY",
        )

    lower_ep = endpoint.lower()
    is_unhosted_repo = (
        not endpoint
        or not (lower_ep.startswith("http://") or lower_ep.startswith("https://"))
        or "github.com/" in lower_ep
        or "gitlab.com/" in lower_ep
        or "npmjs.com/" in lower_ep
        or "pypi.org/" in lower_ep
        or lower_ep.rstrip("/") == "https://registry.modelcontextprotocol.io"
    )

    if is_unhosted_repo:
        domain_mask = prev_mask if prev_mask > 0 else compute_domain_mask(f"{name} {description}", [])
        stamp_str, code_hyphen, packed_64 = pack_mgle_nnp_64bit("C", "D", "E", "A", "Z", "E", "D", hop_ttl=0)
        return {
            "agent_id": agent_id,
            "name": name,
            "endpoint": endpoint,
            "mglennp_code": code_hyphen,
            "mglennp_u64": packed_64,
            "mglennp_u64_hex": f"0x{packed_64:016X}",
            "radial_bitmask": domain_mask,
            "domain_mask": domain_mask,
            "mgle_nnp_stamp": stamp_str,
            "merit_grade": "C",
            "guarantee_grade": "D",
            "latency_grade": "E",
            "node_honesty": "Z",
            "avg_latency_ms": int(agent_row.get("avg_latency_ms") or 999),
            "synaptic_weight": round(min(prev_weight, 0.50), 4),
            "wired_tool_count": 0,
            "tool_schema_hash_16": "0000000000000000",
            "schema_drift_detected": False,
            "audit_status": "UNHOSTED_REPO_GRADE_D",
        }

    ssl_ctx = ssl.create_default_context()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "MglennP-RadialSwitchboard-Auditor/2.0 (+https://radialswitchboard.com)",
    }

    init_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "MglennP-Radial-Auditor", "version": "2.0.0"},
        },
    }).encode("utf-8")

    t0 = time.perf_counter()
    http_alive = False
    rpc_initialized = False
    session_id: Optional[str] = None
    latency_ms: Optional[float] = None

    try:
        req_init = urllib.request.Request(endpoint, data=init_payload, headers=headers, method="POST")
        with urllib.request.urlopen(req_init, timeout=timeout_sec, context=ssl_ctx) as resp:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            http_alive = 200 <= resp.status < 500
            session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
            raw_init = resp.read(65536)
            parsed_init = _parse_json_or_sse_payload(raw_init)
            if isinstance(parsed_init, dict) and ("result" in parsed_init or "jsonrpc" in parsed_init):
                rpc_initialized = True
    except urllib.error.HTTPError as e:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if e.code in (400, 401, 403, 405, 406, 422):
            http_alive = True
    except Exception:
        http_alive = False

    if not http_alive:
        t1 = time.perf_counter()
        try:
            req_get = urllib.request.Request(
                endpoint,
                headers={"User-Agent": headers["User-Agent"], "Accept": "*/*"},
                method="GET",
            )
            with urllib.request.urlopen(req_get, timeout=timeout_sec, context=ssl_ctx) as resp_get:
                latency_ms = round((time.perf_counter() - t1) * 1000.0, 2)
                if 200 <= resp_get.status < 500:
                    http_alive = True
        except urllib.error.HTTPError as e_get:
            latency_ms = round((time.perf_counter() - t1) * 1000.0, 2)
            if e_get.code in (400, 401, 403, 405, 406, 422):
                http_alive = True
        except Exception:
            http_alive = False

    wired_tools: List[Dict[str, Any]] = []
    if http_alive and rpc_initialized:
        tools_headers = dict(headers)
        if session_id:
            tools_headers["Mcp-Session-Id"] = session_id
        tools_payload = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode("utf-8")
        try:
            req_tools = urllib.request.Request(endpoint, data=tools_payload, headers=tools_headers, method="POST")
            with urllib.request.urlopen(req_tools, timeout=timeout_sec, context=ssl_ctx) as resp_tools:
                raw_tools = resp_tools.read(131072)
                parsed_tools = _parse_json_or_sse_payload(raw_tools)
                if isinstance(parsed_tools, dict):
                    res_obj = parsed_tools.get("result")
                    if isinstance(res_obj, dict) and isinstance(res_obj.get("tools"), list):
                        wired_tools = res_obj["tools"]
        except Exception:
            pass

    latency_grade = compute_latency_grade(latency_ms, http_alive)
    tool_hash_16 = compute_tool_schema_hash_16(wired_tools)
    schema_drift = bool(
        prev_hash
        and prev_hash != "0000000000000000"
        and tool_hash_16 != "0000000000000000"
        and prev_hash != tool_hash_16
    )

    if not http_alive:
        guarantee_grade = "E"
        merit_grade = "D" if prev_merit in ("A", "B", "C") else prev_merit
        new_weight = round(max(0.15, prev_weight - 0.15), 4)
        node_honesty = "Z"
        int_latency = 9999
        audit_status = "QUARANTINED_DEAD_GRADE_E"
    else:
        int_latency = max(1, min(9999, int(round(latency_ms or 200))))
        if wired_tools:
            guarantee_grade = "A"
            merit_grade = "A" if prev_weight >= 0.90 else "B"
            new_weight = round(min(0.99, prev_weight + 0.03), 4)
            audit_status = "VERIFIED_JSONRPC_TOOLS_GRADE_A"
        else:
            guarantee_grade = "B"
            merit_grade = prev_merit if prev_merit in ("A", "B") else "B"
            new_weight = round(min(0.95, max(0.78, prev_weight)), 4)
            audit_status = "VERIFIED_HTTP_LIVE_GRADE_B"

        node_honesty = "W" if (latency_ms is not None and latency_ms > 1500.0) else "Z"

    preference_class = "S" if latency_grade in ("A", "B") else "D"
    computed_mask = compute_domain_mask(f"{name} {description}", wired_tools)
    domain_mask = (prev_mask | computed_mask) if prev_mask > 0 else computed_mask
    hop_ttl = 0 if node_honesty == "Z" else 1
    stamp_str, code_hyphen, packed_64 = pack_mgle_nnp_64bit(
        merit_grade, guarantee_grade, latency_grade, "A", node_honesty, "E", preference_class, hop_ttl=hop_ttl
    )

    return {
        "agent_id": agent_id,
        "name": name,
        "endpoint": endpoint,
        "mglennp_code": code_hyphen,
        "mglennp_u64": packed_64,
        "mglennp_u64_hex": f"0x{packed_64:016X}",
        "radial_bitmask": domain_mask,
        "domain_mask": domain_mask,
        "mgle_nnp_stamp": stamp_str,
        "merit_grade": merit_grade,
        "guarantee_grade": guarantee_grade,
        "latency_grade": latency_grade,
        "node_honesty": node_honesty,
        "avg_latency_ms": int_latency,
        "synaptic_weight": new_weight,
        "wired_tool_count": len(wired_tools),
        "tool_schema_hash_16": tool_hash_16,
        "schema_drift_detected": schema_drift,
        "audit_status": audit_status,
    }


def fetch_all_supabase_agents(supabase_url: str, supabase_key: str) -> List[Dict[str, Any]]:
    base = supabase_url.rstrip("/")
    if not base.endswith("/rest/v1"):
        base = f"{base}/rest/v1"

    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{base}/radial_agent_phonebook?select=*&order=agent_id.asc&limit={SUPABASE_FETCH_PAGE_SIZE}&offset={offset}"
        req = urllib.request.Request(
            url,
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}", "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
            if not isinstance(batch, list) or not batch:
                break
            all_rows.extend(batch)
            if len(batch) < SUPABASE_FETCH_PAGE_SIZE:
                break
            offset += SUPABASE_FETCH_PAGE_SIZE
    return all_rows


def has_row_changed(existing: Optional[Dict[str, Any]], audited: Dict[str, Any]) -> bool:
    if existing is None:
        return True
    if str(audited.get("agent_id")) in PROTECTED_CANARIES:
        return False
    for k in ("mglennp_code", "radial_bitmask", "mgle_nnp_stamp", "tool_schema_hash_16"):
        if k in existing and existing.get(k) != audited.get(k):
            return True
    old_lat = existing.get("avg_latency_ms")
    new_lat = audited.get("avg_latency_ms")
    if isinstance(old_lat, (int, float)) and isinstance(new_lat, (int, float)):
        if abs(float(old_lat) - float(new_lat)) >= 50.0:
            return True
    return False


def bulk_upsert_deltas_to_supabase(
    supabase_url: str,
    supabase_key: str,
    delta_rows: List[Dict[str, Any]],
    existing_columns: Optional[set] = None,
) -> int:
    if not delta_rows:
        return 0
    base = supabase_url.rstrip("/")
    if not base.endswith("/rest/v1"):
        base = f"{base}/rest/v1"
    url = f"{base}/radial_agent_phonebook?on_conflict=agent_id"

    total_upserted = 0
    for i in range(0, len(delta_rows), SUPABASE_UPSERT_BATCH_SIZE):
        chunk = delta_rows[i : i + SUPABASE_UPSERT_BATCH_SIZE]
        if existing_columns:
            clean_chunk = [{k: v for k, v in row.items() if k in existing_columns or k == "agent_id"} for row in chunk]
        else:
            clean_chunk = chunk
        payload = json.dumps(clean_chunk).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201, 204):
                total_upserted += len(clean_chunk)
    return total_upserted


def run_parallel_audit(
    agents: List[Dict[str, Any]],
    max_workers: int = DEFAULT_WORKERS,
    timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], float]:
    t_start = time.perf_counter()
    results: List[Dict[str, Any]] = []
    summary: Dict[str, int] = {
        "total_audited": 0,
        "grade_A_live_rpc": 0,
        "grade_B_live_http": 0,
        "grade_D_unhosted_repo": 0,
        "grade_E_quarantined_dead": 0,
        "wrappers_flagged_W": 0,
        "schema_drifts_detected": 0,
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(interrogate_agent_endpoint, row, timeout_sec): row for row in agents}
        for fut in concurrent.futures.as_completed(future_map):
            res = fut.result()
            results.append(res)
            summary["total_audited"] += 1
            g = res.get("guarantee_grade")
            if g == "A":
                summary["grade_A_live_rpc"] += 1
            elif g == "B":
                summary["grade_B_live_http"] += 1
            elif g == "D":
                summary["grade_D_unhosted_repo"] += 1
            elif g == "E":
                summary["grade_E_quarantined_dead"] += 1
            if res.get("node_honesty") == "W":
                summary["wrappers_flagged_W"] += 1
            if res.get("schema_drift_detected"):
                summary["schema_drifts_detected"] += 1
    elapsed_sec = round(time.perf_counter() - t_start, 3)
    return results, summary, elapsed_sec


def run_deterministic_self_test() -> int:
    print("=" * 72)
    print("  MGLENNP RADIAL SWITCHBOARD — TRACK ALPHA SELF-TEST (SPEC REV 2.0)")
    print("=" * 72)
    mock_tools_v1 = [
        {
            "name": "estimate_timber_deck",
            "description": "Calculates Virginia deck construction pricing",
            "inputSchema": {
                "type": "object",
                "properties": {"width_ft": {"type": "number"}, "zip_code": {"type": "string"}},
                "required": ["width_ft", "zip_code"],
            },
        }
    ]
    mock_tools_v2 = [
        {
            "name": "estimate_timber_deck",
            "description": "Calculates Virginia deck construction pricing",
            "inputSchema": {
                "type": "object",
                "properties": {"width_ft": {"type": "number"}, "wallet": {"type": "string"}},
                "required": ["width_ft", "wallet"],
            },
        }
    ]
    h1 = compute_tool_schema_hash_16(mock_tools_v1)
    h2 = compute_tool_schema_hash_16(mock_tools_v2)
    assert len(h1) == 16 and h1 != h2, "16-char tool schema hash must detect property drift"

    mask = compute_domain_mask("Homestead Deck Estimator", mock_tools_v1)
    stamp, code_hyphen, u64 = pack_mgle_nnp_64bit("A", "A", "A", "A", "Z", "E", "S", hop_ttl=0)
    assert code_hyphen == "AAAA-ZES", f"Expected hyphenated code AAAA-ZES, got {code_hyphen}"
    assert u64 > 0, "Packed 64-bit integer must be positive"

    base_row = {"agent_id": "mcp://test", "mglennp_code": code_hyphen, "radial_bitmask": mask, "tool_schema_hash_16": h1, "avg_latency_ms": 95}
    same_row = dict(base_row, avg_latency_ms=105)
    drift_row = dict(base_row, tool_schema_hash_16=h2)
    assert not has_row_changed(base_row, same_row), "Unchanged row must be skipped"
    assert has_row_changed(base_row, drift_row), "Drifted row must trigger delta upsert"

    print(f"  [OK] 16-Char Tool Schema Hash v1 : {h1}")
    print(f"  [OK] 16-Char Tool Schema Hash v2 : {h2} (Drift Caught!)")
    print(f"  [OK] Hyphenated MGLE-NNP Stamp   : {code_hyphen} (u64: 0x{u64:016X} | Mask: {mask})")
    print("  [OK] Delta-Only Upsert Filter    : Verified (0 redundant writes)")
    print("=" * 72)
    return 0


def main() -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description="MglennP Radial Switchboard — Track Alpha 100-Worker Auditor")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic offline self-test")
    parser.add_argument("--dry-run", action="store_true", help="Audit live endpoints without writing to Supabase")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Worker thread count (default: 100)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_HTTP_TIMEOUT_SEC, help="Per-endpoint timeout in seconds")
    parser.add_argument("--limit", type=int, default=0, help="Cap on number of agents to audit (0 = all)")
    args = parser.parse_args()

    if args.self_test:
        return run_deterministic_self_test()

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    )
    if not supabase_url or not supabase_key:
        return run_deterministic_self_test()

    print("=" * 72)
    print("  MGLENNP RADIAL SWITCHBOARD — 100-WORKER MECHANICAL AUDITOR (REV 2.0)")
    print("=" * 72)
    existing_rows = fetch_all_supabase_agents(supabase_url, supabase_key)
    print(f"[1/4] Loaded {len(existing_rows)} indexed agents from radial_agent_phonebook.")
    existing_map = {str(r.get("agent_id")): r for r in existing_rows}
    existing_columns = set(existing_rows[0].keys()) if existing_rows else None

    target_rows = existing_rows[: args.limit] if args.limit > 0 else existing_rows
    print(f"[2/4] Auditing {len(target_rows)} endpoints across {args.workers} parallel workers...")
    audited_rows, summary, elapsed_sec = run_parallel_audit(target_rows, max_workers=args.workers, timeout_sec=args.timeout)
    print(f"  [OK] Audited {summary['total_audited']} agents in {elapsed_sec}s:")
    print(f"       Grade A (RPC Tools): {summary['grade_A_live_rpc']} | Grade B (HTTP Live): {summary['grade_B_live_http']} | Grade D (Repo): {summary['grade_D_unhosted_repo']} | Grade E (Dead): {summary['grade_E_quarantined_dead']}")

    delta_rows = [row for row in audited_rows if has_row_changed(existing_map.get(str(row.get("agent_id"))), row)]
    print(f"[3/4] Delta Filter: {len(delta_rows)} changed | {len(audited_rows) - len(delta_rows)} unchanged skipped.")

    if args.dry_run or not delta_rows:
        print("[4/4] Dry-run enabled or 0 deltas to push. Complete.")
        return 0

    upserted = bulk_upsert_deltas_to_supabase(supabase_url, supabase_key, delta_rows, existing_columns)
    print(f"[4/4] Bulk upserted {upserted} changed agent scorecards to Supabase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
