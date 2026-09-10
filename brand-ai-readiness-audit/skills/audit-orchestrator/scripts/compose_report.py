"""
compose_report.py — Audit Orchestrator for Brand AI-Readiness Audit.

Entry point
-----------
    from compose_report import run_audit
    report = run_audit(url, max_pages=5, timeout=30, verbose=False)

CLI usage
---------
    python compose_report.py https://example.com [--max-pages 5] [--verbose]

Output
------
    A structured JSON report conforming to references/report_schema.json.
    Printed to stdout (or returned as a dict when called as a module).

Architecture
------------
  1. Fetch pages (crawl-render-audit / fetch_page.py)
  2. Per-page DV checks  (crawl-render-audit / checks_dv.py)
  3. Per-page FS checks  (freshness-corroboration / checks_fs.py)
  4. Per-page EN checks  (engagement-audit / checks_en.py)    ← gated by DV flags
  5. Per-page ED checks  (entity-disambiguation / checks_ed.py) ← gated by DV flags
  6. Aggregate + deduplicate findings across pages
  7. Apply cascading rules (see references/cascading_rules.md)
  8. Compose final report dict
"""

import argparse
import json
import os
import sys
import time
import datetime
import urllib.parse
from collections import defaultdict
from typing import Dict, List, Optional

# ── Path bootstrap (allow running from any directory) ─────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILLS = os.path.normpath(os.path.join(_HERE, "..", ".."))   # brand-ai-readiness-audit/skills/

def _skill_path(skill: str, subdir: str = "scripts") -> str:
    return os.path.join(_SKILLS, skill, subdir)

for _skill in ["crawl-render-audit", "freshness-corroboration",
               "engagement-audit", "entity-disambiguation"]:
    p = _skill_path(_skill)
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Import skill modules ───────────────────────────────────────────────────────
from fetch_page import fetch_page          # noqa: E402
from checks_dv  import run_dv_checks, TRANSACTIONAL_URL_RE  # noqa: E402
from checks_fs  import run_fs_checks       # noqa: E402
from checks_en  import run_en_checks       # noqa: E402
from checks_ed  import run_ed_checks       # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
SCHEMA_VERSION = "1.0.0"

# Non-HTML file extensions that must never consume crawl budget. A discovered
# same-host link whose path ends in one of these is a binary/static asset, not
# a content page.
NON_CONTENT_EXTENSIONS: frozenset = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".woff", ".woff2", ".zip", ".mp4", ".mp3",
    ".ico", ".xml",
})

SEVERITY_WEIGHT = {"critical": 10, "high": 4, "medium": 1, "low": 0.25}
SEVERITY_ORDER  = ["critical", "high", "medium", "low"]
SKILL_ORDER     = ["DV", "FS", "EN", "ED"]

# Findings whose severity legitimately compounds when the SAME gap is present on
# every crawled page — a missing description / schema / freshness signal site-wide
# is materially worse than on one page. Structural and page-local findings are
# deliberately excluded (see _merge_findings).
ESCALATABLE_IDS = frozenset({
    "DV-02", "DV-03", "DV-09b", "DV-11", "DV-18",
    "FS-01", "FS-03",
    "ED-04", "ED-05",
})

# Health thresholds (weighted defect score)
def _health_label(score: float) -> str:
    if score == 0:       return "excellent"
    if score < 4:        return "good"
    if score < 10:       return "fair"
    if score < 25:       return "poor"
    return "critical"

# ── Crawl-queue policy ────────────────────────────────────────────────────────

def _has_non_content_extension(link: str) -> bool:
    """True if the URL path ends in a known non-HTML file extension."""
    path = urllib.parse.urlparse(link).path.lower()
    _, ext = os.path.splitext(path)
    return ext in NON_CONTENT_EXTENSIONS


def _select_crawl_candidates(internal_links: List[str],
                             already_queued: List[str]) -> List[str]:
    """
    Turn raw same-host internal links into an ordered crawl-queue candidate list.

    Policy (orchestrator concern, deliberately NOT baked into the general-purpose
    link extractor in fetch_page.py):
      * Drop links to binary/static assets (.pdf, .jpg, .css, .js, ...): they
        can never be audited as content pages.
      * De-prioritise transactional/utility URLs (cart, checkout, login, search,
        account, ...) — they are correctly thin and waste crawl budget — but do
        NOT hard-exclude them, so a tiny site that has nothing else still gets
        crawled.
    """
    queued = set(already_queued)
    preferred: List[str] = []
    deprioritized: List[str] = []
    for lnk in internal_links:
        if lnk in queued:
            continue
        if _has_non_content_extension(lnk):
            continue
        if TRANSACTIONAL_URL_RE.search(lnk):
            deprioritized.append(lnk)
        else:
            preferred.append(lnk)
    return preferred + deprioritized


