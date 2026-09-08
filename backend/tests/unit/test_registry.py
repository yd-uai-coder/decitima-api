"""作業単位 1-2: AlgorithmStrategy Protocol と registry / select_strategy。"""

import pytest
from tests.fixtures.optimization import build_route_problem, build_shift_problem

from app.algorithms.base import AlgorithmStrategy
from app.algorithms.registry import REGISTRY, all_strategies, find_strategy, get_strategies
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution
from app.services.algorithm_selection import select_strategy
from app.services.errors import NoAlgorithmError


class _FakeStrategy:
    """Protocol は継承不要 ── meta と solve を持てば AlgorithmStrategy として通る。"""

    meta = AlgorithmMeta(name="fake", family="graph", implementation="handwritten")

    def solve(self, problem):  # noqa: ANN001, ANN201
        return CandidateSolution(
            status="valid",
            assignments=RouteSolution(path_node_ids=[], path_edge_ids=[], total_weight=0.0),
            produced_by=self.meta,
        )

# @pytest.fixture は、pytestのテストで使う「テスト用の準備処理」を定義するためのデコレータ
# 「テストを実行する前に、REGISTRY にフェイクの戦略を登録しておき、テストが終わったら元に戻す」
# 以降のtest関数でroute_has_fakeを呼び出すとフェイクを差し込んだREGISTRYをテストに使用できる・
@pytest.fixture
def route_has_fake(monkeypatch: pytest.MonkeyPatch) -> _FakeStrategy:
    """REGISTRY["route_planning"] にフェイク1件を差し込んだ状態(テスト後は自動で戻る)。"""
    fake = _FakeStrategy()
    monkeypatch.setitem(REGISTRY, "route_planning", [fake])
    return fake

# _FakeStrategyがmetaとsolveを持つので、AlgorithmStrategyの型と合う事を確認
def test_fake_conforms_to_protocol() -> None:
    # @runtime_checkable なので isinstance が使える。名前の存在しか見ない点に注意
    assert isinstance(_FakeStrategy(), AlgorithmStrategy)

# get_strategiesがRegistryからproblem_typeのアルゴリズム一覧を読み込んでいる事を確認
def test_get_strategies_returns_registered_candidates(route_has_fake: _FakeStrategy) -> None:
    assert route_has_fake in get_strategies("route_planning")
    assert get_strategies("unknown_type") == []

# all_strategiesが(problem_typeとアルゴリズム一覧のペア)の一覧を返す事を確認
def test_all_strategies_returns_pairs(route_has_fake: _FakeStrategy) -> None:
    pairs = all_strategies()
    assert ("route_planning",) not in pairs  # ペアであってタプル1要素ではない
    assert ("route_planning", route_has_fake) in pairs


# build_route_problemはselect_strategyにOptimizationProblemを渡すためのフェイク
# OptimizationProblemの中を確認したいわけではないのでbuild_route_problemの引数は空で良い
# select_strategyの戻りは下記2つのテストにおいては_FakeStrategy
def test_select_strategy_default_returns_first_candidate(route_has_fake: _FakeStrategy) -> None:
    assert select_strategy(build_route_problem()).meta.name == "fake"


def test_select_strategy_honors_requested_name(route_has_fake: _FakeStrategy) -> None:
    assert select_strategy(build_route_problem(), requested="fake").meta.name == "fake"


def test_select_strategy_unknown_requested_raises(route_has_fake: _FakeStrategy) -> None:
    with pytest.raises(NoAlgorithmError):
        select_strategy(build_route_problem(), requested="a_star")

# shift_schedulingを用意したのでNoAlgorithmErrorは出ない->テストを無効化する
# def test_select_strategy_unregistered_problem_type_raises() -> None:
#     # shift_scheduling はまだ登録アルゴリズムが無い(Phase 5)
#     with pytest.raises(NoAlgorithmError):
#         select_strategy(build_shift_problem())

def test_select_strategy_no_candidates_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Phase 6 で全 problem_type に strategy が付いた。「候補ゼロ → NoAlgorithmError」は
    # registry キーを空にして確認する(Phase 5 までは shift が空だったのでそれを使っていた)。
    monkeypatch.setitem(REGISTRY, "shift_scheduling", [])
    with pytest.raises(NoAlgorithmError):
        select_strategy(build_shift_problem())


def test_find_strategy_name_mismatch_returns_none(route_has_fake: _FakeStrategy) -> None:
    # 候補はあるが requested 名が一致しない → 送出せず None(next(..., None) の分岐)
    assert find_strategy(build_route_problem(), requested="nope") is None


def test_find_strategy_empty_candidates_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # 候補ゼロでも送出せず None(送出は services 層の select_strategy の役割)
    monkeypatch.setitem(REGISTRY, "route_planning", [])
    assert find_strategy(build_route_problem()) is None
