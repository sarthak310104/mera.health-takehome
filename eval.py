"""Score extraction predictions against gold. No API calls.

Usage: python eval.py runs/<label>

Optional gold_corrections.json: {"<stem>": {"<gold test_name>": {"value": ..., "unit": ..., "reference_range": ...}}}
overrides those fields of the named gold rows; scores are then printed for original and corrected gold.
"""
import difflib
import json
import re
import sys
from pathlib import Path

FIELDS = ("value", "unit", "reference_range")


def norm(text) -> str:
    return " ".join(re.sub(r"[^\w\s]", "", str(text).lower()).split())


def abbrs(name) -> list[str]:
    return [norm(a) for a in re.findall(r"\(([^)]*)\)", str(name))]


def similarity(a, b) -> float:
    na, nb = norm(a), norm(b)
    if na == nb or (na and na in abbrs(b)) or (nb and nb in abbrs(a)):
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def match_rows(gold, pred):
    """One-to-one matching on name only, best similarity first. Returns {gold_idx: pred_idx}."""
    pairs = sorted(((similarity(g["test_name"], p["test_name"]), gi, pi)
                    for gi, g in enumerate(gold) for pi, p in enumerate(pred)), key=lambda t: (-t[0], t[1], t[2]))
    matched, used = {}, set()
    for sim, gi, pi in pairs:
        if sim >= 0.8 and gi not in matched and pi not in used:
            matched[gi] = pi
            used.add(pi)
    return matched


def number(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def same(field, g, p) -> bool:
    if g is None or p is None:
        return g is None and p is None
    if field == "value":
        gn, pn = number(g), number(p)
        if gn is not None and pn is not None:
            return gn == pn
        return " ".join(str(g).lower().split()) == " ".join(str(p).lower().split())
    if field == "unit":
        fix = lambda u: str(u).lower().replace("µ", "u").replace("μ", "u").replace(" ", "")
        return fix(g) == fix(p)
    fix = lambda r: re.sub(r"[,\s]", "", str(r))
    return fix(g) == fix(p)


def score(gold, pred):
    c = dict.fromkeys(("gold", "pred", "matched", "value_ok", "unit_ok", "range_ok", "full", "invented",
                       "wrong_value", "extra"), 0)
    c["gold"], c["pred"] = len(gold), len(pred)
    matched, issues = match_rows(gold, pred), []
    for gi, pi in matched.items():
        g, p = gold[gi], pred[pi]
        ok = {f: same(f, g.get(f), p.get(f)) for f in FIELDS}
        c["matched"] += 1
        c["value_ok"] += ok["value"]
        c["unit_ok"] += ok["unit"]
        c["range_ok"] += ok["reference_range"]
        c["full"] += all(ok.values())
        c["wrong_value"] += not ok["value"]
        c["invented"] += g.get("reference_range") is None and p.get("reference_range") is not None
        issues += [(g["test_name"], f, g.get(f), p.get(f)) for f in FIELDS if not ok[f]]
    for gi, g in enumerate(gold):
        if gi not in matched:
            issues.append((g["test_name"], "row", "in gold", "missing from prediction"))
    for pi, p in enumerate(pred):
        if pi not in set(matched.values()):
            c["extra"] += 1
            issues.append((p["test_name"], "row", "not in gold", "extra in prediction"))
    return c, issues


def rate(a, b):
    return a / b if b else None


def summarize(c):
    c = dict(c, critical=c["wrong_value"] + c["extra"])
    c.update(recall=rate(c["matched"], c["gold"]), precision=rate(c["matched"], c["pred"]),
             value_acc=rate(c["value_ok"], c["matched"]), unit_acc=rate(c["unit_ok"], c["matched"]),
             range_acc=rate(c["range_ok"], c["matched"]), full_acc=rate(c["full"], c["gold"]))
    return c


def evaluate(golds, preds):
    per, issues, total = {}, [], {}
    for stem, gold in golds.items():
        c, found = score(gold, preds.get(stem) or [])
        per[stem] = summarize(c)
        issues += [(stem, *i) for i in found]
        for k, v in c.items():
            total[k] = total.get(k, 0) + v
    return {"reports": per, "totals": summarize(total),
            "mismatches": [dict(zip(("report", "test", "field", "gold", "predicted"), i)) for i in issues]}


def pct(x):
    return "  -  " if x is None else f"{x * 100:5.1f}"


def show(title, result):
    print(f"\n== {title} ==")
    print(f"{'report':<12}{'gold':>5}{'pred':>5}{'recall':>7}{'prec':>7}{'value':>7}{'unit':>7}{'range':>7}"
          f"{'full':>7}{'invent':>7}{'critic':>7}")
    for name, r in [*result["reports"].items(), ("TOTAL", result["totals"])]:
        print(f"{name:<12}{r['gold']:>5}{r['pred']:>5}{pct(r['recall']):>7}{pct(r['precision']):>7}"
              f"{pct(r['value_acc']):>7}{pct(r['unit_acc']):>7}{pct(r['range_acc']):>7}{pct(r['full_acc']):>7}"
              f"{r['invented']:>7}{r['critical']:>7}")
    print(f"critical = wrong values ({result['totals']['wrong_value']}) + unmatched predicted rows ({result['totals']['extra']})")
    print(f"\nMismatches ({title}):")
    for m in result["mismatches"]:
        print(f"  {m['report']} | {m['test']} | {m['field']} | gold={m['gold']!r} | pred={m['predicted']!r}")


def apply_corrections(golds, corrections):
    fixed = {}
    for stem, rows in golds.items():
        fixes = {norm(k): v for k, v in corrections.get(stem, {}).items()}
        fixed[stem] = [{**r, **fixes.get(norm(r["test_name"]), {})} for r in rows]
    return fixed


def load_rows(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))["tests"] if path.exists() else None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    run = Path(sys.argv[1])
    golds = {p.stem: load_rows(p) for p in sorted(Path("gold").glob("*.json"))}
    preds = {stem: load_rows(run / f"{stem}.json") for stem in golds}
    output = {"original": evaluate(golds, preds)}
    show("original gold", output["original"])
    corrections = Path("gold_corrections.json")
    if corrections.exists():
        fixed = apply_corrections(golds, json.loads(corrections.read_text(encoding="utf-8")))
        output["corrected"] = evaluate(fixed, preds)
        show("corrected gold", output["corrected"])
    (run / "eval.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {run / 'eval.json'}")


if __name__ == "__main__":
    main()
