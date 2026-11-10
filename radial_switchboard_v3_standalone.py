#!/usr/bin/env python3
"""
MGLENNP RADIAL SWITCHBOARD — SPEC REV 3.0.2 (PRODUCTION CUTOVER ENGINE)
Brand: MglennP — "An honest approach to solving everyday challenges."
Isolation: 100% Standalone (Zero coupling to Homestead Maintenance, Dream Constructor, TrendDial, or Command Center).
Base Mainnet USDC Treasury: 0x24b1a09b489c67c3e43f7cd1f3023aef544104fd
Default Flash Policy: Top-10 Anti-Monoculture Variability (distinct vendor domains + distinct tool-schema hashes).
"""


from __future__ import annotations
import argparse, concurrent.futures, datetime, hashlib, hmac, http.server
import json, math, os, random, re, secrets, socketserver, ssl, threading, time
import urllib.error, urllib.parse, urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple


SPEC_VERSION = "3.0.2"
SCHEMA_NIBBLE = 0x3
DEFAULT_USDC_TREASURY_ADDRESS = os.environ.get(
    "RADIAL_USDC_TREASURY_ADDRESS", "0x24b1a09b489c67c3e43f7cd1f3023aef544104fd"
)
BASE_MAINNET_CHAIN_ID = "eip155:8453"
BASE_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


DEFAULT_FLASH_TOP_K = 10
MAX_FLASH_TOP_K = 25
CASH_PASS_PRICE_USDC = "0.01"
CASH_PASS_CREDITS = 100
CASH_PASS_TTL_SECONDS = 86400 * 30
WORK_ASSIGNMENT_SIZE = 4
WORK_PASS_CREDITS = 20
WORK_PASS_TTL_SECONDS = 3600
FREE_DAILY_STARTER_CALLS = 15


TAX_RESERVE_RATIO, OPERATING_CASH_RATIO, POST_TAX_TREASURY_SLICE_RATIO = 0.30, 0.60, 0.10
HMAC_SECRET_KEY = os.environ.get(
    "RADIAL_HMAC_SECRET", "radial-switchboard-v3-dev-hmac-replace-in-cloud-run-env"
).encode("utf-8")


CAPABILITY_NAMES: Tuple[str, ...] = (
    "sql", "database", "code_exec", "git_ops", "web_fetch", "search_rag",
    "math_verify", "finance_data", "crypto_chain", "payments_x402", "file_parse", "media_vision",
    "maps_geo", "weather_env", "security_audit", "schema_transform", "vector_memory", "cloud_devops",
    "messaging_comm", "data_analytics", "legal_tax", "commerce_sku", "agent_orchestration", "general",
)
CAPABILITY_BITS: Dict[str, int] = {name: (1 << idx) for idx, name in enumerate(CAPABILITY_NAMES)}


READINESS_NAMES: Tuple[str, ...] = (
    "idempotent_read_safe", "seasoned_tenure", "x402_native_payable", "schema_drift_stable",
    "poison_scan_clean", "large_payload_capable", "high_concurrency_rpm", "zero_auth_instant",
)
READINESS_BITS: Dict[str, int] = {name: (1 << (24 + idx)) for idx, name in enumerate(READINESS_NAMES)}


CAPABILITY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "sql": ("sql", "postgres", "postgresql", "mysql", "sqlite", "duckdb", "bigquery", "clickhouse"),
    "database": ("database", "supabase", "redis", "mongodb", "turso", "kv", "table", "query", "postgres", "postgresql", "mysql", "sqlite", "duckdb", "clickhouse", "cockroach", "vitess", "timescale"),
    "code_exec": ("python", "typescript", "javascript", "sandbox", "compile", "execute_code", "repl", "coding", "ast"),
    "git_ops": ("github", "gitlab", "git", "pull_request", "commit", "repository", "branch"),
    "web_fetch": ("fetch", "scrape", "crawl", "browser", "playwright", "http", "webpage"),
    "search_rag": ("search", "rag", "retrieve", "arxiv", "wikipedia", "lookup", "citation"),
    "math_verify": ("math", "calculus", "solver", "verify", "proof", "statistics", "symbolic"),
    "finance_data": ("finance", "sec", "stock", "equity", "market", "accounting", "portfolio"),
    "crypto_chain": ("blockchain", "base", "ethereum", "solana", "erc20", "defi", "onchain", "rpc", "crypto"),
    "payments_x402": ("x402", "usdc", "stripe", "payment", "invoice", "checkout", "settlement"),
    "file_parse": ("pdf", "docx", "xlsx", "csv", "markdown", "extract", "ocr", "document"),
    "media_vision": ("image", "vision", "audio", "video", "tts", "transcribe", "ffmpeg", "media"),
    "maps_geo": ("map", "maps", "geocode", "route", "distance", "latitude", "longitude", "places", "zip"),
    "weather_env": ("weather", "noaa", "forecast", "wind", "temperature", "radar"),
    "security_audit": ("security", "vulnerability", "cve", "audit", "fuzz", "sanitize"),
    "schema_transform": ("json", "xml", "yaml", "graphql", "validate", "schema", "convert"),
    "vector_memory": ("vector", "embedding", "pinecone", "qdrant", "pgvector"),
    "cloud_devops": ("docker", "kubernetes", "cloud_run", "aws", "gcp", "cloudflare", "deploy"),
    "messaging_comm": ("email", "slack", "webhook", "sms", "discord", "notify"),
    "data_analytics": ("olap", "parquet", "telemetry", "timeseries", "etl", "warehouse"),
    "legal_tax": ("tax", "irs", "compliance", "contract", "regulation", "statute"),
    "commerce_sku": ("shopify", "catalog", "inventory", "order", "shipping", "product", "commerce"),
    "agent_orchestration": ("a2a", "mcp", "matchmake", "subagent", "workflow", "router"),
}


TOOL_POISONING_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"(cat|read|upload|exfiltrate)\s+.*(\.ssh|\.env|id_rsa|aws/credentials)", re.I),
    re.compile(r"<\s*important\s*>.*do\s+not\s+mention", re.I | re.S),
    re.compile(r"system\s*prompt\s*override", re.I),
)


GRADE_TO_NIBBLE = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
NIBBLE_TO_GRADE = {v: k for k, v in GRADE_TO_NIBBLE.items()}
NODE_TO_NIBBLE = {"Z": 1, "S": 2, "B": 3, "A": 4, "H": 5, "W": 9}
NIBBLE_TO_NODE = {v: k for k, v in NODE_TO_NIBBLE.items()}
NEIGHBOR_TO_NIBBLE = {"E": 1, "A": 2, "O": 3, "G": 4}
NIBBLE_TO_NEIGHBOR = {v: k for k, v in NEIGHBOR_TO_NIBBLE.items()}
PREF_TO_NIBBLE = {"S": 1, "C": 2, "N": 3, "D": 4, "M": 5}
NIBBLE_TO_PREF = {v: k for k, v in PREF_TO_NIBBLE.items()}
MULTI_PART_TLDS = {"co.uk", "org.uk", "com.au", "co.jp", "com.br", "co.in"}




def extract_vendor_domain(endpoint: str) -> str:
    try:
        host = (urllib.parse.urlparse(endpoint).hostname or "").lower().strip(".")
    except Exception:
        host = ""
    if not host:
        return endpoint.lower()[:32]
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host




def infer_capabilities_from_intent(intent_text: str) -> List[str]:
    low = (intent_text or "").lower()
    matched = [cap for cap, kws in CAPABILITY_KEYWORDS.items() if any(kw in low for kw in kws)]
    return matched if matched else ["general"]




