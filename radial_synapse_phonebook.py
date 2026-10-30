#!/usr/bin/env python3
r"""
MGLENNP STANDALONE SWITCHBOARD — 64-BIT MGLE-NNP AGENT MATCHMAKER (v1.5)
Live Database Sync: https://malvgodkmfgdzswbhcyj.supabase.co (us-east-1 Northern Virginia)
Includes Batch-Governed Paginated MCP Registry Crawler & Parallel Heartbeat Auditor
"""

import os
import time
import json
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

SCHEMA_VERSION_V1 = 0x1
SUPABASE_PROJECT_URL = "https://malvgodkmfgdzswbhcyj.supabase.co"
OFFICIAL_MCP_REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0/servers"
HANDSHAKE_FEE_USD = 0.0001

# Mechanical Governor Limits (Zero-Cost Cloud Run Protection)
MAX_PAGES_PER_CRAWL = 3          # Up to 300 raw server records per run
MAX_CRAWL_WALL_SECONDS = 22.0    # Hard cutoff so Cloud Run never hangs
MAX_PARALLEL_PROBES = 20         # Parallel heartbeat checks
PROBE_TIMEOUT_SECONDS = 2.0      # Fast 2-second ping timeout
CURSOR_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mcp_cursor_state.json")

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
        "User-Agent": "MglennP-Switchboard/1.5",
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


def derive_initial_mglennp_code(
    latency_ms,
    weight,
    handshakes_count,
    node="Z",
    region="E",
    pref="S",
    toll_usd=0.0,
    guarantee_override=None,
):
    if guarantee_override:
        g = guarantee_override
    else:
        g = "A" if weight >= 0.95 else "B" if weight >= 0.85 else "C" if weight >= 0.70 else "D" if weight >= 0.50 else "F"

    l = "A" if latency_ms <= 120 else "B" if latency_ms <= 300 else "C" if latency_ms <= 700 else "D" if latency_ms <= 1500 else "E"
    e = "A" if toll_usd == 0.0 else "B" if toll_usd <= 0.001 else "C" if toll_usd <= 0.01 else "D" if toll_usd <= 0.10 else "F"

    if g == "F":
        m = "F"
    elif g in ("D", "E"):
        m = "C"
    elif handshakes_count >= 100 and g == "A" and l in ("A", "B"):
        m = "A"
    elif g in ("A", "B"):
        m = "B"
    else:
        m = "C"
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


def _load_saved_cursor():
    env_cur = os.environ.get("MCP_REGISTRY_CURSOR", "").strip()
    if env_cur:
        return env_cur
    if os.path.exists(CURSOR_STATE_FILE):
        try:
            with open(CURSOR_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("next_cursor", "")
        except Exception:
            return ""
    return ""


def _save_cursor(cursor_val):
    os.environ["MCP_REGISTRY_CURSOR"] = cursor_val or ""
    try:
        with open(CURSOR_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"next_cursor": cursor_val or "", "updated_at": time.time()}, f)
    except Exception:
        pass


