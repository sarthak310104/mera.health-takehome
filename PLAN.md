# PLAN

## How I'm breaking this down
1. **Baseline run, nothing changed.** Get the supplied extractor running as-is (Gemini free tier, `gemini-3.8-flash`), save its raw output for all 12 reports, and record model, latency and token counts per report.
2. **Eval before any fixes.** Match rows by normalised test name within a report, then score each matched row on value, unit and reference range. I'll report:
   - row recall (missed tests)
   - row precision (invented tests)
   - value accuracy on matched rows (the number a doctor reads)
   - unit and range accuracy
   - a separate count of invented reference ranges

   A wrong or invented value counts as worse than a null. I freeze the eval definition before touching the extractor.
3. **Audit the gold labels.** They were "made in a hurry", so I'll check each one against its source document and keep any corrections in a separate file. Scores get reported against both the original and the corrected labels.
4. **Unlabelled reports (04, 07, 10, 12).** I'll hand-check these against the image and keep them as a separate set, not mixed into the gold score.
5. **Diagnose**, from per-field errors on the baseline, before choosing fixes.
6. **Fix one thing per commit**, cheapest first, re-running the eval and recording cost and latency after each change.

## What I'll look at first
The prompt and the preprocessing in `extract.py`, then the per-field breakdown of the baseline's errors.

## What I expect to find
- The prompt forces `value` to be a number, so results like "Negative", "< 0.5", "8-10" and "2,03,000" get lost or mangled.
- The prompt tells the model to fill in "standard" reference ranges, so it will invent ranges that aren't on the report.
- PDFs are rendered at 60 DPI and only page 1 is sent, so multi-page reports lose rows and small digits get misread.
- A document that isn't a lab report, or a value that's crossed out, will get plausible-looking invented results.
- Some gold labels will be wrong.

## What I don't plan to do (unless evidence says otherwise)
- No RAG, fine-tuning or multi-step agent.
- No separate OCR pass.
- No fixes tailored to particular sample reports.
- No changes to the eval after I see scores.

Eight labelled reports is not too big of a sample, so I'll run each configuration more than once to see how much the score varies between runs.

## Special Note
In case new findings are there during the process, I will be adding changes to PLAN-v2.md just to show that new changes were needed and have been thoroughly followed as per the second file.