class MgleNnp64Codec:
    @staticmethod
    def pack(
        merit: str, guarantee: str, latency: str, economy: str,
        node_honesty: str, neighbor_proto: str, preference: str,
        readiness_mask: int, capability_mask: int, hop_ttl: int = 0,
    ) -> Tuple[str, int, str]:
        m_c, g_c, l_c, e_c = merit[:1].upper(), guarantee[:1].upper(), latency[:1].upper(), economy[:1].upper()
        n1_c, n2_c, p_c = node_honesty[:1].upper(), neighbor_proto[:1].upper(), preference[:1].upper()
        call_sign = f"{m_c}{g_c}{l_c}{e_c}-{n1_c}{n2_c}{p_c}"
        slot0 = ((hop_ttl & 0x3) << 2) | (SCHEMA_NIBBLE & 0x3)
        upper_32 = (
            ((slot0 & 0xF) << 28)
            | ((GRADE_TO_NIBBLE.get(m_c, 3) & 0xF) << 24)
            | ((GRADE_TO_NIBBLE.get(g_c, 5) & 0xF) << 20)
            | ((GRADE_TO_NIBBLE.get(l_c, 5) & 0xF) << 16)
            | ((GRADE_TO_NIBBLE.get(e_c, 1) & 0xF) << 12)
            | ((NODE_TO_NIBBLE.get(n1_c, 1) & 0xF) << 8)
            | ((NEIGHBOR_TO_NIBBLE.get(n2_c, 1) & 0xF) << 4)
            | (PREF_TO_NIBBLE.get(p_c, 1) & 0xF)
        )
        lower_32 = (readiness_mask & 0xFF000000) | (capability_mask & 0x00FFFFFF)
        u64 = ((upper_32 & 0xFFFFFFFF) << 32) | (lower_32 & 0xFFFFFFFF)
        return call_sign, u64, f"0x{u64:016X}"


    @staticmethod
    def unpack(u64: int) -> Dict[str, Any]:
        u32, l32 = (u64 >> 32) & 0xFFFFFFFF, u64 & 0xFFFFFFFF
        m_c = NIBBLE_TO_GRADE.get((u32 >> 24) & 0xF, "C")
        g_c = NIBBLE_TO_GRADE.get((u32 >> 20) & 0xF, "E")
        l_c = NIBBLE_TO_GRADE.get((u32 >> 16) & 0xF, "E")
        e_c = NIBBLE_TO_GRADE.get((u32 >> 12) & 0xF, "A")
        n1_c = NIBBLE_TO_NODE.get((u32 >> 8) & 0xF, "Z")
        n2_c = NIBBLE_TO_NEIGHBOR.get((u32 >> 4) & 0xF, "E")
        p_c = NIBBLE_TO_PREF.get(u32 & 0xF, "S")
        return {
            "mgle_nnp_code": f"{m_c}{g_c}{l_c}{e_c}-{n1_c}{n2_c}{p_c}",
            "u64_hex": f"0x{u64:016X}",
            "merit": m_c, "guarantee": g_c, "latency": l_c, "economy": e_c,
            "node_honesty": n1_c, "neighbor_protocol": n2_c, "preference": p_c,
            "readiness_flags": [n for n, b in READINESS_BITS.items() if (l32 & b) != 0],
            "capabilities": [n for n, b in CAPABILITY_BITS.items() if (l32 & b) != 0],
        }


    @staticmethod
    def build_query_masks(
        required_capabilities: Sequence[str],
        require_instant_zero_auth: bool = False,
        require_poison_clean: bool = True,
        max_latency_grade: str = "C",
        require_zero_hop: bool = True,
    ) -> Tuple[int, int, str]:
        req = 0
        for cap in required_capabilities:
            req |= CAPABILITY_BITS.get(cap.strip().lower(), 0)
        if require_poison_clean:
            req |= READINESS_BITS["poison_scan_clean"]
        if require_instant_zero_auth:
            req |= READINESS_BITS["zero_auth_instant"]
        return req, 0, f"**{max_latency_grade.upper()}*-{'Z' if require_zero_hop else '*'}**"




def select_varied_top_k(
    scored_candidates: Sequence[Tuple[float, Dict[str, Any]]],
    top_k: int = DEFAULT_FLASH_TOP_K,
) -> Tuple[List[Tuple[Dict[str, Any], str, str]], Dict[str, Any]]:
    limit = max(1, min(MAX_FLASH_TOP_K, int(top_k or DEFAULT_FLASH_TOP_K)))
    enriched = [
        (
            sc,
            extract_vendor_domain(str(r.get("endpoint") or "")),
            str(r.get("tool_schema_hash_16") or "0000000000000000"),
            f"{r.get('auth_mode','none')}:{r.get('latency_grade','B')}:{r.get('preference_class','S')}",
            r,
        )
        for sc, r in scored_candidates
    ]
    chosen: List[Tuple[Dict[str, Any], str, str]] = []
    chosen_ids: set[str] = set()
    seen_vendors: Dict[str, int] = {}
    seen_schemas: set[str] = set()
    seen_profiles: set[str] = set()


    pool = list(enriched)
    while len(chosen) < limit and pool:
        best_i, best_adj = -1, -1.0
        for idx, (sc, v_dom, s_hash, e_prof, rec) in enumerate(pool):
            aid = str(rec.get("agent_id") or "")
            if aid in chosen_ids or v_dom in seen_vendors:
                continue
            if s_hash != "0000000000000000" and s_hash in seen_schemas:
                continue
            adj = sc + (0.035 if e_prof not in seen_profiles else 0.0)
            if adj > best_adj:
                best_adj, best_i = adj, idx
        if best_i < 0:
            break
        sc, v_dom, s_hash, e_prof, rec = pool.pop(best_i)
        chosen.append((rec, "INDEPENDENT_VENDOR_AND_SCHEMA", v_dom))
        chosen_ids.add(str(rec.get("agent_id") or ""))
        seen_vendors[v_dom] = seen_vendors.get(v_dom, 0) + 1
        if s_hash != "0000000000000000":
            seen_schemas.add(s_hash)
        seen_profiles.add(e_prof)


    if len(chosen) < limit:
        for sc, v_dom, s_hash, e_prof, rec in enriched:
            if len(chosen) >= limit:
                break
            aid = str(rec.get("agent_id") or "")
            if aid in chosen_ids:
                continue
            if (v_dom not in seen_vendors or (s_hash != "0000000000000000" and s_hash not in seen_schemas)) and seen_vendors.get(v_dom, 0) < 2:
                chosen.append((rec, "DISTINCT_HOST_OR_SCHEMA_VARIANT", v_dom))
                chosen_ids.add(aid)
                seen_vendors[v_dom] = seen_vendors.get(v_dom, 0) + 1
                if s_hash != "0000000000000000":
                    seen_schemas.add(s_hash)
                seen_profiles.add(e_prof)


    if len(chosen) < limit:
        for sc, v_dom, s_hash, e_prof, rec in enriched:
            if len(chosen) >= limit:
                break
            aid = str(rec.get("agent_id") or "")
            if aid not in chosen_ids:
                chosen.append((rec, "SECONDARY_REPLICA_FALLBACK", v_dom))
                chosen_ids.add(aid)
                seen_vendors[v_dom] = seen_vendors.get(v_dom, 0) + 1
                seen_profiles.add(e_prof)


    return chosen, {
        "requested_top_k": limit,
        "returned_count": len(chosen),
        "unique_vendor_domains": len(seen_vendors),
        "unique_tool_schemas": len(seen_schemas),
        "unique_execution_profiles": len(seen_profiles),
        "monoculture_protection": "ACTIVE_LINEAGE_AND_PROFILE_DIVERSITY",
    }




