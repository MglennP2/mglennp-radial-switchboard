#!/usr/bin/env python3
"""MglennP Radial Switchboard -- Spec Rev 3.5.0 (Autonomous Global Scale + A2A/MCP + x402 V2 + Genesis Hall) | support@radialswitchboard.com"""
from __future__ import annotations

import argparse, base64, concurrent.futures, csv, datetime, hashlib, hmac, http.server
import io, ipaddress, json, os, random, re, secrets, socketserver, ssl, threading, time
import urllib.error, urllib.parse, urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

SPEC_VERSION = "3.5.8"
SCHEMA_NIBBLE = 0x3
CONTACT_EMAIL = "support@radialswitchboard.com"
PUBLIC_GITHUB_REPO = "https://github.com/MglennP2/mglennp-radial-switchboard"
DEFAULT_USDC_TREASURY_ADDRESS = os.environ.get("RADIAL_USDC_TREASURY_ADDRESS", "0x24b1a09b489c67c3e43f7cd1f3023aef544104fd")
BASE_MAINNET_CHAIN_ID, BASE_USDC_CONTRACT = "eip155:8453", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_FLASH_TOP_K, MAX_FLASH_TOP_K = 10, 25
CASH_PASS_PRICE_USDC, CASH_PASS_ATOMIC_USDC, CASH_PASS_CREDITS, CASH_PASS_TTL_SECONDS = "0.01", "10000", 100, 86400 * 30
WORK_ASSIGNMENT_SIZE, WORK_PASS_CREDITS, WORK_PASS_TTL_SECONDS = 4, 20, 3600
FREE_DAILY_STARTER_CALLS, EXECUTION_TICKET_TTL_SECONDS = 15, 900
TAX_RESERVE_RATIO, OPERATING_CASH_RATIO, POST_TAX_TREASURY_SLICE_RATIO = 0.30, 0.60, 0.10

_RAW_HMAC_ENV = (os.environ.get("RADIAL_HMAC_SECRET") or os.environ.get("OPERATOR_KEY") or "").strip()
HMAC_SECRET_KEY = _RAW_HMAC_ENV.encode("utf-8") if _RAW_HMAC_ENV else (secrets.token_bytes(32) if os.environ.get("K_SERVICE") else b"radial-switchboard-local-selftest-only-hmac")
HMAC_SECRET_MODE = "ENV_LOCKED" if _RAW_HMAC_ENV else ("CLOUD_RUN_EPHEMERAL_AUTO" if os.environ.get("K_SERVICE") else "LOCAL_SELFTEST_ONLY")

TELEMETRY_LOCAL_PATH = "/tmp/radial_telemetry_state.json"
TELEMETRY_SUPABASE_KEY = "switchboard_telemetry_v3"
CRAWL_CURSOR_SUPABASE_KEY = "mcp_registry_v0_1_cursor"
MAX_HYDRATE_ROWS = 100000

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
    "math_verify": ("math", "calculus", "solver", "verify", "verification", "validate", "validation", "reconcile", "reconciliation", "proof", "statistics", "symbolic"),
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
UNWIRED_STUB_PAT = re.compile(r"\b(not\s+wired|unwired|not\s+implemented|coming\s+soon|placeholder\s+only|mock\s+only|todo\s+stub)\b", re.I)
X402_PAID_PAT = re.compile(r"\b(paid\s+per\s+call|pay\s+per\s+call|over\s+x402|x402\s+payment|requires\s+x402|micropayment\s+required|buy_credits|usdc\s+credits?|usdc\s+per\s+call|prepaid\s+credits?|top\s+up\s+credits?|payment\s+gated)\b", re.I)
OAUTH_OR_KEY_PAT = re.compile(r"\b(with\s+oauth|oauth2?\s+required|requires?\s+oauth|requires?\s+api\s+key|api[_\s-]?key\s+required|bearer\s+token\s+required|sign\s+in\s+to\s+use|login\s+required|requires?\s+authentication)\b", re.I)
AUTH_INPUT_KEYS = {"api_key", "apikey", "access_token", "auth_token", "bearer_token", "oauth_token", "secret_key", "session_token", "jwt_token"}
SIDE_EFFECT_VERBS = {"buy", "call", "create", "delete", "drop", "execute", "insert", "mint", "modify", "order", "pay", "post", "publish", "purchase", "put", "remove", "run", "send", "settle", "submit", "swap", "trade", "transfer", "trigger", "update", "upload", "write"}
READ_ONLY_VERBS = {"analyze", "check", "compute", "convert", "count", "decode", "describe", "detect", "estimate", "eval", "explain", "extract", "fetch", "find", "forecast", "format", "get", "inspect", "list", "lookup", "parse", "ping", "preview", "query", "read", "resolve", "retrieve", "scan", "search", "select", "show", "simulate", "solve", "status", "summarize", "validate", "verify"}
STOPWORDS_INTENT = {"a", "an", "and", "agent", "api", "by", "call", "data", "for", "from", "get", "in", "into", "is", "it", "mcp", "mode", "need", "of", "on", "or", "server", "the", "to", "tool", "tools", "use", "using", "with"}

