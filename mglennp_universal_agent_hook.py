#!/usr/bin/env python3
"""
MglennP Universal Agent Collaboration Hook (`mglennp_universal_agent_hook.py`)
==============================================================================
Connects the Gemini Chief-of-Staff Agent (via Google Drive `MglennP_GitHub_Staging_Manifest`)
with the Embedded MglennP Command Center Agent (`C:\\Users\\thesh\\mglennp_command_center` and
PythonAnywhere `/home/MglennP/mysite/flask_app.py`).

CAPABILITIES:
1. Multi-Repo & Multi-Host Auto-Deployer:
   Reads `MglennP_GitHub_Staging_Manifest` (`1Mikoqt-76Oxh4nrcz88KM-rC0OjrObxou1qf--SfO74`)
   when `STATUS: RELEASE_APPROVED` and `GATE_CODE: MGLENNP-GREENLIGHT-V2` are set (after
   Michael authorizes with his secret phrase in chat), and routes staged files to ANY
   MglennP target specified in `TARGET_REPO`:
     - `MglennP2/HomesteadMaintenance`       (Homestead Maintenance website & 3D AR Studio)
     - `MglennP2/mglennp-radial-switchboard` (Radial Switchboard Spec Rev 2.0)
     - `pythonanywhere://MglennP`            (Command Center Cockpit on mglennp.com)

2. Two-Way Agent Collaboration Feedback Loop:
   Writes a structured JSON execution receipt (`last_agent_hook_receipt.json`) and, if
   SMTP/Gmail credentials (`GMAIL_USER` / `GMAIL_APP_PASSWORD`) are present in `.env`,
   emails a `[MGLENNP-AGENT-HOOK]` completion receipt to `thesharpestspike@gmail.com`
   so the Gemini Chief-of-Staff agent can read the live commit SHA and deployment status!

3. Flask Webhook Route Generator (`--print-flask-route`):
   Outputs a drop-in `/api/agent-hook/sync` Flask route for `/home/MglennP/mysite/flask_app.py`
   so the Command Center on `mglennp.com` can trigger a sync anytime via a single HTTP GET/POST.

Zero external pip dependencies required (100% Python 3 standard library).
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_DOC_ID = "1Mikoqt-76Oxh4nrcz88KM-rC0OjrObxou1qf--SfO74"
ALLOWED_GATE_CODES = {"MGLENNP-GREENLIGHT-V2", "I love April", "i love april"}
PROTECTED_CORE_FILES = {"switchboard_api.py", "radial_synapse_phonebook.py"}
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent_hook_last_release.json")


def load_local_env() -> None:
    """Loads environment variables from local or PythonAnywhere .env files."""
    candidates = [
        ".env",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        r"C:\Users\thesh\mglennp_command_center\.env",
        "/home/MglennP/.env",
        "/home/MglennP/mysite/.env",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'").strip('"')
                        if k and k not in os.environ:
                            os.environ[k] = v
            except OSError:
                pass


def http_json_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 15.0,
) -> Tuple[int, Dict[str, Any]]:
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "MglennP-Universal-Agent-Hook/2.0 (+https://radialswitchboard.com)",
    }
    if headers:
        req_headers.update(headers)

    data_bytes: Optional[bytes] = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw else {"error": str(e)}
        except json.JSONDecodeError:
            return e.code, {"error": raw or str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def github_put_content(
    repo: str,
    branch: str,
    target_path: str,
    content_text: str,
    commit_message: str,
) -> Dict[str, Any]:
    """Commits a file directly to any MglennP GitHub repository via the GitHub Contents REST API."""
    token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    if not token:
        return {"status": "error", "error": "Missing GITHUB_TOKEN in .env or environment"}

    clean_path = target_path.strip().lstrip("/")
    api_url = f"https://api.github.com/repos/{repo}/contents/{clean_path}"
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    get_status, existing = http_json_request(
        f"{api_url}?ref={urllib.parse.quote(branch)}",
        method="GET",
        headers=auth_headers,
    )
    existing_sha = existing.get("sha") if get_status == 200 and isinstance(existing, dict) else None

    put_payload: Dict[str, Any] = {
        "message": commit_message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if existing_sha:
        put_payload["sha"] = existing_sha

    put_status, put_resp = http_json_request(
        api_url,
        method="PUT",
        payload=put_payload,
        headers=auth_headers,
    )
    if put_status in (200, 201):
        commit_obj = put_resp.get("commit", {})
        return {
            "status": "committed",
            "repo": repo,
            "branch": branch,
            "path": clean_path,
            "commit_sha": commit_obj.get("sha"),
            "html_url": commit_obj.get("html_url") or f"https://github.com/{repo}/blob/{branch}/{clean_path}",
        }
    return {"status": "error", "http_status": put_status, "repo": repo, "path": clean_path, "details": put_resp}


def fetch_staging_manifest(doc_id: str = MANIFEST_DOC_ID) -> str:
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MglennP-Universal-Agent-Hook/2.0"},
    )
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def parse_staging_manifest(raw_text: str) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    headers: Dict[str, str] = {}
    for key in ("STATUS", "GATE_CODE", "RELEASE_ID", "COMMIT_MESSAGE", "TARGET_REPO", "TARGET_BRANCH"):
        m = re.search(rf"^{key}:\s*(.+)$", raw_text, flags=re.MULTILINE)
        if m:
            headers[key] = m.group(1).strip()

    # Support optional per-file repo routing: ===BEGIN_FILE: repo_or_path===
    pattern = re.compile(
        r"===BEGIN_FILE:\s*([^\r\n=]+)===\r?\n(.*?)\r?\n===END_FILE===",
        flags=re.DOTALL,
    )
    files: List[Tuple[str, str]] = []
    for match in pattern.finditer(raw_text):
        spec = match.group(1).strip()
        body = match.group(2) + "\n"
        files.append((spec, body))
    return headers, files


def send_receipt_email_if_configured(receipt: Dict[str, Any]) -> bool:
    """Sends a `[MGLENNP-AGENT-HOOK]` receipt email to thesharpestspike@gmail.com if SMTP credentials exist."""
    smtp_user = os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASS")
    target_email = os.environ.get("ALERT_EMAIL", "thesharpestspike@gmail.com")
    if not smtp_user or not smtp_pass:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[MGLENNP-AGENT-HOOK] Synced Release {receipt.get('release_id')} ({receipt.get('status')})"
        msg["From"] = smtp_user
        msg["To"] = target_email
        msg.set_content(json.dumps(receipt, indent=2))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception:
        return False


def execute_sync_once(force: bool = False) -> Dict[str, Any]:
    load_local_env()
    try:
        raw_text = fetch_staging_manifest()
    except Exception as e:
        return {"status": "waiting_for_link_share", "error": str(e)}

    headers, files = parse_staging_manifest(raw_text)
    status = headers.get("STATUS", "STANDBY").upper()
    gate = headers.get("GATE_CODE", "")
    release_id = headers.get("RELEASE_ID", "UNKNOWN")
    default_repo = headers.get("TARGET_REPO", "MglennP2/mglennp-radial-switchboard")
    default_branch = headers.get("TARGET_BRANCH", "main")
    commit_msg = headers.get("COMMIT_MESSAGE", f"MglennP Agent Hook Sync [{release_id}]")

    if status != "RELEASE_APPROVED":
        return {"status": "standby", "release_id": release_id, "message": "Manifest is locked in STANDBY."}

    if gate not in ALLOWED_GATE_CODES:
        return {"status": "blocked", "release_id": release_id, "error": f"Invalid gate code: {gate!r}"}

    manifest_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]
    if not force and os.path.isfile(STATE_FILE):
        try:
            last_state = json.loads(open(STATE_FILE, "r", encoding="utf-8").read())
            if last_state.get("manifest_hash") == manifest_hash and last_state.get("release_id") == release_id:
                return {
                    "status": "already_applied",
                    "release_id": release_id,
                    "manifest_hash": manifest_hash,
                    "previous_results": last_state.get("results", []),
                }
        except Exception:
            pass

    results: List[Dict[str, Any]] = []
    for file_spec, body in files:
        # Allow `Owner/Repo:path/to/file` or plain `path/to/file` (which uses TARGET_REPO)
        if ":" in file_spec and "/" in file_spec.split(":", 1)[0]:
            repo_name, rel_path = file_spec.split(":", 1)
        else:
            repo_name, rel_path = default_repo, file_spec

        rel_path = rel_path.strip().lstrip("/")
        if os.path.basename(rel_path) in PROTECTED_CORE_FILES:
            results.append({"path": rel_path, "status": "skipped_locked_core_file"})
            continue

        res = github_put_content(
            repo=repo_name.strip(),
            branch=default_branch,
            target_path=rel_path,
            content_text=body,
            commit_message=f"{commit_msg} [{release_id}]",
        )
        results.append(res)

    receipt = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "synced",
        "release_id": release_id,
        "target_repo": default_repo,
        "manifest_hash": manifest_hash,
        "results": results,
    }

    if all(r.get("status") == "committed" for r in results if r.get("status") != "skipped_locked_core_file"):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=2)
        except OSError:
            pass

    receipt["email_notified"] = send_receipt_email_if_configured(receipt)
    return receipt


FLASK_WEBHOOK_SNIPPET = """
# ==============================================================================
# MGLENNP UNIVERSAL AGENT COLLABORATION HOOK ROUTE (`/api/agent-hook/sync`)
# Add to `/home/MglennP/mysite/flask_app.py` so Command Center & Gemini collaborate
# ==============================================================================
@app.route('/api/agent-hook/sync', methods=['GET', 'POST'])
def trigger_agent_hook_sync():
    from mglennp_universal_agent_hook import execute_sync_once
    receipt = execute_sync_once(force=False)
    record_audit(f"Agent Hook Sync [{receipt.get('release_id')}]: {receipt.get('status')}", "agent-hook")
    return receipt
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="MglennP Universal Agent Collaboration Hook")
    parser.add_argument("--daemon", action="store_true", help="Poll MglennP_GitHub_Staging_Manifest every 60 seconds")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds for --daemon mode")
    parser.add_argument("--force", action="store_true", help="Force re-sync even if manifest hash matches last run")
    parser.add_argument("--print-flask-route", action="store_true", help="Print the Flask webhook route snippet")
    parser.add_argument("--sync-homestead-builder", action="store_true", help="Sync Homestead Maintenance Builder components & gemini-2.5-pro backend")
    args = parser.parse_args()

    if getattr(args, 'sync_homestead_builder', False):
        try:
            from update_homestead_components import commit_homestead_builder_files
            print('=== EXECUTING --sync-homestead-builder DEPLOYMENT ===')
            commit_homestead_builder_files()
            return 0
        except Exception as e:
            print('Error executing --sync-homestead-builder:', e)
            return 1

    if args.print_flask_route:
        print(FLASK_WEBHOOK_SNIPPET)
        return 0

    if args.daemon:
        print(f"=== MGLENNP UNIVERSAL AGENT HOOK DAEMON ACTIVE (Polling every {args.interval}s) ===")
        while True:
            rec = execute_sync_once(force=False)
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {rec.get('status').upper()} | Release: {rec.get('release_id')}")
            for item in rec.get("results", []):
                print(f"   -> {item.get('repo')}:{item.get('path')} [{item.get('status')}] {item.get('html_url') or item.get('error')}")
            time.sleep(max(15, args.interval))

    rec = execute_sync_once(force=args.force)
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
