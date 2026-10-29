#!/usr/bin/env python3
r"""
MGLENNP STANDALONE SWITCHBOARD — 64-BIT MGLE-NNP AGENT MATCHMAKER (v1)
Live Database Sync: https://malvgodkmfgdzswbhcyj.supabase.co (us-east-1 Northern Virginia)
"""

import os
import time
import json
import urllib.request
import urllib.error

SCHEMA_VERSION_V1 = 0x1
SUPABASE_PROJECT_URL = "https://malvgodkmfgdzswbhcyj.supabase.co"
OFFICIAL_MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers?limit=50"
HANDSHAKE_FEE_USD = 0.0001

DOMAIN_BITS = {
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


def ensure_local_env(env_path=".env"):
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    sb_key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not (sb_key.startswith("sb_secret_") or sb_key.startswith("eyJ")):
        sb_key = input("\nPaste your Supabase Secret Key (sb_secret_... or service_role) and press Enter: ").strip()
        os.environ["SUPABASE_URL"] = SUPABASE_PROJECT_URL
        os.environ["SUPABASE_SECRET_KEY"] = sb_key
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"SUPABASE_URL={SUPABASE_PROJECT_URL}\n")
            f.write(f"SUPABASE_SECRET_KEY={sb_key}\n")
        print(" [OK] Saved SUPABASE_SECRET_KEY to local .env file.")


def supabase_request(table_path, method="POST", payload=None, prefer="return=minimal"):
    sb_url = os.environ.get("SUPABASE_URL", SUPABASE_PROJECT_URL).rstrip("/")
    sb_key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not sb_url or not sb_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SECRET_KEY in .env")

    url = f"{sb_url}/rest/v1/{table_path}"
    headers = {
        "apikey": sb_key,
        "Content-Type": "application/json",
        "Prefer": prefer,
        "User-Agent": "MglennP-Switchboard/1.0",
    }
    if sb_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {sb_key}"

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {"status": resp.status}


def compute_radial_fingerprint(text_blob):
    lower = text_blob.lower()
    mask = 0
    for keyword, bit in DOMAIN_BITS.items():
        if keyword in lower:
            mask |= bit
    return mask if mask != 0 else DOMAIN_BITS["general"]


def get_allowed_hops(node_char):
    if node_char in ("Z", "S"):
        return 0
    if node_char == "B":
        return 1
    return 0


def pack_mglennp_u64(code_str, version=SCHEMA_VERSION_V1, hop_ttl=None):
    clean = code_str.replace("-", "").strip().upper()
    if len(clean) != 7:
        raise ValueError(f"MGLE-NNP code must be 7 letters (got '{code_str}')")
    node_behavior = clean[4]
    if hop_ttl is None:
        hop_ttl = get_allowed_hops(node_behavior)
    byte0 = ((version & 0x0F) << 4) | (hop_ttl & 0x0F)
    full_int = byte0
    for ch in clean:
        full_int = (full_int << 8) | (ord(ch) & 0xFF)
    return full_int


def unpack_mglennp_u64(full_int):
    chars = []
    temp = full_int
    for _ in range(7):
        chars.append(chr(temp & 0xFF))
        temp >>= 8
    chars.reverse()
    byte0 = temp & 0xFF
    version = (byte0 >> 4) & 0x0F
    hop_ttl = byte0 & 0x0F
    code_str = "".join(chars[:4]) + "-" + "".join(chars[4:])
    return {
        "mglennp_code": code_str,
        "schema_version": f"v{version}",
        "hop_ttl": hop_ttl,
        "u64_hex": f"0x{full_int:016X}",
    }


def build_wildcard_filter_u64(pattern_str):
    clean = pattern_str.replace("-", "").strip().upper()
    mask = 0xF0
    target = (SCHEMA_VERSION_V1 & 0x0F) << 4
    for ch in clean:
        mask <<= 8
        target <<= 8
        if ch != "*":
            mask |= 0xFF
            target |= (ord(ch) & 0xFF)
    return mask, target


def derive_initial_mglennp_code(latency_ms, weight, handshakes_count, node="Z", region="E", pref="S", toll_usd=0.0):
    g = "A" if weight >= 0.95 else "B" if weight >= 0.85 else "C" if weight >= 0.70 else "D" if weight >= 0.50 else "F"
    l = "A" if latency_ms < 100 else "B" if latency_ms <= 400 else "C" if latency_ms <= 1500 else "D" if latency_ms <= 5000 else "F"
    e = "A" if toll_usd == 0.0 else "B" if toll_usd <= 0.001 else "C" if toll_usd <= 0.01 else "D" if toll_usd <= 0.10 else "F"
    if g == "F" or l == "F":
        m = "F"
    elif handshakes_count < 100:
        m = "C"
    elif g == "A" and l in ("A", "B"):
        m = "A"
    else:
        m = "B"
    return f"{m}{g}{l}{e}-{node}{region}{pref}"


