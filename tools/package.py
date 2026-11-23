"""Build dist/QuestieForeverFixes-<version>.zip from addon/QuestieForeverFixes (version from the .toc)."""
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "addon" / "QuestieForeverFixes"
NAME = "QuestieForeverFixes"
FILES = [f"{NAME}.toc", "Core.lua", "Data.lua", "icon.png"]


def main():
    toc = (ADDON / f"{NAME}.toc").read_text(encoding="utf-8")
    m = re.search(r"^## Version:\s*(\S+)", toc, re.M)
    if not m:
        raise SystemExit("no '## Version' line in the .toc")
    out = ROOT / "dist" / f"{NAME}-{m.group(1)}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(ADDON / f, f"{NAME}/{f}")
    print(out)
    for i in zipfile.ZipFile(out).infolist():
        print(" ", i.filename, i.file_size)


if __name__ == "__main__":
    main()
