"""ProblemValidationService ── 問題定義の妥当性(Algorithm Engine に渡す前)。

- Input Validation(型・値域)は Pydantic の Field 制約が既に担う(route_planner.py の
  weight=Field(ge=0) 等)。
- Semantic Validation(問題全体の整合・実行可能性)は problem_type ごとの検査関数を
  app/domain/problems/semantic.py の SEMANTIC_CHECKS レジストリに集約。このサービスは
  レジストリを回すだけ。
- 例外: route の「到達可能性」だけは graph アルゴリズム(app/algorithms/)を使うため、
  domain → algorithms の逆流を避けてここに置く。
    - route の到達可能性        route_reachable
    - network の全拠点連結性     all_nodes_connected
    - project の依存 DAG が非巡回か has_cycle
    - logistics のデポ→全配送先の到達可能性 logistics_deliveries_reachable

整合性の欠陥 → ProblemValidationError(400)。原理的に解が無い → InfeasibleProblemError(400)。
原則: 「明らかに無理」だけを弾き、グレーゾーンは通す)。
"""

from __future__ import annotations

from app.algorithms.graph.adjacency import build_link_adjacency
from app.algorithms.graph.connectivity import all_nodes_connected
from app.algorithms.graph.reachability import route_reachable, logistics_deliveries_reachable
from app.algorithms.graph.topological import has_cycle, successors_from_edges
from app.domain.problems.problem import ForbiddenConstraint, OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.project_manager import ProjectData   
from app.domain.problems.logistics import LogisticsData
from app.domain.problems.semantic import SEMANTIC_CHECKS
from app.services.errors import InfeasibleProblemError, ProblemValidationError

class ProblemValidationService:
    """OptimizationProblem がアルゴリズムに渡せる状態か、問題全体を見て検査する。"""

    def validate(self, problem: OptimizationProblem) -> None:
        """検査に通れば None を返す。整合性 NG は ProblemValidationError、
        到達不能は InfeasibleProblemError を送出する。"""

        # SEMANTIC_CHECKSからproblem_typeをキーにcheckに関数を格納するループ
        #   -> 変数checkに関数が入っているため引数(problem)で関数が実行される
        #       -> 結果をissues配列に格納する。
        issues = [
            issue
            for check in SEMANTIC_CHECKS.get(problem.problem_type, [])
            for issue in check(problem)
        ]

        # SEMANTIC_CHECKSはィールドを見るだけで判定できる整合性の欠陥
        # 整合性の欠陥が1件でもあれば、
        # そちらを優先して弾く(到達可能性の判定は端点が実在してこそ意味を持つため)
        integrity = [i.message for i in issues if not i.infeasible]
        if integrity:
            raise ProblemValidationError("; ".join(integrity))

        infeasible = [i.message for i in issues if i.infeasible]

        # problem.constraintsがForbiddenConstraintならitemのセットを作る
        forbidden = {
            item
            for c in problem.constraints
            if isinstance(c, ForbiddenConstraint)
            for item in c.items
        }

        # ここからは グラフ探索を走らせないと判定できない不整合確認
        # route: goal が start から到達可能か ── 「計算」なので route_reachable(algorithms)に任せる
        if isinstance(problem.data, RouteData):
            if not route_reachable(problem.data, forbidden):
                infeasible.append(
                    f"goal {problem.data.goal!r} is unreachable from {problem.data.start!r} "
                    f"after removing {len(forbidden)} forbidden edge(s)"
                )
        # network: 敷設可能リンク全体で全拠点が繋がるか(繋がらなければ全域木は作れない)
        elif isinstance(problem.data, NetworkDesignData):
            adjacency = build_link_adjacency(problem.data, forbidden)
            if not all_nodes_connected((n.id for n in problem.data.nodes), adjacency):
                infeasible.append(
                    f"candidate links (minus {len(forbidden)} forbidden) cannot connect all nodes"
                )
        # project: 依存グラフが DAG か ── 閉路があるとトポロジカル順が存在しない
        elif isinstance(problem.data, ProjectData):
            successors = successors_from_edges(
                (t.id for t in problem.data.tasks),
                ((d.predecessor, d.successor) for d in problem.data.dependencies),
            )
            if has_cycle(successors):
                infeasible.append("dependency graph has a cycle: no topological order exists")
        # logistics: デポから全配送先ノードへ道路網で到達できるか
        elif isinstance(problem.data, LogisticsData) and not logistics_deliveries_reachable(
            problem.data, forbidden
        ):
            infeasible.append(
                f"not all deliveries are reachable from depot {problem.data.depot_id!r} "
                f"after removing {len(forbidden)} forbidden segment(s)"
            )


        if infeasible:
            raise InfeasibleProblemError("; ".join(infeasible))