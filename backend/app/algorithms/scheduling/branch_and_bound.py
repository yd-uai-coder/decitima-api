"""BranchAndBoundShiftStrategy(分枝限定法)── バックトラッキング + 下界で枝刈り + 決定論的 anytime。

Backtracking との差:
  1. **下界(lower bound)**: 部分割当の時点で「これ以上どう頑張っても score はこの値未満にならない」
     楽観的な推定を計算し、現在の最良解 以上なら subtree を丸ごと切る。
     ここでは additive で支配的な `labor_cost` に楽観推定(残りスロットを最安スタッフで埋めた場合)を
     使い、maximize 目的は metric ≤ 1 とみて −w、他は 0 と見積もる(admissible = 真の最小以下)。
  2. **決定論的 anytime**: `solve` は純粋関数の契約(時刻を読まない)を守るため、壁時計ではなく
     **展開ノード数の予算** `_MAX_NODES` で打ち切る。予算切れ時はその時点の最良解を
     `metrics["_truncated"]=1.0` 付きで返す(`Phase-0-5.md` §5.1 の宿題の結論)。壁時計の
     `SOLVE_TIMEOUT_SECONDS` は `SolveService` 側の安全網のまま。

`_ops` = 展開ノード数 + 下界計算数。
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

from app.algorithms.patterns.sliding_window import run_length_at, to_ordinal
from app.algorithms.scheduling.common import (
    eligible_staff,
    parse_shift_problem,
    score,
    shift_solution,
    slot_hours,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff
from app.domain.solutions.shift_scheduler import Assignment
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

# 決定論的なノード予算。これを超えたら最良解 + _truncated で打ち切る。
_MAX_NODES = 200_000


class BranchAndBoundShiftStrategy:
    """手実装の分枝限定法(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="branch_and_bound",
        family="scheduling",
        implementation="handwritten",
        time_complexity="最悪 O(kⁿ)、下界で枝刈り",
        space_complexity="O(スロット数)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_shift_problem(problem)
        search = _BnbSearch(problem, data)
        search.run()
        return shift_solution(
            search.best, data=data, ops=search.ops, meta=self.meta, truncated=search.truncated
        )


class _BnbSearch:
    def __init__(self, problem: OptimizationProblem, data: ShiftData) -> None:
        self._problem = problem
        self._data = data
        self._slots = sorted(data.slots, key=lambda s: s.id)
        self._eligible = {s.id: eligible_staff(s, data) for s in self._slots}
        # スロットごとの「最安で埋めた場合のコスト」── 下界の残余分に使う
        self._cheapest = {s.id: _cheapest_fill_cost(s, self._eligible[s.id]) for s in self._slots}
        self._suffix_cheapest = _suffix_sums([self._cheapest[s.id] for s in self._slots])

        self.best: Assignment | None = None
        self.best_score = float("inf")
        self.ops = 0
        self.truncated = False
        self._hours: dict[str, float] = {st.id: 0.0 for st in data.staff}
        self._day_count: dict[str, dict[int, int]] = {st.id: {} for st in data.staff}

    def run(self) -> None:
        self._recurse(0, {}, partial_labor=0.0)

    def _recurse(self, i: int, assignments: Assignment, partial_labor: float) -> None:
        if self.ops >= _MAX_NODES:
            self.truncated = True
            return
        if i == len(self._slots):
            s, _metrics = score(self._problem, self._data, assignments)
            if s < self.best_score:
                self.best_score = s
                self.best = {k: list(v) for k, v in assignments.items()}
            return

        # 下界: labor_cost の楽観推定(残りを最安で埋める)。現最良を超えられないなら subtree を切る
        self.ops += 1
        lower = _lower_bound(self._problem, partial_labor + self._suffix_cheapest[i])
        if lower >= self.best_score:
            return

        slot = self._slots[i]
        length = slot_hours(slot)
        day_ord = to_ordinal(slot.day)
        for combo in combinations(self._eligible[slot.id], slot.required_headcount):
            self.ops += 1
            if self.ops >= _MAX_NODES:
                self.truncated = True
                return
            if not self._can_take(combo, length, day_ord):
                continue
            self._apply(combo, length, day_ord, +1)
            assignments[slot.id] = [st.id for st in combo]
            self._recurse(i + 1, assignments, partial_labor + _combo_cost(combo, length))
            del assignments[slot.id]
            self._apply(combo, length, day_ord, -1)

    def _can_take(self, combo: Sequence[Staff], length: float, day_ord: int) -> bool:
        for st in combo:
            if self._hours[st.id] + length > self._data.max_weekly_hours:
                return False
            present = set(self._day_count[st.id]) | {day_ord}
            if run_length_at(present, day_ord) > self._data.max_consecutive_days:
                return False
        return True

    def _apply(self, combo: Sequence[Staff], length: float, day_ord: int, sign: int) -> None:
        for st in combo:
            self._hours[st.id] += sign * length
            counter = self._day_count[st.id]
            counter[day_ord] = counter.get(day_ord, 0) + sign
            if counter[day_ord] <= 0:
                counter.pop(day_ord, None)


def _combo_cost(combo: Sequence[Staff], length: float) -> float:
    return sum(st.hourly_wage * length for st in combo)


def _cheapest_fill_cost(slot: ShiftSlot, eligible: Sequence[Staff]) -> float:
    """slot を最安スタッフ required_headcount 人で埋めたときの人件費(埋められないなら 0)。"""
    length = slot_hours(slot)
    take = [st.hourly_wage for st in eligible[: slot.required_headcount]]
    return sum(w * length for w in take)


def _suffix_sums(values: list[float]) -> list[float]:
    """suffix[i] = values[i:] の和。長さ len(values)+1(末尾 0)。"""
    out = [0.0] * (len(values) + 1)
    for i in range(len(values) - 1, -1, -1):
        out[i] = out[i + 1] + values[i]
    return out


def _lower_bound(problem: OptimizationProblem, optimistic_labor: float) -> float:
    """weighted_sum(小さいほど良い)の admissible な下界。

    - labor_cost 目的(minimize): final ≥ optimistic_labor なので寄与 ≥ w · optimistic_labor
    - その他の minimize 目的(hour_variance 等、metric ≥ 0): 寄与 ≥ 0
    - maximize 目的(day_off_satisfaction、metric ≤ 1): 寄与 = −w·metric ≥ −w
    weight ≥ 0 を前提。真の最小 score を決して上回らない。
    """
    lb = 0.0
    for o in problem.objectives:
        if o.target == "labor_cost" and o.sense == "minimize":
            lb += o.weight * optimistic_labor
        elif o.sense == "maximize":
            lb -= o.weight
    return lb
