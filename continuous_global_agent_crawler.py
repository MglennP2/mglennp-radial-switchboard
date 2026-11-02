#!/usr/bin/env python3
from __future__ import annotations
import datetime, hashlib, json, os, urllib.parse, urllib.request
from typing import Any, Dict, List, Tuple


STATE_FILE = ".global_crawler_cursor.json"
GLOBAL_DISCOVERY_QUERIES: List[str] = [
    "topic:mcp-server",
    "topic:model-context-protocol",
    "topic:a2a-agent",
    "topic:mcp-tools",
    "mcp-server in:name,description",
    "fastmcp in:readme",
    "modelcontextprotocol in:readme",
    "agent2agent in:readme",
]
DOMAIN_KEYWORDS: Dict[str, int] = {
    "finance": 1 << 0, "crypto": 1 << 1, "coding": 1 << 2, "github": 1 << 3,
    "search": 1 << 4, "web": 1 << 5, "database": 1 << 6, "sql": 1 << 7,
    "weather": 1 << 8, "maps": 1 << 9, "construction": 1 << 10, "cad": 1 << 11,
    "commerce": 1 << 12, "payments": 1 << 13, "media": 1 << 14, "general": 1 << 15,
}


def compute_mgle_nnp_and_fingerprint(name: str, desc: str, homepage: str) -> Tuple[str, int, int, str]:
    blob = f"{name} {desc}".lower()
    domain_mask = 0
    for kw, bit in DOMAIN_KEYWORDS.items():
        if kw in blob:
            domain_mask |= bit
    if domain_mask == 0:
        domain_mask = DOMAIN_KEYWORDS["general"]
    has_live_url = bool(homepage and homepage.startswith("https://") and "github.com" not in homepage.lower())
    g_grade = "B" if has_live_url else "D"
    mgle_nnp = "CBBB-ZES" if has_live_url else "CDCB-ZES"
    upper_hash = int(hashlib.sha256(mgle_nnp.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF
    return mgle_nnp, (upper_hash << 32) | (domain_mask & 0xFFFFFFFF), domain_mask, g_grade


def crawl_batch() -> Dict[str, Any]:
    state = {"query_index": 0, "page": 1, "total_new_indexed": 0}
    if os.path.isfile(STATE_FILE):
        try:
            state = json.loads(open(STATE_FILE, "r", encoding="utf-8").read())
        except Exception:
            pass
    q_idx = int(state.get("query_index", 0)) % len(GLOBAL_DISCOVERY_QUERIES)
    page = max(1, min(20, int(state.get("page", 1))))
    q_str = GLOBAL_DISCOVERY_QUERIES[q_idx]
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "MglennP-Global-Crawler/2.2"}
    gh_tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if gh_tok:
        headers["Authorization"] = f"Bearer {gh_tok}"
    url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q_str)}&sort=updated&order=desc&per_page=30&page={page}"
    records = []
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as resp:
            items = json.loads(resp.read().decode("utf-8")).get("items", [])
            for it in items:
                fn = it.get("full_name") or "unknown/agent"
                desc = (it.get("description") or "MCP/A2A agent")[:400]
                hp = (it.get("homepage") or "").strip()
                ep = hp if hp.startswith("http") else (it.get("html_url") or f"https://github.com/{fn}")
                code, fp64, dmask, g = compute_mgle_nnp_and_fingerprint(fn, desc, hp)
                records.append({
                    "agent_slug": f"gh://{fn.lower()}", "display_name": fn, "endpoint_url": ep,
                    "source_registry": f"github:{q_str}", "mgle_nnp_code": code,
                    "fingerprint_64bit": fp64, "domain_bits_16": dmask, "guarantee_grade": g,
                    "last_probed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
    except Exception as e:
        return {"status": "error", "error": str(e)}
    next_p = page + 1 if page < 10 else 1
    state["page"] = next_p
    state["query_index"] = (q_idx + 1) % len(GLOBAL_DISCOVERY_QUERIES) if next_p == 1 else q_idx
    state["total_new_indexed"] = int(state.get("total_new_indexed", 0)) + len(records)
    open(STATE_FILE, "w", encoding="utf-8").write(json.dumps(state, indent=2))
    return {"status": "crawled", "query": q_str, "page": page, "discovered": len(records)}


if __name__ == "__main__":
    print(json.dumps(crawl_batch(), indent=2))