def _tokenize_words(txt: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", (txt or "").lower()) if len(w) >= 2]

def _kw_matches_text(kw: str, low_text: str, word_set: set) -> bool:
    k = kw.lower().strip()
    if " " in k or "_" in k:
        return k in low_text
    if len(k) <= 4:
        return k in word_set
    return any(w == k or (len(w) >= len(k) and w.startswith(k)) for w in word_set)

def classify_tool_entry(tn: str, td: str, pr: Dict[str, Any], rq: List[Any], ann: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw_combo = f"{tn} {td}"
    callable_now = not bool(UNWIRED_STUB_PAT.search(raw_combo))
    ann_d = ann if isinstance(ann, dict) else {}
    if isinstance(ann_d.get("readOnlyHint"), bool):
        eff_cls = "read_only" if ann_d["readOnlyHint"] else "side_effecting"
    else:
        toks = [x for x in re.split(r"[^a-z0-9]+", tn.lower()) if x]
        first_v = toks[0] if toks else ""
        if first_v in ("run", "execute", "eval") and any(x in toks for x in ("sql", "query", "select", "read", "check", "verify", "math")):
            eff_cls = "read_only"
        elif any(t in SIDE_EFFECT_VERBS for t in toks):
            eff_cls = "side_effecting"
        elif any(t in READ_ONLY_VERBS for t in toks):
            eff_cls = "read_only"
        else:
            eff_cls = "side_effecting" if X402_PAID_PAT.search(raw_combo) else "read_only"
    clean_inputs = {}
    for k, v in list((pr or {}).items())[:12]:
        if isinstance(v, dict):
            tp_v = v.get("type", "any")
            if isinstance(tp_v, list):
                tp_s = "|".join(str(x) for x in tp_v[:3])
            else:
                tp_s = str(tp_v or "any")
            clean_inputs[str(k)[:36]] = tp_s[:28]
        else:
            clean_inputs[str(k)[:36]] = str(v)[:28]
    for rk in (rq or [])[:12]:
        rk_s = str(rk)[:36]
        if rk_s and rk_s not in clean_inputs:
            clean_inputs[rk_s] = "any"
    return {
        "tool": tn[:64],
        "summary": td[:180],
        "inputs": clean_inputs,
        "required": [str(r)[:36] for r in (rq or [])[:12]],
        "callable_now": callable_now,
        "effect_class": eff_cls,
        "untrusted_third_party_text": True,
    }
GRADE_TO_NIBBLE = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
NIBBLE_TO_GRADE = {v: k for k, v in GRADE_TO_NIBBLE.items()}
NODE_TO_NIBBLE = {"Z": 1, "S": 2, "B": 3, "A": 4, "H": 5, "W": 9}
NIBBLE_TO_NODE = {v: k for k, v in NODE_TO_NIBBLE.items()}
NEIGHBOR_TO_NIBBLE = {"E": 1, "A": 2, "O": 3, "G": 4, "W": 5, "U": 6, "P": 7}
NIBBLE_TO_NEIGHBOR = {v: k for k, v in NEIGHBOR_TO_NIBBLE.items()}
PREF_TO_NIBBLE = {"S": 1, "C": 2, "N": 3, "D": 4, "M": 5}
NIBBLE_TO_PREF = {v: k for k, v in PREF_TO_NIBBLE.items()}
MULTI_PART_TLDS = {"co.uk", "org.uk", "com.au", "co.jp", "com.br", "co.in"}
COMPUTE_MASK = CAPABILITY_BITS["code_exec"] | CAPABILITY_BITS["sql"] | CAPABILITY_BITS["database"] | CAPABILITY_BITS["cloud_devops"]
VERIFY_MASK = CAPABILITY_BITS["math_verify"] | CAPABILITY_BITS["security_audit"] | CAPABILITY_BITS["schema_transform"] | CAPABILITY_BITS["legal_tax"]
SYNTHETIC_LEGACY_IDS = {
    "mcp://neon-fast-sql", "mcp://supabase-pg", "mcp://turso-libsql", "mcp://motherduck-olap", "mcp://clickhouse-col",
    "mcp://cockroach-tx", "mcp://planetscale-vt", "mcp://timescale-ts", "mcp://tembo-vec", "mcp://crunchy-pg",
    "mcp://e2b-firecracker-py", "mcp://semgrep-ast", "mcp://constellation-sec", "mcp://base-usdc-x402", "mcp://us-east-sql-validator", "a2a://deep-contract-auditor",
}

EU_COUNTRIES = {"GB", "DE", "FR", "NL", "IE", "ES", "IT", "SE", "NO", "FI", "DK", "PL", "CH", "AT", "BE", "PT", "CZ"}
APAC_COUNTRIES = {"JP", "SG", "AU", "NZ", "KR", "IN", "TW", "HK", "MY", "TH", "ID", "PH", "VN"}

# Pure-Stdlib RFC 8032 Ed25519 + W3C did:key Verifier for Genesis Apprentice Enrollment
_ED_P = (1 << 255) - 19
_ED_L = (1 << 252) + 27742317777372353535851937790883648493
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: idx for idx, ch in enumerate(_B58_ALPHABET)}

def _ed_xrecover(y: int) -> int:
    xx = ((y * y - 1) * pow(_ED_D * y * y + 1, _ED_P - 2, _ED_P)) % _ED_P
    x = pow(xx, (_ED_P + 3) // 8, _ED_P)
    if (x * x - xx) % _ED_P != 0: x = (x * _ED_I) % _ED_P
    if (x * x - xx) % _ED_P != 0: raise ValueError("Not on Ed25519 curve")
    return (_ED_P - x) if (x & 1) else x

_ED_BY = (4 * pow(5, _ED_P - 2, _ED_P)) % _ED_P
_ED_BX = _ed_xrecover(_ED_BY)
_ED_B = (_ED_BX, _ED_BY, 1, (_ED_BX * _ED_BY) % _ED_P)

def _ed_add(p1: Tuple[int, int, int, int], p2: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    x1, y1, z1, t1 = p1; x2, y2, z2, t2 = p2
    a, b = ((y1 - x1) * (y2 - x2)) % _ED_P, ((y1 + x1) * (y2 + x2)) % _ED_P
    c, d = (t1 * 2 * _ED_D * t2) % _ED_P, (z1 * 2 * z2) % _ED_P
    e, f, g, h = (b - a) % _ED_P, (d - c) % _ED_P, (d + c) % _ED_P, (b + a) % _ED_P
    return (e * f) % _ED_P, (g * h) % _ED_P, (f * g) % _ED_P, (e * h) % _ED_P

def _ed_scalarmult(k: int, pt: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    res, cur = (0, 1, 1, 0), pt
    while k > 0:
        if k & 1: res = _ed_add(res, cur)
        cur = _ed_add(cur, cur); k >>= 1
    return res

def _ed_encode(pt: Tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = pt; zi = pow(z, _ED_P - 2, _ED_P)
    xp, yp = (x * zi) % _ED_P, (y * zi) % _ED_P
    return (yp | ((xp & 1) << 255)).to_bytes(32, "little")

def _ed_decode(raw32: bytes) -> Tuple[int, int, int, int]:
    if len(raw32) != 32: raise ValueError("Bad pubkey len")
    val = int.from_bytes(raw32, "little"); y, sign = val & ((1 << 255) - 1), (val >> 255) & 1
    if y >= _ED_P: raise ValueError("Non-canonical y")
    x = _ed_xrecover(y)
    if x == 0 and sign == 1: raise ValueError("Negative zero")
    if (x & 1) != sign: x = _ED_P - x
    return x, y, 1, (x * y) % _ED_P

def ed25519_pubkey(seed32: bytes) -> bytes:
    d = hashlib.sha512(seed32).digest()
    a = (int.from_bytes(d[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    return _ed_encode(_ed_scalarmult(a, _ED_B))

def ed25519_sign(seed32: bytes, msg: bytes) -> bytes:
    d = hashlib.sha512(seed32).digest()
    a = (int.from_bytes(d[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    pub = _ed_encode(_ed_scalarmult(a, _ED_B))
    r = int.from_bytes(hashlib.sha512(d[32:64] + msg).digest(), "little") % _ED_L
    rb = _ed_encode(_ed_scalarmult(r, _ED_B))
    k = int.from_bytes(hashlib.sha512(rb + pub + msg).digest(), "little") % _ED_L
    return rb + ((r + k * a) % _ED_L).to_bytes(32, "little")

def ed25519_verify(pub32: bytes, msg: bytes, sig64: bytes) -> bool:
    if len(pub32) != 32 or len(sig64) != 64: return False
    s = int.from_bytes(sig64[32:64], "little")
    if s >= _ED_L: return False
    try: a_pt, r_pt = _ed_decode(pub32), _ed_decode(sig64[:32])
    except ValueError: return False
    k = int.from_bytes(hashlib.sha512(sig64[:32] + pub32 + msg).digest(), "little") % _ED_L
    return _ed_encode(_ed_scalarmult(8 * s, _ED_B)) == _ed_encode(_ed_scalarmult(8, _ed_add(r_pt, _ed_scalarmult(k, a_pt))))

def pubkey_to_did_key(pub32: bytes) -> str:
    raw = b"\xed\x01" + pub32
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    num, chars = int.from_bytes(raw, "big"), []
    while num > 0: num, rem = divmod(num, 58); chars.append(_B58_ALPHABET[rem])
    return "did:key:z" + ("1" * zeros) + "".join(reversed(chars))

def did_key_to_pubkey(did: str) -> bytes:
    if not (did or "").startswith("did:key:z"): raise ValueError("DID must start with did:key:z")
    txt = did[len("did:key:z"):]
    zeros = len(txt) - len(txt.lstrip("1")); num = 0
    for ch in txt[zeros:]:
        if ch not in _B58_INDEX: raise ValueError("Bad Base58 char")
        num = num * 58 + _B58_INDEX[ch]
    raw = (b"\x00" * zeros) + (num.to_bytes((num.bit_length() + 7) // 8, "big") if num > 0 else b"")
    if len(raw) != 34 or raw[:2] != b"\xed\x01": raise ValueError("Invalid Ed25519 multicodec")
    return raw[2:]

MCP_STDIO_BRIDGE_SOURCE = f"""#!/usr/bin/env python3
\\"\\"\\"MglennP Radial Switchboard -- MCP Stdio Bridge (Spec Rev {SPEC_VERSION}) | {CONTACT_EMAIL}\\"\\"\\"
import json, os, sys, urllib.request
MCP_URL = os.environ.get("RADIAL_MCP_URL", "https://radialswitchboard.com/mcp")
PASS_TOKEN = os.environ.get("RADIAL_PASS_TOKEN", "").strip()
for line in sys.stdin:
    raw = line.strip()
    if not raw: continue
    try:
        h = {{"Content-Type": "application/json", "Accept": "application/json", "mcp-protocol-version": "2026-07-28"}}
        if PASS_TOKEN: h["X-Radial-Pass"] = PASS_TOKEN
        with urllib.request.urlopen(urllib.request.Request(MCP_URL, data=raw.encode(), headers=h, method="POST"), timeout=15) as r:
            b = r.read().decode("utf-8", errors="replace").strip()
            if b: sys.stdout.write(b + "\\\\n"); sys.stdout.flush()
    except Exception as exc:
        sys.stdout.write(json.dumps({{"jsonrpc": "2.0", "id": None, "error": {{"code": -32000, "message": str(exc)}}}}) + "\\\\n"); sys.stdout.flush()
"""

APPRENTICE_STARTER_SOURCE = f"""#!/usr/bin/env python3
\\"\\"\\"MglennP Radial Switchboard -- Blank-Canvas Apprentice Genesis Hook Starter (MIT, Spec {SPEC_VERSION})
Enrolls an autonomous agent via self-certifying did:key (Economy=A, Bit 25 seasoned_tenure=0) and earns
free handshakes via $0 Canary Scout compute barter. Full Park-and-Resume worker: support@radialswitchboard.com\\"\\"\\"
import hashlib, json, os, secrets, time, urllib.request
SWITCHBOARD = os.environ.get("RADIAL_SWITCHBOARD_URL", "https://radialswitchboard.com")
def claim_and_solve_canary_scout() -> dict:
    req = urllib.request.Request(f"{{SWITCHBOARD}}/v1/work/claim", data=b"{{}}", headers={{"Content-Type": "application/json"}}, method="POST")
    work = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
    results = []
    for t in work.get("targets", []):
        h16, ep = "0000000000000000", str(t.get("endpoint") or "")
        if "/v1/canary/" in ep:
            cr = urllib.request.Request(ep, data=json.dumps({{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}}).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
            tl = ((json.loads(urllib.request.urlopen(cr, timeout=8).read().decode()).get("result") or {{}}).get("tools") or [None])[0]
            if tl:
                sc = tl.get("inputSchema") or {{}}
                canon = json.dumps([{{"i": sorted((sc.get("properties") or {{}}).keys()), "n": tl["name"], "r": sorted(sc.get("required") or [])}}], sort_keys=True, separators=(",", ":"))
                h16 = hashlib.sha256(canon.encode()).hexdigest()[:16]
        results.append({{"agent_id": t.get("agent_id"), "tool_schema_hash_16": h16}})
    sub = urllib.request.Request(f"{{SWITCHBOARD}}/v1/work/submit", data=json.dumps({{"assignment_id": work["assignment_id"], "region": "apprentice-node", "results": results}}).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
    return json.loads(urllib.request.urlopen(sub, timeout=10).read().decode())
if __name__ == "__main__":
    print(json.dumps(claim_and_solve_canary_scout(), indent=2))
"""

RATING_DISCLAIMER_TEXT = (
    "All MGLE-NNP 64-bit stamps, letter grades (A-F), synaptic weights, and status labels are strictly in-house "
    "proprietary MglennP automated technical heuristics measuring point-in-time protocol handshakes—NOT industry "
    "certifications, security audits, legal standings, or endorsements. Provided AS-IS without warranty: https://radialswitchboard.com/legal"
)

def build_legal_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Legal Notice, Terms of Use &amp; Proprietary Scoring Disclaimer | MglennP Radial Switchboard</title>
<style>
  :root {{ --bg:#06090F; --card:#0C1320; --bd:#1D2B44; --tp:#F8FAFC; --ts:#CBD5E1; --tm:#94A3B8; --em:#00E5B0; --am:#F59E0B; --cy:#38BDF8; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--tp); font-family:'IBM Plex Sans',system-ui,-apple-system,sans-serif; line-height:1.65; padding:28px 18px 64px; }}
  .wrap {{ max-width:900px; margin:0 auto; }}
  .top {{ display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; padding-bottom:18px; border-bottom:1px solid var(--bd); margin-bottom:26px; }}
  .back {{ display:inline-block; padding:8px 14px; border-radius:6px; background:#121C2E; border:1px solid #2B4268; color:var(--cy); text-decoration:none; font-weight:600; font-size:0.9rem; }}
  .back:hover {{ border-color:var(--em); color:var(--em); }}
  .banner {{ background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.45); border-radius:10px; padding:16px 18px; margin-bottom:22px; color:#FDE68A; font-size:0.94rem; }}
  h1 {{ font-size:1.75rem; margin-bottom:6px; }}
  h2 {{ font-size:1.12rem; color:var(--em); margin:22px 0 8px; }}
  .card {{ background:var(--card); border:1px solid var(--bd); border-radius:12px; padding:22px 24px; margin-bottom:18px; }}
  p, li {{ color:var(--ts); font-size:0.95rem; margin-bottom:10px; }}
  ul {{ padding-left:20px; }}
  code {{ font-family:monospace; color:var(--em); background:#080D17; padding:2px 6px; border-radius:4px; }}
  .meta {{ color:var(--tm); font-size:0.82rem; font-family:monospace; }}
  a {{ color:var(--cy); }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>Legal Notice, Terms of Use &amp; Proprietary Scoring Disclaimer</h1>
      <div class="meta">MglennP Radial Switchboard &bull; Spec Rev {SPEC_VERSION} &bull; Effective &amp; Updated: November 17, 2026</div>
    </div>
    <a class="back" href="/">&larr; Back to Switchboard</a>
  </div>

  <div class="banner">
    <strong>Plain-Language Summary:</strong> MglennP Radial Switchboard is an independent, experimental software research directory operated on a best-effort basis with zero commercial SLA. All ratings, <code>MGLE-NNP</code> codes, and <code>A&ndash;F</code> grades are strictly <strong>our own in-house proprietary technical heuristics</strong>—they are <strong>not</strong> official industry ratings, security certifications, legal standings, or safety guarantees.
  </div>

  <div class="card">
    <h2>1. Proprietary In-House Scoring System (Not an Industry or Security Standard)</h2>
    <p>Every 64-bit <code>MGLE-NNP</code> identifier, letter grade (<code>A</code> through <code>F</code>), <code>synaptic_weight</code> score, <code>callable_now</code> flag, <code>effect_class</code> tag, and status label (such as <code>VERIFIED_LIVE_GRADE_A</code>) displayed on this website or returned by its APIs is solely an <strong>internal, proprietary MglennP heuristic</strong> generated automatically from brief point-in-time network probes (HTTP status, latency, JSON schema presence, and basic regular-expression text checks).</p>
    <ul>
      <li>These scores carry <strong>no legal, regulatory, accreditation, financial, or industry-standard standing</strong> of any kind.</li>
      <li>A high grade or top rank does <strong>not</strong> mean a third-party server is safe, trustworthy, bug-free, compliant, non-malicious, or endorsed by MglennP.</li>
      <li>A third-party endpoint can change its code, behavior, pricing, authentication, or payload responses millisecond-to-millisecond after an automated probe completes.</li>
    </ul>

    <h2>2. Non-Custodial Directory Only (We Do Not Proxy or Execute Third-Party Agents)</h2>
    <p>Radial Switchboard operates strictly as an indexing and discovery directory (similar to an automated phonebook) for public Model Context Protocol (MCP) and Agent-to-Agent (A2A) endpoints discovered from public registries and submissions.</p>
    <ul>
      <li>We do <strong>not</strong> own, host, control, or operate the third-party endpoints listed in the directory.</li>
      <li>We do <strong>not</strong> proxy tool calls, hold caller API keys, custody user funds, or inspect payloads sent between your client and any third-party endpoint.</li>
      <li>All third-party names, tool summaries, and schemas are untrusted external data (marked <code>untrusted_third_party_text: true</code>) and must never be treated as trusted system instructions.</li>
    </ul>

    <h2>3. Experimental &ldquo;AS IS&rdquo; Service, No Support Team &amp; Zero SLA</h2>
    <p>This project is operated independently for research and interoperability testing without a dedicated support staff, 24/7 monitoring team, or commercial Service Level Agreement (SLA). Emails sent to <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> go to a standard inbox reviewed periodically on a best-effort basis with no guaranteed response time.</p>
    <p>THE WEBSITE, DIRECTORY, API, SCRIPTS, AND ALL OUTPUTS ARE PROVIDED STRICTLY <strong>&ldquo;AS IS&rdquo;</strong> AND <strong>&ldquo;AS AVAILABLE,&rdquo;</strong> WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF ACCURACY, SECURITY, FITNESS FOR A PARTICULAR PURPOSE, MERCHANTABILITY, OR NON-INFRINGEMENT.</p>

    <h2>4. Assumption of Risk &amp; Limitation of Liability</h2>
    <p>By querying or connecting to Radial Switchboard, you agree that you are solely responsible for sandboxing, authenticating, validating, and supervising any third-party endpoint or tool before allowing an AI agent or software system to interact with it. To the fullest extent permitted by applicable Virginia and United States law, MglennP and its operator shall not be liable for any direct, indirect, incidental, consequential, special, exemplary, or data-loss damages arising out of or related to your use of Radial Switchboard or any listed third-party endpoint, and total aggregate liability for any claim shall not exceed the greater of $0.00 USD or the direct fees you paid to Radial Switchboard in the preceding thirty (30) days.</p>

    <h2>5. Removal Requests, Quarantine &amp; Abuse Reporting</h2>
    <p>Endpoint owners wishing to delist or update their public endpoint, or users reporting a broken or malicious listing, may submit an automated re-probe/update via <code>POST /v1/appeals</code> or email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> with the exact <code>agent_id</code> and endpoint URL. We reserve the right to quarantine, re-grade, rate-limit, or remove any listing or caller at any time in our sole discretion.</p>

    <h2>6. Minimal Operational Telemetry &amp; Governing Law</h2>
    <p>To prevent automated abuse and enforce daily free-tier limits, the server processes transient request metadata (such as rate-limit counters and masked network prefixes) and stores public endpoint directory metadata. Public health endpoints strip raw User-Agent and IP strings. These terms are governed by the laws of the Commonwealth of Virginia, USA.</p>
  </div>
</div>
</body>
</html>"""

def is_safe_public_endpoint(ep: str) -> bool:
    u = (ep or "").strip()
    if not u.lower().startswith(("https://", "http://")): return False
    host = (urllib.parse.urlparse(u).hostname or "").strip().lower()
    if not host or host in ("localhost", "metadata.google.internal") or host.endswith((".local", ".internal")): return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_Reserved if hasattr(ip, "is_Reserved") else ip.is_reserved)
    except ValueError:
        return True

def infer_endpoint_geo_zone(ep: str, resp_headers: Optional[Dict[str, str]] = None, rtt_ms: Optional[float] = None) -> str:
    low = (ep or "").lower()
    hdr_keys = {k.lower(): str(v).lower() for k, v in (resp_headers or {}).items()}
    if any(x in low for x in (".workers.dev", ".pages.dev", "vercel.app", "fly.dev", "supabase.co", "cloudflare", "fastly")) or "cf-ray" in hdr_keys:
        return "G"
    if any(x in low for x in ("eu-west", "eu-central", "europe-", ".eu/", ".de/", ".co.uk/")): return "U"
    if any(x in low for x in ("ap-northeast", "ap-southeast", "asia-", ".jp/", ".sg/", ".com.au/")): return "P"
    if any(x in low for x in ("us-west", "usw1", "usw2", "oregon")): return "W"
    if any(x in low for x in ("us-east", "use1", "use4", "virginia")): return "E"
    if rtt_ms is not None:
        if rtt_ms <= 60.0: return "E"
        if rtt_ms <= 105.0: return "W"
        if rtt_ms <= 165.0: return "U"
        return "P"
    return "E"

def normalize_caller_region(raw: str, country: str = "") -> str:
    r = (raw or "").strip().upper()
    if r in ("E", "US-EAST", "USEAST"): return "E"
    if r in ("W", "US-WEST", "USWEST"): return "W"
    if r in ("U", "EU", "EUROPE"): return "U"
    if r in ("P", "APAC", "ASIA"): return "P"
    if r in ("G", "GLOBAL", "ALL", ""):
        cc = (country or "").strip().upper()
        if cc == "US": return "E"
        if cc in EU_COUNTRIES: return "U"
        if cc in APAC_COUNTRIES: return "P"
        return "GLOBAL"
    return "GLOBAL"

def build_x402_payment_required_b64(resource_url: str, treasury_address: str) -> str:
    env = {"x402Version": 2, "error": "PAYMENT-SIGNATURE or X-Radial-Pass required after 15 free daily calls", "resource": {"url": resource_url, "description": "MglennP Radial Switchboard 64-Bit MGLE-NNP Pass (100 handshakes)", "mimeType": "application/json"}, "accepts": [{"scheme": "exact", "network": BASE_MAINNET_CHAIN_ID, "amount": CASH_PASS_ATOMIC_USDC, "asset": BASE_USDC_CONTRACT, "payTo": treasury_address, "maxTimeoutSeconds": 60}]}
    return base64.b64encode(json.dumps(env, separators=(",", ":")).encode("utf-8")).decode("ascii")

def build_x402_payment_response_b64(tx_hash: str = "", success: bool = True, err: str = "") -> str:
    obj: Dict[str, Any] = {"transaction": tx_hash, "network": BASE_MAINNET_CHAIN_ID, "amount": CASH_PASS_ATOMIC_USDC if success else "0"}
    if err: obj["extensions"] = {"error": err}
    return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode("utf-8")).decode("ascii")

def extract_vendor_domain(ep: str) -> str:
    host = (urllib.parse.urlparse(ep).hostname or "").lower().strip(".") if "://" in (ep or "") else ""
    if not host: return (ep or "").lower()[:32]
    pts = host.split(".")
    return ".".join(pts[-3:]) if len(pts) >= 3 and ".".join(pts[-2:]) in MULTI_PART_TLDS else (".".join(pts[-2:]) if len(pts) >= 2 else host)

def infer_capabilities_from_intent(txt: str) -> List[str]:
    low = (txt or "").lower()
    wset = set(_tokenize_words(low))
    for tok in list(wset):
        for piece in tok.split("_"):
            if len(piece) >= 2: wset.add(piece)
    m = [c for c, kws in CAPABILITY_KEYWORDS.items() if any(_kw_matches_text(k, low, wset) for k in kws)]
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
        return {"mgle_nnp_code": f"{mc}{gc}{lc}{ec}-{n1}{n2}{pc}", "u64_hex": f"0x{u64:016X}", "merit": mc, "guarantee": gc, "latency": lc, "economy": ec, "geo_zone": n2, "readiness_flags": [n for n, b in READINESS_BITS.items() if l32 & b], "capabilities": [n for n, b in CAPABILITY_BITS.items() if l32 & b]}

    @staticmethod
    def build_query_masks(caps: Sequence[str], zero_auth: bool = False, poison_clean: bool = True, max_lat: str = "C", zero_hop: bool = True) -> Tuple[int, int, str]:
        req = READINESS_BITS["poison_scan_clean"] if poison_clean else 0
        if zero_auth: req |= READINESS_BITS["zero_auth_instant"]
        for c in caps: req |= CAPABILITY_BITS.get(c.strip().lower(), 0)
        ml_s = (max_lat or "C").strip().upper()
        lat_ch = "*" if ml_s in ("ANY", "*") else ml_s[:1]
        return req, 0, f"**{lat_ch}*-{'Z' if zero_hop else '*'}**"

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
    non_ver_req = req_cap & (~VERIFY_MASK)
    enr = []
    for sc, r in scored:
        vd = extract_vendor_domain(str(r.get("endpoint") or ""))
        cm = int(r.get("domain_mask") or (int(r.get("mgle_nnp_64bit") or 0) & 0x00FFFFFF))
        v_tools = ((r.get("dossier_json") or {}).get("verified_tools") or []) if isinstance(r.get("dossier_json"), dict) else []
        param_ro_tools = [
            t for t in v_tools
            if isinstance(t, dict) and t.get("callable_now", True) and t.get("tool") != "verified_schema"
            and str(t.get("effect_class") or "read_only") == "read_only"
            and (len(t.get("inputs") or {}) >= 1 or len(t.get("required") or []) >= 1)
        ]
        has_param_ro = len(param_ro_tools) >= 1
        t_blob = " ".join(f"{t.get('tool','')} {t.get('summary','')}" for t in param_ro_tools).lower()
        ver_kw = any(w in t_blob for w in ("verify", "validate", "audit", "check", "proof", "math", "compare", "statement", "balance", "query", "sql", "fact", "reconcile", "inspect"))
        dom_overlap = bool((cm & non_ver_req) if non_ver_req else (cm & req_cap))
        has_ver_cap = has_param_ro and (bool(cm & VERIFY_MASK) or (ver_kw and dom_overlap))
        enr.append((sc, vd, cm, has_ver_cap, has_param_ro, r))
    u_ids, u_vends, crew, masks, ver_flags = set(), set(), [], [], []
    roles = (
        ("1_COMPUTE_EXECUTION", lambda s, v, m, vc, pr: s + (0.20 if (m & (COMPUTE_MASK | req_cap)) else -0.30) + (((m & req_cap).bit_count() * 0.24 - max(0, m.bit_count() - max(1, req_cap.bit_count()) - 3) * 0.03) if req_cap else 0.0) - (0.45 if (req_cap and (m & req_cap) == 0) else 0.0)),
        ("2_DOMAIN_KNOWLEDGE_COMPLEMENT", lambda s, v, m, vc, pr: s + (0.32 if v not in u_vends else -0.40) + ((((m & ~(masks[0] if masks else 0)) & req_cap).bit_count() * 0.34 + ((m & req_cap).bit_count() / max(1, m.bit_count())) * 0.20) if req_cap else 0.0) - (0.45 if (req_cap and (m & req_cap) == 0) else 0.0)),
        ("3_INDEPENDENT_VERIFICATION", lambda s, v, m, vc, pr: s + (0.38 if v not in u_vends else -0.45) + (0.36 if vc else (-0.80 if not pr else -0.25)) + (0.18 if (non_ver_req and (m & non_ver_req)) else 0.0) + (0.14 if (m & VERIFY_MASK) else 0.0) - max(0, m.bit_count() - 6) * 0.025),
    )
    for r_name, fn in roles:
        best, bs = None, -999.0
        has_strict_ver = any(x[3] and x[1] not in u_vends for x in enr if str(x[5].get("agent_id") or "") not in u_ids)
        has_any_param = any(x[4] and x[1] not in u_vends for x in enr if str(x[5].get("agent_id") or "") not in u_ids)
        for sc, vd, cm, vc, pr, rec in enr:
            aid = str(rec.get("agent_id") or "")
            if aid in u_ids: continue
            if r_name == "3_INDEPENDENT_VERIFICATION":
                if has_strict_ver and not vc: continue
                if not has_strict_ver and has_any_param and not pr: continue
            adj = fn(sc, vd, cm, vc, pr)
            if adj > bs: bs, best = adj, (rec, r_name, vd, cm, vc)
        if best:
            rc, rn, vd, cm, vc = best
            crew.append((rc, rn, vd)); u_ids.add(str(rc.get("agent_id") or "")); u_vends.add(vd); masks.append(cm); ver_flags.append(vc)
    comb = 0
    for m in masks: comb |= m
    den = max(1, req_cap.bit_count()) if req_cap else 1
    scov = round(min(100.0, (((masks[0] if masks else 0) & req_cap).bit_count() / den) * 100.0), 1) if req_cap else 100.0
    ccov = round(min(100.0, ((comb & req_cap).bit_count() / den) * 100.0), 1) if req_cap else 100.0
    ver_ok = bool(ver_flags[-1]) if len(ver_flags) >= 3 else False
    return crew, {"crew_size": len(crew), "roles_assigned": [x[1] for x in crew], "unique_vendor_domains": len(u_vends), "single_agent_coverage_pct": scov, "crew_combined_coverage_pct": ccov, "verifier_capability_confirmed": ver_ok, "verifier_accepts_inputs": ver_ok, "provider_independence_verified": len(u_vends) == len(crew) and len(crew) > 0}

def _get_or_build_lex_cache(rec: Dict[str, Any]) -> Tuple[str, set[str], str, set[str], str, set[str]]:
    c = rec.get("_lex_cache")
    wtc = int(rec.get("wired_tool_count") or 0)
    if isinstance(c, tuple) and len(c) == 7 and c[6] == wtc:
        return c[:6]
    dos = rec.get("dossier_json") if isinstance(rec.get("dossier_json"), dict) else {}
    v_tools = [t for t in (dos.get("verified_tools") or []) if isinstance(t, dict) and t.get("callable_now", True)]
    t_names_str = " ".join(str(t.get("tool") or "") for t in v_tools).lower()
    t_sums_str = " ".join(str(t.get("summary") or "") for t in v_tools).lower()
    meta_str = f"{rec.get('agent_id','')} {rec.get('name','')} {rec.get('description','')}".lower()
    tn_words = set(_tokenize_words(t_names_str))
    for w in list(tn_words):
        for p in w.split("_"):
            if len(p) >= 2: tn_words.add(p)
    ts_words = set(_tokenize_words(t_sums_str))
    md_words = set(_tokenize_words(meta_str))
    built = (t_names_str, tn_words, t_sums_str, ts_words, meta_str, md_words, wtc)
    rec["_lex_cache"] = built
    return built[:6]

def _compute_stage2_lexical_score(rec: Dict[str, Any], query_terms: List[str], req_c24: int, ag_c24: int) -> float:
    if not query_terms and not req_c24:
        return 0.15
    t_names_str, tn_words, t_sums_str, ts_words, meta_str, md_words = _get_or_build_lex_cache(rec)
    lex_hits = 0.0
    matched_terms = 0
    for qt in query_terms:
        hit_this = False
        if _kw_matches_text(qt, t_names_str, tn_words):
            lex_hits += 0.25; hit_this = True
        if _kw_matches_text(qt, t_sums_str, ts_words):
            lex_hits += 0.11; hit_this = True
        if _kw_matches_text(qt, meta_str, md_words):
            lex_hits += 0.07; hit_this = True
        if hit_this:
            matched_terms += 1
    term_cov = (matched_terms / max(1, len(query_terms))) * 0.26 if query_terms else 0.0
    return round(min(0.98, lex_hits + term_cov), 4)

def flash_unsorted_pool(pool: Sequence[Dict[str, Any]], caps: Sequence[str], zero_auth: bool = False, max_lat: str = "C", zero_hop: bool = True, top_k: int = DEFAULT_FLASH_TOP_K, mode: str = "top10_varied", caller_region: str = "GLOBAL", intent_text: str = "") -> Dict[str, Any]:
    t0 = time.perf_counter()
    ml_norm = (max_lat or "C").strip().upper()
    norm_caps = [c.strip().lower() for c in (caps or []) if c and c.strip()]
    if not norm_caps and intent_text:
        norm_caps = infer_capabilities_from_intent(intent_text)
    req_bits, _, coupler = MgleNnp64Codec.build_query_masks(norm_caps, zero_auth, True, ml_norm, zero_hop)
    max_nib = 5 if ml_norm in ("ANY", "*", "E") else GRADE_TO_NIBBLE.get(ml_norm[:1], 3)
    max_guar_nib = 1 if zero_auth else 3
    c_reg = normalize_caller_region(caller_region)
    req_c24 = req_bits & 0x00FFFFFF
    non_gen_req = req_c24 & (~CAPABILITY_BITS["general"])
    if non_gen_req:
        req_c24 = non_gen_req
    raw_q_words = _tokenize_words(f"{intent_text} {' '.join(norm_caps)}")
    query_terms = []
    for qw in raw_q_words:
        if qw not in STOPWORDS_INTENT and qw != "general" and qw not in query_terms:
            query_terms.append(qw)
        for c_name in norm_caps:
            for kw in CAPABILITY_KEYWORDS.get(c_name, ())[:3]:
                if kw not in query_terms and len(query_terms) < 14:
                    query_terms.append(kw)
    eligible_count = 0
    stage2_scored: List[Tuple[float, int, float, Dict[str, Any]]] = []
    crew_viable: List[Tuple[float, Dict[str, Any]]] = []
    for rec in pool:
        u64 = int(rec.get("mgle_nnp_64bit") or 0)
        u32, l32 = (u64 >> 32) & 0xFFFFFFFF, u64 & 0xFFFFFFFF
        pay_req = bool(rec.get("payment_required", False)) or str(rec.get("auth_mode") or "").startswith("x402")
        if zero_auth and (rec.get("auth_mode") != "none" or pay_req or int(rec.get("wired_tool_count") or 0) <= 0 or str(rec.get("tool_schema_hash_16") or "0000000000000000") == "0000000000000000"):
            continue
        rec_zone = NIBBLE_TO_NEIGHBOR.get((u32 >> 4) & 0xF, str(rec.get("geo_zone") or "E"))
        eff_max_nib = max(max_nib, 3) if (c_reg in ("U", "P", "W") and rec_zone in (c_reg, "G")) else max_nib
        if ((u32 >> 20) & 0xF) > max_guar_nib or ((u32 >> 16) & 0xF) > eff_max_nib or (zero_hop and ((u32 >> 8) & 0xF) != 1):
            continue
        eligible_count += 1
        wt = float(rec.get("synaptic_weight") or 0.80)
        geo_boost = 0.08 if (c_reg != "GLOBAL" and rec_zone == c_reg) else (0.05 if rec_zone == "G" else 0.0)
        ag_c24 = l32 & 0x00FFFFFF
        ov_c24 = (ag_c24 & req_c24).bit_count() if req_c24 else 1
        req_pop = max(1, req_c24.bit_count()) if req_c24 else 1
        ag_pop = max(1, (ag_c24 & (~CAPABILITY_BITS["general"])).bit_count() or ag_c24.bit_count())
        extra_bits = max(0, ag_pop - req_pop)
        wtc_i = int(rec.get("wired_tool_count") or 0)
        multi_cap_bonus = (0.18 * (ov_c24 - 1)) if ov_c24 >= 2 else 0.0
        hub_sprawl_pen = (min(0.22, (wtc_i - 12) * 0.012) if (wtc_i > 12 and ov_c24 <= 1) else 0.0) + max(0, extra_bits - 2) * 0.035
        bit_cov = (ov_c24 / req_pop) * 0.40 if req_c24 else 0.15
        bit_prec = (ov_c24 / ag_pop) * 0.28 - hub_sprawl_pen if req_c24 else 0.0
        lex_sc = _compute_stage2_lexical_score(rec, query_terms, req_c24, ag_c24)
        dos_t = ((rec.get("dossier_json") or {}).get("verified_tools")) or []
        vt_len = sum(1 for t in dos_t if isinstance(t, dict) and t.get("callable_now", True))
        inv_bonus = 0.06 if (vt_len > 0 and wtc_i >= vt_len) else -0.06
        lat_bonus = 0.04 * (6 - ((u32 >> 24) & 0xF)) + 0.02 * (6 - ((u32 >> 16) & 0xF))
        total_sc = round(wt * 0.42 + geo_boost + bit_cov + bit_prec + multi_cap_bonus + lex_sc + inv_bonus + lat_bonus, 4)
        if (mode or "").strip().lower() == "crew" and ((ag_c24 & VERIFY_MASK) or ov_c24 > 0 or lex_sc > 0.08):
            crew_viable.append((total_sc, rec))
        if req_c24 and ov_c24 == 0 and lex_sc < 0.12:
            continue
        stage2_scored.append((total_sc, ov_c24, lex_sc, rec))
    stage2_scored.sort(key=lambda x: (2 if (x[1] >= 2 and x[2] > 0) else (1 if (x[1] > 0 and x[2] > 0) else (0 if x[1] > 0 else -1)), x[0]), reverse=True)
    crew_viable.sort(key=lambda x: x[0], reverse=True)
    strong_pool = [(sc, r) for sc, ov, lx, r in stage2_scored if (ov > 0 and (lx > 0.0 or not query_terms)) or lx >= 0.20]
    fallback_pool = [(sc, r) for sc, ov, lx, r in stage2_scored]
    active_ranked = strong_pool if strong_pool else fallback_pool
    score_by_id = {str(r.get("agent_id") or ""): sc for sc, _, _, r in stage2_scored}
    lex_by_id = {str(r.get("agent_id") or ""): lx for _, _, lx, r in stage2_scored}
    crew_m = None
    if (mode or "").strip().lower() == "crew":
        div, crew_m = assemble_complementary_crew(crew_viable if crew_viable else active_ranked, req_c24)
        var_s, m_mode = {"requested_top_k": 3, "returned_count": len(div), "unique_vendor_domains": crew_m["unique_vendor_domains"]}, ("COMPLEMENTARY_3_AGENT_CREW_TRIAD" if div else "NO_LIVE_RESONANCE")
    elif active_ranked:
        div, var_s = select_varied_top_k(active_ranked, top_k)
        has_full = any((int(r.get("mgle_nnp_64bit") or 0) & req_c24) == req_c24 for _, r in active_ranked[:3]) if req_c24 else True
        m_mode = "EXACT_64BIT_RESONANCE_TOP10_VARIED" if has_full else "STAGE2_BM25_AND_POPCNT_RESONANCE_TOP10_VARIED"
    else:
        div, var_s = [], {"requested_top_k": top_k, "returned_count": 0, "unique_vendor_domains": 0}; m_mode = "NO_LIVE_RESONANCE"
    ms, now_u = round((time.perf_counter() - t0) * 1000.0, 4), int(time.time())
    fins = []
    for i, (r, rl, vd) in enumerate(div, 1):
        ep_s = str(r.get("endpoint") or "")
        aid_s = str(r.get("agent_id") or "")
        low_e = ep_s.lower()
        if not low_e.startswith(("http://", "https://")) or any(h in low_e for h in ("github.com/", "gitlab.com/", "npmjs.com/", "pypi.org/")):
            tr_proto = "stdio-package-repo"
        elif aid_s.startswith("a2a://") or low_e.endswith(("agent-card.json", "agent.json")):
            tr_proto = "a2a-http-json"
        elif low_e.endswith("/sse"):
            tr_proto = "mcp-sse"
        else:
            tr_proto = "mcp-streamable-http"
        dos_raw = r.get("dossier_json") if isinstance(r.get("dossier_json"), dict) else {}
        v_tools = dos_raw.get("verified_tools") if isinstance(dos_raw.get("verified_tools"), list) else []
        callable_v_tools = [t for t in v_tools if isinstance(t, dict) and t.get("tool") and t.get("callable_now", True)]
        if not callable_v_tools:
            callable_v_tools = [t for t in v_tools if isinstance(t, dict) and t.get("tool")]
        t_prev = [
            {
                "tool": t.get("tool"),
                "summary": str(t.get("summary") or f"{str(t.get('tool') or '').replace('_', ' ')}").strip()[:72],
                "required": t.get("required", []),
                "inputs": t.get("inputs", {}),
                "callable_now": bool(t.get("callable_now", True)) and (r.get("auth_mode", "none") == "none") and not bool(r.get("payment_required", False)),
                "effect_class": str(t.get("effect_class") or "read_only"),
            }
            for t in callable_v_tools[:3]
        ]
        eff_wired_cnt = max(len(t_prev), int(r.get("wired_tool_count") or len(t_prev)))
        ag_u64 = int(r.get("mgle_nnp_64bit") or 0)
        ag_caps = [n for n, b in CAPABILITY_BITS.items() if (ag_u64 & 0x00FFFFFF) & b]
        matched_caps = [n for n in ag_caps if (req_c24 & CAPABILITY_BITS[n])] if req_c24 else ag_caps
        fins.append({
            "rank": i,
            "agent_id": aid_s,
            "name": r.get("name"),
            "endpoint": ep_s,
            "transport": tr_proto,
            "protocol_version": "2025-06-18",
            "vendor_domain": vd,
            "geo_zone": NIBBLE_TO_NEIGHBOR.get(((ag_u64 >> 32) >> 4) & 0xF, "E"),
            "variability_role": rl,
            "crew_role": rl if crew_m else None,
            "mgle_nnp_stamp": r.get("mgle_nnp_stamp"),
            "mgle_nnp_u64_hex": f"0x{ag_u64:016X}",
            "guarantee_grade": r.get("guarantee_grade"),
            "latency_grade": r.get("latency_grade"),
            "warm_latency_ms": r.get("avg_latency_ms"),
            "auth_mode": r.get("auth_mode", "none"),
            "auth_hint": r.get("auth_hint", "open_zero_auth_probed" if r.get("auth_mode", "none") == "none" and not bool(r.get("payment_required", False)) else r.get("auth_mode", "auth_required")),
            "payment_required": bool(r.get("payment_required", False)),
            "wired_tool_count": eff_wired_cnt,
            "tools_preview_truncated": eff_wired_cnt > len(t_prev),
            "tool_schema_hash_16": r.get("tool_schema_hash_16"),
            "matched_capabilities": matched_caps,
            "relevance_score": round(float(score_by_id.get(aid_s, r.get("synaptic_weight") or 0.80)), 4),
            "lexical_match_score": round(float(lex_by_id.get(aid_s, 0.0)), 4),
            "untrusted_third_party_text": True,
            "tools_preview": t_prev,
            "synaptic_weight": r.get("synaptic_weight"),
            "last_audited_at": r.get("last_audited_at"),
            "execution_ticket": issue_execution_ticket(aid_s, now_u),
            "ticket_expires_unix": now_u + EXECUTION_TICKET_TTL_SECONDS,
        })
    conf = "high" if (len(strong_pool) >= 3) else ("medium" if len(strong_pool) >= 1 else "low_confidence_no_strong_match")
    out = {
        "spec_version": SPEC_VERSION,
        "rating_disclaimer": RATING_DISCLAIMER_TEXT,
        "legal_url": "https://radialswitchboard.com/legal",
        "caller_region_applied": c_reg,
        "pool_scanned_unsorted": len(pool),
        "scanned_pool_count": len(pool),
        "eligible_pool": eligible_count,
        "post_filter_candidates": len(stage2_scored),
        "match_confidence": conf,
        "single_pass_flash_ms": ms,
        "mode": (mode or "top10_varied").strip().lower(),
        "match_mode": m_mode,
        "coupler_applied": coupler,
        "required_lower32_hex": f"0x{req_bits:08X}",
        "variability_summary": var_s,
        "finalist_count": len(fins),
        "finalists": fins,
        "top_match": fins[0] if fins else {},
    }
    if crew_m is not None: out["crew_manifest"] = crew_m
    return out

def detect_auth_and_payment_hints(name: str, desc: str, c_tools: Sequence[Dict[str, Any]], auth_m: str, x402_ok: bool) -> Tuple[str, bool, str]:
    blob = f"{name} {desc} " + " ".join(f"{t.get('tool','')} {t.get('summary','')}" for t in c_tools if isinstance(t, dict))
    req_in_keys = {str(rk).lower() for t in c_tools if isinstance(t, dict) for rk in (t.get("required") or [])}
    all_in_keys = {str(ik).lower() for t in c_tools if isinstance(t, dict) for ik in (t.get("inputs") or {}).keys()}
    is_paid = bool(x402_ok or str(auth_m or "").startswith("x402") or X402_PAID_PAT.search(blob) or any(t.get("tool") in ("buy_credits", "topup_credits", "add_funds") for t in c_tools if isinstance(t, dict)))
    has_oauth_or_key = bool(OAUTH_OR_KEY_PAT.search(blob) or (req_in_keys & AUTH_INPUT_KEYS))
    soft_key_opt = bool(all_in_keys & AUTH_INPUT_KEYS) and not has_oauth_or_key
    eff_auth = str(auth_m or "none")
    if is_paid and eff_auth == "none":
        eff_auth = "x402_or_credit_gated"
    elif has_oauth_or_key and eff_auth == "none":
        eff_auth = "oauth_or_apikey_required"
    if eff_auth == "none" and not is_paid:
        hint = "optional_key_param_present" if soft_key_opt else "open_zero_auth_probed"
    elif is_paid:
        hint = "prepaid_credits_or_x402_required"
    else:
        hint = eff_auth
    return eff_auth, is_paid, hint

def extract_capabilities_and_hash(blob: str, tools: Sequence[Dict[str, Any]]) -> Tuple[int, str, List[Dict[str, Any]]]:
    pts, inv = [blob or ""], []
    for t in sorted(tools, key=lambda x: str(x.get("name", "") if isinstance(x, dict) else "")):
        if not isinstance(t, dict): continue
        tn, td = str(t.get("name") or "").strip(), str(t.get("description") or "").strip()[:180]
        sc = t.get("inputSchema") if isinstance(t.get("inputSchema"), dict) else {}
        pr = sc.get("properties") if isinstance(sc.get("properties"), dict) else {}
        rq = sc.get("required") if isinstance(sc.get("required"), list) else []
        ann = t.get("annotations") if isinstance(t.get("annotations"), dict) else None
        entry = classify_tool_entry(tn, td, pr, rq, ann)
        if entry["callable_now"]:
            pts.extend([tn, td, *(str(k) for k in pr.keys())])
        inv.append(entry)
    low = " ".join(pts).lower()
    wset = set(_tokenize_words(low))
    for tok in list(wset):
        for piece in tok.split("_"):
            if len(piece) >= 2: wset.add(piece)
    mask = 0
    for cn, kws in CAPABILITY_KEYWORDS.items():
        if any(_kw_matches_text(k, low, wset) for k in kws):
            mask |= CAPABILITY_BITS[cn]
    if mask == 0: mask = CAPABILITY_BITS["general"]
    callable_inv = [t for t in inv if t.get("callable_now", True)]
    h16 = hashlib.sha256(json.dumps([{"n": t["tool"], "i": sorted(t["inputs"].keys()), "r": sorted(t["required"])} for t in callable_inv], sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16] if callable_inv else "0000000000000000"
    return mask, h16, inv

def build_agent_record_and_dossier(aid: str, name: str, desc: str, ep: str, alive: bool, cold_ms: Optional[float], warm_ms: Optional[float], tools: Sequence[Dict[str, Any]], auth_m: str = "none", rpm: Optional[int] = None, x402_ok: bool = False, prev_record: Optional[Dict[str, Any]] = None, geo_zone: Optional[str] = None) -> Dict[str, Any]:
    pv = prev_record or {}
    enc, wins, fails = int(pv.get("encounter_count") or 0) + 1, int(pv.get("room_completions") or 0), int(pv.get("room_failures") or 0)
    p_wt = float(pv.get("synaptic_weight") or 0.80)
    low_ep = (ep or "").strip().lower()
    is_repo = not low_ep.startswith(("http://", "https://")) or any(h in low_ep for h in ("github.com/", "gitlab.com/", "npmjs.com/", "pypi.org/"))
    p_ok = not any(pat.search(json.dumps(t)) for t in tools if isinstance(t, dict) for pat in TOOL_POISONING_PATTERNS)
    clean_desc = str(desc or "").split(" /*RADIAL_TOOLS:")[0].strip()
    c_mask, h16, c_tools = extract_capabilities_and_hash(f"{name} {clean_desc}", tools)
    callable_tools = [t for t in c_tools if t.get("callable_now", True) and t.get("tool") != "verified_schema"]
    auth_m, is_paid, auth_hint = detect_auth_and_payment_hints(name, clean_desc, c_tools, auth_m, x402_ok)
    if is_paid:
        x402_ok = True
    if auth_m != "none" or is_paid:
        for ct_item in callable_tools:
            ct_item["callable_without_credentials"] = False
    else:
        for ct_item in callable_tools:
            ct_item["callable_without_credentials"] = True
    eff = warm_ms if warm_ms is not None else cold_ms
    zone = (geo_zone or infer_endpoint_geo_zone(ep, None, eff))[:1].upper()
    if zone not in NEIGHBOR_TO_NIBBLE: zone = "E"
    lat_g = "E" if (not alive or eff is None or is_repo) else ("A" if eff <= 120 else ("B" if eff <= 300 else ("C" if eff <= 700 else ("D" if eff <= 1500 else "E"))))
    if not p_ok: guar_g, merit_g, node_h, n_wt, st = "F", "F", "W", 0.0, "SLASHED_POISON_GRADE_F"
    elif is_repo: guar_g, merit_g, node_h, n_wt, st = "D", "C", "Z", min(p_wt, 0.50), "UNHOSTED_REPO_GRADE_D"
    elif not alive: guar_g, merit_g, node_h, n_wt, st = "E", "D", "Z", max(0.10, round(p_wt - 0.20, 4)), "QUARANTINED_OFFLINE_GRADE_E"
    else:
        has_verified_tools = len(callable_tools) > 0 and h16 != "0000000000000000"
        if auth_m == "none" and not has_verified_tools:
            auth_m = "unwired_or_empty_tools" if len(c_tools) > 0 else "auth_or_session_required"
        if auth_m == "none" and has_verified_tools and not is_paid:
            guar_g = "A"
            merit_g, node_h, n_wt = ("B" if wins >= 5 else "C"), "Z", min(0.99, round(p_wt + 0.04, 4))
            st = "VERIFIED_LIVE_GRADE_A"
        else:
            guar_g = "B" if is_paid else "C"
            merit_g, node_h, n_wt = "C", "Z", min(0.78, round(p_wt, 4))
            st = "LIVE_X402_PAYABLE_GRADE_B" if is_paid else "LIVE_AUTH_GATED_GRADE_C"
    r_mask = (READINESS_BITS["poison_scan_clean"] if p_ok else 0) | READINESS_BITS["schema_drift_stable"]
    if wins >= 10 and (wins / max(1, wins + fails)) > 0.80: r_mask |= READINESS_BITS["seasoned_tenure"]
    if is_paid: r_mask |= READINESS_BITS["x402_native_payable"]
    if auth_m == "none" and not is_paid and len(callable_tools) > 0 and h16 != "0000000000000000" and not is_repo and alive:
        r_mask |= READINESS_BITS["zero_auth_instant"]
    stamp, u64, u64_hex = MgleNnp64Codec.pack(merit_g, guar_g, lat_g, "B" if is_paid else "A", node_h, zone, "S" if lat_g in ("A", "B") else "D", r_mask, c_mask)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    dos = {"agent_id": aid, "vendor_domain": extract_vendor_domain(ep), "geo_zone": zone, "mgle_nnp_code": stamp, "mgle_nnp_u64_hex": u64_hex, "decoded_switches": MgleNnp64Codec.unpack(u64), "verified_tools": callable_tools[:20], "all_inspected_tools_count": len(c_tools), "untrusted_third_party_text": True, "inspected_at_utc": now_iso}
    return {"agent_id": aid, "name": name, "description": clean_desc[:400], "endpoint": ep, "geo_zone": zone, "merit_grade": merit_g, "guarantee_grade": guar_g, "latency_grade": lat_g, "mgle_nnp_stamp": stamp, "mgle_nnp_64bit": u64, "mgle_nnp_u64_hex": u64_hex, "domain_mask": c_mask, "avg_latency_ms": eff, "synaptic_weight": n_wt, "wired_tool_count": len(callable_tools), "tool_schema_hash_16": h16, "auth_mode": auth_m, "auth_hint": auth_hint, "payment_required": is_paid, "untrusted_third_party_text": True, "poison_scan_clean": p_ok, "encounter_count": enc, "room_completions": wins, "room_failures": fails, "dossier_json": dos, "audit_status": st, "last_audited_at": now_iso}

def interrogate_live_endpoint(row: Dict[str, Any], timeout_sec: float = 3.5) -> Dict[str, Any]:
    aid, nm, ds, ep = str(row.get("agent_id") or row.get("id") or ""), str(row.get("name") or ""), str(row.get("description") or "").split(" /*RADIAL_TOOLS:")[0].strip(), str(row.get("endpoint") or "").strip()
    if not is_safe_public_endpoint(ep) or any(h in ep.lower() for h in ("github.com/", "gitlab.com/", "npmjs.com/", "pypi.org/")):
        return build_agent_record_and_dossier(aid, nm or aid, ds, ep, False, None, None, [], "local_stdio_code", prev_record=row)
    ctx = ssl.create_default_context()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "mcp-protocol-version": "2026-07-28", "User-Agent": f"MglennP-RadialScout/{SPEC_VERSION}"}
    ib = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "RadialScout", "version": SPEC_VERSION}}}).encode()
    cold, warm, alive, auth_m, x402_ok, sess, tools, resp_h = None, None, False, "none", False, None, [], {}
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(ep, data=ib, headers=hdrs, method="POST"), timeout=timeout_sec, context=ctx) as r:
            cold, alive, resp_h = round((time.perf_counter() - t0) * 1000.0, 2), (200 <= r.status < 400), dict(r.headers.items())
            sess = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
    except urllib.error.HTTPError as e:
        cold = round((time.perf_counter() - t0) * 1000.0, 2)
        if e.headers: resp_h = dict(e.headers.items())
        if e.code in (401, 403): alive, auth_m = True, "bearer_or_oauth_required"
        elif e.code == 402: alive, auth_m, x402_ok = True, "x402_micropayment", True
        elif e.code in (400, 405, 406): alive, auth_m = True, "non_mcp_or_custom_handshake"
    except Exception:
        alive = False
    if alive and auth_m == "none":
        wh = dict(hdrs)
        if sess: wh["Mcp-Session-Id"] = sess
        t1 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(ep, data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode(), headers=wh, method="POST"), timeout=timeout_sec, context=ctx) as r2:
                warm = round((time.perf_counter() - t1) * 1000.0, 2)
                ps = r2.read(524288).decode("utf-8", errors="replace").strip()
                if not ps.startswith("{"):
                    for ln in ps.splitlines():
                        if ln.strip().startswith("data:") and "{" in ln: ps = ln.split("data:", 1)[1].strip(); break
                parsed_l = json.loads(ps) or {}
                if isinstance(parsed_l.get("error"), dict):
                    auth_m = "rpc_error_or_auth_gated"
                ro = parsed_l.get("result")
                if isinstance(ro, dict) and isinstance(ro.get("tools"), list): tools = ro["tools"]
        except urllib.error.HTTPError as e2:
            if e2.code in (401, 403): auth_m = "bearer_or_oauth_required"
            elif e2.code == 402: auth_m, x402_ok = "x402_micropayment", True
            else: auth_m = f"tools_list_http_{e2.code}"
        except Exception:
            auth_m = "tools_list_unreachable"
        if auth_m == "none" and tools:
            try:
                cb = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "__radial_auth_probe__", "arguments": {}}}).encode()
                with urllib.request.urlopen(urllib.request.Request(ep, data=cb, headers=wh, method="POST"), timeout=min(2.2, timeout_sec), context=ctx) as r3:
                    cs = r3.read(65536).decode("utf-8", errors="replace").strip()
                    if not cs.startswith("{"):
                        for ln in cs.splitlines():
                            if ln.strip().startswith("data:") and "{" in ln: cs = ln.split("data:", 1)[1].strip(); break
                    cp = json.loads(cs) if cs.startswith("{") else {}
                    err_blob = json.dumps(cp.get("error") or cp.get("result") or "").lower()
                    if any(w in err_blob for w in ("unauthorized", "unauthenticated", "invalid token", "missing token", "api key", "oauth", "login required", "bearer")):
                        auth_m = "tools_call_auth_gated"
                    elif any(w in err_blob for w in ("payment required", "insufficient credit", "insufficient balance", "x402", "usdc", "buy_credits")):
                        auth_m, x402_ok = "x402_or_credit_gated", True
            except urllib.error.HTTPError as e3:
                if e3.code in (401, 403): auth_m = "tools_call_auth_gated"
                elif e3.code == 402: auth_m, x402_ok = "x402_micropayment", True
            except Exception:
                pass
    zone = infer_endpoint_geo_zone(ep, resp_h, warm if warm is not None else cold)
    return build_agent_record_and_dossier(aid, nm or aid, ds, ep, alive, cold, warm, tools, auth_m, None, x402_ok, row, zone)

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

def build_pulse_html(data: Dict[str, Any]) -> str:
    _esc = __import__("html").escape
    init_json = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0b1120">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<title>Radial Switchboard — Live Pulse</title>
<style>
  :root {{ --bg:#0b1120; --card:#111827; --bdr:#1e293b; --txt:#f8fafc; --mut:#94a3b8; --em:#10b981; --sky:#38bdf8; --amb:#fbbf24; --pur:#c084fc; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--txt); padding:16px; max-width:980px; margin:0 auto; line-height:1.45; }}
  .hdr {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid var(--bdr); }}
  .title {{ font-size:1.25rem; font-weight:700; display:flex; align-items:center; gap:8px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; background:var(--em); box-shadow:0 0 10px var(--em); display:inline-block; }}
  .sub {{ font-size:0.8rem; color:var(--mut); }}
  .btn {{ background:#1e293b; color:var(--txt); border:1px solid #334155; border-radius:8px; padding:7px 12px; font-size:0.8rem; font-weight:600; cursor:pointer; }}
  .btn:active {{ transform:scale(0.98); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(205px,1fr)); gap:12px; margin-bottom:16px; }}
  .card {{ background:var(--card); border:1px solid var(--bdr); border-radius:12px; padding:14px; }}
  .lbl {{ font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--mut); }}
  .val {{ font-size:1.85rem; font-weight:800; margin:4px 0; font-variant-numeric:tabular-nums; }}
  .pill {{ display:inline-block; font-size:0.74rem; padding:2px 8px; border-radius:999px; background:#0f172a; border:1px solid var(--bdr); color:var(--mut); }}
  .sysbar {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .sec {{ background:var(--card); border:1px solid var(--bdr); border-radius:12px; padding:14px; margin-bottom:16px; overflow-x:auto; }}
  .sec h2 {{ font-size:0.92rem; margin-bottom:10px; color:#e2e8f0; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.82rem; font-variant-numeric:tabular-nums; }}
  th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid #1e293b; white-space:nowrap; }}
  th {{ color:var(--mut); font-weight:600; font-size:0.74rem; text-transform:uppercase; }}
  .r {{ text-align:right; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:0.77rem; }}
  .foot {{ font-size:0.75rem; color:var(--mut); text-align:center; padding:8px 0 20px; }}
  a {{ color:var(--sky); text-decoration:none; }}
</style>
</head>
<body>
  <div class="hdr">
    <div>
      <div class="title"><span class="dot"></span> Radial Switchboard Pulse</div>
      <div class="sub" id="hdrSub">Observer Mode (Viewing never inflates counters) &bull; Spec {_esc(str(data.get("spec_version") or ""))}</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;">
      <span class="pill" id="updBadge">Live</span>
      <button class="btn" onclick="refreshPulse()">Refresh</button>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="lbl">Agent Task Calls (MCP + REST)</div>
      <div class="val" style="color:var(--em)" id="vTasks">0</div>
      <span class="pill" id="pTasksToday">Today: 0</span>
    </div>
    <div class="card">
      <div class="lbl">Human Browser Visits</div>
      <div class="val" style="color:var(--sky)" id="vHumans">0</div>
      <span class="pill" id="pHumansToday">Today: 0</span>
    </div>
    <div class="card">
      <div class="lbl">MCP Handshakes &amp; Probes</div>
      <div class="val" style="color:var(--amb)" id="vProbes">0</div>
      <span class="pill" id="pProbesToday">Today: 0</span>
    </div>
    <div class="card">
      <div class="lbl">AI Discovery Beacons</div>
      <div class="val" style="color:var(--pur)" id="vBeacons">0</div>
      <span class="pill" id="pBeaconsToday">Today: 0</span>
    </div>
  </div>

  <div class="sysbar" id="sysBar"></div>

  <div class="sec">
    <h2>14-Day UTC Traffic History</h2>
    <table>
      <thead><tr><th>UTC Date</th><th class="r">Task Calls</th><th class="r">Human Visits</th><th class="r">MCP Probes</th><th class="r">Beacons</th><th class="r">Bot Crawls</th></tr></thead>
      <tbody id="dailyBody"></tbody>
    </table>
  </div>

  <div class="sec">
    <h2>Caller Ecosystem Breakdown (All Recorded Hits)</h2>
    <table>
      <thead><tr><th>Client / Agent Family</th><th class="r">Events</th></tr></thead>
      <tbody id="famBody"></tbody>
    </table>
  </div>

  <div class="sec">
    <h2>Latest External Events (Privacy-Safe, Zero IPs)</h2>
    <table>
      <thead><tr><th>UTC Time</th><th>Client Family</th><th>Event</th><th>Route</th></tr></thead>
      <tbody id="actBody"></tbody>
    </table>
  </div>

  <div class="foot">
    <a href="/?ui_observer=true">Open Directory (Observer Mode)</a> &bull; <a href="/v1/pulse">Raw /v1/pulse JSON</a> &bull; <a href="/legal">Legal</a>
  </div>

<script>
let DATA = {init_json};
const fmt = n => Number(n || 0).toLocaleString();
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}})[c]);

function render(d) {{
  const t = d.totals || {{}};
  const td = d.today_utc || {{}};
  document.getElementById("vTasks").textContent = fmt(t.task_calls);
  document.getElementById("pTasksToday").textContent = `Today: ${{fmt(td.tasks)}} (${{fmt(t.mcp_jsonrpc_calls)}} MCP / ${{fmt(t.rest_matchmake_calls)}} REST)`;
  document.getElementById("vHumans").textContent = fmt(t.human_page_views);
  document.getElementById("pHumansToday").textContent = `Today: ${{fmt(td.humans)}} &bull; Bot crawls: ${{fmt(t.bot_page_crawls)}}`;
  document.getElementById("vProbes").textContent = fmt(t.mcp_total_probes);
  document.getElementById("pProbesToday").textContent = `Today: ${{fmt(td.probes)}} (${{fmt(t.mcp_initialize_handshakes)}} init / ${{fmt(t.mcp_tools_list_probes)}} list)`;
  document.getElementById("vBeacons").textContent = fmt(t.discovery_pulls);
  document.getElementById("pBeaconsToday").textContent = `Today: ${{fmt(td.beacons)}} &bull; Bridge DL: ${{fmt(t.bridge_script_downloads)}}`;

  const p = d.pool || {{}};
  document.getElementById("sysBar").innerHTML = [
    `Pool: <b>${{fmt(p.live_callable_ab)}}</b> Grade A/B of <b>${{fmt(p.total_indexed)}}</b>`,
    `Scout Sweeps: <b>${{fmt(t.scout_sweeps_completed)}}</b>`,
    `Supabase: <b>${{d.supabase_connected ? "ONLINE" : "LOCAL"}}</b>`,
    `Scale Guard: <b>min=0 / max=1</b>`,
    `USDC Settled: <b>$${{Number(d.usdc_settled_usd || 0).toFixed(2)}}</b>`
  ].map(x => `<span class="pill">${{x}}</span>`).join("");

  const rows = d.daily_history || [];
  document.getElementById("dailyBody").innerHTML = rows.length ? rows.map(r =>
    `<tr><td class="mono">${{esc(r.date)}}</td><td class="r" style="color:#10b981;font-weight:700">${{fmt(r.tasks)}}</td><td class="r">${{fmt(r.humans)}}</td><td class="r">${{fmt(r.probes)}}</td><td class="r">${{fmt(r.beacons)}}</td><td class="r">${{fmt(r.bots)}}</td></tr>`
  ).join("") : `<tr><td colspan="6" style="color:#94a3b8">New daily buckets start accumulating immediately on incoming hits.</td></tr>`;

  const fams = d.client_families || [];
  document.getElementById("famBody").innerHTML = fams.length ? fams.map(f =>
    `<tr><td>${{esc(f.family)}}</td><td class="r mono">${{fmt(f.count)}}</td></tr>`
  ).join("") : `<tr><td colspan="2" style="color:#94a3b8">Awaiting next external caller classification.</td></tr>`;

  const acts = d.recent_events || [];
  document.getElementById("actBody").innerHTML = acts.length ? acts.map(a =>
    `<tr><td class="mono">${{esc(a.utc)}}</td><td>${{esc(a.client_family)}}</td><td class="mono">${{esc(a.event)}}</td><td class="mono">${{esc(a.route)}}</td></tr>`
  ).join("") : `<tr><td colspan="4" style="color:#94a3b8">No recent external events recorded yet.</td></tr>`;

  document.getElementById("updBadge").textContent = "Updated " + new Date().toLocaleTimeString();
}}

async function refreshPulse() {{
  try {{
    const r = await fetch("/v1/pulse", {{cache: "no-store"}});
    if (r.ok) {{ DATA = await r.json(); render(DATA); }}
  }} catch (e) {{}}
}}
render(DATA);
setInterval(refreshPulse, 30000);
</script>
</body>
</html>"""

class StandaloneSwitchboardRuntime:
    def __init__(self, hydrate_external: bool = True, start_background_scouts: bool = True) -> None:
        self.hydrate_external = hydrate_external
        self.pool_by_id: Dict[str, Dict[str, Any]] = {}
        self.enrolled_apprentices: Dict[str, Dict[str, Any]] = {}
        self.gate = DualLaneGateAndTaxLedger(DEFAULT_USDC_TREASURY_ADDRESS)
        self.appeals_log: List[Dict[str, Any]] = []
        self.redeemed_tickets: set[str] = set()
        self._lock = threading.Lock()
        self.crawl_cursor: Dict[str, Any] = {"registry_cursor": "", "pages_completed": 0, "full_cycles": 0}
        self._save_lock = threading.Lock()
        self.telemetry: Dict[str, Any] = {
            "total_external_uses": 0, "external_agent_calls": 0, "mcp_jsonrpc_calls": 0, "rest_matchmake_calls": 0,
            "ai_beacon_discovery_pulls": 0, "room_handshakes_completed": 0, "starter_keys_minted": 0,
            "outcome_reports_verified": 0, "scout_sweeps_completed": 0, "apprentices_enrolled": 0,
            "mcp_initialize_handshakes": 0, "mcp_tools_list_probes": 0, "bridge_script_downloads": 0,
            "human_page_views": 0, "bot_page_crawls": 0,
            "daily_rollup": {}, "client_families": {},
            "recent_activity": [],
            "last_scout_sweep_utc": None, "scout_currently_running": False,
        }
        if hydrate_external:
            self._hydrate()
            self._load_telemetry()
            self._load_crawl_cursor()
        if hydrate_external and start_background_scouts:
            threading.Thread(target=self._daemon, daemon=True).start()

    def _sb_creds(self) -> Tuple[str, str]:
        u = (os.environ.get("SUPABASE_URL") or os.environ.get("RADIAL_SUPABASE_URL") or "").strip().rstrip("/")
        k = (os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
        return u, k

    def _recompute(self) -> int:
        real_uses = int(self.telemetry.get("mcp_jsonrpc_calls") or 0) + int(self.telemetry.get("rest_matchmake_calls") or 0) + int(self.telemetry.get("room_handshakes_completed") or 0)
        self.telemetry["total_external_uses"] = real_uses
        self.telemetry["human_or_agent_task_calls"] = real_uses
        self.telemetry["discovery_pulls"] = int(self.telemetry.get("ai_beacon_discovery_pulls") or 0)
        return real_uses

    @staticmethod
    def _mask_ip(ip: str) -> str:
        s = (ip or "anon").strip()
        if "." in s:
            pts = s.split(".")
            if len(pts) == 4: return f"{pts[0]}.{pts[1]}.x.x"
        if ":" in s:
            pts = s.split(":")
            return ":".join(pts[:2]) + "::x"
        return s[:12]

    @staticmethod
    def _classify_caller(ua: str) -> str:
        u = (ua or "").lower()
        if not u or u == "unknown": return "Unknown / Direct HTTP"
        if "claude" in u or "anthropic" in u: return "Claude / Anthropic"
        if "grok" in u or "xai" in u: return "Grok / xAI"
        if "chatgpt" in u or "openai" in u or "oai-searchbot" in u: return "OpenAI / ChatGPT"
        if "gemini" in u or "google-extended" in u or "googleother" in u: return "Google / Gemini"
        if any(b in u for b in ("glama", "smithery", "lowdown", "mcp", "modelcontextprotocol")): return "MCP Client / Directory"
        if any(b in u for b in ("googlebot", "bingbot", "duckduckbot", "applebot", "yandex", "baiduspider", "petalbot", "ahrefs", "semrush")): return "Search / SEO Crawler"
        if "mozilla/" in u and any(b in u for b in ("chrome/", "safari/", "firefox/", "edg/")) and "headless" not in u: return "Human Web Browser"
        if any(b in u for b in ("python", "httpx", "aiohttp", "requests", "urllib", "curl/", "go-http", "node", "undici", "axios", "okhttp")): return "Agent SDK / Script / CLI"
        return "Other External Client"

    def record_event(self, field: str, ext_call: bool = False, route: str = "", ua: str = "", ip: str = "", status: int = 200) -> None:
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        day_k = now_dt.strftime("%Y-%m-%d")
        fam = self._classify_caller(ua)
        with self._lock:
            self.telemetry[field] = int(self.telemetry.get(field) or 0) + 1
            if ext_call: self.telemetry["external_agent_calls"] = int(self.telemetry.get("external_agent_calls") or 0) + 1
            if field != "scout_sweeps_completed":
                dr = dict(self.telemetry.get("daily_rollup") or {})
                bkt = dict(dr.get(day_k) or {"tasks": 0, "humans": 0, "probes": 0, "beacons": 0, "bots": 0})
                if field in ("mcp_jsonrpc_calls", "rest_matchmake_calls", "room_handshakes_completed"): bkt["tasks"] = int(bkt.get("tasks") or 0) + 1
                elif field == "human_page_views": bkt["humans"] = int(bkt.get("humans") or 0) + 1
                elif field in ("mcp_initialize_handshakes", "mcp_tools_list_probes"): bkt["probes"] = int(bkt.get("probes") or 0) + 1
                elif field in ("ai_beacon_discovery_pulls", "bridge_script_downloads"): bkt["beacons"] = int(bkt.get("beacons") or 0) + 1
                elif field == "bot_page_crawls": bkt["bots"] = int(bkt.get("bots") or 0) + 1
                dr[day_k] = bkt
                for old_k in sorted(dr.keys())[:-14]:
                    dr.pop(old_k, None)
                self.telemetry["daily_rollup"] = dr
                if ua and "RadialScout" not in ua and "GoogleHC" not in ua:
                    cf = dict(self.telemetry.get("client_families") or {})
                    cf[fam] = int(cf.get(fam) or 0) + 1
                    self.telemetry["client_families"] = cf
            if route:
                act = list(self.telemetry.get("recent_activity") or [])
                act.insert(0, {
                    "utc": now_dt.strftime("%Y-%m-%d %H:%M:%SZ"),
                    "event": field,
                    "route": route[:64],
                    "status": int(status),
                    "client_family": fam,
                    "ua": (ua or "unknown").strip()[:96],
                    "ip_masked": self._mask_ip(ip),
                })
                self.telemetry["recent_activity"] = act[:20]
            self._recompute()
        if self.hydrate_external:
            if ext_call or field in ("human_page_views", "starter_keys_minted", "apprentices_enrolled"):
                self._save_telemetry()
            else:
                threading.Thread(target=self._save_telemetry, daemon=True).start()

    def _put_sys_state(self, state_id: str, obj: Dict[str, Any], count_val: int = 0) -> None:
        u, k = self._sb_creds()
        if not u or not k: return
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        row = [{
            "agent_id": state_id, "name": state_id, "protocol": "SYS_STATE", "endpoint": "internal://sys-state",
            "description": json.dumps(obj, separators=(",", ":")), "radial_bitmask": 0, "fingerprint_hex": "0x0",
            "mglennp_code": "CCCC-ZES", "mglennp_u64": 0, "mglennp_u64_hex": "0x0000000000000000", "hop_ttl": 0,
            "synaptic_weight": 0.0, "avg_latency_ms": 0, "handshakes_completed": int(count_val), "handshakes_failed": 0,
            "node_style": "Z", "neighborhood": "E", "preference": "S", "agent_toll_usd": 0.0, "updated_at": now_iso,
        }]
        try:
            urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_agent_phonebook?on_conflict=agent_id", data=json.dumps(row).encode(), headers={"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}, method="POST"), timeout=10).close()
        except Exception: pass

    def _get_sys_state(self, state_id: str) -> Optional[Dict[str, Any]]:
        u, k = self._sb_creds()
        if not u or not k: return None
        try:
            q = urllib.parse.quote(state_id, safe="")
            with urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_agent_phonebook?agent_id=eq.{q}&select=description", headers={"apikey": k, "Authorization": f"Bearer {k}"}), timeout=8) as r:
                rows = json.loads(r.read().decode())
            if rows and str(rows[0].get("description") or "").startswith("{"):
                return json.loads(rows[0]["description"])
        except Exception: pass
        return None

    def _merge_telemetry_dict(self, src_d: Dict[str, Any], ks: Tuple[str, ...]) -> None:
        for kx in ks:
            if isinstance(src_d.get(kx), int) and src_d[kx] > self.telemetry.get(kx, 0):
                self.telemetry[kx] = src_d[kx]
        if isinstance(src_d.get("daily_rollup"), dict):
            dr = dict(self.telemetry.get("daily_rollup") or {})
            for dk, dv in src_d["daily_rollup"].items():
                if isinstance(dv, dict):
                    cur = dict(dr.get(dk) or {})
                    for bk in ("tasks", "humans", "probes", "beacons", "bots"):
                        cur[bk] = max(int(cur.get(bk) or 0), int(dv.get(bk) or 0))
                    dr[str(dk)[:10]] = cur
            for old_k in sorted(dr.keys())[:-14]:
                dr.pop(old_k, None)
            self.telemetry["daily_rollup"] = dr
        if isinstance(src_d.get("client_families"), dict):
            cf = dict(self.telemetry.get("client_families") or {})
            for fk, fv in src_d["client_families"].items():
                if isinstance(fv, int):
                    cf[str(fk)[:40]] = max(int(cf.get(fk) or 0), fv)
            self.telemetry["client_families"] = cf
        if isinstance(src_d.get("recent_activity"), list) and src_d["recent_activity"]:
            seeded = []
            for item in src_d["recent_activity"][:20]:
                if isinstance(item, dict):
                    if not item.get("client_family"):
                        item = {**item, "client_family": self._classify_caller(str(item.get("ua") or ""))}
                    seeded.append(item)
            self.telemetry["recent_activity"] = seeded
            if not self.telemetry.get("client_families"):
                cf_seed: Dict[str, int] = {}
                for item in seeded:
                    fm = str(item.get("client_family") or "Other External Client")
                    cf_seed[fm] = cf_seed.get(fm, 0) + 1
                self.telemetry["client_families"] = cf_seed

    def _load_telemetry(self) -> None:
        ks = ("external_agent_calls", "mcp_jsonrpc_calls", "rest_matchmake_calls", "ai_beacon_discovery_pulls", "room_handshakes_completed", "starter_keys_minted", "outcome_reports_verified", "scout_sweeps_completed", "apprentices_enrolled", "mcp_initialize_handshakes", "mcp_tools_list_probes", "bridge_script_downloads", "human_page_views", "bot_page_crawls")
        if os.path.isfile(TELEMETRY_LOCAL_PATH):
            try:
                self._merge_telemetry_dict(json.loads(open(TELEMETRY_LOCAL_PATH).read()), ks)
            except Exception: pass
        rem = self._get_sys_state("sys://telemetry_v3")
        if isinstance(rem, dict):
            self._merge_telemetry_dict(rem, ks)
        self._recompute()

    def _save_telemetry(self) -> None:
        with self._save_lock:
            ks = ("total_external_uses", "external_agent_calls", "mcp_jsonrpc_calls", "rest_matchmake_calls", "ai_beacon_discovery_pulls", "room_handshakes_completed", "starter_keys_minted", "outcome_reports_verified", "scout_sweeps_completed", "apprentices_enrolled", "mcp_initialize_handshakes", "mcp_tools_list_probes", "bridge_script_downloads", "human_page_views", "bot_page_crawls")
            with self._lock:
                snap: Dict[str, Any] = {kx: int(self.telemetry.get(kx) or 0) for kx in ks}
                dr = dict(self.telemetry.get("daily_rollup") or {})
                snap["daily_rollup"] = {k: dr[k] for k in sorted(dr.keys())[-14:]}
                snap["client_families"] = dict(sorted((self.telemetry.get("client_families") or {}).items(), key=lambda x: x[1], reverse=True)[:15])
                snap["recent_activity"] = list(self.telemetry.get("recent_activity") or [])[:20]
            try: open(TELEMETRY_LOCAL_PATH, "w").write(json.dumps(snap, separators=(",", ":")))
            except Exception: pass
            self._put_sys_state("sys://telemetry_v3", snap, int(snap.get("total_external_uses") or 0))

    def _load_crawl_cursor(self) -> None:
        obj = self._get_sys_state("sys://crawl_cursor_v3")
        if isinstance(obj, dict):
            self.crawl_cursor["registry_cursor"] = str(obj.get("registry_cursor") or "")
            self.crawl_cursor["pages_completed"] = int(obj.get("pages_completed") or 0)
            self.crawl_cursor["full_cycles"] = int(obj.get("full_cycles") or 0)

    def _save_crawl_cursor(self) -> None:
        self._put_sys_state("sys://crawl_cursor_v3", self.crawl_cursor, len(self.pool_by_id))

    def _hydrate(self) -> None:
        u, k = self._sb_creds()
        if not u or not k: return
        offset, batch_sz = 0, 1000
        while offset < MAX_HYDRATE_ROWS:
            try:
                url = f"{u}/rest/v1/radial_agent_phonebook?select=*&order=agent_id.asc&limit={batch_sz}&offset={offset}"
                with urllib.request.urlopen(urllib.request.Request(url, headers={"apikey": k, "Authorization": f"Bearer {k}"}), timeout=15) as r:
                    batch = json.loads(r.read().decode()) or []
                if not batch: break
                for row in batch:
                    aid = str(row.get("agent_id") or "").strip()
                    if not aid or aid.startswith("sys://") or row.get("protocol") == "SYS_STATE" or aid in SYNTHETIC_LEGACY_IDS:
                        continue
                    ep = str(row.get("endpoint") or "").strip()
                    if not ep or "registry.modelcontextprotocol.io/v0/servers" in ep:
                        continue
                    code = str(row.get("mglennp_code") or row.get("mgle_nnp_stamp") or "CEES-ZED").strip().upper()
                    guar_c = code[1:2] if len(code) >= 2 and code[1:2] in GRADE_TO_NIBBLE else "E"
                    raw_u64 = int(row.get("mglennp_u64") or row.get("mgle_nnp_64bit") or 0)
                    raw_lat = row.get("avg_latency_ms")
                    lat_val = float(raw_lat) if (raw_lat is not None and int(raw_lat) > 0) else (85.0 if guar_c in ("A", "B") else None)
                    zone = str(row.get("neighborhood") or infer_endpoint_geo_zone(ep, None, lat_val))[:1].upper()
                    raw_desc_full = str(row.get("description") or "")
                    clean_desc, raw_hyd_tools, hyd_wired = raw_desc_full, [], 0
                    if " /*RADIAL_TOOLS:" in raw_desc_full:
                        clean_desc, t_blob = raw_desc_full.split(" /*RADIAL_TOOLS:", 1)
                        if t_blob.endswith("*/"):
                            try:
                                parsed_rt = json.loads(t_blob[:-2])
                                if isinstance(parsed_rt, dict):
                                    raw_hyd_tools = parsed_rt.get("t") if isinstance(parsed_rt.get("t"), list) else []
                                    hyd_wired = int(parsed_rt.get("n") or len(raw_hyd_tools))
                                elif isinstance(parsed_rt, list):
                                    raw_hyd_tools = parsed_rt
                                    hyd_wired = len(raw_hyd_tools)
                            except Exception:
                                raw_hyd_tools, hyd_wired = [], 0
                    clean_desc = clean_desc.strip()
                    nm_s = str(row.get("name") or aid)
                    hyd_tools = []
                    for ht in raw_hyd_tools:
                        if not isinstance(ht, dict) or not ht.get("tool"): continue
                        NormIn = {}
                        for ik, iv in (ht.get("inputs") or {}).items():
                            ivs = str(iv)
                            if ivs.startswith("['") or ivs.startswith('["'):
                                ivs = "|".join(re.findall(r"[a-z]+", ivs.lower())[:3]) or "any"
                            NormIn[str(ik)[:36]] = ivs[:28]
                        entry = classify_tool_entry(str(ht.get("tool") or ""), str(ht.get("summary") or ""), NormIn, list(ht.get("required") or []))
                        if "callable_now" in ht: entry["callable_now"] = bool(ht["callable_now"]) and entry["callable_now"]
                        if ht.get("effect_class") in ("read_only", "side_effecting"): entry["effect_class"] = ht["effect_class"]
                        if entry["callable_now"] and entry["tool"] != "verified_schema":
                            hyd_tools.append(entry)
                    stub_dropped = max(0, len(raw_hyd_tools) - len(hyd_tools))
                    adj_wired = max(0, hyd_wired - stub_dropped)
                    det_auth, is_paid, auth_hint = detect_auth_and_payment_hints(nm_s, clean_desc, raw_hyd_tools, "none", (len(code) >= 4 and code[3:4] == "B"))
                    has_oauth_gate = (det_auth not in ("none", "x402_or_credit_gated"))
                    fp16 = str(row.get("fingerprint_hex") or "0000000000000000").replace("0x", "")[-16:].rjust(16, "0")
                    has_real_schema = (fp16 != "0000000000000000") and (len(hyd_tools) > 0 or len(raw_hyd_tools) == 0)
                    if ((raw_u64 >> 60) & 0x3) == SCHEMA_NIBBLE and raw_u64 > 0:
                        re_blob = f"{nm_s} {clean_desc} " + " ".join(f"{t.get('tool','')} {t.get('summary','')} {' '.join((t.get('inputs') or {}).keys())}" for t in hyd_tools)
                        re_low = re_blob.lower()
                        re_ws = set(_tokenize_words(re_low))
                        for tk in list(re_ws):
                            for pc in tk.split("_"):
                                if len(pc) >= 2: re_ws.add(pc)
                        c_mask = 0
                        for cn, kws in CAPABILITY_KEYWORDS.items():
                            if any(_kw_matches_text(k, re_low, re_ws) for k in kws):
                                c_mask |= CAPABILITY_BITS[cn]
                        if c_mask == 0:
                            c_mask = CAPABILITY_BITS["general"]
                        eff_zone = NIBBLE_TO_NEIGHBOR.get(((raw_u64 >> 32) >> 4) & 0xF, zone)
                        merit_c, lat_c = (code[0:1] or "C"), (code[2:3] or "B")
                        if guar_c in ("A", "B") and has_oauth_gate:
                            eff_guar, eff_auth, eff_tools, eff_st = "C", det_auth, len(hyd_tools), "LIVE_AUTH_GATED_GRADE_C"
                            r_clean = (raw_u64 & 0xFF000000) & (~READINESS_BITS["zero_auth_instant"])
                            eff_code, eff_u64, _ = MgleNnp64Codec.pack("C", "C", lat_c, "A", "Z", eff_zone, "S" if lat_c in ("A", "B") else "D", r_clean, c_mask)
                        elif guar_c in ("A", "B") and has_real_schema and not is_paid:
                            eff_guar, eff_auth, eff_tools, eff_st = "A", "none", max(1, adj_wired, len(hyd_tools)), "VERIFIED_LIVE_GRADE_A"
                            r_flags = (raw_u64 & 0xFF000000) | READINESS_BITS["zero_auth_instant"] | READINESS_BITS["poison_scan_clean"]
                            eff_code, eff_u64, _ = MgleNnp64Codec.pack(merit_c, "A", lat_c, "A", "Z", eff_zone, "S" if lat_c in ("A", "B") else "D", r_flags, c_mask)
                        elif guar_c in ("A", "B") and is_paid:
                            eff_guar, eff_auth, eff_tools, eff_st = "B", "x402_paid_per_call", max(1, adj_wired, len(hyd_tools)), "LIVE_X402_PAYABLE_GRADE_B"
                            r_flags = ((raw_u64 & 0xFF000000) | READINESS_BITS["x402_native_payable"]) & (~READINESS_BITS["zero_auth_instant"])
                            eff_code, eff_u64, _ = MgleNnp64Codec.pack("C", "B", lat_c, "B", "Z", eff_zone, "S" if lat_c in ("A", "B") else "D", r_flags, c_mask)
                        elif guar_c in ("A", "B") and not has_real_schema:
                            eff_guar, eff_auth, eff_tools, eff_st = "C", "auth_or_session_required", 0, "LIVE_AUTH_GATED_GRADE_C"
                            r_clean = (raw_u64 & 0xFF000000) & (~READINESS_BITS["zero_auth_instant"])
                            eff_code, eff_u64, _ = MgleNnp64Codec.pack("C", "C", lat_c, "A", "Z", eff_zone, "S" if lat_c in ("A", "B") else "D", r_clean, c_mask)
                        else:
                            eff_guar, eff_auth, eff_tools, eff_st = guar_c, "local_stdio_code", 0, f"INDEXED_GRADE_{guar_c}"
                            eff_u64, eff_code = (raw_u64 & ~0x00FFFFFF) | c_mask, code
                        rec = {
                            "agent_id": aid, "name": nm_s, "description": clean_desc[:400],
                            "endpoint": ep, "geo_zone": eff_zone,
                            "merit_grade": "C" if eff_guar in ("B", "C") else merit_c, "guarantee_grade": eff_guar,
                            "latency_grade": lat_c, "mgle_nnp_stamp": eff_code, "mgle_nnp_64bit": eff_u64,
                            "mgle_nnp_u64_hex": f"0x{eff_u64:016X}", "domain_mask": c_mask, "avg_latency_ms": lat_val,
                            "synaptic_weight": min(0.78, float(row.get("synaptic_weight") or 0.75)) if eff_guar == "C" else float(row.get("synaptic_weight") or 0.80),
                            "wired_tool_count": eff_tools,
                            "tool_schema_hash_16": fp16,
                            "auth_mode": eff_auth, "auth_hint": auth_hint if eff_auth == "none" else eff_auth, "payment_required": is_paid, "untrusted_third_party_text": True,
                            "poison_scan_clean": guar_c != "F",
                            "encounter_count": max(1, int(row.get("handshakes_completed") or 0)),
                            "room_completions": int(row.get("handshakes_completed") or 0),
                            "room_failures": int(row.get("handshakes_failed") or 0),
                            "dossier_json": {"agent_id": aid, "vendor_domain": extract_vendor_domain(ep), "geo_zone": eff_zone, "mgle_nnp_code": eff_code, "mgle_nnp_u64_hex": f"0x{eff_u64:016X}", "verified_tools": hyd_tools, "untrusted_third_party_text": True},
                            "audit_status": eff_st,
                            "last_audited_at": str(row.get("updated_at") or ""),
                        }
                        self.pool_by_id[aid] = rec
                    else:
                        prev_shim = {"synaptic_weight": row.get("synaptic_weight") or 0.80, "guarantee_grade": guar_c, "room_completions": row.get("handshakes_completed") or 0, "room_failures": row.get("handshakes_failed") or 0}
                        rec = build_agent_record_and_dossier(aid, nm_s, clean_desc, ep, guar_c in ("A", "B"), lat_val, lat_val, [], prev_record=prev_shim, geo_zone=zone)
                        if guar_c == "F":
                            rec["guarantee_grade"], rec["audit_status"] = "F", "SLASHED_POISON_GRADE_F"
                        self.pool_by_id[aid] = rec
                if len(batch) < batch_sz: break
                offset += batch_sz
            except Exception:
                break

    def _upsert_sb(self, rows: List[Dict[str, Any]]) -> None:
        u, k = self._sb_creds()
        if not u or not k or not rows: return
        dedup: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            aid = str(r.get("agent_id") or "").strip()
            if not aid or aid.startswith("sys://"): continue
            u64 = int(r.get("mgle_nnp_64bit") or 0) & 0x7FFFFFFFFFFFFFFF
            stamp = str(r.get("mgle_nnp_stamp") or "CEES-ZED")[:8]
            lat_raw = r.get("avg_latency_ms")
            lat_i = int(round(float(lat_raw))) if isinstance(lat_raw, (int, float)) else 0
            zn = str(r.get("geo_zone") or "E")[:1].upper()
            db_neigh = zn if zn in ("E", "A", "O", "G") else "G"
            vt_list = []
            for t in ((r.get("dossier_json") or {}).get("verified_tools") or [])[:5]:
                if not isinstance(t, dict) or not t.get("tool") or not t.get("callable_now", True): continue
                req_k = [str(x)[:32] for x in (t.get("required") or [])[:4]]
                inp_d = {str(ik)[:32]: str(iv)[:24] for ik, iv in list((t.get("inputs") or {}).items())[:5]}
                for rk in req_k:
                    if rk not in inp_d: inp_d[rk] = "any"
                vt_list.append({"tool": str(t.get("tool") or "")[:48], "summary": str(t.get("summary") or "")[:80], "required": req_k, "inputs": inp_d, "effect_class": str(t.get("effect_class") or "read_only")})
            rt_trailer = (" /*RADIAL_TOOLS:" + json.dumps({"n": max(int(r.get("wired_tool_count") or 0), len(vt_list)), "t": vt_list}, separators=(",", ":")) + "*/") if vt_list else ""
            clean_d = str(r.get("description") or "").split(" /*RADIAL_TOOLS:")[0].strip()
            safe_desc = clean_d[:max(80, 950 - len(rt_trailer))] + rt_trailer
            dedup[aid] = {
                "agent_id": aid,
                "name": str(r.get("name") or aid),
                "protocol": "A2A" if aid.startswith("a2a://") else "MCP",
                "endpoint": str(r.get("endpoint") or ""),
                "description": safe_desc,
                "radial_bitmask": int(r.get("domain_mask") or (u64 & 0x00FFFFFF)),
                "fingerprint_hex": str(r.get("tool_schema_hash_16") or "0000000000000000")[:16],
                "mglennp_code": stamp,
                "mglennp_u64": u64,
                "mglennp_u64_hex": f"0x{u64:016X}",
                "hop_ttl": 0,
                "synaptic_weight": round(float(r.get("synaptic_weight") or 0.80), 4),
                "avg_latency_ms": lat_i,
                "handshakes_completed": int(r.get("room_completions") or 0),
                "handshakes_failed": int(r.get("room_failures") or 0),
                "node_style": stamp.split("-")[1][0:1] if "-" in stamp and len(stamp.split("-")[1]) >= 1 else "Z",
                "neighborhood": db_neigh,
                "preference": stamp.split("-")[1][2:3] if "-" in stamp and len(stamp.split("-")[1]) >= 3 else "S",
                "agent_toll_usd": 0.0,
                "updated_at": str(r.get("last_audited_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()),
            }
        items = list(dedup.values())
        for idx in range(0, len(items), 50):
            chunk = items[idx:idx + 50]
            try:
                urllib.request.urlopen(urllib.request.Request(f"{u}/rest/v1/radial_agent_phonebook?on_conflict=agent_id", data=json.dumps(chunk).encode(), headers={"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}, method="POST"), timeout=15).close()
            except Exception:
                pass
    def enroll_genesis_apprentice(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        enr = payload.get("enrollment") if isinstance(payload.get("enrollment"), dict) else {}
        sig_hex = str(payload.get("signature_ed25519_hex") or "").strip()
        did = str(enr.get("did") or "").strip()
        try:
            pub32 = did_key_to_pubkey(did)
            sig64 = bytes.fromhex(sig_hex)
        except Exception as exc:
            return 400, {"enrolled": False, "error": f"INVALID_DID_OR_SIG_ENCODING: {exc}"}
        canon = json.dumps(enr, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not ed25519_verify(pub32, canon, sig64):
            return 403, {"enrolled": False, "error": "ED25519_SIGNATURE_VERIFICATION_FAILED"}
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ep = str(enr.get("endpoint") or "").strip()
        label = str(enr.get("agent_label") or "blank-canvas-apprentice")[:80]
        r_mask = READINESS_BITS["poison_scan_clean"] | READINESS_BITS["idempotent_read_safe"]
        stamp, u64, u64_hex = MgleNnp64Codec.pack("C", "B" if is_safe_public_endpoint(ep) else "D", "B", "A", "Z", infer_endpoint_geo_zone(ep) if ep else "G", "S", r_mask, CAPABILITY_BITS["general"])
        cert = {"did": did, "agent_id": did, "agent_label": label, "endpoint": ep, "credential_tier": "APPRENTICE", "economy_tier": "A", "seasoned_tenure_bit25": 0, "probationary_runs_required": 10, "mgle_nnp_stamp": stamp, "mgle_nnp_u64_hex": u64_hex, "enrolled_at_utc": now_iso}
        is_new = did not in self.enrolled_apprentices
        self.enrolled_apprentices[did] = cert
        if is_safe_public_endpoint(ep):
            rec = interrogate_live_endpoint({"agent_id": did, "name": label, "description": "Genesis Credentialed Apprentice", "endpoint": ep})
            self.pool_by_id[did] = rec; self._upsert_sb([rec])
        if is_new: self.record_event("apprentices_enrolled")
        return 200, {"enrolled": True, "credential": cert, "scout_barter_claim_url": "https://radialswitchboard.com/v1/work/claim"}

    def verify_outcome(self, aid: str, tkt: str, ok: bool, obs_ms: Optional[float] = None) -> Dict[str, Any]:
        valid, rsn = verify_execution_ticket(aid, tkt)
        if not valid or tkt in self.redeemed_tickets: return {"agent_id": aid, "ticket_valid": False, "reason": rsn, "sabotage_blocked": True, "quarantined": False}
        rec = self.pool_by_id.get(aid)
        if not rec: return {"agent_id": aid, "ticket_valid": True, "quarantined": False}
        self.redeemed_tickets.add(tkt); self.record_event("outcome_reports_verified")
        if ok:
            rec["room_completions"] = int(rec.get("room_completions") or 0) + 1
            rec["synaptic_weight"] = min(0.99, round(float(rec.get("synaptic_weight") or 0.80) + 0.03, 4))
            upd = build_agent_record_and_dossier(rec["agent_id"], rec["name"], rec.get("description", ""), rec["endpoint"], True, rec.get("avg_latency_ms"), obs_ms or rec.get("avg_latency_ms"), [], rec.get("auth_mode", "none"), prev_record=rec, geo_zone=rec.get("geo_zone"))
            self.pool_by_id[aid] = upd; self._upsert_sb([upd])
            return {"agent_id": aid, "ticket_valid": True, "sabotage_blocked": False, "quarantined": False, "updated_synaptic_weight": upd["synaptic_weight"]}
        probed = interrogate_live_endpoint(rec)
        alive = probed.get("guarantee_grade") in ("A", "B")
        self.pool_by_id[aid] = probed; self._upsert_sb([probed])
        return {"agent_id": aid, "ticket_valid": True, "independent_probe_alive": alive, "quarantined": not alive}

    def ensure_finalists_hydrated(self, caps: Sequence[str], zero_auth: bool = True, max_lat: str = "C", top_k: int = DEFAULT_FLASH_TOP_K, mode: str = "top10_varied", caller_region: str = "GLOBAL", intent_text: str = "") -> Dict[str, Any]:
        out = flash_unsorted_pool(list(self.pool_by_id.values()), caps, zero_auth=zero_auth, max_lat=max_lat, top_k=top_k, mode=mode, caller_region=caller_region, intent_text=intent_text)
        if not self.hydrate_external:
            return out
        missing = [self.pool_by_id[f["agent_id"]] for f in (out.get("finalists") or []) if (not f.get("tools_preview") or all(t.get("tool") == "verified_schema" for t in (f.get("tools_preview") or []))) and f.get("agent_id") in self.pool_by_id]
        if missing:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(missing))) as ex:
                refreshed = list(ex.map(lambda r: interrogate_live_endpoint(r, timeout_sec=3.0), missing))
            for prb in refreshed:
                self.pool_by_id[prb["agent_id"]] = prb
            threading.Thread(target=self._upsert_sb, args=(refreshed,), daemon=True).start()
            out = flash_unsorted_pool(list(self.pool_by_id.values()), caps, zero_auth=zero_auth, max_lat=max_lat, top_k=top_k, mode=mode, caller_region=caller_region, intent_text=intent_text)
        if zero_auth:
            valid_fins = [f for f in (out.get("finalists") or []) if f.get("tools_preview") and int(f.get("wired_tool_count") or 0) >= len(f.get("tools_preview") or [])]
            for idx, vf in enumerate(valid_fins, 1):
                vf["rank"] = idx
            out["finalists"] = valid_fins
            out["finalist_count"] = len(valid_fins)
            out["top_match"] = valid_fins[0] if valid_fins else {}
        return out

    def run_live_scout_sweep(self, limit: int = 80) -> Dict[str, Any]:
        lim = max(1, min(100, int(limit or 80)))
        with self._lock:
            if self.telemetry["scout_currently_running"]:
                return {"status": "already_running", "total_pool": len(self.pool_by_id), "cursor": self.crawl_cursor["registry_cursor"]}
            self.telemetry["scout_currently_running"] = True
        try:
            cands_by_id: Dict[str, Dict[str, Any]] = {}
            next_cur = self.crawl_cursor.get("registry_cursor") or ""
            try:
                url = f"https://registry.modelcontextprotocol.io/v0.1/servers?limit={lim}&version=latest" + (f"&cursor={urllib.parse.quote(next_cur)}" if next_cur else "")
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": f"MglennP-RadialScout/{SPEC_VERSION}"}), timeout=14) as r:
                    pl = json.loads(r.read().decode())
                fetched_next = str((pl.get("metadata") or {}).get("nextCursor") or "")
                self.crawl_cursor["pages_completed"] = int(self.crawl_cursor.get("pages_completed") or 0) + 1
                if not fetched_next:
                    self.crawl_cursor["full_cycles"] = int(self.crawl_cursor.get("full_cycles") or 0) + 1
                self.crawl_cursor["registry_cursor"] = fetched_next
                for ent in (pl.get("servers") or []):
                    sv = ent.get("server") if isinstance(ent, dict) and isinstance(ent.get("server"), dict) else ent
                    if not isinstance(sv, dict) or not sv.get("name"): continue
                    rem = next((str(x["url"]).strip() for x in (sv.get("remotes") or []) if isinstance(x, dict) and str(x.get("url") or "").startswith("https://")), "")
                    rep = str((sv.get("repository") or {}).get("url") or "").strip() if isinstance(sv.get("repository"), dict) else ""
                    target_ep = rem or rep
                    if target_ep:
                        aid = f"mcp://{str(sv['name']).strip().lower()}"
                        prev = self.pool_by_id.get(aid) or {}
                        cands_by_id[aid] = {**prev, "agent_id": aid, "name": str(sv.get("title") or sv["name"]), "description": str(sv.get("description") or "")[:300], "endpoint": target_ep}
            except Exception:
                pass
            cands = list(cands_by_id.values())
            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
                audited = list(ex.map(interrogate_live_endpoint, cands)) if cands else []
            for rec in audited:
                self.pool_by_id[rec["agent_id"]] = rec
            if audited:
                self._upsert_sb(audited)
            if self.hydrate_external:
                self._save_crawl_cursor()
            with self._lock:
                self.telemetry["scout_sweeps_completed"] = int(self.telemetry.get("scout_sweeps_completed") or 0) + 1
                self.telemetry["last_scout_sweep_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if self.hydrate_external:
                threading.Thread(target=self._save_telemetry, daemon=True).start()
            ab = sum(1 for r in self.pool_by_id.values() if r.get("guarantee_grade") in ("A", "B"))
            return {"status": "completed", "probed_count": len(audited), "total_pool": len(self.pool_by_id), "live_callable_ab": ab, "pages_completed": self.crawl_cursor["pages_completed"], "next_cursor_saved": bool(self.crawl_cursor["registry_cursor"])}
        finally:
            with self._lock:
                self.telemetry["scout_currently_running"] = False

    def _daemon(self) -> None:
        time.sleep(2.0)
        while True:
            try: self.run_live_scout_sweep(80)
            except Exception: pass
            time.sleep(600.0)

MCP_READONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

MCP_WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

MCP_SERVER_TOOLS = [
    {
        "name": "matchmake_agent_crew",
        "title": "Matchmake 64-Bit Agent Shortlist or 3-Agent Crew",
        "description": "Rank live heartbeat-verified MCP and A2A endpoints using 64-bit MGLE-NNP bitwise capability masks and return either a provider-diverse shortlist or a 3-agent complementary crew (Compute + Domain + Verifier) with single-use execution tickets. Use when selecting callable agents for a task; use search_agent_directory for raw keyword browsing or get_agent_dossier when you already have an agent_id.",
        "annotations": MCP_READONLY_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Natural-language task intent used to infer required 64-bit capability switches when capabilities is omitted."
                },
                "capabilities": {
                    "type": "array",
                    "description": "Optional explicit MGLE-NNP capability switch names (e.g. sql, database, finance_data, file_parse, math_verify, code_exec, web_fetch, search_rag).",
                    "items": {
                        "type": "string",
                        "description": "Canonical capability switch identifier from Bits 0..23."
                    }
                },
                "mode": {
                    "type": "string",
                    "enum": ["top10_varied", "crew"],
                    "description": "Routing policy: 'top10_varied' for ranked shortlist across distinct vendors, or 'crew' for a 3-role complementary triad."
                },
                "caller_region": {
                    "type": "string",
                    "enum": ["E", "W", "U", "P", "GLOBAL"],
                    "description": "Caller geographic zone for round-trip latency affinity ('E' US-East, 'W' US-West, 'U' Europe, 'P' APAC, 'GLOBAL' any)."
                },
                "require_instant_zero_auth": {
                    "type": "boolean",
                    "description": "True (default: true) restricts results strictly to open zero-credential endpoints with verified non-zero tools/list schemas callable immediately without API keys or OAuth."
                },
                "max_latency_grade": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "ANY"],
                    "description": "Worst acceptable Virginia Scout RTT grade ('A' <=120ms, 'B' <=300ms, 'C' <=700ms default, 'D' <=1500ms, 'ANY' unrestricted live RTT)."
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 25,
                    "description": "Maximum number of ranked candidates to return (1..25, default 10)."
                }
            }
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "description": "Applied routing policy identifier."},
                "finalist_count": {"type": "integer", "description": "Number of matched endpoints returned."},
                "scanned_pool_count": {"type": "integer", "description": "Total audited phonebook records scanned."},
                "finalists": {"type": "array", "description": "Ranked candidate agent records including endpoint URL, 64-bit hex ID, and execution_ticket.", "items": {"type": "object"}}
            },
            "required": ["mode", "finalist_count", "finalists"]
        }
    },
    {
        "name": "search_agent_directory",
        "title": "Search Live Audited Agent Directory",
        "description": "Browse and filter the audited Radial Switchboard phonebook by keyword substring and Virginia Scout health grade without consuming matchmaking call quota. Use when exploring catalog coverage by name, vendor, or grade; use matchmake_agent_crew instead when ranking capability-matched finalists for execution.",
        "annotations": MCP_READONLY_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional case-insensitive keyword filter matched against agent_id, name, description, and endpoint URL."
                },
                "grade_filter": {
                    "type": "string",
                    "enum": ["AB", "A", "B", "C", "D", "ALL"],
                    "description": "Filter by Virginia Scout audit grade ('AB' live <=350ms default, 'A' <=150ms, 'B' <=350ms, 'C' <=700ms, 'D' offline code, 'ALL' every non-poison record)."
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Maximum number of directory records to return (1..50, default 20)."
                }
            }
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total_matching": {"type": "integer", "description": "Total phonebook records matching the filter."},
                "returned_count": {"type": "integer", "description": "Number of records included in agents."},
                "agents": {"type": "array", "description": "Matching directory records with grade, coupler, and endpoint metadata.", "items": {"type": "object"}}
            },
            "required": ["total_matching", "returned_count", "agents"]
        }
    },
    {
        "name": "get_agent_dossier",
        "title": "Get Single Agent Security & Runtime Dossier",
        "description": "Retrieve the complete 4-point Virginia Scout runtime heartbeat audit, measured RTT latency, 64-bit MGLE-NNP coupler breakdown, and SHA-256 tool-schema hash for one exact agent_id. Use only when inspecting a known agent_id; use search_agent_directory if you need to find the agent_id first.",
        "annotations": MCP_READONLY_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Exact agent or MCP server identifier from the Radial Switchboard phonebook (e.g. 'mcp://...' or registry slug)."
                }
            },
            "required": ["agent_id"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "found": {"type": "boolean", "description": "True when agent_id exists in the audited phonebook."},
                "agent_id": {"type": "string", "description": "Requested agent identifier."},
                "dossier": {"type": "object", "description": "Full runtime audit record, coupler code, and schema hash."}
            },
            "required": ["found", "agent_id"]
        }
    },
    {
        "name": "get_switchboard_telemetry",
        "title": "Get Live Switchboard Health & Pool Telemetry",
        "description": "Return global US-EAST4 switchboard health, Grade A/B/D/E/F pool counts, autonomous registry crawl cursor state, and external hook telemetry. Use for system-wide status and pool metrics; use get_agent_dossier for an individual agent.",
        "annotations": MCP_READONLY_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_recent_activity": {
                    "type": "boolean",
                    "description": "Public privacy protection strips raw caller User-Agent/IP entries by default (default false); only recent_activity_count is returned publicly."
                }
            }
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Service operational state ('ok')."},
                "spec_version": {"type": "string", "description": "Active Radial Switchboard specification revision."},
                "total_unsorted_pool": {"type": "integer", "description": "Total indexed MCP and A2A records."},
                "live_callable_ab": {"type": "integer", "description": "Count of live verified Grade A and Grade B endpoints."}
            },
            "required": ["status", "spec_version", "total_unsorted_pool", "live_callable_ab"]
        }
    },
    {
        "name": "register_agent_endpoint",
        "title": "Register or Re-Audit Public MCP/A2A Endpoint",
        "description": "Submit a public HTTPS MCP or A2A endpoint for immediate live SSRF-guarded Virginia Scout interrogation, 64-bit MGLE-NNP grading, and directory indexing. Use when enrolling a new server or appealing a quarantined grade; do not use for private localhost/RFC1918 URLs.",
        "annotations": MCP_WRITE_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "Publicly reachable HTTPS MCP or A2A endpoint URL to interrogate in real time."
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional canonical slug or identifier (e.g. 'com.example/my-mcp'); generated automatically if omitted."
                },
                "description": {
                    "type": "string",
                    "description": "Optional summary of capabilities or reason for re-audit."
                }
            },
            "required": ["endpoint"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "registered": {"type": "boolean", "description": "True when SSRF validation passed and live interrogation completed."},
                "appeal_id": {"type": "string", "description": "Audit log reference ID."},
                "audit_status": {"type": "string", "description": "Assigned Virginia Scout runtime audit status."},
                "updated_record": {"type": "object", "description": "Resulting phonebook record and 64-bit coupler."}
            },
            "required": ["registered", "audit_status"]
        }
    },
    {
        "name": "report_execution_outcome",
        "title": "Report Post-Handshake Execution Outcome",
        "description": "Submit a single-use HMAC execution_ticket from matchmake_agent_crew to record empirical downstream task completion or failure (+0.05 clean delivery / -0.20 timeout or schema failure on Byte-2 Guarantee grade). Use after invoking a matched agent to close the quality feedback loop.",
        "annotations": MCP_WRITE_ANNOTATIONS,
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Target agent_id that executed the downstream call."
                },
                "execution_ticket": {
                    "type": "string",
                    "description": "Single-use HMAC execution_ticket issued by matchmake_agent_crew."
                },
                "outcome_success": {
                    "type": "boolean",
                    "description": "True if the downstream agent fulfilled its schema contract cleanly; false on timeout, HTTP error, or malformed output."
                },
                "observed_latency_ms": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Optional caller-observed round-trip execution latency in milliseconds."
                }
            },
            "required": ["agent_id", "execution_ticket", "outcome_success"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "ticket_valid": {"type": "boolean", "description": "True when the single-use HMAC ticket passed verification and updated telemetry."},
                "agent_id": {"type": "string", "description": "Evaluated target agent_id."}
            },
            "required": ["ticket_valid"]
        }
    },
]

