"""solve / algorithms / solutions API のリクエスト・レスポンススキーマ。

app/domain/ のモデルを import して薄く包む
(HTTP 境界の型 = schemas、システム内部の共通言語 = domain。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution, ConstraintViolation


class SolveRequest(BaseModel):
    """solve API のリクエスト。構造化済みの問題と、任意のアルゴリズム指定。"""

    problem: OptimizationProblem  # domain のモデルをそのまま受ける
    algorithm: str | None = None  # 指定なければ rule-based 選択
    persist: bool = True  # False なら結果を保存しない(教材の試行用)
    timeout_seconds: float | None = Field(default=None, gt=0)  # 上限は services/timeouts.py が settings.SOLVE_TIMEOUT_SECONDS で頭打ちにする


class SolveResponse(BaseModel):
    """solve API のレスポンス。検証済みの解と、永続化された場合の ID。"""

    solution: CandidateSolution
    problem_id: uuid.UUID | None = None
    solution_id: uuid.UUID | None = None


class VerifyRequest(BaseModel):
    """verify API のリクエスト。検証したい問題と、その候補解のペア。"""

    problem: OptimizationProblem
    solution: CandidateSolution


class VerifyResponse(BaseModel):
    """verify API のレスポンス。検証後の status / 違反一覧 / metrics のみを返す
    (解そのものはクライアントが送ってきたものなので返さない)。"""

    status: str  # "valid" | "invalid" | "infeasible"
    violations: list[ConstraintViolation]
    metrics: dict[str, float]


class AlgorithmInfo(BaseModel):
    """registry に登録された 1 アルゴリズムの公開情報。"""

    name: str
    family: str
    implementation: str
    problem_types: list[str]  # この (name, implementation) が登録されている problem_type
    time_complexity: str | None = None


class AlgorithmListResponse(BaseModel):
    algorithms: list[AlgorithmInfo]


class SolutionRead(BaseModel):
    """永続化された解 1 件の読み出し。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    problem_id: uuid.UUID
    status: str
    algorithm_name: str
    algorithm_implementation: str
    created_at: datetime
    payload: dict  # CandidateSolution.model_dump(mode="json") の全体


class ProblemRead(BaseModel):
    """永続化された問題 1 件の読み出し。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    problem_type: str
    created_at: datetime
    payload: dict  # OptimizationProblem.model_dump(mode="json") の全体

# -----------------------------------------
# Benchmark
# -----------------------------------------

class BenchmarkRequest(BaseModel):
    """benchmark API のリクエスト。1 問題を複数アルゴリズムで解いて比較する。"""

    problem: OptimizationProblem
    # algorithms: None なら problem_type の全候補。指定すれば meta.name でフィルタ
    algorithms: list[str] | None = None
    runs: int = Field(default=3, ge=1, le=20)  # 中央値を取る試行回数
    persist: bool = True  # False なら benchmark_runs に保存しない
    timeout_seconds: float | None = Field(default=None, gt=0)  # 1 run あたりの上限


class BenchmarkEntry(BaseModel):
    """1 アルゴリズムの測定結果 1 件。time / memory は直接比較できるが、
    operation_count はアルゴリズム定義の単位(Dijkstra=heap pop 数、
    BruteForce=展開した部分パス数)なので「内部仕事量」としてのみ読む。"""

    algorithm: AlgorithmMeta
    solution_status: str  # "valid" | "invalid" | "infeasible"
    metrics: dict[str, float]  # solve が返した metrics(total_weight / _ops 等)
    elapsed_ms_median: float
    elapsed_ms_p25: float
    elapsed_ms_p75: float
    peak_memory_kb: float
    operation_count: int | None = None  # metrics["_ops"]。数えていなければ None
    hard_violations: int  # Verification が付けた hard 違反の件数
    soft_violations: int
    # quality_ratio: 目的関数値 / この run 中の最良値(Phase 3-4)。目的が metrics に
    # 無ければ None。1.0 なら最良(オラクルと同値)
    quality_ratio: float | None = None


class BenchmarkResponse(BaseModel):
    """benchmark API のレスポンス。アルゴリズム横並びの entries と、保存した場合の ID。"""

    entries: list[BenchmarkEntry]
    benchmark_id: uuid.UUID | None = None


class BenchmarkRunRead(BaseModel):
    """永続化されたベンチマーク実行 1 件の読み出し。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    problem_type: str
    created_at: datetime
    payload: dict  # {"problem": ..., "entries": [...], "runs": N}
