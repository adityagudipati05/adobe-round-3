# Cascading Rules — Cross-Skill Ownership & Routing

> This document is the authoritative reference for how findings are **gated**,
> **routed**, and **deduplicated** across the four audit skills.  
> `compose_report.py` implements every rule listed here.

---

## 1. Ownership boundary: DV owns fetch-layer problems

| Problem | Owner | Notes |
|---------|-------|-------|
| Page blocked by bot-detect | **DV-13** | EN routed to EN-12; FS and ED not run |
| Page disallowed by robots.txt | **DV-16** | As above |
| Page has noindex | DV (no finding emitted) | Page marked `intentionally_excluded`; other skills skip |
| No `<meta>` description | **DV-01** | FS/EN/ED still run |
| No Organization schema | **DV-03** | ED-02 must NOT fire when no schema exists |

---

## 2. Cascading gates: DV flags feed downstream skills

### 2a. DV-13 / DV-16 → Engagement gate

```
if dv_flags["dv13_fired"] or dv_flags["dv16_fired"]:
    route EN to → EN-12 ("Page inaccessible to AI crawlers") only
    suppress all other EN checks
```

Rationale: engagement problems are irrelevant when the page isn't crawled at all.

### 2b. DV-01 critical → Engagement gate

```
if dv_flags["dv01_critical"]:
    route EN to → EN-13 ("No crawlable content: engagement moot") only
    suppress all other EN checks
```

`dv01_critical` is set on the DV flags when DV-01 fires AND the page has
< 50 words of body text (the `dv01_critical` flag from `run_dv_checks`).

### 2c. wikidata_backed → Entity-Disambiguation skip

```
if dv_flags["wikidata_backed"]:
    log site-level strength: "Entity anchored to Wikidata knowledge graph"
    skip ED-01 through ED-06 entirely
    ED-05 logged as strength
```

### 2d. Blocked / disallowed / errored / noindex fetch → skip FS **and** ED

```
if dv_flags["dv13_fired"] or dv_flags["dv16_fired"]
   or page_result["blocked"] or page_result["robots_disallowed"]
   or page_result["error"] or page_result["noindex"]:
    skip all FS checks   (no readable / in-scope page to assess)
    skip all ED checks   (no readable identity signal; DV owns the page)
```

A `noindex` page is `intentionally_excluded` — the site has declared it out of
scope, so no discoverability/engagement finding applies to it.

DV-13 / DV-16 are the single owning finding for an inaccessible page. Running
FS or ED on the challenge/error HTML only produces `unscored` noise or a
domain-derived phantom entity. EN is already routed to EN-12 by rule 2a.

### 2e. Entity-Disambiguation is site-level

ED-01 … ED-06 run only on **identity-relevant pages**: the homepage, or a URL
whose path names the organisation (`/about`, `/company`, `/who-we-are`,
`/our-story`, `/contact`, `/team`, `/leadership`, `/impressum`, `/corporate`).
On every other crawled page the ED skill returns an empty result, so one
identity defect is not re-emitted once per product / category / article URL.

---

## 3. Deduplication rules

### 3a. DV-03 vs ED-02

- DV-03: **No Organization schema at all** — fires when `_parse_org_schema()` returns `None`.
- ED-02: **Schema present but lacks sameAs/identifier** — fires ONLY when
  (a) `_ed01_fired = True`, AND (b) an Organization schema exists.

**Never fire both DV-03 and ED-02 for the same page.** The orchestrator must
check: if DV-03 is in `dv_result["findings"]`, suppress ED-02 even if it fires.

### 3b. Cross-page deduplication

When the same check ID fires on multiple pages:
- **Merge into a single finding**: take the worst-severity instance; list all
  affected page URLs in the `pages` array.
- **flag_only items are also merged by id** — one entry per check carrying the
  full `pages` list. Their recommendation text is page-independent (a
  "verify this manually" note), so five near-identical copies of FS-05 / EN-06
  across a crawl is noise, not signal.

### 3c. Strength deduplication

Log a strength **once per site** (not once per page). The orchestrator
collapses duplicate strength IDs.

---

## 4. Severity escalation

| Condition | Action |
|-----------|--------|
| A **`medium`** finding whose id is in the escalatable set fires on **every** audited page (and ≥ 3) | Escalate to `high` (and sync `suggested_action.priority`). Escalatable ids are the metadata / identity gaps that genuinely compound when repeated site-wide: `DV-02`, `DV-03`, `DV-09b`, `DV-11`, `DV-18`, `FS-01`, `FS-03`, `ED-04`, `ED-05`. |
| Any other finding (structural / engagement — `DV-15`, `FS-04`, `EN-05`, `EN-07`, `EN-08`, …) | **Never escalated by crawl breadth.** The repeat is one template, not new evidence. |
| Base severity `low`, or base severity `high`/`critical` | Never escalated. `critical` is only ever set explicitly by a check (`DV-01` auto, `DV-13`, `DV-16`) — escalation can never manufacture it. |

---

## 5. Overall health scoring

The `overall_health` field in the summary scorecard is derived from a
**weighted defect score**:

```
score = (critical × 10) + (high × 4) + (medium × 1) + (low × 0.25)
```

| Score range | Label |
|-------------|-------|
| 0 | `excellent` |
| 1–3 | `good` |
| 4–9 | `fair` |
| 10–24 | `poor` |
| ≥ 25 | `critical` |

---

## 6. Suggested actions ordering

The `suggested_actions` array in the report is sorted by:
1. `priority` (critical → high → medium → low)
2. Finding frequency (how many pages triggered it — descending)
3. Skill order: DV → FS → EN → ED (for ties)
