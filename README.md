# Lab report extractor: evaluation and fixes

## Setup (differs from starter kit)
- Windows + Git Bash. Poppler from github.com/oschwartz10612/poppler-windows, `Library/bin` on PATH. Venv: `source .venv/Scripts/activate`.
- Model: `gemini-3.8-flash` (unchanged). Free-tier daily quota ran out before 6 reports, so I linked billing to the project. Set `GEMINI_API_KEY` in your environment.
- No Python packages needed.

| Command | What it does |
|---|---|
| `python extract.py <file>` | Entry point, unchanged interface. Prints schema-valid JSON. |
| `python run_all.py <label>` | Runs every report via `extract.py`, with retries; saves outputs, latency, tokens to `runs/<label>/` |
| `python eval.py runs/<label>` | Scores against gold (original and corrected). `--labels labels_hand` scores my labels for the 4 unlabelled reports. `--strict` reproduces eval v1. |
| `python cost.py runs/<a> runs/<b>` | Cost per report, cost per 10k, latency |

## Result
| | Baseline | Final |
|---|---|---|
| Rows fully correct, gold (8 reports, 138 rows, corrected) | 72.5% | **100%** (3 runs: 2 at Fix 2, 1 final) |
| Rows fully correct, my labels (4 reports, 28 rows) | 96.4% | **100%** |
| Invented reference ranges / critical errors | 3 / 6 | 0 / 0 |
| Cost per report / per 10k reports | $0.0084 / $84 | **$0.0036 / $36** |
| Latency median / max | 15.0s / 37.2s | **6.6s / 18.0s** |

100% is on 12 clean, synthetic reports. The 6 unseen ones will be harder; this eval can't measure what it doesn't contain.

## Eval (task 2)
- **Row = correct** if value, unit and reference range all match the gold row (headline metric). Value compared numerically after removing commas (so "2,03,000" = 203000), otherwise as case-insensitive text. No unit conversion: 3.03 lakh is not 303000.
- **Critical errors** (wrong value on a matched row + predicted rows with no gold match) and **invented ranges** (gold has none, prediction does) are reported separately: a wrong number is worse for a doctor than a missing one.
- **Row matching:** exact or abbreviation or token-set name match, then order-aware gap filling (rows are printed in order). Never uses values to match.
- **Eval changes, all disclosed:** v1 counted renamed tests (ALP vs "Alkaline Phosphatase") as both missing and extra, so 16 of 20 "critical errors" were renames. Fixed in v2 before any extractor change; v1 kept as `--strict`. v3 removed fuzzy name matching after it paired "S. Cholesterol" with "HDL Cholesterol" (report_08 is a JPG, unaffected by the code change; I checked the JSON by hand). Every run was rescored with v3.
- **Gold:** audited all 8 files against the reports. One error: report_01 Platelet Count is 340000 on the PDF, 304000 in gold. Fixed in `gold_corrections.json`; scores reported for both.
- **Unlabelled reports (04, 07, 10, 12):** I labelled them myself in `labels_hand/`, seeded from baseline output and then corrected row by row against the reports (names back to printed form, values as printed, report_07 Globulin 3.3 -> 3.1, report_12 empty). Scored separately, never mixed with gold.
- **Known limit:** when the model renames and drops rows in the same section, a renamed row counts as an extra row.