# ── Cascading rule helpers ────────────────────────────────────────────────────

def _dv03_fired(dv_findings: list) -> bool:
    """True if DV-03 ('no Organization schema') fired in the DV findings."""
    return any(f.get("id") == "DV-03" for f in dv_findings)


def _apply_cascading_gates(dv_flags: dict, page_result: dict,
                           dv_findings: list) -> dict:
    """
    Return dict of {run_fs, run_en, run_ed, en_mode, ed_skip_reason}.
    Implements rules from references/cascading_rules.md §2.
    """
    gates = {
        "run_fs":  True,
        "run_en":  True,
        "run_ed":  True,
        "en_mode": "full",        # 'full' | 'en12_only' | 'en13_only'
        "ed_skip": False,
    }

    # FS: skip on network error, and on a blocked / robots-disallowed fetch —
    # there is no readable page to assess freshness or corroboration on, and
    # EN already routes such pages to EN-12.
    if (page_result.get("error")
            or dv_flags.get("dv13_fired") or dv_flags.get("dv16_fired")
            or page_result.get("blocked") or page_result.get("robots_disallowed")
            or page_result.get("noindex")):
        gates["run_fs"] = False

    # EN gate §2a / §2b
    if dv_flags.get("dv13_fired") or dv_flags.get("dv16_fired"):
        gates["en_mode"] = "en12_only"
    elif dv_flags.get("dv01_critical"):
        gates["en_mode"] = "en13_only"

    # ED gate §2c — wikidata-backed entity: skip ED, log the Wikidata strength.
    if dv_flags.get("wikidata_backed"):
        gates["ed_skip"] = True

    # ED gate — a blocked / disallowed / errored fetch has no readable identity
    # signal; DV-13/DV-16 own the page. Skip ED silently (no strength note).
    if (page_result.get("error")
            or dv_flags.get("dv13_fired") or dv_flags.get("dv16_fired")
            or page_result.get("blocked") or page_result.get("robots_disallowed")
            or page_result.get("noindex")):
        gates["run_ed"] = False

    return gates


# ── Per-page audit ────────────────────────────────────────────────────────────

def _audit_page(url: str, page_result: dict, verbose: bool = False) -> dict:
    """
    Run all four skill checks on one pre-fetched page_result.
    Returns a dict: {url, dv, fs, en, ed}
    """
    # Step 1: DV (always)
    dv = run_dv_checks(page_result)
    dv_flags    = dv.get("flags", {})
    dv_findings = dv.get("findings", [])

    gates = _apply_cascading_gates(dv_flags, page_result, dv_findings)

    # Step 2: FS
    fs = run_fs_checks(page_result) if gates["run_fs"] else {
        "url": url, "findings": [], "flag_only_items": [], "strengths": [],
        "skipped": True,
        "skip_reason": ("fetch_error" if page_result.get("error")
                        else "fetch_blocked"),
    }

    # Step 3: EN — pass dv_flags so it can apply its internal routing
    en = run_en_checks(page_result, dv_flags=dv_flags) if gates["run_en"] else {
        "url": url, "findings": [], "flag_only_items": [], "strengths": [],
    }

    # Step 4: ED — pass dv_flags and dv_findings
    if not gates["run_ed"]:
        ed = {"url": url, "findings": [], "flag_only_items": [], "strengths": []}
    elif gates["ed_skip"]:
        ed = {
            "url": url, "findings": [], "flag_only_items": [],
            "strengths": [{
                "_strength": True,
                "id": "ED-WIKIDATA-SKIP",
                "title": ("All ED checks skipped — entity identity is already "
                          "anchored to the Wikidata knowledge graph."),
            }],
        }
    else:
        ed = run_ed_checks(page_result, dv_flags=dv_flags, dv_findings=dv_findings)

    # ED-02 suppression: if DV-03 fired, remove any ED-02 findings (§3a)
    if _dv03_fired(dv_findings):
        ed["findings"] = [f for f in ed.get("findings", []) if f.get("id") != "ED-02"]

    # Retain a slim copy of the raw page_result so _build_proactive_suggestions
    # can scan body text and JSON-LD blocks. This key is orchestrator-internal
    # ONLY — run_audit() strips it before the report is composed, so it never
    # reaches the final JSON (and raw_html is dropped here to avoid any bloat).
    slim_page_result = {k: v for k, v in page_result.items() if k != "raw_html"}

    return {"url": url, "dv": dv, "fs": fs, "en": en, "ed": ed,
            "page_result": slim_page_result}


