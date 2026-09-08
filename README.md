# 🏆 Adobe University Hackathon 2026 — Round 3
## Brand AI-Readiness Audit — Agent Skill Marketplace

[![Adobe Hackathon 2026](https://img.shields.io/badge/Adobe%20Hackathon-Round%203%20Submission-FF0000?style=for-the-badge&logo=adobe&logoColor=white)](https://github.com/adityagudipati05/adobe-round-3)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Test Coverage](https://img.shields.io/badge/Tests-180%20Passing%20(100%25)-success.svg?style=for-the-badge)](./brand-ai-readiness-audit/)
[![Execution Guardrails](https://img.shields.io/badge/Execution-Recommend--Only-orange.svg?style=for-the-badge)](./brand-ai-readiness-audit/README.md#guardrails)

> An enterprise-grade **Agent Skill Marketplace** that performs comprehensive **AI-Readiness & On-Site Engagement Audits** for websites. Produces deterministic, structured JSON reports containing actionable findings, risk severity levels, page aggregation, and prioritized recommendations.

---

## 📌 Executive Summary

Modern AI search engines and conversational assistants (e.g. ChatGPT, Claude, Perplexity, Gemini) index, digest, and cite web content differently than traditional web crawlers. Simultaneously, on-site visitors require clear navigation, trust signals, and zero friction.

This repository delivers the **Brand AI-Readiness Audit Marketplace**, a multi-agent modular evaluation suite submitted for **Adobe University Hackathon 2026 (Round 3)**.

### Core Objectives:
1. **AI Discoverability Audit (DV-01 … DV-20)**: Evaluates robots.txt policy, JS-rendering vulnerabilities, JSON-LD structured schema completeness, llms.txt availability, canonical routing, and AI-spam signals.
2. **Freshness & Corroboration (FS-01 … FS-06)**: Detects date staleness, numerical/listing mismatches across content sections, footer date drift, and explicit `[citation needed]` markers.
3. **Visitor Engagement Audit (EN-01 … EN-13)**: Assesses friction, dead links, breadcrumb navigation, CTA visibility, paywalls, and trust signals with dynamic cascading routes based on visibility findings.
4. **Entity Disambiguation (ED-01 … ED-06)**: Validates Wikidata/Wikipedia resolution, Organization sameAs attributes, social profile linkages, and brand name collision risks.
5. **Orchestrator Engine**: Crawls multi-page sites, applies strict cascading/ownership rules, aggregates severity, and generates schema-valid JSON reports.

---

## 🏗️ Architecture & Orchestration Flow

The architecture follows a strict decoupled marketplace model governed by `marketplace.json`. The `audit-orchestrator` acts as the single entrypoint controlling all downstream audit skills.

```
                         ┌────────────────────────────────┐
                         │   Target URL (CLI Input)       │
                         └───────────────┬────────────────┘
                                         │
                                         ▼
                         ┌────────────────────────────────┐
                         │       audit-orchestrator       │
                         │   (Crawls pages up to --max)   │
                         └───────────────┬────────────────┘
                                         │
     ┌───────────────────┬───────────────┴───────────────┬───────────────────┐
     ▼                   ▼                               ▼                   ▼
┌─────────┐      ┌───────────────┐               ┌───────────────┐   ┌───────────────┐
│ crawl-  │      │  freshness-   │               │  engagement-  │   │    entity-    │
│ render- │      │ corroboration │               │     audit     │   │disambiguation │
│  audit  │      │  (FS-01..06)  │               │  (EN-01..13)  │   │  (ED-01..06)  │
│(DV-01..)│      └───────┬───────┘               └───────┬───────┘   └───────┬───────┘
└────┬────┘              │                               │                   │
     │                   │                               │                   │
     └─────────┬─────────┴───────────────┬───────────────┴───────────────────┘
               │                         │
               ▼                         ▼
    ┌──────────────────────┐  ┌──────────────────────┐
    │  dv_flags & Route    │  │  Cascading & Dup     │
    │  Gating Resolution   │  │  Suppression Engine  │
    └──────────┬───────────┘  └──────────┬───────────┘
               │                         │
               └────────────┬────────────┘
                            │
                            ▼
           ┌──────────────────────────────────┐
           │      compose_report.py           │
           │  • Page-level Severity Escalation│
           │  • Action Item Prioritization   │
           │  • Schema Verification           │
           └────────────────┬─────────────────┘
                            │
                            ▼
           ┌──────────────────────────────────┐
           │     Final JSON Audit Report      │
           └──────────────────────────────────┘
```

---

## 📂 Repository Structure

```
adobe-round-3/
├── README.md                                   # Root technical overview & marketplace manual
├── brand-ai-readiness-audit-submission.zip     # Submission zip archive (<50 MB limit, clean)
└── brand-ai-readiness-audit/                   # Main Skill Marketplace Directory
    ├── marketplace.json                        # Marketplace manifest declaring all 5 skills
    ├── README.md                               # Inner technical documentation & schemas
    ├── run_phase7_special_cases.py             # Validation runner for edge cases
    ├── test_dv_checks_stdlib.py                # Pure stdlib unit test suite (41 tests)
    ├── smoke_test_dv.py                        # DV check unit suite (33 tests)
    ├── smoke_test_fs.py                        # FS check unit suite (25 tests)
    ├── smoke_test_en.py                        # EN check unit suite (27 tests)
    ├── smoke_test_ed.py                        # ED check unit suite (31 tests)
    ├── smoke_test_orchestrator.py              # Full multi-page pipeline suite (27 tests)
    ├── reports/                                # Real-world production audit reports
    │   ├── wikipedia_tim.json                  # Wikipedia / Wikidata sameAs report
    │   ├── kisansuvidha.json                   # JS-render gap critical routing report
    │   ├── hackernews.json                     # HackerNews schema & header gap report
    │   ├── python_org.json                     # Python.org freshness & entity report
    │   ├── bot_block_dv13_en12.json            # Bot-block / WAF challenge report
    │   └── noindex_en11.json                   # Noindex exclusion short-circuit report
    └── skills/                                 # Individual Skill Packages
        ├── audit-orchestrator/                 # [ENTRYPOINT] Core orchestration engine
        │   ├── SKILL.md                        # Agent prompt & orchestration specification
        │   ├── references/                     # report_schema.json & cascading_rules.md
        │   └── scripts/compose_report.py       # Main report compilation CLI script
        ├── crawl-render-audit/                 # Visibility & Crawlability (DV-01 .. DV-20)
        │   ├── SKILL.md                        # Skill definition & checklist reference
        │   ├── references/dv_checklist.md      # Detailed check specifications
        │   └── scripts/                        # fetch_page.py & checks_dv.py
        ├── freshness-corroboration/            # Date Freshness & Markers (FS-01 .. FS-06)
        │   ├── SKILL.md                        # Skill definition & checklist reference
        │   ├── references/fs_checklist.md      # Detailed check specifications
        │   └── scripts/checks_fs.py            # FS audit engine
        ├── engagement-audit/                   # On-Site Visitor Friction (EN-01 .. EN-13)
        │   ├── SKILL.md                        # Skill definition & checklist reference
        │   ├── references/en_checklist.md      # Detailed check specifications
        │   └── scripts/checks_en.py            # EN audit engine
        └── entity-disambiguation/              # Brand Entity Identity (ED-01 .. ED-06)
            ├── SKILL.md                        # Skill definition & checklist reference
            ├── references/ed_checklist.md      # Detailed check specifications
            └── scripts/checks_ed.py            # ED audit engine
```

---

## 🛍️ Agent Skill Marketplace Registry

| Skill ID | Role | Entrypoint | Check Range | Focus Area |
|---|---|:---:|:---:|---|
| **`audit-orchestrator`** | Orchestrator | ✅ **Yes** | N/A | Multi-page crawl, skill pipeline sequence, cascading rule engine, severity escalation & report emission |
| **`crawl-render-audit`** | Evaluator | ❌ No | DV-01 .. DV-20 | Bot-blocking, robots.txt, JS rendering, JSON-LD schema, canonicals, llms.txt, meta tags |
| **`freshness-corroboration`** | Evaluator | ❌ No | FS-01 .. FS-06 | Stale dates, numerical/count mismatches, footer date drift, explicit corroboration tags |
| **`engagement-audit`** | Evaluator | ❌ No | EN-01 .. EN-13 | Dynamic routing, wayfinding, breadcrumbs, paywalls, broken links, trust signals, CTA visibility |
| **`entity-disambiguation`** | Evaluator | ❌ No | ED-01 .. ED-06 | Wikidata verification, Organization sameAs, social profile links, brand collision risks |

---

## 🚀 Quick Start Guide

### Prerequisites
- Python **3.10+**
- Standard dependencies: `requests`, `beautifulsoup4`, `lxml`

### Installation

```bash
# Clone the repository
git clone https://github.com/adityagudipati05/adobe-round-3.git
cd adobe-round-3/brand-ai-readiness-audit

# Install required dependencies
pip install requests beautifulsoup4 lxml
```

### Running an Audit

```bash
# Basic single-page audit
python skills/audit-orchestrator/scripts/compose_report.py https://example.com

# Multi-page audit (up to 10 pages) with custom JSON output path
python skills/audit-orchestrator/scripts/compose_report.py https://example.com \
  --max-pages 10 \
  --out report.json
```

---

## 🧪 Verification & Test Suite

The marketplace is validated by **180 automated unit tests** (0 network calls required) achieving **100% pass rate** across all individual checks, cascading logic, and orchestrator scenarios.

### Running Unit Tests

```bash
cd brand-ai-readiness-audit

# Run standard library offline tests
python test_dv_checks_stdlib.py

# Run individual skill smoke suites
python smoke_test_dv.py
python smoke_test_fs.py
python smoke_test_en.py
python smoke_test_ed.py

# Run full pipeline integration test suite
python smoke_test_orchestrator.py
```

### Test Coverage Summary

| Test Suite | Total Checks | Scope | Status |
|---|:---:|---|:---:|
| `test_dv_checks_stdlib.py` | 41 | Pure stdlib functions, robots.txt RFC 9309 compliance & edge cases | ✅ PASS |
| `smoke_test_dv.py` | 33 | Visibility & Crawlability (DV-01 … DV-20) | ✅ PASS |
| `smoke_test_fs.py` | 25 | Freshness & Corroboration (FS-01 … FS-06) | ✅ PASS |
| `smoke_test_en.py` | 27 | Engagement Friction & Routing Gates (EN-01 … EN-13) | ✅ PASS |
| `smoke_test_ed.py` | 31 | Entity Disambiguation & Wikidata Gates (ED-01 … ED-06) | ✅ PASS |
| `smoke_test_orchestrator.py` | 27 | Full end-to-end multi-page pipeline (8 complex scenarios) | ✅ PASS |
| **Total Automated Tests** | **180** | **Comprehensive Marketplace Validation** | **100% PASS** |

---

## 📊 Sample Report Format

All audit reports strictly conform to `skills/audit-orchestrator/references/report_schema.json`:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-08T06:15:00Z",
  "schema_version": "1.0.0",
  "target_url": "https://example.com",
  "pages_audited": [
    "https://example.com/",
    "https://example.com/about"
  ],
  "summary": {
    "total_findings": 12,
    "critical_findings": 1,
    "high_findings": 3,
    "medium_findings": 6,
    "low_findings": 2,
    "total_flag_only": 4,
    "total_strengths": 2,
    "overall_health": "fair",
    "category_scores": {
      "DV": 5,
      "FS": 2,
      "EN": 3,
      "ED": 2
    }
  },
  "findings": [
    {
      "id": "DV-03",
      "title": "No valid JSON-LD structured data (Organization expected)",
      "severity": "high",
      "evidence": "Raw HTML contains 0 JSON-LD script blocks.",
      "suggested_action": {
        "summary": "Add Organization JSON-LD to every core page.",
        "priority": "high"
      },
      "pages": [
        "https://example.com/"
      ]
    }
  ],
  "flag_only_items": [],
  "strengths": [],
  "suggested_actions": []
}
```

---

## 🛡️ Operational Guardrails & Compliance

- 🔒 **Recommend-Only**: The marketplace is strictly diagnostic. No script ever alters live site code or database state.
- 🌐 **Read-Only HTTP**: Operates purely via read-only `GET` or `HEAD` requests.
- 🤖 **Respects `robots.txt`**: Evaluates `robots.txt` rules before crawling sub-pages.
- ⚡ **Rate & Bandwidth Safe**: Multi-page crawls are capped via `--max-pages` with sequential request throttles.
- 📦 **Clean Package**: Submission contains zero binary model weights, temporary caches, or untracked state.

---

## 👥 Authors & Acknowledgments

Submitted for **Adobe University Hackathon 2026 — Round 3**.
- **Repository**: [adityagudipati05/adobe-round-3](https://github.com/adityagudipati05/adobe-round-3)
- **Contributor**: [saivasishtamulpuru9-netizen](https://github.com/saivasishtamulpuru9-netizen)
