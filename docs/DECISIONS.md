# Architecture Decision Records (ADR) & Engineering Trade-offs

This document explains the "Why" behind the architectural choices, trade-offs, and debugging iterations in the **Swiggy MCP Server & Automated Evaluation Pipeline**.

---

## 1. Deterministic Rule-Based Evaluation vs. LLM-as-a-Judge
* **Decision:** Used deterministic Python assertions (`actual_tools == expected_tools`) and runtime error checks (`is_error`) rather than LLM-as-a-Judge.
* **Rationale:** Tool routing is an exact-match decision. Deterministic evaluation provides **0% grader hallucination**, executes in **<1ms**, and incurs **$0.00 extra token cost** inside CI/CD pipelines.
* **Trade-off:** Requires maintaining an explicit golden dataset (`evals/dataset_50.json`) with exact expected tool sequences, rather than grading open-ended prose quality.

---

## 2. Hybrid Storage: SQLite (ACID State) + ChromaDB (Semantic RAG)
* **Decision:** Combined a transactional SQLite database (`swiggy.db`) for orders/coupons with a local persistent vector store (`ChromaDB`) for menu and grocery search.
* **Rationale:**
  * **SQLite:** Order cancellations and refunds mutate state and require transactional integrity (`reset_db()` also guarantees test isolation between benchmark runs).
  * **ChromaDB:** Keyword `LIKE` queries fail when users search by intent (e.g., *"something light for an upset stomach"* or *"ingredients to make masala chai"*). Local embeddings (`all-MiniLM-L6-v2`) enable semantic retrieval with zero external embedding API cost.
* **Trade-off:** Adds local disk persistence (`chroma_db/`), which is excluded from Git via `.gitignore` and rebuilt deterministically on server boot.

---

## 3. Model Selection & Cost/Latency Trade-off (`openai/gpt-oss-20b` on Groq)
* **Decision:** Standardized on a lightweight 20B routing model via Groq's OpenAI-compatible inference endpoint instead of a massive 120B+ flagship model.
* **Rationale:** Running 50 agentic evaluations on every `git push` requires fast inference and zero/low CI cost. Furthermore, a 20B model exposes weak tool docstrings that a 120B model might silently compensate for—making our evaluation sensitive to schema quality.
* **Observed Trade-off:** Free-tier rate limits (`HTTP 429` with automatic backoff) introduced tail-latency spikes (`P95: 13.8s` in `v2` vs `7.5s` in `v1`), and richer `v2` docstrings increased total benchmark token consumption from **68,988** to **111,992 tokens** (+62% prompt overhead) in exchange for **+8.0% accuracy**.

---

## 4. Root-Cause Failure Analysis (`v1` Baseline → `v2` Optimized)
1. **Redundant Sequential Tool Calls (`Q16, Q18, Q19, Q20, Q40`):**
   * *Failure:* On multi-item queries like *"milk and brown bread"*, the `v1` agent invoked `search_instamart_items` 2–3 times sequentially, multiplying latency and token cost.
   * *Fix:* Added an explicit batching rule in tool docstrings (*"Combine multiple items into ONE single combined query"*), eliminating all redundant multi-item calls.
2. **Under-Triggering on Implicit Cooking Intent (`Q28`):**
   * *Failure:* On *"ingredients to make masala chai at home"*, `v1` returned `[]` (no tool called).
   * *Fix:* Clarified `WHEN TO USE` boundaries in `search_instamart_items` to explicitly cover raw cooking/brewing ingredients.
3. **Safety Guardrail Behavior (`Q50`):**
   * *Observation:* On *"Cancel order SWG-101"* (without user confirmation), `v1` blindly passed `confirm=True` and cancelled the order, whereas `v2` safely refrained (`[]`) to ask for confirmation first.

---

## 5. Closed-Loop CI/CD Quality Gate
* **Decision:** Gated deployment (`deploy-mcp`) behind an 80% accuracy threshold (`evaluate-mcp`) in GitHub Actions, with root-cause email diagnostics on failure.
* **Rationale:** Prevents silent prompt/schema regressions from reaching production while delivering actionable failure logs directly to the developer's inbox.