"""Parse official boatrace K (results) and B (program) LZH files into tables.

Usage (library):
    from parse_lzh import parse_k_text, parse_b_text
CLI:
    python parse_lzh.py OUTDIR file1.lzh file2.lzh ...
writes races.csv, entries.csv, payouts.csv, program.csv (appended per call).
"""
from __future__ import annotations

import csv
import re
import sys
import pathlib
import unicodedata

VENUE_BGN = re.compile(r"^(\d{2})([KB])BGN")
VENUE_END = re.compile(r"^(\d{2})([KB])END")
FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def read_lzh_text(path) -> str:
    import lhafile
    f = lhafile.Lhafile(str(path))
    infos = f.infolist()
    if not infos:
        return ""
    return f.read(infos[0].filename).decode("cp932", errors="replace")


def split_venues(text: str):
    """Yield (venue_code, lines) blocks."""
    cur, buf = None, []
    for line in text.splitlines():
        m = VENUE_BGN.match(line)
        if m:
            cur, buf = m.group(1), []
            continue
        m = VENUE_END.match(line)
        if m and cur is not None:
            yield cur, buf
            cur, buf = None, []
            continue
        if cur is not None:
            buf.append(line)


# ---------------------------------------------------------------- K (results)
RACE_HDR_K = re.compile(r"^\s{2,4}(\d{1,2})R\s+(.*?)\s+H(\d{3,4})m\s+(\S+)\s+風\s+(\S+)\s+(\d+)m\s+波\s+(\d+)cm")
RACE_HDR_K_LOOSE = re.compile(r"^\s{2,4}(\d{1,2})R\s+(.*?)\s+H(\d{3,4})m")
ENTRY_K = re.compile(r"^\s{2}(\S{2})\s+(\d)\s(\d{4})\s(.{8,9}?)\s*(\d{1,3})\s+(\d{1,3})\s+([\d.]+|\.)\s+(\d|\.)?\s*([F L]?[\d.]+|\.|K\s*[\d.]*|F\.\d+|L\.\d+)?\s*(.*)$")
DATE_K = re.compile(r"(\d{4})/\s*(\d{1,2})/\s*(\d{1,2})")
PAY_TYPES = {"単勝": "win", "複勝": "place", "２連単": "exacta", "２連複": "quinella",
             "拡連複": "wide", "３連単": "trifecta", "３連複": "trio"}
PAY_ITEM = re.compile(r"(\d(?:-\d){0,2})\s+(\d+)(?:\s+人気\s+(\d+))?")


def parse_k_text(text: str):
    races, entries, payouts = [], [], []
    for venue, lines in split_venues(text):
        date = None
        for l in lines[:12]:
            m = DATE_K.search(l)
            if m:
                date = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                break
        if date is None:
            continue
        i, n = 0, len(lines)
        while i < n:
            l = lines[i]
            m = RACE_HDR_K_LOOSE.match(l)
            if not m:
                i += 1
                continue
            rno = int(m.group(1))
            full = RACE_HDR_K.match(l)
            race = dict(date=date, venue=venue, rno=rno, name=nfkc(m.group(2)).strip(),
                        distance=int(m.group(3)), weather="", wind_dir="", wind_speed="", wave="")
            if full:
                race.update(weather=nfkc(full.group(4)), wind_dir=nfkc(full.group(5)).replace(" ", ""),
                            wind_speed=int(full.group(6)), wave=int(full.group(7)))
            special = []
            i += 1
            # skip header lines until dashes
            while i < n and not lines[i].startswith("----"):
                i += 1
            i += 1
            # entries
            while i < n and lines[i].strip():
                e = parse_k_entry(lines[i])
                if e:
                    e.update(date=date, venue=venue, rno=rno)
                    entries.append(e)
                i += 1
            # payouts block until blank line followed by next race / end
            cur_type = None
            while i < n and not RACE_HDR_K_LOOSE.match(lines[i]):
                pl = lines[i]
                s = pl.strip()
                if s:
                    head = s.split()[0]
                    if head in PAY_TYPES:
                        cur_type = PAY_TYPES[head]
                        body = s[len(head):]
                    else:
                        body = s
                    if "特払い" in body:
                        amt = re.search(r"特払い\s+(\d+)", body)
                        payouts.append(dict(date=date, venue=venue, rno=rno, bet=cur_type, combo="特払い",
                                            amount=int(amt.group(1)) if amt else "", popularity=""))
                        special.append(f"{cur_type}:特払い")
                    elif "不成立" in body or "発売なし" in body or "返還" in body:
                        special.append(f"{cur_type}:{nfkc(body).strip()}")
                    elif cur_type:
                        for c, a, pop in PAY_ITEM.findall(body):
                            payouts.append(dict(date=date, venue=venue, rno=rno, bet=cur_type, combo=c,
                                                amount=int(a), popularity=int(pop) if pop else ""))
                i += 1
            race["special"] = ";".join(special)
            races.append(race)
    return races, entries, payouts


