"""Structuring ワークフロー全体で引き回される状態。

処理の流れ: テキスト -> 分類 -> シード読み込み -> objectives/constraints 抽出
-> ドメイン別 data 抽出 -> 組み立て -> 検証。条件分岐は無い一直線のパイプライン
(ドメインごとの違いはノード内部のレジストリ参照で吸収する。11-5)。

"""

from typing import Any, TypedDict

from app.domain.problems.problem import OptimizationProblem
from app.schemas.structuring import ExtractedConstraint, ExtractedObjective


class GraphState(TypedDict):
    text: str  # ユーザーの自然言語入力
    problem_type: str | None  # classify_problem_type の出力
    base_problem: OptimizationProblem | None  # load_base_problem の出力(シードの複製)
    objectives_patch: list[ExtractedObjective]  # extract_objectives_constraints の出力
    constraints_patch: list[ExtractedConstraint]  # 同上
    data_patch: dict[str, Any]  # extract_domain_data の出力
    notes: list[str]  # assemble_problem が付ける注記(例: 目的抽出なしでシード既定を維持)
    problem: OptimizationProblem | None  # assemble_problem の出力(validate_problem が検証)