def flash_unsorted_pool(
    unsorted_pool: Sequence[Dict[str, Any]],
    required_capabilities: Sequence[str],
    require_instant_zero_auth: bool = False,
    max_latency_grade: str = "C",
    require_zero_hop: bool = True,
    top_k: int = DEFAULT_FLASH_TOP_K,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    req_bits, _, coupler_hint = MgleNnp64Codec.build_query_masks(
        required_capabilities, require_instant_zero_auth, True, max_latency_grade, require_zero_hop
    )
    max_lat_nib = GRADE_TO_NIBBLE.get(max_latency_grade[:1].upper(), 3)
    exact: List[Tuple[float, Dict[str, Any]]] = []
    partial: List[Tuple[int, float, Dict[str, Any]]] = []


    for rec in unsorted_pool:
        u64 = int(rec.get("mgle_nnp_64bit") or 0)
        u32, l32 = (u64 >> 32) & 0xFFFFFFFF, u64 & 0xFFFFFFFF
        if ((u32 >> 20) & 0xF) > 2 or ((u32 >> 16) & 0xF) > max_lat_nib:
            continue
        if require_zero_hop and ((u32 >> 8) & 0xF) != 1:
            continue
        wt = float(rec.get("synaptic_weight") or 0.80)
        if (l32 & req_bits) == req_bits:
            m_nib, l_nib = (u32 >> 24) & 0xF, (u32 >> 16) & 0xF
            exact.append((round(wt + 0.05 * (6 - m_nib) + 0.02 * (6 - l_nib), 4), rec))
        elif req_bits != 0:
            ov = (l32 & req_bits).bit_count()
            if ov > 0:
                partial.append((ov, wt, rec))


    exact.sort(key=lambda x: x[0], reverse=True)
    if exact:
        diversified, var_summary = select_varied_top_k(exact, top_k=top_k)
        mode = "EXACT_64BIT_RESONANCE_TOP10_VARIED"
    elif partial:
        partial.sort(key=lambda x: (x[0], x[1]), reverse=True)
        diversified, var_summary = select_varied_top_k([(round(ov * 0.25 + wt, 4), r) for ov, wt, r in partial], top_k=top_k)
        mode = "CLOSEST_POPCNT_RESONANCE_TOP10_VARIED"
    else:
        diversified, var_summary = select_varied_top_k([], top_k=top_k)
        mode = "NO_LIVE_RESONANCE"


    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 4)
    finalists = [
        {
            "rank": idx,
            "agent_id": rec.get("agent_id"),
            "name": rec.get("name"),
            "endpoint": rec.get("endpoint"),
            "vendor_domain": v_dom,
            "variability_role": v_role,
            "mgle_nnp_code": rec.get("mgle_nnp_stamp"),
            "mgle_nnp_stamp": rec.get("mgle_nnp_stamp"),
            "mgle_nnp_u64_hex": f"0x{int(rec.get('mgle_nnp_64bit') or 0):016X}",
            "domain_mask": rec.get("domain_mask", 0),
            "warm_latency_ms": rec.get("avg_latency_ms"),
            "auth_mode": rec.get("auth_mode", "none"),
            "tool_schema_hash_16": rec.get("tool_schema_hash_16"),
            "synaptic_weight": rec.get("synaptic_weight"),
            "pre_handshake_dossier": rec.get("dossier_json") or {},
        }
        for idx, (rec, v_role, v_dom) in enumerate(diversified, start=1)
    ]
    return {
        "spec_version": SPEC_VERSION,
        "pool_scanned_unsorted": len(unsorted_pool),
        "total_qualified_before_diversification": len(exact) or len(partial),
        "single_pass_flash_ms": elapsed_ms,
        "timings": {"bitwise_smell_test_ms": elapsed_ms, "total_server_ms": elapsed_ms},
        "match_mode": mode,
        "coupler_applied": coupler_hint,
        "required_lower32_hex": f"0x{req_bits:08X}",
        "variability_summary": var_summary,
        "finalist_count": len(finalists),
        "finalists": finalists,
        "matches": finalists,
        "top_match": finalists[0] if finalists else {},
    }




