"""Sliding Window(スライディングウィンドウ)── プリミティブ。

「連続する区間を窓としてスキャンし、条件が壊れたら窓を縮める / リセットする」技法。
Shift Scheduler では **連続勤務日数**の判定に使う:

- `max_consecutive_days` … 完成した勤務日集合の最長連続日数(窓 = 途切れない暦日の並び)。
  事後検証は Phase 2 の `structure._longest_consecutive_run`(`itertools.pairwise` の 1 回スキャン)が
  担当しており、こちらは **探索中の逐次判定**用に別に置く(Backtracking が使う)。
- `run_length_at` … ある日 d を勤務日に加えたとき、d を含む連続ランの長さ。窓を d から左右へ
  広げるだけなので O(ラン長)。Backtracking が「この 1 手で連続勤務日数が上限を超えるか」を
  毎手 O(1)〜O(K) で判定するのに使う。

registry には載らない。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def _ordinals(days: Iterable[str | date]) -> list[int]:
    """ISO 日付 or date を「日単位の序数」に。連続日は差 1 になる。"""
    return sorted((d if isinstance(d, date) else date.fromisoformat(d)).toordinal() for d in days)


def max_consecutive_days(days: Iterable[str | date]) -> int:
    """勤務日集合の最長連続日数。窓 = 途切れない暦日の並び。空なら 0。"""
    ords = _ordinals(days)
    if not ords:
        return 0
    longest = run = 1

    # 日付の配列から「隣り合う2つの日付」をペアにする(prev:前日、cur:当日)
    for prev, cur in zip(ords, ords[1:], strict=False):
        run = run + 1 if cur - prev == 1 else 1  # 途切れたら窓をリセット
        longest = max(longest, run)
    return longest


def run_length_at(present_ordinals: set[int], point: int) -> int:
    """present_ordinals に point が在るとして、point を含む連続ランの長さ。

    窓を point から左右に広げる ── O(ラン長)。Backtracking の逐次チェック用。
    """
    length = 1
    left = point - 1
    while left in present_ordinals:
        length += 1
        left -= 1
    right = point + 1
    while right in present_ordinals:
        length += 1
        right += 1
    return length


def to_ordinal(day: str | date) -> int:
    """ISO 日付 or date → 日単位の序数(`run_length_at` に渡す前の変換用)。"""
    return (day if isinstance(day, date) else date.fromisoformat(day)).toordinal()
