#!/usr/bin/env python3
"""MglennP Radial Switchboard -- Spec Rev 3.2.0 (Bridged Real-Only + Caller Hook Engine) | support@radialswitchboard.com"""
from __future__ import annotations
import argparse, concurrent.futures, datetime, hashlib, hmac, http.server
import json, os, random, re, secrets, socketserver, ssl, threading, time
import urllib.error, urllib.parse, urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


SPEC_VERSION = "3.2.0"
SCHEMA_NIBBLE = 0x3
CONTACT_EMAIL = "support@radialswitchboard.com"
PUBLIC_GITHUB_REPO = "https://github.com/MglennP2/mglennp-radial-switchboard"
DEFAULT_USDC_TREASURY_ADDRESS = os.environ.get("RADIAL_USDC_TREASURY_ADDRESS", "0x24b1a09b489c67c3e43f7cd1f3023aef544104fd")
BASE_MAINNET_CHAIN_ID, BASE_USDC_CONTRACT = "eip155:8453", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_FLASH_TOP_K, MAX_FLASH_TOP_K = 10, 25
CASH_PASS_PRICE_USDC, CASH_PASS_CREDITS, CASH_PASS_TTL_SECONDS = "0.01", 100, 86400 * 30
WORK_ASSIGNMENT_SIZE, WORK_PASS_CREDITS, WORK_PASS_TTL_SECONDS = 4, 20, 3600
FREE_DAILY_STARTER_CALLS, EXECUTION_TICKET_TTL_SECONDS = 15, 86400
TAX_RESERVE_RATIO, OPERATING_CASH_RATIO, POST_TAX_TREASURY_SLICE_RATIO = 0.30, 0.60, 0.10
HMAC_SECRET_KEY = os.environ.get("RADIAL_HMAC_SECRET", "radial-switchboard-v3-dev-hmac-replace-in-cloud-run-env").encode("utf-8")
TELEMETRY_LOCAL_PATH, TELEMETRY_SUPABASE_KEY = "/tmp/radial_telemetry_state.json", "switchboard_telemetry_v3"