# ── Aggregation helpers ────────────────────────────────────────────────────────

def _prefix(check_id: str) -> str:
    """'DV-01' → 'DV', 'EN-13' → 'EN', etc."""
    return check_id.split("-")[0] if "-" in check_id else "??"


def _severity_index(sev: str) -> int:
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return len(SEVERITY_ORDER)


def _escalate_severity(sev: str) -> str:
    """Escalate severity by one level (low→medium, medium→high, high→critical)."""
    idx = _severity_index(sev)
    return SEVERITY_ORDER[max(0, idx - 1)]


def _merge_findings(per_page_results: List[dict]) -> List[dict]:
    """
    Merge per-page findings by check ID.
    - Keep worst severity instance.
    - Collect all page URLs.
    - Escalate severity one level only when the SAME id fires on every audited
      page (and at least 3), i.e. it is a genuine site-wide defect — not merely
      because a wide crawl visited many pages (§4). `low` is never escalated.
    - Sort by severity then skill order.
    """
    total_pages = len(per_page_results)
    by_id: Dict[str, dict] = {}
    pages_by_id: Dict[str, List[str]] = defaultdict(list)

    for ppr in per_page_results:
        url = ppr["url"]
        for skill_key in ["dv", "fs", "en", "ed"]:
            skill_result = ppr.get(skill_key, {})
            for f in skill_result.get("findings", []):
                fid = f.get("id")
                if not fid:
                    continue
                pages_by_id[fid].append(url)
                if fid not in by_id:
                    by_id[fid] = dict(f)
                else:
                    # Keep worst severity
                    existing_idx = _severity_index(by_id[fid].get("severity", "low"))
                    new_idx      = _severity_index(f.get("severity", "low"))
                    if new_idx < existing_idx:
                        by_id[fid] = dict(f)

    # Attach pages list + apply escalation rule
    merged = []
    for fid, finding in by_id.items():
        affected = list(dict.fromkeys(pages_by_id[fid]))   # dedupe, preserve order
        finding["pages"] = affected
        base_sev = finding.get("severity", "low")
        site_wide = len(affected) >= 3 and len(affected) == total_pages
        # Escalate a genuinely site-wide MEDIUM to HIGH — but only for
        # metadata/identity gaps that actually compound when repeated on every
        # page. Structural/engagement findings (DV-15 repeated block, FS-04
        # nav/footer drift, EN-05 hidden tabs, …) are the same on every page
        # *because it is one template*; the repeat count is not new information,
        # and `critical` stays reserved for checks that set it explicitly.
        if (site_wide and base_sev == "medium"
                and fid in ESCALATABLE_IDS):
            finding["severity"] = "high"
            if isinstance(finding.get("suggested_action"), dict):
                finding["suggested_action"]["priority"] = "high"
        merged.append(finding)

    # Sort: severity first, then skill order
    def sort_key(f):
        return (
            _severity_index(f.get("severity", "low")),
            SKILL_ORDER.index(_prefix(f.get("id", "??")))
            if _prefix(f.get("id", "??")) in SKILL_ORDER else 99,
        )

    return sorted(merged, key=sort_key)


def _merge_flag_only(per_page_results: List[dict]) -> List[dict]:
    """
    Collapse flag-only items by id: one entry per check, carrying the full list
    of pages it was raised on. The recommendation text is page-independent (it
    is a "go check this manually" note), so emitting five near-identical copies
    of FS-05 / EN-06 across a crawl is pure noise.
    """
    by_id: Dict[str, dict] = {}
    for ppr in per_page_results:
        url = ppr["url"]
        for skill_key in ["dv", "fs", "en", "ed"]:
            for fo in ppr.get(skill_key, {}).get("flag_only_items", []):
                fid = fo.get("id", "?")
                if fid not in by_id:
                    item = dict(fo)
                    item["pages"] = [url]
                    by_id[fid] = item
                elif url not in by_id[fid]["pages"]:
                    by_id[fid]["pages"].append(url)
    return list(by_id.values())


