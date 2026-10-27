"""Score extraction predictions against gold. No API calls.

Usage: python eval.py runs/<label> [--strict] [--labels <dir>]

--labels <dir> scores against <dir>/<stem>.json instead of gold/ (gold_corrections.json is then ignored, and
output goes to eval_<dir>.json). A labels file with an empty tests list makes every predicted row an unmatched
(critical) row.

--strict reproduces v1 (name equality, abbreviation, similarity >= 0.8 only; no trailing-unit stripping on
reference ranges) and writes eval_strict.json.
Otherwise (v3) names match only on exact normalised name, parenthetical abbreviation or equal word sets (no
difflib similarity), and leftover rows are paired by position within gaps.

Optional gold_corrections.json: {"report_01": [{"test_name": "...", "field": "value", "corrected": "...",
"evidence": "..."}]} overrides that field of the named gold row; scores are then printed for original and corrected gold.
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


def similarity(a, b, strict=False) -> float:
    na, nb = norm(a), norm(b)
    if na == nb or (na and na in abbrs(b)) or (nb and nb in abbrs(a)):
        return 1.0
    if strict:
        return difflib.SequenceMatcher(None, na, nb).ratio()
    return 1.0 if set(na.split()) == set(nb.split()) else 0.0


def match_rows(gold, pred, strict=False):
    """One-to-one matching on name only, best similarity first, then (unless strict) order-aware gap filling.

    Returns ({gold_idx: pred_idx}, set of position-matched gold_idx).
    """
    pairs = sorted(((similarity(g["test_name"], p["test_name"], strict), gi, pi)
                    for gi, g in enumerate(gold) for pi, p in enumerate(pred)), key=lambda t: (-t[0], t[1], t[2]))
    matched, used, positional = {}, set(), set()
    for sim, gi, pi in pairs:
        if sim >= 0.8 and gi not in matched and pi not in used:
            matched[gi] = pi
            used.add(pi)
    if strict:
        return matched, positional
    anchors = [(-1, -1), *sorted(matched.items()), (len(gold), len(pred))]
    for (g0, p0), (g1, p1) in zip(anchors, anchors[1:]):
        free_g = [gi for gi in range(g0 + 1, g1) if gi not in matched]
        free_p = [pi for pi in range(p0 + 1, p1) if pi not in used]
        if free_g and len(free_g) == len(free_p):
            for gi, pi in zip(free_g, free_p):
                matched[gi] = pi
                positional.add(gi)
    return matched, positional


def number(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def strip_unit(rng, unit):
    rng = str(rng).strip()
    if unit and rng.lower().endswith(str(unit).strip().lower()):
        return rng[:len(rng) - len(str(unit).strip())]
    return rng


def same(field, g, p, g_unit=None, p_unit=None, strict=False) -> bool:
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
    fix = lambda r: re.sub(r"[,\s]", "", r)
    if strict:
        return fix(str(g)) == fix(str(p))
    return fix(strip_unit(g, g_unit)) == fix(strip_unit(p, p_unit))


def score(gold, pred, strict=False):
    c = dict.fromkeys(("gold", "pred", "matched", "pos", "name_exact", "value_ok", "unit_ok", "range_ok", "full",
                       "invented", "wrong_value", "extra"), 0)
    c["gold"], c["pred"] = len(gold), len(pred)
    (matched, positional), issues = match_rows(gold, pred, strict), []
    for gi, pi in matched.items():
        g, p = gold[gi], pred[pi]
        ok = {f: same(f, g.get(f), p.get(f), g.get("unit"), p.get("unit"), strict) for f in FIELDS}
        c["matched"] += 1
        c["pos"] += gi in positional
        c["name_exact"] += " ".join(g["test_name"].lower().split()) == " ".join(p["test_name"].lower().split())
        if gi in positional:
            issues.append((g["test_name"], "name (position-matched)", g["test_name"], p["test_name"]))
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
             range_acc=rate(c["range_ok"], c["matched"]), full_acc=rate(c["full"], c["gold"]),
             name_exact_acc=rate(c["name_exact"], c["matched"]))
    return c


def evaluate(golds, preds, strict=False):
    per, issues, total = {}, [], {}
    for stem, gold in golds.items():
        c, found = score(gold, preds.get(stem) or [], strict)
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
          f"{'full':>7}{'invent':>7}{'critic':>7}{'pos':>5}{'nameEx':>8}")
    for name, r in [*result["reports"].items(), ("TOTAL", result["totals"])]:
        print(f"{name:<12}{r['gold']:>5}{r['pred']:>5}{pct(r['recall']):>7}{pct(r['precision']):>7}"
              f"{pct(r['value_acc']):>7}{pct(r['unit_acc']):>7}{pct(r['range_acc']):>7}{pct(r['full_acc']):>7}"
              f"{r['invented']:>7}{r['critical']:>7}{r['pos']:>5}{pct(r['name_exact_acc']):>8}")
    print(f"critical = wrong values ({result['totals']['wrong_value']}) + unmatched predicted rows ({result['totals']['extra']})")
    print(f"\nMismatches ({title}):")
    for m in result["mismatches"]:
        print(f"  {m['report']} | {m['test']} | {m['field']} | gold={m['gold']!r} | pred={m['predicted']!r}")


def apply_corrections(golds, corrections):
    fixed = {stem: [dict(r) for r in rows] for stem, rows in golds.items()}
    for stem, entries in corrections.items():
        for e in entries:
            rows = [r for r in fixed.get(stem, []) if norm(r["test_name"]) == norm(e["test_name"])]
            if not rows:
                print(f"warning: correction not applied, no gold row {e['test_name']!r} in {stem}", file=sys.stderr)
            for r in rows:
                r[e["field"]] = e["corrected"]
    return fixed


def load_rows(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))["tests"] if path.exists() else None


def main() -> None:
    args = sys.argv[1:]
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    labels = Path("gold")
    if "--labels" in args:
        i = args.index("--labels")
        if i + 1 >= len(args):
            sys.exit(__doc__)
        labels = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    run = Path(args[0])
    is_gold = labels.resolve() == Path("gold").resolve()
    golds = {p.stem: load_rows(p) for p in sorted(labels.glob("*.json"))}
    preds = {stem: load_rows(run / f"{stem}.json") for stem in golds}
    output = {"original": evaluate(golds, preds, strict)}
    show("original gold" if is_gold else f"labels: {labels}", output["original"])
    corrections = Path("gold_corrections.json")
    if is_gold and corrections.exists():
        fixed = apply_corrections(golds, json.loads(corrections.read_text(encoding="utf-8")))
        output["corrected"] = evaluate(fixed, preds, strict)
        show("corrected gold", output["corrected"])
    out_path = run / f"eval{'_strict' if strict else ''}{'' if is_gold else '_' + labels.name}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
