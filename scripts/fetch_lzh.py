"""Download official boatrace result (K) and program (B) LZH files.

Usage: python fetch_lzh.py START(YYYY-MM-DD) END(YYYY-MM-DD) OUTDIR
Polite: one request every ~1.5 s, 3 retries, 404 is recorded and skipped.
"""
import sys, time, datetime as dt, urllib.request, urllib.error, pathlib

BASE = "https://www1.mbrace.or.jp/od2/{kind}/{ym}/{k}{ymd}.lzh"
UA = {"User-Agent": "Mozilla/5.0 (personal research; low rate)"}


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def main():
    start = dt.date.fromisoformat(sys.argv[1]); end = dt.date.fromisoformat(sys.argv[2])
    out = pathlib.Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
    missing = []
    d = start
    while d <= end:
        for kind in ("K", "B"):
            name = f"{kind.lower()}{d:%y%m%d}.lzh"
            dest = out / name
            if dest.exists():
                continue
            data = get(BASE.format(kind=kind, ym=f"{d:%Y%m}", k=kind.lower(), ymd=f"{d:%y%m%d}"))
            if data is None:
                missing.append(name)
            else:
                dest.write_bytes(data)
            time.sleep(1.5)
        d += dt.timedelta(days=1)
    (out / "missing.txt").write_text("\n".join(missing) + ("\n" if missing else ""))
    print(f"done {start}..{end}: missing {len(missing)}")


if __name__ == "__main__":
    main()
