"""AlgorithmStrategy ── すべての「問題まるごとを解く」アルゴリズムが満たす契約。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

@runtime_checkable
class AlgorithmStrategy(Protocol):
    """1つのアルゴリズムが満たす契約。problem を受けて候補解を返すだけ。"""

    meta: AlgorithmMeta

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        """OptimizationProblem を決定論的に解いて CandidateSolution を返す。検証はしない。"""
        ...