## Diagnosis (task 3)
| Failure | Example | Root cause |
|---|---|---|
| Pages after page 1 never read | report_11: all 24 page-2 rows missing (e.g. Urea 42) | `pdftoppm -f 1 -l 1 -singlefile` renders only page 1 |
| Non-numeric results lost or mangled | report_06: Erythrocytes "1-2" -> 1.5, CRP "< 0.5" -> 0.5, Sugar "Present (+)" (the abnormal finding) dropped | Prompt "value must be a number" + `clean()` casting to float |
| Invented reference ranges | report_03: T3 "80 - 200", T4 "4.5 - 12.0" where the report prints none (and the lab's own T4 range is 5.1 - 14.1, see report_10) | Prompt "fill in the standard reference range" |

Also: tests renamed everywhere ("LDL-C (Direct)" -> "LDL Cholesterol", losing the method), from "use the standard medical name". And report_07 Globulin read as 3.3 (printed 3.1); see Fix 4.

## Fixes, one per commit (task 4)
| Fix | Gold (corrected) | My labels | Notes |
|---|---|---|---|
| Baseline | 72.5% | 96.4% | |
| 1. Send all PDF pages in one request | 81.2% | 96.4% | report_11 +13 correct rows |
| 2. Prompt: names/values as printed, no invented ranges, null if unreadable, empty for non-reports; keep value as string | 100% (x2) | 96.4% | |
| 3. DPI 60 -> 150 | 100% | 96.4% | **Reverted**, see task 5 |
| 4. Thinking level low | 100% (x2) | **100%** | Fixed report_07 Globulin; output tokens -66% |
| 5. Unparseable reply raises (retried) instead of returning `[]` | 100% | 100% | Previously a malformed reply looked like an empty report |

## What didn't help (task 5)
- **DPI 60 -> 150** to fix report_07 Globulin: no change (still 3.3; scores unchanged). Token counts explain it: every image costs exactly 1,092 tokens regardless of input resolution, so the extra detail was discarded before the model saw it.
- **Prompt rule "never work a value out from other rows"**: Globulin stayed 3.3 in all 5 runs at default thinking. 3.3 = Total Protein 7.7 - Albumin 4.4: the model was computing, not reading. Only lowering thinking fixed it (2/2 runs). More reasoning made extraction worse.
- **Prompt examples:** my Fix 2 prompt contained examples copied from the sample reports ("< 0.5", "1-2"…), a risk of overfitting. Removing them scored the same (100%), so the final prompt has none.

## Cost and scale
Prices: $0.75 / 1M input, $3.75 / 1M output including thinking (gemini-3.8-flash standard tier, checked 27-10-2026). At 10,000 reports/day: ~$36/day now vs ~$84 for the baseline. Not latency-sensitive, so the Batch API (half price) would bring it to ~$18/day. Rates are scheduled to double on 1 Jan 2027. The free tier is unusable at this volume (quota exhausted in under 6 reports), and the starter has no retries: my first smoke test failed 5 of 6 times (503s, timeouts). `run_all.py` retries; production would need the same.

## Three questions (task 6)
**RAG:** No. The job is transcribing what's printed. The worst baseline errors came from the model adding outside knowledge (invented ranges, "standard" names); retrieval would feed it more. Retrieval could help a later, separate step, such as mapping printed names to standard codes, not extraction.

**Fine-tuning:** Not now. Every failure here was caused by instructions or pipeline and was fixed with a prompt and code change at no training cost. 8 hastily labelled reports (one wrong) aren't training data. Worth revisiting only if production shows a persistent error class on specific layouts or handwriting that prompting can't fix, with corrected labels from human review.

**Multi-step agent:** Not earned. One call per report hits 100% here at $0.0036 and 6.6s. report_07 shows more reasoning made it worse. What would earn its place next: cheap deterministic checks after extraction that flag rows for human review, not more model steps.

## Prompt
The single extraction prompt is `PROMPT` in `extract.py`. Why each rule:
- **Names as printed:** traceability to the report; renaming lost "(Direct)".
- **Value as string, as printed:** keeps "< 0.5", "1-2", "Negative"; the numeric rule averaged and dropped results.
- **Range only if printed, never from knowledge:** removes invented ranges.
- **Null if unreadable, never calculated:** a guess is worse than a gap for a doctor.
- **Empty list for non-reports:** keeps report_12 (a prescription with advised tests) empty.
- **No `status` field:** it was the model's own normal/high judgment, not printed data.

## Not done, on purpose
No OCR stage, RAG, fine-tuning, agent or name normalisation; no repeated runs beyond 2 per key config; thinking budget not tuned below "low". Known risk: a reply truncated at the token limit fails all retries (but visibly, in `meta.json`).

## Decision log
Full timestamped log in `PLAN-v2.md`. Types: **Dir** = how I directed the agent, **Over** = overruled the agent, **Agent** = agent was right or found something, **Ver** = verified by hand, **Plan** = changed the plan.

| Type | What happened | Evidence / outcome |
|---|---|---|
| Dir | Wrote `CLAUDE.md` rules before any code: agent never calls the API or runs scripts, never commits, never changes extraction behaviour unless asked | Kept API spend and runs under my control; every result in `runs/` is from a run I made |
| Dir | Broke work into small prompts: runner, eval, one fix per prompt, each reviewed as a diff before commit | Git history: one change per commit |
| Dir | Put retries in `run_all.py`, not `extract.py`, so the baseline extractor stayed untouched | Baseline diff = one stderr logging line |
| Ver | Re-read the email before letting the agent edit `extract.py`: only the entry point must stay intact, not the file | Instrumentation limited to one stderr line, checked in the diff |
| Plan | Free-tier quota ran out before 6 reports; switched to a billed project instead of a different model, to keep before/after comparable | Same model throughout |
| Ver | Smoke test: 5 of 6 calls failed (503s, timeouts); output renamed tests; model read 340000 where gold says 304000 | First evidence for reliability, renaming and gold error |
| Plan | Eval v1 double-counted renamed tests (16 of 20 critical errors were renames). Changed matching (v2) before any extractor change; v1 kept as `--strict` | v1 output saved; v1 was run before being committed, disclosed |
| Over | Agent applied a v2 change inside `--strict` too; made `--strict` reproduce v1 exactly | `--strict` matches the saved v1 numbers |
| Ver | Found gold error: report_01 Platelet Count 340000 on the PDF, 304000 in gold | `gold_corrections.json`; scores reported for both |
| Ver | Hand-checked all 13 position-matched pairs against the reports | 13/13 correct |
| Ver | Zoomed report_07: pen circle, not a scribble; Globulin is printed 3.1, model said 3.3 | Became the key case for Fix 4 |
| Ver | report_12 (prescription): baseline already returned `[]` | Reported as correct, used as a regression check |
| Ver | Labelled the 4 unlabelled reports myself, correcting every row against the report | Corrections listed in Eval section |
| Agent | Agent saved hand-label results to a separate file unasked; accepted because it stops overwriting gold results | `eval_labels_hand.json` |
| Agent | I reported a column-spacing bug; agent said the code was correct. I read the format string myself: agent was right, spaces were lost in copying | No change made |
| Ver / Plan | After Fix 1, report_08 (a JPG, untouched by the change) dropped to 0%. Checked its JSON by hand: all 6 values correct. Eval had fuzzy-matched "S. Cholesterol" to "HDL Cholesterol". Removed fuzzy matching (v3) instead of tuning the threshold; rescored every run | report_08 back to 100% |
| Plan | Chose the fix order myself: pages (largest, mechanical), prompt, DPI, thinking, parse failures | `PLAN-v2.md` |
| Ver | After Fix 2's 100%, spot-checked 13 previously failing values in the raw JSON | 13/13 correct |
| Ver | Repeated key runs to separate real gains from run-to-run variance (the model is not deterministic: "1-2" came back as 1.5 in one run and 2.0 in another) | Fix 2 and Fix 4 each 100% in 2/2 runs |
| Ver | My Fix 2 prompt had examples copied from the samples; ran an ablation without them | Same score, so examples removed |
| Plan | DPI 150 changed nothing; token counts showed every image is 1,092 tokens regardless of resolution | Reverted to 60 |
| Plan | Tested the hypothesis that thinking caused the Globulin 3.3 (= 7.7 − 4.4) | Low thinking: 3.1 in 2/2 runs, 2–3× faster |
| Agent | Agent flagged that a malformed reply silently becomes `[]` (already in the baseline) | Fixed as Fix 5 |
| Ver | Cross-checked `cost.py` against my own hand calculation | Identical to the cent |
| Plan | Cut scope to stay near the timebox: no OCR, RAG, fine-tuning, agent, name normalisation or extra repeat runs | See "Not done, on purpose" |

Time: about 4.5 hours of active work, plus time lost to quota limits and manual data checks and filing.
Agent transcripts: `transcripts/`.