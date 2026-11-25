import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from fpdf import FPDF

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from database import reset_db
from mcp_client import run_agent_query

DATASET_PATH = Path(__file__).parent / "dataset_50.json"
REPORT_TXT_PATH = ROOT_DIR / "eval_report.txt"
REPORT_PDF_PATH = ROOT_DIR / "eval_report.pdf"
METRICS_JSON_PATH = ROOT_DIR / "eval_metrics.json"
ACCURACY_THRESHOLD = 0.80


def _clean_ascii(text: str) -> str:
    """Ensure clean latin-1 compatibility for standard PDF fonts."""
    return text.encode("latin-1", "replace").decode("latin-1")


def generate_pdf_report(metrics: dict, failed_details: list[str], output_path: Path):
    """Generate a clean, professional PDF evaluation report for CI/CD email attachment."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header Banner
    passed = metrics["passed"]
    pdf.set_fill_color(24, 34, 56)
    pdf.rect(0, 0, 210, 32, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, "Swiggy MCP Server - CI/CD Evaluation Report", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(0, 6, f"Generated: {timestamp} | Benchmark: 50 Golden Queries", ln=True)

    # Quality Gate Status Banner
    pdf.ln(12)
    if passed:
        pdf.set_fill_color(220, 252, 231)
        pdf.set_text_color(22, 101, 52)
        status_text = f"QUALITY GATE: PASSED ({metrics['accuracy_pct']}% >= 80.0% Threshold) - CD Triggered"
    else:
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(153, 27, 27)
        status_text = f"QUALITY GATE: FAILED ({metrics['accuracy_pct']}% < 80.0% Threshold) - Deployment Blocked"

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 10, f"  {status_text}", ln=True, fill=True)
    pdf.ln(5)

    # Metrics Summary Table
    pdf.set_text_color(20, 20, 20)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "1. Benchmark Performance Metrics", ln=True)

    rows = [
        ("Total Benchmark Queries", f"{metrics['total']}"),
        ("Correct Tool Selection", f"{metrics['correct']} / {metrics['total']} ({metrics['accuracy_pct']}%)"),
        ("Wrong / Redundant Tool Calls", f"{metrics['wrong_tool']} / {metrics['total']}"),
        ("Runtime / API Tool Failures", f"{metrics['tool_failed']} / {metrics['total']}"),
        ("Average End-to-End Latency", f"{metrics['avg_latency_ms']} ms"),
        ("P95 End-to-End Latency", f"{metrics['p95_latency_ms']} ms"),
        ("Total Tokens Consumed", f"{metrics['total_tokens']:,} tokens ($0.00 Free Tier)"),
    ]

    pdf.set_font("Helvetica", "", 10)
    for label, val in rows:
        pdf.set_fill_color(245, 247, 250)
        pdf.cell(95, 8, f"  {label}", border=1, fill=True)
        pdf.cell(95, 8, f"  {val}", border=1, ln=True)

    # Root-Cause Failure Breakdown
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "2. Root-Cause Diagnostic Log (Failed Queries)", ln=True)
    pdf.set_font("Helvetica", "", 9)

    if not failed_details:
        pdf.cell(0, 8, "No failures detected! All 50 queries passed.", ln=True)
    else:
        for entry in failed_details[:20]:
            pdf.multi_cell(0, 5, _clean_ascii(entry))
            pdf.ln(2)

    pdf.output(str(output_path))


async def run_evaluation():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    total = len(dataset)
    correct_count = 0
    wrong_tool_count = 0
    tool_failed_count = 0

    latencies = []
    total_tokens = 0
    failed_details = []

    print(f"Starting 50-Question MCP Evaluation Benchmark (Threshold: {ACCURACY_THRESHOLD:.0%})...\n")

    for item in dataset:
        reset_db()
        q_id = item["id"]
        category = item["category"]
        question = item["question"]
        expected = item["expected_tools"]

        await asyncio.sleep(1.5)

        result = await run_agent_query(question)
        actual = result["tools_called"]
        errors = result["tool_errors"]
        latencies.append(result["latency_ms"])
        total_tokens += result["total_tokens"]

        if errors:
            tool_failed_count += 1
            status = "TOOL FAILED"
            failed_details.append(
                f"[Q{q_id} | {category}] {status} | Query: {question}\n"
                f"Expected: {expected} | Actual: {actual} | Error: {errors[0][:140]}"
            )
        elif actual != expected:
            wrong_tool_count += 1
            status = "WRONG TOOL"
            failed_details.append(
                f"[Q{q_id} | {category}] {status} | Query: {question}\n"
                f"Expected: {expected} | Actual: {actual}"
            )
        else:
            correct_count += 1
            status = "PASS"

        print(f"Q{q_id:02d} [{category:9s}] -> {status} | Expected: {expected} | Got: {actual}")

    accuracy = correct_count / total
    avg_latency = round(float(np.mean(latencies)), 2)
    p95_latency = round(float(np.percentile(latencies, 95)), 2)

    metrics_data = {
        "total": total,
        "correct": correct_count,
        "wrong_tool": wrong_tool_count,
        "tool_failed": tool_failed_count,
        "accuracy_pct": round(accuracy * 100, 1),
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "total_tokens": total_tokens,
        "passed": accuracy >= ACCURACY_THRESHOLD,
    }

    # Generate PDF Report + JSON + Short Email Body
    generate_pdf_report(metrics_data, failed_details, REPORT_PDF_PATH)

    short_summary = (
        f"Swiggy MCP Server Evaluation Summary\n"
        f"Status: {'PASSED' if metrics_data['passed'] else 'FAILED'} ({metrics_data['accuracy_pct']}% Accuracy)\n"
        f"Correct: {correct_count}/{total} | Wrong Tool: {wrong_tool_count} | Tool Failed: {tool_failed_count}\n"
        f"Avg Latency: {avg_latency} ms | P95 Latency: {p95_latency} ms\n\n"
        f"Please find the full formatted diagnostic PDF report attached (eval_report.pdf)."
    )
    with open(REPORT_TXT_PATH, "w", encoding="utf-8") as f:
        f.write(short_summary)

    with open(METRICS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    print("\n" + short_summary)

    if accuracy < ACCURACY_THRESHOLD:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_evaluation())