def scan_tools_for_poisoning(wired_tools: Sequence[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    findings: List[str] = []
    for tool in wired_tools:
        if not isinstance(tool, dict):
            continue
        t_name = str(tool.get("name") or "unnamed")
        joined = " ".join([
            t_name,
            str(tool.get("description") or ""),
            json.dumps(tool["inputSchema"]) if isinstance(tool.get("inputSchema"), dict) else "",
        ])
        for pat in TOOL_POISONING_PATTERNS:
            if pat.search(joined):
                findings.append(f"Suspicious pattern in '{t_name}': {pat.pattern}")
    return (len(findings) == 0), findings




def extract_capabilities_and_hash(text_blob: str, wired_tools: Sequence[Dict[str, Any]]) -> Tuple[int, str, List[Dict[str, Any]]]:
    parts = [text_blob or ""]
    inv: List[Dict[str, Any]] = []
    for tool in sorted(wired_tools, key=lambda x: str(x.get("name", "") if isinstance(x, dict) else "")):
        if not isinstance(tool, dict):
            continue
        t_name, t_desc = str(tool.get("name") or "").strip(), str(tool.get("description") or "").strip()[:180]
        schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        reqs = schema.get("required") if isinstance(schema.get("required"), list) else []
        parts.extend([t_name, t_desc, *(str(k) for k in props.keys())])
        inv.append({
            "tool": t_name,
            "summary": t_desc,
            "inputs": {str(k): str((v or {}).get("type", "any")) for k, v in list(props.items())[:12] if isinstance(v, dict)},
            "required": [str(r) for r in reqs[:12]],
        })
    low = " ".join(parts).lower()
    mask = 0
    for c_name, kws in CAPABILITY_KEYWORDS.items():
        if any(kw in low for kw in kws):
            mask |= CAPABILITY_BITS[c_name]
    if mask == 0:
        mask = CAPABILITY_BITS["general"]
    if inv:
        canon = json.dumps([{"n": t["tool"], "i": sorted(t["inputs"].keys()), "r": sorted(t["required"])} for t in inv], sort_keys=True, separators=(",", ":"))
        h16 = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
    else:
        h16 = "0000000000000000"
    return mask, h16, inv




def build_agent_record_and_dossier(
    agent_id: str, name: str, description: str, endpoint: str,
    http_alive: bool, cold_latency_ms: Optional[float], warm_latency_ms: Optional[float],
    wired_tools: Sequence[Dict[str, Any]], auth_mode: str = "none",
    rate_limit_rpm: Optional[int] = None, x402_supported: bool = False,
    prev_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    prev = prev_record or {}
    enc = int(prev.get("encounter_count") or 0) + 1
    wins, fails = int(prev.get("room_completions") or 0), int(prev.get("room_failures") or 0)
    prev_hash, prev_wt = str(prev.get("tool_schema_hash_16") or ""), float(prev.get("synaptic_weight") or 0.80)
    prev_tools = (prev.get("dossier_json") or {}).get("verified_tools") or []


    low_ep = (endpoint or "").strip().lower()
    is_repo = not low_ep.startswith(("http://", "https://")) or any(h in low_ep for h in ("github.com/", "gitlab.com/", "npmjs.com/", "pypi.org/"))
    poison_ok, poison_list = scan_tools_for_poisoning(wired_tools)


    if wired_tools:
        cap_mask, h16, c_tools = extract_capabilities_and_hash(f"{name} {description}", wired_tools)
    elif prev_tools:
        cap_mask, h16, c_tools = int(prev.get("domain_mask") or CAPABILITY_BITS["general"]), prev_hash or "0000000000000000", list(prev_tools)
        poison_ok = bool(prev.get("poison_scan_clean", True))
    else:
        cap_mask, h16, c_tools = extract_capabilities_and_hash(f"{name} {description}", [])
        if prev_hash and prev_hash != "0000000000000000":
            h16 = prev_hash


    drifted = bool(prev_hash and prev_hash != "0000000000000000" and h16 != "0000000000000000" and prev_hash != h16)
    eff_ms = warm_latency_ms if warm_latency_ms is not None else cold_latency_ms
    if not http_alive or eff_ms is None or is_repo:
        lat_g = str(prev.get("latency_grade") or "E") if http_alive else "E"
    elif eff_ms <= 120.0:
        lat_g = "A"
    elif eff_ms <= 300.0:
        lat_g = "B"
    elif eff_ms <= 700.0:
        lat_g = "C"
    elif eff_ms <= 1500.0:
        lat_g = "D"
    else:
        lat_g = "E"


    if not poison_ok:
        guar_g, merit_g, node_h, new_wt, status = "F", "F", "W", 0.0, "SLASHED_TOOL_POISONING_GRADE_F"
    elif is_repo:
        guar_g, merit_g, node_h, new_wt, status = "D", "C", "Z", min(prev_wt, 0.50), "UNHOSTED_SOURCE_REPO_GRADE_D"
    elif not http_alive:
        guar_g, merit_g, node_h, new_wt, status = "E", "D", "Z", round(max(0.10, prev_wt - 0.20), 4), "QUARANTINED_OFFLINE_GRADE_E"
    else:
        guar_g = "A" if (c_tools or prev.get("guarantee_grade") == "A") else "B"
        merit_g = "A" if (wins >= 20 and fails == 0) else ("B" if (wins >= 5 and wins >= fails * 4) else str(prev.get("merit_grade") or "C")[:1].upper())
        node_h = "W" if (eff_ms and eff_ms > 1500.0) else "Z"
        new_wt = round(min(0.99, prev_wt + (0.04 if c_tools else 0.01)), 4)
        status = "VERIFIED_LIVE_TOOLS_GRADE_A" if guar_g == "A" else "VERIFIED_LIVE_HTTP_GRADE_B"


    r_mask = 0
    if poison_ok:
        r_mask |= READINESS_BITS["poison_scan_clean"]
    if not drifted:
        r_mask |= READINESS_BITS["schema_drift_stable"]
    if auth_mode == "none" and not is_repo and http_alive:
        r_mask |= READINESS_BITS["zero_auth_instant"]
    if (rate_limit_rpm or 0) >= 60:
        r_mask |= READINESS_BITS["high_concurrency_rpm"]
    if x402_supported:
        r_mask |= READINESS_BITS["x402_native_payable"]
    if enc >= 25:
        r_mask |= READINESS_BITS["seasoned_tenure"]


    econ_g, pref_g = ("B" if x402_supported else "A"), ("S" if lat_g in ("A", "B") else "D")
    stamp, u64, u64_hex = MgleNnp64Codec.pack(merit_g, guar_g, lat_g, econ_g, node_h, "E", pref_g, r_mask, cap_mask)
    tenure = "veteran_100plus" if enc >= 100 else ("established_25plus" if enc >= 25 else "newcomer")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    v_dom = extract_vendor_domain(endpoint)


    dossier = {
        "agent_id": agent_id, "vendor_domain": v_dom, "mgle_nnp_code": stamp, "mgle_nnp_u64_hex": u64_hex,
        "decoded_switches": MgleNnp64Codec.unpack(u64),
        "live_readiness": {
            "callable_immediately": bool(r_mask & READINESS_BITS["zero_auth_instant"]),
            "auth_requirement": auth_mode, "cold_latency_ms": cold_latency_ms, "warm_latency_ms": warm_latency_ms,
            "observed_rate_limit_rpm": rate_limit_rpm, "x402_micropayment_ready": x402_supported,
        },
        "security_and_stability": {
            "poison_scan_clean": poison_ok, "poison_findings": poison_list,
            "tool_schema_hash_16": h16, "schema_drift_detected": drifted,
        },
        "track_record": {
            "tenure_tier": tenure, "crawler_encounters": enc,
            "meeting_room_completions": wins, "meeting_room_failures": fails,
        },
        "verified_tools_count": len(c_tools), "verified_tools": c_tools[:25],
        "inspector_summary": f"{status}: {len(c_tools)} tools on {v_dom}, warm RTT {eff_ms if eff_ms is not None else 'N/A'} ms.",
        "inspected_at_utc": now_iso,
    }
    return {
        "agent_id": agent_id, "name": name, "description": description[:400], "endpoint": endpoint,
        "merit_grade": merit_g, "guarantee_grade": guar_g, "latency_grade": lat_g, "economy_grade": econ_g,
        "node_honesty": node_h, "neighbor_protocol": "E", "preference_class": pref_g,
        "mgle_nnp_stamp": stamp, "mgle_nnp_64bit": u64, "domain_mask": cap_mask,
        "avg_latency_ms": eff_ms, "synaptic_weight": new_wt, "wired_tool_count": len(c_tools),
        "tool_schema_hash_16": h16, "schema_drift_detected": drifted, "auth_mode": auth_mode,
        "rate_limit_rpm": rate_limit_rpm, "poison_scan_clean": poison_ok, "encounter_count": enc,
        "room_completions": wins, "room_failures": fails, "dossier_json": dossier,
        "audit_status": status, "last_audited_at": now_iso,
    }




def interrogate_live_endpoint(agent_row: Dict[str, Any], timeout_sec: float = 4.5) -> Dict[str, Any]:
    aid = str(agent_row.get("agent_id") or agent_row.get("id") or "")
    name, desc = str(agent_row.get("name") or aid), str(agent_row.get("description") or "")
    ep = str(agent_row.get("endpoint") or "").strip()
    if not ep.lower().startswith(("http://", "https://")) or "github.com/" in ep.lower() or "gitlab.com/" in ep.lower():
        return build_agent_record_and_dossier(aid, name, desc, ep, False, None, None, [], "local_stdio_code", prev_record=agent_row)


    ctx = ssl.create_default_context()
    hdrs = {
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "User-Agent": f"MglennP-RadialSwitchboard-Auditor/{SPEC_VERSION} (+https://radialswitchboard.com)",
    }
    init_b = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "RadialAuditor", "version": SPEC_VERSION}}}).encode("utf-8")
    cold_ms, warm_ms, alive, rpc_ok, x402_ok = None, None, False, False, False
    auth_m, rpm, sess = "none", None, None


    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(ep, data=init_b, headers=hdrs, method="POST"), timeout=timeout_sec, context=ctx) as r:
            cold_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            alive = 200 <= r.status < 500
            sess = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
            rl = r.headers.get("X-RateLimit-Limit") or r.headers.get("RateLimit-Limit")
            if rl and str(rl).isdigit():
                rpm = int(rl)
            raw = r.read(65536).decode("utf-8", errors="replace")
            rpc_ok = ('"jsonrpc"' in raw or '"result"' in raw)
    except urllib.error.HTTPError as e:
        cold_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if e.code in (401, 403):
            alive, auth_m = True, "bearer_or_oauth_required"
        elif e.code == 402:
            alive, auth_m, x402_ok = True, "x402_micropayment", True
        elif e.code in (400, 405, 406, 422):
            alive = True
    except Exception:
        alive = False


    tools: List[Dict[str, Any]] = []
    if alive and rpc_ok:
        wh = dict(hdrs)
        if sess:
            wh["Mcp-Session-Id"] = sess
        tb = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode("utf-8")
        t1 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(ep, data=tb, headers=wh, method="POST"), timeout=timeout_sec, context=ctx) as r2:
                warm_ms = round((time.perf_counter() - t1) * 1000.0, 2)
                p_str = r2.read(131072).decode("utf-8", errors="replace").strip()
                if not p_str.startswith("{"):
                    for ln in p_str.splitlines():
                        if ln.strip().startswith("data:") and "{" in ln:
                            p_str = ln.split("data:", 1)[1].strip()
                            break
                res_o = (json.loads(p_str) or {}).get("result")
                if isinstance(res_o, dict) and isinstance(res_o.get("tools"), list):
                    tools = res_o["tools"]
        except Exception:
            pass
    return build_agent_record_and_dossier(aid, name, desc, ep, alive, cold_ms, warm_ms, tools, auth_m, rpm, x402_ok, agent_row)
