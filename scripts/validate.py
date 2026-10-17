"""Cross-check parsed K data.

1. 各会場冒頭の[払戻金]一覧(3連単/3連複/2連単/2連複)と、レース毎の払戻欄が一致するか
2. 着順(1-2-3着の艇番)と3連単の的中組番が一致するか
Usage: python validate.py PARSED_DIR LZH_FILES...
"""
import re, sys, pathlib, collections
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from parse_lzh import read_lzh_text, split_venues, DATE_K

SUM = re.compile(r"^\s{8,}(\d{1,2})R\s+(.*)$")
ITEM = re.compile(r"(\d-\d(?:-\d)?)\s+(\d+)|(特払い)\s+(\d+)|(不成立|発売なし|返還)")


def summary_table(paths):
    rows = []
    for p in paths:
        for venue, lines in split_venues(read_lzh_text(p)):
            date = None
            for l in lines[:12]:
                m = DATE_K.search(l)
                if m:
                    date = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"; break
            in_tbl = False
            for l in lines:
                if "[払戻金]" in l:
                    in_tbl = True; continue
                if in_tbl:
                    m = SUM.match(l)
                    if not m:
                        if l.strip() == "" and rows and rows[-1]["venue"] == venue:
                            break
                        continue
                    rno = int(m.group(1))
                    # 固定幅: 3連単, 3連複, 2連単, 2連複 の4列
                    body = m.group(2)
                    cells = re.findall(r"(\d-\d(?:-\d)?)\s+(\d+)|(不成立|発売なし|特払い\s+\d+)", body)
                    for bet, (c, a, other) in zip(["trifecta", "trio", "exacta", "quinella"], cells):
                        if c:
                            rows.append(dict(date=date, venue=venue, rno=rno, bet=bet, combo=c, amount=int(a)))
    return pd.DataFrame(rows)


def main():
    d = pathlib.Path(sys.argv[1]); paths = [p for p in sys.argv[2:] if pathlib.Path(p).name.lower().startswith("k")]
    pay = pd.read_csv(d / "payouts.csv", dtype={"venue": str, "combo": str})
    ent = pd.read_csv(d / "entries.csv", dtype={"venue": str})
    races = pd.read_csv(d / "races.csv", dtype={"venue": str})
    pay["venue"] = pay["venue"].str.zfill(2); ent["venue"] = ent["venue"].str.zfill(2); races["venue"] = races["venue"].str.zfill(2)
    summ = summary_table(paths)
    key = ["date", "venue", "rno", "bet", "combo"]
    m = summ.merge(pay[pay.bet.isin(["trifecta", "trio", "exacta", "quinella"])], on=key, how="left", suffixes=("_sum", "_race"))
    mismatch = m[m.amount_sum != m.amount_race]
    print(f"races={len(races)} entries={len(ent)} payouts={len(pay)} summary_items={len(summ)}")
    print(f"summary vs race payout mismatches: {len(mismatch)}")
    if len(mismatch):
        print(mismatch.head(10).to_string())
    # 着順 vs 3連単
    top = ent[ent.finish.isin([1, 2, 3])].sort_values("finish").groupby(["date", "venue", "rno"])["boat"].apply(lambda s: "-".join(map(str, s)) if len(s) == 3 else None).dropna()
    tri = pay[pay.bet == "trifecta"].groupby(["date", "venue", "rno"])["combo"].apply(set)
    j = pd.concat([top.rename("order"), tri.rename("tri")], axis=1, join="inner")
    bad = j[[o not in t for o, t in zip(j.order, j.tri)]]
    print(f"finish order vs trifecta: compared={len(j)} mismatches={len(bad)}")
    if len(bad):
        print(bad.head(10).to_string())
    # 3連単の払戻が無いレース
    no_tri = races.merge(tri.rename("combo").reset_index(), on=["date", "venue", "rno"], how="left")
    print("races without trifecta payout:", int(no_tri.combo.isna().sum()), "| special:",
          collections.Counter(races.special.dropna()).most_common(5))


if __name__ == "__main__":
    main()