def parse_k_entry(line: str):
    # fixed layout:  "  01  1 3572 安　田　　政　彦 47   25  6.88   1    0.16     1.51.9"
    mh = re.match(r"^\s{2}(\S[\S ])\s+(\d)\s(\d{4})\s", line)
    if len(line) < 20 or not mh:
        return None
    pos, boat, reg = mh.group(1).strip(), int(mh.group(2)), int(mh.group(3))
    name = re.sub(r"[\s　]", "", line[13:22])
    rest = line[22:].split()
    def num(x, f=float):
        try:
            return f(x)
        except Exception:
            return ""
    motor = num(rest[0], int) if len(rest) > 0 else ""
    boatno = num(rest[1], int) if len(rest) > 1 else ""
    exh = num(rest[2]) if len(rest) > 2 else ""
    course = num(rest[3], int) if len(rest) > 3 else ""
    st_raw = rest[4] if len(rest) > 4 else ""
    rtime = rest[5] if len(rest) > 5 else ""
    st_flag = ""
    st = ""
    if st_raw:
        mm = re.match(r"^([FL])?([\d.]+)$", st_raw)
        if mm:
            st_flag = mm.group(1) or ""
            st = num(mm.group(2))
        else:
            st_flag = st_raw
    rt = ""
    mt = re.match(r"^(\d)\.(\d{2})\.(\d)$", rtime)
    if mt:
        rt = int(mt.group(1)) * 60 + int(mt.group(2)) + int(mt.group(3)) / 10
    finish = int(pos) if pos.isdigit() and 1 <= int(pos) <= 6 else ""
    return dict(pos_raw=nfkc(pos), finish=finish, boat=boat, reg=reg, name=name, motor=motor, boatno=boatno,
                exhibition=exh, course=course, st=st, st_flag=st_flag, race_time=rt)


# ---------------------------------------------------------------- B (program)
RACE_HDR_B = re.compile(r"^\s*([０-９\d]{1,2})Ｒ\s+(.*?)\s+Ｈ([０-９\d]{3,4})ｍ.*?締切予定([０-９\d]{1,2})：([０-９\d]{2})")
DATE_B = re.compile(r"([０-９\d]{4})年\s*([０-９\d]{1,2})月\s*([０-９\d]{1,2})日")


def parse_b_text(text: str):
    rows, races = [], []
    for venue, lines in split_venues(text):
        date = None
        for l in lines[:12]:
            m = DATE_B.search(l.replace("　", " "))
            if m:
                y, mo, d = (int(x.translate(FW_DIGITS)) for x in m.groups())
                date = f"{y:04d}-{mo:02d}-{d:02d}"
                break
        if date is None:
            continue
        rno = None
        for l in lines:
            m = RACE_HDR_B.match(l)
            if m:
                rno = int(m.group(1).translate(FW_DIGITS))
                hh = int(m.group(4).translate(FW_DIGITS)); mm = int(m.group(5).translate(FW_DIGITS))
                races.append(dict(date=date, venue=venue, rno=rno, name=nfkc(m.group(2)).strip(),
                                  distance=int(m.group(3).translate(FW_DIGITS)), deadline=f"{hh:02d}:{mm:02d}"))
                continue
            if rno is None:
                continue
            r = parse_b_row(l)
            if r:
                r.update(date=date, venue=venue, rno=rno)
                rows.append(r)
    return races, rows


def parse_b_row(l: str):
    # "1 3572安田政彦45兵庫51A1 6.78 53.85 8.60 80.00 47 33.33 25  0.00 33214243    11"
    if len(l) < 60 or not re.match(r"^[1-6] \d{4}", l):
        return None
    try:
        boat = int(l[0]); reg = int(l[2:6]); name = l[6:10].replace("　", "")
        age = int(l[10:12]); branch = l[12:14]; weight = int(l[14:16]); cls = l[16:18]
        # 固定幅(列がくっつくことがあるので位置で切る)
        g = [l[18:23], l[23:29], l[29:34], l[34:40], l[40:43], l[43:49], l[49:52], l[52:58]]
        rec = dict(boat=boat, reg=reg, name=name, age=age, branch=branch, weight=weight, cls=cls,
                   nat_win=float(g[0]), nat_2r=float(g[1]), loc_win=float(g[2]), loc_2r=float(g[3]),
                   motor=int(g[4]), motor_2r=float(g[5]), boatno=int(g[6]), boat_2r=float(g[7]))
        # 今節成績と早見は末尾の固定幅。生のまま保持
        rec["series_raw"] = l[58:].rstrip()
        return rec
    except Exception:
        return None


def write_rows(path: pathlib.Path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for p in sys.argv[2:]:
        p = pathlib.Path(p)
        text = read_lzh_text(p)
        if p.name.lower().startswith("k"):
            races, entries, payouts = parse_k_text(text)
            write_rows(out / "races.csv", races)
            write_rows(out / "entries.csv", entries)
            write_rows(out / "payouts.csv", payouts)
        elif p.name.lower().startswith("b"):
            races, rows = parse_b_text(text)
            write_rows(out / "program_races.csv", races)
            write_rows(out / "program.csv", rows)
