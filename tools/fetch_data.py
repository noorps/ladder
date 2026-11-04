"""download the published salbp benchmark sets and unpack them into data/raw.

sources (assembly-line-balancing.de):
  SALBP_benchmark.zip   otto, otto, scholl (2013) instance generator sets, n=20/50/100/1000
  SALBP-data-sets.zip   scholl (1993) precedence graphs plus the salbp-1 / salbp-2 optimum tables

the raw data is gitignored. data/manifest.json records what was downloaded
(name, bytes, sha256, file counts) and data/optima/*.json holds the published
optimum tables pulled out of the spreadsheets that ship inside the archives.
"""
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OPT = ROOT / "data" / "optima"
MANIFEST = ROOT / "data" / "manifest.json"

SOURCES = {
    "SALBP_benchmark.zip": "https://assembly-line-balancing.de/wp-content/uploads/2017/01/SALBP_benchmark.zip",
    "SALBP-data-sets.zip": "https://assembly-line-balancing.de/wp-content/uploads/2017/01/SALBP-data-sets.zip",
}
# fallback mirror for the otto 2013 sets if the primary host is down
MIRROR = "https://github.com/zixiangliwust/Instances_SALBP1"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(name, url):
    dest = RAW / name
    if dest.exists():
        print(f"have {name} ({dest.stat().st_size} bytes)")
        return dest
    print(f"fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "ladder-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    dest.write_bytes(data)
    print(f"  {len(data)} bytes")
    return dest


def unpack_otto(zpath):
    """SALBP_benchmark.zip holds one zip per size; unpack the n=20/50/100 ones."""
    out = RAW / "otto2013"
    out.mkdir(exist_ok=True)
    counts = {}
    with zipfile.ZipFile(zpath) as z:
        for inner in z.namelist():
            m = re.match(r"(small|medium|large) data set_n=(\d+)\.zip$", inner)
            if not m:
                continue
            n = int(m.group(2))
            with zipfile.ZipFile(io.BytesIO(z.read(inner))) as iz:
                k = 0
                for f in iz.namelist():
                    if f.endswith(".alb"):
                        (out / f"n{n}").mkdir(exist_ok=True)
                        (out / f"n{n}" / Path(f).name).write_bytes(iz.read(f))
                        k += 1
                counts[f"n{n}"] = k
        for inner in z.namelist():
            if inner.endswith(".xlsx"):
                (out / Path(inner).name).write_bytes(z.read(inner))
    return counts


def unpack_scholl(zpath):
    out = RAW / "scholl1993"
    out.mkdir(exist_ok=True)
    k = 0
    with zipfile.ZipFile(zpath) as z:
        for f in z.namelist():
            if f.endswith(".IN2"):
                (out / Path(f).name).write_bytes(z.read(f))
                k += 1
            elif f.endswith(".xlsx") or f.endswith(".DOC"):
                (out / Path(f).name).write_bytes(z.read(f))
    return {"IN2": k}


def otto_optima():
    """read the 'Details of the ... data set' sheets: filename -> optimum (or [lb, ub])."""
    import openpyxl
    res = {}
    for xf in sorted((RAW / "otto2013").glob("*.xlsx")):
        if "1000" in xf.name:
            continue
        wb = openpyxl.load_workbook(xf, read_only=True)
        ws = wb.worksheets[0]
        header = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                if row and any(isinstance(c, str) and "Filename" in c for c in row):
                    header = [str(c).strip() if c else "" for c in row]
                continue
            cells = dict(zip(header, row))
            name = cells.get("<Filename>")
            if not name:
                continue
            name = str(name).strip()
            opt = cells.get("<No of stations in optimum>")
            lb = cells.get("<Lower bound on the number of stations>")
            ub = cells.get("<Upper bound on the number of stations>")
            entry = {"lb": int(lb), "ub": int(ub)}
            if isinstance(opt, (int, float)):
                entry["optimum"] = int(opt)
            else:
                entry["optimum"] = None  # open instance, only [lb, ub] known
            entry["trickiness"] = cells.get("<Trickiness category>")
            res[name] = entry
    return res


def scholl_optima():
    """read 'SALBP data sets.xlsx': salbp-1 (graph, c) -> m*, salbp-2 (graph, m) -> c*."""
    import openpyxl
    wb = openpyxl.load_workbook(RAW / "scholl1993" / "SALBP data sets.xlsx", read_only=True)
    s1, s2 = [], []
    ws = wb["SALBP-1 data set"]
    for row in ws.iter_rows(values_only=True):
        g, c, m = row[0], row[1], row[2]
        if not (isinstance(g, str) and isinstance(c, (int, float))):
            continue
        if isinstance(m, (int, float)):
            s1.append({"graph": g, "c": int(c), "optimum": int(m)})
        elif isinstance(m, str) and "[" in m:
            # the one open instance (wee-mag c=47) carries "[lb,ub]" in the m* column
            lo, hi = [int(x) for x in re.findall(r"\d+", m)]
            s1.append({"graph": g, "c": int(c), "optimum": None, "lb": lo, "ub": hi})
    ws = wb["SALBP-2 data sets"]
    dataset = 0
    for row in ws.iter_rows(values_only=True):
        g, m, c = row[0], row[1], row[2]
        if isinstance(g, str) and g.startswith("Data set"):
            dataset = int(re.findall(r"\d+", g)[0])
        if isinstance(g, str) and isinstance(m, (int, float)) and c is not None:
            if isinstance(c, (int, float)):
                s2.append({"graph": g, "m": int(m), "optimum": int(c), "set": dataset})
            elif isinstance(c, str) and "[" in c:
                lo, hi = [int(x) for x in re.findall(r"\d+", c)]
                s2.append({"graph": g, "m": int(m), "optimum": None, "lb": lo, "ub": hi, "set": dataset})
    return s1, s2


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OPT.mkdir(parents=True, exist_ok=True)
    manifest = {"sources": {}, "counts": {}}
    for name, url in SOURCES.items():
        try:
            p = download(name, url)
        except Exception as e:
            print(f"failed to fetch {name}: {e}", file=sys.stderr)
            if name == "SALBP_benchmark.zip":
                print(f"the otto 2013 instances are also mirrored at {MIRROR}", file=sys.stderr)
            sys.exit(1)
        manifest["sources"][name] = {"url": url, "bytes": p.stat().st_size, "sha256": sha256(p)}
    manifest["counts"]["otto2013"] = unpack_otto(RAW / "SALBP_benchmark.zip")
    manifest["counts"]["scholl1993"] = unpack_scholl(RAW / "SALBP-data-sets.zip")

    otto = otto_optima()
    s1, s2 = scholl_optima()
    (OPT / "otto2013.json").write_text(json.dumps(otto, indent=0, sort_keys=True))
    (OPT / "scholl1993_salbp1.json").write_text(json.dumps(s1, indent=0))
    (OPT / "scholl1993_salbp2.json").write_text(json.dumps(s2, indent=0))
    manifest["counts"]["optima"] = {
        "otto2013": len(otto),
        "otto2013_open": sum(1 for v in otto.values() if v["optimum"] is None),
        "scholl1993_salbp1": len(s1),
        "scholl1993_salbp1_open": sum(1 for v in s1 if v["optimum"] is None),
        "scholl1993_salbp2": len(s2),
        "scholl1993_salbp2_open": sum(1 for v in s2 if v["optimum"] is None),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
