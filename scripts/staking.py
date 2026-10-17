"""賭け金決定(1レース分)。

方針(シミュレーション kelly_sim の結果より):
- 選ぶ: 較正済み確率 p × 購入時オッズ O × 確定/購入時オッズ比 r が閾値 tau を超える買い目
- 額  : 既定は 100円固定。資金10万円・平均オッズが高い買い目では、比率を上げると破綻確率が急増し、
        ケリーは推定誤差の大きい買い目に厚く張るため、真の優位性が小さいと回収率を下げた。
- ケリーを使うのは「較正係数 lam を学習外データで推定済み」かつ「1/4ケリーが100円を十分上回る」場合だけ。
  その場合も 1点 1%・1レース 2%・売上規模による絶対上限 で抑える。

すべて関数は純粋関数。資金や停止判定は呼び出し側(運用ループ)で管理する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

TAKE = 0.75
UNIT = 100  # 舟券の最小単位(円)


@dataclass
class StakeConfig:
    mode: str = "flat"            # "flat" | "kelly"
    tau: float = 1.10             # 期待値の閾値
    flat_amount: int = 100        # flat のときの1点の額
    kelly_fraction: float = 0.25  # ケリーの何分の1か
    lam: float = 0.3              # 自前確率を市場確率へ縮める係数(学習外で推定した較正係数)
    cap_bet: float = 0.01         # 1点の上限(資金比)
    cap_race: float = 0.02        # 1レース合計の上限(資金比)
    abs_cap: int = 5000           # 1点の絶対上限(円)。売上規模でオッズが崩れるのを防ぐ
    max_odds: float | None = 50.0 # これより高いオッズは買わない(分散が大きすぎる)
    min_kelly_yen: int = 200      # 1/4ケリーの額がこれ未満なら flat に落とす


def market_probs(odds: dict[str, float]) -> dict[str, float]:
    inv = {k: 1.0 / o for k, o in odds.items() if o and o > 0}
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()}


def simultaneous_kelly(p: dict[str, float], odds: dict[str, float]) -> dict[str, float]:
    """排他的な結果(同じレースの買い目)に対する同時ケリー。Smoczynski & Tomkins (2010)。
    返り値は資金に対する比率。"""
    items = sorted(((k, p[k], odds[k]) for k in p if k in odds and odds[k] > 0),
                   key=lambda t: t[1] * t[2], reverse=True)
    chosen, sp, sq, R = [], 0.0, 0.0, 1.0
    for k, pk, ok in items:
        if pk * ok <= R:
            break
        chosen.append((k, pk, ok))
        sp += pk; sq += 1.0 / ok
        if sq >= 1.0:
            break
        R = (1.0 - sp) / (1.0 - sq)
    return {k: max(pk - R / ok, 0.0) for k, pk, ok in chosen}


def decide(p_model: dict[str, float], odds_now: dict[str, float], bank: int,
           cfg: StakeConfig = StakeConfig(), drift: dict[str, float] | None = None) -> dict[str, int]:
    """1レースの買い目と額を返す {組番: 円}。

    p_model : 自前モデルの確率(較正前)
    odds_now: 購入判断時点のオッズ
    drift   : 組番ごとの (確定オッズ/購入時オッズ) の推定値。無ければ 1.0
    """
    q = market_probs(odds_now)
    drift = drift or {}
    eff_odds = {k: o * drift.get(k, 1.0) for k, o in odds_now.items()}
    p_cal = {k: q[k] + cfg.lam * (p_model.get(k, q[k]) - q[k]) for k in q}
    sel = [k for k in q
           if p_model.get(k, 0) * eff_odds[k] > cfg.tau and (cfg.max_odds is None or eff_odds[k] <= cfg.max_odds)]
    if not sel or bank < UNIT:
        return {}
    stakes: dict[str, int] = {}
    if cfg.mode == "kelly":
        f = simultaneous_kelly({k: p_cal[k] for k in q}, eff_odds)
        for k in sel:
            amt = min(f.get(k, 0.0) * cfg.kelly_fraction, cfg.cap_bet) * bank
            amt = min(amt, cfg.abs_cap)
            amt = math.floor(amt / UNIT) * UNIT
            stakes[k] = amt if amt >= cfg.min_kelly_yen else cfg.flat_amount
    else:
        for k in sel:
            stakes[k] = cfg.flat_amount
    # 1レース上限
    lim = math.floor(bank * cfg.cap_race / UNIT) * UNIT
    tot = sum(stakes.values())
    if tot > lim:
        if lim < UNIT:
            return {}
        # 期待値の高い順に上限まで残す
        order = sorted(stakes, key=lambda k: p_cal[k] * eff_odds[k], reverse=True)
        kept, acc = {}, 0
        for k in order:
            a = min(stakes[k], lim - acc)
            a = math.floor(a / UNIT) * UNIT
            if a >= UNIT:
                kept[k] = a; acc += a
        stakes = kept
    return {k: v for k, v in stakes.items() if v >= UNIT}


@dataclass
class Guard:
    """運用ループ側の停止判定(ルールDBと同じ値)。"""
    start_bank: int
    peak: int = 0
    stop_dd: float = 0.40       # ピークから -40% で紙上に戻す
    stop_total: float = 0.50    # 総資金 -50% で撤退
    daily_loss_cap: float = 0.05
    day_start_bank: int = 0
    history: list = field(default_factory=list)

    def update(self, bank: int) -> str:
        self.peak = max(self.peak or bank, bank)
        if bank <= self.start_bank * (1 - self.stop_total):
            return "撤退"
        if bank <= self.peak * (1 - self.stop_dd):
            return "紙上に戻す"
        if self.day_start_bank and bank <= self.day_start_bank * (1 - self.daily_loss_cap):
            return "本日停止"
        return "継続"


if __name__ == "__main__":
    # 簡単な自己テスト
    odds = {"1-2": 3.1, "1-3": 4.5, "2-1": 12.0, "1-4": 9.8, "3-1": 25.0}
    pm = {"1-2": 0.30, "1-3": 0.22, "2-1": 0.06, "1-4": 0.12, "3-1": 0.03}
    print("flat :", decide(pm, odds, 100_000))
    print("kelly:", decide(pm, odds, 100_000, StakeConfig(mode="kelly")))
    f = simultaneous_kelly(pm, odds)
    print("kelly fractions:", {k: round(v, 4) for k, v in f.items()})
    g = Guard(start_bank=100_000); print(g.update(100_000), g.update(58_000), g.update(49_000))
