"""BacktrackingShiftStrategy(バックトラッキング)── スロット順に、入れられるスタッフの組を試す DFS。

枝刈り:
  - 週勤務時間が上限を超える組は選ばない
  - 連続勤務日数が上限を超える組は選ばない(sliding_window の逐次判定)
全スロットが埋まったら objectives の重み付き和でスコアし、最良を保持する。

小規模なら最適(探索しきる)。規模が増えると最悪 O(kⁿ) ── Phase 6-6 でその破綻を実測する。
`_ops` = 展開したノード数(スロット × 試した組)。
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
from app.domain.problems.shift_scheduler import ShiftData, Staff
from app.domain.solutions.shift_scheduler import Assignment
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class BacktrackingShiftStrategy:
    """手実装のバックトラッキング(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="backtracking",
        family="scheduling",
        implementation="handwritten",
        time_complexity="最悪 O(kⁿ)、枝刈りで大幅減",
        space_complexity="O(スロット数)(再帰の深さ)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_shift_problem(problem)
        search = _Search(problem, data)
        search.run()
        return shift_solution(search.best, data=data, ops=search.ops, meta=self.meta)


class _Search:
    """再帰の状態を持ち回るヘルパ(solve から 1 回だけ生成)。"""

    def __init__(self, problem: OptimizationProblem, data: ShiftData) -> None:
        self._problem = problem
        self._data = data
        self._slots = sorted(data.slots, key=lambda s: s.id)
        self._eligible = {s.id: eligible_staff(s, data) for s in self._slots}
        self.best: Assignment | None = None
        self.best_score = float("inf")
        self.ops = 0
        # 逐次追跡する状態(apply/undo でロールバック)
        self._hours: dict[str, float] = {st.id: 0.0 for st in data.staff}
        self._day_count: dict[str, dict[int, int]] = {st.id: {} for st in data.staff}

    def run(self) -> None:
        self._recurse(0, {})

    def _recurse(self, i: int, assignments: Assignment) -> None:
        if i == len(self._slots):
            s, _metrics = score(self._problem, self._data, assignments)
            if s < self.best_score:
                self.best_score = s
                self.best = {k: list(v) for k, v in assignments.items()}
            return

        slot = self._slots[i]
        length = slot_hours(slot)
        day_ord = to_ordinal(slot.day)
        for combo in combinations(self._eligible[slot.id], slot.required_headcount):
            self.ops += 1
            if not self._can_take(combo, length, day_ord):
                continue
            self._apply(combo, length, day_ord, +1)
            assignments[slot.id] = [st.id for st in combo]
            self._recurse(i + 1, assignments)
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