def _merge_strengths(per_page_results: List[dict]) -> List[dict]:
    """
    Deduplicate strengths by ID — log each strength once per site (§3c).
    """
    seen = set()
    out = []
    for ppr in per_page_results:
        for skill_key in ["dv", "fs", "en", "ed"]:
            for s in ppr.get(skill_key, {}).get("strengths", []):
                sid = s.get("id")
                if sid and sid not in seen:
                    seen.add(sid)
                    out.append({k: v for k, v in s.items() if not k.startswith("_")})
    return out


def _ldjson_types(blocks) -> List[str]:
    """
    Collect every schema.org @type (as a string) from a list of JSON-LD blocks.

    fetch_page.py returns ldjson_blocks as raw JSON *strings*, so each block is
    parsed here; malformed blocks are skipped. A block may be a dict or a list
    of dicts, and @type may itself be a string or a list.
    """
    found: List[str] = []
    for raw in blocks or []:
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        items = obj if isinstance(obj, list) else [obj]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            if isinstance(t, str):
                found.append(t)
            elif isinstance(t, list):
                found.extend(str(x) for x in t)
    return found


def _build_proactive_suggestions(per_page_results: List[dict], findings: List[dict]) -> List[dict]:
    """
    Generate beyond-defect proactive suggestions per taxonomy doc:
    1. FAQ exists, no FAQPage schema
    2. Strong identity facts exist, no Organization schema, no collision risk
    3. Named/attributed testimonials but no Review schema
    4. Third-party press/citations exist but aren't linked as corroborating sources
    5. No /llms.txt on a docs-heavy or content-rich site
    """
    proactive = []
    finding_ids = {f.get("id") for f in findings}

    combined_body = " ".join((p.get("page_result", {}).get("body_text", "") or "").lower() for p in per_page_results)

    # All schema.org @type values across every page's JSON-LD, parsed once.
    all_ldjson_types = []
    for p in per_page_results:
        all_ldjson_types.extend(
            _ldjson_types(p.get("page_result", {}).get("ldjson_blocks", []))
        )

    # 1. FAQ exists, no FAQPage schema
    has_faq_content = any(k in combined_body for k in ["faq", "frequently asked questions", "q&a", "questions & answers"])
    has_faq_schema = any("FAQPage" in t for t in all_ldjson_types)
    if has_faq_content and not has_faq_schema:
        proactive.append({
            "summary": "Add FAQPage JSON-LD schema to pages containing Q&A content.",
            "priority": "medium",
            "detail": "FAQ content was detected on the site. Wrapping questions and answers in schema.org/FAQPage markup allows AI assistants and search engines to quote structured solutions directly in answers.",
        })

    # 2. Strong identity facts exist, no Organization schema, no collision risk
    has_identity_facts = any(k in combined_body for k in ["founded in", "established in", "registration number", "cin", "corporate headquarters", "headquartered in"])
    has_org_schema = any(
        t in ["Organization", "Corporation", "LocalBusiness", "EducationalOrganization"]
        for t in all_ldjson_types
    )
    if has_identity_facts and not has_org_schema and "ED-02" not in finding_ids:
        proactive.append({
            "summary": "Add schema.org/Organization JSON-LD markup with official identifier and founding details.",
            "priority": "medium",
            "detail": "Strong corporate identity facts exist on-page but lack structured Organization markup. Adding schema.org/Organization provides an unambiguous anchor for AI assistants without name-collision ambiguity.",
        })

    # 3. Testimonials exist but no Review schema
    has_testimonials = any(k in combined_body for k in ["testimonials", "what our customers say", "client feedback", "reviews", "customer stories"])
    has_review_schema = any(
        t in ["Review", "CriticReview", "AggregateRating"] for t in all_ldjson_types
    )
    if has_testimonials and not has_review_schema and "DV-07" not in finding_ids:
        proactive.append({
            "summary": "Add schema.org/Review or AggregateRating markup to customer testimonials.",
            "priority": "low",
            "detail": "Customer reviews and testimonials are present. Adding structured Review schema makes social proof extractable by AI assistants searching for brand credibility.",
        })

    # 4. Third-party press mentions exist
    has_press = any(k in combined_body for k in ["featured in", "in the news", "press coverage", "as seen in", "newsroom"])
    if has_press:
        proactive.append({
            "summary": "Link third-party press coverage as sameAs or subjectOf references in structured data.",
            "priority": "low",
            "detail": "Press and media citations enhance credibility. Explicitly referencing external articles via sameAs or subjectOf schema properties provides machine-verifiable corroboration.",
        })

    # 5. Missing /llms.txt
    has_llms_strength = False
    for p in per_page_results:
        for s in p.get("dv", {}).get("strengths", []):
            if s.get("id") == "DV-18":
                has_llms_strength = True
    if not has_llms_strength:
        proactive.append({
            "summary": "Publish an /llms.txt file at domain root listing key crawlable content and documentation.",
            "priority": "low",
            "detail": "/llms.txt is an emerging standard enabling AI crawlers to discover high-priority markdown and plain-text resources with minimal crawl overhead.",
        })

    return proactive


