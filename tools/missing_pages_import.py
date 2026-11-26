"""Import qffExport batches (tools/wh_quest_page.js) into work/missing/pages/<id>.json.

Usage: python -I tools/missing_pages_import.py BATCH.json [BATCH2.json ...]
Each BATCH.json is the object qffExport returned ({total, from, ids, len, sum, chunks}), saved verbatim.
The chunks are joined and checked against len/sum before anything is written.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(ROOT, "work", "missing", "pages")


def checksum(s):
    """Same as qffExport: sum(charCode * (i % 97 + 1)) mod 1e9+7 over UTF-16 code units."""
    units = s.encode("utf-16-le")
    total = 0
    for i in range(0, len(units), 2):
        c = units[i] | (units[i + 1] << 8)
        total = (total + c * ((i // 2) % 97 + 1)) % 1000000007
    return total, len(units) // 2


def import_batch(path):
    with open(path, encoding="utf-8") as f:
        b = json.load(f)
    s = "".join(b["chunks"])
    got_sum, got_len = checksum(s)
    if (got_len, got_sum) != (b["len"], b["sum"]):
        sys.exit("%s MISMATCH: got len=%d sum=%d, want len=%d sum=%d" % (path, got_len, got_sum, b["len"], b["sum"]))
    os.makedirs(PAGES, exist_ok=True)
    ids = []
    for line in s.split("\n"):
        rec = json.loads(line)
        with open(os.path.join(PAGES, "%d.json" % rec["id"]), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        ids.append(rec["id"])
    if ids != b["ids"]:
        sys.exit("%s id list mismatch: %s vs %s" % (path, ids, b["ids"]))
    print("OK %s: %d records %s" % (os.path.basename(path), len(ids), ids))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        import_batch(p)
