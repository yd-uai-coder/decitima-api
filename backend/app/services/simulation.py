"""SimulationService ── 既存 OptimizationProblem を「一部の値を変えて
複製」し、Validation → アルゴリズム選択 → solve → Verification を複数シナリオ分だけ回して
比較する。

BenchmarkService との対称性:
  Benchmark = 同じ問題 × 違うアルゴリズムを比較(「どのアルゴリズムが速い/良いか」)
  Simulation = 同じアルゴリズム × 違う問題を比較(「条件を変えたら結果がどう変わるか」)

BenchmarkService と異なり永続化を持たない ── 結果はジョブキュー(Phase 9-8)の
`Job.payload` に保持し、専用テーブルは持たない(進行のルール #17: 実消費者無しの新テーブルは
見送り)。したがって session / redis 依存が無く、`run_simulation` は素の async 関数
(呼び出し元はジョブキュー配線側の `app/worker.py::simulate_job`、Phase 10-4)。

override は RFC 7386 JSON Merge Patch(https://www.rfc-editor.org/rfc/rfc7386)相当の
汎用 dict マージ + Pydantic 再検証(`apply_overrides`)。ドメイン別の override コードは
一切増やさない ── README「スキーマ自体は不変」に最も忠実な設計(相談ログ Q53)。
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from app.algorithms.optimization.threshold_search import find_threshold
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import SolutionStatus
from app.schemas.simulation import (
    ScenarioOverride,
    ScenarioResult,
    SensitivityResult,
    SensitivitySpec,
    SimulationRequest,
    SimulationResult,
)
from app.services.algorithm_selection import select_strategy
from app.services.errors import InfeasibleProblemError, NoAlgorithmError, ProblemValidationError
from app.services.isolation import run_isolated
from app.services.timeouts import effective_timeout
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService

_validation = ProblemValidationService()
_verification = SolutionVerificationService()

# シナリオ 1 件が破綻したときに「その 1 件だけ invalid として続行する」対象の例外
_SCENARIO_ERRORS: tuple[type[Exception], ...] = (
    ValidationError,  # apply_overrides の再検証(型・値域)
    ValueError,  # apply_overrides の problem_type ガード等
    ProblemValidationError,  # Semantic Validation
    InfeasibleProblemError,  # 到達不能等
    NoAlgorithmError,  # 固定したアルゴリズムがこの override では該当なし
    TimeoutError,  # solve がタイムアウト
)

def apply_overrides(problem: OptimizationProblem, overrides: dict[str, Any]) -> OptimizationProblem:
    """problem を dict に落として overrides を深くマージし、OptimizationProblem として
    検証し直す(RFC 7386 JSON Merge Patch 相当)。ドメインを跨いだシナリオは意味を持たない
    ため problem_type の変更は禁止する。"""
    if "problem_type" in overrides:
        raise ValueError("scenario overrides must not change problem_type")
    merged = _deep_merge(problem.model_dump(mode="json"), overrides)
    return OptimizationProblem.model_validate(merged)


def _deep_merge(base: Any, patch: Any) -> Any:
    """RFC 7386 JSON Merge Patch。patch が dict でなければ base を丸ごと置き換える
    (list は要素マージせず丸ごと置換)。patch の値が None ならそのキーを削除する。"""

    # patchがdictでなければ、baseを丸ごとpatchで置き換える
    if not isinstance(patch, dict):
        return patch

    result = dict(base) if isinstance(base, dict) else {} # dictでなければ、空のdictを作る

    # dictのキー毎に深く潜って更新内容を整理していく。
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)  # null は「このキーを削除」(RFC 7386)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)  # dict 同士だけ再帰マージ
        else:
            result[key] = value  # スカラー・list は丸ごと置換
    return result


def _solve_once(
    problem: OptimizationProblem, algorithm: str | None
) -> tuple[SolutionStatus, dict[str, float], str]:
    """Validation → アルゴリズム選択 → solve → Verification を 1 回通す(同期・純粋)。
    戻り値は (status, metrics, algorithm_name)。"""
    _validation.validate(problem)
    strategy = select_strategy(problem, algorithm)
    raw = strategy.solve(problem)
    verified = _verification.verify(problem, raw)
    return verified.status, verified.metrics, strategy.meta.name


## 引数：timeout_seconds -----------------------------------------
# ruff の`flake8-async`(ASYNC109)が
# 「`async def` の引数に `timeout` という名前を使うと
# `asyncio.timeout()` コンテキストマネージャを使うべき」
# と警告するため、既存`SolveRequest.timeout_seconds` 
# と同じ命名に揃えた
# ------------------------------------------------------

async def _run_scenario(
    problem: OptimizationProblem, algorithm: str | None, timeout_seconds: float
) -> tuple[SolutionStatus, dict[str, float], str]:
    """`_solve_once` をスレッドに逃がして timeout を監視する(SolveService と同じ理由)。"""

    # 制限時間:timeout_seconds。SOLVE_ISOLATION=process なら超過時に子プロセスごと止める
    return await run_isolated(_solve_once, problem, algorithm, timeout_seconds=timeout_seconds)


async def _run_one_scenario(
    problem: OptimizationProblem, scenario: ScenarioOverride, algorithm: str, timeout_seconds: float
) -> ScenarioResult:
    try:
        merged = apply_overrides(problem, scenario.overrides)
        status, metrics, algo_name = await _run_scenario(merged, algorithm, timeout_seconds)
    except _SCENARIO_ERRORS as exc:
        return ScenarioResult(label=scenario.label, status="invalid_scenario", error=str(exc))
    return ScenarioResult(
        label=scenario.label, status=status, metrics=metrics, algorithm_name=algo_name
    )



async def run_simulation(
    request: SimulationRequest, *, timeout_seconds: float | None = None
) -> SimulationResult:
    """base problem + シナリオ群を実行し、比較結果(+ 任意で感度分析)を返す。

    シナリオ 1 件の破綻(override が invalid / infeasible / 該当アルゴリズム無し)は
    その 1 件を status="invalid_scenario" として記録するだけで全体は続行する
    (「どの条件なら、どの選択をするべきか」を支援する ── 一部が無効でも比較は続く)。
    """
    timeout_seconds = effective_timeout(timeout_seconds or request.timeout_seconds)

    # base ── override 無しの元の問題(比較の基準点)。algorithm 未指定ならここで自動選択
    # された名前を全シナリオに固定する(条件だけを変え、アルゴリズム選択の揺れを比較に
    # 混ぜないため)。
    base_status, base_metrics, base_algorithm = await _run_scenario(
        request.problem, request.algorithm, timeout_seconds
    )
    algorithm = request.algorithm or base_algorithm
    base_result = ScenarioResult(
        label="base", status=base_status, metrics=base_metrics, algorithm_name=base_algorithm
    )

    scenario_results = [
        await _run_one_scenario(request.problem, scenario, algorithm, timeout_seconds)
        for scenario in request.scenarios
    ]

    sensitivity = None
    if request.sensitivity is not None:
        sensitivity = await _run_sensitivity(
            request.problem, algorithm, timeout_seconds, request.sensitivity
        )

    return SimulationResult(base=base_result, scenarios=scenario_results, sensitivity=sensitivity)


def _set_path(path: str, value: Any) -> dict[str, Any]:
    """'data.resource_capacity' → {"data": {"resource_capacity": value}}(ドット区切りの
    dict キーのみ。list の添字は対象外 ── merge patch が list を丸ごと置換するため)。"""
    result: Any = value
    for key in reversed(path.split(".")):
        result = {key: result}
    return result


async def _run_sensitivity(
    problem: OptimizationProblem, algorithm: str, timeout_seconds: float, spec: SensitivitySpec
) -> SensitivityResult | None:
    """感度分析(閾値発見)。MVP の割り切り: 探索中に破綻した(無効な override に当たった)
    場合は比較結果(scenarios)は返しつつ感度分析だけ諦める(sensitivity=None)。"""
    evaluated: dict[int, float] = {}

    def _evaluate(param: int) -> float:
        merged = apply_overrides(problem, _set_path(spec.field_path, param))
        _, metrics, _ = _solve_once(merged, algorithm)
        value = metrics[spec.target_metric]
        evaluated[param] = value  # 二分探索が実際に訪れた点だけを記録する
        return value

    # 最大 log2(range) 回強の evaluate(=solve)を想定した余裕を timeout に持たせる
    budget = timeout_seconds * max(1, (spec.high - spec.low + 1).bit_length())
    try:
        threshold = await asyncio.wait_for(
            asyncio.to_thread(
                find_threshold,
                spec.low,
                spec.high,
                _evaluate,
                target=spec.threshold,
                mode=spec.mode,
            ),
            budget,
        )
    except (*_SCENARIO_ERRORS, KeyError):
        return None
    return SensitivityResult(threshold_value=threshold, evaluated=evaluated)
