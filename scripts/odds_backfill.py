"""過去レースの締切時オッズ(既定: 2連単/2連複)を取得する。

Usage: python odds_backfill.py START END OUTDIR [--pages odds2tf] [--sleep 1.5]
日付ごとに index で開催場を取り、各場 1R の odds2tf から締切時刻(=レース数)を得て全レースを取得。
出力: OUTDIR/odds_final_YYYYMM.jsonl (追記、取得済みのレースはスキップ)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from odds_poller import BASE, PARSERS, get, venues  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start"); ap.add_argument("end"); ap.add_argument("out")
    ap.add_argument("--pages", default="odds2tf")
    ap.add_argument("--sleep", type=float, default=1.5)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pages = a.pages.split(",")
    d = dt.date.fromisoformat(a.start); end = dt.date.fromisoformat(a.end)
    while d <= end:
        hd = d.strftime("%Y%m%d")
        path = out / f"odds_final_{d:%Y%m}.jsonl"
        done = set()
        if path.exists():
            for l in path.open(encoding="utf-8"):
                r = json.loads(l)
                done.add((r["hd"], r["jcd"], r["rno"], r["page"]))
        fh = path.open("a", encoding="utf-8")
        for jcd in venues(hd):
            time.sleep(a.sleep)
            nr = 12
            for rno in range(1, nr + 1):
                for page in pages:
                    if (hd, jcd, rno, page) in done:
                        continue
                    h = get(BASE.format(page=page, rno=rno, jcd=jcd, hd=hd))
                    time.sleep(a.sleep)
                    rec = dict(hd=hd, jcd=jcd, rno=rno, page=page)
                    if h:
                        r = PARSERS[page](h)
                        if rno == 1 and r.get("deadlines"):
                            nr = len(r["deadlines"])
                        r.pop("deadlines", None)
                        rec.update(r)
                    else:
                        rec["error"] = "fetch_failed"
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
                if rno >= nr:
                    break
        fh.close()
        print(hd, "done", flush=True)
        d += dt.timedelta(days=1)


if __name__ == "__main__":
    main()