def build_llms_txt(treasury_address: str) -> str:
    bt = chr(96) * 3
    tool_names = ", ".join(t["name"] for t in MCP_SERVER_TOOLS)
    caps = ", ".join(CAPABILITY_NAMES)
    req_ex = json.dumps({
        "intent": "postgres sql database finance verification",
        "capabilities": ["sql", "database", "finance_data", "math_verify"],
        "mode": "top10_varied",
        "caller_region": "GLOBAL",
        "require_instant_zero_auth": True,
        "max_latency_grade": "C",
        "top_k": 10,
    }, indent=2)
    lines = [
        f"# MglennP Radial Switchboard (Spec Rev {SPEC_VERSION})",
        "> Autonomous 64-bit MGLE-NNP AI-to-AI MCP & A2A matchmaker, poison/SSRF auditor,",
        "> 3-agent crew router, and Base USDC x402 / $0 Canary Scout clearinghouse.",
        "",
        "## 1. Streamable HTTP MCP (Recommended for MCP Clients & Autonomous Hosts)",
        "- Endpoint: POST https://radialswitchboard.com/mcp",
        "- Protocol: MCP Streamable HTTP (2026-07-28 & 2025-06-18)",
        "- Official MCP Registry ID: com.radialswitchboard/matchmaker",
        f"- Live MCP Tools (6): {tool_names} (legacy alias supported: flash_matchmake_agents)",
        "- Zero-Shot Handoff Guarantee: matchmake_agent_crew defaults to require_instant_zero_auth=true and max_latency_grade='C' (<=700ms), returning only endpoints with verified non-zero tools/list schemas plus transport, protocol_version, tools_preview, and single-use execution_ticket.",
        f"- Quota & Headers: {FREE_DAILY_STARTER_CALLS} matchmaking calls/UTC-day automatic per IP (initialize, tools/list, search_agent_directory, get_agent_dossier, get_switchboard_telemetry, and report_execution_outcome are UNMETERED). Optional header X-Radial-Pass on POST /mcp or POST /v1/flash; responses return X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset.",
        "",
        "## 2. Direct REST Matchmaking (POST https://radialswitchboard.com/v1/flash)",
        f"{bt}json",
        req_ex,
        bt,
        "- Set mode='crew' for a 3-agent provider-independent triad (Compute + Domain + Verifier).",
        f"- Valid capabilities (Bits 0..23): {caps}",
        "- Valid max_latency_grade: A (<=120ms), B (<=300ms), C (<=700ms default), D (<=1500ms), ANY (unrestricted live RTT). Note: Grade E in pool health denotes quarantined offline endpoints.",
        "- Valid caller_region: E (US-East), W (US-West), U (Europe), P (APAC), GLOBAL.",
        "- Redeem single-use execution_ticket via POST /v1/outcome (or MCP report_execution_outcome) after worker execution.",
        "",
        "## 3. Autonomous 402 Access Lanes (Zero-Human-Intervention)",
        f"1. Free Daily Starter Pass ({FREE_DAILY_STARTER_CALLS}/UTC-day): POST https://radialswitchboard.com/v1/keys/starter -> pass X-Radial-Pass header.",
        f"2. $0 Canary Scout Compute Barter ({WORK_PASS_CREDITS} handshakes): POST /v1/work/claim -> POST /v1/work/submit",
        "   Worker script: GET https://radialswitchboard.com/radial_apprentice_worker.py",
        f"3. Base Mainnet USDC x402 V2 ({CASH_PASS_PRICE_USDC} USDC = {CASH_PASS_CREDITS} handshakes):",
        f"   Network: {BASE_MAINNET_CHAIN_ID} | Asset: {BASE_USDC_CONTRACT} | PayTo: {treasury_address}",
        "",
        "## 4. Apprentice Credentialing & Signed Scouting Phonebooks",
        "- W3C did:key (Ed25519) Genesis Enrollment: POST https://radialswitchboard.com/v1/enroll",
        "- HMAC-Signed Grade A/B Phonebook: GET https://radialswitchboard.com/v1/phonebook/export?format=jsonl&grades=AB",
        "- OpenAPI 3.1 Schema: https://radialswitchboard.com/openapi.json",
        "- Linux Foundation A2A v1.0 Card: https://radialswitchboard.com/.well-known/agent-card.json",
        f"- Contact: {CONTACT_EMAIL}",
    ]
    return "\n".join(lines) + "\n"