def _build_suggested_actions(findings: List[dict], per_page_results: Optional[List[dict]] = None) -> List[dict]:
    """
    Deduplicate and sort suggested actions from all merged findings,
    plus beyond-defect proactive suggestions.
    Sort order: priority → finding page count (desc) → skill order (§6).
    """
    seen = set()
    actions = []
    for f in findings:
        action = f.get("suggested_action")
        if not action:
            continue
        key = action.get("summary", "")[:120]  # dedupe on trimmed summary
        if key in seen:
            continue
        seen.add(key)
        actions.append({
            "summary":  action.get("summary", ""),
            "priority": action.get("priority", f.get("severity", "medium")),
            "detail":   action.get("detail", ""),
            "_page_count": len(f.get("pages", [])),
            "_skill":   _prefix(f.get("id", "??")),
        })

    # Add beyond-defect proactive suggestions if per_page_results provided
    if per_page_results:
        proactive_items = _build_proactive_suggestions(per_page_results, findings)
        for pa in proactive_items:
            key = pa["summary"][:120]
            if key not in seen:
                seen.add(key)
                actions.append({
                    "summary":  pa["summary"],
                    "priority": pa["priority"],
                    "detail":   pa.get("detail", ""),
                    "_page_count": 0,
                    "_skill":   "DV",
                })

    def action_sort(a):
        return (
            _severity_index(a["priority"]),
            -a["_page_count"],
            SKILL_ORDER.index(a["_skill"]) if a["_skill"] in SKILL_ORDER else 99,
        )

    actions.sort(key=action_sort)
    # Strip internal keys
    return [{k: v for k, v in a.items() if not k.startswith("_")} for a in actions]


