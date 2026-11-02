#!/usr/bin/env python3
from __future__ import annotations
import os, re, sys, urllib.request
from typing import Dict, List, Tuple
from homestead_crew_and_gitops_agent import github_autocommit_file, load_local_env


MANIFEST_DOC_ID = "1Mikoqt-76Oxh4nrcz88KM-rC0OjrObxou1qf--SfO74"
ALLOWED_GATE_CODES = {"MGLENNP-GREENLIGHT-V2", "I love April", "i love april"}
PROTECTED_CORE_FILES = {"switchboard_api.py", "radial_synapse_phonebook.py"}


def fetch_manifest_text(doc_id: str = MANIFEST_DOC_ID) -> str:
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    req = urllib.request.Request(url, headers={"User-Agent": "MglennP-Cloud-Bridge/2.2"})
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def parse_manifest(raw_text: str) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    headers: Dict[str, str] = {}
    for key in ("STATUS", "GATE_CODE", "RELEASE_ID", "COMMIT_MESSAGE", "TARGET_REPO", "TARGET_BRANCH"):
        m = re.search(rf"^{key}:\s*(.+)$", raw_text, flags=re.MULTILINE)
        if m:
            headers[key] = m.group(1).strip()
    clean_text = raw_text.replace("\uec03", "").replace("\uec02", "")
    pattern = re.compile(r"===BEGIN_FILE:\s*([^\r\n=]+)===\r?\n(.*?)\r?\n===END_FILE===", flags=re.DOTALL)
    files: List[Tuple[str, str]] = []
    for match in pattern.finditer(clean_text):
        rel_path = match.group(1).strip().lstrip("/")
        body = match.group(2) + "\n"
        files.append((rel_path, body))
    return headers, files


def run_global_crawler_tick() -> None:
    try:
        from continuous_global_agent_crawler import crawl_batch
            crawl_res = crawl_batch()
            print(f"  [GLOBAL CRAWLER TICK] {crawl_res}")
    except Exception as exc:
        print(f"  [GLOBAL CRAWLER NOTE] {exc}")


def sync_manifest() -> int:
    load_local_env()
    run_global_crawler_tick()
    try:
        raw_text = fetch_manifest_text()
    except Exception as e:
        print(f"[WAITING] Could not read MglennP_GitHub_Staging_Manifest ({e}).")
        return 0
    headers, files = parse_manifest(raw_text)
    status = headers.get("STATUS", "STANDBY").upper()
    gate = headers.get("GATE_CODE", "")
    release_id = headers.get("RELEASE_ID", "UNKNOWN")
    commit_msg = headers.get("COMMIT_MESSAGE", f"Autonomous Cloud Bridge Release {release_id}")
    if status != "RELEASE_APPROVED" or gate not in ALLOWED_GATE_CODES:
        return 0
    for spec, body in files:
        if ":" in spec and "/" in spec.split(":", 1)[0]:
            repo_name, rel_path = spec.split(":", 1)
            if repo_name.strip() != "MglennP2/mglennp-radial-switchboard":
                continue
        else:
            rel_path = spec
        rel_path = rel_path.strip().lstrip("/")
        if os.path.basename(rel_path) in PROTECTED_CORE_FILES:
            continue
        tmp_path = f".staged_{os.path.basename(rel_path)}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(body)
        github_autocommit_file(local_file_path=tmp_path, repo_target_path=rel_path, commit_message=f"{commit_msg} [{release_id}]")
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(sync_manifest())