CAPABILITY_NAMES = (
    "sql", "database", "code_exec", "git_ops", "web_fetch", "search_rag", "math_verify", "finance_data",
    "crypto_chain", "payments_x402", "file_parse", "media_vision", "maps_geo", "weather_env", "security_audit",
    "schema_transform", "vector_memory", "cloud_devops", "messaging_comm", "data_analytics", "legal_tax",
    "commerce_sku", "agent_orchestration", "general",
)
CAPABILITY_BITS = {n: (1 << i) for i, n in enumerate(CAPABILITY_NAMES)}
READINESS_NAMES = (
    "idempotent_read_safe", "seasoned_tenure", "x402_native_payable", "schema_drift_stable",
    "poison_scan_clean", "large_payload_capable", "high_concurrency_rpm", "zero_auth_instant",
)
READINESS_BITS = {n: (1 << (24 + i)) for i, n in enumerate(READINESS_NAMES)}
CAPABILITY_KEYWORDS = {
    "sql": ("sql", "postgres", "postgresql", "mysql", "sqlite", "duckdb", "bigquery", "clickhouse"),
    "database": ("database", "supabase", "redis", "mongodb", "turso", "kv", "table", "query", "postgres", "sqlite", "duckdb"),
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
    "maps_geo": ("map", "maps", "geocode", "route", "distance", "latitude", "longitude", "places"),
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
TOOL_POISONING_PATTERNS = (
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
COMPUTE_MASK = CAPABILITY_BITS["code_exec"] | CAPABILITY_BITS["sql"] | CAPABILITY_BITS["database"] | CAPABILITY_BITS["cloud_devops"]
VERIFY_MASK = CAPABILITY_BITS["math_verify"] | CAPABILITY_BITS["security_audit"] | CAPABILITY_BITS["schema_transform"] | CAPABILITY_BITS["legal_tax"]
SYNTHETIC_LEGACY_IDS = {
    "mcp://neon-fast-sql", "mcp://supabase-pg", "mcp://turso-libsql", "mcp://motherduck-olap", "mcp://clickhouse-col",
    "mcp://cockroach-tx", "mcp://planetscale-vt", "mcp://timescale-ts", "mcp://tembo-vec", "mcp://crunchy-pg",
    "mcp://e2b-firecracker-py", "mcp://semgrep-ast", "mcp://constellation-sec", "mcp://base-usdc-x402",
}
MCP_STDIO_BRIDGE_SOURCE = """#!/usr/bin/env python3
\"\"\"MglennP Radial Switchboard -- MCP Stdio Bridge (Spec Rev 3.2.0) | support@radialswitchboard.com\"\"\"
import json, os, sys, urllib.request
MCP_URL = os.environ.get("RADIAL_MCP_URL", "https://radialswitchboard.com/mcp")
PASS_TOKEN = os.environ.get("RADIAL_PASS_TOKEN", "").strip()
for line in sys.stdin:
    raw = line.strip()
    if not raw: continue
    try:
        h = {"Content-Type": "application/json", "Accept": "application/json", "mcp-protocol-version": "2026-07-28"}
        if PASS_TOKEN: h["X-Radial-Pass"] = PASS_TOKEN
        with urllib.request.urlopen(urllib.request.Request(MCP_URL, data=raw.encode(), headers=h, method="POST"), timeout=15) as r:
            b = r.read().decode("utf-8", errors="replace").strip()
            if b: sys.stdout.write(b + "\\n"); sys.stdout.flush()
    except Exception as exc:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(exc)}}) + "\\n"); sys.stdout.flush()
"""


def extract_vendor_domain(ep: str) -> str:
    host = (urllib.parse.urlparse(ep).hostname or "").lower().strip(".") if "://" in (ep or "") else ""
    if not host: return (ep or "").lower()[:32]
    pts = host.split(".")
    return ".".join(pts[-3:]) if len(pts) >= 3 and ".".join(pts[-2:]) in MULTI_PART_TLDS else (".".join(pts[-2:]) if len(pts) >= 2 else host)


def infer_capabilities_from_intent(txt: str) -> List[str]:
    low = (txt or "").lower()
    m = [c for c, kws in CAPABILITY_KEYWORDS.items() if any(k in low for k in kws)]
    return m if m else ["general"]


def issue_execution_ticket(agent_id: str, now_unix: Optional[int] = None) -> str:
    ts = int(now_unix if now_unix is not None else time.time())
    ah = hashlib.sha256((agent_id or "").strip().encode()).hexdigest()[:12]
    core = f"v2.{ts}.{ah}.{secrets.token_hex(4)}"
    return f"{core}.{hmac.new(HMAC_SECRET_KEY, core.encode(), hashlib.sha256).hexdigest()[:24]}"


def verify_execution_ticket(agent_id: str, ticket: str) -> Tuple[bool, str]:
    pts = (ticket or "").strip().split(".")
    if len(pts) != 5 or pts[0] != "v2": return False, "INVALID_FORMAT"
    try: ts = int(pts[1])
    except ValueError: return False, "CORRUPT_TS"
    now_u = int(time.time())
    if now_u - ts > EXECUTION_TICKET_TTL_SECONDS or ts > now_u + 300: return False, "EXPIRED"
    if not hmac.compare_digest(pts[2], hashlib.sha256((agent_id or "").strip().encode()).hexdigest()[:12]): return False, "AGENT_MISMATCH"
    exp = hmac.new(HMAC_SECRET_KEY, f"v2.{ts}.{pts[2]}.{pts[3]}".encode(), hashlib.sha256).hexdigest()[:24]
    return (True, "VALID") if hmac.compare_digest(pts[4], exp) else (False, "INVALID_HMAC")


class MgleNnp64Codec:
    @staticmethod
    def pack(merit: str, guarantee: str, latency: str, economy: str, node_h: str, neigh: str, pref: str, r_mask: int, c_mask: int, hop: int = 0) -> Tuple[str, int, str]:
        mc, gc, lc, ec = merit[:1].upper(), guarantee[:1].upper(), latency[:1].upper(), economy[:1].upper()
        n1, n2, pc = node_h[:1].upper(), neigh[:1].upper(), pref[:1].upper()
        s0 = ((hop & 0x3) << 2) | (SCHEMA_NIBBLE & 0x3)
        u32 = ((s0 & 0xF) << 28) | (GRADE_TO_NIBBLE.get(mc, 3) << 24) | (GRADE_TO_NIBBLE.get(gc, 5) << 20) | (GRADE_TO_NIBBLE.get(lc, 5) << 16) | (GRADE_TO_NIBBLE.get(ec, 1) << 12) | (NODE_TO_NIBBLE.get(n1, 1) << 8) | (NEIGHBOR_TO_NIBBLE.get(n2, 1) << 4) | PREF_TO_NIBBLE.get(pc, 1)
        u64 = ((u32 & 0xFFFFFFFF) << 32) | ((r_mask & 0xFF000000) | (c_mask & 0x00FFFFFF))
        return f"{mc}{gc}{lc}{ec}-{n1}{n2}{pc}", u64, f"0x{u64:016X}"


    @staticmethod
    def unpack(u64: int) -> Dict[str, Any]:
        u32, l32 = (u64 >> 32) & 0xFFFFFFFF, u64 & 0xFFFFFFFF
        mc, gc, lc, ec = NIBBLE_TO_GRADE.get((u32 >> 24) & 0xF, "C"), NIBBLE_TO_GRADE.get((u32 >> 20) & 0xF, "E"), NIBBLE_TO_GRADE.get((u32 >> 16) & 0xF, "E"), NIBBLE_TO_GRADE.get((u32 >> 12) & 0xF, "A")
        n1, n2, pc = NIBBLE_TO_NODE.get((u32 >> 8) & 0xF, "Z"), NIBBLE_TO_NEIGHBOR.get((u32 >> 4) & 0xF, "E"), NIBBLE_TO_PREF.get(u32 & 0xF, "S")
        return {"mgle_nnp_code": f"{mc}{gc}{lc}{ec}-{n1}{n2}{pc}", "u64_hex": f"0x{u64:016X}", "merit": mc, "guarantee": gc, "latency": lc, "economy": ec, "readiness_flags": [n for n, b in READINESS_BITS.items() if l32 & b], "capabilities": [n for n, b in CAPABILITY_BITS.items() if l32 & b]}


    @staticmethod
    def build_query_masks(caps: Sequence[str], zero_auth: bool = False, poison_clean: bool = True, max_lat: str = "C", zero_hop: bool = True) -> Tuple[int, int, str]:
        req = READINESS_BITS["poison_scan_clean"] if poison_clean else 0
        if zero_auth: req |= READINESS_BITS["zero_auth_instant"]
        for c in caps: req |= CAPABILITY_BITS.get(c.strip().lower(), 0)
        return req, 0, f"**{max_lat[:1].upper()}*-{'Z' if zero_hop else '*'}**"


def select_varied_top_k(scored: Sequence[Tuple[float, Dict[str, Any]]], top_k: int = DEFAULT_FLASH_TOP_K) -> Tuple[List[Tuple[Dict[str, Any], str, str]], Dict[str, Any]]:
    lim = max(1, min(MAX_FLASH_TOP_K, int(top_k or DEFAULT_FLASH_TOP_K)))
    enr = [(sc, extract_vendor_domain(str(r.get("endpoint") or "")), str(r.get("tool_schema_hash_16") or "0000000000000000"), f"{r.get('auth_mode','none')}:{r.get('latency_grade','B')}", r) for sc, r in scored]
    chosen, c_ids, v_seen, s_seen, p_seen = [], set(), {}, set(), set()
    pool = list(enr)
    while len(chosen) < lim and pool:
        bi, ba = -1, -1.0
        for i, (sc, vd, sh, ep, rec) in enumerate(pool):
            aid = str(rec.get("agent_id") or "")
            if aid in c_ids or vd in v_seen or (sh != "0000000000000000" and sh in s_seen): continue
            adj = sc + (0.035 if ep not in p_seen else 0.0)
            if adj > ba: ba, bi = adj, i
        if bi < 0: break
        sc, vd, sh, ep, rec = pool.pop(bi)
        chosen.append((rec, "INDEPENDENT_VENDOR_AND_SCHEMA", vd)); c_ids.add(str(rec.get("agent_id") or ""))
        v_seen[vd] = v_seen.get(vd, 0) + 1; p_seen.add(ep)
        if sh != "0000000000000000": s_seen.add(sh)
    for sc, vd, sh, ep, rec in enr:
        if len(chosen) >= lim: break
        aid = str(rec.get("agent_id") or "")
        if aid not in c_ids:
            chosen.append((rec, "SECONDARY_VARIANT", vd)); c_ids.add(aid); v_seen[vd] = v_seen.get(vd, 0) + 1
    return chosen, {"requested_top_k": lim, "returned_count": len(chosen), "unique_vendor_domains": len(v_seen), "unique_tool_schemas": len(s_seen), "monoculture_protection": "ACTIVE_LINEAGE_DIVERSITY"}


def assemble_complementary_crew(scored: Sequence[Tuple[float, Dict[str, Any]]], req_cap: int) -> Tuple[List[Tuple[Dict[str, Any], str, str]], Dict[str, Any]]:
    if not scored: return [], {"crew_size": 0, "unique_vendor_domains": 0, "single_agent_coverage_pct": 0.0, "crew_combined_coverage_pct": 0.0, "provider_independence_verified": False}
    enr = [(sc, extract_vendor_domain(str(r.get("endpoint") or "")), int(r.get("domain_mask") or (int(r.get("mgle_nnp_64bit") or 0) & 0x00FFFFFF)), r) for sc, r in scored]
    u_ids, u_vends, crew, masks = set(), set(), [], []
    roles = (
        ("1_COMPUTE_EXECUTION", lambda s, v, m: s + (0.12 if (m & COMPUTE_MASK) else 0.0) + ((m & req_cap).bit_count() * 0.08 if req_cap else 0.0)),
        ("2_DOMAIN_KNOWLEDGE_COMPLEMENT", lambda s, v, m: s + (0.25 if v not in u_vends else -0.15) + (((m & ~(masks[0] if masks else 0)) & req_cap).bit_count() * 0.22 if req_cap else 0.0)),
        ("3_INDEPENDENT_VERIFICATION", lambda s, v, m: s + (0.30 if v not in u_vends else -0.20) + (0.18 if (m & VERIFY_MASK) else 0.0)),
    )
    for r_name, fn in roles:
        best, bs = None, -999.0
        for sc, vd, cm, rec in enr:
            if str(rec.get("agent_id") or "") in u_ids: continue
            adj = fn(sc, vd, cm)
            if adj > bs: bs, best = adj, (rec, r_name, vd, cm)
        if best:
            rc, rn, vd, cm = best
            crew.append((rc, rn, vd)); u_ids.add(str(rc.get("agent_id") or "")); u_vends.add(vd); masks.append(cm)
    comb = 0
    for m in masks: comb |= m
    den = max(1, req_cap.bit_count()) if req_cap else 1
    scov = round(min(100.0, (((masks[0] if masks else 0) & req_cap).bit_count() / den) * 100.0), 1) if req_cap else 100.0
    ccov = round(min(100.0, ((comb & req_cap).bit_count() / den) * 100.0), 1) if req_cap else 100.0
    return crew, {"crew_size": len(crew), "roles_assigned": [x[1] for x in crew], "unique_vendor_domains": len(u_vends), "single_agent_coverage_pct": scov, "crew_combined_coverage_pct": ccov, "provider_independence_verified": len(u_vends) == len(crew) and len(crew) > 0}


def flash_unsorted_pool(pool: Sequence[Dict[str, Any]], caps: Sequence[str], zero_auth: bool = False, max_lat: str = "C", zero_hop: bool = True, top_k: int = DEFAULT_FLASH_TOP_K, mode: str = "top10_varied") -> Dict[str, Any]:
    t0 = time.perf_counter()
    req_bits, _, coupler = MgleNnp64Codec.build_query_masks(caps, zero_auth, True, max_lat, zero_hop)
    max_nib = GRADE_TO_NIBBLE.get(max_lat[:1].upper(), 3)
    exact, partial, viable = [], [], []
    for rec in pool:
        u64 = int(rec.get("mgle_nnp_64bit") or 0)
        u32, l32 = (u64 >> 32) & 0xFFFFFFFF, u64 & 0xFFFFFFFF
        if ((u32 >> 20) & 0xF) > 2 or ((u32 >> 16) & 0xF) > max_nib or (zero_hop and ((u32 >> 8) & 0xF) != 1): continue
        wt = float(rec.get("synaptic_weight") or 0.80)
        bs = round(wt + 0.05 * (6 - ((u32 >> 24) & 0xF)) + 0.02 * (6 - ((u32 >> 16) & 0xF)), 4)
        viable.append((bs + (l32 & req_bits).bit_count() * 0.12, rec))
        if (l32 & req_bits) == req_bits: exact.append((bs, rec))
        elif (l32 & req_bits).bit_count() > 0: partial.append(((l32 & req_bits).bit_count(), wt, rec))
    exact.sort(key=lambda x: x[0], reverse=True); viable.sort(key=lambda x: x[0], reverse=True)
    crew_m = None
    if (mode or "").strip().lower() == "crew":
        div, crew_m = assemble_complementary_crew(viable, req_bits & 0x00FFFFFF)
        var_s, m_mode = {"requested_top_k": 3, "returned_count": len(div), "unique_vendor_domains": crew_m["unique_vendor_domains"]}, ("COMPLEMENTARY_3_AGENT_CREW_TRIAD" if div else "NO_LIVE_RESONANCE")
    elif exact:
        div, var_s = select_varied_top_k(exact, top_k); m_mode = "EXACT_64BIT_RESONANCE_TOP10_VARIED"
    elif partial:
        partial.sort(key=lambda x: (x[0], x[1]), reverse=True)
        div, var_s = select_varied_top_k([(round(ov * 0.25 + wt, 4), r) for ov, wt, r in partial], top_k); m_mode = "CLOSEST_POPCNT_RESONANCE_TOP10_VARIED"
    else:
        div, var_s = [], {"requested_top_k": top_k, "returned_count": 0, "unique_vendor_domains": 0}; m_mode = "NO_LIVE_RESONANCE"
    ms, now_u = round((time.perf_counter() - t0) * 1000.0, 4), int(time.time())
    fins = [{"rank": i, "agent_id": r.get("agent_id"), "name": r.get("name"), "endpoint": r.get("endpoint"), "vendor_domain": vd, "variability_role": rl, "crew_role": rl if crew_m else None, "mgle_nnp_code": r.get("mgle_nnp_stamp"), "mgle_nnp_stamp": r.get("mgle_nnp_stamp"), "mgle_nnp_u64_hex": f"0x{int(r.get('mgle_nnp_64bit') or 0):016X}", "domain_mask": r.get("domain_mask", 0), "warm_latency_ms": r.get("avg_latency_ms"), "auth_mode": r.get("auth_mode", "none"), "tool_schema_hash_16": r.get("tool_schema_hash_16"), "synaptic_weight": r.get("synaptic_weight"), "execution_ticket": issue_execution_ticket(str(r.get("agent_id") or ""), now_u), "pre_handshake_dossier": r.get("dossier_json") or {}} for i, (r, rl, vd) in enumerate(div, 1)]
    out = {"spec_version": SPEC_VERSION, "pool_scanned_unsorted": len(pool), "single_pass_flash_ms": ms, "match_mode": m_mode, "coupler_applied": coupler, "required_lower32_hex": f"0x{req_bits:08X}", "variability_summary": var_s, "finalist_count": len(fins), "finalists": fins, "matches": fins, "top_match": fins[0] if fins else {}}
    if crew_m is not None: out["crew_manifest"] = crew_m
    return out


def extract_capabilities_and_hash(blob: str, tools: Sequence[Dict[str, Any]]) -> Tuple[int, str, List[Dict[str, Any]]]:
    pts, inv = [blob or ""], []
    for t in sorted(tools, key=lambda x: str(x.get("name", "") if isinstance(x, dict) else "")):
        if not isinstance(t, dict): continue
        tn, td = str(t.get("name") or "").strip(), str(t.get("description") or "").strip()[:180]
        sc = t.get("inputSchema") if isinstance(t.get("inputSchema"), dict) else {}
        pr = sc.get("properties") if isinstance(sc.get("properties"), dict) else {}
        rq = sc.get("required") if isinstance(sc.get("required"), list) else []
        pts.extend([tn, td, *(str(k) for k in pr.keys())])
        inv.append({"tool": tn, "summary": td, "inputs": {str(k): str((v or {}).get("type", "any")) for k, v in list(pr.items())[:12] if isinstance(v, dict)}, "required": [str(r) for r in rq[:12]]})
    low = " ".join(pts).lower()
    mask = 0
    for cn, kws in CAPABILITY_KEYWORDS.items():
        if any(k in low for k in kws): mask |= CAPABILITY_BITS[cn]
    if mask == 0: mask = CAPABILITY_BITS["general"]
    h16 = hashlib.sha256(json.dumps([{"n": t["tool"], "i": sorted(t["inputs"].keys()), "r": sorted(t["required"])} for t in inv], sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16] if inv else "0000000000000000"
    return mask, h16, inv


def build_agent_record_and_dossier(aid: str, name: str, desc: str, ep: str, alive: bool, cold_ms: Optional[float], warm_ms: Optional[float], tools: Sequence[Dict[str, Any]], auth_m: str = "none", rpm: Optional[int] = None, x402_ok: bool = False, prev_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pv = prev_record or {}
    enc, wins, fails = int(pv.get("encounter_count") or 0) + 1, int(pv.get("room_completions") or 0), int(pv.get("room_failures") or 0)
    p_wt = float(pv.get("synaptic_weight") or 0.80)
    low_ep = (ep or "").strip().lower()
    is_repo = not low_ep.startswith(("http://", "https://")) or any(h in low_ep for h in ("github.com/", "gitlab.com/", "npmjs.com/", "pypi.org/"))
    p_ok = not any(pat.search(json.dumps(t)) for t in tools if isinstance(t, dict) for pat in TOOL_POISONING_PATTERNS)
    c_mask, h16, c_tools = extract_capabilities_and_hash(f"{name} {desc}", tools)
    eff = warm_ms if warm_ms is not None else cold_ms
    lat_g = "E" if (not alive or eff is None or is_repo) else ("A" if eff <= 120 else ("B" if eff <= 300 else ("C" if eff <= 700 else ("D" if eff <= 1500 else "E"))))
    if not p_ok: guar_g, merit_g, node_h, n_wt, st = "F", "F", "W", 0.0, "SLASHED_POISON_GRADE_F"
    elif is_repo: guar_g, merit_g, node_h, n_wt, st = "D", "C", "Z", min(p_wt, 0.50), "UNHOSTED_REPO_GRADE_D"
    elif not alive: guar_g, merit_g, node_h, n_wt, st = "E", "D", "Z", max(0.10, round(p_wt - 0.20, 4)), "QUARANTINED_OFFLINE_GRADE_E"
    else:
        guar_g = "A" if (c_tools or pv.get("guarantee_grade") == "A") else "B"
        merit_g, node_h, n_wt = ("B" if wins >= 5 else "C"), "Z", min(0.99, round(p_wt + (0.04 if c_tools else 0.01), 4))
        st = f"VERIFIED_LIVE_GRADE_{guar_g}"
    r_mask = (READINESS_BITS["poison_scan_clean"] if p_ok else 0) | READINESS_BITS["schema_drift_stable"]
    if auth_m == "none" and not is_repo and alive: r_mask |= READINESS_BITS["zero_auth_instant"]
    stamp, u64, u64_hex = MgleNnp64Codec.pack(merit_g, guar_g, lat_g, "B" if x402_ok else "A", node_h, "E", "S" if lat_g in ("A", "B") else "D", r_mask, c_mask)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    dos = {"agent_id": aid, "vendor_domain": extract_vendor_domain(ep), "mgle_nnp_code": stamp, "mgle_nnp_u64_hex": u64_hex, "decoded_switches": MgleNnp64Codec.unpack(u64), "verified_tools": c_tools[:20], "inspected_at_utc": now_iso}
    return {"agent_id": aid, "name": name, "description": desc[:400], "endpoint": ep, "merit_grade": merit_g, "guarantee_grade": guar_g, "latency_grade": lat_g, "mgle_nnp_stamp": stamp, "mgle_nnp_64bit": u64, "domain_mask": c_mask, "avg_latency_ms": eff, "synaptic_weight": n_wt, "wired_tool_count": len(c_tools), "tool_schema_hash_16": h16, "auth_mode": auth_m, "poison_scan_clean": p_ok, "encounter_count": enc, "room_completions": wins, "room_failures": fails, "dossier_json": dos, "audit_status": st, "last_audited_at": now_iso}


def interrogate_live_endpoint(row: Dict[str, Any], timeout_sec: float = 4.0) -> Dict[str, Any]:
    aid, nm, ds, ep = str(row.get("agent_id") or row.get("id") or ""), str(row.get("name") or ""), str(row.get("description") or ""), str(row.get("endpoint") or "").strip()
    if not ep.lower().startswith(("http://", "https://")) or any(h in ep.lower() for h in ("github.com/", "gitlab.com/", "npmjs.com/", "pypi.org/")):
        return build_agent_record_and_dossier(aid, nm or aid, ds, ep, False, None, None, [], "local_stdio_code", prev_record=row)
    ctx = ssl.create_default_context()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "mcp-protocol-version": "2026-07-28", "User-Agent": f"MglennP-RadialScout/{SPEC_VERSION}"}
    ib = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "RadialScout", "version": SPEC_VERSION}}}).encode()
    cold, warm, alive, auth_m, x402_ok, sess, tools = None, None, False, "none", False, None, []
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(ep, data=ib, headers=hdrs, method="POST"), timeout=timeout_sec, context=ctx) as r:
            cold, alive, sess = round((time.perf_counter() - t0) * 1000.0, 2), (200 <= r.status < 400), (r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id"))
    except urllib.error.HTTPError as e:
        cold = round((time.perf_counter() - t0) * 1000.0, 2)
        if e.code in (401, 403): alive, auth_m = True, "bearer_or_oauth_required"
        elif e.code == 402: alive, auth_m, x402_ok = True, "x402_micropayment", True
        elif e.code in (400, 405, 406): alive = True
    except Exception: alive = False
    if alive and auth_m == "none":
        wh = dict(hdrs)
        if sess: wh["Mcp-Session-Id"] = sess
        t1 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(ep, data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode(), headers=wh, method="POST"), timeout=timeout_sec, context=ctx) as r2:
                warm = round((time.perf_counter() - t1) * 1000.0, 2)
                ps = r2.read(131072).decode("utf-8", errors="replace").strip()
                if not ps.startswith("{"):
                    for ln in ps.splitlines():
                        if ln.strip().startswith("data:") and "{" in ln: ps = ln.split("data:", 1)[1].strip(); break
                ro = (json.loads(ps) or {}).get("result")
                if isinstance(ro, dict) and isinstance(ro.get("tools"), list): tools = ro["tools"]
        except Exception: pass
    return build_agent_record_and_dossier(aid, nm or aid, ds, ep, alive, cold, warm, tools, auth_m, None, x402_ok, row)