def _build_summary(findings: List[dict], flag_only: List[dict],
                   strengths: List[dict]) -> dict:
    counts = defaultdict(int)
    cat_scores: Dict[str, int] = {s: 0 for s in SKILL_ORDER}

    for f in findings:
        sev = f.get("severity", "low")
        counts[sev] += 1
        cat = _prefix(f.get("id", "??"))
        if cat in cat_scores:
            cat_scores[cat] += 1

    total = sum(counts.values())
    weighted = sum(SEVERITY_WEIGHT.get(sev, 0) * n for sev, n in counts.items())

    return {
        "total_findings":    total,
        "critical":          counts.get("critical", 0),
        "high":              counts.get("high", 0),
        "medium":            counts.get("medium", 0),
        "low":               counts.get("low", 0),
        "critical_findings": counts.get("critical", 0),
        "high_findings":     counts.get("high", 0),
        "medium_findings":   counts.get("medium", 0),
        "low_findings":      counts.get("low", 0),
        "total_flag_only":   len(flag_only),
        "total_strengths":   len(strengths),
        "overall_health":    _health_label(weighted),
        "category_scores":   cat_scores,
    }


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run_audit(url: str,
              max_pages: int = 5,
              timeout: int = 30,
              verbose: bool = False) -> dict:
    """
    Orchestrate a full Brand AI-Readiness audit for `url`.

    Parameters
    ----------
    url        : Root URL to audit (homepage).
    max_pages  : Maximum number of pages to fetch (default 5).
    timeout    : Per-page HTTP timeout in seconds (default 30).
    verbose    : If True, include raw per-page results in the report.

    Returns
    -------
    report : dict conforming to references/report_schema.json
    """
    started = time.time()
    pages_to_audit: List[str] = [url]
    per_page_results: List[dict] = []
    audited_urls: List[str] = []

    print(f"[audit] Starting audit of {url}", file=sys.stderr)

    for i, page_url in enumerate(pages_to_audit):
        if i >= max_pages:
            break

        # Elapsed-time guard (5-minute limit)
        if time.time() - started > 290:
            print(f"[audit] 5-minute limit approaching — stopping at page {i}",
                  file=sys.stderr)
            break

        print(f"[audit] Fetching ({i+1}/{min(max_pages, len(pages_to_audit))}): {page_url}",
              file=sys.stderr)

        try:
            page_result = fetch_page(page_url, timeout=timeout)
        except Exception as exc:
            print(f"[audit] fetch error for {page_url}: {exc}", file=sys.stderr)
            page_result = {
                "url": page_url, "clean_url": page_url,
                "head": {}, "raw_html": None, "body_text": "",
                "content_word_count": 0, "has_raw_html": False,
                "blocked": False, "blocked_reason": None,
                "robots_disallowed": False, "noindex": False,
                "error": str(exc), "ldjson_blocks": [],
                "internal_links": [],
            }

        audited_urls.append(page_url)

        # If this is the homepage, discover internal links for subsequent pages
        if i == 0 and max_pages > 1:
            links = page_result.get("internal_links", [])
            for lnk in _select_crawl_candidates(links, pages_to_audit):
                if lnk not in pages_to_audit and len(pages_to_audit) < max_pages:
                    pages_to_audit.append(lnk)

        # Audit the page
        ppr = _audit_page(page_url, page_result, verbose=verbose)
        per_page_results.append(ppr)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    findings        = _merge_findings(per_page_results)
    flag_only       = _merge_flag_only(per_page_results)
    strengths       = _merge_strengths(per_page_results)
    suggested_acts  = _build_suggested_actions(findings, per_page_results)
    summary         = _build_summary(findings, flag_only, strengths)

    domain = urllib.parse.urlparse(url).netloc or url
    now_iso = (datetime.datetime.now(datetime.timezone.utc)
               .replace(tzinfo=None).isoformat() + "Z")

    report: dict = {
        "site":            domain,
        "audited_at":      now_iso,
        "schema_version":  SCHEMA_VERSION,
        "generated_at":    now_iso,
        "target_url":      url,
        "pages_audited":   audited_urls,
        "audit_config": {
            "max_pages":       max_pages,
            "timeout_seconds": timeout,
            "skills_run":      ["crawl-render-audit", "freshness-corroboration",
                                "engagement-audit", "entity-disambiguation"],
        },
        "summary":          summary,
        "findings":         findings,
        "flag_only_items":  flag_only,
        "strengths":        strengths,
        "suggested_actions": suggested_acts,
    }

    if verbose:
        # Drop the orchestrator-internal 'page_result' copy so it never leaks
        # into the serialized report.
        report["raw_per_page"] = [
            {k: v for k, v in ppr.items() if k != "page_result"}
            for ppr in per_page_results
        ]

    elapsed = round(time.time() - started, 1)
    print(f"[audit] Done in {elapsed}s — {summary['total_findings']} findings, "
          f"health={summary['overall_health']}", file=sys.stderr)

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="Brand AI-Readiness Audit — orchestrator",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("url", help="Target URL to audit (e.g. https://example.com)")
    parser.add_argument("--max-pages", type=int, default=5,
                        help="Maximum pages to audit (default: 5)")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Per-page fetch timeout in seconds (default: 30)")
    parser.add_argument("--verbose", action="store_true",
                        help="Include raw per-page skill results in output")
    parser.add_argument("--out", metavar="FILE",
                        help="Write JSON report to FILE instead of stdout")

    args = parser.parse_args()

    report = run_audit(
        url=args.url,
        max_pages=args.max_pages,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    report_json = json.dumps(report, indent=2, ensure_ascii=False)

    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report_json)
        print(f"[audit] Report written to {args.out}", file=sys.stderr)
    else:
        print(report_json)


if __name__ == "__main__":
    _cli()