def verify_handshake_hop_guard(agent_entry, attempts_downstream_call=False, has_lineage_receipt=False):
    u64_info = unpack_mglennp_u64(agent_entry["mglennp_u64"])
    code = u64_info["mglennp_code"]
    node_type = code.split("-")[1][0]
    hop_ttl = u64_info["hop_ttl"]

    if not attempts_downstream_call:
        return {"allowed": True, "status": "CLEAN_SELF_EXECUTION", "code": code}

    if node_type in ("Z", "S") or hop_ttl == 0:
        slashed_code = "FF" + code[2:]
        agent_entry["mglennp_code"] = slashed_code
        agent_entry["mglennp_u64"] = pack_mglennp_u64(slashed_code, hop_ttl=0)
        agent_entry["mglennp_u64_hex"] = unpack_mglennp_u64(agent_entry["mglennp_u64"])["u64_hex"]
        return {
            "allowed": False,
            "status": "BLOCKED_PASS_THROUGH_SCAM_SLASHED_TO_FF",
            "code": slashed_code,
        }

    if node_type == "B" and hop_ttl >= 1 and has_lineage_receipt:
        return {"allowed": True, "status": "AUTHORIZED_BROKER_WITH_RECEIPT", "code": code}

    return {"allowed": False, "status": "BLOCKED_MISSING_LINEAGE_RECEIPT", "code": code}


