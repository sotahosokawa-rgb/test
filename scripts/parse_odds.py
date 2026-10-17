"""Parse boatrace.jp odds pages (odds3t / odds3f / odds2tf / oddstf / oddsk).

各ページの td.oddsPoint は「行優先」で並ぶ。列 = 1着(または小さい方)の艇番。
検証: 2025-01-01 桐生12R で 3連単1-2-3=4.5(払戻450円)、2連単1-2=1.9(190円)、単勝1=1.2(120円) が一致。
"""
from __future__ import annotations

import itertools
import re
import warnings

from bs4 import BeautifulSoup

try:
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except Exception:
    pass

BOATS = range(1, 7)


def _vals(table):
    out = []
    for td in table.select("td.oddsPoint"):
        t = td.get_text(strip=True)
        try:
            out.append(float(t))
        except ValueError:
            out.append(None)  # 欠場・発売なし等
    return out


def _tables(html):
    s = BeautifulSoup(html, "lxml")
    return s, [t for t in s.select("table") if t.select("td.oddsPoint")]


def _deadlines(s):
    """ページ上部の 締切予定時刻 (1R..12R)。"""
    for t in s.select("table"):
        tx = t.get_text(" ", strip=True)
        if "締切予定時刻" in tx:
            return re.findall(r"\b(\d{1,2}:\d{2})\b", tx)
    return []


def _status(s):
    tx = s.get_text(" ", strip=True)
    if "締切時オッズ" in tx:
        return "final"
    m = re.search(r"(\d{1,2}:\d{2})\s*現在", tx)
    return f"asof {m.group(1)}" if m else "unknown"


def trifecta(html):
    s, tbls = _tables(html)
    v = _vals(tbls[0]) if tbls else []
    out = {}
    if len(v) == 120:
        cols = {i: [(j, k) for j in BOATS for k in BOATS if len({i, j, k}) == 3] for i in BOATS}
        for n in range(20):
            for ci, i in enumerate(BOATS):
                j, k = cols[i][n]
                out[f"{i}-{j}-{k}"] = v[n * 6 + ci]
    return dict(odds=out, deadlines=_deadlines(s), status=_status(s))


def exacta_quinella(html):
    s, tbls = _tables(html)
    ex, qu = {}, {}
    if len(tbls) >= 1:
        v = _vals(tbls[0])
        if len(v) == 30:
            cols = {i: [j for j in BOATS if j != i] for i in BOATS}
            for n in range(5):
                for ci, i in enumerate(BOATS):
                    ex[f"{i}-{cols[i][n]}"] = v[n * 6 + ci]
    if len(tbls) >= 2:
        v = _vals(tbls[1])
        if len(v) == 15:
            pairs = [(i, j) for j in range(2, 7) for i in range(1, j)]  # 行=大きい方, 行内=小さい方
            for (i, j), x in zip(pairs, v):
                qu[f"{i}-{j}"] = x
    return dict(exacta=ex, quinella=qu, deadlines=_deadlines(s), status=_status(s))


def win_place(html):
    s, tbls = _tables(html)
    win, place = {}, {}
    if len(tbls) >= 1:
        for b, x in zip(BOATS, _vals(tbls[0])):
            win[str(b)] = x
    if len(tbls) >= 2:
        for b, td in zip(BOATS, tbls[1].select("td.oddsPoint")):
            m = re.match(r"([\d.]+)-([\d.]+)", td.get_text(strip=True))
            place[str(b)] = (float(m.group(1)), float(m.group(2))) if m else None
    return dict(win=win, place=place, deadlines=_deadlines(s), status=_status(s))


def trio(html):
    s, tbls = _tables(html)
    v = _vals(tbls[0]) if tbls else []
    out = {}
    if len(v) == 20:
        # 3連複: DOM順は検証後に確定する(現状は組番の辞書順を仮置き)
        for c, x in zip(itertools.combinations(BOATS, 3), v):
            out["-".join(map(str, c))] = x
    return dict(odds=out, deadlines=_deadlines(s), status=_status(s), verified=False)


if __name__ == "__main__":
    import sys, json
    kind, path = sys.argv[1], sys.argv[2]
    html = open(path, encoding="utf-8").read()
    fn = dict(odds3t=trifecta, odds2tf=exacta_quinella, oddstf=win_place, odds3f=trio)[kind]
    r = fn(html)
    print(json.dumps({k: (v if not isinstance(v, dict) else dict(list(v.items())[:8])) for k, v in r.items()}, ensure_ascii=False))