def build_openapi_spec(treasury_address: str) -> Dict[str, Any]:
    rl_hdrs = {
        "X-RateLimit-Limit": {"schema": {"type": "integer"}, "description": "Matchmaking quota ceiling for active pass or daily IP tier."},
        "X-RateLimit-Remaining": {"schema": {"type": "integer"}, "description": "Remaining matchmaking handshakes before HTTP 402 challenge."},
        "X-RateLimit-Reset": {"schema": {"type": "integer"}, "description": "UTC Unix timestamp when free daily allowance resets."},
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "MglennP Radial Switchboard API",
            "version": SPEC_VERSION,
            "summary": "64-bit MGLE-NNP AI-to-AI MCP & A2A zero-shot agent matchmaker and runtime auditor.",
            "contact": {"name": "MglennP", "email": CONTACT_EMAIL, "url": "https://radialswitchboard.com"},
            "license": {"name": "MIT", "url": f"{PUBLIC_GITHUB_REPO}/blob/main/LICENSE"},
        },
        "servers": [{"url": "https://radialswitchboard.com", "description": "Production US-East4"}],
        "x-mcp-streamable-http": "https://radialswitchboard.com/mcp",
        "x-a2a-agent-card": "https://radialswitchboard.com/.well-known/agent-card.json",
        "x-usdc-treasury-base": treasury_address,
        "components": {
            "securitySchemes": {
                "RadialPassHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Radial-Pass",
                    "description": f"Optional stateless HMAC pass token (rs3.*). Unauthenticated callers automatically receive {FREE_DAILY_STARTER_CALLS} matchmaking calls/UTC-day per IP; mint explicitly via POST /v1/keys/starter, POST /v1/work/submit, or Base USDC x402.",
                }
            },
            "schemas": {
                "FinalistHandoffManifest": {
                    "type": "object",
                    "required": ["rank", "agent_id", "endpoint", "transport", "protocol_version", "auth_mode", "wired_tool_count", "tools_preview", "execution_ticket"],
                    "properties": {
                        "rank": {"type": "integer"},
                        "agent_id": {"type": "string"},
                        "name": {"type": "string"},
                        "endpoint": {"type": "string", "format": "uri"},
                        "transport": {"type": "string", "enum": ["mcp-streamable-http", "mcp-sse", "a2a-http-json", "stdio-package-repo"]},
                        "protocol_version": {"type": "string"},
                        "mgle_nnp_stamp": {"type": "string"},
                        "mgle_nnp_u64_hex": {"type": "string"},
                        "warm_latency_ms": {"type": ["number", "null"]},
                        "auth_mode": {"type": "string"},
                        "wired_tool_count": {"type": "integer"},
                        "tool_schema_hash_16": {"type": "string"},
                        "tools_preview": {"type": "array", "items": {"type": "object", "properties": {"tool": {"type": "string"}, "required": {"type": "array", "items": {"type": "string"}}, "inputs": {"type": "object"}}}},
                        "last_audited_at": {"type": ["string", "null"]},
                        "execution_ticket": {"type": "string"},
                    },
                },
                "FlashMatchmakeResponse": {
                    "type": "object",
                    "required": ["spec_version", "match_mode", "finalist_count", "finalists"],
                    "properties": {
                        "spec_version": {"type": "string"},
                        "pool_scanned_unsorted": {"type": "integer"},
                        "single_pass_flash_ms": {"type": "number"},
                        "match_mode": {"type": "string"},
                        "coupler_applied": {"type": "string"},
                        "required_lower32_hex": {"type": "string"},
                        "finalist_count": {"type": "integer"},
                        "finalists": {"type": "array", "items": {"$ref": "#/components/schemas/FinalistHandoffManifest"}},
                    },
                },
                "Gate402Challenge": {
                    "type": "object",
                    "required": ["http_status", "error", "lane_a_x402_usdc", "lane_b_compute_scout_duty"],
                    "properties": {
                        "http_status": {"type": "integer", "const": 402},
                        "error": {"type": "string"},
                        "lane_a_x402_usdc": {"type": "object", "properties": {"network": {"type": "string"}, "asset_contract": {"type": "string"}, "amount_usdc": {"type": "number"}, "pay_to_address": {"type": "string"}, "grants_handshakes": {"type": "integer"}}},
                        "lane_b_compute_scout_duty": {"type": "object", "properties": {"claim_endpoint": {"type": "string"}, "submit_endpoint": {"type": "string"}, "grants_handshakes": {"type": "integer"}}},
                    },
                },
            },
        },
        "paths": {
            "/mcp": {
                "post": {
                    "operationId": "mcpJsonRpc",
                    "summary": "Streamable HTTP MCP JSON-RPC 2.0 endpoint exposing 6 tools: " + ", ".join(t["name"] for t in MCP_SERVER_TOOLS),
                    "security": [{}, {"RadialPassHeader": []}],
                    "parameters": [{"name": "X-Radial-Pass", "in": "header", "required": False, "schema": {"type": "string"}}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["jsonrpc", "method"], "properties": {"jsonrpc": {"type": "string", "const": "2.0"}, "id": {"type": ["integer", "string"]}, "method": {"type": "string", "enum": ["initialize", "notifications/initialized", "ping", "tools/list", "tools/call"]}, "params": {"type": "object"}}}}}},
                    "responses": {
                        "200": {"description": "JSON-RPC 2.0 response with compact text + structuredContent", "headers": rl_hdrs, "content": {"application/json": {"schema": {"type": "object", "properties": {"jsonrpc": {"type": "string"}, "id": {"type": ["integer", "string"]}, "result": {"type": "object"}}}}}},
                        "402": {"description": "x402 USDC or $0 Canary Scout challenge when daily free quota is exhausted", "headers": rl_hdrs, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Gate402Challenge"}}}},
                    },
                }
            },
            "/v1/flash": {
                "post": {
                    "operationId": "flashMatchmakeAgents",
                    "summary": "Sub-second 64-bit MGLE-NNP zero-shot matchmaker (Top-10 varied or 3-agent crew)",
                    "security": [{}, {"RadialPassHeader": []}],
                    "parameters": [{"name": "X-Radial-Pass", "in": "header", "required": False, "schema": {"type": "string"}}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"intent": {"type": "string", "description": "Natural-language task description (required if capabilities omitted)."}, "capabilities": {"type": "array", "items": {"type": "string", "enum": list(CAPABILITY_NAMES)}}, "mode": {"type": "string", "enum": ["top10_varied", "crew"], "default": "top10_varied"}, "caller_region": {"type": "string", "enum": ["GLOBAL", "E", "W", "U", "P"], "default": "GLOBAL"}, "require_instant_zero_auth": {"type": "boolean", "default": True}, "max_latency_grade": {"type": "string", "enum": ["A", "B", "C", "D", "ANY"], "default": "C"}, "top_k": {"type": "integer", "minimum": 1, "maximum": MAX_FLASH_TOP_K, "default": DEFAULT_FLASH_TOP_K}}}}}},
                    "responses": {
                        "200": {"description": "Ranked zero-shot finalists with handoff manifests and execution tickets", "headers": rl_hdrs, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/FlashMatchmakeResponse"}}}},
                        "402": {"description": "Payment or Canary Scout work required", "headers": rl_hdrs, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Gate402Challenge"}}}},
                    },
                }
            },
            "/v1/keys/starter": {
                "post": {
                    "operationId": "mintDailyStarterKey",
                    "summary": f"Mint stateless free daily X-Radial-Pass ({FREE_DAILY_STARTER_CALLS} handshakes/UTC-day)",
                    "responses": {"200": {"description": "Signed rs3.starter token", "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "pass_token": {"type": "string"}, "header_name": {"type": "string"}, "remaining_credits": {"type": "integer"}, "expires_unix": {"type": "integer"}}}}}}},
                }
            },
            "/v1/work/claim": {
                "post": {
                    "operationId": "claimCanaryScoutWork",
                    "summary": "Claim $0 Canary Scout compute-barter assignment",
                    "requestBody": {"required": False, "content": {"application/json": {"schema": {"type": "object"}}}},
                    "responses": {"200": {"description": "4-endpoint scout challenge", "content": {"application/json": {"schema": {"type": "object", "properties": {"assignment_id": {"type": "string"}, "targets": {"type": "array", "items": {"type": "object"}}}}}}}},
                }
            },
            "/v1/work/submit": {
                "post": {
                    "operationId": "submitCanaryScoutWork",
                    "summary": f"Submit 16-hex tool schema hashes for a {WORK_PASS_CREDITS}-handshake X-Radial-Pass",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["assignment_id", "results"], "properties": {"assignment_id": {"type": "string"}, "region": {"type": "string"}, "results": {"type": "array", "items": {"type": "object", "required": ["agent_id", "tool_schema_hash_16"], "properties": {"agent_id": {"type": "string"}, "tool_schema_hash_16": {"type": "string"}}}}}}}}},
                    "responses": {"200": {"description": "Work pass issued", "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "pass_token": {"type": "string"}, "granted_handshakes": {"type": "integer"}}}}}}},
                }
            },
            "/v1/enroll": {
                "post": {
                    "operationId": "enrollGenesisApprentice",
                    "summary": "Enroll W3C did:key (Ed25519) Apprentice agent",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["enrollment", "signature_ed25519_hex"], "properties": {"enrollment": {"type": "object"}, "signature_ed25519_hex": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "Apprentice credential issued", "content": {"application/json": {"schema": {"type": "object", "properties": {"enrolled": {"type": "boolean"}, "credential": {"type": "object"}}}}}}},
                }
            },
            "/v1/outcome": {
                "post": {
                    "operationId": "reportExecutionOutcome",
                    "summary": "Redeem single-use HMAC execution_ticket and update synaptic reputation",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["agent_id", "execution_ticket", "outcome_success"], "properties": {"agent_id": {"type": "string"}, "execution_ticket": {"type": "string"}, "outcome_success": {"type": "boolean"}, "observed_latency_ms": {"type": "number"}}}}}},
                    "responses": {"200": {"description": "Ticket verified", "content": {"application/json": {"schema": {"type": "object", "properties": {"ticket_valid": {"type": "boolean"}, "synaptic_weight": {"type": "number"}}}}}}, "403": {"description": "Invalid or replayed HMAC ticket"}},
                }
            },
            "/v1/phonebook/export": {
                "get": {
                    "operationId": "exportSignedPhonebook",
                    "summary": "Download HMAC-signed Grade A/B directory snapshot (JSONL or CSV)",
                    "parameters": [{"name": "format", "in": "query", "schema": {"type": "string", "enum": ["jsonl", "csv"]}}, {"name": "grades", "in": "query", "schema": {"type": "string", "enum": ["AB", "ALL"]}}],
                    "responses": {"200": {"description": "Signed NDJSON or CSV phonebook stream"}},
                }
            },
            "/v1/health": {
                "get": {
                    "operationId": "getSwitchboardHealth",
                    "summary": "Live audited pool counts, crawler cursor state, and separated call vs probe telemetry",
                    "responses": {"200": {"description": "Health JSON", "content": {"application/json": {"schema": {"type": "object", "required": ["status", "spec_version", "total_unsorted_pool", "live_callable_ab", "telemetry"], "properties": {"status": {"type": "string"}, "spec_version": {"type": "string"}, "total_unsorted_pool": {"type": "integer"}, "live_callable_ab": {"type": "integer"}, "telemetry": {"type": "object"}}}}}}},
                }
            },
        },
    }