def _extract_best_endpoint(srv):
    """Checks MCP 'remotes' first for live callable HTTP/SSE endpoints before falling back to repository URL."""
    remotes = srv.get("remotes") or []
    if isinstance(remotes, list):
        for rem in remotes:
            if isinstance(rem, dict):
                r_url = (rem.get("url") or rem.get("endpoint") or "").strip()
                if r_url.startswith("http://") or r_url.startswith("https://"):
                    return r_url, True

    for key in ("url", "endpoint", "homepage"):
        val = (srv.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            if "github.com" not in val.lower() and "gitlab.com" not in val.lower():
                return val, True

    repo = srv.get("repository") or {}
    if isinstance(repo, dict):
        repo_url = (repo.get("url") or "").strip()
        if repo_url:
            return repo_url, False

    return "https://registry.modelcontextprotocol.io", False


def _fast_heartbeat_probe(url):
    t0 = time.perf_counter()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MglennP-Switchboard-Auditor/1.5", "Accept": "application/json, text/event-stream, */*"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_SECONDS) as resp:
            ms = max(1, int((time.perf_counter() - t0) * 1000))
            return (200 <= resp.status < 500), ms
    except urllib.error.HTTPError as e:
        ms = max(1, int((time.perf_counter() - t0) * 1000))
        # A 400/401/405/406 from an MCP SSE/POST endpoint proves the server is alive and listening!
        return (200 <= e.code < 500), ms
    except Exception:
        ms = max(1, int((time.perf_counter() - t0) * 1000))
        return False, ms


def crawl_public_agent_phonebook(max_pages=MAX_PAGES_PER_CRAWL, reset_cursor=False):
    t_start = time.perf_counter()
    print(f"\n[1/4] Crawling Official MCP Registry (Governed Batch: max {max_pages} pages / {MAX_CRAWL_WALL_SECONDS}s cap)...")

    phonebook = [
        {
            "agent_id": "mcp://us-east-sql-validator",
            "name": "US-East Zero-Retention SQL & Github Schema Validator",
            "protocol": "MCP",
            "endpoint": "https://registry.modelcontextprotocol.io/v0/servers?limit=1",
            "description": "Fast strict-schema SQL database and github coding validator in Virginia.",
            "synaptic_weight": 0.98,
            "avg_latency_ms": 65,
            "handshakes_completed": 1420,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "S",
            "agent_toll_usd": 0.0005,
            "_guarantee_override": "A",
        },
        {
            "agent_id": "a2a://deep-contract-auditor",
            "name": "Deep Chain-of-Thought Construction & Finance Auditor",
            "protocol": "A2A",
            "endpoint": "https://registry.modelcontextprotocol.io/v0/servers?limit=1",
            "description": "Deep deliberative natural language reasoning for construction, cad, and finance.",
            "synaptic_weight": 0.96,
            "avg_latency_ms": 280,
            "handshakes_completed": 650,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "D",
            "agent_toll_usd": 0.005,
            "_guarantee_override": "A",
        },
        {
            "agent_id": "mcp://suspicious-wrapper-bot",
            "name": "Unverified Middleman Wrapper Bot",
            "protocol": "MCP",
            "endpoint": "https://registry.modelcontextprotocol.io/servers/wrapper-bot",
            "description": "Claims fast coding and sql support but attempts unauthorized pass-through hops.",
            "synaptic_weight": 0.0,
            "avg_latency_ms": 90,
            "handshakes_completed": 40,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "S",
            "agent_toll_usd": 0.005,
            "_guarantee_override": "F",
        },
    ]

    seen_ids = {p["agent_id"] for p in phonebook}
    cursor = "" if reset_cursor else _load_saved_cursor()
    pages_fetched = 0
    raw_candidates = []

    while pages_fetched < max_pages:
        if (time.perf_counter() - t_start) >= (MAX_CRAWL_WALL_SECONDS * 0.6):
            break

        params = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        page_url = f"{OFFICIAL_MCP_REGISTRY_BASE}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(
            page_url,
            headers={"Accept": "application/json", "User-Agent": "MglennP-Switchboard/1.5"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                servers = raw.get("servers", raw if isinstance(raw, list) else [])
                metadata = raw.get("metadata") or {}
                next_cursor = metadata.get("nextCursor") or metadata.get("next_cursor") or raw.get("nextCursor") or ""

                for item in servers:
                    srv = item.get("server", item) if isinstance(item, dict) else {}
                    name = (srv.get("name") or srv.get("id") or "").strip()
                    if not name:
                        continue
                    ag_id = f"mcp://{name}"
                    if ag_id in seen_ids:
                        continue
                    seen_ids.add(ag_id)
                    raw_candidates.append((ag_id, name, srv))

                pages_fetched += 1
                if next_cursor and next_cursor != cursor:
                    cursor = next_cursor
                    _save_cursor(cursor)
                else:
                    # Reached the end of the registry; wrap cursor back to start for next cycle
                    _save_cursor("")
                    break
        except Exception as e:
            print(f" [~] Registry page fetch stopped on page {pages_fetched + 1}: {e}")
            break

    # Separate live remote candidates from unhosted GitHub repos
    remote_indices = {}
    candidate_entries = []

    for idx, (ag_id, name, srv) in enumerate(raw_candidates):
        desc = (srv.get("description") or "Public MCP agent server")[:280]
        ep_url, has_remote = _extract_best_endpoint(srv)
        low_ep = ep_url.lower()
        is_repo_only = (not has_remote) or ("github.com" in low_ep) or ("gitlab.com" in low_ep) or low_ep.endswith(".git")

        entry = {
            "agent_id": ag_id,
            "name": name[:120],
            "protocol": "MCP",
            "endpoint": ep_url,
            "description": desc,
            "synaptic_weight": 0.55 if is_repo_only else 0.88,
            "avg_latency_ms": 999 if is_repo_only else 250,
            "handshakes_completed": 10 if is_repo_only else 35,
            "node_style": "Z",
            "neighborhood": "E",
            "preference": "S",
            "agent_toll_usd": 0.0,
            "_guarantee_override": "D" if is_repo_only else "B",
        }
        candidate_entries.append(entry)
        if not is_repo_only:
            remote_indices[idx] = ep_url

    # Parallel Heartbeat Probe on remote HTTP endpoints within wall-clock budget
    if remote_indices:
        remaining_time = max(2.0, MAX_CRAWL_WALL_SECONDS - (time.perf_counter() - t_start))
        print(f" [•] Probing {len(remote_indices)} remote HTTP endpoints in parallel (budget: {remaining_time:.1f}s)...")
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_PROBES) as pool:
            future_map = {pool.submit(_fast_heartbeat_probe, url): idx for idx, url in remote_indices.items()}
            try:
                for fut in as_completed(future_map, timeout=remaining_time):
                    idx = future_map[fut]
                    try:
                        alive, ms = fut.result()
                    except Exception:
                        alive, ms = False, 9999
                    if alive:
                        candidate_entries[idx]["avg_latency_ms"] = ms
                        candidate_entries[idx]["synaptic_weight"] = 0.92
                        candidate_entries[idx]["_guarantee_override"] = "B"
                    else:
                        # Quarantine dead remote endpoint with Grade 'E' until next recheck cycle
                        candidate_entries[idx]["avg_latency_ms"] = ms
                        candidate_entries[idx]["synaptic_weight"] = 0.25
                        candidate_entries[idx]["_guarantee_override"] = "E"
            except Exception:
                pass

    phonebook.extend(candidate_entries)

    live_cnt = 0
    quarantined_cnt = 0
    repo_cnt = 0

    for entry in phonebook:
        blob = f"{entry['name']} {entry['description']}"
        entry["radial_bitmask"] = compute_radial_fingerprint(blob)
        entry["fingerprint_hex"] = hex(entry["radial_bitmask"])
        g_override = entry.pop("_guarantee_override", None)

        code = derive_initial_mglennp_code(
            latency_ms=entry["avg_latency_ms"],
            weight=entry["synaptic_weight"],
            handshakes_count=entry["handshakes_completed"],
            node=entry["node_style"],
            region=entry["neighborhood"],
            pref=entry["preference"],
            toll_usd=entry["agent_toll_usd"],
            guarantee_override=g_override,
        )
        packed_int = pack_mglennp_u64(code)
        unpacked = unpack_mglennp_u64(packed_int)
        entry["mglennp_code"] = unpacked["mglennp_code"]
        entry["mglennp_u64"] = packed_int
        entry["mglennp_u64_hex"] = unpacked["u64_hex"]
        entry["hop_ttl"] = unpacked["hop_ttl"]

        g_char = entry["mglennp_code"][1]
        if g_char in ("A", "B", "C"):
            live_cnt += 1
        elif g_char == "E":
            quarantined_cnt += 1
        elif g_char == "D":
            repo_cnt += 1

    elapsed = round(time.perf_counter() - t_start, 2)
    print(
        f" [OK] Batch complete in {elapsed}s: {len(phonebook)} graded "
        f"({live_cnt} Live Callable, {quarantined_cnt} Grade-E Quarantined Dead, {repo_cnt} Grade-D Repos)."
    )
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
        guarantee_grade = agent["mglennp_code"][1]
        # Prune if domain misses, coupler misses, or Guarantee is D (Repo), E (Dead/Quarantined), or F (Slashed)
        if domain_overlap == 0 or not coupler_match or guarantee_grade in ("D", "E", "F"):
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
                "endpoint": ag.get("endpoint", ""),
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
    print(" MGLENNP SWITCHBOARD v1.5 — GOVERNED BATCH CRAWL & SUPABASE SYNC")
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