"""Live check of fact-grounded answers against real questions.

Costs a few tenths of a penny per question. Not part of the unit suite.

  python code/eval/run_rag.py
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import rag  # noqa: E402

CASES = HERE / "rag_cases.json"
REFUSALS = [
    "what is the meaning of life",
    "how do I get a parking permit",
]


def main():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    hits = 0
    started = time.time()
    for case in cases:
        text, cited = rag.answer(case["question"])
        topics = [fact["topic"].lower() for fact in cited]
        wanted = case["expected_topic"].lower()
        hit = any(wanted in topic for topic in topics)
        hits += hit
        mark = "PASS" if hit else "MISS"
        print(f"[{mark}] {case['question'][:56]:<58} -> {', '.join(t['topic'] for t in cited) or 'none'}")
        if text:
            print("        " + text.replace("\n", " | ")[:190])
    print(f"\nanswers citing the expected fact: {hits}/{len(cases)} "
          f"in {time.time() - started:.1f}s")

    print("\nRefusals, where no checked fact answers the question:")
    refused = 0
    for question in REFUSALS:
        text, cited = rag.answer(question)
        ok = not text and not cited
        refused += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {question}: {text.replace(chr(10), ' | ')[:160] or 'no answer'}")
    print(f"refused cleanly: {refused}/{len(REFUSALS)}")
    return 0 if hits == len(cases) and refused == len(REFUSALS) else 1


if __name__ == "__main__":
    sys.exit(main())
