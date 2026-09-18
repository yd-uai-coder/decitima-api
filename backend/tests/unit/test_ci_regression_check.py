# DeciTima samples │ 作業単位 15-10
"""`scripts/ci_regression_check.py` の単体テスト。

対象: `_measure_one`(実測1件分の組み立て)/ `_TARGETS`(対象一覧)/
`_REGRESSION_RATIO_THRESHOLD`(閾値定数)。ドライバ: このテスト関数。
スタブ不要 ── 対象の strategy はいずれも純粋で外部依存(DB/Redis/LLM)を呼ばないため、
実際に(小規模な)問題を解かせて実測する。
"""

from scripts.ci_regression_check import _REGRESSION_RATIO_THRESHOLD, _TARGETS, _measure_one


def test_targets_cover_three_distinct_problem_types() -> None:
    problem_types = {pt for pt, _ in _TARGETS}
    assert problem_types == {"route_planning", "travel_planning", "project_scheduling"}


def test_measure_one_returns_benchmark_entry_shape() -> None:
    problem_type, strategy = _TARGETS[0]
    entry = _measure_one(problem_type, strategy)

    assert entry["algorithm"]["name"] == strategy.meta.name
    assert entry["elapsed_ms_median"] >= 0
    assert entry["peak_memory_kb"] >= 0


def test_regression_threshold_is_a_sane_multiplier() -> None:
    # 1.0 未満だとほぼ全ての実測が「回帰」扱いになりCIが常に赤くなる
    assert _REGRESSION_RATIO_THRESHOLD > 1.0
