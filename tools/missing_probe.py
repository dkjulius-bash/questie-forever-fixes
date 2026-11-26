"""Step 1 of the missing-quest hunt: QuestV2 ids not in QuestieDB, probed via the Wowhead tooltip API.

Writes work/missing/candidates.json. Tooltip cache: work/missing/tooltip/.
"""
import csv
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from qdb_decode import InstalledDB  # noqa: E402
from wh_tooltip import WH  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB"
JUNK = re.compile(r"unused|\bnyi\b|deprecated|\btest|<txt>|\[ph\]|\bph\b|placeholder|\bdnd\b|do not use|"
                  r"copy of|\bzz|\bold\b|^<|\bdepricated|\(123\)|reuse|\bqa\b|debug|internal|template|never used|\[dnt\]|\bbeta\b",
                  re.I)


def main():
    db = InstalledDB(QDB)
    have = db.ids("Quest")
    v2 = [int(r["ID"]) for r in csv.DictReader(open(os.path.join(ROOT, "work", "db2", "QuestV2.csv")))]
    ids = sorted(set(v2) - have)
    wh = WH(os.path.join(ROOT, "work", "missing", "tooltip"), offline="--offline" in sys.argv)
    out = []
    for n, i in enumerate(ids):
        d = wh.get("quest", i) or {}
        name = html.unescape(d.get("name") or "")
        known = "error" not in d and bool(name.strip())
        text = re.sub(r"<[^>]+>", " ", html.unescape(d.get("tooltip") or ""))
        text = re.sub(r"\s+", " ", text).strip()
        junk = bool(JUNK.search(name)) if known else None
        out.append({"id": i, "known": known, "name": name, "junk": junk,
                    "error": d.get("error"), "tooltipText": text[:400]})
        if n % 100 == 0:
            print(n, len(ids), flush=True)
    summ = {"questV2": len(set(v2)), "questieDB": len(have), "candidates": len(ids),
            "whKnown": sum(o["known"] for o in out),
            "real": sum(1 for o in out if o["known"] and not o["junk"])}
    with open(os.path.join(ROOT, "work", "missing", "candidates.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summ, "candidates": out}, f, indent=1, ensure_ascii=False)
    print(summ)


if __name__ == "__main__":
    main()
