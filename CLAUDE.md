# CLAUDE.md

Rules for this project.

- Do not run `extract.py`, `run_all.py`, or anything that calls the Gemini API. The user runs all scripts and pastes the output. Do not do any manual testing or trial runs.
- The only command you may run to check your work is `python -m py_compile <file>`.
- Do not change extraction behaviour in `extract.py` (prompt, DPI, pages, parsing, cleaning) unless the user explicitly asks in that prompt.
- Do not commit. The user reviews and commits.
- The user is on Windows using Git Bash. Any commands you give them must work in Git Bash.
- Keep code small and stdlib-only unless the user approves a dependency. The baseline is ~120 lines; don't balloon it.
