# DeciTima samples │ 初出 Phase 13
"""作業単位 13-1: `app.domain.problems.algorithm_catalog`。

テスト対象 / ドライバ / スタブ:
- 対象: `describe_algorithm` / `ALGORITHM_DESCRIPTIONS`
- ドライバ: このテスト関数
- スタブ不要 ── 対象が純粋(副作用なし)で外部依存を呼ばないため。

Phase 12 の `_ALGORITHM_DESCRIPTIONS`/`_describe`(`algorithm_recommendation.py` 内の非公開
定数)をそのまま抽出したもの。値は不変であることをここで確認する(進行のルール #12.4 の
「リファクタの写経ミス検知スモーク」── `test_algorithm_recommendation_service.py` 側は無改造の
まま再実行することで、抽出後も既存の呼び出し側の挙動が壊れていないことを別途確認する)。
"""

from __future__ import annotations

from app.algorithms.registry import all_strategies
from app.domain.problems.algorithm_catalog import ALGORITHM_DESCRIPTIONS, describe_algorithm


# (Phase 13)
def test_describe_algorithm_returns_known_description() -> None:
    assert describe_algorithm("route_planning", "dijkstra") == (
        "非負辺の単一始点最短路。手実装、既定の選択。"
    )


# (Phase 13)
def test_describe_algorithm_returns_empty_string_for_unknown_pair() -> None:
    assert describe_algorithm("route_planning", "no_such_algorithm") == ""
    assert describe_algorithm("no_such_problem_type", "dijkstra") == ""


# (Phase 13)
def test_algorithm_descriptions_cover_every_registered_strategy() -> None:
    """registry の全24 strategy に対応する説明が漏れなく存在するか(1対1対応の維持を保証)。"""
    registered_keys = {(pt, s.meta.name) for pt, s in all_strategies()}
    assert registered_keys <= ALGORITHM_DESCRIPTIONS.keys()