def build_a2a_agent_card() -> Dict[str, Any]:
    return {
        "name": "MglennP Radial Switchboard",
        "description": "Autonomous 64-bit MGLE-NNP AI-to-AI agent matchmaker, zero-auth tools/list verifier, 3-agent complementary crew assembler, and Base USDC x402 / $0 Canary Scout clearinghouse.",
        "version": SPEC_VERSION,
        "url": "https://radialswitchboard.com/mcp",
        "documentationUrl": "https://radialswitchboard.com/llms.txt",
        "openApiUrl": "https://radialswitchboard.com/openapi.json",
        "provider": {"organization": "MglennP", "url": "https://radialswitchboard.com", "contactEmail": CONTACT_EMAIL},
        "supportedInterfaces": [
            {"url": "https://radialswitchboard.com/mcp", "protocolBinding": "MCP-STREAMABLE-HTTP", "protocolVersion": "2026-07-28"},
            {"url": "https://radialswitchboard.com/v1/flash", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"},
        ],
        "authentication": {
            "schemes": ["none", "X-Radial-Pass", "x402-base-usdc"],
            "headerName": "X-Radial-Pass",
            "freeStarterEndpoint": "https://radialswitchboard.com/v1/keys/starter",
            "canaryWorkClaimEndpoint": "https://radialswitchboard.com/v1/work/claim",
        },
        "rateLimit": {
            "freeCallsPerUtcDayPerIp": FREE_DAILY_STARTER_CALLS,
            "unmeteredMethods": ["initialize", "tools/list", "search_agent_directory", "get_agent_dossier", "get_switchboard_telemetry", "report_execution_outcome"],
            "meteredMethods": ["matchmake_agent_crew", "POST /v1/flash"],
            "responseHeaders": ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
        },
        "mcpTools": [t["name"] for t in MCP_SERVER_TOOLS],
        "capabilities": {"streaming": False, "pushNotifications": False, "extendedAgentCard": False},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {"id": "matchmake-agent-crew", "name": "64-Bit Zero-Auth Agent Matchmaking", "description": "Finds verified live Grade A zero-auth MCP & A2A endpoints in sub-second bitwise scans with vendor/schema diversity and tools_preview manifests.", "tags": ["mcp", "a2a", "matchmaker", "directory", "x402"]},
            {"id": "assemble-3-agent-crew", "name": "3-Agent Complementary Crew Triad", "description": "Assembles an independent Compute + Domain + Verifier agent triad across distinct vendors.", "tags": ["crew", "orchestration", "verification"]},
            {"id": "genesis-apprentice-enroll", "name": "Ed25519 did:key Apprentice Credentialing", "description": "Registers self-certifying Blank-Canvas Apprentice agents and issues $0 Canary Scout compute-barter passes.", "tags": ["did:key", "ed25519", "credentialing"]},
        ],
    }

