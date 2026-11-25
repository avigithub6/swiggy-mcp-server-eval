import asyncio
import json
import sys
import time
from pathlib import Path
import numpy as np

# Allow importing from src/
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from database import reset_db
from mcp_client import run_agent_query

DATASET_PATH = Path(__file__).parent / "dataset_50.json"
REPORT_PATH = ROOT_DIR / "eval_report.txt"
METRICS_JSON_PATH = ROOT_DIR / "eval_metrics.json"
ACCURACY_THRESHOLD = 0.80  # 80% CI/CD Quality Gate


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

    print(f"🚀 Starting 50-Question MCP Evaluation Benchmark (Threshold: {ACCURACY_THRESHOLD:.0%})...\n")

    for item in dataset:
        # Reset SQLite state before every query for 100% test isolation
        reset_db()

        q_id = item["id"]
        category = item["category"]
        question = item["question"]
        expected = item["expected_tools"]

        # Small pacing delay to stay comfortably within Groq free-tier RPM limits
        await asyncio.sleep(1.5)

        result = await run_agent_query(question)
        actual = result["tools_called"]
        errors = result["tool_errors"]
        latencies.append(result["latency_ms"])
        total_tokens += result["total_tokens"]

        if errors:
            tool_failed_count += 1
            status = "❌ TOOL FAILED"
            failed_details.append(
                f"[Q{q_id} | {category}] {status}\n"
                f"   Query: {question}\n"
                f"   Expected: {expected} | Actual: {actual}\n"
                f"   Error: {errors[0]}"
            )
        elif actual != expected:
            wrong_tool_count += 1
            status = "⚠️ WRONG TOOL"
            failed_details.append(
                f"[Q{q_id} | {category}] {status}\n"
                f"   Query: {question}\n"
                f"   Expected: {expected} | Actual: {actual}"
            )
        else:
            correct_count += 1
            status = "✅ PASS"

        print(f"Q{q_id:02d} [{category:9s}] -> {status} | Expected: {expected} | Got: {actual} ({result['latency_ms']}ms)")

    accuracy = correct_count / total
    avg_latency = round(float(np.mean(latencies)), 2)
    p95_latency = round(float(np.percentile(latencies, 95)), 2)

    summary_lines = [
        "====================================================",
        "       SWIGGY MCP SERVER EVALUATION REPORT          ",
        "====================================================",
        f"Total Questions   : {total}",
        f"✅ Correct Tool   : {correct_count}/{total} ({accuracy:.1%})",
        f"⚠️ Wrong Tool     : {wrong_tool_count}/{total} ({wrong_tool_count/total:.1%})",
        f"❌ Tool Failed    : {tool_failed_count}/{total} ({tool_failed_count/total:.1%})",
        f"⏱️ Avg Latency    : {avg_latency} ms",
        f"⚡ P95 Latency    : {p95_latency} ms",
        f"🪙 Total Tokens   : {total_tokens} (Cost: $0.00 - Groq Free Tier)",
        f"🎯 Quality Gate   : {'PASSED ✅' if accuracy >= ACCURACY_THRESHOLD else 'FAILED 🚨'} (Min: {ACCURACY_THRESHOLD:.0%})",
        "====================================================",
    ]

    if failed_details:
        summary_lines.append("\n--- ROOT CAUSE FAILURE LOG (Top Failures) ---")
        summary_lines.extend(failed_details[:15])

    report_text = "\n".join(summary_lines)
    print("\n" + report_text)

    # Save report for GitHub Actions Email Alert
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Save structured metrics JSON
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
    with open(METRICS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    if accuracy < ACCURACY_THRESHOLD:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_evaluation())