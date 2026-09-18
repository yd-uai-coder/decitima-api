"""`LlmOnly*Strategy` 6 本が共有するプロンプト部品と `AlgorithmMeta`。

目的・制約は6ドメイン共通の形(`Objective`/`AnyConstraint`)を持つので、自然言語化はここに
1本化する(ドメイン別データのカタログ化だけが各 `*_llm.py` の担当)。
`catalog_entries`(id/name カタログを渡して grounding させる)と同じ狙い ── 「実在する id
だけを使わせる」。
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, create_model
from app.domain.problems.problem import (
    ForbiddenConstraint,
    GenericConstraint,
    NumericBoundConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
    StaffingConstraint,
)
from app.domain.solutions.solution import AlgorithmMeta

# 6 クラス共通の meta。REGISTRY には登録しないので `(problem_type, name)` の衝突は起きない
# (Phase 12 の教訓 ── name 単体キーだと衝突するが、比較専用リストは problem_type ごとに
# 1 エントリしか持たないため単純な dict のキーにできる)。
LLM_ONLY_META = AlgorithmMeta(name="llm_only", family="llm", implementation="llm")


def render_objectives(problem: OptimizationProblem) -> str:
    """目的を自然言語化する。"""
    return (
        "\n".join(f"- {o.sense} {o.target}(重み {o.weight})" for o in problem.objectives)
        or "(目的なし)"
    )


def render_constraints(problem: OptimizationProblem) -> str:
    """制約を自然言語化する。kind ごとに意味が違うので isinstance で分岐する。"""
    if not problem.constraints:
        return "(制約なし)"
    lines: list[str] = []
    for c in problem.constraints:
        if isinstance(c, NumericBoundConstraint):
            lines.append(f"- [{c.severity}] {c.field} {c.operator} {c.value}")
        elif isinstance(c, RequiredInclusionConstraint):
            lines.append(f"- [{c.severity}] 必ず含める: {c.items}")
        elif isinstance(c, ForbiddenConstraint):
            lines.append(f"- [{c.severity}] 使用禁止: {c.items}")
        elif isinstance(c, StaffingConstraint):
            lines.append(f"- [{c.severity}] 各スロットの必要人数を満たす")
        elif isinstance(c, GenericConstraint):
            lines.append(f"- [{c.severity}] {c.kind}: {c.description or '(説明なし)'}")
    return "\n".join(lines)


def strip_problem_type(schema: type[BaseModel]) -> type[BaseModel]:
    """LLM に渡す構造化出力スキーマから判別子フィールド problem_type を除く。

    `Literal[...] = "..."` のような単一値フィールドは Pydantic の JSON Schema では
    `"const"` になるが、Gemini の構造化出力(`response_json_schema`)は `const` を
    サポートしないため制約が失われ、LLM が任意の文字列を埋めてしまう
    (実測: `RouteSolution` で `"shortest_path"` のような無関係な値を生成)。
    最初から見せず、各 `*_llm.py` の `solve()` 側で固定値を足し戻す。
    """
    # fields: Any にしておく ── create_model の **kwargs 展開はキーワードごとに違う型
    # (str/tuple/ConfigDict 等)を取るため、動的な dict を渡すと pyright が静的に解決できない
    # (Pydantic 公式でも既知の制限)。動的生成そのものが目的の関数なので Any で割り切る。
    fields: dict[str, Any] = {
        name: (field.annotation, field)
        for name, field in schema.model_fields.items()
        if name != "problem_type"
    }
    return create_model(f"{schema.__name__}Llm", **fields)
