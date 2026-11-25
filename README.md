# Swiggy MCP Server & Automated Evaluation Pipeline

A production-style **Model Context Protocol (MCP)** server (built on MCP Python SDK v2) for Swiggy Food & Instamart workflows, paired with a **50-question deterministic evaluation engine** and a **closed-loop GitHub Actions CI/CD quality gate** with automated PDF diagnostic reporting.

---

## Project Overview

LLM agents connected to external tools often fail silently when tool descriptions overlap (e.g., ordering raw groceries vs. cooked meals, or cancelling an active order vs. refunding a delivered one).

This project solves that problem through **Eval-Driven MCP Development**:
1. **Stateful MCP Server (`src/mcp_server.py`):** Exposes 8 domain tools backed by **SQLite** (transactional order/coupon state) and **ChromaDB** (semantic RAG search over dishes and groceries).
2. **Custom MCP Client (`src/mcp_client.py`):** Orchestrates multi-step tool chaining over `stdio` transport with structured logging, latency profiling, and token observability.
3. **50-Question Golden Benchmark (`evals/evaluate.py`):** Evaluates direct, ambiguous, multi-step, and edge-case queries with full SQLite state isolation between tests and generates a formatted PDF diagnostic report (`eval_report.pdf`).
4. **Automated CI/CD Quality Gate (`.github/workflows/mcp-cicd.yml`):** Blocks deployment and emails the formatted PDF root-cause report to the developer if tool-selection accuracy drops below **80%**.

---

## System Architecture

```mermaid
flowchart TD
    Dev[Developer Git Push] --> CI[GitHub Actions CI: 50-Question Eval]
    CI --> Client[MCP Client Orchestrator]
    Client <-->|stdio / JSON-RPC| Server[Swiggy MCP Server - SDK v2]

    subgraph Stateful Backend
        Server --> VectorDB[(ChromaDB: Semantic Menu & Grocery RAG)]
        Server --> SQL[(SQLite: Orders, Status & Coupons)]
    end

    Client --> Telemetry[Telemetry Engine: Accuracy, P95 Latency & Tokens]
    Telemetry --> PDF[Generate Formatted PDF Diagnostic Report]
    PDF --> Gate{Accuracy >= 80%?}

    Gate -- No (Fail) --> FailMail[Email Root-Cause PDF Report to Developer]
    FailMail --> Dev

    Gate -- Yes (Pass) --> PassMail[Email Passed PDF Report]
    PassMail --> CD[GitHub Actions CD: Deploy Verified Server]
```

---

## Verified Benchmark Results (Live CI/CD & Local Runs)

Evaluated across **50 realistic Swiggy queries** (`25 Direct`, `15 Ambiguous`, `5 Multi-Step Chained`, `5 Edge Cases`):

| Metric | `v1` Baseline (Minimal Docstrings) | CI Incident (`120B` Rate-Limited) | `v2` Production CI (`openai/gpt-oss-20b`) | Net Impact (`v1` → `v2`) |
| :--- | :--- | :--- | :--- | :--- |
| **Correct Tool Accuracy** | 42 / 50 (**84.0%**) | 3 / 50 (**6.0%**) | 46 / 50 (**92.0%**) | **+8.0% Accuracy** |
| **Wrong / Redundant Tool Calls** | 8 / 50 (**16.0%**) | 1 / 50 (**2.0%**) | 4 / 50 (**8.0%**) | **-50% Error Rate** |
| **Runtime / API Tool Failures** | 0 / 50 (**0.0%**) | 46 / 50 (**92.0%** - HTTP 429) | 0 / 50 (**0.0%**) | **100% Reliable** |
| **Avg End-to-End Latency** | 4,683.06 ms | 5,934.88 ms | **6,758.89 ms** | Includes full MCP + RAG loop |
| **P95 Latency** | 7,510.47 ms | 41,264.77 ms | **16,319.86 ms** | Includes free-tier backoff |
| **Total Tokens (50 Queries)** | 68,988 tokens | 9,271 tokens (aborted) | **115,095 tokens** | Richer schema boundaries |
| **CI/CD Cost per Run** | **\$0.00** | **\$0.00** | **\$0.00** | Groq Free Tier |
| **Quality Gate Status (≥80%)** | PASSED | **FAILED 🚨 (CD Blocked)** | **PASSED ✅ (CD Triggered)** | Automated Protection |

---

## Repository Structure

```text
swiggy-mcp-server-eval/
├── .github/workflows/
│   └── mcp-cicd.yml          # Closed-loop CI/CD pipeline + PDF email alerts
├── src/
│   ├── database.py           # SQLite transactional database + test isolation reset
│   ├── vector_store.py       # ChromaDB semantic search for Food & Instamart
│   ├── mcp_server.py         # 8 Swiggy MCP tools with Pydantic & safety guardrails
│   └── mcp_client.py         # Async MCP client with multi-step tool chaining
├── evals/
│   ├── dataset_50.json       # 50-question golden evaluation benchmark
│   └── evaluate.py           # Deterministic evaluator, PDF report generator & gate
├── docs/
│   └── DECISIONS.md          # Architectural trade-offs & root-cause failure log
└── requirements.txt
```

---

## Quickstart (Run Locally)

```bash
# 1. Clone & activate virtual environment
git clone https://github.com
cd swiggy-mcp-server-eval
python -m venv venv
venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Groq API key to .env
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Run the 50-question evaluation benchmark (generates eval_report.pdf & eval_metrics.json)
python evals/evaluate.py
```

---

## Technical Rationale & Trade-offs

See [`docs/DECISIONS.md`](docs/DECISIONS.md) for detailed architectural decisions, model selection rationale, and root-cause debugging logs.
