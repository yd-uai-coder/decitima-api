"""OrToolsCpSatShiftStrategy(産業ソルバートラック)── OR-Tools CP-SAT で割当を解く。

手実装(Greedy / Backtracking / B&B)と**同じ `AlgorithmStrategy` 契約・同じ `ShiftSolution`**。
違うのは `implementation="library:ortools"` と、中身が CP-SAT の探索であること。仕事がソルバーの
中なので `_ops`(操作回数)は出さない ── 「ライブラリトラックは操作回数を出せない」= 2 トラック
比較の観察点(`Phase-0-4.md` / README §8)。

モデル(整数線形):
  - `x[s, t]` bool ── スタッフ s をスロット t に入れるか(eligible な組だけ変数を作る)
  - スロットごと `Σ x == required_headcount`
  - スタッフごと `Σ x · slot_hours ≤ max_weekly_hours`
  - `works_on_day[s, d]` = その日どれかのスロットに入ったか。連続 (max+1) 日窓で `Σ ≤ max`
  - 目的 = weighted_sum を整数に載せた線形式を `minimize`:
      labor_cost(minimize)  → + w · Σ x·wage·hours
      day_off_satisfaction(maximize)→ 希望休違反 `works_on_day` を + (w/希望休数) で最小化
      hour_variance(minimize)→ CP-SAT は二乗を嫌うので **勤務時間の spread(max−min)** を代理に最小化
        (手実装は本物の分散でスコアするので、両者の最適が完全一致しないことがある ── 教材の観察点)

**決定論**: `num_search_workers=1` + `random_seed` 固定 → purity テスト(同入力 → 同出力)も緑。
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.algorithms.scheduling.common import (
    eligible_staff,
    parse_shift_problem,
    shift_solution,
    slot_hours,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.shift_scheduler import Assignment  # 型は定義元から(common は関数の窓口)
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

_SCALE = 1000  # weight(小数)を整数係数にするスケール


class OrToolsCpSatShiftStrategy:
    """OR-Tools CP-SAT(implementation="library:ortools")。"""

    meta = AlgorithmMeta(
        name="cp_sat",
        family="scheduling",
        implementation="library:ortools",
        time_complexity="理論的には NP 困難、実用上は多くの規模で現実的",
        space_complexity="ソルバー依存",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_shift_problem(problem)
        model = cp_model.CpModel()

        # x[s, t]: eligible な (staff, slot) だけ変数を作る
        elig = {slot.id: eligible_staff(slot, data) for slot in data.slots}
        x: dict[tuple[str, str], cp_model.IntVar] = {}
        for slot in data.slots:
            for st in elig[slot.id]:
                x[st.id, slot.id] = model.new_bool_var(f"x_{st.id}_{slot.id}")

        # 必要人数ちょうど
        for slot in data.slots:
            vars_here = [x[st.id, slot.id] for st in elig[slot.id]]
            model.add(sum(vars_here) == slot.required_headcount)

        # 週勤務時間上限
        for st in data.staff:
            load = [
                x[st.id, slot.id] * int(slot_hours(slot))
                for slot in data.slots
                if (st.id, slot.id) in x
            ]
            if load:
                model.add(sum(load) <= int(data.max_weekly_hours))

        # works_on_day[s, d] と連続勤務日数
        days = sorted({slot.day for slot in data.slots})
        work_day: dict[tuple[str, str], cp_model.IntVar] = {}
        for st in data.staff:
            for day in days:
                slots_today = [slot for slot in data.slots if slot.day == day]
                lits = [x[st.id, s.id] for s in slots_today if (st.id, s.id) in x]
                w = model.new_bool_var(f"work_{st.id}_{day}")
                if lits:
                    model.add_max_equality(w, lits)
                else:
                    model.add(w == 0)
                work_day[st.id, day] = w
        _add_consecutive_limits(model, data, days, work_day)

        # 目的
        model.minimize(_objective(model, problem, data, x, work_day))

        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return shift_solution(None, data=data, ops=None, meta=self.meta)

        assignments: Assignment = {slot.id: [] for slot in data.slots}
        for (sid, tid), var in x.items():
            if solver.value(var):
                assignments[tid].append(sid)
        return shift_solution(assignments, data=data, ops=None, meta=self.meta)


def _add_consecutive_limits(model, data, days, work_day) -> None:
    """連続 (max_consecutive_days + 1) 日の窓ごとに Σ work_on_day ≤ max。"""
    from datetime import date

    ordinals = [date.fromisoformat(d).toordinal() for d in days]
    window = data.max_consecutive_days + 1
    for st in data.staff:
        for start in range(len(days)):
            chunk = [
                work_day[st.id, days[j]]
                for j in range(start, len(days))
                if ordinals[j] - ordinals[start] < window
            ]
            if len(chunk) == window:
                model.add(sum(chunk) <= data.max_consecutive_days)


def _objective(model, problem, data, x, work_day):
    """weighted_sum を整数線形式に。小さいほど良い(minimize)。"""
    hours = {slot.id: int(slot_hours(slot)) for slot in data.slots}
    wage = {st.id: int(round(st.hourly_wage)) for st in data.staff}
    terms: list = []

    for obj in problem.objectives:
        coeff = int(round(_SCALE * obj.weight))
        if obj.target == "labor_cost" and obj.sense == "minimize":
            terms.append(coeff * sum(var * wage[sid] * hours[tid] for (sid, tid), var in x.items()))
        elif obj.target == "day_off_satisfaction" and obj.sense == "maximize":
            offs = [
                work_day[st.id, day]
                for st in data.staff
                for day in st.requested_days_off
                if (st.id, day) in work_day
            ]
            total_requested = sum(len(st.requested_days_off) for st in data.staff)
            if offs and total_requested:
                # satisfaction = 1 − 違反 / 希望休数 → 違反を + (coeff / 希望休数) で最小化
                terms.append((coeff // total_requested) * sum(offs))
        elif obj.target == "hour_variance" and obj.sense == "minimize":
            loads = []
            for st in data.staff:
                load = model.new_int_var(0, int(data.max_weekly_hours), f"load_{st.id}")
                model.add(
                    load
                    == sum(
                        x[st.id, slot.id] * hours[slot.id]
                        for slot in data.slots
                        if (st.id, slot.id) in x
                    )
                )
                loads.append(load)
            if loads:
                hi = model.new_int_var(0, int(data.max_weekly_hours), "load_max")
                lo = model.new_int_var(0, int(data.max_weekly_hours), "load_min")
                model.add_max_equality(hi, loads)
                model.add_min_equality(lo, loads)
                terms.append(coeff * (hi - lo))  # spread は variance の代理

    return sum(terms) if terms else 0
