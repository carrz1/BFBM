"""Reusable extractor: given a saved read_console_messages JSON file and an
output directory, find every SLOT<N>_BEGIN...SLOT<N>_END payload and write
it to <outdir>/slot<N>_quals.tsv. Skips slots that already have a non-empty
file on disk (idempotent / safe to re-run after partial flushes).
"""
import json
import re
import sys
from pathlib import Path

def extract(console_file, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(console_file).read_text(encoding="utf-8"))
    combined = "\n".join(item.get("text", "") for item in data)

    pattern = re.compile(r"SLOT(\d+)_BEGIN(.*?)SLOT\1_END", re.DOTALL)
    found = {}
    for m in pattern.finditer(combined):
        slot = m.group(1)
        payload = m.group(2)
        # keep first occurrence only (messages can appear duplicated in the dump)
        if slot not in found:
            found[slot] = payload

    written = []
    skipped = []
    for slot, payload in found.items():
        out_path = outdir / f"slot{slot}_quals.tsv"
        if out_path.exists() and out_path.stat().st_size > 0:
            skipped.append(slot)
            continue
        out_path.write_text(payload, encoding="utf-8", newline="")
        written.append(slot)

    print(f"Found {len(found)} slot payloads in dump.")
    print(f"Wrote {len(written)} new files: {sorted(written, key=int)}")
    if skipped:
        print(f"Skipped {len(skipped)} already-present files: {sorted(skipped, key=int)}")
    return written


if __name__ == "__main__":
    console_file = sys.argv[1]
    outdir = sys.argv[2]
    extract(console_file, outdir)
