#!/usr/bin/env python3
"""Generate a historical GitHub Pages report from pytest JUnit XML output."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
import re
import sys
import textwrap
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET

_REPO_ROOT = Path(__file__).resolve().parents[1]
TBSIM_REPO = "starsimhub/tbsim"
TBSIM_ISSUES_URL = f"https://github.com/{TBSIM_REPO}/issues"
TBSIM_NEW_ISSUE_URL = f"https://github.com/{TBSIM_REPO}/issues/new"


def _get_bug_registry() -> dict[str, dict]:
    try:
        root = str(_REPO_ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)
        from findings.bug_registry import BUG_BY_TEST

        return BUG_BY_TEST
    except Exception:
        return {}


_BUG_BY_TEST = _get_bug_registry()


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
    cls = {
        "passed": "badge-pass",
        "failed": "badge-fail",
        "error": "badge-err",
        "skipped": "badge-skip",
    }.get(status, "badge-skip")
    return f"<span class='badge {cls}'>{html.escape(status)}</span>"


def _parse_test_id(test_id: str) -> tuple[str, str]:
    if "::" in test_id:
        module, name = test_id.split("::", 1)
        return module, name
    return "", test_id


def _is_flaky(test_id: str, runs: list[dict]) -> bool:
    statuses = {run.get("tests", {}).get(test_id) for run in runs}
    statuses.discard(None)
    statuses.discard("not-run")
    return bool(
        len(statuses) > 1
        and "passed" in statuses
        and statuses.intersection({"failed", "error"})
    )


def _module_has_failures(module: str, test_ids: list[str], runs_sorted: list[dict]) -> bool:
    if not runs_sorted:
        return False
    latest_tests = runs_sorted[0].get("tests", {})
    for test_id in test_ids:
        mod, _ = _parse_test_id(test_id)
        if mod == module and latest_tests.get(test_id) in {"failed", "error"}:
            return True
    return False


def _matrix_sort_key(test_id: str, runs_sorted: list[dict], all_test_ids: list[str]) -> tuple:
    module, name = _parse_test_id(test_id)
    latest = (
        runs_sorted[0].get("tests", {}).get(test_id, "not-run")
        if runs_sorted
        else "not-run"
    )
    fail_rank = 0 if latest in {"failed", "error"} else 1
    mod_fail = 0 if _module_has_failures(module, all_test_ids, runs_sorted) else 1
    flaky_rank = 0 if _is_flaky(test_id, runs_sorted) else 1
    return (mod_fail, module, fail_rank, flaky_rank, name)


def _pass_rate(summary: dict) -> int:
    total = summary.get("total", 0)
    if not total:
        return 0
    return round(100 * summary.get("passed", 0) / total)


def _quality_history_chart(runs_sorted: list[dict]) -> str:
    if not runs_sorted:
        return "<p class='panel-note'>Quality history appears after the first CI run.</p>"

    runs_chrono = list(reversed(runs_sorted))
    count = len(runs_chrono)
    width = 960
    height = 200 if count <= 4 else min(260, 170 + count * 6)
    margin_left, margin_right, margin_top, margin_bottom = 48, 24, 18, 52
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    bar_band = 36 if any(
        run["summary"]["failed"] + run["summary"]["error"] for run in runs_chrono
    ) else 0
    line_h = plot_h - bar_band - (8 if bar_band else 0)

    rates = [_pass_rate(run["summary"]) for run in runs_chrono]
    issues = [
        run["summary"]["failed"] + run["summary"]["error"] for run in runs_chrono
    ]
    max_issues = max(max(issues), 1)

    cluster_w = plot_w if count > 6 else min(plot_w, max(count * 64, 96))

    def x_at(index: int) -> float:
        if count == 1:
            return margin_left + plot_w / 2
        start = margin_left + (plot_w - cluster_w) / 2
        return start + (index / (count - 1)) * cluster_w

    def y_rate(rate: float) -> float:
        return margin_top + line_h - (rate / 100.0) * line_h

    def bar_height(issue_count: int) -> float:
        if not bar_band:
            return 0.0
        return (issue_count / max_issues) * (bar_band - 8)

    parts = [
        "<figure class='quality-chart'>",
        f"<svg class='quality-chart-svg' viewBox='0 0 {width} {height}' role='img' "
        f"aria-label='Validation quality history across {count} runs'>",
    ]

    for tick in (0, 50, 100):
        y = y_rate(tick)
        parts.append(
            f"<line class='chart-grid' x1='{margin_left}' y1='{y:.1f}' "
            f"x2='{width - margin_right}' y2='{y:.1f}' />"
        )
        parts.append(
            f"<text class='chart-axis-label chart-axis-left' x='{margin_left - 10}' "
            f"y='{y + 4:.1f}' text-anchor='end'>{tick}%</text>"
        )

    if bar_band:
        bar_top = margin_top + line_h + 10
        parts.append(
            f"<text class='chart-axis-label chart-axis-left' x='{margin_left - 10}' "
            f"y='{bar_top + bar_band - 6:.1f}' text-anchor='end'>0</text>"
        )
        parts.append(
            f"<text class='chart-axis-label chart-axis-left' x='{margin_left - 10}' "
            f"y='{bar_top + 10:.1f}' text-anchor='end'>{max_issues}</text>"
        )
        parts.append(
            f"<text class='chart-axis-title' x='{margin_left - 10}' "
            f"y='{bar_top + bar_band / 2:.1f}' text-anchor='end' "
            f"transform='rotate(-90 {margin_left - 10} {bar_top + bar_band / 2:.1f})'>"
            f"Open issues</text>"
        )

    area_points = [f"{margin_left},{y_rate(0)}"]
    for index, rate in enumerate(rates):
        area_points.append(f"{x_at(index):.1f},{y_rate(rate):.1f}")
    area_points.append(f"{x_at(count - 1):.1f},{y_rate(0)}")
    parts.append(f"<polygon class='chart-area' points='{' '.join(area_points)}' />")

    line_points = " ".join(
        f"{x_at(index):.1f},{y_rate(rate):.1f}" for index, rate in enumerate(rates)
    )
    parts.append(f"<polyline class='chart-line' points='{line_points}' />")

    bar_width = min(28, max(10, plot_w / max(count * 1.8, 1)))
    for index, run in enumerate(runs_chrono):
        x = x_at(index)
        rate = rates[index]
        issue_count = issues[index]
        label = f"#{run['run_number']}.{run['run_attempt']}"
        short_ts = run["timestamp"].split(" ", 1)[0]
        tooltip = (
            f"{label} · {rate}% pass · {issue_count} open issues · {run['timestamp']} UTC"
        )
        report_path = html.escape(run["report_path"])

        if bar_band and issue_count:
            bar_h = bar_height(issue_count)
            bar_y = margin_top + line_h + 10 + (bar_band - 8) - bar_h
            parts.append(
                f"<a href='{report_path}' class='chart-bar-link'>"
                f"<rect class='chart-bar' x='{x - bar_width / 2:.1f}' y='{bar_y:.1f}' "
                f"width='{bar_width:.1f}' height='{bar_h:.1f}' rx='3'>"
                f"<title>{html.escape(tooltip)}</title></rect></a>"
            )

        point_class = "chart-point is-failing" if issue_count else "chart-point"
        parts.append(
            f"<a href='{report_path}' class='chart-point-link'>"
            f"<circle class='{point_class}' cx='{x:.1f}' cy='{y_rate(rate):.1f}' r='5.5'>"
            f"<title>{html.escape(tooltip)}</title></circle></a>"
        )
        parts.append(
            f"<text class='chart-x-label' x='{x:.1f}' y='{height - margin_bottom + 18}' "
            f"text-anchor='middle'>{html.escape(label)}</text>"
        )
        parts.append(
            f"<text class='chart-x-sub' x='{x:.1f}' y='{height - margin_bottom + 32}' "
            f"text-anchor='middle'>{html.escape(short_ts)}</text>"
        )

    parts.append(
        f"<text class='chart-axis-title' x='{margin_left - 8}' y='{margin_top + line_h / 2:.1f}' "
        f"text-anchor='middle' transform='rotate(-90 {margin_left - 8} {margin_top + line_h / 2:.1f})'>"
        f"Pass %</text>"
    )
    parts.append("</svg>")
    parts.append(
        "<figcaption class='chart-legend'>"
        "<span><span class='chart-key chart-key-line'></span> Pass rate (%)</span>"
        "<span><span class='chart-key chart-key-bar'></span> Open issues (failed + error)</span>"
        "<span class='chart-legend-note'>Oldest run left · newest right · click a point or bar for the run report</span>"
        "</figcaption></figure>"
    )
    return "".join(parts)


def _pytest_node(test_id: str) -> str:
    module, name = _parse_test_id(test_id)
    if module:
        return f"pytest {module.replace('.', '/')}.py::{name}"
    return f"pytest {test_id}"


def _test_anchor(test_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", test_id).strip("-")
    return f"test-{slug}"


def _status_sort_rank(status: str) -> int:
    return {
        "failed": 0,
        "error": 1,
        "skipped": 2,
        "passed": 3,
        "not-run": 4,
    }.get(status, 5)


def _sort_header(label: str, key: str, sort_type: str = "string", default: str = "") -> str:
    default_attr = f" data-sort-default='{default}'" if default else ""
    return (
        f"<th><button type='button' class='sort-btn' "
        f"data-sort-key='{html.escape(key)}' data-sort-type='{html.escape(sort_type)}'{default_attr}>"
        f"{html.escape(label)}<span class='sort-indicator' aria-hidden='true'></span></button></th>"
    )


def _copy_attr(text: str) -> str:
    return html.escape(text, quote=True).replace("\n", "&#10;")


def _pages_base_url(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}"


def _report_page_url(run_meta: dict, anchor: str = "") -> str:
    base = _pages_base_url(run_meta.get("repo", "starsimhub/tbsim_comps"))
    path = run_meta.get("report_path", "").lstrip("/")
    url = f"{base}/{path}" if path else base
    if anchor:
        url += f"#{anchor}"
    return url


def _bug_for_test(test_id: str) -> dict | None:
    _, name = _parse_test_id(test_id)
    return _BUG_BY_TEST.get(name)


def _tbsim_issue_url(
    test_id: str,
    *,
    pytest_cmd: str,
    run_meta: dict,
    detail: str = "",
    anchor: str = "",
) -> str:
    bug = _bug_for_test(test_id)
    _, name = _parse_test_id(test_id)
    if bug:
        title = f"{bug['id']}: {bug['title']}"
    else:
        title = f"Validation failure: {name or test_id}"

    lines = ["## Summary", ""]
    if bug:
        lines.extend(
            [
                f"Tracked by **{bug['id']}** in the tbsim_comps validation harness.",
                "",
                "### Symptom",
                bug["symptom"],
                "",
                "### Expected",
                bug["expected"],
                "",
                "### Repro",
                "```python",
                bug["repro"],
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"Failing validation test: `{test_id}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Harness repro",
            "",
            "```bash",
            pytest_cmd,
            "```",
            "",
            f"- **Run:** {run_meta.get('run_url', '')}",
            f"- **Recorded:** {run_meta.get('timestamp', '')} UTC",
            f"- **Report:** {_report_page_url(run_meta, anchor)}",
        ]
    )
    if detail.strip():
        lines.extend(
            [
                "",
                "## Traceback",
                "",
                "```",
                detail.strip()[:4000],
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "---",
            f"Filed from the [tbsim_comps validation registry]({_pages_base_url(run_meta.get('repo', 'starsimhub/tbsim_comps'))}/).",
            "",
            f"<!-- tbsim-comps-test:{test_id} -->",
            "",
            "After filing, return to the validation report and click **Link issue** with the new GitHub issue number.",
        ]
    )

    params = urlencode({"title": title, "body": "\n".join(lines)}, quote_via=quote)
    return f"{TBSIM_NEW_ISSUE_URL}?{params}"


def _load_issue_links() -> dict[str, dict]:
    path = _REPO_ROOT / "findings" / "issue_links.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("links", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _parse_github_issue_ref(value: str | int) -> tuple[int, str] | None:
    if isinstance(value, int):
        return value, f"{TBSIM_ISSUES_URL}/{value}"
    text = str(value).strip()
    match = re.search(r"(?:issues/(\d+)|#(\d+)|^(\d+)$)", text)
    if not match:
        return None
    number = int(match.group(1) or match.group(2) or match.group(3))
    return number, f"{TBSIM_ISSUES_URL}/{number}"


def _issue_link_for_test(test_id: str) -> dict | None:
    links = _load_issue_links()
    if test_id in links:
        entry = links[test_id]
        parsed = _parse_github_issue_ref(entry.get("issue", ""))
        if parsed:
            number, url = parsed
            bug = _bug_for_test(test_id)
            return {
                "issue": number,
                "url": url,
                "tbug_id": entry.get("tbug_id") or (bug["id"] if bug else ""),
            }

    bug = _bug_for_test(test_id)
    if bug and bug.get("github_issue"):
        parsed = _parse_github_issue_ref(bug["github_issue"])
        if parsed:
            number, url = parsed
            return {"issue": number, "url": url, "tbug_id": bug["id"]}
    return None


def _render_issue_actions_inner(
    linked: dict | None,
    *,
    file_url: str,
    tbug_id: str,
) -> str:
    parts: list[str] = []
    if linked:
        parts.append(
            f"<a class='link-btn issue-linked' href='{html.escape(linked['url'])}' "
            f"target='_blank' rel='noopener' title='View upstream tbsim issue'>"
            f"tbsim #{linked['issue']}</a>"
        )
        tag = linked.get("tbug_id") or tbug_id
        if tag:
            parts.append(f"<span class='issue-tag'>{html.escape(tag)}</span>")
        link_label = "Edit link"
    else:
        label = f"File {tbug_id}" if tbug_id else "File tbsim bug"
        parts.append(
            f"<a class='link-btn' href='{html.escape(file_url)}' target='_blank' rel='noopener' "
            f"title='Open pre-filled issue on {html.escape(TBSIM_REPO)}'>"
            f"{html.escape(label)}</a>"
        )
        link_label = "Link issue"
    parts.append(
        f"<button type='button' class='mini-btn' data-link-tbsim-issue "
        f"title='Attach the GitHub issue number after filing'>{link_label}</button>"
    )
    return "".join(parts)


def _tbsim_issue_actions(
    test_id: str,
    *,
    pytest_cmd: str,
    run_meta: dict,
    detail: str = "",
    anchor: str = "",
) -> str:
    bug = _bug_for_test(test_id)
    tbug_id = bug["id"] if bug else ""
    linked = _issue_link_for_test(test_id)
    file_url = _tbsim_issue_url(
        test_id,
        pytest_cmd=pytest_cmd,
        run_meta=run_meta,
        detail=detail,
        anchor=anchor,
    )
    inner = _render_issue_actions_inner(linked, file_url=file_url, tbug_id=tbug_id)
    return (
        f"<span class='tbsim-issue-actions' data-tbsim-issue-actions "
        f"data-test-id='{html.escape(test_id, quote=True)}' "
        f"data-tbug-id='{html.escape(tbug_id, quote=True)}' "
        f"data-file-url='{html.escape(file_url, quote=True)}'>{inner}</span>"
    )


def _issue_links_script() -> str:
    enriched: dict[str, dict] = {}
    for test_id, entry in _load_issue_links().items():
        parsed = _parse_github_issue_ref(entry.get("issue", ""))
        if not parsed:
            continue
        number, url = parsed
        bug = _bug_for_test(test_id)
        enriched[test_id] = {
            "issue": number,
            "url": url,
            "tbug_id": entry.get("tbug_id") or (bug["id"] if bug else ""),
            "linked_at": entry.get("linked_at", ""),
        }
    payload = json.dumps({"links": enriched})
    return f'<script type="application/json" id="tbsim-issue-links">{payload}</script>'


def _build_action_queue(runs_sorted: list[dict], sorted_test_ids: list[str]) -> tuple[str, str]:
    if not runs_sorted:
        return "", ""
    latest = runs_sorted[0]
    report_path = latest["report_path"]
    run_url = latest["run_url"]
    failing_cmds: list[str] = []
    items: list[str] = []
    for test_id in sorted_test_ids:
        status = latest.get("tests", {}).get(test_id)
        if status not in {"failed", "error"}:
            continue
        module, name = _parse_test_id(test_id)
        pytest_cmd = _pytest_node(test_id)
        failing_cmds.append(pytest_cmd)
        anchor = _test_anchor(test_id)
        items.append(
            "<li class='action-item'>"
            f"<div class='action-item-main'>"
            f"<a class='action-item-title' href='{html.escape(report_path)}#{anchor}'>"
            f"{html.escape(name or test_id)}</a>"
            f"<span class='action-item-module'>{html.escape(module)}</span>"
            f"</div>"
            f"<div class='action-item-controls'>"
            f"{_status_badge(status)}"
            f"{_tbsim_issue_actions(test_id, pytest_cmd=pytest_cmd, run_meta=latest, anchor=anchor)}"
            f"<button type='button' class='mini-btn' data-copy-text='{_copy_attr(pytest_cmd)}' "
            f"title='Copy pytest command'>Copy cmd</button>"
            f"</div>"
            "</li>"
        )
    queue_html = (
        "<ul class='action-list'>"
        + "".join(items)
        + "</ul>"
        if items
        else "<p class='panel-note'>No failing tests in the latest run. Validation is clear.</p>"
    )
    copy_all = "\n".join(failing_cmds)
    return queue_html, copy_all


_REPORT_THEME_SCRIPT = """
(function () {
  var KEY = 'tbsim-registry-theme';
  var root = document.documentElement;
  function resolve(mode) {
    if (mode === 'dark') return 'dark';
    if (mode === 'light') return 'light';
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  var mode = localStorage.getItem(KEY) || 'system';
  root.setAttribute('data-theme-mode', mode);
  root.setAttribute('data-theme', resolve(mode));
})();
"""


_THEME_SWITCHER = """
<div class="theme-switch" role="group" aria-label="Color theme">
  <button type="button" class="theme-btn" data-theme-choice="light" aria-pressed="false" title="Light theme">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>
    <span>Light</span>
  </button>
  <button type="button" class="theme-btn" data-theme-choice="dark" aria-pressed="false" title="Dark theme">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 14.5A8.5 8.5 0 1 1 9.5 3a6.5 6.5 0 1 0 11.5 11.5z"/></svg>
    <span>Dark</span>
  </button>
  <button type="button" class="theme-btn" data-theme-choice="system" aria-pressed="false" title="System theme">
    <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/></svg>
    <span>System</span>
  </button>
</div>
"""


_REPORT_JS = """
(function () {
  var KEY = 'tbsim-registry-theme';
  var root = document.documentElement;

  function resolve(mode) {
    if (mode === 'dark') return 'dark';
    if (mode === 'light') return 'light';
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyMode(mode) {
    root.setAttribute('data-theme-mode', mode);
    root.setAttribute('data-theme', resolve(mode));
    localStorage.setItem(KEY, mode);
    document.querySelectorAll('[data-theme-choice]').forEach(function (btn) {
      var active = btn.getAttribute('data-theme-choice') === mode;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  document.querySelectorAll('[data-theme-choice]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyMode(btn.getAttribute('data-theme-choice'));
    });
  });

  var initial = root.getAttribute('data-theme-mode') || localStorage.getItem(KEY) || 'system';
  applyMode(initial);

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    if ((root.getAttribute('data-theme-mode') || 'system') === 'system') {
      root.setAttribute('data-theme', resolve('system'));
    }
  });

  function copyText(text, trigger) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(function () {
      if (!trigger) return;
      var prev = trigger.textContent;
      trigger.textContent = 'Copied';
      trigger.classList.add('is-copied');
      setTimeout(function () {
        trigger.textContent = prev;
        trigger.classList.remove('is-copied');
      }, 1400);
    });
  }

  document.querySelectorAll('[data-copy-text]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      copyText(btn.getAttribute('data-copy-text') || '', btn);
    });
  });

  function rowValue(row, key, type) {
    var raw = row.getAttribute(key) || '';
    if (type === 'number') return parseFloat(raw) || 0;
    return raw.toLowerCase();
  }

  function updateSortIndicators(table, activeBtn, dir) {
    table.querySelectorAll('.sort-btn').forEach(function (btn) {
      btn.classList.remove('is-active', 'is-asc', 'is-desc');
      btn.removeAttribute('data-dir');
    });
    if (activeBtn) {
      activeBtn.classList.add('is-active', dir === 'asc' ? 'is-asc' : 'is-desc');
      activeBtn.setAttribute('data-dir', dir);
    }
  }

  function sortDataTable(table) {
    var tbody = table.tBodies[0];
    if (!tbody) return;
    var rowSelector = table.getAttribute('data-row-selector') || '.data-row';
    var activeBtn = table.querySelector('.sort-btn.is-active');
    if (!activeBtn) return;
    var key = activeBtn.getAttribute('data-sort-key');
    var type = activeBtn.getAttribute('data-sort-type') || 'string';
    var dir = activeBtn.getAttribute('data-dir') || 'asc';
    var rows = Array.prototype.slice.call(tbody.querySelectorAll(rowSelector));
    rows.sort(function (a, b) {
      var av = rowValue(a, key, type);
      var bv = rowValue(b, key, type);
      if (av < bv) return dir === 'asc' ? -1 : 1;
      if (av > bv) return dir === 'asc' ? 1 : -1;
      return 0;
    });
    rows.forEach(function (row) { tbody.appendChild(row); });
    if (table.id === 'matrix-table') {
      table.classList.add('is-sorted');
      tbody.querySelectorAll('.group-row').forEach(function (row) { row.hidden = true; });
    }
  }

  function filterDataTable(table) {
    var tbody = table.tBodies[0];
    if (!tbody) return;
    var rowSelector = table.getAttribute('data-row-selector') || '.data-row';
    var searchInput = document.getElementById(table.getAttribute('data-search-input') || '');
    var statusSelect = document.getElementById(table.getAttribute('data-status-input') || '');
    var matrixFilter = table.getAttribute('data-matrix-filter-group');
    var testFilterGroup = table.getAttribute('data-test-filter-group');
    var moduleSelect = document.getElementById(table.getAttribute('data-module-input') || '');
    var query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    var status = statusSelect ? statusSelect.value : 'all';
    var module = moduleSelect ? moduleSelect.value : 'all';
    var matrixMode = 'all';
    var testMode = 'all';
    if (matrixFilter) {
      var matrixScope = table.closest('.panel') || document;
      matrixScope.querySelectorAll('[data-matrix-filter]').forEach(function (btn) {
        if (btn.classList.contains('is-active')) {
          matrixMode = btn.getAttribute('data-matrix-filter') || 'all';
        }
      });
    }
    if (testFilterGroup) {
      var scope = table.closest('.panel') || document;
      scope.querySelectorAll('[data-test-filter]').forEach(function (btn) {
        if (btn.classList.contains('is-active')) {
          testMode = btn.getAttribute('data-test-filter') || 'all';
        }
      });
    }
    var visibleCount = 0;
    Array.prototype.forEach.call(tbody.querySelectorAll(rowSelector), function (row) {
      var blob = (row.getAttribute('data-search') || row.textContent || '').toLowerCase();
      var rowStatus = row.getAttribute('data-filter-status') || row.getAttribute('data-latest-status') || '';
      var rowModule = row.getAttribute('data-filter-module') || '';
      var flaky = row.getAttribute('data-flaky') === 'true';
      var slow = row.getAttribute('data-slow') === 'true';
      var matchesQuery = !query || blob.indexOf(query) !== -1;
      var matchesStatus =
        status === 'all' ||
        rowStatus === status ||
        (status === 'failing' && (rowStatus === 'failed' || rowStatus === 'error'));
      var matchesModule = module === 'all' || rowModule === module;
      var matchesMatrix =
        !matrixFilter ||
        matrixMode === 'all' ||
        (matrixMode === 'failing' && (rowStatus === 'failed' || rowStatus === 'error')) ||
        (matrixMode === 'flaky' && flaky);
      var matchesTest =
        !testFilterGroup ||
        testMode === 'all' ||
        (testMode === 'failing' && (rowStatus === 'failed' || rowStatus === 'error')) ||
        (testMode === 'slow' && slow);
      var visible = matchesQuery && matchesStatus && matchesModule && matchesMatrix && matchesTest;
      row.hidden = !visible;
      if (visible) visibleCount += 1;
    });
    if (table.id === 'matrix-table') {
      tbody.querySelectorAll('.group-row').forEach(function (groupRow) {
        var moduleName = groupRow.getAttribute('data-module');
        if (!moduleName || table.classList.contains('is-sorted')) {
          groupRow.hidden = true;
          return;
        }
        var moduleRows = tbody.querySelectorAll('.matrix-row[data-module="' + moduleName + '"]');
        groupRow.hidden = !Array.prototype.some.call(moduleRows, function (row) { return !row.hidden; });
      });
    }
    var countNode = document.getElementById(table.getAttribute('data-count-target') || '');
    if (countNode) {
      countNode.textContent = visibleCount + ' shown';
    }
  }

  function initDataTable(table) {
    var defaultBtn = table.querySelector('.sort-btn[data-sort-default]');
    table.querySelectorAll('.sort-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var current = table.querySelector('.sort-btn.is-active');
        var dir = 'asc';
        if (current === btn) {
          dir = btn.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
        } else if (btn.getAttribute('data-sort-default')) {
          dir = btn.getAttribute('data-sort-default');
        }
        updateSortIndicators(table, btn, dir);
        sortDataTable(table);
        filterDataTable(table);
      });
    });
    if (defaultBtn) {
      updateSortIndicators(table, defaultBtn, defaultBtn.getAttribute('data-sort-default') || 'asc');
      sortDataTable(table);
    }

    var searchInput = document.getElementById(table.getAttribute('data-search-input') || '');
    if (searchInput) {
      searchInput.addEventListener('input', function () { filterDataTable(table); });
    }
    var statusSelect = document.getElementById(table.getAttribute('data-status-input') || '');
    if (statusSelect) {
      statusSelect.addEventListener('change', function () { filterDataTable(table); });
    }
    var moduleSelect = document.getElementById(table.getAttribute('data-module-input') || '');
    if (moduleSelect) {
      moduleSelect.addEventListener('change', function () { filterDataTable(table); });
    }
    filterDataTable(table);
  }

  document.querySelectorAll('[data-table]').forEach(initDataTable);

  document.querySelectorAll('[data-matrix-filter]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('[data-matrix-filter]').forEach(function (other) {
        other.classList.remove('is-active');
      });
      btn.classList.add('is-active');
      var matrixTable = document.getElementById('matrix-table');
      if (matrixTable) filterDataTable(matrixTable);
    });
  });

  document.querySelectorAll('[data-test-filter]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('[data-test-filter]').forEach(function (other) {
        other.classList.remove('is-active');
      });
      btn.classList.add('is-active');
      var testsTable = document.getElementById('run-tests-table');
      if (testsTable) filterDataTable(testsTable);
    });
  });

  document.querySelectorAll('[data-copy-visible-cmds]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var selector = btn.getAttribute('data-copy-visible-cmds') || '#run-tests-table';
      var table = document.querySelector(selector);
      if (!table || !table.tBodies[0]) return;
      var cmds = [];
      Array.prototype.forEach.call(
        table.tBodies[0].querySelectorAll('.test-row:not([hidden])'),
        function (row) {
          var cmd = row.getAttribute('data-copy-cmd');
          if (cmd) cmds.push(cmd);
        }
      );
      copyText(cmds.join('\\n'), btn);
    });
  });

  document.querySelectorAll('[data-jump]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var target = document.querySelector(btn.getAttribute('data-jump') || '');
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  var matrixSortMode = document.getElementById('matrix-sort-mode');
  if (matrixSortMode) {
    matrixSortMode.addEventListener('change', function () {
      var table = document.getElementById('matrix-table');
      if (!table) return;
      var key = matrixSortMode.value;
      var type = key === 'data-sort-status' ? 'number' : 'string';
      var dir = key === 'data-sort-status' ? 'asc' : 'asc';
      var btn = table.querySelector('.sort-btn[data-sort-key="' + key + '"]');
      if (!btn) {
        btn = document.createElement('button');
        btn.className = 'sort-btn';
        btn.setAttribute('data-sort-key', key);
        btn.setAttribute('data-sort-type', type);
        btn.style.display = 'none';
        table.querySelector('thead tr').appendChild(btn);
      }
      updateSortIndicators(table, btn, dir);
      sortDataTable(table);
      filterDataTable(table);
    });
  }

  var ISSUE_LINKS_KEY = 'tbsim-issue-links';
  var TBSIM_ISSUES_BASE = 'https://github.com/starsimhub/tbsim/issues';

  function loadEmbeddedIssueLinks() {
    var node = document.getElementById('tbsim-issue-links');
    if (!node) return {};
    try {
      return JSON.parse(node.textContent || '{}').links || {};
    } catch (err) {
      return {};
    }
  }

  function loadStoredIssueLinks() {
    try {
      return JSON.parse(localStorage.getItem(ISSUE_LINKS_KEY) || '{}');
    } catch (err) {
      return {};
    }
  }

  function saveStoredIssueLinks(links) {
    localStorage.setItem(ISSUE_LINKS_KEY, JSON.stringify(links));
  }

  function parseIssueInput(raw) {
    if (!raw) return null;
    var text = String(raw).trim();
    var match = text.match(/(?:issues\\/(\\d+)|#(\\d+)|^(\\d+))$/);
    if (!match) return null;
    var num = parseInt(match[1] || match[2] || match[3], 10);
    return { issue: num, url: TBSIM_ISSUES_BASE + '/' + num };
  }

  function getIssueLinkForTest(testId) {
    var stored = loadStoredIssueLinks();
    if (stored[testId]) return stored[testId];
    var embedded = loadEmbeddedIssueLinks();
    return embedded[testId] || null;
  }

  function renderIssueActions(container) {
    var testId = container.getAttribute('data-test-id');
    var tbugId = container.getAttribute('data-tbug-id') || '';
    var fileUrl = container.getAttribute('data-file-url') || '';
    var linked = getIssueLinkForTest(testId);
    container.textContent = '';

    var fileLink = document.createElement('a');
    fileLink.className = 'link-btn';
    fileLink.target = '_blank';
    fileLink.rel = 'noopener';
    if (linked && linked.issue) {
      fileLink.classList.add('issue-linked');
      fileLink.href = linked.url || (TBSIM_ISSUES_BASE + '/' + linked.issue);
      fileLink.textContent = 'tbsim #' + linked.issue;
      fileLink.title = 'View upstream tbsim issue';
      container.appendChild(fileLink);
      var tag = linked.tbug_id || tbugId;
      if (tag) {
        var tagNode = document.createElement('span');
        tagNode.className = 'issue-tag';
        tagNode.textContent = tag;
        container.appendChild(tagNode);
      }
    } else {
      fileLink.href = fileUrl;
      fileLink.textContent = tbugId ? ('File ' + tbugId) : 'File tbsim bug';
      fileLink.title = 'Open pre-filled issue on starsimhub/tbsim';
      container.appendChild(fileLink);
    }

    var linkBtn = document.createElement('button');
    linkBtn.type = 'button';
    linkBtn.className = 'mini-btn';
    linkBtn.setAttribute('data-link-tbsim-issue', '');
    linkBtn.setAttribute('data-test-id', testId);
    linkBtn.textContent = (linked && linked.issue) ? 'Edit link' : 'Link issue';
    linkBtn.title = 'Attach the GitHub issue number after filing';
    container.appendChild(linkBtn);
  }

  function refreshIssueActions(testId) {
    document.querySelectorAll('[data-tbsim-issue-actions]').forEach(function (node) {
      if (!testId || node.getAttribute('data-test-id') === testId) {
        renderIssueActions(node);
      }
    });
  }

  document.querySelectorAll('[data-tbsim-issue-actions]').forEach(renderIssueActions);

  document.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-link-tbsim-issue]');
    if (!btn) return;
    var container = btn.closest('[data-tbsim-issue-actions]');
    var testId = btn.getAttribute('data-test-id') || (container && container.getAttribute('data-test-id'));
    if (!testId) return;

    var current = getIssueLinkForTest(testId);
    var input = window.prompt(
      'Paste the tbsim GitHub issue number or URL after filing (leave blank to remove):',
      current ? String(current.issue) : ''
    );
    if (input === null) return;

    if (!String(input).trim()) {
      if (!current) return;
      if (!window.confirm('Remove the linked tbsim issue for this failure?')) return;
      var cleared = loadStoredIssueLinks();
      delete cleared[testId];
      saveStoredIssueLinks(cleared);
      refreshIssueActions(testId);
      return;
    }

    var parsed = parseIssueInput(input);
    if (!parsed) {
      window.alert('Could not parse issue number. Use #425 or the full GitHub URL.');
      return;
    }

    var tbugId = (current && current.tbug_id) || (container && container.getAttribute('data-tbug-id')) || '';
    if (tbugId) parsed.tbug_id = tbugId;

    var stored = loadStoredIssueLinks();
    stored[testId] = parsed;
    saveStoredIssueLinks(stored);
    refreshIssueActions(testId);

    var persistArg = parsed.tbug_id || testId;
    var persistCmd = 'python scripts/link_tbsim_issue.py ' + persistArg + ' ' + parsed.issue;
    if (window.confirm('Linked tbsim #' + parsed.issue + '. Copy the persist command for the team registry?')) {
      copyText(persistCmd);
    }
  });
})();
"""


_REPORT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

[data-theme="light"] {
  color-scheme: light;
  --bg: #e4e4e2;
  --bg-accent: rgba(184, 115, 51, 0.06);
  --bg-warm: rgba(212, 168, 50, 0.06);
  --surface: #f2f2f0;
  --surface-muted: #eaeae8;
  --surface-raised: #fafaf8;
  --border: #c8c8c4;
  --border-strong: #b0b0ac;
  --text: #121110;
  --muted: #6e6e6a;
  --link: #a8622a;
  --link-hover: #8a4f1f;
  --accent: #b87333;
  --cta: #4a78a8;
  --pass: #2f8f62;
  --pass-bg: rgba(47, 143, 98, 0.12);
  --pass-border: rgba(47, 143, 98, 0.34);
  --fail: #c44a3a;
  --fail-bg: rgba(196, 74, 58, 0.1);
  --fail-border: rgba(196, 74, 58, 0.32);
  --warn: #d4a832;
  --warn-bg: rgba(212, 168, 50, 0.14);
  --warn-border: rgba(212, 168, 50, 0.36);
  --skip: #7a7a76;
  --skip-bg: rgba(122, 122, 118, 0.12);
  --skip-border: rgba(122, 122, 118, 0.28);
  --empty: #d8d8d4;
  --shadow: 0 14px 40px rgba(0, 0, 0, 0.08);
  --shadow-soft: 0 4px 18px rgba(0, 0, 0, 0.05);
  --sidebar-bg: #dcdcd9;
  --sparkline: #b87333;
  --sparkline-fill: rgba(184, 115, 51, 0.12);
  --hero-glow: rgba(184, 115, 51, 0.1);
  --button-fg: #ffffff;
  --row-hover: rgba(0, 0, 0, 0.04);
  --chip-bg: #fafaf8;
  --chip-active-bg: #b87333;
  --chip-active-fg: #ffffff;
}

[data-theme="dark"] {
  color-scheme: dark;
  --bg: #040404;
  --bg-accent: rgba(212, 132, 74, 0.12);
  --bg-warm: rgba(240, 112, 104, 0.06);
  --surface: #111110;
  --surface-muted: #181817;
  --surface-raised: #222221;
  --border: rgba(255, 255, 255, 0.08);
  --border-strong: rgba(212, 132, 74, 0.22);
  --text: #f4f2ee;
  --muted: #949490;
  --link: #e89858;
  --link-hover: #ffc088;
  --accent: #d4844a;
  --cta: #6898c8;
  --pass: #62c992;
  --pass-bg: rgba(98, 201, 146, 0.12);
  --pass-border: rgba(98, 201, 146, 0.32);
  --fail: #f07068;
  --fail-bg: rgba(240, 112, 104, 0.1);
  --fail-border: rgba(240, 112, 104, 0.28);
  --warn: #e8b840;
  --warn-bg: rgba(232, 184, 64, 0.1);
  --warn-border: rgba(232, 184, 64, 0.28);
  --skip: #707070;
  --skip-bg: rgba(112, 112, 112, 0.12);
  --skip-border: rgba(112, 112, 112, 0.24);
  --empty: #2a2a28;
  --shadow: 0 24px 64px rgba(0, 0, 0, 0.55);
  --shadow-soft: 0 8px 24px rgba(0, 0, 0, 0.35);
  --shadow-glow: 0 0 48px rgba(212, 132, 74, 0.07);
  --sidebar-bg: #070707;
  --sparkline: #d4844a;
  --sparkline-fill: rgba(212, 132, 74, 0.12);
  --hero-glow: rgba(212, 132, 74, 0.14);
  --button-fg: #0a0a09;
  --row-hover: rgba(212, 132, 74, 0.06);
  --chip-bg: rgba(255, 255, 255, 0.04);
  --chip-active-bg: #d4844a;
  --chip-active-fg: #0a0a09;
  --panel-line: rgba(212, 132, 74, 0.5);
}

[data-theme="dark"] body {
  background:
    radial-gradient(ellipse 900px 520px at 92% -8%, rgba(212, 132, 74, 0.1), transparent 62%),
    radial-gradient(ellipse 680px 420px at 6% 105%, rgba(212, 132, 74, 0.05), transparent 58%),
    radial-gradient(ellipse 480px 280px at 50% 42%, rgba(255, 255, 255, 0.018), transparent 72%),
    #040404;
}

[data-theme="dark"] .sidebar {
  background:
    linear-gradient(180deg, rgba(212, 132, 74, 0.05) 0%, transparent 32%),
    linear-gradient(90deg, #070707, #0a0a09);
  box-shadow: inset -1px 0 0 rgba(212, 132, 74, 0.07);
}
[data-theme="dark"] .sidebar-nav a:hover {
  background: rgba(212, 132, 74, 0.09);
  border-color: rgba(212, 132, 74, 0.16);
  color: var(--text);
}
[data-theme="dark"] .brand-mark {
  background:
    radial-gradient(circle at 30% 30%, rgba(212, 132, 74, 0.55), transparent 55%),
    radial-gradient(circle at 70% 70%, rgba(240, 112, 104, 0.35), transparent 50%),
    var(--surface-raised);
  border-color: var(--border-strong);
  box-shadow: 0 0 28px rgba(212, 132, 74, 0.18);
}
[data-theme="dark"] .panel,
[data-theme="dark"] .card,
[data-theme="dark"] .stat,
[data-theme="dark"] .stamp,
[data-theme="dark"] .theme-switch,
[data-theme="dark"] .action-panel {
  background: linear-gradient(165deg, rgba(34, 34, 33, 0.96), rgba(17, 17, 16, 0.99));
  border-color: var(--border);
  box-shadow:
    var(--shadow-soft),
    var(--shadow-glow),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
[data-theme="dark"] .panel {
  position: relative;
  overflow: hidden;
}
[data-theme="dark"] .panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 18px;
  right: 18px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--panel-line), transparent);
  pointer-events: none;
}
[data-theme="dark"] .overview-ring::after {
  background: linear-gradient(165deg, #222221, #111110);
  box-shadow: inset 0 0 24px rgba(0, 0, 0, 0.45);
}
[data-theme="dark"] .kpi-cell {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--border);
}
[data-theme="dark"] .action-btn {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--border);
}
[data-theme="dark"] .action-btn:hover {
  border-color: var(--border-strong);
  color: var(--link-hover);
  background: rgba(212, 132, 74, 0.08);
}
[data-theme="dark"] .action-btn.primary {
  background: linear-gradient(180deg, #e09558 0%, #c87238 100%);
  border-color: rgba(255, 200, 150, 0.18);
  color: var(--button-fg);
  box-shadow:
    0 4px 22px rgba(212, 132, 74, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.14);
}
[data-theme="dark"] .action-btn.primary:hover {
  filter: brightness(1.07);
  color: var(--button-fg);
  box-shadow:
    0 8px 30px rgba(212, 132, 74, 0.42),
    inset 0 1px 0 rgba(255, 255, 255, 0.18);
}
[data-theme="dark"] .theme-btn.is-active {
  background: var(--accent);
  color: var(--chip-active-fg);
  box-shadow: 0 0 16px rgba(212, 132, 74, 0.28);
}
[data-theme="dark"] .mini-btn {
  color: var(--text);
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--border);
}
[data-theme="dark"] .mini-btn:hover {
  color: var(--chip-active-fg);
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: 0 0 14px rgba(212, 132, 74, 0.22);
}
[data-theme="dark"] .test-cell .test-module {
  color: var(--muted);
}
[data-theme="dark"] .test-cell .test-name {
  color: var(--text);
}
[data-theme="dark"] .test-cell .test-name:hover {
  color: var(--link-hover);
}
[data-theme="dark"] .test-row-fail {
  background: linear-gradient(90deg, rgba(240, 112, 104, 0.08), rgba(240, 112, 104, 0.03));
  box-shadow: inset 3px 0 0 var(--fail);
}
[data-theme="dark"] .link-btn {
  color: var(--link);
  font-weight: 600;
}
[data-theme="dark"] .link-btn:hover {
  color: var(--link-hover);
}
[data-theme="dark"] .dur-cell span {
  color: var(--text);
}
[data-theme="dark"] th {
  color: var(--muted);
  background: rgba(255, 255, 255, 0.025);
  border-bottom-color: var(--border-strong);
}
[data-theme="dark"] .filter-chip {
  color: var(--text);
  background: var(--chip-bg);
  border-color: var(--border);
}
[data-theme="dark"] .filter-chip.is-active {
  background: var(--chip-active-bg);
  color: var(--chip-active-fg);
  border-color: transparent;
  box-shadow: 0 0 18px rgba(212, 132, 74, 0.24);
}
[data-theme="dark"] .table-search,
[data-theme="dark"] .table-select,
[data-theme="dark"] .matrix-search {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: var(--border);
  color: var(--text);
}
[data-theme="dark"] .table-search:focus,
[data-theme="dark"] .matrix-search:focus {
  border-color: var(--border-strong);
  outline: 2px solid rgba(212, 132, 74, 0.25);
  outline-offset: 1px;
}
[data-theme="dark"] .table-search,
[data-theme="dark"] .matrix-search {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%23949490' stroke-width='2'%3E%3Ccircle cx='7' cy='7' r='5'/%3E%3Cpath d='M11 11l3 3'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: 12px center;
}
[data-theme="dark"] .panel-note,
[data-theme="dark"] .table-meta,
[data-theme="dark"] .subnav {
  color: var(--muted);
}
[data-theme="dark"] .issue-linked {
  color: var(--link-hover);
}
[data-theme="dark"] .badge-pass {
  box-shadow: 0 0 12px rgba(98, 201, 146, 0.12);
}
[data-theme="dark"] .badge-fail {
  box-shadow: 0 0 12px rgba(240, 112, 104, 0.12);
}
[data-theme="dark"] .chart-grid {
  stroke: rgba(255, 255, 255, 0.06);
}
[data-theme="dark"] .rich-report summary {
  background: rgba(255, 255, 255, 0.02);
}
[data-theme="dark"] pre {
  background: #0a0a09;
  border: 1px solid var(--border);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  margin: 0;
  color: var(--text);
  background: var(--bg);
  min-height: 100vh;
  font-size: 14px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
.app {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  min-height: 100vh;
}
.sidebar {
  position: sticky;
  top: 0;
  align-self: start;
  height: 100vh;
  padding: 28px 20px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 28px;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background:
    radial-gradient(circle at 30% 30%, var(--pass), transparent 55%),
    radial-gradient(circle at 70% 70%, var(--fail), transparent 50%),
    var(--surface-raised);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-soft);
}
.brand-copy strong {
  display: block;
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--accent);
}
.brand-copy span {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sidebar-nav a {
  display: block;
  padding: 10px 12px;
  border-radius: 10px;
  color: var(--muted);
  font-weight: 500;
  border: 1px solid transparent;
}
.sidebar-nav a:hover {
  color: var(--text);
  background: var(--surface);
  border-color: var(--border);
  text-decoration: none;
}
.sidebar-block {
  margin-top: auto;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}
.sidebar-block h3 {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 10px;
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-weight: 600;
}
.main { min-width: 0; padding: 28px 28px 72px; }
.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.eyebrow {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 8px;
}
h1 {
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: clamp(1.85rem, 3.8vw, 2.65rem);
  font-weight: 700;
  line-height: 1.08;
  letter-spacing: -0.035em;
  margin: 0;
  color: var(--accent);
}
h2 {
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--accent);
}
h3 {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  font-weight: 500;
  margin: 0 0 8px;
  color: var(--text);
}
.stamp {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 14px;
  padding: 14px 16px;
  min-width: 210px;
  text-align: right;
  box-shadow: var(--shadow-soft);
}
.stamp-label {
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 4px;
}
.stamp-value {
  font-size: 12px;
  margin: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.theme-switch {
  display: inline-flex;
  padding: 4px;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}
.theme-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 7px 10px;
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.theme-btn svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: round;
}
.theme-btn span { display: none; }
.theme-btn.is-active {
  background: var(--accent);
  color: var(--button-fg);
}
.theme-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
@media (min-width: 1100px) {
  .theme-btn span { display: inline; }
}
.hero-shell {
  display: none;
}
.overview-panel {
  padding: 16px 18px 14px;
  margin-top: 14px;
}
.overview-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
}
.overview-ring {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  position: relative;
  flex-shrink: 0;
}
.overview-ring::after {
  content: '';
  position: absolute;
  inset: 9px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--border);
}
.overview-ring-value {
  position: relative;
  z-index: 1;
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.05rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.overview-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.kpi-cell {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface-muted);
  min-width: 0;
}
.kpi-cell.fail { border-color: var(--fail-border); background: var(--fail-bg); }
.kpi-cell.warn { border-color: var(--warn-border); background: var(--warn-bg); }
.kpi-cell.pass { border-color: var(--pass-border); background: var(--pass-bg); }
.kpi-label {
  display: block;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 2px;
}
.kpi-value {
  display: block;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.kpi-note {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.quality-chart-svg {
  width: 100%;
  height: auto;
  display: block;
  max-height: 210px;
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 8px;
  font-size: 11px;
  color: var(--muted);
}
.hero-primary,
.hero-side {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow: var(--shadow);
  overflow: hidden;
  position: relative;
}
.hero-primary {
  padding: 24px;
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 22px;
  align-items: center;
}
.hero-primary::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 100% 0%, var(--hero-glow), transparent 42%);
  pointer-events: none;
}
.hero-side { padding: 20px; }
.hero-ring {
  width: 132px;
  height: 132px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  position: relative;
  z-index: 1;
}
.hero-ring::after {
  content: '';
  position: absolute;
  inset: 16px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--border);
}
.hero-ring-value {
  position: relative;
  z-index: 1;
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.65rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.hero-copy { position: relative; z-index: 1; }
.hero-title {
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.35rem;
  margin: 0 0 8px;
}
.hero-copy p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-muted);
  font-size: 12px;
  font-weight: 600;
}
.hero-chip.fail { color: var(--fail); border-color: var(--fail-border); background: var(--fail-bg); }
.hero-chip.warn { color: var(--warn); border-color: var(--warn-border); background: var(--warn-bg); }
.hero-chip.pass { color: var(--pass); border-color: var(--pass-border); background: var(--pass-bg); }
.quality-chart {
  margin: 0;
  padding: 0;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.test-cell { line-height: 1.35; }
.test-cell .test-module {
  display: block;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  color: var(--muted);
  margin-bottom: 2px;
}
.test-cell .test-name {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  color: var(--link);
  text-decoration: none;
}
.test-cell .test-name:hover { text-decoration: underline; }
.test-row-fail { background: var(--fail-bg); }
.test-row-fail:hover { background: color-mix(in srgb, var(--fail-bg) 80%, var(--row-hover)); }
.dur-cell { min-width: 88px; }
.dur-cell span {
  display: block;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.dur-bar {
  height: 4px;
  background: var(--empty);
  border-radius: 999px;
  overflow: hidden;
  margin-top: 4px;
}
.dur-bar span {
  display: block;
  height: 100%;
  background: var(--accent);
  border-radius: inherit;
}
.test-row-fail .dur-bar span { background: var(--fail); }
.action-stack {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.chart-grid {
  stroke: var(--border);
  stroke-width: 1;
  stroke-dasharray: 4 4;
}
.chart-area {
  fill: var(--sparkline-fill);
  stroke: none;
}
.chart-line {
  fill: none;
  stroke: var(--pass);
  stroke-width: 2.75;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.chart-bar {
  fill: var(--fail);
  opacity: 0.82;
  transition: opacity 0.15s ease;
}
.chart-bar-link:hover .chart-bar { opacity: 1; }
.chart-point {
  fill: var(--surface);
  stroke: var(--pass);
  stroke-width: 2.5;
  transition: r 0.15s ease;
}
.chart-point.is-failing {
  stroke: var(--fail);
  fill: var(--fail-bg);
}
.chart-point-link:hover .chart-point { r: 7; }
.chart-axis-label {
  fill: var(--muted);
  font-size: 11px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.chart-axis-title {
  fill: var(--muted);
  font-size: 10px;
  font-family: 'Plus Jakarta Sans', ui-sans-serif, sans-serif;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.chart-x-label {
  fill: var(--text);
  font-size: 11px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-weight: 600;
}
.chart-x-sub {
  fill: var(--muted);
  font-size: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.chart-key {
  width: 18px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}
.chart-key-line { background: var(--pass); }
.chart-key-bar { background: var(--fail); opacity: 0.82; }
.chart-legend-note {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted);
}
.stat {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 18px 18px 18px 20px;
  position: relative;
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}
.stat::before {
  content: '';
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 4px;
  border-radius: 0 3px 3px 0;
  background: var(--pass);
}
.stat::after {
  content: '';
  position: absolute;
  right: -18px;
  top: -18px;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--pass-bg);
  opacity: 0.65;
}
.stat.fail::before { background: var(--fail); }
.stat.fail::after { background: var(--fail-bg); }
.stat.warn::before { background: var(--warn); }
.stat.warn::after { background: var(--warn-bg); }
.stat-label {
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 8px;
}
.stat-value {
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: clamp(1.55rem, 2.5vw, 2rem);
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.03em;
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.stat-note { font-size: 12px; color: var(--muted); margin: 8px 0 0; }
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 18px;
  margin-top: 14px;
  box-shadow: var(--shadow-soft);
}
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
  margin-bottom: 12px;
}
.panel-note { font-size: 12px; color: var(--muted); margin: 0; }
.subnav { color: var(--muted); font-size: 13px; margin: 0 0 20px; }
.grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 18px;
  margin-top: 16px;
  box-shadow: var(--shadow-soft);
}
.grid .card p {
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.85rem;
  line-height: 1;
  margin: 8px 0 0;
  font-variant-numeric: tabular-nums;
}
.matrix-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.matrix-search {
  flex: 1 1 240px;
  max-width: 420px;
  padding: 10px 12px 10px 36px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface-muted) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%235a6b82' stroke-width='2'%3E%3Ccircle cx='7' cy='7' r='5'/%3E%3Cpath d='M11 11l3 3'/%3E%3C/svg%3E") 12px center no-repeat;
  color: var(--text);
  font: inherit;
}
.matrix-search:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
  border-color: var(--accent);
}
.filter-chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
}
.filter-chip {
  border: 1px solid var(--border);
  background: var(--chip-bg);
  color: var(--muted);
  padding: 8px 12px;
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.filter-chip.is-active {
  background: var(--chip-active-bg);
  border-color: transparent;
  color: var(--chip-active-fg);
}
.filter-chip:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
table { width: 100%; border-collapse: collapse; }
th, td {
  text-align: left;
  padding: 11px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
th {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border-strong);
  background: var(--surface-muted);
}
tbody tr:hover { background: var(--row-hover); }
tr[hidden] { display: none; }
.run-row td:first-child {
  font-weight: 600;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
}
a { color: var(--link); text-decoration: none; }
a:hover { color: var(--link-hover); text-decoration: underline; }
a:focus-visible { outline: 2px solid var(--link); outline-offset: 2px; border-radius: 2px; }
.badge {
  display: inline-block;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid;
}
.badge-pass { color: var(--pass); background: var(--pass-bg); border-color: var(--pass-border); }
.badge-fail { color: var(--fail); background: var(--fail-bg); border-color: var(--fail-border); }
.badge-err { color: var(--warn); background: var(--warn-bg); border-color: var(--warn-border); }
.badge-skip { color: var(--skip); background: var(--skip-bg); border-color: var(--skip-border); }
.rate-wrap { min-width: 96px; }
.rate-bar {
  height: 6px;
  background: var(--empty);
  border-radius: 999px;
  overflow: hidden;
  margin-top: 6px;
}
.rate-bar span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--pass), color-mix(in srgb, var(--pass) 70%, white));
  border-radius: inherit;
}
.rate-bar.fail span {
  background: linear-gradient(90deg, var(--fail), color-mix(in srgb, var(--fail) 70%, white));
}
.rate-num { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.matrix { overflow-x: auto; padding-bottom: 4px; }
.matrix table { min-width: 640px; }
.matrix thead th { position: sticky; top: 0; z-index: 2; }
.matrix th:not(:first-child),
.matrix td:not(:first-child) { text-align: center; width: 48px; padding: 6px 4px; }
.matrix td:first-child,
.matrix th:first-child {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--surface);
  min-width: 320px;
  max-width: 480px;
}
.matrix thead th:first-child { z-index: 3; background: var(--surface-muted); }
.test-id { display: block; line-height: 1.4; }
.test-id {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  line-height: 1.4;
}
a.test-name {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  text-decoration: none;
}
a.test-name:hover { color: var(--link); text-decoration: underline; }
.group-row td {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  background: var(--surface-muted);
  border-bottom: 1px solid var(--border);
  padding: 10px;
}
.flaky-tag {
  display: inline-block;
  margin-left: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--warn);
  background: var(--warn-bg);
  border: 1px solid var(--warn-border);
  border-radius: 999px;
  padding: 1px 6px;
  vertical-align: middle;
}
.cell {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1px solid color-mix(in srgb, var(--text) 10%, transparent);
  vertical-align: middle;
}
.cell-pass { background: var(--pass); box-shadow: 0 0 0 2px var(--pass-bg); }
.cell-fail { background: var(--fail); box-shadow: 0 0 10px var(--fail-bg); }
.cell-err { background: var(--warn); box-shadow: 0 0 8px var(--warn-bg); }
.cell-skip { background: var(--skip); }
.cell-none { background: var(--empty); }
.cell-flaky { outline: 2px dashed var(--warn); outline-offset: 2px; }
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 16px;
  font-size: 12px;
  color: var(--muted);
}
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.button {
  display: inline-block;
  margin: 8px 0 0;
  background: var(--cta);
  color: var(--button-fg);
  padding: 10px 14px;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border: 0;
  border-radius: 10px;
}
.button:hover { filter: brightness(1.06); text-decoration: none; color: var(--button-fg); }
pre {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  white-space: pre-wrap;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.55;
}
.rich-report { padding: 0; overflow: hidden; }
.rich-report summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
.rich-report summary > span:first-child {
  color: var(--accent);
}
.rich-report summary small { color: var(--muted); font-weight: 500; }
.rich-report:not([open]) summary { border-bottom: 0; }
.rich-report:not([open]) .hint-open { display: none; }
.rich-report[open] .hint-closed { display: none; }
.rich-report iframe { display: block; width: 100%; min-height: 780px; border: 0; background: #fff; }
.rich-report p { margin: 12px 18px 18px; }
.empty { padding: 18px; }
.wrap { max-width: 1280px; margin: 0 auto; padding: 28px 24px 72px; }
.masthead {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: end;
  margin-bottom: 22px;
}
.hero-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  gap: 16px;
  margin-bottom: 22px;
}
.gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px 12px;
  box-shadow: var(--shadow-soft);
}
.gauge-ring {
  width: 84px;
  height: 84px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  position: relative;
}
.gauge-ring::after {
  content: '';
  position: absolute;
  inset: 11px;
  border-radius: 50%;
  background: var(--surface);
}
.gauge-value {
  position: relative;
  z-index: 1;
  font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.05rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.gauge-label {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--muted);
  text-align: center;
}
.health-strip {
  height: 5px;
  background: var(--empty);
  border-radius: 999px;
  overflow: hidden;
  margin: 0 0 22px;
}
.health-fill {
  display: block;
  height: 100%;
  background: var(--pass);
  border-radius: inherit;
}
.health-strip.is-failing .health-fill { background: var(--fail); }
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 14px;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-soft);
  text-decoration: none;
}
.action-btn:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
.action-btn.primary {
  background: var(--cta);
  border-color: transparent;
  color: var(--button-fg);
}
.action-btn.primary:hover { filter: brightness(1.06); color: var(--button-fg); border-color: transparent; }
.action-btn.is-copied { background: var(--pass-bg); border-color: var(--pass-border); color: var(--pass); }
.action-panel {
  background: linear-gradient(180deg, var(--surface), var(--surface-muted));
}
.action-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.action-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
}
.action-item-main { min-width: 0; }
.action-item-title {
  display: block;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}
.action-item-module {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--muted);
}
.action-item-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.mini-btn {
  border: 1px solid var(--border);
  background: var(--surface-muted);
  color: var(--muted);
  border-radius: 999px;
  padding: 5px 10px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.mini-btn:hover { color: var(--accent); border-color: var(--accent); }
.mini-btn.is-copied { color: var(--pass); border-color: var(--pass-border); background: var(--pass-bg); }
.table-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.table-toolbar-left,
.table-toolbar-right {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.table-search,
.table-select {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface-muted);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}
.table-search {
  min-width: 220px;
  padding-left: 36px;
  background: var(--surface-muted) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%235a6b82' stroke-width='2'%3E%3Ccircle cx='7' cy='7' r='5'/%3E%3Cpath d='M11 11l3 3'/%3E%3C/svg%3E") 12px center no-repeat;
}
.table-select { min-width: 150px; }
.table-meta {
  font-size: 12px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.sort-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: inherit;
  font-weight: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  cursor: pointer;
  padding: 0;
}
.sort-btn:hover { color: var(--accent); }
.sort-btn.is-active { color: var(--accent); }
.sort-indicator {
  width: 10px;
  height: 10px;
  position: relative;
  opacity: 0.35;
}
.sort-btn.is-active .sort-indicator { opacity: 1; }
.sort-btn.is-asc .sort-indicator::after,
.sort-btn.is-desc .sort-indicator::after {
  content: '';
  position: absolute;
  left: 2px;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
}
.sort-btn.is-asc .sort-indicator::after {
  bottom: 1px;
  border-bottom: 6px solid currentColor;
}
.sort-btn.is-desc .sort-indicator::after {
  top: 1px;
  border-top: 6px solid currentColor;
}
.row-actions {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
.link-btn {
  font-size: 12px;
  font-weight: 600;
}
.tbsim-issue-actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.issue-tag {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-2);
}
.issue-linked { color: var(--accent); }
@media (max-width: 1080px) {
  .app { grid-template-columns: 1fr; }
  .sidebar {
    position: static;
    height: auto;
    border-right: 0;
    border-bottom: 1px solid var(--border);
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    padding: 16px 20px;
  }
  .sidebar-nav { flex-direction: row; flex-wrap: wrap; }
  .sidebar-block { margin-top: 0; padding-top: 0; border-top: 0; width: 100%; }
  .hero-shell { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .main { padding: 20px 16px 56px; }
  .hero-primary { grid-template-columns: 1fr; text-align: center; }
  .hero-ring { margin: 0 auto; }
  .summary-grid, .grid, .hero-row { grid-template-columns: 1fr; }
  .masthead, .topbar { flex-direction: column; align-items: stretch; }
  .stamp { text-align: left; }
  .overview-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .chart-legend-note { margin-left: 0; width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


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
    failing_cmds: list[str] = []
    max_duration = max((t["duration"] for t in tests), default=1.0) or 1.0
    modules = sorted({(_parse_test_id(t["id"])[0] or "other") for t in tests})
    module_options = "".join(
        f"<option value='{html.escape(mod.lower())}'>{html.escape(mod)}</option>"
        for mod in modules
    )
    for idx, t in enumerate(tests):
        anchor = _test_anchor(t["id"])
        pytest_cmd = _pytest_node(t["id"])
        module, name = _parse_test_id(t["id"])
        if t["status"] in {"failed", "error"}:
            failing_cmds.append(pytest_cmd)
        source = _source_url(run_meta["repo"], run_meta["sha"], t["file"], t["line"])
        source_link = (
            f"<a class='link-btn' href='{html.escape(source)}' target='_blank' rel='noopener'>Source</a>"
            if source
            else ""
        )
        trace_link = (
            f"<a class='mini-btn' href='#{anchor}'>Trace</a>"
            if t["status"] in {"failed", "error"}
            else ""
        )
        issue_actions = (
            _tbsim_issue_actions(
                t["id"],
                pytest_cmd=pytest_cmd,
                run_meta=run_meta,
                detail=t.get("detail", ""),
                anchor=anchor,
            )
            if t["status"] in {"failed", "error"}
            else ""
        )
        status_rank = _status_sort_rank(t["status"])
        dur_pct = round(100 * t["duration"] / max_duration)
        row_cls = "data-row test-row"
        if t["status"] in {"failed", "error"}:
            row_cls += " test-row-fail"
        rows.append(
            f"<tr class='{row_cls}' data-filter-status='{html.escape(t['status'])}'"
            f" data-filter-module='{html.escape(module.lower())}'"
            f" data-sort-name='{html.escape(t['id'].lower())}'"
            f" data-sort-status='{status_rank}'"
            f" data-sort-duration='{t['duration']:.6f}'"
            f" data-slow='{'true' if t['duration'] > 1.0 else 'false'}'"
            f" data-copy-cmd='{_copy_attr(pytest_cmd)}'"
            f" data-search='{html.escape(t['id'].lower())} {html.escape(t['status'])} {html.escape(module.lower())}'>"
            f"<td><div class='test-cell'>"
            f"<span class='test-module'>{html.escape(module or 'test')}</span>"
            f"<a class='test-name' href='#{anchor}' title='{html.escape(t['id'])}'>{html.escape(name or t['id'])}</a>"
            f"</div></td>"
            f"<td>{_status_badge(t['status'])}</td>"
            f"<td><div class='dur-cell'><span>{t['duration']:.3f}s</span>"
            f"<div class='dur-bar'><span style='width:{dur_pct}%'></span></div></div></td>"
            f"<td><div class='action-stack'>{trace_link}{issue_actions}{source_link}"
            f"<button type='button' class='mini-btn' data-copy-text='{_copy_attr(pytest_cmd)}'>Copy cmd</button>"
            f"<button type='button' class='mini-btn' data-copy-text='{_copy_attr(t['id'])}'>Copy id</button>"
            f"</div></td>"
            "</tr>"
        )

        if t["status"] in {"failed", "error"}:
            detail = html.escape(t["detail"][:20000] or "No traceback provided.")
            detail_cards.append(
                "<section class='card'>"
                f"<h3 id='{anchor}'>{html.escape(t['id'])}</h3>"
                f"<p>{_status_badge(t['status'])} "
                f"{_tbsim_issue_actions(t['id'], pytest_cmd=pytest_cmd, run_meta=run_meta, detail=t.get('detail', ''), anchor=anchor)} "
                f"<button type='button' class='mini-btn' data-copy-text='{_copy_attr(pytest_cmd)}'>Copy pytest cmd</button>"
                f"</p>"
                f"<pre>{detail}</pre>"
                "</section>"
            )

    rich_report_panel = (
        "<details class='card rich-report'>"
        "<summary><span>Rich pytest report</span>"
        "<small><span class='hint-closed'>Click to expand</span>"
        "<span class='hint-open'>Click to collapse</span></small></summary>"
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
        f"<li><a href='#{_test_anchor(t['id'])}'>{html.escape(t['id'])}</a> "
        f"{_tbsim_issue_actions(t['id'], pytest_cmd=_pytest_node(t['id']), run_meta=run_meta, detail=t.get('detail', ''), anchor=_test_anchor(t['id']))} "
        f"<button type='button' class='mini-btn' data-copy-text='{_copy_attr(_pytest_node(t['id']))}'>Copy cmd</button></li>"
        for t in tests
        if t["status"] in {"failed", "error"}
    )
    if not fail_list:
        fail_list = "<li>No failing tests in this run.</li>"
    copy_all_failures = "\n".join(failing_cmds)

    run_pass_rate = _pass_rate(run_meta["summary"])
    run_failures = by_status["failed"] + by_status["error"]
    run_stat_cls = "fail" if run_failures else "pass"

    content = f"""<!doctype html>
