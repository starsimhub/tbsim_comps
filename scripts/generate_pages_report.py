#!/usr/bin/env python3
"""Generate a historical GitHub Pages report from pytest JUnit XML output."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET


def _infer_file_from_classname(classname: str) -> str:
    if not classname:
        return ""
    return f"{classname.replace('.', '/')}.py"


def _infer_source_from_detail(detail: str, fallback_file: str, fallback_line: str) -> tuple[str, str]:
    match = re.search(r"(tests/[^:\s]+\.py):(\d+)", detail)
    if match:
        return match.group(1), match.group(2)
    return fallback_file, fallback_line


def _parse_junit(junit_path: Path) -> tuple[list[dict], dict]:
    if not junit_path.exists():
        return [
            {
                "id": "workflow::pytest-results",
                "classname": "workflow",
                "name": "pytest-results",
                "status": "error",
                "file": "",
                "line": "",
                "duration": 0.0,
                "detail": f"JUnit XML was not found at {junit_path}. The test command may not have started or may have failed before pytest wrote results.",
            }
        ], {"total": 1, "passed": 0, "failed": 0, "error": 1, "skipped": 0}

    tree = ET.parse(junit_path)
    root = tree.getroot()

    testcases: list[dict] = []
    summary = {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}

    for case in root.iter("testcase"):
        classname = case.attrib.get("classname", "").strip()
        name = case.attrib.get("name", "").strip()
        file_path = case.attrib.get("file", "").strip() or _infer_file_from_classname(classname)
        line = case.attrib.get("line", "").strip()
        duration = float(case.attrib.get("time", "0") or 0)

        test_id = f"{classname}::{name}" if classname else name
        status = "passed"
        detail = ""

        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")

        if failure is not None:
            status = "failed"
            detail = (failure.text or failure.attrib.get("message", "")).strip()
        elif error is not None:
            status = "error"
            detail = (error.text or error.attrib.get("message", "")).strip()
        elif skipped is not None:
            status = "skipped"
            detail = (skipped.text or skipped.attrib.get("message", "")).strip()

        file_path, line = _infer_source_from_detail(detail, file_path, line)

        summary["total"] += 1
        summary[status] += 1

        testcases.append(
            {
                "id": test_id,
                "classname": classname,
                "name": name,
                "status": status,
                "file": file_path,
                "line": line,
                "duration": duration,
                "detail": detail,
            }
        )

    return testcases, summary


def _load_history(path: Path) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"runs": []}


def _status_badge(status: str) -> str:
    palette = {
        "passed": ("#14532d", "#dcfce7"),
        "failed": ("#7f1d1d", "#fee2e2"),
        "error": ("#7c2d12", "#ffedd5"),
        "skipped": ("#1f2937", "#e5e7eb"),
    }
    fg, bg = palette.get(status, ("#1f2937", "#e5e7eb"))
    return (
        f"<span class='badge' style='color:{fg};background:{bg};'>"
        f"{html.escape(status)}</span>"
    )


def _source_url(repo: str, sha: str, file_path: str, line: str) -> str | None:
    if not repo or not sha or not file_path:
        return None
    anchor = f"#L{line}" if line else ""
    return f"https://github.com/{repo}/blob/{sha}/{file_path}{anchor}"


def _render_run_page(
    run_dir: Path,
    run_meta: dict,
    tests: list[dict],
    pytest_report_relpath: str | None,
) -> None:
    failed = [t for t in tests if t["status"] in {"failed", "error"}]
    by_status = {"failed": 0, "error": 0, "skipped": 0, "passed": 0}
    for t in tests:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1

    rows = []
    detail_cards = []
    for idx, t in enumerate(tests):
        anchor = f"test-{idx}"
        source = _source_url(run_meta["repo"], run_meta["sha"], t["file"], t["line"])
        source_link = (
            f"<a href='{html.escape(source)}' target='_blank' rel='noopener'>source</a>"
            if source
            else "-"
        )
        rows.append(
            "<tr>"
            f"<td><a href='#{anchor}'>{html.escape(t['id'])}</a></td>"
            f"<td>{_status_badge(t['status'])}</td>"
            f"<td>{t['duration']:.3f}s</td>"
            f"<td>{source_link}</td>"
            "</tr>"
        )

        if t["status"] in {"failed", "error"}:
            detail = html.escape(t["detail"][:20000] or "No traceback provided.")
            detail_cards.append(
                "<section class='card'>"
                f"<h3 id='{anchor}'>{html.escape(t['id'])}</h3>"
                f"<p>{_status_badge(t['status'])}</p>"
                f"<pre>{detail}</pre>"
                "</section>"
            )

    rich_report_panel = (
        "<details class='card rich-report' open>"
        "<summary><span>Rich pytest report</span><small>Click to collapse</small></summary>"
        f"<iframe src='{html.escape(pytest_report_relpath)}' title='Rich pytest-html report'></iframe>"
        f"<p><a class='button' href='{html.escape(pytest_report_relpath)}'>Open rich report in a new tab</a></p>"
        "</details>"
        if pytest_report_relpath
        else (
            "<section class='card rich-report empty'>"
            "<h2>Rich pytest report unavailable</h2>"
            "<p>The pytest-html artifact was not produced for this run.</p>"
            "</section>"
        )
    )

    fail_list = "".join(
        f"<li><a href='#test-{i}'>{html.escape(t['id'])}</a></li>"
        for i, t in enumerate(tests)
        if t["status"] in {"failed", "error"}
    )
    if not fail_list:
        fail_list = "<li>No failing tests in this run.</li>"

    content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Test Run {html.escape(run_meta["run_id"])} - {html.escape(run_meta["workflow"])}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    :root {{ color-scheme: dark; --bg:#070b16; --panel:rgba(15,23,42,.74); --panel-strong:rgba(15,23,42,.92); --border:rgba(148,163,184,.22); --text:#e5eefb; --muted:#9fb0c6; --accent:#7dd3fc; --accent-strong:#2563eb; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: Inter, ui-sans-serif, system-ui, sans-serif; margin: 0; background: radial-gradient(circle at 15% 0%, rgba(59,130,246,.24), transparent 32rem), radial-gradient(circle at 85% 10%, rgba(14,165,233,.18), transparent 28rem), linear-gradient(180deg, #020617, var(--bg)); color:var(--text); }}
    .wrap {{ max-width: 1320px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: clamp(2rem, 4vw, 4rem); letter-spacing: -.055em; margin: 10px 0 4px; }}
    h2 {{ font-size: 1.05rem; letter-spacing: -.02em; }}
    .subnav {{ color: var(--muted); margin-bottom: 18px; }}
    .grid {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 14px; }}
    .card {{ background:linear-gradient(180deg, var(--panel), rgba(15,23,42,.56)); border:1px solid var(--border); border-radius:18px; padding:18px; margin-top: 16px; box-shadow: 0 18px 55px rgba(2,6,23,.32); backdrop-filter: blur(18px); }}
    .grid .card p {{ font-size: 2rem; font-weight: 800; margin: 0; letter-spacing: -.05em; }}
    .badge {{ font-size: 11px; border-radius: 999px; padding: 4px 10px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ text-align:left; border-bottom:1px solid rgba(148,163,184,.18); padding: 10px 8px; font-size: 14px; vertical-align: top; }}
    th {{ color:#b8c7dc; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
    a {{ color:var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .button {{ display:inline-block; margin: 8px 0 0; background:linear-gradient(135deg, var(--accent-strong), #0891b2); color:white; padding:10px 14px; border-radius:12px; font-weight:700; box-shadow: 0 10px 30px rgba(37,99,235,.26); }}
    pre {{ font-family:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; background:#020617; border-radius:14px; padding:14px; border:1px solid var(--border); overflow-x:auto; }}
    .rich-report {{ padding: 0; overflow: hidden; }}
    .rich-report summary {{ cursor:pointer; list-style:none; display:flex; align-items:center; justify-content:space-between; gap: 16px; padding: 16px 18px; border-bottom:1px solid var(--border); font-weight:800; letter-spacing:-.02em; }}
    .rich-report summary::-webkit-details-marker {{ display:none; }}
    .rich-report summary small {{ color:var(--muted); font-weight:600; letter-spacing:0; }}
    .rich-report iframe {{ display:block; width:100%; min-height: 780px; border:0; background:#fff; }}
    .rich-report p {{ margin: 12px 18px 18px; }}
    .empty {{ padding: 18px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Run #{html.escape(str(run_meta["run_number"]))} (attempt {html.escape(str(run_meta["run_attempt"]))})</h1>
    <p class="subnav"><a href="../../index.html">Back to dashboard</a> · <a href="{html.escape(run_meta["run_url"])}">GitHub Actions run</a></p>
    {rich_report_panel}
    <div class="grid">
      <div class="card"><h2>Total</h2><p>{run_meta["summary"]["total"]}</p></div>
      <div class="card"><h2>Passed</h2><p>{by_status["passed"]}</p></div>
      <div class="card"><h2>Failed/Error</h2><p>{by_status["failed"] + by_status["error"]}</p></div>
      <div class="card"><h2>Skipped</h2><p>{by_status["skipped"]}</p></div>
    </div>
    <section class="card">
      <h2>Failing tests</h2>
      <ul>{fail_list}</ul>
    </section>
    <section class="card">
      <h2>All tests</h2>
      <table>
        <thead><tr><th>Test</th><th>Status</th><th>Duration</th><th>Link</th></tr></thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </section>
    {"".join(detail_cards)}
  </div>
</body>
</html>
"""
    run_dir.joinpath("index.html").write_text(content, encoding="utf-8")


