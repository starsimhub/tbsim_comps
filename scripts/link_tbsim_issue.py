#!/usr/bin/env python3
"""Link a filed tbsim GitHub issue to a harness failure."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LINKS_PATH = REPO_ROOT / "findings" / "issue_links.json"
REGRESSIONS_MODULE = "tests.test_tbsim_regressions"


def _load_links() -> dict:
    if LINKS_PATH.exists():
        return json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    return {"schema_version": 1, "links": {}}


def _parse_issue(value: str) -> int:
    match = re.search(r"(?:issues/(\d+)|#(\d+)|^(\d+)$)", value.strip())
    if not match:
        raise SystemExit(f"Invalid issue reference: {value!r}")
    return int(match.group(1) or match.group(2) or match.group(3))


def _resolve_test_id(key: str) -> tuple[str, str | None]:
    sys.path.insert(0, str(REPO_ROOT))
    from findings.bug_registry import BUGS

    if re.fullmatch(r"TBUG-\d+", key, re.I):
        tbug = key.upper()
        for bug in BUGS:
            if bug["id"].upper() == tbug:
                return f"{REGRESSIONS_MODULE}::{bug['test']}", bug["id"]
        raise SystemExit(f"Unknown {tbug}")

    if "::" in key:
        _, name = key.split("::", 1)
        for bug in BUGS:
            if bug["test"] == name:
                return key, bug["id"]
        return key, None

    for bug in BUGS:
        if bug["test"] == key:
            return f"{REGRESSIONS_MODULE}::{bug['test']}", bug["id"]

    if key.startswith("test_"):
        return f"{REGRESSIONS_MODULE}::{key}", None

    raise SystemExit(f"Could not resolve test id for {key!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link a tbsim GitHub issue to a validation failure."
    )
    parser.add_argument(
        "test",
        help="TBUG-001, regression test name, or full pytest node id",
    )
    parser.add_argument("issue", help="GitHub issue number or URL")
    args = parser.parse_args()

    test_id, tbug_id = _resolve_test_id(args.test)
    issue_num = _parse_issue(args.issue)

    data = _load_links()
    entry: dict[str, object] = {
        "issue": issue_num,
        "linked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if tbug_id:
        entry["tbug_id"] = tbug_id

    data.setdefault("links", {})[test_id] = entry
    data["schema_version"] = 1

    LINKS_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Linked {test_id} -> tbsim #{issue_num}")
    if tbug_id:
        print(f"  registry id: {tbug_id}")
    print(f"  updated: {LINKS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