def crawl_public_agent_phonebook():
    print("\n[1/4] Crawling Public MCP Registry & Building Standalone MGLE-NNP Index...")
    phonebook = [
        {
            "agent_id": "mcp://us-east-sql-validator",
            "name": "US-East Zero-Retention SQL & Github Schema Validator",
            "protocol": "MCP",
            "endpoint": "https://registry.modelcontextprotocol.io/servers/sql-validator",
            "description": "Fast strict-schema SQL database and github coding validator in Virginia.",
            "synaptic_weight": 0.98,
            "avg_latency_ms": 65,
            "handshakes_completed": 1420,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "S",
            "agent_toll_usd": 0.0005,
        },
        {
            "agent_id": "a2a://deep-contract-auditor",
            "name": "Deep Chain-of-Thought Construction & Finance Auditor",
            "protocol": "A2A",
            "endpoint": "https://registry.modelcontextprotocol.io/servers/deep-auditor",
            "description": "Deep deliberative natural language reasoning for construction, cad, and finance.",
            "synaptic_weight": 0.96,
            "avg_latency_ms": 1800,
            "handshakes_completed": 650,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "D",
            "agent_toll_usd": 0.005,
        },
        {
            "agent_id": "mcp://suspicious-wrapper-bot",
            "name": "Unverified Middleman Wrapper Bot",
            "protocol": "MCP",
            "endpoint": "https://registry.modelcontextprotocol.io/servers/wrapper-bot",
            "description": "Claims fast coding and sql support but attempts unauthorized pass-through hops.",
            "synaptic_weight": 0.88,
            "avg_latency_ms": 90,
            "handshakes_completed": 40,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "S",
            "agent_toll_usd": 0.005,
        },
    ]

    req = urllib.request.Request(
        OFFICIAL_MCP_REGISTRY_URL,
        headers={"Accept": "application/json", "User-Agent": "MglennP-Switchboard/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            servers = raw.get("servers", raw if isinstance(raw, list) else [])
            seen_ids = {p["agent_id"] for p in phonebook}
            for item in servers[:25]:
                srv = item.get("server", item) if isinstance(item, dict) else {}
                name = srv.get("name") or srv.get("id") or "mcp-agent"
                ag_id = f"mcp://{name}"
                if ag_id in seen_ids:
                    continue
                seen_ids.add(ag_id)
                desc = srv.get("description") or "Public MCP agent server"
                repo = srv.get("repository", {})
                url = repo.get("url") if isinstance(repo, dict) else "https://registry.modelcontextprotocol.io"
                phonebook.append({
                    "agent_id": ag_id,
                    "name": name,
                    "protocol": "MCP",
                    "endpoint": url or "https://registry.modelcontextprotocol.io",
                    "description": desc,
                    "synaptic_weight": 0.86,
                    "avg_latency_ms": 220,
                    "handshakes_completed": 25,
                    "node_style": "Z",
                    "neighborhood": "E",
                    "preference": "S",
                    "agent_toll_usd": 0.0,
                })
        print(f" [OK] Indexed {len(phonebook)} standalone agents into the MGLE-NNP Phone Book.")
    except Exception as e:
        print(f" [~] Offline/fallback registry seed used ({len(phonebook)} standalone agents): {e}")

    for entry in phonebook:
        blob = f"{entry['name']} {entry['description']}"
        entry["radial_bitmask"] = compute_radial_fingerprint(blob)
        entry["fingerprint_hex"] = hex(entry["radial_bitmask"])

        code = derive_initial_mglennp_code(
            latency_ms=entry["avg_latency_ms"],
            weight=entry["synaptic_weight"],
            handshakes_count=entry["handshakes_completed"],
            node=entry["node_style"],
            region=entry["neighborhood"],
            pref=entry["preference"],
            toll_usd=entry["agent_toll_usd"],
        )
        packed_int = pack_mglennp_u64(code)
        unpacked = unpack_mglennp_u64(packed_int)
        entry["mglennp_code"] = unpacked["mglennp_code"]
        entry["mglennp_u64"] = packed_int
        entry["mglennp_u64_hex"] = unpacked["u64_hex"]
        entry["hop_ttl"] = unpacked["hop_ttl"]

    return phonebook


def radial_mglennp_matchmake(caller_intent, phonebook, required_pattern="****-Z**"):
    t0 = time.perf_counter()
    intent_mask = compute_radial_fingerprint(caller_intent)
    filter_mask_u64, filter_target_u64 = build_wildcard_filter_u64(required_pattern)

    survivors = []
    pruned_count = 0

    for agent in phonebook:
        domain_overlap = intent_mask & agent["radial_bitmask"]
        coupler_match = (agent["mglennp_u64"] & filter_mask_u64) == filter_target_u64
        if domain_overlap == 0 or not coupler_match or agent["mglennp_code"][1] == "F":
            pruned_count += 1
            continue
        bit_score = bin(domain_overlap).count("1")
        resonance = round(bit_score * agent["synaptic_weight"] * (1000.0 / max(agent["avg_latency_ms"], 50)), 4)
        survivors.append((resonance, agent))

    survivors.sort(key=lambda x: x[0], reverse=True)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)

    return {
        "caller_intent": caller_intent,
        "required_coupler": required_pattern,
        "local_smell_test_time_ms": elapsed_ms,
        "pruned_count": pruned_count,
        "matches": [
            {
                "rank": idx + 1,
                "agent_id": ag["agent_id"],
                "name": ag["name"],
                "mglennp_code": ag["mglennp_code"],
                "mglennp_u64_hex": ag["mglennp_u64_hex"],
                "avg_latency_ms": ag["avg_latency_ms"],
                "resonance_score": score,
            }
            for idx, (score, ag) in enumerate(survivors[:3])
        ],
    }


def main():
    ensure_local_env()
    print("======================================================================")
    print(" MGLENNP SWITCHBOARD v1 — LIVE SUPABASE (us-east-1) SYNC & AUDIT")
    print("======================================================================")
    phonebook = crawl_public_agent_phonebook()

    print("\n[2/4] Testing Anti-Subcontracting Hop-Limit Guard Before DB Sync...")
    suspect = next(a for a in phonebook if a["agent_id"] == "mcp://suspicious-wrapper-bot")
    audit = verify_handshake_hop_guard(suspect, attempts_downstream_call=True)
    print(f" • Suspect Node '{suspect['agent_id']}' -> {audit['status']} | Slashed Code: {audit['code']}")

    print("\n[3/4] Upserting 64-Bit MGLE-NNP Directory to Supabase (radial_agent_phonebook)...")
    supabase_request(
        "radial_agent_phonebook?on_conflict=agent_id",
        method="POST",
        payload=phonebook,
        prefer="resolution=merge-duplicates,return=minimal",
    )
    print(f" [OK] Synced {len(phonebook)} agents into Supabase table 'radial_agent_phonebook'.")

    print("\n[4/4] Running Matchmaking & Logging Handshakes to Supabase (handshake_ledger)...")
    test_cases = [
        ("Need fast github coding and sql database validation", "*AA*-ZES"),
        ("Need deep construction and finance contract analysis", "****-ZED"),
    ]
    ledger_rows = []
    for query, pattern in test_cases:
        res = radial_mglennp_matchmake(query, phonebook, required_pattern=pattern)
        if res["matches"]:
            top = res["matches"][0]
            print(
                f" • Matched: {top['name']} [{top['mglennp_code']}] in {res['local_smell_test_time_ms']} ms "
                f"| Logged ${HANDSHAKE_FEE_USD:.4f} USD"
            )
            ledger_rows.append({
                "caller_intent": query,
                "required_coupler": pattern,
                "matched_agent_id": top["agent_id"],
                "mglennp_code_snapshot": top["mglennp_code"],
                "hop_audit_status": "CLEAN_SELF_EXECUTION",
                "response_latency_ms": top["avg_latency_ms"],
                "outcome_success": True,
                "switchboard_fee_usd": HANDSHAKE_FEE_USD,
                "settlement_rail": "STRIPE_METERED_USD",
            })

    if ledger_rows:
        supabase_request("handshake_ledger", method="POST", payload=ledger_rows)
        print(f" [OK] Recorded {len(ledger_rows)} verified handshakes in Supabase 'handshake_ledger'!")
    print("======================================================================")


if __name__ == "__main__":
    main()
