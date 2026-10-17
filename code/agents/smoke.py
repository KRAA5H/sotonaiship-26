"""Live smoke test: real DeepSeek calls (thinking off) through the whole agent workflow.

Needs DEEPSEEK_API_KEY (root .env). Uses a temporary database and pin store, so
the demo data is never touched. Prints each turn's reply, which agents ran and
how long each took, then the tokens, latency and cost from the usage log.

  python code/agents/smoke.py

Prices are DeepSeek's published deepseek-flash rates, read from
https://api-docs.deepseek.com/quick_start/pricing on 2026-10-17 (USD per
million tokens, peak hours, the worst case): input $0.30 (cache miss), $0.006
(cache hit), output $1.20.
"""

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

TMP = Path(tempfile.mkdtemp(prefix="kerbside-smoke-"))
os.environ["DB_PATH"] = str(TMP / "kerbside.db")
os.environ["SOTONFIX_DB"] = str(TMP / "pin.db")
os.environ["LLM_USAGE_LOG"] = str(TMP / "usage.jsonl")

import llm  # noqa: E402
import reports_db  # noqa: E402
from agents import ORCHESTRATOR, Turn  # noqa: E402

PRICE_IN, PRICE_HIT, PRICE_OUT = 0.30, 0.006, 1.20

SCRIPT = [
    ("+440000000001", "massive pothole outside 12 lawn road, nearly burst my tyre"),
    ("+440000000002", "someone has dumped a mattress and bags of rubbish"),
    ("+440000000002", "portswood rd"),                       # the follow-up: no model call
    ("+440000000003", "racist graffiti on the wall by the bus stop on bevois valley road"),
    ("+440000000004", "my neighbour plays really loud music every night"),
    ("+440000000005", "my bin wasn't collected today"),
    ("+440000000006", "how long does a pothole take to fix?"),
    ("+440000000007", "pothole on the M27 near junction 5"),
    ("+440000000008", "broken glass all over the cycle path on shirley high street"),
    ("+440000000009", "lawn road"),                          # a fragment: never "outside Southampton"
]


def main():
    if not (os.getenv("DEEPSEEK_API_KEY") or "").strip():
        print("No DEEPSEEK_API_KEY: put it in the root .env and run again.")
        return 1
    reports_db.init_db()
    print(f"model {llm.DS_MODEL}, thinking off, temp db {TMP}\n")
    totals = []
    for sender, text in SCRIPT:
        started = time.perf_counter()
        outcome = ORCHESTRATOR.handle(Turn(sender=sender, text=text, chat=sender,
                                           link_base="https://kerbside.example"))
        seconds = time.perf_counter() - started
        totals.append(seconds)
        print(f"> {text}")
        print(f"  {seconds:.2f}s  " + " | ".join(f"{s['agent']} {s['ms']}ms" for s in outcome.trace))
        print("  " + (outcome.reply or "(silence)").replace("\n", "\n  "))
        print()

    lines = [json.loads(line) for line in Path(os.environ["LLM_USAGE_LOG"]).read_text(encoding="utf-8").splitlines()]
    ok = [line for line in lines if line["status"] == 200]
    cost = 0.0
    for line in ok:
        hit = line.get("cache_hit_tokens") or 0
        miss = (line.get("prompt_tokens") or 0) - hit
        cost += (miss * PRICE_IN + hit * PRICE_HIT + (line.get("completion_tokens") or 0) * PRICE_OUT) / 1e6
    by_purpose = {}
    for line in ok:
        by_purpose.setdefault(line["purpose"], []).append(line["ms"])
    print(f"turns: {len(totals)}, median {statistics.median(totals):.2f}s, slowest {max(totals):.2f}s")
    for purpose, values in sorted(by_purpose.items()):
        print(f"  {purpose:7} {len(values)} calls, median {statistics.median(values)} ms")
    print(f"model calls: {len(lines)} ({len(ok)} answered), thinking on: {sum(1 for l in lines if l['thinking'])}")
    print(f"cost: ${cost:.5f} for {len(totals)} turns, ${cost / len(totals):.5f} per turn (peak prices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