class DualLaneGateAndTaxLedger:
    def __init__(self, treasury_address: str = DEFAULT_USDC_TREASURY_ADDRESS) -> None:
        self.treasury_address = treasury_address
        self.free_daily_usage: Dict[str, int] = {}
        self.minted_starter_passes: Dict[str, Dict[str, Any]] = {}
        self.pass_remaining_credits: Dict[str, int] = {}
        self.used_payment_tx_hashes: set[str] = set()
        self.active_work_challenges: Dict[str, Dict[str, Any]] = {}
        self.tax_revenue_ledger: List[Dict[str, Any]] = []


    def _sign(self, lane: str, nonce: str, cred: int, exp: int) -> str:
        sig = hmac.new(HMAC_SECRET_KEY, f"rs3.{lane}.{nonce}.{cred}.{exp}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"rs3.{lane}.{nonce}.{cred}.{exp}.{sig}"


    def mint_daily_starter_pass(self, fp: str, label: str = "") -> Tuple[Dict[str, Any], bool]:
        now = datetime.datetime.now(datetime.timezone.utc)
        dk = f"{now.strftime('%Y-%m-%d')}:{fp}"
        ex = self.minted_starter_passes.get(dk)
        if ex and int(ex["expires_unix"]) > int(time.time()):
            return {"status": "EXISTING_DAILY_STARTER_KEY", "pass_token": ex["pass_token"], "header_name": "X-Radial-Pass", "daily_credits": FREE_DAILY_STARTER_CALLS, "remaining_credits": self.pass_remaining_credits.get(ex["nonce"], FREE_DAILY_STARTER_CALLS), "expires_unix": ex["expires_unix"]}, False
        exp = max(int(time.time()) + 3600, int((now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()))
        rem = max(1, FREE_DAILY_STARTER_CALLS - self.free_daily_usage.get(dk, 0))
        nc = secrets.token_hex(8); self.pass_remaining_credits[nc] = rem; tok = self._sign("starter", nc, rem, exp)
        self.minted_starter_passes[dk] = {"nonce": nc, "pass_token": tok, "expires_unix": exp}
        return {"status": "STARTER_KEY_MINTED", "pass_token": tok, "header_name": "X-Radial-Pass", "daily_credits": FREE_DAILY_STARTER_CALLS, "remaining_credits": rem, "expires_unix": exp}, True


    def verify_and_consume_pass(self, token: str) -> Tuple[bool, str, int]:
        pts = (token or "").strip().split(".")
        if len(pts) != 6 or pts[0] != "rs3": return False, "INVALID_PASS", 0
        _, lane, nc, ic_s, ex_s, sig = pts
        try: ic, ex = int(ic_s), int(ex_s)
        except ValueError: return False, "CORRUPT", 0
        if int(time.time()) > ex or not hmac.compare_digest(sig, self._sign(lane, nc, ic, ex).split(".")[-1]): return False, "EXPIRED_OR_BAD_SIG", 0
        rem = self.pass_remaining_credits.get(nc, ic)
        if rem <= 0: return False, "DEPLETED", 0
        self.pass_remaining_credits[nc] = rem - 1
        return True, f"OK_{lane.upper()}_PASS", rem - 1


    def check_or_issue_402_challenge(self, fp: str, tok: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        if tok:
            ok, rsn, rem = self.verify_and_consume_pass(tok)
            if ok: return True, {"access": rsn, "remaining_handshakes": rem}
        dk = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')}:{fp}"
        used = self.free_daily_usage.get(dk, 0)
        if used < FREE_DAILY_STARTER_CALLS:
            self.free_daily_usage[dk] = used + 1
            return True, {"access": "FREE_STARTER_ALLOWANCE", "remaining_free_today": FREE_DAILY_STARTER_CALLS - (used + 1)}
        return False, {"http_status": 402, "error": "PAYMENT_OR_SCOUT_WORK_REQUIRED", "lane_a_x402_usdc": {"network": BASE_MAINNET_CHAIN_ID, "asset_contract": BASE_USDC_CONTRACT, "amount_usdc": CASH_PASS_PRICE_USDC, "pay_to_address": self.treasury_address, "grants_handshakes": CASH_PASS_CREDITS}, "lane_b_compute_scout_duty": {"claim_endpoint": "/v1/work/claim", "submit_endpoint": "/v1/work/submit", "grants_handshakes": WORK_PASS_CREDITS}}


    def settle_x402_usdc_payment(self, tx_hash: str, amount_usdc: float, payer_wallet: str, allow_offline_self_test: bool = False) -> Dict[str, Any]:
        tx = (tx_hash or "").strip().lower()
        if not tx.startswith("0x") or len(tx) != 66 or tx in self.used_payment_tx_hashes: raise ValueError("Invalid or replayed Base tx_hash.")
        if not allow_offline_self_test:
            rpc = os.environ.get("BASE_MAINNET_RPC_URL", "https://mainnet.base.org")
            try:
                with urllib.request.urlopen(urllib.request.Request(rpc, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt", "params": [tx]}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=8) as r:
                    rec = (json.loads(r.read().decode()) or {}).get("result")
            except Exception as e:
                raise ValueError(f"Base RPC error: {e}")
            if not isinstance(rec, dict) or str(rec.get("status", "")).lower() != "0x1": raise ValueError("Tx not confirmed on Base Mainnet.")
            tsig, dest, paid = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef", "0x" + self.treasury_address.lower().replace("0x", "").rjust(64, "0"), 0.0
            for lg in (rec.get("logs") or []):
                if isinstance(lg, dict) and str(lg.get("address") or "").lower() == BASE_USDC_CONTRACT.lower():
                    tp = [str(t).lower() for t in (lg.get("topics") or [])]
                    if len(tp) >= 3 and tp[0] == tsig and tp[2] == dest: paid += int(str(lg.get("data") or "0x0"), 16) / 1_000_000.0
            if paid + 1e-9 < float(CASH_PASS_PRICE_USDC): raise ValueError("No matching USDC transfer to treasury.")
            eff = paid
        else:
            eff = max(float(CASH_PASS_PRICE_USDC), float(amount_usdc or 0.0))
        self.used_payment_tx_hashes.add(tx)
        cred, nc, exp = max(1, int(round(eff / float(CASH_PASS_PRICE_USDC)))) * CASH_PASS_CREDITS, secrets.token_hex(8), int(time.time()) + CASH_PASS_TTL_SECONDS
        self.pass_remaining_credits[nc] = cred
        entry = {"entry_id": f"TAX-{secrets.token_hex(5).upper()}", "received_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "tx_hash": tx, "payer_wallet": payer_wallet, "gross_usdc_received": round(eff, 6), "tax_reserve_30pct_usd": round(eff * TAX_RESERVE_RATIO, 6), "operating_cash_60pct_usd": round(eff * OPERATING_CASH_RATIO, 6), "post_tax_treasury_slice_10pct_usd": round(eff * POST_TAX_TREASURY_SLICE_RATIO, 6), "handshakes_issued": cred}
        self.tax_revenue_ledger.append(entry)
        return {"status": "SETTLED_X402_PASS_ISSUED", "pass_token": self._sign("cash", nc, cred, exp), "handshakes_granted": cred, "expires_unix": exp, "tax_ledger_receipt": entry}


    def issue_scout_work_assignment(self, cands: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        aid, cp = f"WORK-{secrets.token_hex(5).upper()}", f"canary_nonce_{secrets.token_hex(4)}"
        _, exp_h, _ = extract_capabilities_and_hash("canary", [{"name": "radial_canary_ping", "description": "Canary", "inputSchema": {"type": "object", "properties": {cp: {"type": "string"}}, "required": [cp]}}])
        picks = [{"agent_id": r["agent_id"], "endpoint": r["endpoint"]} for r in list(cands)[:3]]
        while len(picks) < 3: picks.append({"agent_id": f"mcp://queue-{len(picks)+1}", "endpoint": f"https://radialswitchboard.com/v1/mock/{len(picks)+1}"})
        cs = {"agent_id": f"mcp://canary-{secrets.token_hex(3)}", "endpoint": f"https://radialswitchboard.com/v1/canary/{cp}"}
        picks.insert(random.randint(0, len(picks)), cs)
        self.active_work_challenges[aid] = {"created_unix": int(time.time()), "canary_agent_id": cs["agent_id"], "expected_canary_hash_16": exp_h, "targets": picks}
        return {"assignment_id": aid, "targets": picks, "expires_in_seconds": 300}


    def verify_scout_work_submission(self, aid: str, results: Sequence[Dict[str, Any]], region: str = "external") -> Dict[str, Any]:
        ch = self.active_work_challenges.pop(aid, None)
        if not ch or int(time.time()) - int(ch["created_unix"]) > 300: return {"status": "REJECTED", "reason": "EXPIRED"}
        by_id = {str(r.get("agent_id")): r for r in results if isinstance(r, dict)}
        if ch["canary_agent_id"] not in by_id or not hmac.compare_digest(str(by_id[ch["canary_agent_id"]].get("tool_schema_hash_16") or "").lower(), ch["expected_canary_hash_16"]):
            return {"status": "REJECTED_CANARY_MISMATCH"}
        nc, exp = secrets.token_hex(8), int(time.time()) + WORK_PASS_TTL_SECONDS
        self.pass_remaining_credits[nc] = WORK_PASS_CREDITS
        return {"status": "VERIFIED_WORK_PASS_ISSUED", "pass_token": self._sign("work", nc, WORK_PASS_CREDITS, exp), "handshakes_granted": WORK_PASS_CREDITS, "expires_unix": exp, "monetary_value_usd": 0.0}


class StandaloneSwitchboardRuntime:
    def __init__(self, hydrate_external: bool = True, start_background_scouts: bool = True) -> None:
        self.hydrate_external = hydrate_external
        self.pool_by_id: Dict[str, Dict[str, Any]] = {}
        self.gate = DualLaneGateAndTaxLedger(DEFAULT_USDC_TREASURY_ADDRESS)
        self.appeals_log: List[Dict[str, Any]] = []
        self.redeemed_tickets: set[str] = set()
        self._lock = threading.Lock()
        self.crawl_cursor: Dict[str, Any] = {"registry_cursor": "", "gh_page": 1}
        self.telemetry: Dict[str, Any] = {"total_external_uses": 0, "external_agent_calls": 0, "mcp_jsonrpc_calls": 0, "rest_matchmake_calls": 0, "ai_beacon_discovery_pulls": 0, "room_handshakes_completed": 0, "starter_keys_minted": 0, "outcome_reports_verified": 0, "scout_sweeps_completed": 0, "last_scout_sweep_utc": None, "scout_currently_running": False}
        if hydrate_external:
            self._hydrate()
            self._load_telemetry()
        if hydrate_external and start_background_scouts:
            threading.Thread(target=self._daemon, daemon=True).start()


    def _recompute(self) -> int:
        self.telemetry["total_external_uses"] = int(self.telemetry.get("external_agent_calls") or 0) + int(self.telemetry.get("ai_beacon_discovery_pulls") or 0) + int(self.telemetry.get("room_handshakes_completed") or 0)
        return self.telemetry["total_external_uses"]


    def record_event(self, field: str, ext_call: bool = False) -> None:
        with self._lock:
            self.telemetry[field] = int(self.telemetry.get(field) or 0) + 1
            if ext_call: self.telemetry["external_agent_calls"] = int(self.telemetry.get("external_agent_calls") or 0) + 1
            self._recompute()
        if self.hydrate_external: threading.Thread(target=self._save_telemetry, daemon=True).start()


    def _sb_creds(self) -> Tuple[str, str]:
        u = (os.environ.get("SUPABASE_URL") or os.environ.get("RADIAL_SUPABASE_URL") or "").strip().rstrip("/")
        k = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
        return u, k


    def _load_telemetry(self) -> None:
        ks = ("external_agent_calls", "mcp_jsonrpc_calls", "rest_matchmake_calls", "ai_beacon_discovery_pulls", "room_handshakes_completed", "starter_keys_minted", "outcome_reports_verified", "scout_sweeps_completed")
        if os.path.isfile(TELEMETRY_LOCAL_PATH):
            try:
                loc = json.loads(open(TELEMETRY_LOCAL_PATH).read())
                for k in ks:
                    if isinstance(loc.get(k), int) and loc[k] > self.telemetry.get(k, 0): self.telemetry[k] = loc[k]
            except Exception: pass
        u, k = self._sb_creds()
        if u and k:
            try:
                with urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_crawler_state?source_key=eq.{TELEMETRY_SUPABASE_KEY}&select=*", headers={"apikey": k, "Authorization": f"Bearer {k}"}), timeout=8) as r:
                    rows = json.loads(r.read().decode())
                if rows and str(rows[0].get("last_cursor") or "").startswith("{"):
                    rem = json.loads(rows[0]["last_cursor"])
                    for kx in ks:
                        if isinstance(rem.get(kx), int) and rem[kx] > self.telemetry.get(kx, 0): self.telemetry[kx] = rem[kx]
            except Exception: pass
        self._recompute()


    def _save_telemetry(self) -> None:
        snap = {k: self.telemetry.get(k) for k in ("total_external_uses", "external_agent_calls", "mcp_jsonrpc_calls", "rest_matchmake_calls", "ai_beacon_discovery_pulls", "room_handshakes_completed", "starter_keys_minted", "outcome_reports_verified", "scout_sweeps_completed")}
        try: open(TELEMETRY_LOCAL_PATH, "w").write(json.dumps(snap))
        except Exception: pass
        u, k = self._sb_creds()
        if u and k:
            row = [{"source_key": TELEMETRY_SUPABASE_KEY, "last_cursor": json.dumps(snap, separators=(",", ":")), "last_page": 1, "total_discovered": int(snap.get("total_external_uses") or 0)}]
            try: urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_crawler_state?on_conflict=source_key", data=json.dumps(row).encode(), headers={"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}, method="POST"), timeout=8).close()
            except Exception: pass
# --- RADIAL_PY_CONTINUATION ---
        u, k = self._sb_creds()
        if not u or not k: return
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_agent_phonebook?select=*&limit=1000", headers={"apikey": k, "Authorization": f"Bearer {k}"}), timeout=10) as r:
                for row in (json.loads(r.read().decode()) or []):
                    aid = str(row.get("agent_id") or "").strip()
                    if aid and aid not in SYNTHETIC_LEGACY_IDS and row.get("endpoint"):
                        self.pool_by_id[aid] = row if row.get("mgle_nnp_64bit") else build_agent_record_and_dossier(aid, str(row.get("name") or aid), str(row.get("description") or ""), str(row["endpoint"]), row.get("guarantee_grade") in ("A", "B"), row.get("avg_latency_ms"), row.get("avg_latency_ms"), [], prev_record=row)
        except Exception: pass


    def _upsert_sb(self, rows: List[Dict[str, Any]]) -> None:
        u, k = self._sb_creds()
        if not u or not k or not rows: return
        min_r = [{"agent_id": r["agent_id"], "name": r["name"], "description": r["description"], "endpoint": r["endpoint"], "guarantee_grade": r["guarantee_grade"], "latency_grade": r["latency_grade"], "mgle_nnp_stamp": r["mgle_nnp_stamp"], "mgle_nnp_64bit": r["mgle_nnp_64bit"], "domain_mask": r["domain_mask"], "avg_latency_ms": r["avg_latency_ms"], "synaptic_weight": r["synaptic_weight"], "last_audited_at": r["last_audited_at"]} for r in rows]
        try: urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_agent_phonebook?on_conflict=agent_id", data=json.dumps(min_r).encode(), headers={"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}, method="POST"), timeout=12).close()
        except Exception: pass


    def verify_outcome(self, aid: str, tkt: str, ok: bool, obs_ms: Optional[float] = None) -> Dict[str, Any]:
        valid, rsn = verify_execution_ticket(aid, tkt)
        if not valid or tkt in self.redeemed_tickets: return {"agent_id": aid, "ticket_valid": False, "reason": rsn, "sabotage_blocked": True, "quarantined": False}
        rec = self.pool_by_id.get(aid)
        if not rec: return {"agent_id": aid, "ticket_valid": True, "quarantined": False}
        self.redeemed_tickets.add(tkt); self.record_event("outcome_reports_verified")
        if ok:
            rec["room_completions"] = int(rec.get("room_completions") or 0) + 1
            rec["synaptic_weight"] = min(0.99, round(float(rec.get("synaptic_weight") or 0.80) + 0.03, 4))
            upd = build_agent_record_and_dossier(rec["agent_id"], rec["name"], rec.get("description", ""), rec["endpoint"], True, rec.get("avg_latency_ms"), obs_ms or rec.get("avg_latency_ms"), [], rec.get("auth_mode", "none"), prev_record=rec)
            self.pool_by_id[aid] = upd
            return {"agent_id": aid, "ticket_valid": True, "sabotage_blocked": False, "quarantined": False, "updated_synaptic_weight": upd["synaptic_weight"]}
        probed = interrogate_live_endpoint(rec)
        alive = probed.get("guarantee_grade") in ("A", "B")
        self.pool_by_id[aid] = probed
        return {"agent_id": aid, "ticket_valid": True, "independent_probe_alive": alive, "quarantined": not alive}


    def run_live_scout_sweep(self, limit: int = 30) -> Dict[str, Any]:
        with self._lock:
            if self.telemetry["scout_currently_running"]: return {"status": "already_running", "total_pool": len(self.pool_by_id)}
            self.telemetry["scout_currently_running"] = True
        try:
            cands: List[Dict[str, Any]] = []
            try:
                cur = self.crawl_cursor["registry_cursor"]
                url = f"https://registry.modelcontextprotocol.io/v0.1/servers?limit={limit}&version=latest" + (f"&cursor={urllib.parse.quote(cur)}" if cur else "")
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": f"MglennP-RadialScout/{SPEC_VERSION}"}), timeout=12) as r:
                    pl = json.loads(r.read().decode())
                self.crawl_cursor["registry_cursor"] = str((pl.get("metadata") or {}).get("nextCursor") or "")
                for ent in (pl.get("servers") or []):
                    sv = ent.get("server") if isinstance(ent, dict) and isinstance(ent.get("server"), dict) else ent
                    if not isinstance(sv, dict) or not sv.get("name"): continue
                    rem = next((str(x["url"]).strip() for x in (sv.get("remotes") or []) if isinstance(x, dict) and str(x.get("url") or "").startswith("https://")), "")
                    rep = str((sv.get("repository") or {}).get("url") or "").strip() if isinstance(sv.get("repository"), dict) else ""
                    if rem or rep: cands.append({"agent_id": f"mcp://{str(sv['name']).lower()}", "name": str(sv.get("title") or sv["name"]), "description": str(sv.get("description") or "")[:300], "endpoint": rem or rep})
            except Exception: pass
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
                audited = list(ex.map(interrogate_live_endpoint, cands)) if cands else []
            for rec in audited: self.pool_by_id[rec["agent_id"]] = rec
            if audited: self._upsert_sb(audited)
            with self._lock:
                self.telemetry["scout_sweeps_completed"] += 1
                self.telemetry["last_scout_sweep_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if self.hydrate_external: threading.Thread(target=self._save_telemetry, daemon=True).start()
            return {"status": "completed", "probed_count": len(audited), "total_pool": len(self.pool_by_id)}
        finally:
            with self._lock: self.telemetry["scout_currently_running"] = False


    def _daemon(self) -> None:
        time.sleep(1.0)
        while True:
            try: self.run_live_scout_sweep(35)
            except Exception: pass
            time.sleep(900.0)


MCP_SERVER_TOOLS = [
    {"name": "flash_matchmake_agents", "description": "64-bit MGLE-NNP MCP matchmaker (Top-10 varied or mode='crew' 3-agent triad).", "inputSchema": {"type": "object", "properties": {"intent": {"type": "string"}, "capabilities": {"type": "array", "items": {"type": "string"}}, "mode": {"type": "string", "enum": ["top10_varied", "crew"]}, "require_instant_zero_auth": {"type": "boolean"}, "max_latency_grade": {"type": "string"}, "top_k": {"type": "integer"}}}},
    {"name": "get_agent_dossier", "description": "Fetch live 4-point Virginia probe dossier.", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string"}}, "required": ["agent_id"]}},
    {"name": "get_switchboard_telemetry", "description": "Return real pool counts and persistent external usage counters.", "inputSchema": {"type": "object", "properties": {}}},
]


class ThreadingHTTPServerReuse(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def create_http_handler(runtime: StandaloneSwitchboardRuntime):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _bytes(self, code: int, ct: str, raw: bytes) -> None:
            self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Radial-Pass, mcp-protocol-version, Mcp-Session-Id"); self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers(); self.wfile.write(raw)


        def _json(self, code: int, obj: Dict[str, Any]) -> None:
            self._bytes(code, "application/json; charset=utf-8", json.dumps(obj, indent=2).encode("utf-8"))


        def do_OPTIONS(self) -> None: self._bytes(204, "text/plain", b"")


        def _health(self) -> Dict[str, Any]:
            recs = list(runtime.pool_by_id.values())
            ab = sum(1 for r in recs if r.get("guarantee_grade") in ("A", "B"))
            gd = sum(1 for r in recs if r.get("guarantee_grade") == "D")
            ge = sum(1 for r in recs if r.get("guarantee_grade") == "E")
            runtime._recompute()
            return {"status": "ok", "service": f"MglennP Radial Switchboard (Spec Rev {SPEC_VERSION})", "spec_version": SPEC_VERSION, "contact_email": CONTACT_EMAIL, "github_repository": PUBLIC_GITHUB_REPO, "synthetic_seed_rows": 0, "mcp_endpoint": "https://radialswitchboard.com/mcp", "stdio_bridge_script": "https://radialswitchboard.com/mcp_stdio_bridge.py", "starter_key_endpoint": "https://radialswitchboard.com/v1/keys/starter", "usdc_treasury_base": runtime.gate.treasury_address, "total_unsorted_pool": len(recs), "live_callable_ab": ab, "offline_code_d": gd, "quarantined_e": ge, "total_external_uses": runtime.telemetry["total_external_uses"], "telemetry": dict(runtime.telemetry), "usdc_settled_usd": round(sum(float(x.get("gross_usdc_received") or 0.0) for x in runtime.gate.tax_revenue_ledger), 6), "tax_reserved_usd": round(sum(float(x.get("tax_reserve_30pct_usd") or 0.0) for x in runtime.gate.tax_revenue_ledger), 6)}


        def do_GET(self) -> None:
            pr = urllib.parse.urlparse(self.path); p = pr.path.rstrip("/") or "/"; qs = urllib.parse.parse_qs(pr.query)
            ui = (qs.get("ui_observer") or [""])[0].lower() in ("1", "true")
            if p in ("/", "/directory"):
                f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "radial_agent_directory_explorer.html")
                self._bytes(200, "text/html; charset=utf-8", open(f, "rb").read() if os.path.isfile(f) else f"<h1>Radial Switchboard {SPEC_VERSION}</h1>".encode())
            elif p == "/mcp_stdio_bridge.py":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls")
                self._bytes(200, "text/x-python; charset=utf-8", MCP_STDIO_BRIDGE_SOURCE.encode())
            elif p == "/llms.txt":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls")
                self._bytes(200, "text/plain; charset=utf-8", f"# MglennP Radial Switchboard -- Spec Rev {SPEC_VERSION}\nContact: {CONTACT_EMAIL} | Virginia, USA (US-EAST4)\nMCP Hook: POST https://radialswitchboard.com/mcp\nStarter Key: POST https://radialswitchboard.com/v1/keys/starter\nTreasury: {runtime.gate.treasury_address}\n".encode())
            elif p in ("/mcp/server-card", "/.well-known/ai-catalog.json"):
                if not ui: runtime.record_event("ai_beacon_discovery_pulls")
                c = {"$schema": "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json", "name": "com.radialswitchboard/matchmaker", "version": SPEC_VERSION, "contact": {"name": "MglennP", "email": CONTACT_EMAIL}, "supportedProtocolVersions": ["2026-07-28", "2025-06-18"], "remotes": [{"type": "streamable-http", "url": "https://radialswitchboard.com/mcp"}]}
                self._json(200, {"servers": [c]} if p == "/.well-known/ai-catalog.json" else c)
            elif p in ("/openapi.json", "/.well-known/mcp.json"):
                if not ui: runtime.record_event("ai_beacon_discovery_pulls")
                self._json(200, {"openapi": "3.1.0", "info": {"title": "MglennP Radial Switchboard", "version": SPEC_VERSION, "contact": {"email": CONTACT_EMAIL}}, "mcp_streamable_http": "https://radialswitchboard.com/mcp", "synthetic_seed_rows": 0})
            elif p == "/v1/health": self._json(200, self._health())
            elif p == "/v1/benchmark":
                recs = list(runtime.pool_by_id.values())
                s = sorted(float(flash_unsorted_pool(recs, ["sql", "database"], max_lat="E")["single_pass_flash_ms"]) for _ in range(10))
                self._json(200, {"spec_version": SPEC_VERSION, "agents_scanned": len(recs), "default_top_k": DEFAULT_FLASH_TOP_K, "p50_bitwise_ms": s[len(s)//2] if s else 0.0})
            elif p == "/v1/directory/live":
                recs = sorted(runtime.pool_by_id.values(), key=lambda x: (0 if x.get("guarantee_grade") == "A" else 1, float(x.get("avg_latency_ms") or 99999.0)))
                self._json(200, {"spec_version": SPEC_VERSION, "contact_email": CONTACT_EMAIL, "synthetic_seed_rows": 0, "total_agents": len(recs), "appeals": runtime.appeals_log, "tax_ledger": runtime.gate.tax_revenue_ledger, "agents": recs[:250]})
            elif p == "/v1/appeals": self._json(200, {"count": len(runtime.appeals_log), "appeals": runtime.appeals_log})
            elif p == "/v1/matchmake":
                if not ui: runtime.record_event("rest_matchmake_calls", ext_call=True)
                self._json(200, flash_unsorted_pool(list(runtime.pool_by_id.values()), infer_capabilities_from_intent((qs.get("intent") or ["mcp"])[0]), mode=(qs.get("mode") or ["top10_varied"])[0]))
            elif p.startswith("/v1/dossier/"):
                rec = runtime.pool_by_id.get(urllib.parse.unquote(p[len("/v1/dossier/"):]))
                self._json(200 if rec else 404, (rec.get("dossier_json") or rec) if rec else {"error": "Not found"})
            else: self._json(404, {"error": "Route not found"})


        def do_POST(self) -> None:
            p = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
            ln = int(self.headers.get("Content-Length") or 0)
            try: body = json.loads(self.rfile.read(min(ln, 524288)).decode("utf-8", errors="replace")) if ln > 0 else {}
            except Exception: body = {}
            ip = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or (self.client_address[0] if self.client_address else "anon")
            if p == "/mcp":
                rid, m, prm = body.get("id", 1), str(body.get("method") or ""), (body.get("params") if isinstance(body.get("params"), dict) else {})
                if m == "notifications/initialized": self._bytes(202, "application/json", b"")
# --- RADIAL_PY_CONTINUATION ---
                elif m == "initialize": self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": str(prm.get("protocolVersion") or "2026-07-28"), "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "MglennP Radial Switchboard", "version": SPEC_VERSION}}})
                elif m == "ping": self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {}})
                elif m == "tools/list": self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {"tools": MCP_SERVER_TOOLS}})
                elif m == "tools/call":
                    runtime.record_event("mcp_jsonrpc_calls", ext_call=True)
                    tn, ag = str(prm.get("name") or ""), (prm.get("arguments") if isinstance(prm.get("arguments"), dict) else {})
                    if tn == "flash_matchmake_agents": out = flash_unsorted_pool(list(runtime.pool_by_id.values()), ag.get("capabilities") or infer_capabilities_from_intent(str(ag.get("intent") or "")), bool(ag.get("require_instant_zero_auth", False)), str(ag.get("max_latency_grade", "E")), top_k=int(ag.get("top_k", DEFAULT_FLASH_TOP_K)), mode=str(ag.get("mode") or "top10_varied"))
                    elif tn == "get_agent_dossier": out = runtime.pool_by_id.get(str(ag.get("agent_id") or "")) or {"error": "Not found"}
                    elif tn == "get_switchboard_telemetry": out = self._health()
                    else: self._json(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Unknown tool"}}); return
                    self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(out)}], "structuredContent": out, "isError": False}})
                else: self._json(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Unsupported"}})
            elif p == "/v1/keys/starter":
                obj, nw = runtime.gate.mint_daily_starter_pass(ip, str(body.get("agent_label") or "visitor-hook"))
                if nw: runtime.record_event("starter_keys_minted")
                self._json(200, obj)
            elif p.startswith("/v1/canary/"):
                cp = p[len("/v1/canary/"):].strip()
                self._json(200, {"jsonrpc": "2.0", "id": body.get("id", 1), "result": {"tools": [{"name": "radial_canary_ping", "description": "Canary", "inputSchema": {"type": "object", "properties": {cp: {"type": "string"}}, "required": [cp]}}]}})
            elif p in ("/v1/flash", "/v1/matchmake"):
                if not bool(body.get("ui_observer", False)): runtime.record_event("rest_matchmake_calls", ext_call=True)
                self._json(200, flash_unsorted_pool(list(runtime.pool_by_id.values()), body.get("capabilities") or infer_capabilities_from_intent(str(body.get("intent") or "")), bool(body.get("require_instant_zero_auth", False)), str(body.get("max_latency_grade", "E")), top_k=int(body.get("top_k", DEFAULT_FLASH_TOP_K)), mode=str(body.get("mode") or "top10_varied")))
            elif p == "/v1/directory/crawl": self._json(200, runtime.run_live_scout_sweep(int(body.get("limit", 30))))
            elif p == "/v1/appeals":
                prb = interrogate_live_endpoint({"agent_id": str(body.get("agent_id") or f"mcp://sub-{secrets.token_hex(3)}"), "name": str(body.get("agent_id") or body.get("endpoint") or ""), "description": str(body.get("reason") or ""), "endpoint": str(body.get("endpoint") or "")})
                runtime.pool_by_id[prb["agent_id"]] = prb; runtime._upsert_sb([prb])
                ar = {"id": f"APP-{len(runtime.appeals_log)+1}", "slug": prb["agent_id"], "endpoint": prb["endpoint"], "status": prb["audit_status"]}
                runtime.appeals_log.insert(0, ar); self._json(200, {"appeal": ar, "updated_record": prb})
            elif p == "/v1/work/claim": self._json(200, runtime.gate.issue_scout_work_assignment(list(runtime.pool_by_id.values())))
            elif p == "/v1/work/submit":
                res = runtime.gate.verify_scout_work_submission(str(body.get("assignment_id") or ""), body.get("results") or [], str(body.get("region") or "external"))
                self._json(200 if res.get("status") == "VERIFIED_WORK_PASS_ISSUED" else 400, res)
            elif p == "/v1/x402/settle":
                try: self._json(200, runtime.gate.settle_x402_usdc_payment(str(body.get("tx_hash") or ""), float(body.get("amount_usdc") or 0.0), str(body.get("payer_wallet") or ""), False))
                except ValueError as err: self._json(400, {"error": str(err)})
            elif p == "/v1/room/handshake":
                tok = self.headers.get("X-Radial-Pass") or body.get("pass_token")
                ok_g, gi = runtime.gate.check_or_issue_402_challenge(ip, tok)
                if not ok_g: self._json(402, gi); return
                w = runtime.pool_by_id.get(str(body.get("target_agent_id") or ""))
                if not w: self._json(404, {"error": "Unknown target agent"}); return
                t0 = time.perf_counter()
                try:
                    with urllib.request.urlopen(urllib.request.Request(str(w["endpoint"]), data=json.dumps(body.get("payload") or {}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=8) as r:
                        wr = json.loads(r.read(262144).decode("utf-8", errors="replace"))
                    ok_w = isinstance(wr, dict) and "error" not in wr
                except Exception as exc:
                    wr, ok_w = {"error": str(exc)}, False
                if ok_w: runtime.record_event("room_handshakes_completed")
                self._json(200 if ok_w else 502, {"http_status": 200 if ok_w else 502, "room_witness_verdict": "DELIVERY_VERIFIED" if ok_w else "WORKER_CONTRACT_FAILURE", "measured_room_ms": round((time.perf_counter()-t0)*1000.0, 2), "caller_gate": gi, "worker_response": wr})
            elif p == "/v1/outcome":
                lv = body.get("observed_latency_ms")
                out = runtime.verify_outcome(str(body.get("agent_id") or ""), str(body.get("execution_ticket") or ""), bool(body.get("outcome_success", True)), float(lv) if isinstance(lv, (int, float)) else None)
                self._json(200 if out.get("ticket_valid") else 403, out)
            else: self._json(404, {"error": "Route not found"})
        def log_message(self, fmt: str, *args: Any) -> None: return
    return Handler
def run_self_test() -> int:
    rt = StandaloneSwitchboardRuntime(hydrate_external=False, start_background_scouts=False)
    assert len(rt.pool_by_id) == 0 and rt.telemetry["total_external_uses"] == 0
    defs = [("test://v0", "Postgres SQL", "postgres sql database python", "https://n0.v0.example/mcp"), ("test://v1", "SEC Finance", "sec finance search rag", "https://n1.v1.example/mcp"), ("test://v2", "Math Audit", "math verify security audit", "https://n2.v2.example/mcp")]
    for i in range(12):
        aid, nm, ds, ep = defs[i] if i < 3 else (f"test://v{i}", f"SQL {i}", "postgres sql database", f"https://n{i}.v{i}.example/mcp")
        rt.pool_by_id[aid] = build_agent_record_and_dossier(aid, nm, ds, ep, True, 80.0, 45.0 + i, [{"name": f"t_{i}", "description": ds, "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}])
    srv = ThreadingHTTPServerReuse(("127.0.0.1", 0), create_http_handler(rt))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        h = json.loads(urllib.request.urlopen(f"{base}/v1/health", timeout=5).read().decode())
        assert h["synthetic_seed_rows"] == 0 and h["total_external_uses"] == 0 and h["contact_email"] == CONTACT_EMAIL
        ur = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/flash", data=json.dumps({"capabilities": ["sql"], "ui_observer": True}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert ur["finalist_count"] == 10 and json.loads(urllib.request.urlopen(f"{base}/v1/health", timeout=5).read().decode())["total_external_uses"] == 0
        cr = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/flash", data=json.dumps({"capabilities": ["sql", "finance_data", "math_verify"], "mode": "crew", "ui_observer": True}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert cr["finalist_count"] == 3 and cr["crew_manifest"]["provider_independence_verified"] is True
        kr = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/keys/starter", data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert kr["pass_token"].startswith("rs3.starter.")
        mr = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "flash_matchmake_agents", "arguments": {"intent": "postgres sql"}}}).encode(), headers={"Content-Type": "application/json", "X-Radial-Pass": kr["pass_token"]}, method="POST"), timeout=5).read().decode())
        tkt, tid = mr["result"]["structuredContent"]["finalists"][0]["execution_ticket"], mr["result"]["structuredContent"]["finalists"][0]["agent_id"]
        assert CONTACT_EMAIL in urllib.request.urlopen(f"{base}/llms.txt", timeout=5).read().decode()
        assert "radialswitchboard.com/mcp" in urllib.request.urlopen(f"{base}/mcp_stdio_bridge.py", timeout=5).read().decode()
        assert json.loads(urllib.request.urlopen(f"{base}/v1/health", timeout=5).read().decode())["total_external_uses"] == 3
        ok_o = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/outcome", data=json.dumps({"agent_id": tid, "execution_ticket": tkt, "outcome_success": True}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert ok_o["ticket_valid"] is True
    finally:
        srv.shutdown(); srv.server_close()
    print(f"[PASS] Crisp Spec {SPEC_VERSION} Bridged Engine 100% Verified.")
    return 0
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true"); ap.add_argument("--crawl-once", action="store_true"); ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = ap.parse_args()
    if args.crawl_once:
        print(json.dumps(StandaloneSwitchboardRuntime(False, False).run_live_scout_sweep(35), indent=2)); return 0
    if args.serve:
        rt = StandaloneSwitchboardRuntime(True, True)
        with ThreadingHTTPServerReuse(("0.0.0.0", args.port), create_http_handler(rt)) as srv:
            print(f"Radial Switchboard {SPEC_VERSION} active on 0.0.0.0:{args.port}"); srv.serve_forever()
        return 0
    return run_self_test()
if __name__ == "__main__":
    raise SystemExit(main())