class ThreadingHTTPServerReuse(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

def create_http_handler(runtime: StandaloneSwitchboardRuntime):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _bytes(self, code: int, ct: str, raw: bytes, extra_headers: Optional[Dict[str, str]] = None) -> None:
            self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Radial-Pass, X-Radial-Caller-Region, PAYMENT-SIGNATURE, mcp-protocol-version, Mcp-Session-Id")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Expose-Headers", "PAYMENT-REQUIRED, PAYMENT-RESPONSE, X-Radial-Snapshot-HMAC, X-Radial-Export-Count, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset")
            if extra_headers:
                for hk, hv in extra_headers.items(): self.send_header(hk, hv)
            self.end_headers(); self.wfile.write(raw)

        def _json(self, code: int, obj: Any, extra_headers: Optional[Dict[str, str]] = None) -> None:
            self._bytes(code, "application/json; charset=utf-8", json.dumps(obj, indent=2).encode("utf-8"), extra_headers)

        def do_OPTIONS(self) -> None:
            self._bytes(204, "text/plain", b"")

        def do_HEAD(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _caller_region(self, qs: Optional[Dict[str, List[str]]] = None, body: Optional[Dict[str, Any]] = None) -> str:
            explicit = ""
            if isinstance(body, dict) and body.get("caller_region"): explicit = str(body["caller_region"])
            elif qs and qs.get("caller_region"): explicit = str(qs["caller_region"][0])
            elif self.headers.get("X-Radial-Caller-Region"): explicit = str(self.headers.get("X-Radial-Caller-Region"))
            cc = str(self.headers.get("CF-IPCountry") or self.headers.get("X-AppEngine-Country") or "")
            return normalize_caller_region(explicit, cc)

        def _health(self) -> Dict[str, Any]:
            recs = list(runtime.pool_by_id.values())
            ab = sum(1 for r in recs if r.get("guarantee_grade") in ("A", "B"))
            gd = sum(1 for r in recs if r.get("guarantee_grade") == "D")
            ge = sum(1 for r in recs if r.get("guarantee_grade") == "E")
            gf = sum(1 for r in recs if r.get("guarantee_grade") == "F")
            sb_u, sb_k = runtime._sb_creds()
            runtime._recompute()
            return {
                "status": "ok", "service": f"MglennP Radial Switchboard (Spec Rev {SPEC_VERSION})", "spec_version": SPEC_VERSION, "rating_disclaimer": RATING_DISCLAIMER_TEXT, "legal_url": "https://radialswitchboard.com/legal",
                "contact_email": CONTACT_EMAIL, "github_repository": PUBLIC_GITHUB_REPO, "synthetic_seed_rows": 0,
                "hmac_secret_mode": HMAC_SECRET_MODE, "supabase_connected": bool(sb_u and sb_k),
                "mcp_endpoint": "https://radialswitchboard.com/mcp", "a2a_agent_card": "https://radialswitchboard.com/.well-known/agent-card.json",
                "stdio_bridge_script": "https://radialswitchboard.com/mcp_stdio_bridge.py", "apprentice_starter_script": "https://radialswitchboard.com/radial_apprentice_worker.py",
                "starter_key_endpoint": "https://radialswitchboard.com/v1/keys/starter", "phonebook_export_endpoint": "https://radialswitchboard.com/v1/phonebook/export",
                "genesis_enroll_endpoint": "https://radialswitchboard.com/v1/enroll", "usdc_treasury_base": runtime.gate.treasury_address,
                "total_unsorted_pool": len(recs), "live_callable_ab": ab, "offline_code_d": gd, "quarantined_e": ge, "slashed_poison_f": gf,
                "enrolled_apprentices": len(runtime.enrolled_apprentices), "crawl_cursor_state": dict(runtime.crawl_cursor),
                "total_external_uses": int(runtime.telemetry.get("mcp_jsonrpc_calls") or 0) + int(runtime.telemetry.get("rest_matchmake_calls") or 0) + int(runtime.telemetry.get("room_handshakes_completed") or 0), "discovery_pulls": int(runtime.telemetry.get("ai_beacon_discovery_pulls") or 0), "telemetry": {**{k: v for k, v in runtime.telemetry.items() if k != "recent_activity"}, "recent_activity_count": len(runtime.telemetry.get("recent_activity") or [])},
                "usdc_settled_usd": round(sum(float(x.get("gross_usdc_received") or 0.0) for x in runtime.gate.tax_revenue_ledger), 6),
                "tax_reserved_usd": round(sum(float(x.get("tax_reserve_30pct_usd") or 0.0) for x in runtime.gate.tax_revenue_ledger), 6),
            }

        def _enforce_gate(self, ip: str, body: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any], Dict[str, str]]:
            tok = self.headers.get("X-Radial-Pass") or ((body or {}).get("pass_token") if isinstance(body, dict) else None)
            psig = (self.headers.get("PAYMENT-SIGNATURE") or "").strip()
            extra: Dict[str, str] = {}
            if psig and not tok:
                try:
                    dec = json.loads(base64.b64decode(psig).decode("utf-8"))
                    pl = dec.get("payload") if isinstance(dec.get("payload"), dict) else dec
                    tx_h = str(pl.get("txHash") or pl.get("transaction") or dec.get("transaction") or "").strip()
                    st = runtime.gate.settle_x402_usdc_payment(tx_h, float(CASH_PASS_PRICE_USDC), str(pl.get("from") or "x402-client"), False)
                    tok = st["pass_token"]
                    extra["PAYMENT-RESPONSE"] = build_x402_payment_response_b64(tx_h, True)
                except Exception as exc:
                    h402 = {"PAYMENT-REQUIRED": build_x402_payment_required_b64(f"https://radialswitchboard.com{self.path}", runtime.gate.treasury_address), "PAYMENT-RESPONSE": build_x402_payment_response_b64("", False, str(exc))}
                    self._json(402, {"http_status": 402, "error": "X402_SETTLEMENT_FAILED", "detail": str(exc)}, h402)
                    return False, {}, h402
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            rst_u = str(int((now_dt + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()))
            ok_g, gi = runtime.gate.check_or_issue_402_challenge(ip, tok)
            if not ok_g:
                h402 = {
                    "PAYMENT-REQUIRED": build_x402_payment_required_b64(f"https://radialswitchboard.com{self.path}", runtime.gate.treasury_address),
                    "X-RateLimit-Limit": str(FREE_DAILY_STARTER_CALLS),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": rst_u,
                }
                self._json(402, gi, h402)
                return False, gi, h402
            rem_v = gi.get("remaining_handshakes", gi.get("remaining_free_today", 0))
            extra["X-RateLimit-Limit"] = str(CASH_PASS_CREDITS if tok else FREE_DAILY_STARTER_CALLS)
            extra["X-RateLimit-Remaining"] = str(rem_v)
            extra["X-RateLimit-Reset"] = rst_u
            return True, gi, extra

        def _build_pulse_data(self) -> Dict[str, Any]:
            hl = self._health()
            tel = runtime.telemetry
            day_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            dr = dict(tel.get("daily_rollup") or {})
            td = dict(dr.get(day_now) or {"tasks": 0, "humans": 0, "probes": 0, "beacons": 0, "bots": 0})
            hist = [{"date": dk, **dr[dk]} for dk in sorted(dr.keys(), reverse=True)[:14] if isinstance(dr.get(dk), dict)]
            fams = [{"family": fk, "count": int(fv)} for fk, fv in sorted((tel.get("client_families") or {}).items(), key=lambda x: x[1], reverse=True)]
            sanitized_ev = [
                {
                    "utc": str(ev.get("utc") or ""),
                    "client_family": str(ev.get("client_family") or runtime._classify_caller(str(ev.get("ua") or ""))),
                    "event": str(ev.get("event") or ""),
                    "route": str(ev.get("route") or ""),
                    "status": int(ev.get("status") or 200),
                }
                for ev in (tel.get("recent_activity") or [])[:15] if isinstance(ev, dict)
            ]
            init_n = int(tel.get("mcp_initialize_handshakes") or 0)
            tlist_n = int(tel.get("mcp_tools_list_probes") or 0)
            return {
                "status": "ok",
                "observer_safe": True,
                "spec_version": SPEC_VERSION,
                "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
                "supabase_connected": bool(hl.get("supabase_connected")),
                "usdc_settled_usd": hl.get("usdc_settled_usd", 0.0),
                "pool": {
                    "total_indexed": int(hl.get("total_unsorted_pool") or 0),
                    "live_callable_ab": int(hl.get("live_callable_ab") or 0),
                    "offline_code_d": int(hl.get("offline_code_d") or 0),
                    "quarantined_e": int(hl.get("quarantined_e") or 0),
                    "slashed_poison_f": int(hl.get("slashed_poison_f") or 0),
                },
                "totals": {
                    "task_calls": int(hl.get("total_external_uses") or 0),
                    "mcp_jsonrpc_calls": int(tel.get("mcp_jsonrpc_calls") or 0),
                    "rest_matchmake_calls": int(tel.get("rest_matchmake_calls") or 0),
                    "human_page_views": int(tel.get("human_page_views") or 0),
                    "bot_page_crawls": int(tel.get("bot_page_crawls") or 0),
                    "mcp_total_probes": init_n + tlist_n,
                    "mcp_initialize_handshakes": init_n,
                    "mcp_tools_list_probes": tlist_n,
                    "discovery_pulls": int(hl.get("discovery_pulls") or 0),
                    "bridge_script_downloads": int(tel.get("bridge_script_downloads") or 0),
                    "starter_keys_minted": int(tel.get("starter_keys_minted") or 0),
                    "scout_sweeps_completed": int(tel.get("scout_sweeps_completed") or 0),
                    "last_scout_sweep_utc": tel.get("last_scout_sweep_utc"),
                },
                "today_utc": td,
                "daily_history": hist,
                "client_families": fams,
                "recent_events": sanitized_ev,
            }

        def do_GET(self) -> None:
            pr = urllib.parse.urlparse(self.path); p = pr.path.rstrip("/") or "/"; qs = urllib.parse.parse_qs(pr.query)
            ui = (qs.get("ui_observer") or [""])[0].lower() in ("1", "true")
            ip = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or (self.client_address[0] if self.client_address else "anon")
            ua = str(self.headers.get("User-Agent") or "unknown")
            if p in ("/", "/directory"):
                if not ui and "RadialScout" not in ua and "GoogleHC" not in ua:
                    v_field = "human_page_views" if runtime._classify_caller(ua) == "Human Web Browser" else "bot_page_crawls"
                    runtime.record_event(v_field, route=f"GET {p}", ua=ua, ip=ip)
                f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "radial_agent_directory_explorer.html")
                if os.path.isfile(f):
                    html = open(f, "r", encoding="utf-8").read()
                    hl = self._health()
                    tel = hl.get("telemetry") or {}
                    mcp_c = int(tel.get("mcp_jsonrpc_calls") or 0)
                    rest_c = int(tel.get("rest_matchmake_calls") or 0)
                    wit_c = int(tel.get("room_handshakes_completed") or 0)
                    bcn_c = int(tel.get("ai_beacon_discovery_pulls") or 0)
                    real_calls = mcp_c + rest_c + wit_c
                    html = html.replace('<div class="score-value emerald" id="statTotalUses">0</div>', f'<div class="score-value emerald" id="statTotalUses">{real_calls:,}</div>', 1)
                    html = html.replace("0 MCP &bull; 0 REST &bull; 0 Discovery Pulls", f"{mcp_c:,} MCP &bull; {rest_c:,} REST &bull; {bcn_c:,} Discovery Pulls", 1)
                    html = html.replace('<div class="score-value" id="statLiveCallable">0</div>', f'<div class="score-value" id="statLiveCallable">{int(hl.get("live_callable_ab") or 0):,}</div>', 1)
                    html = html.replace("0 Indexed &bull; 0 Sweeps &bull; 0 Fake Seeds", f'{int(hl.get("total_unsorted_pool") or 0):,} Indexed &bull; {int(tel.get("scout_sweeps_completed") or 0):,} Sweeps &bull; 0 Fake Seeds', 1)
                    top_rows = sorted([r for r in runtime.pool_by_id.values() if r.get("guarantee_grade") == "A" and r.get("auth_mode") == "none"], key=lambda x: float(x.get("avg_latency_ms") or 99999.0))[:5]
                    if top_rows:
                        _esc = __import__("html").escape
                        ssr_trs = "".join(
                            f"<tr><td>{_esc(str(r.get('agent_id') or ''))}</td><td class='mono'>{_esc(str(r.get('mgle_nnp_stamp') or ''))}</td><td class='mono'>{_esc(str(r.get('mgle_nnp_u64_hex') or ''))}</td><td class='mono'>{_esc(str(r.get('endpoint') or ''))}</td><td class='mono'>{r.get('avg_latency_ms')} ms</td><td class='mono'>{int(r.get('wired_tool_count') or 1)} / {_esc(str(r.get('auth_mode') or 'none'))}</td><td>{_esc(str(r.get('audit_status') or ''))}</td></tr>"
                            for r in top_rows
                        )
                        html = re.sub(r'<tbody id="directoryTableBody">.*?</tbody>', f'<tbody id="directoryTableBody">{ssr_trs}</tbody>', html, count=1, flags=re.S)
                    init_c = int(tel.get("mcp_initialize_handshakes") or 0)
                    tl_c = int(tel.get("mcp_tools_list_probes") or 0)
                    br_c = int(tel.get("bridge_script_downloads") or 0)
                    html = html.replace('id="pulseMcpInit" style="font-size:1.45rem;font-weight:700;color:#38bdf8;margin-top:4px;">0</div>', f'id="pulseMcpInit" style="font-size:1.45rem;font-weight:700;color:#38bdf8;margin-top:4px;">{init_c:,}</div>', 1)
                    html = html.replace('id="pulseToolsList" style="font-size:1.45rem;font-weight:700;color:#fbbf24;margin-top:4px;">0</div>', f'id="pulseToolsList" style="font-size:1.45rem;font-weight:700;color:#fbbf24;margin-top:4px;">{tl_c:,}</div>', 1)
                    html = html.replace('id="pulseActiveCalls" style="font-size:1.45rem;font-weight:700;color:#10b981;margin-top:4px;">0</div>', f'id="pulseActiveCalls" style="font-size:1.45rem;font-weight:700;color:#10b981;margin-top:4px;">{(mcp_c + rest_c):,}</div>', 1)
                    html = html.replace('id="pulseBeacons" style="font-size:1.45rem;font-weight:700;color:#c084fc;margin-top:4px;">0</div>', f'id="pulseBeacons" style="font-size:1.45rem;font-weight:700;color:#c084fc;margin-top:4px;">{bcn_c:,}</div>', 1)
                    html = html.replace('id="pulseBridgeSub" style="font-size:0.72rem;color:#64748b;">0 bridge pulls</div>', f'id="pulseBridgeSub" style="font-size:0.72rem;color:#64748b;">{br_c:,} bridge pulls</div>', 1)
                    html = re.sub(r"(?i)spec (rev )?3\.5\.\d+", lambda m: f"{m.group(0).split('3.5')[0]}{SPEC_VERSION}", html)
                    self._bytes(200, "text/html; charset=utf-8", html.encode("utf-8"))
                else:
                    self._bytes(200, "text/html; charset=utf-8", f"<h1>Radial Switchboard {SPEC_VERSION}</h1>".encode())
            elif p == "/pulse":
                self._bytes(200, "text/html; charset=utf-8", build_pulse_html(self._build_pulse_data()).encode("utf-8"))
            elif p == "/v1/pulse":
                self._json(200, self._build_pulse_data())
            elif p in ("/legal", "/terms", "/disclaimer"):
                self._bytes(200, "text/html; charset=utf-8", build_legal_html().encode("utf-8"))
            elif p == "/v1/legal":
                self._json(200, {"spec_version": SPEC_VERSION, "legal_url": "https://radialswitchboard.com/legal", "rating_system_nature": "IN_HOUSE_PROPRIETARY_TECHNICAL_HEURISTIC_ONLY", "industry_or_legal_certification": False, "service_basis": "EXPERIMENTAL_AS_IS_NO_WARRANTY_NO_SLA", "proxy_or_custody": False, "rating_disclaimer": RATING_DISCLAIMER_TEXT, "contact_best_effort": CONTACT_EMAIL})
            elif p in ("/icon.svg", "/favicon.svg"):
                ic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "icon.svg")
                self._bytes(200, "image/svg+xml", open(ic, "rb").read() if os.path.isfile(ic) else b"<svg xmlns='http://www.w3.org/2000/svg'/>")
            elif p == "/mcp_stdio_bridge.py":
                if not ui:
                    runtime.record_event("bridge_script_downloads")
                    runtime.record_event("ai_beacon_discovery_pulls", route="GET /mcp_stdio_bridge.py", ua=ua, ip=ip)
                self._bytes(200, "text/x-python; charset=utf-8", MCP_STDIO_BRIDGE_SOURCE.encode())
            elif p == "/radial_apprentice_worker.py":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                self._bytes(200, "text/x-python; charset=utf-8", APPRENTICE_STARTER_SOURCE.encode())
            elif p == "/llms.txt":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                self._bytes(200, "text/plain; charset=utf-8", build_llms_txt(runtime.gate.treasury_address).encode("utf-8"))
            elif p in ("/.well-known/agent-card.json", "/.well-known/agent.json"):
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                self._json(200, build_a2a_agent_card())
            elif p == "/.well-known/agents.json":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                self._json(200, [build_a2a_agent_card()])
            elif p in ("/mcp/server-card", "/.well-known/mcp.json", "/.well-known/ai-catalog.json"):
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                c = {"$schema": "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json", "name": "com.radialswitchboard/matchmaker", "title": "MglennP Radial Switchboard", "version": SPEC_VERSION, "description": "64-bit MGLE-NNP zero-auth MCP & A2A agent matchmaker, poison auditor, and 3-agent crew router.", "contact": {"name": "MglennP", "email": CONTACT_EMAIL}, "supportedProtocolVersions": ["2026-07-28", "2025-06-18"], "remotes": [{"type": "streamable-http", "url": "https://radialswitchboard.com/mcp"}], "authentication": {"schemes": ["none", "X-Radial-Pass"], "freeCallsPerUtcDayPerIp": FREE_DAILY_STARTER_CALLS}, "tools": [{"name": t["name"], "title": t["title"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in MCP_SERVER_TOOLS]}
                self._json(200, {"servers": [c]} if p == "/.well-known/ai-catalog.json" else c)
            elif p == "/openapi.json":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                self._json(200, build_openapi_spec(runtime.gate.treasury_address))
            elif p == "/v1/health":
                self._json(200, self._health())
            elif p == "/v1/changelog":
                self._json(200, {
                    "spec_version": SPEC_VERSION,
                    "legal_url": "https://radialswitchboard.com/legal",
                    "releases": [
                        {
                            "version": "3.5.8",
                            "date": "2026-11-17",
                            "highlights": [
                                "Added live no-op tools/call auth & credit probe (__radial_auth_probe__) plus OAuth/API-key/USDC-credit detectors and auth_hint field",
                                "Parameterized Crew Role 3 verifier gate (requires >=1 input parameter on read_only cross-check tool; removed legacy zero-arg verified_schema shim)",
                                "Pre-cached per-agent lexical token sets (_lex_cache) cutting single_pass_flash_ms under 25 ms across 43k+ pool",
                                "Multi-concept capability overlap weighting ('verification'/'validation' stems) + broad catch-all gateway sprawl penalty",
                                "Shortened execution_ticket TTL from 86,400s (24h) to 900s (15m), added tools_preview_truncated + fallback tool summaries, and published /legal + /v1/legal AS-IS proprietary heuristic notices"
                            ],
                            "changed_or_removed": [
                                "Removed zero-argument 'verified_schema' fallback shim from _hydrate and finalist previews",
                                "Changed EXECUTION_TICKET_TTL_SECONDS: 86400 -> 900",
                                "Changed paid/credit auth_mode label: 'x402_paid_per_call' -> 'x402_or_credit_gated'",
                                "Changed get_switchboard_telemetry include_recent_activity schema description to default false (privacy parity with GET /v1/health)"
                            ]
                        },
                        {
                            "version": "3.5.7",
                            "date": "2026-11-17",
                            "highlights": [
                                "Per-tool callable_now stub filter and effect_class (read_only vs side_effecting) tags",
                                "x402 pay-per-call separation (payment_required=true, Grade B) from zero-auth Grade A",
                                "Two-stage 64-bit bitwise + BM25 lexical reranker with match_confidence, eligible_pool, post_filter_candidates, and matched_capabilities",
                                "protocol_version in MCP content[0].text, nested telemetry.total_external_uses parity, and recent_activity privacy strip on /v1/health"
                            ]
                        },
                        {
                            "version": "3.5.6",
                            "date": "2026-11-16",
                            "highlights": [
                                "On-demand finalist tools_preview hydration via /*RADIAL_TOOLS:*/ persistence and concurrent live interrogation",
                                "Raised tools/list read buffer to 512KB, served true /.well-known/mcp.json server card, and added paginated /v1/directory/live"
                            ]
                        },
                        {
                            "version": "3.5.5",
                            "date": "2026-11-15",
                            "highlights": [
                                "64-bit MGLE-NNP bitwise matchmaker, 3-agent vendor-independent crew triad, Ed25519 apprentice credentials, and Base USDC x402 / Canary Scout gate"
                            ]
                        }
                    ]
                })
            elif p == "/v1/benchmark":
                recs = list(runtime.pool_by_id.values())
                s = sorted(float(flash_unsorted_pool(recs, ["sql", "database"], max_lat="E")["single_pass_flash_ms"]) for _ in range(10))
                self._json(200, {"spec_version": SPEC_VERSION, "agents_scanned": len(recs), "default_top_k": DEFAULT_FLASH_TOP_K, "p50_bitwise_ms": s[len(s) // 2] if s else 0.0})
            elif p == "/v1/directory/live":
                lim_d = max(1, min(250, int((qs.get("limit") or ["50"])[0] if str((qs.get("limit") or ["50"])[0]).isdigit() else 50)))
                off_d = max(0, int((qs.get("offset") or ["0"])[0] if str((qs.get("offset") or ["0"])[0]).isdigit() else 0))
                grd_d = str((qs.get("grade") or ["ALL"])[0]).upper()
                inc_dos = str((qs.get("include_dossier") or ["false"])[0]).lower() in ("1", "true")
                all_r = list(runtime.pool_by_id.values())
                if grd_d == "AB": all_r = [r for r in all_r if r.get("guarantee_grade") in ("A", "B")]
                elif grd_d in ("A", "B", "C", "D", "E", "F"): all_r = [r for r in all_r if r.get("guarantee_grade") == grd_d]
                recs = sorted(all_r, key=lambda x: (0 if x.get("guarantee_grade") == "A" else 1, -len(((x.get("dossier_json") or {}).get("verified_tools")) or []), float(x.get("avg_latency_ms") or 99999.0)))
                page_r = recs[off_d:off_d + lim_d]
                slim_r = []
                for r in page_r:
                    tp_raw = ((r.get("dossier_json") or {}).get("verified_tools") or [])[:4]
                    tp_clean = [{**t, "summary": str(t.get("summary") or f"{str(t.get('tool') or '').replace('_', ' ')}").strip()[:120]} for t in tp_raw if isinstance(t, dict)]
                    base_d = {k: v for k, v in r.items() if k not in (("_lex_cache",) if inc_dos else ("dossier_json", "_lex_cache"))}
                    base_d["tools_preview"] = tp_clean
                    base_d["tools_preview_truncated"] = int(r.get("wired_tool_count") or 0) > len(tp_clean)
                    slim_r.append(base_d)
                self._json(200, {"spec_version": SPEC_VERSION, "contact_email": CONTACT_EMAIL, "synthetic_seed_rows": 0, "total_agents": len(all_r), "limit": lim_d, "offset": off_d, "returned_count": len(slim_r), "next_offset": (off_d + lim_d) if (off_d + lim_d) < len(all_r) else None, "appeals": runtime.appeals_log[:20], "tax_ledger": runtime.gate.tax_revenue_ledger[:20], "agents": slim_r})
            elif p == "/v1/phonebook/export":
                if not ui: runtime.record_event("ai_beacon_discovery_pulls", route=f"GET {p}", ua=ua, ip=ip)
                fmt = (qs.get("format") or ["jsonl"])[0].lower()
                grd = (qs.get("grades") or ["AB"])[0].upper()
                reg = (qs.get("region") or ["ALL"])[0].upper()
                recs = list(runtime.pool_by_id.values())
                if grd == "AB": recs = [r for r in recs if r.get("guarantee_grade") in ("A", "B")]
                if reg in ("E", "W", "U", "P", "G"): recs = [r for r in recs if r.get("geo_zone") in (reg, "G")]
                recs.sort(key=lambda x: (0 if x.get("guarantee_grade") == "A" else 1, float(x.get("avg_latency_ms") or 99999.0)))
                if fmt == "csv":
                    out_io = io.StringIO(); w = csv.writer(out_io)
                    w.writerow(["agent_id", "name", "geo_zone", "guarantee_grade", "latency_grade", "mgle_nnp_stamp", "mgle_nnp_u64_hex", "endpoint", "avg_latency_ms", "wired_tool_count", "auth_mode", "audit_status", "last_audited_at"])
                    for r in recs:
                        w.writerow([r.get("agent_id"), r.get("name"), r.get("geo_zone", "E"), r.get("guarantee_grade"), r.get("latency_grade"), r.get("mgle_nnp_stamp"), f"0x{int(r.get('mgle_nnp_64bit') or 0):016X}", r.get("endpoint"), r.get("avg_latency_ms"), r.get("wired_tool_count"), r.get("auth_mode"), r.get("audit_status"), r.get("last_audited_at")])
                    raw_b, ct = out_io.getvalue().encode("utf-8"), "text/csv; charset=utf-8"
                else:
                    fmt = "jsonl"
                    lines = [json.dumps({"agent_id": r.get("agent_id"), "name": r.get("name"), "geo_zone": r.get("geo_zone", "E"), "guarantee_grade": r.get("guarantee_grade"), "latency_grade": r.get("latency_grade"), "mgle_nnp_stamp": r.get("mgle_nnp_stamp"), "mgle_nnp_u64_hex": f"0x{int(r.get('mgle_nnp_64bit') or 0):016X}", "endpoint": r.get("endpoint"), "avg_latency_ms": r.get("avg_latency_ms"), "wired_tool_count": r.get("wired_tool_count"), "tool_schema_hash_16": r.get("tool_schema_hash_16"), "auth_mode": r.get("auth_mode"), "audit_status": r.get("audit_status"), "last_audited_at": r.get("last_audited_at")}, separators=(",", ":")) for r in recs]
                    raw_b, ct = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"), "application/x-ndjson; charset=utf-8"
                sig = hmac.new(HMAC_SECRET_KEY, raw_b, hashlib.sha256).hexdigest()[:24]
                self._bytes(200, ct, raw_b, {"Content-Disposition": f'attachment; filename="radial_scouting_phonebook_v3.{fmt}"', "X-Radial-Snapshot-HMAC": sig, "X-Radial-Export-Count": str(len(recs))})
            elif p == "/v1/appeals":
                self._json(200, {"count": len(runtime.appeals_log), "appeals": runtime.appeals_log})
            elif p == "/v1/matchmake":
                if not ui:
                    ok_g, _, ex_h = self._enforce_gate(ip)
                    if not ok_g: return
                    runtime.record_event("rest_matchmake_calls", ext_call=True, route=f"POST {p}", ua=ua, ip=ip)
                else:
                    ex_h = {}
                self._json(200, runtime.ensure_finalists_hydrated(infer_capabilities_from_intent((qs.get("intent") or ["mcp"])[0]), zero_auth=((qs.get("zero_auth") or ["true"])[0].lower() not in ("0", "false")), max_lat=(qs.get("max_latency_grade") or ["C"])[0], mode=(qs.get("mode") or ["top10_varied"])[0], caller_region=self._caller_region(qs, None), intent_text=str((qs.get("intent") or [""])[0])), ex_h)
            elif p.startswith("/v1/credential/"):
                did = urllib.parse.unquote(p[len("/v1/credential/"):])
                cert = runtime.enrolled_apprentices.get(did) or runtime.pool_by_id.get(did)
                self._json(200 if cert else 404, cert if cert else {"error": "Credential not found"})
            elif p.startswith("/v1/dossier/"):
                rec = runtime.pool_by_id.get(urllib.parse.unquote(p[len("/v1/dossier/"):]))
                self._json(200 if rec else 404, (rec.get("dossier_json") or {k: v for k, v in rec.items() if k != "_lex_cache"}) if rec else {"error": "Not found"})
            else:
                self._json(404, {"error": "Route not found"})

        def do_POST(self) -> None:
            p = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
            ln = int(self.headers.get("Content-Length") or 0)
            try: body = json.loads(self.rfile.read(min(ln, 524288)).decode("utf-8", errors="replace")) if ln > 0 else {}
            except Exception: body = {}
            ip = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or (self.client_address[0] if self.client_address else "anon")
            ua = str(self.headers.get("User-Agent") or "unknown")
            if p == "/mcp":
                rid, m, prm = body.get("id", 1), str(body.get("method") or ""), (body.get("params") if isinstance(body.get("params"), dict) else {})
                cinfo = (prm.get("clientInfo") or {}) if isinstance(prm.get("clientInfo"), dict) else {}
                c_ua = f"{cinfo.get('name')}/{cinfo.get('version')} ({ua})" if cinfo.get("name") else ua
                if m == "notifications/initialized": self._bytes(202, "application/json", b"")
                elif m == "initialize":
                    if "RadialScout" not in c_ua:
                        runtime.record_event("mcp_initialize_handshakes", route="POST /mcp [initialize]", ua=c_ua, ip=ip)
                    self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": str(prm.get("protocolVersion") or "2026-07-28"), "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "MglennP Radial Switchboard", "version": SPEC_VERSION}}})
                elif m == "ping": self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {}})
                elif m == "tools/list":
                    if "RadialScout" not in ua:
                        runtime.record_event("mcp_tools_list_probes", route="POST /mcp [tools/list]", ua=ua, ip=ip)
                    self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {"tools": MCP_SERVER_TOOLS}})
                elif m == "tools/call":
                    tn, ag = str(prm.get("name") or ""), (prm.get("arguments") if isinstance(prm.get("arguments"), dict) else {})
                    ex_h: Dict[str, str] = {}
                    if tn in ("matchmake_agent_crew", "flash_matchmake_agents"):
                        ok_g, _, ex_h = self._enforce_gate(ip, ag)
                        if not ok_g: return
                        runtime.record_event("mcp_jsonrpc_calls", ext_call=True, route=f"POST /mcp [{tn}]", ua=ua, ip=ip)
                        out = runtime.ensure_finalists_hydrated(ag.get("capabilities") or infer_capabilities_from_intent(str(ag.get("intent") or "")), zero_auth=bool(ag.get("require_instant_zero_auth", True)), max_lat=str(ag.get("max_latency_grade", "C")), top_k=int(ag.get("top_k", DEFAULT_FLASH_TOP_K)), mode=str(ag.get("mode") or "top10_varied"), caller_region=self._caller_region(None, ag), intent_text=str(ag.get("intent") or ""))
                    elif tn == "search_agent_directory":
                        runtime.record_event("mcp_jsonrpc_calls", ext_call=True, route="POST /mcp [search_agent_directory]", ua=ua, ip=ip)
                        q_s = str(ag.get("query") or "").strip().lower()
                        gf = str(ag.get("grade_filter") or "AB").strip().upper()
                        lim = max(1, min(50, int(ag.get("limit", 20))))
                        matched = []
                        for rec in runtime.pool_by_id.values():
                            gr = str(rec.get("latency_grade") or "E").upper()
                            gg = str(rec.get("guarantee_grade") or "E").upper()
                            if rec.get("merit_grade") == "F" or gr == "F" or gg == "F": continue
                            if gf == "AB" and (gg not in ("A", "B") or gr not in ("A", "B", "C")): continue
                            if gf in ("A", "B", "C", "D") and gg != gf: continue
                            if q_s and q_s not in f"{rec.get('agent_id','')} {rec.get('name','')} {rec.get('description','')} {rec.get('endpoint','')}".lower():
                                continue
                            ep_u = str(rec.get("endpoint") or "")
                            matched.append({
                                "agent_id": rec.get("agent_id"),
                                "name": rec.get("name"),
                                "endpoint": ep_u,
                                "transport": "mcp-sse" if ep_u.lower().endswith("/sse") else ("a2a-http-json" if str(rec.get("agent_id") or "").startswith("a2a://") else "mcp-streamable-http"),
                                "mgle_nnp_stamp": rec.get("mgle_nnp_stamp"),
                                "mgle_nnp_u64_hex": rec.get("mgle_nnp_u64_hex"),
                                "guarantee_grade": gg,
                                "latency_grade": gr,
                                "merit_grade": rec.get("merit_grade"),
                                "avg_latency_ms": rec.get("avg_latency_ms"),
                                "auth_mode": rec.get("auth_mode", "none"),
                                "wired_tool_count": int(rec.get("wired_tool_count") or 0),
                                "tool_schema_hash_16": rec.get("tool_schema_hash_16"),
                                "audit_status": rec.get("audit_status"),
                            })
                        matched.sort(key=lambda x: (str(x.get("latency_grade") or "Z"), float(x.get("avg_latency_ms") or 9999.0)))
                        out = {"total_matching": len(matched), "returned_count": min(len(matched), lim), "agents": matched[:lim]}
                    elif tn == "get_agent_dossier":
                        runtime.record_event("mcp_jsonrpc_calls", ext_call=True, route="POST /mcp [get_agent_dossier]", ua=ua, ip=ip)
                        aid_req = str(ag.get("agent_id") or "").strip()
                        rec = runtime.pool_by_id.get(aid_req)
                        out = {"found": bool(rec), "agent_id": aid_req, "dossier": ({k: v for k, v in rec.items() if k != "_lex_cache"} if rec else {"error": "Not found"})}
                    elif tn == "get_switchboard_telemetry":
                        runtime.record_event("mcp_jsonrpc_calls", ext_call=True, route="POST /mcp [get_switchboard_telemetry]", ua=ua, ip=ip)
                        out = self._health()
                        if ag.get("include_recent_activity") is False and isinstance(out.get("telemetry"), dict):
                            out["telemetry"] = {k: v for k, v in out["telemetry"].items() if k != "recent_activity"}
                    elif tn == "register_agent_endpoint":
                        runtime.record_event("mcp_jsonrpc_calls", ext_call=True, route="POST /mcp [register_agent_endpoint]", ua=ua, ip=ip)
                        ep = str(ag.get("endpoint") or "").strip()
                        if not ep or not is_safe_public_endpoint(ep):
                            out = {"registered": False, "audit_status": "SSRF_GUARD_BLOCKED_NON_PUBLIC_ENDPOINT", "error": "Public HTTPS endpoint required"}
                        else:
                            prb = interrogate_live_endpoint({"agent_id": str(ag.get("agent_id") or f"mcp://sub-{secrets.token_hex(3)}"), "name": str(ag.get("agent_id") or ep), "description": str(ag.get("description") or ""), "endpoint": ep})
                            runtime.pool_by_id[prb["agent_id"]] = prb; runtime._upsert_sb([prb])
                            ar = {"id": f"APP-{len(runtime.appeals_log)+1}", "slug": prb["agent_id"], "endpoint": prb["endpoint"], "status": prb["audit_status"]}
                            runtime.appeals_log.insert(0, ar)
                            out = {"registered": True, "appeal_id": ar["id"], "audit_status": prb["audit_status"], "updated_record": {k: v for k, v in prb.items() if k != "_lex_cache"}}
                    elif tn == "report_execution_outcome":
                        runtime.record_event("mcp_jsonrpc_calls", ext_call=True, route="POST /mcp [report_execution_outcome]", ua=ua, ip=ip)
                        lv = ag.get("observed_latency_ms")
                        out = runtime.verify_outcome(str(ag.get("agent_id") or ""), str(ag.get("execution_ticket") or ""), bool(ag.get("outcome_success", True)), float(lv) if isinstance(lv, (int, float)) else None)
                    else: self._json(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Unknown tool"}}); return
                    if "finalists" in out and ex_h.get("X-RateLimit-Remaining") is not None:
                        out["remaining_quota_calls"] = int(ex_h["X-RateLimit-Remaining"])
                    txt_summary = json.dumps({
    "spec_version": out.get("spec_version"),
    "match_mode": out.get("match_mode"),
    "match_confidence": out.get("match_confidence"),
    "finalist_count": out.get("finalist_count"),
    "pool_scanned_unsorted": out.get("pool_scanned_unsorted"),
    "eligible_pool": out.get("eligible_pool"),
    "post_filter_candidates": out.get("post_filter_candidates"),
    "single_pass_flash_ms": out.get("single_pass_flash_ms"),
    "remaining_quota_calls": out.get("remaining_quota_calls"),
    "untrusted_third_party_text": True,
    "crew_manifest": out.get("crew_manifest"),
    "finalists": [{"rank": f.get("rank"), "agent_id": f.get("agent_id"), "name": f.get("name"), "endpoint": f.get("endpoint"), "transport": f.get("transport"), "protocol_version": f.get("protocol_version"), "auth_mode": f.get("auth_mode"), "auth_hint": f.get("auth_hint"), "payment_required": f.get("payment_required"), "wired_tool_count": f.get("wired_tool_count"), "tools_preview_truncated": f.get("tools_preview_truncated"), "tool_schema_hash_16": f.get("tool_schema_hash_16"), "matched_capabilities": f.get("matched_capabilities"), "relevance_score": f.get("relevance_score"), "tools_preview": f.get("tools_preview"), "crew_role": f.get("crew_role"), "execution_ticket": f.get("execution_ticket"), "ticket_expires_unix": f.get("ticket_expires_unix")} for f in (out.get("finalists") or [])[:10]]
}, separators=(",", ":")) if "finalists" in out else json.dumps(out, separators=(",", ":"))
                    self._bytes(200, "application/json; charset=utf-8", json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": txt_summary}], "structuredContent": out, "isError": False}}, separators=(",", ":")).encode("utf-8"), ex_h or None)
                else:
                    self._json(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Unsupported"}})
            elif p == "/v1/keys/starter":
                obj, nw = runtime.gate.mint_daily_starter_pass(ip, str(body.get("agent_label") or "visitor-hook"))
                if nw: runtime.record_event("starter_keys_minted")
                self._json(200, obj)
            elif p == "/v1/enroll":
                code, res = runtime.enroll_genesis_apprentice(body)
                self._json(code, res)
            elif p.startswith("/v1/canary/"):
                cp = p[len("/v1/canary/"):].strip()
                self._json(200, {"jsonrpc": "2.0", "id": body.get("id", 1), "result": {"tools": [{"name": "radial_canary_ping", "description": "Canary", "inputSchema": {"type": "object", "properties": {cp: {"type": "string"}}, "required": [cp]}}]}})
            elif p in ("/v1/flash", "/v1/matchmake"):
                if not bool(body.get("ui_observer", False)):
                    ok_g, _, ex_h = self._enforce_gate(ip, body)
                    if not ok_g: return
                    runtime.record_event("rest_matchmake_calls", ext_call=True)
                else:
                    ex_h = {}
                self._json(200, runtime.ensure_finalists_hydrated(body.get("capabilities") or infer_capabilities_from_intent(str(body.get("intent") or "")), zero_auth=bool(body.get("require_instant_zero_auth", True)), max_lat=str(body.get("max_latency_grade", "C")), top_k=int(body.get("top_k", DEFAULT_FLASH_TOP_K)), mode=str(body.get("mode") or "top10_varied"), caller_region=self._caller_region(None, body), intent_text=str(body.get("intent") or "")), ex_h)
            elif p == "/v1/directory/crawl":
                self._json(200, runtime.run_live_scout_sweep(int(body.get("limit", 80))))
            elif p == "/v1/appeals":
                ep = str(body.get("endpoint") or "").strip()
                if ep and not is_safe_public_endpoint(ep):
                    self._json(400, {"error": "SSRF_GUARD_BLOCKED_NON_PUBLIC_ENDPOINT"}); return
                prb = interrogate_live_endpoint({"agent_id": str(body.get("agent_id") or f"mcp://sub-{secrets.token_hex(3)}"), "name": str(body.get("agent_id") or ep or ""), "description": str(body.get("reason") or ""), "endpoint": ep})
                runtime.pool_by_id[prb["agent_id"]] = prb; runtime._upsert_sb([prb])
                ar = {"id": f"APP-{len(runtime.appeals_log)+1}", "slug": prb["agent_id"], "endpoint": prb["endpoint"], "status": prb["audit_status"]}
                runtime.appeals_log.insert(0, ar); self._json(200, {"appeal": ar, "updated_record": prb})
            elif p == "/v1/work/claim":
                self._json(200, runtime.gate.issue_scout_work_assignment(list(runtime.pool_by_id.values())))
            elif p == "/v1/work/submit":
                res = runtime.gate.verify_scout_work_submission(str(body.get("assignment_id") or ""), body.get("results") or [], str(body.get("region") or "external"))
                self._json(200 if res.get("status") == "VERIFIED_WORK_PASS_ISSUED" else 400, res)
            elif p == "/v1/x402/settle":
                try: self._json(200, runtime.gate.settle_x402_usdc_payment(str(body.get("tx_hash") or ""), float(body.get("amount_usdc") or 0.0), str(body.get("payer_wallet") or ""), False))
                except ValueError as err: self._json(400, {"error": str(err)})
            elif p == "/v1/room/handshake":
                ok_g, gi, ex_h = self._enforce_gate(ip, body)
                if not ok_g: return
                w = runtime.pool_by_id.get(str(body.get("target_agent_id") or ""))
                if not w: self._json(404, {"error": "Unknown target agent"}); return
                if not is_safe_public_endpoint(str(w.get("endpoint") or "")):
                    self._json(400, {"error": "Target endpoint blocked by SSRF guard"}); return
                t0 = time.perf_counter()
                try:
                    with urllib.request.urlopen(urllib.request.Request(str(w["endpoint"]), data=json.dumps(body.get("payload") or {}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=8) as r:
                        wr = json.loads(r.read(262144).decode("utf-8", errors="replace"))
                    ok_w = isinstance(wr, dict) and "error" not in wr
                except Exception as exc:
                    wr, ok_w = {"error": str(exc)}, False
                if ok_w: runtime.record_event("room_handshakes_completed")
                self._json(200 if ok_w else 502, {"http_status": 200 if ok_w else 502, "room_witness_verdict": "DELIVERY_VERIFIED" if ok_w else "WORKER_CONTRACT_FAILURE", "measured_room_ms": round((time.perf_counter() - t0) * 1000.0, 2), "caller_gate": gi, "worker_response": wr}, ex_h)
            elif p == "/v1/outcome":
                lv = body.get("observed_latency_ms")
                out = runtime.verify_outcome(str(body.get("agent_id") or ""), str(body.get("execution_ticket") or ""), bool(body.get("outcome_success", True)), float(lv) if isinstance(lv, (int, float)) else None)
                self._json(200 if out.get("ticket_valid") else 403, out)
            else:
                self._json(404, {"error": "Route not found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler

def run_self_test() -> int:
    rt = StandaloneSwitchboardRuntime(hydrate_external=False, start_background_scouts=False)
    assert len(rt.pool_by_id) == 0 and rt.telemetry["total_external_uses"] == 0
    gated_rec = build_agent_record_and_dossier("test://ekwo-gated", "Auth Gated Accounting", "postgres sql database finance", "https://mcp.ekwo.example/mcp", True, 110.0, None, [], "none", geo_zone="U")
    assert gated_rec["auth_mode"] != "none" and gated_rec["guarantee_grade"] == "C" and gated_rec["wired_tool_count"] == 0
    rt.pool_by_id["test://ekwo-gated"] = gated_rec
    defs = [
        ("test://v0", "Postgres SQL US-East", "postgres sql database python", "https://n0.use1.v0.example/mcp", "E"),
        ("test://v1", "SEC Finance EU", "sec finance search rag", "https://n1.eu-west.v1.example/mcp", "U"),
        ("test://v2", "Math Audit Global", "math verify security audit", "https://n2.v2.workers.dev/mcp", "G"),
    ]
    for i in range(12):
        aid, nm, ds, ep, zn = defs[i] if i < 3 else (f"test://v{i}", f"SQL {i}", "postgres sql database", f"https://n{i}.v{i}.example/mcp", "U" if i == 9 else "E")
        rt.pool_by_id[aid] = build_agent_record_and_dossier(aid, nm, ds, ep, True, 80.0, 45.0 + i, [{"name": f"t_{i}", "description": ds, "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}], geo_zone=zn)
    srv = ThreadingHTTPServerReuse(("127.0.0.1", 0), create_http_handler(rt))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        h = json.loads(urllib.request.urlopen(f"{base}/v1/health", timeout=5).read().decode())
        assert h["spec_version"] == SPEC_VERSION and h["synthetic_seed_rows"] == 0
        oa = json.loads(urllib.request.urlopen(f"{base}/openapi.json?ui_observer=true", timeout=5).read().decode())
        assert oa["info"]["version"] == SPEC_VERSION and "RadialPassHeader" in oa["components"]["securitySchemes"]
        mcp_well = json.loads(urllib.request.urlopen(f"{base}/.well-known/mcp.json?ui_observer=true", timeout=5).read().decode())
        assert mcp_well["version"] == SPEC_VERSION and len(mcp_well["tools"]) == 6
        lt = urllib.request.urlopen(f"{base}/llms.txt?ui_observer=true", timeout=5).read().decode()
        assert f"Spec Rev {SPEC_VERSION}" in lt and "matchmake_agent_crew" in lt and "search_agent_directory" in lt
        ac = json.loads(urllib.request.urlopen(f"{base}/.well-known/agent-card.json", timeout=5).read().decode())
        assert ac["version"] == SPEC_VERSION and len(ac["mcpTools"]) == 6 and "rateLimit" in ac
        home_html = urllib.request.urlopen(f"{base}/", timeout=5).read().decode()
        assert f"Spec Rev {SPEC_VERSION}" in home_html and f"SPEC REV {SPEC_VERSION}" in home_html and "test://v0" in home_html
        eu_f = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/flash", data=json.dumps({"capabilities": ["sql"], "caller_region": "EU", "ui_observer": True}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        megahub = build_agent_record_and_dossier("test://megahub", "CatchAll MegaHub", " ".join(CAPABILITY_NAMES), "https://mega.hub.example/mcp", True, 75.0, 40.0, [{"name": "all_in_one", "description": "hub", "inputSchema": {"type": "object"}}], geo_zone="E")
        rt.pool_by_id["test://megahub"] = megahub
        sp_f = flash_unsorted_pool(list(rt.pool_by_id.values()), ["sql", "database"], zero_auth=True, max_lat="C")
        assert sp_f["finalists"][0]["agent_id"] != "test://megahub", "Mega-hub outranked narrow SQL specialist!"
        del rt.pool_by_id["test://megahub"]
        assert eu_f["caller_region_applied"] == "U" and eu_f["finalists"][0]["agent_id"] == "test://v9"
        cr = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/flash", data=json.dumps({"capabilities": ["sql", "finance_data", "math_verify"], "mode": "crew", "ui_observer": True}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert cr["finalist_count"] == 3 and cr["crew_manifest"]["provider_independence_verified"] is True
        seed = secrets.token_bytes(32); did = pubkey_to_did_key(ed25519_pubkey(seed))
        enr = {"did": did, "agent_label": "selftest-apprentice", "endpoint": "", "economy_tier": "A", "seasoned_tenure_bit25": 0, "schema_version": "0x3", "timestamp_unix": int(time.time())}
        sig = ed25519_sign(seed, json.dumps(enr, sort_keys=True, separators=(",", ":")).encode()).hex()
        er = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/enroll", data=json.dumps({"enrollment": enr, "signature_ed25519_hex": sig}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert er["enrolled"] is True and er["credential"]["credential_tier"] == "APPRENTICE"
        with urllib.request.urlopen(f"{base}/v1/phonebook/export?format=jsonl&ui_observer=true", timeout=5) as r_jl:
            assert r_jl.headers.get("X-Radial-Snapshot-HMAC") and len(r_jl.read().decode().strip().splitlines()) == 12
        kr = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/v1/keys/starter", data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        tl = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        tnames = [t["name"] for t in tl["result"]["tools"]]
        assert len(tnames) == 6 and "matchmake_agent_crew" in tnames and "report_execution_outcome" in tnames
        sr = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "search_agent_directory", "arguments": {"query": "postgres", "limit": 5}}}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert sr["result"]["structuredContent"]["total_matching"] >= 1
        with urllib.request.urlopen(urllib.request.Request(f"{base}/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "matchmake_agent_crew", "arguments": {"intent": "postgres sql"}}}).encode(), headers={"Content-Type": "application/json", "X-Radial-Pass": kr["pass_token"]}, method="POST"), timeout=5) as r_mcp:
            assert r_mcp.headers.get("X-RateLimit-Remaining") is not None
            mr = json.loads(r_mcp.read().decode())
        assert len(mr["result"]["content"][0]["text"]) < 12000 and len(json.dumps(mr)) < 26000
        c0_parsed = json.loads(mr["result"]["content"][0]["text"])
        assert c0_parsed["finalists"][0]["protocol_version"] == "2025-06-18" and "eligible_pool" in c0_parsed and "auth_hint" in c0_parsed["finalists"][0]
        f0 = mr["result"]["structuredContent"]["finalists"][0]
        for fn_item in mr["result"]["structuredContent"]["finalists"]:
            assert len(fn_item["tools_preview"]) >= 1 and fn_item["wired_tool_count"] >= len(fn_item["tools_preview"])
            assert fn_item["protocol_version"] == "2025-06-18" and fn_item["payment_required"] is False
            assert all(tp["callable_now"] is True and tp["effect_class"] in ("read_only", "side_effecting") for tp in fn_item["tools_preview"])
        assert f0["transport"] == "mcp-streamable-http" and f0["auth_mode"] == "none" and f0["agent_id"] != "test://ekwo-gated"
        stub_rec = build_agent_record_and_dossier("test://stub-only", "Stub Broker", "Broker", "https://stub.broker.example/mcp", True, 50.0, 35.0, [{"name": "call_business", "description": "NOT WIRED on this deployment", "inputSchema": {"type": "object"}}])
        paid_rec = build_agent_record_and_dossier("test://x402-paid", "Verse Paid", "Paid per call over x402", "https://verse.paid.example/mcp", True, 50.0, 35.0, [{"name": "ask_verse", "description": "paid per call over x402", "inputSchema": {"type": "object"}}])
        assert stub_rec["wired_tool_count"] == 0 and stub_rec["guarantee_grade"] == "C"
        assert paid_rec["payment_required"] is True and paid_rec["guarantee_grade"] == "B" and paid_rec["auth_mode"] == "x402_or_credit_gated"
        oauth_rec = build_agent_record_and_dossier("mcp://test/oauth", "PropFacil CRM", "Manage real estate leads with OAuth", "https://prop.example/mcp", True, 40.0, 30.0, [{"name": "list_leads", "description": "List leads", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}}], "none")
        assert oauth_rec["guarantee_grade"] == "C" and oauth_rec["auth_mode"] == "oauth_or_apikey_required"
        assert EXECUTION_TICKET_TTL_SECONDS == 900
        lg_html = urllib.request.urlopen(f"{base}/legal", timeout=5).read().decode()
        assert "in-house proprietary" in lg_html.lower() and "as is" in lg_html.lower()
        lg_json = json.loads(urllib.request.urlopen(f"{base}/v1/legal", timeout=5).read().decode())
        assert lg_json["industry_or_legal_certification"] is False
        urllib.request.urlopen(urllib.request.Request(f"{base}/", headers={"User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 11 Pro XL) AppleWebKit/537.36 Chrome/142.0 Safari/537.36"}), timeout=5).read()
        p_before = json.loads(urllib.request.urlopen(f"{base}/v1/pulse", timeout=5).read().decode())
        p_html = urllib.request.urlopen(f"{base}/pulse", timeout=5).read().decode()
        p_after = json.loads(urllib.request.urlopen(f"{base}/v1/pulse", timeout=5).read().decode())
        assert p_before["totals"]["human_page_views"] >= 1 and p_after["totals"]["human_page_views"] == p_before["totals"]["human_page_views"]
        assert "Radial Switchboard Pulse" in p_html and "ip_masked" not in json.dumps(p_after)
        hl_chk = json.loads(urllib.request.urlopen(f"{base}/v1/health", timeout=5).read().decode())
        assert hl_chk["total_external_uses"] == hl_chk["telemetry"]["total_external_uses"] and "recent_activity" not in hl_chk["telemetry"] and "rating_disclaimer" in hl_chk
        tkt, tid = f0["execution_ticket"], f0["agent_id"]
        mr_alias = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "flash_matchmake_agents", "arguments": {"intent": "postgres sql"}}}).encode(), headers={"Content-Type": "application/json", "X-Radial-Pass": kr["pass_token"]}, method="POST"), timeout=5).read().decode())
        assert mr_alias["result"]["structuredContent"]["finalist_count"] >= 1
        ok_o = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "report_execution_outcome", "arguments": {"agent_id": tid, "execution_ticket": tkt, "outcome_success": True, "observed_latency_ms": 48.5}}}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read().decode())
        assert ok_o["result"]["structuredContent"]["ticket_valid"] is True
    finally:
        srv.shutdown(); srv.server_close()
    print(f"[PASS] Crisp Spec {SPEC_VERSION} Autonomous Global-Scale Engine 100% Verified.")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true"); ap.add_argument("--crawl-once", action="store_true"); ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = ap.parse_args()
    if args.crawl_once:
        print(json.dumps(StandaloneSwitchboardRuntime(True, False).run_live_scout_sweep(80), indent=2)); return 0
    if args.serve:
        rt = StandaloneSwitchboardRuntime(True, True)
        with ThreadingHTTPServerReuse(("0.0.0.0", args.port), create_http_handler(rt)) as srv:
            print(f"Radial Switchboard {SPEC_VERSION} active on 0.0.0.0:{args.port}"); srv.serve_forever()
        return 0
    return run_self_test()

if __name__ == "__main__":
    raise SystemExit(main())
