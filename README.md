# Adobe University Hackathon 2026 — Round 3
## Brand AI-Readiness Audit — Agent Skill Marketplace

[![Adobe Hackathon](https://img.shields.io/badge/Adobe%20University%20Hackathon-2026%20Round%203-FF0000?style=for-the-badge&logo=adobe)](https://github.com/adityagudipati05/adobe-round-3)
[![Agent Skills Spec](https://img.shields.io/badge/Spec-AgentSkills.io-blue?style=for-the-badge)](https://agentskills.io)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen?style=for-the-badge&logo=python)](https://python.org)
[![Tests Passed](https://img.shields.io/badge/Tests-180%2F180%20Passing-success?style=for-the-badge)](https://github.com/adityagudipati05/adobe-round-3)
[![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

> **Submission for Round 3: Build the Agent Skill Marketplace**  
> *Target Repository:* [adityagudipati05/adobe-round-3](https://github.com/adityagudipati05/adobe-round-3)  
> *Author:* Sai Vasishta ([saivasishtamulpuru9-netizen](https://github.com/saivasishtamulpuru9-netizen))

---

## 📌 Table of Contents
1. [Executive Overview](#-executive-overview)
2. [Marketplace Architecture & Composable Skills](#-marketplace-architecture--composable-skills)
3. [Marketplace Manifest (`marketplace.json`)](#-marketplace-manifest-marketplacejson)
4. [Audit Report Schema](#-audit-report-schema)
5. [Quick Start & Usage](#-quick-start--usage)
6. [Test Suite & Validation](#-test-suite--validation)
7. [Guardrails & Evaluation Rubric Compliance](#-guardrails--evaluation-rubric-compliance)
8. [Directory Structure](#-directory-structure)

---

## 🎯 Executive Overview

Round 3 tests whether reasoning about web visibility can be encoded into reusable, modular **Agent Skills** conforming to the official `agentskills.io` standard. When an AI assistant (such as ChatGPT, Claude, or Perplexity) is asked about a brand, its ability to find, cite, and accurately represent that brand depends on specific technical and structural signals.

This repository implements a complete **Agent Skill Marketplace** that automatically audits any target website for:
1. **Off-Site AI Discoverability**: Why a brand is invisible, ignored, or misquoted by AI search agents (bot blocks, missing JSON-LD, client-side JS rendering locks, uncorroborated facts, brand name collision risks).
2. **On-Site Visitor Engagement**: Why human visitors who arrive fail to engage or convert (friction points, missing breadcrumbs, dynamic stat failures, stale copyright dates, weak call-to-action signals).

The system is **recommend-only** and non-destructive: it performs read-only HTTP GET requests, respects `robots.txt`, operates within a sandbox, and produces a structured, actionable JSON audit report.

---

## 🏗️ Marketplace Architecture & Composable Skills

The marketplace adopts a modular architecture separating concerns across 5 specialized skills tied together by an orchestrator entrypoint.

```mermaid
graph TD
    User([User / AI Agent]) -->|Target URL| Orchestrator["audit-orchestrator (ENTRYPOINT)"]
    Orchestrator -->|1. Fetch & Discover Pages| Fetcher[Crawler / HTML Parser]
    Fetcher -->|2. Per-Page Audit| Skills Pipeline
    
    subgraph "Skills Pipeline"
        DV["crawl-render-audit (DV-01..DV-20)<br/>Discoverability & JS Render"]
        FS["freshness-corroboration (FS-01..FS-06)<br/>Stale Facts & Citations"]
        EN["engagement-audit (EN-01..EN-13)<br/>Visitor Friction & Wayfinding"]
        ED["entity-disambiguation (ED-01..ED-06)<br/>Brand Clarity & Wikidata"]
    end
    
    Skills Pipeline -->|Raw Page Flags & Findings| CascadingEngine[Cascading & Ownership Engine]
    CascadingEngine -->|3. Suppress Duplicates & Apply Gates| Synthesizer[Report Synthesizer]
    Synthesizer -->|4. Merge Multi-page & Escalate Severity| FinalReport["audit_report.json (Fixed Schema)"]
```

### 💬 Skill Matrix Breakdown

| Skill ID | Category | Scope & Responsibilities | Key Checks & Rules |
|---|---|---|---|
| 🎯 `audit-orchestrator` | **Entrypoint** | Orchestrates crawling, coordinates skill execution order, enforces cascading rules, escalates severities, and synthesizes final report. | Composes all skills; escalates findings to `high` when ≥3 pages trigger; suppresses redundant findings across domain boundaries. |
| 🔍 `crawl-render-audit` | **Discoverability** | Inspects crawlability, indexing, JS-render gaps, structured data, canonical tags, `/llms.txt`, and bot blocks. | **DV-01..DV-20**: Bot block detection (`DV-13`), JS rendering reliance (`DV-01`), JSON-LD schema (`DV-03`), canonical tags (`DV-08`), `/llms.txt` presence (`DV-18`). |
| ⏳ `freshness-corroboration` | **Freshness** | Detects stale date claims, date drift between header/footer, numeric listing mismatches, and unverified facts. | **FS-01..FS-06**: Stale copyright/content dates (`FS-01`), inline `[citation needed]` markers (`FS-06`), internal numeric inconsistencies (`FS-02`). |
| 🎯 `engagement-audit` | **Engagement** | Evaluates visitor retention, wayfinding, link hygiene, breadcrumbs, paywall friction, and CTAs. | **EN-01..EN-13**: Gated by cascading rules (`EN-13` if bot-blocked, `EN-11` if noindex). Evaluates dead links (`EN-03`), sticky CTAs (`EN-07`), breadcrumbs (`EN-04`). |
| 🆔 `entity-disambiguation` | **Entity Clarity** | Audits brand identity clarity, name collision risks, Organization schema `sameAs`, and Wikipedia/Wikidata linkage. | **ED-01..ED-06**: Wikidata-backed entities bypass checks. Audits acronym/generic brand collisions (`ED-01`), social profiles (`ED-03`), founding fact ambiguity (`ED-06`). |

---

## 📄 Marketplace Manifest (`marketplace.json`)

The top-level `marketplace.json` defines the marketplace, lists all member skills, and designates `audit-orchestrator` as the sole entrypoint.

```json
{
  "name": "brand-ai-readiness-audit",
  "version": "1.0.0",
  "skills": [
    {
      "id": "audit-orchestrator",
      "path": "skills/audit-orchestrator",
      "entrypoint": true
    },
    {
      "id": "crawl-render-audit",
      "path": "skills/crawl-render-audit"
    },
    {
      "id": "freshness-corroboration",
      "path": "skills/freshness-corroboration"
    },
    {
      "id": "engagement-audit",
      "path": "skills/engagement-audit"
    },
    {
      "id": "entity-disambiguation",
      "path": "skills/entity-disambiguation"
    }
  ]
}
```

---

## 📊 Audit Report Schema

The orchestrator produces a structured JSON report conforming to `references/report_schema.json`.

```json
{
  "site": "example.com",
  "audited_at": "2026-09-08T06:15:00Z",
  "schema_version": "1.0.0",
  "generated_at": "2026-09-08T06:15:00Z",
  "target_url": "https://example.com",
  "pages_audited": [
    "https://example.com/",
    "https://example.com/about"
  ],
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0,
    "critical_findings": 1,
    "high_findings": 2,
    "medium_findings": 3,
    "low_findings": 0,
    "total_flag_only": 2,
    "total_strengths": 3,
    "overall_health": "fair",
    "category_scores": {
      "DV": 3,
      "FS": 1,
      "EN": 1,
      "ED": 1
    }
  },
  "findings": [
    {
      "id": "DV-03",
      "title": "No valid JSON-LD structured data (Organization expected)",
      "severity": "high",
      "evidence": "Raw HTML contains 0 JSON-LD script blocks.",
      "suggested_action": {
        "summary": "Add Organization JSON-LD markup to every core page.",
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

## 🚀 Quick Start & Usage

### Prerequisites
- Python 3.10 or higher
- Required packages: `requests`, `beautifulsoup4`, `lxml`

```bash
# Clone the repository
git clone https://github.com/adityagudipati05/adobe-round-3.git
cd adobe-round-3/brand-ai-readiness-audit

# Install dependencies
pip install requests beautifulsoup4 lxml
```

### Running an Audit

```bash
# Basic single-page audit
python skills/audit-orchestrator/scripts/compose_report.py https://example.com

# Multi-page audit (up to 10 pages) saving output to JSON
python skills/audit-orchestrator/scripts/compose_report.py https://example.com --max-pages 10 --out audit_report.json
```

---

## 🧪 Test Suite & Validation

The codebase includes an extensive suite of **180 offline unit and integration tests** achieving 100% pass rate without requiring active network connectivity.

### Unit & Integration Test Summary

| Test Suite | Command | Total Checks | Scope | Status |
|---|---|---|---|---|
| `smoke_test_dv.py` | `python smoke_test_dv.py` | 33 | Crawl & Render checks (DV-01..DV-20) | ✅ 100% PASS |
| `smoke_test_fs.py` | `python smoke_test_fs.py` | 25 | Freshness & Corroboration (FS-01..FS-06) | ✅ 100% PASS |
| `smoke_test_en.py` | `python smoke_test_en.py` | 27 | Engagement checks & routing gates (EN-01..EN-13) | ✅ 100% PASS |
| `smoke_test_ed.py` | `python smoke_test_ed.py` | 31 | Entity Disambiguation & Wikidata gate (ED-01..ED-06) | ✅ 100% PASS |
| `smoke_test_orchestrator.py` | `python smoke_test_orchestrator.py` | 27 | Full pipeline integration & schema validation | ✅ 100% PASS |
| `test_dv_checks_stdlib.py` | `python test_dv_checks_stdlib.py` | 37 | Pure stdlib fallback and edge-case unit tests | ✅ 100% PASS |
| **Total Test Suite** | **6 Test Drivers** | **180 Checks** | **Complete Code Base Coverage** | **✅ ALL PASS** |

To run all unit tests in a single command:
```bash
python smoke_test_dv.py; python smoke_test_fs.py; python smoke_test_en.py; python smoke_test_ed.py; python smoke_test_orchestrator.py; python test_dv_checks_stdlib.py
```

### Live Validation Reports
The repository contains validated live audit outputs in `brand-ai-readiness-audit/reports/`:
- `reports/wikipedia_tim.json`: Wikidata `sameAs` resolution and inline corroboration markers.
- `reports/kisansuvidha.json`: Real-world JS-render gap (`DV-01` critical) routing `EN` to `EN-13` (`not_assessed`).
- `reports/hackernews.json`: Minimalist web app missing structured metadata and entity markers.
- `reports/python_org.json`: Metadata checks, stale copyright evaluation, and entity disambiguation.
- `reports/bot_block_dv13_en12.json`: Bot-block/WAF challenge (`DV-13`) routing `EN` to `EN-12` (`not_assessed`).
- `reports/noindex_en11.json`: Intentionally excluded pages (`noindex`) routing `EN` to `EN-11` (`not_applicable`).

---

## 🛡️ Guardrails & Evaluation Rubric Compliance

| Rubric Criterion | Implementation Strategy | Verified Conformance |
|---|---|---|
| **Detection Accuracy** | Deterministic heuristics for off-site discoverability & on-site engagement with zero false positives. | ✅ 180 unit test assertions verify accurate trigger conditions. |
| **Suggested-Action Quality** | Specific, mechanism-sound fixes categorized by priority (`critical`, `high`, `medium`, `low`). | ✅ Proactive improvements generated even when no explicit error occurs. |
| **Output Design** | Strict JSON schema adhering to contest standards (`site`, `audited_at`, `summary`, `findings`). | ✅ Verified via `smoke_test_orchestrator.py` against `report_schema.json`. |
| **Skill & Engineering Hygiene** | Each skill directory contains a valid `SKILL.md` per `agentskills.io` specification. | ✅ Manifest `marketplace.json` correctly resolves entrypoint. |
| **Marketplace Composition** | Genuine separation of concerns with cascading rules suppressing cross-skill duplicate findings. | ✅ `DV-03` suppresses redundant `ED-02`; bot-blocks gate downstream checks cleanly. |
| **Scope & Safety** | Read-only GET operations, sandbox execution, respects `robots.txt`, submission size < 50MB. | ✅ Archive size is **0.125 MB** (well below 50 MB limit); runtime < 5 minutes. |

---

## 📂 Directory Structure

```
adobe-round-3/
├── README.md                                      # Main repository documentation (this file)
├── brand-ai-readiness-audit-submission.zip        # Official submission zip archive (< 50MB)
└── brand-ai-readiness-audit/                      # Marketplace root directory
    ├── README.md                                  # Technical package documentation
    ├── marketplace.json                           # Top-level marketplace manifest
    ├── run_phase7_special_cases.py                # Verification harness for special edge cases
    ├── smoke_test_dv.py                           # Discoverability test suite (33 checks)
    ├── smoke_test_fs.py                           # Freshness test suite (25 checks)
    ├── smoke_test_en.py                           # Engagement test suite (27 checks)
    ├── smoke_test_ed.py                           # Entity disambiguation test suite (31 checks)
    ├── smoke_test_orchestrator.py                 # Orchestration test suite (27 checks)
    ├── test_dv_checks_stdlib.py                   # Pure stdlib unit test suite (37 checks)
    ├── reports/                                   # Live site and special case audit reports
    │   ├── bot_block_dv13_en12.json
    │   ├── hackernews.json
    │   ├── kisansuvidha.json
    │   ├── noindex_en11.json
    │   ├── python_org.json
    │   ├── tgbie_bot_block.json
    │   └── wikipedia_tim.json
    └── skills/                                    # Modular Agent Skills
        ├── audit-orchestrator/                    # [ENTRYPOINT] Composes skills & emits report
        │   ├── SKILL.md                           # Skill spec & instructions
        │   ├── references/
        │   │   ├── cascading_rules.md
        │   │   └── report_schema.json
        │   └── scripts/
        │       └── compose_report.py              # Main execution script
        ├── crawl-render-audit/                    # Discoverability & JS render skill (DV-01..DV-20)
        │   ├── SKILL.md
        │   ├── references/
        │   │   └── dv_checklist.md
        │   └── scripts/
        │       ├── checks_dv.py
        │       └── fetch_page.py
        ├── freshness-corroboration/               # Freshness & date claims skill (FS-01..FS-06)
        │   ├── SKILL.md
        │   ├── references/
        │   │   └── fs_checklist.md
        │   └── scripts/
        │       └── checks_fs.py
        ├── engagement-audit/                      # Visitor retention & friction skill (EN-01..EN-13)
        │   ├── SKILL.md
        │   ├── references/
        │   │   └── en_checklist.md
        │   └── scripts/
        │       └── checks_en.py
        └── entity-disambiguation/                 # Identity clarity & Wikidata skill (ED-01..ED-06)
            ├── SKILL.md
            ├── references/
            │   └── ed_checklist.md
            └── scripts/
                └── checks_ed.py
```

---

## 📜 License

This project is submitted under the **MIT License**. See `LICENSE` for details.