def _render_dashboard(site_dir: Path, runs: list[dict]) -> None:
    runs_sorted = sorted(
        runs,
        key=lambda item: (item.get("timestamp", ""), int(item.get("run_number", 0))),
        reverse=True,
    )

    # Build a compact test status history timeline across all runs.
    all_test_ids: set[str] = set()
    for run in runs_sorted:
        all_test_ids.update(run.get("tests", {}).keys())

    run_headers = "".join(
        "<th><a href='{report_path}' title='Run #{run_number} ({status})'>#{run_number}.{run_attempt}</a></th>".format(
            report_path=html.escape(run["report_path"]),
            run_number=html.escape(str(run["run_number"])),
            run_attempt=html.escape(str(run["run_attempt"])),
            status=html.escape(run["status"]),
        )
        for run in runs_sorted
    )

    matrix_rows = []
    for test_id in sorted(all_test_ids):
        cells = []
        for run in runs_sorted:
            status = run.get("tests", {}).get(test_id, "not-run")
            color = {
                "passed": "#22c55e",
                "failed": "#ef4444",
                "error": "#fb923c",
                "skipped": "#94a3b8",
                "not-run": "#334155",
            }.get(status, "#334155")
            cell = (
                "<td><a href='{run_link}' title='{status}'><span class='dot' style='background:{color};'></span></a></td>"
            ).format(
                run_link=html.escape(run["report_path"]),
                status=html.escape(status),
                color=color,
            )
            cells.append(cell)
        matrix_rows.append(
            "<tr><td>{}</td>{}</tr>".format(html.escape(test_id), "".join(cells))
        )

    run_rows = []
    for run in runs_sorted:
        s = run["summary"]
        run_rows.append(
            "<tr>"
            f"<td><a href='{html.escape(run['report_path'])}'>#{run['run_number']}.{run['run_attempt']}</a></td>"
            f"<td>{_status_badge(run['status'])}</td>"
            f"<td>{html.escape(run['timestamp'])}</td>"
            f"<td>{s['passed']}/{s['total']}</td>"
            f"<td>{s['failed']}</td>"
            f"<td>{s['error']}</td>"
            f"<td>{s['skipped']}</td>"
            f"<td><a href='{html.escape(run['run_url'])}'>actions</a></td>"
            "</tr>"
        )

    total_runs = len(runs_sorted)
    latest = runs_sorted[0] if runs_sorted else None
    latest_text = "No runs yet."
    if latest:
        latest_text = (
            f"Latest run: #{latest['run_number']}.{latest['run_attempt']} "
            f"({latest['summary']['passed']}/{latest['summary']['total']} passed)"
        )

    content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>tbsim validation dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    :root {{ color-scheme: dark; --bg:#070b16; --panel:rgba(15,23,42,.74); --border:rgba(148,163,184,.22); --text:#e5eefb; --muted:#9fb0c6; --accent:#7dd3fc; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: Inter, ui-sans-serif, system-ui, sans-serif; margin: 0; background: radial-gradient(circle at 15% 0%, rgba(59,130,246,.24), transparent 32rem), radial-gradient(circle at 85% 10%, rgba(14,165,233,.18), transparent 28rem), linear-gradient(180deg, #020617, var(--bg)); color:var(--text); }}
    .wrap {{ max-width: 1440px; margin: 0 auto; padding: 28px; }}
    .hero {{ background:linear-gradient(135deg, rgba(30,41,59,.88), rgba(15,23,42,.72)); border:1px solid var(--border); border-radius: 22px; padding: 26px; box-shadow: 0 24px 70px rgba(2,6,23,.36); backdrop-filter: blur(18px); }}
    h1 {{ font-size: clamp(2.2rem, 4vw, 4.6rem); letter-spacing: -.06em; margin: 6px 0 10px; }}
    h2 {{ margin: 8px 0 12px; letter-spacing: -.025em; }}
    p {{ color:var(--muted); }}
    .badge {{ font-size: 11px; border-radius: 999px; padding: 4px 10px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; }}
    .card {{ background:linear-gradient(180deg, var(--panel), rgba(15,23,42,.56)); border:1px solid var(--border); border-radius: 18px; padding: 18px; margin-top: 16px; box-shadow: 0 18px 55px rgba(2,6,23,.32); backdrop-filter: blur(18px); }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ text-align:left; border-bottom:1px solid rgba(148,163,184,.18); padding: 10px 8px; font-size: 13px; }}
    th {{ color:#b8c7dc; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
    a {{ color:var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .matrix {{ overflow-x: auto; }}
    .dot {{ width: 12px; height: 12px; border-radius: 999px; display: inline-block; box-shadow: 0 0 0 3px rgba(255,255,255,.05); }}
    .small th, .small td {{ padding: 6px; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>tbsim validation test dashboard</h1>
      <p>{html.escape(latest_text)}</p>
      <p>Total tracked runs: {total_runs}</p>
    </section>
    <section class="card">
      <h2>Run history</h2>
      <table>
        <thead><tr><th>Run</th><th>Status</th><th>Timestamp (UTC)</th><th>Passed</th><th>Failed</th><th>Error</th><th>Skipped</th><th>Link</th></tr></thead>
        <tbody>
          {"".join(run_rows)}
        </tbody>
      </table>
    </section>
    <section class="card matrix">
      <h2>All tests across previous executions</h2>
      <table class="small">
        <thead><tr><th>Test ID</th>{run_headers}</tr></thead>
        <tbody>
          {"".join(matrix_rows)}
        </tbody>
      </table>
      <p>Dot colors: green=passed, red=failed, orange=error, gray=skipped, dark=not run.</p>
    </section>
  </div>
</body>
</html>
"""
    site_dir.joinpath("index.html").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate GitHub Pages report with test history."
    )
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--site-dir", required=True, type=Path)
    parser.add_argument("--existing-history", type=Path)
    parser.add_argument("--pytest-html", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-number", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ref-name", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()

    args.site_dir.mkdir(parents=True, exist_ok=True)
    run_dir = args.site_dir / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    tests, summary = _parse_junit(args.junit)

    # Copy raw artifacts for direct inspection.
    junit_target = run_dir / "junit.xml"
    if args.junit.exists():
        junit_target.write_text(args.junit.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        junit_target.write_text(
            "<testsuites><testsuite errors='1' failures='0' skipped='0' tests='1'>"
            "<testcase classname='workflow' name='pytest-results'>"
            "<error message='JUnit XML was not produced'>The pytest JUnit XML artifact was not found.</error>"
            "</testcase></testsuite></testsuites>\n",
            encoding="utf-8",
        )

    pytest_html_relpath = None
    if args.pytest_html and args.pytest_html.exists():
        html_target = run_dir / "pytest-report.html"
        html_target.write_text(
            args.pytest_html.read_text(encoding="utf-8"), encoding="utf-8"
        )
        pytest_html_relpath = "pytest-report.html"

    history_path = args.existing_history if args.existing_history else Path("")
    history = _load_history(history_path) if str(history_path) else {"runs": []}

    test_status_map = {t["id"]: t["status"] for t in tests}
    run_status = "failed" if summary["failed"] or summary["error"] else "passed"
    if summary["total"] > 0 and summary["skipped"] == summary["total"]:
        run_status = "skipped"

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    run_meta = {
        "run_id": args.run_id,
        "run_number": args.run_number,
        "run_attempt": args.run_attempt,
        "workflow": args.workflow,
        "repo": args.repo,
        "sha": args.sha,
        "ref_name": args.ref_name,
        "run_url": args.run_url,
        "status": run_status,
        "summary": summary,
        "tests": test_status_map,
        "timestamp": now,
        "report_path": f"runs/{args.run_id}/index.html",
    }

    runs = history.get("runs", [])
    runs = [
        r
        for r in runs
        if not (
            str(r.get("run_id")) == args.run_id
            and int(r.get("run_attempt", 1)) == args.run_attempt
        )
    ]
    runs.append(run_meta)
    runs = sorted(runs, key=lambda r: (r.get("timestamp", ""), r.get("run_number", 0)))
    history["runs"] = runs
    history["generated_at"] = now
    history["schema_version"] = 1

    _render_run_page(run_dir, run_meta, tests, pytest_html_relpath)
    _render_dashboard(args.site_dir, runs)
    (args.site_dir / "history.json").write_text(
        json.dumps(history, indent=2, sort_keys=True), encoding="utf-8"
    )

    note = textwrap.dedent(
        """
        Generated by scripts/generate_pages_report.py.
        This folder is published to GitHub Pages by CI.
        """
    ).strip()
    (args.site_dir / "README.txt").write_text(f"{note}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
