"""締切前オッズのスナップショット収集。

使い方: python odds_poller.py OUTDIR [--until HH:MM] [--offsets 10,5,2] [--workers 2]
- 当日(JST)の開催場を index ページから取得し、各場の締切予定時刻を odds2tf(1R) から取得
- 各レースの締切 T に対し T-10, T-5, T-2 分(既定)と T+4 分(締切時オッズ)に
  odds2tf(2連単/2連複), oddstf(単勝/複勝), odds3t(3連単) を取得
- 1ページ取得は約10秒。同時接続は workers (既定2)
- 生HTMLは保存せず、パースしたオッズを JSON Lines で OUTDIR/odds_YYYYMMDD.jsonl に追記
- --until を過ぎた締切のレースは扱わない(ジョブの実行時間制限 6 時間に合わせて分割実行するため)
"""
from __future__ import annotations

import argparse
import datetime as dt
import heapq
import json
import pathlib
import re
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from parse_odds import exacta_quinella, trifecta, win_place  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))
BASE = "https://www.boatrace.jp/owpc/pc/race/{page}?rno={rno}&jcd={jcd}&hd={hd}"
UA = {"User-Agent": "Mozilla/5.0 (personal research; low rate)"}
PARSERS = {"odds2tf": exacta_quinella, "oddstf": win_place, "odds3t": trifecta}


def now():
    return dt.datetime.now(JST)


def get(url, timeout=40):
    for a in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            time.sleep(3 * (a + 1))
    return None


def venues(hd):
    h = get(f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}") or ""
    return sorted(set(re.findall(rf"jcd=(\d{{2}})&(?:amp;)?hd={hd}", h)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--until", default="23:59")
    ap.add_argument("--offsets", default="10,5,2")
    ap.add_argument("--final-after", type=int, default=4)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--pages", default="odds2tf,oddstf,odds3t")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    today = now().date(); hd = today.strftime("%Y%m%d")
    until = dt.datetime.combine(today, dt.time.fromisoformat(a.until), JST)
    pages = a.pages.split(",")
    offsets = [int(x) for x in a.offsets.split(",")]
    fout = (out / f"odds_{hd}.jsonl").open("a", encoding="utf-8")
    lock = threading.Lock()

    def log(rec):
        with lock:
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()

    # 1) 開催場と締切時刻
    jcds = venues(hd)
    sched = []  # (fire_time, jcd, rno, deadline, tag)
    for jcd in jcds:
        h = get(BASE.format(page="odds2tf", rno=1, jcd=jcd, hd=hd))
        time.sleep(1)
        if not h:
            continue
        dls = exacta_quinella(h)["deadlines"]
        log(dict(kind="schedule", hd=hd, jcd=jcd, deadlines=dls, fetched=now().isoformat()))
        for i, t in enumerate(dls, start=1):
            T = dt.datetime.combine(today, dt.time.fromisoformat(t if len(t) == 5 else "0" + t), JST)
            if T > until or T + dt.timedelta(minutes=a.final_after) < now():
                continue
            for off in offsets:
                ft = T - dt.timedelta(minutes=off)
                if ft > now():
                    sched.append((ft, jcd, i, T, f"T-{off}"))
            sched.append((T + dt.timedelta(minutes=a.final_after), jcd, i, T, "final"))
    heapq.heapify(sched)
    print(f"{hd}: venues={len(jcds)} snapshots={len(sched)} until={a.until}", flush=True)

    # 2) 実行
    q_lock = threading.Lock()

    def worker():
        while True:
            with q_lock:
                if not sched:
                    return
                ft, jcd, rno, T, tag = heapq.heappop(sched)
            wait = (ft - now()).total_seconds()
            if wait > 0:
                time.sleep(wait)
            statuses = []
            for page in pages:
                t0 = now()
                h = get(BASE.format(page=page, rno=rno, jcd=jcd, hd=hd))
                rec = dict(kind="odds", hd=hd, jcd=jcd, rno=rno, deadline=T.strftime("%H:%M"), tag=tag, page=page,
                           requested=t0.isoformat(timespec="seconds"), received=now().isoformat(timespec="seconds"))
                if h:
                    r = PARSERS[page](h); r.pop("deadlines", None)
                    rec.update(r)
                else:
                    rec["error"] = "fetch_failed"
                statuses.append(rec.get("status"))
                log(rec)
                time.sleep(1)
            # 締切後の取得で確定表示になっていなければ(発走遅延など)、5分後に最大3回まで取り直す
            if tag.startswith("final") and any(st != "final" for st in statuses):
                n = int(tag[5:] or 1)
                if n < 4:
                    with q_lock:
                        heapq.heappush(sched, (now() + dt.timedelta(minutes=5), jcd, rno, T, f"final{n + 1}"))

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(a.workers)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    fout.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()