<html lang="en" data-theme="light" data-theme-mode="system">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Run #{html.escape(str(run_meta["run_number"]))}.{html.escape(str(run_meta["run_attempt"]))} · tbsim validation</title>
  <script>{_REPORT_THEME_SCRIPT}</script>
  <style>
{_REPORT_CSS}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <p class="eyebrow">Run detail · {html.escape(run_meta["workflow"])}</p>
        <h1>Run #{html.escape(str(run_meta["run_number"]))}.{html.escape(str(run_meta["run_attempt"]))}</h1>
      </div>
      <div class="topbar-actions">
        {_THEME_SWITCHER}
        <div class="stamp">
          <p class="stamp-label">Recorded (UTC)</p>
          <p class="stamp-value">{html.escape(run_meta["timestamp"])}</p>
        </div>
      </div>
    </div>
    <p class="subnav"><a href="../../index.html">Back to registry</a> · <a href="{html.escape(run_meta["run_url"])}">Open in GitHub Actions</a></p>
    <div class="action-bar">
      <a class="action-btn primary" href="{html.escape(run_meta["run_url"])}" target="_blank" rel="noopener">Open GitHub Actions</a>
      <button type="button" class="action-btn" data-jump="#failing-tests">Jump to failures</button>
      <button type="button" class="action-btn" data-jump="#full-test-list">Full test list</button>
      {f'<button type="button" class="action-btn" data-copy-text="{_copy_attr(copy_all_failures)}">Copy all failing pytest cmds</button>' if failing_cmds else '<button type="button" class="action-btn" disabled>Copy all failing pytest cmds</button>'}
      {f'<a class="action-btn" href="{html.escape(TBSIM_ISSUES_URL)}" target="_blank" rel="noopener">Browse tbsim issues</a>' if failing_cmds else ''}
      {f'<a class="action-btn" href="{html.escape(pytest_report_relpath)}">Open rich report</a>' if pytest_report_relpath else ''}
    </div>
    <section class="hero-row">
      <div class="summary-grid">
        <div class="stat {run_stat_cls}">
          <p class="stat-label">Pass rate</p>
          <p class="stat-value">{run_pass_rate}%</p>
          <p class="stat-note">{by_status["passed"]}/{run_meta["summary"]["total"]} tests passed</p>
        </div>
        <div class="stat">
          <p class="stat-label">Total tests</p>
          <p class="stat-value">{run_meta["summary"]["total"]}</p>
          <p class="stat-note">Collected in this run</p>
        </div>
        <div class="stat {'fail' if run_failures else ''}">
          <p class="stat-label">Failures</p>
          <p class="stat-value">{run_failures}</p>
          <p class="stat-note">Failed + error</p>
        </div>
        <div class="stat">
          <p class="stat-label">Skipped</p>
          <p class="stat-value">{by_status["skipped"]}</p>
          <p class="stat-note">Not executed</p>
        </div>
      </div>
      <div class="gauge">
        <div class="gauge-ring" style="background: conic-gradient(var(--pass) 0 {run_pass_rate}%, var(--empty) {run_pass_rate}% 100%);">
          <span class="gauge-value">{run_pass_rate}%</span>
        </div>
        <p class="gauge-label">Pass rate</p>
      </div>
    </section>
    {rich_report_panel}
    <section class="panel" id="failing-tests">
      <div class="panel-head">
        <h2>Failing tests</h2>
        <p class="panel-note">{run_failures} need attention · file upstream bugs, then link the GitHub issue number</p>
      </div>
      <ul>{fail_list}</ul>
    </section>
    <section class="panel" id="full-test-list">
      <div class="panel-head">
        <h2>Full test list</h2>
        <p class="panel-note">Filter, sort, jump to tracebacks, copy cmds</p>
      </div>
      <div class="table-toolbar">
        <div class="table-toolbar-left">
          <input class="table-search" id="run-tests-search" type="search" placeholder="Search tests or modules…" aria-label="Search tests" />
          <select class="table-select" id="run-tests-status" aria-label="Filter by status">
            <option value="all">All statuses</option>
            <option value="failed">Failed</option>
            <option value="error">Error</option>
            <option value="passed">Passed</option>
            <option value="skipped">Skipped</option>
            <option value="failing">Failing (failed + error)</option>
          </select>
          <select class="table-select" id="run-tests-module" aria-label="Filter by module">
            <option value="all">All modules</option>
            {module_options}
          </select>
          <div class="filter-chips" role="group" aria-label="Quick filters">
            <button type="button" class="filter-chip is-active" data-test-filter="all">All</button>
            <button type="button" class="filter-chip" data-test-filter="failing">Failing</button>
            <button type="button" class="filter-chip" data-test-filter="slow">Slow (&gt;1s)</button>
          </div>
        </div>
        <div class="table-toolbar-right">
          <button type="button" class="mini-btn" data-copy-visible-cmds="#run-tests-table">Copy visible cmds</button>
          <span class="table-meta" id="run-tests-count">{len(tests)} total</span>
        </div>
      </div>
      <table id="run-tests-table" data-table="run-tests" data-search-input="run-tests-search" data-status-input="run-tests-status" data-module-input="run-tests-module" data-test-filter-group="run-tests" data-count-target="run-tests-count">
        <thead><tr>
          {_sort_header("Test", "data-sort-name")}
          {_sort_header("Status", "data-sort-status", "number", "asc")}
          {_sort_header("Duration", "data-sort-duration", "number")}
          <th>Actions</th>
        </tr></thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </section>
    {"".join(detail_cards)}
  </div>
  {_issue_links_script()}
  <script>{_REPORT_JS}</script>
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

    cell_class = {
        "passed": "cell-pass",
        "failed": "cell-fail",
        "error": "cell-err",
        "skipped": "cell-skip",
        "not-run": "cell-none",
    }

    sorted_test_ids = sorted(
        all_test_ids,
        key=lambda tid: _matrix_sort_key(tid, runs_sorted, sorted(all_test_ids)),
    )
    flaky_count = sum(1 for tid in sorted_test_ids if _is_flaky(tid, runs_sorted))

    matrix_rows = []
    current_module = None
    for test_id in sorted_test_ids:
        module, name = _parse_test_id(test_id)
        if module and module != current_module:
            current_module = module
            matrix_rows.append(
                f"<tr class='group-row' data-module='{html.escape(module)}'>"
                f"<td colspan='{len(runs_sorted) + 1}'>{html.escape(module)}</td></tr>"
            )
        flaky = _is_flaky(test_id, runs_sorted)
        flaky_tag = "<span class='flaky-tag'>flaky</span>" if flaky else ""
        latest_status = (
            runs_sorted[0].get("tests", {}).get(test_id, "not-run") if runs_sorted else "not-run"
        )
        pytest_cmd = _pytest_node(test_id)
        issue_actions = ""
        if latest_status in {"failed", "error"} and runs_sorted:
            issue_actions = _tbsim_issue_actions(
                test_id,
                pytest_cmd=pytest_cmd,
                run_meta=runs_sorted[0],
                anchor=_test_anchor(test_id),
            )
        cells = []
        for run in runs_sorted:
            status = run.get("tests", {}).get(test_id, "not-run")
            cls = cell_class.get(status, "cell-none")
            extra = " cell-flaky" if flaky else ""
            cell = (
                f"<td><a href='{html.escape(run['report_path'])}' title='{html.escape(status)}'>"
                f"<span class='cell {cls}{extra}'></span></a></td>"
            )
            cells.append(cell)
        matrix_rows.append(
            "<tr class='matrix-row data-row'"
            f" data-module='{html.escape(module)}'"
            f" data-test-name='{html.escape(name or test_id)}'"
            f" data-latest-status='{html.escape(latest_status)}'"
            f" data-filter-status='{html.escape(latest_status)}'"
            f" data-flaky='{'true' if flaky else 'false'}'"
            f" data-sort-name='{html.escape((name or test_id).lower())}'"
            f" data-sort-module='{html.escape(module.lower())}'"
            f" data-sort-status='{_status_sort_rank(latest_status)}'"
            f" data-search='{html.escape((name or test_id).lower())} {html.escape(module.lower())} {html.escape(latest_status)}'>"
            f"<td><span class='test-id'>"
            f"<a class='test-name' href='{html.escape(runs_sorted[0]['report_path'])}#{_test_anchor(test_id)}' "
            f"title='Open latest result'>{html.escape(name or test_id)}</a>"
            f"{flaky_tag}"
            f"{issue_actions}"
            f"<button type='button' class='mini-btn' data-copy-text='{_copy_attr(pytest_cmd)}'>Copy cmd</button>"
            f"</span></td>"
            f"{''.join(cells)}"
            "</tr>"
        )

    run_rows = []
    for run in runs_sorted:
        s = run["summary"]
        pct = _pass_rate(s)
        bar_cls = "" if pct >= 100 else " fail"
        run_label = f"#{run['run_number']}.{run['run_attempt']}"
        run_rows.append(
            f"<tr class='run-row data-row' data-filter-status='{html.escape(run['status'])}'"
            f" data-sort-run='{run['run_number']:06d}.{run['run_attempt']}'"
            f" data-sort-status='{html.escape(run['status'])}'"
            f" data-sort-ts='{html.escape(run['timestamp'])}'"
            f" data-sort-passed='{pct}'"
            f" data-sort-failed='{s['failed']}'"
            f" data-sort-error='{s['error']}'"
            f" data-sort-skipped='{s['skipped']}'"
            f" data-search='{html.escape(run_label.lower())} {html.escape(run['status'])} {html.escape(run['timestamp'])}'>"
            f"<td><a href='{html.escape(run['report_path'])}'>{run_label}</a></td>"
            f"<td>{_status_badge(run['status'])}</td>"
            f"<td>{html.escape(run['timestamp'])}</td>"
            f"<td><div class='rate-wrap'><span class='rate-num'>{s['passed']}/{s['total']}</span>"
            f"<div class='rate-bar{bar_cls}'><span style='width:{pct}%'></span></div></div></td>"
            f"<td>{s['failed']}</td>"
            f"<td>{s['error']}</td>"
            f"<td>{s['skipped']}</td>"
            f"<td><div class='row-actions'>"
            f"<a class='link-btn' href='{html.escape(run['report_path'])}'>Report</a>"
            f"<a class='link-btn' href='{html.escape(run['run_url'])}'>Actions</a>"
            f"</div></td>"
            "</tr>"
        )

    total_runs = len(runs_sorted)
    latest = runs_sorted[0] if runs_sorted else None
    latest_pass_rate = _pass_rate(latest["summary"]) if latest else 0
    latest_failures = 0
    latest_stamp = "No runs recorded yet"
    latest_note = "Waiting for first CI execution"
    stat_cls = ""
    if latest:
        latest_failures = latest["summary"]["failed"] + latest["summary"]["error"]
        latest_stamp = (
            f"#{latest['run_number']}.{latest['run_attempt']} · "
            f"{html.escape(latest['timestamp'])} UTC"
        )
        latest_note = (
            f"{latest['summary']['passed']}/{latest['summary']['total']} tests passed"
        )
        stat_cls = "fail" if latest_failures else "pass"

    gauge_gradient = (
        f"conic-gradient(var(--pass) 0 {latest_pass_rate}%, var(--empty) {latest_pass_rate}% 100%)"
        if latest
        else "conic-gradient(var(--empty) 0 100%)"
    )
    quality_chart = _quality_history_chart(runs_sorted)
    action_queue_html, copy_all_failures = _build_action_queue(runs_sorted, sorted_test_ids)
    latest_report = latest["report_path"] if latest else ""
    latest_actions = latest["run_url"] if latest else ""
    copy_btn = (
        f'<button type="button" class="action-btn" data-copy-text="{_copy_attr(copy_all_failures)}">Copy all failing pytest cmds</button>'
        if copy_all_failures
        else '<button type="button" class="action-btn" disabled>Copy all failing pytest cmds</button>'
    )

    content = f"""<!doctype html>
<html lang="en" data-theme="light" data-theme-mode="system">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>tbsim validation registry</title>
  <script>{_REPORT_THEME_SCRIPT}</script>
  <style>
{_REPORT_CSS}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-mark" aria-hidden="true"></div>
        <div class="brand-copy">
          <strong>tbsim registry</strong>
          <span>External validation harness</span>
        </div>
      </div>
      <nav class="sidebar-nav" aria-label="Page sections">
        <a href="#overview">Overview</a>
        <a href="#quality-history">Quality history</a>
        <a href="#action-queue">Fix next</a>
        <a href="#run-history">Run history</a>
        <a href="#test-matrix">Test matrix</a>
      </nav>
      <div class="sidebar-block">
        <h3>Matrix legend</h3>
        <div class="legend">
          <span><span class="cell cell-pass"></span> passed</span>
          <span><span class="cell cell-fail"></span> failed</span>
          <span><span class="cell cell-err"></span> error</span>
          <span><span class="cell cell-skip"></span> skipped</span>
          <span><span class="cell cell-none"></span> not run</span>
          <span><span class="cell cell-pass cell-flaky"></span> flaky</span>
        </div>
      </div>
    </aside>

    <main class="main">
      <div class="topbar" id="overview">
        <div>
          <p class="eyebrow">Starsim · CI validation</p>
          <h1>tbsim validation registry</h1>
        </div>
        <div class="topbar-actions">
          {_THEME_SWITCHER}
          <div class="stamp">
            <p class="stamp-label">Latest run</p>
            <p class="stamp-value">{latest_stamp}</p>
          </div>
        </div>
      </div>

      <div class="action-bar">
        <button type="button" class="action-btn primary" data-jump="#action-queue">Review failures</button>
        {f'<a class="action-btn" href="{html.escape(latest_report)}">Open latest report</a>' if latest_report else ''}
        {f'<a class="action-btn" href="{html.escape(latest_actions)}" target="_blank" rel="noopener">Open GitHub Actions</a>' if latest_actions else ''}
        {copy_btn}
        {f'<a class="action-btn" href="{html.escape(TBSIM_ISSUES_URL)}" target="_blank" rel="noopener">Browse tbsim issues</a>' if copy_all_failures else ''}
        <button type="button" class="action-btn" data-jump="#quality-history">View quality chart</button>
        <button type="button" class="action-btn" data-jump="#test-matrix">Filter test matrix</button>
      </div>

      <section class="panel overview-panel" id="quality-history">
        <div class="overview-head">
          <div class="overview-ring" style="background: {gauge_gradient};">
            <span class="overview-ring-value">{latest_pass_rate}%</span>
          </div>
          <div class="overview-kpis">
            <div class="kpi-cell {stat_cls}">
              <span class="kpi-label">Passed</span>
              <span class="kpi-value">{latest_note}</span>
              <span class="kpi-note">{latest_pass_rate}% pass rate</span>
            </div>
            <div class="kpi-cell {'fail' if latest_failures else ''}">
              <span class="kpi-label">Open failures</span>
              <span class="kpi-value">{latest_failures}</span>
              <span class="kpi-note">Failed + error</span>
            </div>
            <div class="kpi-cell {'warn' if flaky_count else ''}">
              <span class="kpi-label">Flaky</span>
              <span class="kpi-value">{flaky_count}</span>
              <span class="kpi-note">Mixed history</span>
            </div>
            <div class="kpi-cell">
              <span class="kpi-label">Runs</span>
              <span class="kpi-value">{total_runs}</span>
              <span class="kpi-note">On record</span>
            </div>
          </div>
        </div>
        {quality_chart}
      </section>

      <section class="panel action-panel" id="action-queue">
        <div class="panel-head">
          <h2>Fix next</h2>
          <p class="panel-note">Failing tests from the latest run · jump to traceback or copy a local pytest cmd</p>
        </div>
        {action_queue_html}
      </section>

      <section class="panel" id="run-history">
        <div class="panel-head">
          <h2>Run history</h2>
          <p class="panel-note">Sort columns · filter by status · search runs</p>
        </div>
        <div class="table-toolbar">
          <div class="table-toolbar-left">
            <input class="table-search" id="run-history-search" type="search" placeholder="Search runs…" aria-label="Search runs" />
            <select class="table-select" id="run-history-status" aria-label="Filter runs by status">
              <option value="all">All statuses</option>
              <option value="failed">Failed only</option>
              <option value="passed">Passed only</option>
              <option value="skipped">Skipped only</option>
            </select>
          </div>
          <div class="table-toolbar-right">
            <span class="table-meta" id="run-history-count">0 shown</span>
          </div>
        </div>
        <table id="run-history-table" data-table="run-history" data-search-input="run-history-search" data-status-input="run-history-status" data-count-target="run-history-count">
          <thead><tr>
            {_sort_header("Run", "data-sort-run", "number")}
            {_sort_header("Status", "data-sort-status")}
            {_sort_header("Timestamp (UTC)", "data-sort-ts", "string", "desc")}
            {_sort_header("Passed", "data-sort-passed", "number")}
            {_sort_header("Failed", "data-sort-failed", "number")}
            {_sort_header("Error", "data-sort-error", "number")}
            {_sort_header("Skipped", "data-sort-skipped", "number")}
            <th>Actions</th>
          </tr></thead>
          <tbody>
            {"".join(run_rows) if run_rows else "<tr><td colspan='8'>No runs recorded yet.</td></tr>"}
          </tbody>
        </table>
      </section>

      <section class="panel matrix" id="test-matrix">
        <div class="panel-head">
          <h2>Test matrix</h2>
          <p class="panel-note">Sort by test, module, or status · search and filter</p>
        </div>
        <div class="table-toolbar">
          <div class="table-toolbar-left">
            <input class="table-search" id="matrix-search" type="search" placeholder="Search tests by name or module…" aria-label="Search tests" />
            <div class="filter-chips" role="group" aria-label="Matrix filters">
              <button type="button" class="filter-chip is-active" data-matrix-filter="all">All tests</button>
              <button type="button" class="filter-chip" data-matrix-filter="failing">Failing now</button>
              <button type="button" class="filter-chip" data-matrix-filter="flaky">Flaky only</button>
            </div>
            <select class="table-select" id="matrix-sort-mode" aria-label="Sort matrix by">
              <option value="data-sort-name">Sort: test name</option>
              <option value="data-sort-module">Sort: module</option>
              <option value="data-sort-status">Sort: latest status</option>
            </select>
          </div>
          <div class="table-toolbar-right">
            <span class="table-meta" id="matrix-count">0 shown</span>
          </div>
        </div>
        <table id="matrix-table" data-table="matrix" data-row-selector=".matrix-row" data-search-input="matrix-search" data-matrix-filter-group="matrix" data-count-target="matrix-count">
          <thead><tr>
            {_sort_header("Test", "data-sort-name", "string", "asc")}
            {run_headers}
          </tr></thead>
          <tbody>
            {"".join(matrix_rows) if matrix_rows else "<tr><td colspan='1'>No tests recorded yet.</td></tr>"}
          </tbody>
        </table>
      </section>
    </main>
  </div>
  {_issue_links_script()}
  <script>{_REPORT_JS}</script>
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
