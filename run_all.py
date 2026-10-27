"""Run extract.py over every file in reports/ with retries; save outputs and run metadata.

Usage: python run_all.py <label>
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ATTEMPTS, RETRY_WAIT, REPORT_WAIT = 6, 30, 5


def parse_usage(stderr: str):
    for line in stderr.splitlines():
        if line.startswith("USAGE "):
            try:
                return json.loads(line[len("USAGE "):])
            except json.JSONDecodeError:
                return None
    return None


def run_one(path: Path, env: dict) -> dict:
    attempts, result = [], {"ok": False, "latency": None, "usage": None, "stdout": ""}
    for n in range(1, ATTEMPTS + 1):
        start = time.perf_counter()
        proc = subprocess.run([sys.executable, "extract.py", str(path)], capture_output=True,
                              encoding="utf-8", errors="replace", env=env)
        latency = time.perf_counter() - start
        if proc.returncode == 0:
            attempts.append({"attempt": n, "error": None})
            result.update(ok=True, latency=round(latency, 2), usage=parse_usage(proc.stderr), stdout=proc.stdout)
            break
        error = (proc.stderr.strip().splitlines() or [f"exit code {proc.returncode}"])[-1]
        attempts.append({"attempt": n, "error": error})
        print(f"  attempt {n}/{ATTEMPTS} failed: {error}")
        if n < ATTEMPTS:
            time.sleep(RETRY_WAIT)
    result["attempts"] = attempts
    return result


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python run_all.py <label>")
    out_dir = Path("runs") / sys.argv[1]
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    reports = sorted(p for p in Path("reports").iterdir() if p.is_file())
    meta = {"model": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"), "reports": {}}
    for i, path in enumerate(reports):
        print(f"[{i + 1}/{len(reports)}] {path.name}")
        result = run_one(path, env)
        if result["ok"]:
            (out_dir / f"{path.stem}.json").write_text(result.pop("stdout"), encoding="utf-8")
            print(f"  ok in {result['latency']}s, usage={result['usage']}")
        else:
            result.pop("stdout")
            print("  FAILED after all attempts")
        meta["reports"][path.name] = result
        if i < len(reports) - 1:
            time.sleep(REPORT_WAIT)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    ok = sum(r["ok"] for r in meta["reports"].values())
    print(f"Done: {ok}/{len(reports)} ok. Wrote {out_dir / 'meta.json'}")


if __name__ == "__main__":
    main()
