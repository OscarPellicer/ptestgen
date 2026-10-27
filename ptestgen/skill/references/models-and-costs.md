# Models and costs

Measured in one course (Health Data Analytics, Universitat de València, 2026): 21 lab notebooks and 27 three-question handwritten exams per session. Opus 5.5 at medium effort is the reference; "difference" is the mean absolute difference from it. These are small samples: tell the teacher so, and let them choose.

| Task | Option | Cost per session | Difference |
|---|---|---:|---|
| Exam headers (model, ID, name) | **Opus 5.5, low effort (default)** | ~$0.002/exam | fewest misreads |
| | Sonnet 5.5 / Haiku 5.5 | less | misread more names and IDs |
| | TrOCR (local, free) | $0 | unreliable |
| Open answers (27 × 3) | **Opus 5.5, medium, crops at 900 px (default)** | ~$1.30 | 0.02 / 1 |
| | Sonnet 5.5, high | ~$0.61 | 0.04 / 1 |
| | Haiku 5.5 | ~$0.05 | 0.06 / 1 |
| Lab notebooks (21) | **Opus 5.5, medium, compacted (default)** | ~$3.40 | 0.22 / 10 (= rerun noise) |
| | Opus 5.5, low | ~$3.20 | 0.36 / 10 |
| | Sonnet 5.5, high | ~$1.70 | 0.20 / 10 |
| | Sonnet 5.5, medium | ~$1.45 | 0.94 / 10: skims, avoid |
| | Haiku 5.5 | ~$0.11 | 0.49 / 10, more lenient |

List prices (USD per million input / output tokens): Opus 5.5 $4 / $20, Sonnet 5.5 $2 / $10, Haiku 5.5 $0.10 / $0.50. `ptestgen course metrics` computes the real cost of a step from its `llm_calls.jsonl` (override prices with `prices:` in the course record).

Recommendation to present:
- **Correctness first (default):** Opus 5.5 medium for grading, low for headers. About $5 per session of this size.
- **Half the cost, similar grades:** Sonnet 5.5 at **high** effort (never medium).
- **Cheapest:** Haiku 5.5 for open exam answers; review its grades.

Estimate before running: open answers ≈ $0.016 per answer with Opus medium; notebooks ≈ $0.16 per notebook (depends on its length: the prompt size is printed per submission).

Effort: `low | medium | high` (`--effort`, `--id-reader-effort`). Other providers: any OpenRouter id (`--model google/gemini-3.8-flash`) with `OPENROUTER_API_KEY`; not measured here.
