"""Extract structured lab results from a lab report.

Usage:
    python extract.py reports/report_01.pdf

Prints JSON matching schema.json to stdout.
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
DPI = 150

PROMPT = """Extract every test result row from this lab report.

Return only JSON: {"tests": [{"test_name": "...", "value": "...", "unit": "...", "reference_range": "..."}]}

Rules:
- One entry per result row, in the order printed, across all pages.
- test_name: exactly as printed, including abbreviations and brackets. Do not expand or standardise names.
- value: a string, copied exactly as printed, including any symbols or text. Never round, convert, average or calculate.
- unit: as printed, or null if none. If the unit is printed inside the reference range column, put it in unit and leave it out of reference_range.
- reference_range: exactly as printed, or null if the report does not print one. Never fill in a range from your own knowledge.
- If a value cannot be read, use null. Never work it out from other rows.
- Ignore handwritten notes, comments, method lines and patient details.
- If the document contains no test results (for example a prescription or a list of advised tests), return {"tests": []}.
"""

MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def load_image(path: Path) -> list[tuple[str, str]]:
    """Return [(media_type, base64 data), ...] for the report, one entry per page."""
    if path.suffix.lower() == ".pdf":
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "page"
            try:
                subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(path), str(prefix)],
                               check=True, capture_output=True)
            except FileNotFoundError:
                raise RuntimeError("Install Poppler (pdftoppm); see README.md.") from None
            pages = sorted(Path(directory).glob("page-*.png"))
            return [("image/png", base64.standard_b64encode(p.read_bytes()).decode()) for p in pages]
    return [(MEDIA_TYPES[path.suffix.lower()], base64.standard_b64encode(path.read_bytes()).decode())]


def call_model(images: list[tuple[str, str]]) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY; see README.md. No API call made.")
    body = {
        "contents": [{"role": "user", "parts": [
            *({"inlineData": {"mimeType": media_type, "data": data}} for media_type, data in images),
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 16000},
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Gemini HTTP {error.code}; check API access, model and quota. See README.md.") from None
    except urllib.error.URLError:
        raise RuntimeError("Gemini connection failed; check network/TLS access and retry. See README.md.") from None
    print("USAGE " + json.dumps(result.get("usageMetadata")), file=sys.stderr)
    candidate = result.get("candidates", [{}])[0]
    return "".join(part["text"] for part in candidate.get("content", {}).get("parts", [])
                   if "text" in part and not part.get("thought"))


def parse(text: str) -> list[dict]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(match.group(0))["tests"]
    except Exception:
        return []


def clean(tests: list[dict]) -> list[dict]:
    out = []
    for t in tests:
        out.append({
            "test_name": str(t.get("test_name", "")).strip(),
            "value": None if t.get("value") is None else str(t["value"]).strip(),
            "unit": t.get("unit") or None,
            "reference_range": t.get("reference_range") or None,
        })
    return out


def extract(path: Path) -> dict:
    return {"tests": clean(parse(call_model(load_image(path))))}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        print(json.dumps(extract(Path(sys.argv[1])), indent=2, ensure_ascii=False))
    except RuntimeError as error:
        sys.exit(str(error))
