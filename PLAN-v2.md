# 2026-10-27

## 12:45, Added billing for Gemini
Free-tier daily quota was exhausted before the 6th report, which would have made the timebox impossible. Linked billing to the project. Spend is tracked and reported per report in the README.

## 12:50, Eval v1 double-counted renamed tests
Eval v1 counted renamed tests (ALP -> Alkaline Phosphatase, TG -> Triglycerides) as both missing and extra, so 16 of 20 "critical errors" were renames. Changed matching to order-aware gap filling (v2) before any extractor change. v1 kept as --strict; v1 was run before being committed, so its output is saved in eval_v1_output.txt.

## 12:55, Overruled agent on --strict
Claude Code applied the new range-unit stripping in --strict mode too. Asked it to make --strict reproduce v1 exactly.

## 13:00, Gold error in report_01
Platelet Count gold is 304000; the PDF prints 340000. Added to gold_corrections.json and report scores against both original and corrected gold.

## 16:35, Checked position-matched pairs by hand
Hand-checked all 13 position-matched pairs against the source reports: 13/13 correct.
Known limitation: report_06 "Urine pH" and "Urine Leukocytes" are renames that gap filling can't pair because nearby rows were dropped. Left as is rather than tuning the eval further.

## 16:36, Unlabelled reports
report_12 (prescription): baseline correctly returns no rows; kept as a regression check.
report_07: pen circle around Albumin/Globulin. Model gave Globulin 3.3; the report prints 3.1 (verified by zooming). 3.3 = 7.7 - 4.4, so the model may have computed it instead of reading it. Hypothesis: resolution; to test with higher DPI.

## 16:57, Hand labels for 04, 07, 10, 12
Seeded from baseline output, then corrected every row against the report. Corrections: test names back to printed form (report_04: 5, report_07: 2, report_10: <fill in>), values to printed form (Creatinine "1.00" not 1.0), Globulin 3.3 -> 3.1. Scored separately from gold.

## 17:00, Accepted agent suggestion
Claude Code saved hand-label results to a separate file (eval_labels_hand.json) without being asked. Kept it: stops hand-label runs from overwriting gold results.

## 17:18, Agent pushback on column spacing
I reported eval table columns running together. Claude Code said the format string was correct. I read the code myself (eval.py line 164): it was right. Spaces were lost in copying the terminal output. No change made.

## 17:44, Wrong result, personal check
report_08 (JPG, unaffected by Fix 1) dropped to 0%. Hand-checked runs/fix1_pages/report_08.json: all 6 values correct. Eval had fuzzy-matched S. Cholesterol to HDL Cholesterol. Removed fuzzy matching (v3) and rescored all runs.