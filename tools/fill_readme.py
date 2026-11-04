"""paste the generated tables into the readme between <!-- TABLE: name --> and <!-- /TABLE -->
markers, so every number in the readme comes from results/<label>/*.json."""
import argparse
import contextlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import tables  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def capture(fn, out_dir):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(out_dir)
    return buf.getvalue().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    out_dir = ROOT / "results" / args.label
    sections = {
        "benchmark": lambda d: capture(tables.benchmark_tables, d),
        "comsoal": lambda d: capture(tables.comsoal_table, d),
        "sim": lambda d: capture(tables.sim_tables, d),
        "agent": lambda d: capture(tables.agent_tables, d),
    }
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name, fn in sections.items():
        body = fn(out_dir)
        if not body:
            continue
        block = f"<!-- TABLE: {name} -->\n{body}\n<!-- /TABLE -->"
        pat = re.compile(rf"<!-- TABLE: {name} -->.*?<!-- /TABLE -->", re.S)
        if pat.search(readme):
            readme = pat.sub(lambda m: block, readme, count=1)
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    print("readme tables filled from", out_dir)


if __name__ == "__main__":
    main()