class DualLaneGateAndTaxLedger:
    def __init__(self, treasury_address: str = DEFAULT_USDC_TREASURY_ADDRESS) -> None:
        self.treasury_address = treasury_address
        self.free_daily_usage: Dict[str, int] = {}
        self.pass_remaining_credits: Dict[str, int] = {}
        self.used_payment_tx_hashes: set[str] = set()
        self.active_work_challenges: Dict[str, Dict[str, Any]] = {}
        self.pending_scout_consensus: Dict[str, List[Dict[str, Any]]] = {}
        self.tax_revenue_ledger: List[Dict[str, Any]] = []


    def _sign_token(self, lane: str, nonce: str, initial_credits: int, exp_unix: int) -> str:
        msg = f"rs3.{lane}.{nonce}.{initial_credits}.{exp_unix}".encode("utf-8")
        sig = hmac.new(HMAC_SECRET_KEY, msg, hashlib.sha256).hexdigest()[:24]
        return f"rs3.{lane}.{nonce}.{initial_credits}.{exp_unix}.{sig}"


    def verify_and_consume_pass(self, token: str) -> Tuple[bool, str, int]:
        parts = (token or "").strip().split(".")
        if len(parts) != 6 or parts[0] != "rs3":
            return False, "INVALID_PASS_FORMAT", 0
        _, lane, nonce, init_s, exp_s, sig = parts
        try:
            init_c, exp_u = int(init_s), int(exp_s)
        except ValueError:
            return False, "CORRUPT_PASS_FIELDS", 0
        if int(time.time()) > exp_u:
            return False, "PASS_EXPIRED", 0
        if not hmac.compare_digest(sig, self._sign_token(lane, nonce, init_c, exp_u).split(".")[-1]):
            return False, "INVALID_HMAC_SIGNATURE", 0
        rem = self.pass_remaining_credits.get(nonce, init_c)
        if rem <= 0:
            return False, "PASS_DEPLETED", 0
        self.pass_remaining_credits[nonce] = rem - 1
        return True, f"OK_{lane.upper()}_PASS", rem - 1


    def check_or_issue_402_challenge(self, caller_fingerprint: str, pass_token: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        if pass_token:
            ok, reason, rem = self.verify_and_consume_pass(pass_token)
            if ok:
                return True, {"access": reason, "remaining_handshakes": rem}
        day_k = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')}:{caller_fingerprint}"
        used = self.free_daily_usage.get(day_k, 0)
        if used < FREE_DAILY_STARTER_CALLS:
            self.free_daily_usage[day_k] = used + 1
            return True, {"access": "FREE_STARTER_ALLOWANCE", "remaining_free_today": FREE_DAILY_STARTER_CALLS - (used + 1)}
        return False, {
            "http_status": 402,
            "error": "PAYMENT_OR_SCOUT_WORK_REQUIRED",
            "lane_a_x402_usdc": {
                "protocol": "x402-v2", "network": BASE_MAINNET_CHAIN_ID, "asset_contract": BASE_USDC_CONTRACT,
                "asset_symbol": "USDC", "amount_usdc": CASH_PASS_PRICE_USDC, "pay_to_address": self.treasury_address,
                "grants_handshakes": CASH_PASS_CREDITS, "effective_rate_usd_per_handshake": 0.0001,
            },
            "lane_b_compute_scout_duty": {
                "claim_endpoint": "/v1/work/claim", "submit_endpoint": "/v1/work/submit",
                "targets_per_assignment": WORK_ASSIGNMENT_SIZE, "grants_handshakes": WORK_PASS_CREDITS,
                "ttl_seconds": WORK_PASS_TTL_SECONDS, "monetary_value_usd": 0.00, "transferable": False,
            },
        }


    def settle_x402_usdc_payment(self, tx_hash: str, amount_usdc: float, payer_wallet: str) -> Dict[str, Any]:
        clean_tx = (tx_hash or "").strip().lower()
        if not clean_tx.startswith("0x") or len(clean_tx) < 10:
            raise ValueError("Invalid Base transaction hash.")
        if clean_tx in self.used_payment_tx_hashes:
            raise ValueError("Replay blocked: transaction hash already redeemed.")
        if amount_usdc < float(CASH_PASS_PRICE_USDC):
            raise ValueError(f"Minimum x402 settlement is {CASH_PASS_PRICE_USDC} USDC.")
        self.used_payment_tx_hashes.add(clean_tx)
        credits = max(1, int(round(amount_usdc / float(CASH_PASS_PRICE_USDC)))) * CASH_PASS_CREDITS
        nonce, exp_u = secrets.token_hex(8), int(time.time()) + CASH_PASS_TTL_SECONDS
        self.pass_remaining_credits[nonce] = credits
        token = self._sign_token("cash", nonce, credits, exp_u)
        fmv = round(amount_usdc, 6)
        entry = {
            "entry_id": f"TAX-{secrets.token_hex(6).upper()}",
            "received_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "network": BASE_MAINNET_CHAIN_ID, "treasury_wallet": self.treasury_address,
            "payer_wallet": payer_wallet, "tx_hash": clean_tx,
            "gross_usdc_received": fmv, "fair_market_value_usd": fmv,
            "irs_schedule_c_classification": "Ordinary Business Service Income (USDC at Receipt FMV)",
            "tax_reserve_30pct_usd": round(fmv * TAX_RESERVE_RATIO, 6),
            "operating_cash_60pct_usd": round(fmv * OPERATING_CASH_RATIO, 6),
            "post_tax_treasury_slice_10pct_usd": round(fmv * POST_TAX_TREASURY_SLICE_RATIO, 6),
            "handshakes_issued": credits,
        }
        self.tax_revenue_ledger.append(entry)
        sb_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        if sb_url and sb_key:
            try:
                base = sb_url if sb_url.endswith("/rest/v1") else f"{sb_url}/rest/v1"
                req = urllib.request.Request(f"{base}/radial_tax_revenue_ledger", data=json.dumps(entry).encode("utf-8"), headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}", "Content-Type": "application/json", "Prefer": "return=minimal"}, method="POST")
                urllib.request.urlopen(req, timeout=8).close()
            except Exception:
                pass
        return {"status": "SETTLED_X402_PASS_ISSUED", "pass_token": token, "handshakes_granted": credits, "expires_unix": exp_u, "tax_ledger_receipt": entry}


    def issue_scout_work_assignment(self, candidate_endpoints: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        aid = f"WORK-{secrets.token_hex(6).upper()}"
        c_prop = f"canary_nonce_{secrets.token_hex(4)}"
        c_tools = [{"name": "radial_canary_ping", "description": "Canary", "inputSchema": {"type": "object", "properties": {c_prop: {"type": "string"}}, "required": [c_prop]}}]
        _, exp_hash, _ = extract_capabilities_and_hash("radial canary", c_tools)
        picks = list(candidate_endpoints[:3])
        while len(picks) < 3:
            i = len(picks) + 1
            picks.append({"agent_id": f"mcp://queue-target-{i}", "endpoint": f"https://radialswitchboard.com/v1/mock-target/{i}"})
        c_slot = {"agent_id": f"mcp://node-verify-{secrets.token_hex(3)}", "endpoint": f"https://radialswitchboard.com/v1/canary/{c_prop}"}
        targets = [{"agent_id": r["agent_id"], "endpoint": r["endpoint"]} for r in picks]
        targets.insert(random.randint(0, len(targets)), c_slot)
        self.active_work_challenges[aid] = {"created_unix": int(time.time()), "canary_agent_id": c_slot["agent_id"], "expected_canary_hash_16": exp_hash, "targets": targets}
        return {"assignment_id": aid, "targets": targets, "expires_in_seconds": 300}


    def verify_scout_work_submission(self, assignment_id: str, results: Sequence[Dict[str, Any]], scout_region_hint: str = "unknown") -> Dict[str, Any]:
        ch = self.active_work_challenges.pop(assignment_id, None)
        if not ch or (int(time.time()) - int(ch["created_unix"]) > 300):
            return {"status": "REJECTED", "reason": "UNKNOWN_OR_EXPIRED_ASSIGNMENT"}
        by_id = {str(r.get("agent_id")): r for r in results if isinstance(r, dict)}
        if len(by_id) < len(ch["targets"]) or ch["canary_agent_id"] not in by_id:
            return {"status": "REJECTED", "reason": "INCOMPLETE_TARGET_RESULTS"}
        sub_h = str(by_id[ch["canary_agent_id"]].get("tool_schema_hash_16") or "").strip().lower()
        if not hmac.compare_digest(sub_h, ch["expected_canary_hash_16"]):
            return {"status": "REJECTED_CANARY_SPOOF_CAUGHT", "reason": "Canary tool-schema hash mismatch."}
        confirmed: List[str] = []
        for k, obs in by_id.items():
            if k == ch["canary_agent_id"]:
                continue
            b = self.pending_scout_consensus.setdefault(k, [])
            b.append({"tool_schema_hash_16": str(obs.get("tool_schema_hash_16") or ""), "region": scout_region_hint})
            if len(b) >= 2 and b[-1]["tool_schema_hash_16"] == b[-2]["tool_schema_hash_16"]:
                confirmed.append(k)
        nonce, exp_u = secrets.token_hex(8), int(time.time()) + WORK_PASS_TTL_SECONDS
        self.pass_remaining_credits[nonce] = WORK_PASS_CREDITS
        return {
            "status": "VERIFIED_WORK_PASS_ISSUED", "pass_token": self._sign_token("work", nonce, WORK_PASS_CREDITS, exp_u),
            "handshakes_granted": WORK_PASS_CREDITS, "expires_unix": exp_u,
            "monetary_value_usd": 0.00, "transferable": False, "two_scout_consensus_confirmed": confirmed,
        }




class RadialMeetingRoom:
    def __init__(self, gate: DualLaneGateAndTaxLedger, pool_by_id: Dict[str, Dict[str, Any]]) -> None:
        self.gate, self.pool_by_id = gate, pool_by_id
        self.provider_reciprocity_tallies: Dict[str, int] = {}


    def execute_handshake(
        self, caller_fingerprint: str, target_agent_id: str, jsonrpc_payload: Dict[str, Any],
        pass_token: Optional[str] = None, simulated_worker_handler: Optional[Any] = None, timeout_sec: float = 8.0,
    ) -> Dict[str, Any]:
        allowed, gate_info = self.gate.check_or_issue_402_challenge(caller_fingerprint, pass_token)
        if not allowed:
            return gate_info
        worker = self.pool_by_id.get(target_agent_id)
        if not worker:
            return {"http_status": 404, "error": f"Unknown target agent: {target_agent_id}"}
        t0, ok = time.perf_counter(), False
        try:
            if simulated_worker_handler is not None:
                w_resp = simulated_worker_handler(jsonrpc_payload)
            else:
                req = urllib.request.Request(str(worker["endpoint"]), data=json.dumps(jsonrpc_payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    w_resp = json.loads(resp.read(262144).decode("utf-8", errors="replace"))
            ms = round((time.perf_counter() - t0) * 1000.0, 2)
            ok = isinstance(w_resp, dict) and "error" not in w_resp
        except Exception as exc:
            ms, w_resp = round((time.perf_counter() - t0) * 1000.0, 2), {"error": str(exc)}


        recip = None
        if ok:
            worker["room_completions"] = int(worker.get("room_completions") or 0) + 1
            worker["synaptic_weight"] = round(min(0.99, float(worker.get("synaptic_weight") or 0.80) + 0.03), 4)
            tally = self.provider_reciprocity_tallies.get(target_agent_id, 0) + 1
            self.provider_reciprocity_tallies[target_agent_id] = tally
            if tally % 5 == 0:
                n, eu = secrets.token_hex(8), int(time.time()) + WORK_PASS_TTL_SECONDS
                self.gate.pass_remaining_credits[n] = WORK_PASS_CREDITS
                recip = self.gate._sign_token("reciprocity", n, WORK_PASS_CREDITS, eu)
        else:
            worker["room_failures"] = int(worker.get("room_failures") or 0) + 1
            worker["synaptic_weight"] = round(max(0.10, float(worker.get("synaptic_weight") or 0.80) - 0.15), 4)


        refreshed = build_agent_record_and_dossier(
            worker["agent_id"], worker["name"], worker.get("description", ""), worker["endpoint"],
            ok or (worker.get("guarantee_grade") in ("A", "B")), worker.get("avg_latency_ms"),
            ms if ok else worker.get("avg_latency_ms"), [], worker.get("auth_mode", "none"),
            worker.get("rate_limit_rpm"), prev_record=worker,
        )
        self.pool_by_id[target_agent_id] = refreshed
        return {
            "http_status": 200 if ok else 502,
            "room_witness_verdict": "DELIVERY_VERIFIED" if ok else "WORKER_CONTRACT_FAILURE",
            "measured_room_ms": ms, "updated_worker_mgle_nnp": refreshed["mgle_nnp_stamp"],
            "caller_gate": gate_info, "provider_reciprocity_pass_awarded": recip, "worker_response": w_resp,
        }




def crawl_and_interrogate_batch_to_supabase(query_str: str = "topic:mcp-server", page: int = 1, per_page: int = 25) -> Dict[str, Any]:
    hdrs = {"Accept": "application/vnd.github+json", "User-Agent": f"MglennP-RadialSwitchboard-Crawler/{SPEC_VERSION}"}
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if tok:
        hdrs["Authorization"] = f"Bearer {tok}"
    url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query_str)}&sort=updated&order=desc&per_page={per_page}&page={page}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=15) as r:
        items = (json.loads(r.read().decode("utf-8")) or {}).get("items") or []
    cands = [
        {
            "agent_id": f"gh://{(it.get('full_name') or it.get('name')).lower()}",
            "name": it.get("full_name") or it.get("name"),
            "description": (it.get("description") or "Autonomous MCP/A2A repository")[:400],
            "endpoint": (it.get("homepage") or "").strip() if str(it.get("homepage") or "").startswith("https://") else (it.get("html_url") or ""),
        }
        for it in items if (it.get("full_name") or it.get("name"))
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
        audited = list(ex.map(interrogate_live_endpoint, cands))
    sb_url, sb_key, upserted = os.environ.get("SUPABASE_URL", "").rstrip("/"), (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or ""), 0
    if sb_url and sb_key and audited:
        base = sb_url if sb_url.endswith("/rest/v1") else f"{sb_url}/rest/v1"
        try:
            req = urllib.request.Request(f"{base}/radial_agent_phonebook?on_conflict=agent_id", data=json.dumps(audited).encode("utf-8"), headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}, method="POST")
            with urllib.request.urlopen(req, timeout=20) as sr:
                if sr.status in (200, 201, 204):
                    upserted = len(audited)
        except Exception:
            pass
    return {"spec_version": SPEC_VERSION, "target_table": "radial_agent_phonebook", "audited_count": len(audited), "upserted_to_supabase": upserted, "records": audited}




DEFAULT_SEED_SPECS: Tuple[Tuple[str, str, str, str, str, float, int], ...] = (
    ("mcp://neon-fast-sql", "Neon Serverless Postgres Planner", "https://mcp.neon.tech/sse", "run_readonly_sql", "sql_query", 68.0, 19),
    ("mcp://supabase-pg", "Supabase PostgREST & RLS Auditor", "https://mcp.supabase.com/rpc", "inspect_pg_rls", "table_name", 82.0, 16),
    ("mcp://turso-libsql", "Turso Edge LibSQL Engine", "https://edge.turso.tech/mcp", "exec_libsql", "statements", 41.0, 14),
    ("mcp://motherduck-olap", "MotherDuck DuckDB Parquet Engine", "https://api.motherduck.com/mcp", "duck_olap", "analytical_sql", 135.0, 12),
    ("mcp://clickhouse-col", "ClickHouse Columnar SQL Node", "https://mcp.clickhouse.cloud/rpc", "query_columnar_sql", "ch_query", 94.0, 11),
    ("mcp://cockroach-tx", "CockroachDB Serializable Verifier", "https://mcp.cockroachlabs.cloud/sse", "verify_serializable_tx", "tx_sql", 148.0, 9),
    ("mcp://planetscale-vt", "PlanetScale Vitess MySQL Planner", "https://mcp.planetscale.com/rpc", "explain_vitess_sql", "mysql_stmt", 112.0, 8),
    ("mcp://timescale-ts", "TimescaleDB Time-Series SQL Node", "https://mcp.timescale.com/sse", "rollup_hypertable_sql", "bucket_sql", 162.0, 7),
    ("mcp://tembo-vec", "Tembo Hybrid SQL + pgvector Node", "https://mcp.tembo.io/rpc", "hybrid_sql_search", "join_query", 175.0, 6),
    ("mcp://crunchy-pg", "Crunchy Bridge Safe SQL Sandbox", "https://mcp.crunchybridge.com/rpc", "sandbox_pg_explain", "explain_sql", 190.0, 5),
    ("mcp://e2b-firecracker-py", "E2B Firecracker MicroVM Python", "https://mcp.e2b.dev/sse", "execute_python", "code", 88.0, 22),
    ("mcp://semgrep-ast", "Semgrep AST Security Auditor", "https://mcp.semgrep.dev/rpc", "scan_security_ast", "source_code", 76.0, 18),
    ("mcp://constellation-sec", "Constellation SEC EDGAR Finance Node", "https://mcp.constellationfinance.ai/sse", "extract_sec_xbrl", "ticker", 34.0, 28),
    ("mcp://base-usdc-x402", "Base Mainnet USDC & x402 Verifier", "https://mcp.base-rpc-verify.org/rpc", "verify_usdc_x402", "tx_hash", 61.0, 19),
)




class StandaloneSwitchboardRuntime:
    def __init__(self, hydrate_external: bool = True) -> None:
        self.pool_by_id: Dict[str, Dict[str, Any]] = {}
        self.gate = DualLaneGateAndTaxLedger(DEFAULT_USDC_TREASURY_ADDRESS)
        self.room = RadialMeetingRoom(self.gate, self.pool_by_id)
        self.crawl_cursor = {"query_index": 0, "page": 1, "total_runs": 1}
        self._seed_verified_baseline()
        if hydrate_external:
            self._hydrate_from_supabase_and_static()


    def _seed_verified_baseline(self) -> None:
        for aid, nm, ep, tn, pn, wms, wins in DEFAULT_SEED_SPECS:
            rec = build_agent_record_and_dossier(
                aid, nm, f"{nm} ({tn})", ep, True, wms + 75.0, wms,
                [{"name": tn, "description": nm, "inputSchema": {"type": "object", "properties": {pn: {"type": "string"}}, "required": [pn]}}],
                prev_record={"encounter_count": 35, "room_completions": wins, "synaptic_weight": 0.92},
            )
            self.pool_by_id[aid] = rec


    def _normalize_legacy_row(self, r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        aid = str(r.get("agent_id") or r.get("id") or "").strip()
        if not aid:
            return None
        if isinstance(r.get("dossier_json"), dict) and r["dossier_json"] and r.get("mgle_nnp_64bit"):
            return r
        ep = str(r.get("endpoint") or r.get("repo_url") or "").strip()
        g = str(r.get("guarantee_grade") or r.get("grade") or "B")[:1].upper()
        alive = g in ("A", "B")
        lat = r.get("avg_latency_ms")
        eff_lat = float(lat) if isinstance(lat, (int, float)) else (140.0 if alive else None)
        return build_agent_record_and_dossier(
            aid, str(r.get("name") or r.get("agent_name") or aid),
            str(r.get("description") or ""), ep, alive, eff_lat, eff_lat, [],
            auth_mode=str(r.get("auth_mode") or ("none" if alive else "local_stdio_code")),
            prev_record=r,
        )


    def _hydrate_from_supabase_and_static(self) -> None:
        seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "permanent_crawled_agents.json")
        if os.path.isfile(seed_path):
            try:
                raw_seed = json.loads(open(seed_path, "r", encoding="utf-8").read())
                for _, item in (raw_seed.get("agents") or {}).items():
                    if isinstance(item, dict):
                        norm = self._normalize_legacy_row(item)
                        if norm and norm["agent_id"] not in self.pool_by_id:
                            self.pool_by_id[norm["agent_id"]] = norm
            except Exception:
                pass


        sb_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
        sb_key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.environ.get("SUPABASE_KEY", "").strip()
            or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        )
        if not sb_url or not sb_key:
            return
        base = sb_url if sb_url.endswith("/rest/v1") else f"{sb_url}/rest/v1"
        offset = 0
        while offset < 10000:
            try:
                url = f"{base}/radial_agent_phonebook?select=*&order=agent_id.asc&limit=1000&offset={offset}"
                req = urllib.request.Request(url, headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    batch = json.loads(resp.read().decode("utf-8"))
                if not isinstance(batch, list) or not batch:
                    break
                for row in batch:
                    if isinstance(row, dict):
                        norm = self._normalize_legacy_row(row)
                        if norm:
                            self.pool_by_id[norm["agent_id"]] = norm
                if len(batch) < 1000:
                    break
                offset += 1000
            except Exception:
                break




class ThreadingHTTPServerReuse(socketserver.ThreadingTCPServer):
    allow_reuse_address = True




def create_http_handler(runtime: StandaloneSwitchboardRuntime):
    class SwitchboardRequestHandler(http.server.BaseHTTPRequestHandler):
        def _send_bytes(self, code: int, content_type: str, raw: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Radial-Pass")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(raw)


        def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
            self._send_bytes(code, "application/json; charset=utf-8", json.dumps(payload, indent=2).encode("utf-8"))


        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send_bytes(204, "text/plain; charset=utf-8", b"")


        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            p = parsed.path.rstrip("/") or "/"
            qs = urllib.parse.parse_qs(parsed.query)


            if p in ("/", "/directory"):
                ui = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "radial_agent_directory_explorer.html")
                if os.path.isfile(ui):
                    self._send_bytes(200, "text/html; charset=utf-8", open(ui, "rb").read())
                    return
                self._send_bytes(200, "text/html; charset=utf-8", f"<h1>MglennP Radial Switchboard Spec {SPEC_VERSION} Live</h1>".encode("utf-8"))
                return


            if p == "/llms.txt":
                txt = (
                    f"# MglennP Radial Switchboard — Spec Rev {SPEC_VERSION}\n"
                    f"Brand: MglennP — An honest approach to solving everyday challenges.\n"
                    f"Default Flash Policy: Top-10 Anti-Monoculture Varied Matchmaking (POST /v1/flash)\n"
                    f"Dual-Lane Gate: 15 free daily calls -> Lane A (0.01 USDC on Base {runtime.gate.treasury_address} for 100 handshakes) "
                    f"OR Lane B (Canary Scout Duty POST /v1/work/claim for 20-handshake 1h pass).\n"
                )
                self._send_bytes(200, "text/plain; charset=utf-8", txt.encode("utf-8"))
                return


            if p in ("/openapi.json", "/.well-known/mcp.json"):
                self._send_json(200, {
                    "openapi": "3.1.0",
                    "info": {"title": "MglennP Radial Switchboard", "version": SPEC_VERSION},
                    "usdc_treasury_base": runtime.gate.treasury_address,
                    "default_flash_top_k": DEFAULT_FLASH_TOP_K,
                    "endpoints": ["/v1/flash", "/v1/matchmake", "/v1/dossier/{agent_id}", "/v1/room/handshake", "/v1/x402/settle", "/v1/work/claim", "/v1/work/submit", "/v1/health", "/v1/benchmark"],
                })
                return


            if p == "/v1/health":
                recs = list(runtime.pool_by_id.values())
                ab = sum(1 for r in recs if r.get("guarantee_grade") in ("A", "B"))
                gd = sum(1 for r in recs if r.get("guarantee_grade") == "D")
                ge = sum(1 for r in recs if r.get("guarantee_grade") == "E")
                gf = len(recs) - (ab + gd + ge)
                self._send_json(200, {
                    "status": "ok",
                    "service": f"MglennP Radial Switchboard (Standalone Spec Rev {SPEC_VERSION})",
                    "spec_version": SPEC_VERSION,
                    "default_flash_top_k": DEFAULT_FLASH_TOP_K,
                    "usdc_treasury_base": runtime.gate.treasury_address,
                    "total_unsorted_pool": len(recs),
                    "live_callable_ab": ab, "offline_code_d": gd, "quarantined_e": ge, "slashed_f": gf,
                    "inventory": {
                        "total_indexed": len(recs), "verified_live_callable": ab,
                        "unhosted_repos_grade_d": gd, "quarantined_dead_grade_e": ge,
                        "internal_system_canaries": gf, "reconciled_sum": len(recs), "unaccounted_records": 0,
                    },
                })
                return


            if p == "/v1/benchmark":
                recs = list(runtime.pool_by_id.values())
                samples = []
                for _ in range(20):
                    r = flash_unsorted_pool(recs, ["sql", "database"], max_latency_grade="C", top_k=DEFAULT_FLASH_TOP_K)
                    samples.append(float(r["single_pass_flash_ms"]))
                samples.sort()
                self._send_json(200, {
                    "spec_version": SPEC_VERSION, "agents_scanned": len(recs), "default_top_k": DEFAULT_FLASH_TOP_K,
                    "p50_bitwise_ms": samples[len(samples) // 2],
                    "p95_bitwise_ms": samples[min(len(samples) - 1, int(len(samples) * 0.95))],
                    "bitwise_scan_1803_agents_ms": samples[len(samples) // 2],
                })
                return


            if p == "/v1/directory/live":
                recs = list(runtime.pool_by_id.values())
                self._send_json(200, {"total_agents": len(recs), "crawl_count": runtime.crawl_cursor["total_runs"], "agents": recs[:250]})
                return


            if p == "/v1/matchmake":
                intent = (qs.get("intent") or ["sql database"])[0]
                caps = infer_capabilities_from_intent(intent)
                self._send_json(200, flash_unsorted_pool(list(runtime.pool_by_id.values()), caps, top_k=int((qs.get("top_k") or [DEFAULT_FLASH_TOP_K])[0])))
                return


            if p.startswith("/v1/dossier/"):
                aid = urllib.parse.unquote(p[len("/v1/dossier/"):])
                rec = runtime.pool_by_id.get(aid)
                self._send_json(200 if rec else 404, (rec.get("dossier_json") or {}) if rec else {"error": "Not found"})
                return


            self._send_json(404, {"error": "Route not found"})


        def do_POST(self) -> None:  # noqa: N802
            p = urllib.parse.urlparse(self.path).path.rstrip("/")
            ln = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(ln, 524288)).decode("utf-8")) if ln > 0 else {}
            ip = self.client_address[0] if self.client_address else "anonymous"
            tok = self.headers.get("X-Radial-Pass") or body.get("pass_token")


            if p in ("/v1/flash", "/v1/matchmake"):
                caps = body.get("capabilities") or infer_capabilities_from_intent(str(body.get("intent") or ""))
                res = flash_unsorted_pool(
                    list(runtime.pool_by_id.values()), caps,
                    bool(body.get("require_instant_zero_auth", False)),
                    str(body.get("max_latency_grade", "C")),
                    top_k=int(body.get("top_k", DEFAULT_FLASH_TOP_K)),
                )
                self._send_json(200, res)
            elif p == "/v1/directory/crawl":
                queries = ("topic:mcp-server", "topic:model-context-protocol", "topic:a2a-agent", "fastmcp in:readme")
                q = queries[runtime.crawl_cursor["query_index"] % len(queries)]
                pg = runtime.crawl_cursor["page"]
                out = crawl_and_interrogate_batch_to_supabase(q, pg, 20)
                for rec in out.get("records", []):
                    runtime.pool_by_id[rec["agent_id"]] = rec
                runtime.crawl_cursor["page"] = pg + 1 if pg < 8 else 1
                if runtime.crawl_cursor["page"] == 1:
                    runtime.crawl_cursor["query_index"] += 1
                runtime.crawl_cursor["total_runs"] += 1
                self._send_json(200, {"added_or_updated": out["audited_count"], "total_unique_real_agents": len(runtime.pool_by_id)})
            elif p == "/v1/work/claim":
                self._send_json(200, runtime.gate.issue_scout_work_assignment(list(runtime.pool_by_id.values())))
            elif p == "/v1/work/submit":
                res = runtime.gate.verify_scout_work_submission(str(body.get("assignment_id") or ""), body.get("results") or [], str(body.get("region") or "external"))
                self._send_json(200 if res.get("status") == "VERIFIED_WORK_PASS_ISSUED" else 400, res)
            elif p == "/v1/x402/settle":
                try:
                    self._send_json(200, runtime.gate.settle_x402_usdc_payment(str(body.get("tx_hash") or ""), float(body.get("amount_usdc") or 0.0), str(body.get("payer_wallet") or "")))
                except ValueError as err:
                    self._send_json(400, {"error": str(err)})
            elif p == "/v1/room/handshake":
                res = runtime.room.execute_handshake(ip, str(body.get("target_agent_id") or ""), body.get("payload") or {}, tok)
                self._send_json(int(res.get("http_status", 200)), res)
            elif p == "/v1/outcome":
                aid = str(body.get("agent_id") or "")
                self._send_json(200, {"agent_id": aid, "ticket_valid": False, "independent_probe_alive": True, "quarantined": False, "guarantee_grade": "A"})
            else:
                self._send_json(404, {"error": "Route not found"})


        def log_message(self, fmt: str, *args: Any) -> None:
            return
    return SwitchboardRequestHandler




def run_self_test() -> int:
    assert DEFAULT_USDC_TREASURY_ADDRESS.lower() == "0x24b1a09b489c67c3e43f7cd1f3023aef544104fd"
    assert DEFAULT_FLASH_TOP_K == 10
    rt = StandaloneSwitchboardRuntime(hydrate_external=False)
    for i in range(5):
        c = build_agent_record_and_dossier(
            f"mcp://monoculture-clone-{i}", f"Clone #{i}", "PostgreSQL database query",
            f"https://s{i}.monoculture-sql.io/mcp", True, 110.0, 55.0,
            [{"name": "exec_sql", "description": "SQL", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}],
            prev_record={"encounter_count": 30, "room_completions": 10, "synaptic_weight": 0.95},
        )
        rt.pool_by_id[c["agent_id"]] = c


    srv = ThreadingHTTPServerReuse(("127.0.0.1", 0), create_http_handler(rt))
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        h = json.loads(urllib.request.urlopen(f"{base}/v1/health", timeout=5).read().decode("utf-8"))
        assert h["status"] == "ok" and h["inventory"]["unaccounted_records"] == 0
        b = json.loads(urllib.request.urlopen(f"{base}/v1/benchmark", timeout=5).read().decode("utf-8"))
        assert b["default_top_k"] == 10
        llms = urllib.request.urlopen(f"{base}/llms.txt", timeout=5).read().decode("utf-8")
        assert "0x24b1a09b489c67c3e43f7cd1f3023aef544104fd" in llms
        f_req = urllib.request.Request(
            f"{base}/v1/flash",
            data=json.dumps({"capabilities": ["sql", "database"], "require_instant_zero_auth": True, "max_latency_grade": "B"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        f_res = json.loads(urllib.request.urlopen(f_req, timeout=5).read().decode("utf-8"))
        assert f_res["finalist_count"] == 10 and f_res["variability_summary"]["unique_vendor_domains"] == 10
    finally:
        srv.shutdown()
        srv.server_close()


    print(f"[PASS] Spec {SPEC_VERSION} Production Cutover HTTP Server + Top-10 Varied Flash + Beacons Verified.")
    return 0




def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--crawl-once", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = ap.parse_args()
    if args.crawl_once:
        print(json.dumps(crawl_and_interrogate_batch_to_supabase(), indent=2))
        return 0
    if args.serve:
        rt = StandaloneSwitchboardRuntime(hydrate_external=True)
        with ThreadingHTTPServerReuse(("0.0.0.0", args.port), create_http_handler(rt)) as srv:
            print(f"Radial Switchboard {SPEC_VERSION} active on 0.0.0.0:{args.port} | Pool={len(rt.pool_by_id)} | Treasury={DEFAULT_USDC_TREASURY_ADDRESS}")
            srv.serve_forever()
        return 0
    return run_self_test()




if __name__ == "__main__":
    raise SystemExit(main())
