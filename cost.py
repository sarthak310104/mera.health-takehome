"""Summarise token cost and latency per run folder.

Usage: python cost.py runs/<label> [runs/<label> ...]
"""
import json
import statistics
import sys
from pathlib import Path

# USD per 1M tokens, gemini-3.8-flash standard paid tier. Supplied by the project owner, not looked up here:
# check against Google's current Gemini API pricing page before quoting.
INPUT_PER_M = 0.75
OUTPUT_PER_M = 3.75
NAN = float("nan")


def mean(values):
    return sum(values) / len(values) if values else NAN


def summarize(run: str) -> str:
    reports = list(json.loads((Path(run) / "meta.json").read_text(encoding="utf-8"))["reports"].values())
    ok = [r for r in reports if r["ok"]]
    usage = [r["usage"] for r in ok if r.get("usage")]
    tokens_in = mean([u.get("promptTokenCount", 0) for u in usage])
    tokens_out = mean([u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0) for u in usage])
    cost = (tokens_in * INPUT_PER_M + tokens_out * OUTPUT_PER_M) / 1_000_000
    latency = [r["latency"] for r in ok if r.get("latency") is not None]
    failed = sum(a["error"] is not None for r in reports for a in r["attempts"])
    return (f"{run}: ok {len(ok)}/{len(reports)} | in {tokens_in:.0f} out {tokens_out:.0f} tok "
            f"(from {len(usage)} with usage) | ${cost:.5f}/report ${cost * 10000:.2f}/10k | latency s "
            f"mean {mean(latency):.1f} median {statistics.median(latency) if latency else NAN:.1f} "
            f"max {max(latency, default=NAN):.1f} | failed attempts {failed}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for run in sys.argv[1:]:
        print(summarize(run))
