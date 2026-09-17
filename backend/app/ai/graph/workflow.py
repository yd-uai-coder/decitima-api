"""Structuring ワークフローの組み立て。

処理の流れ: テキスト -> 分類 -> シード読み込み -> objectives/constraints 抽出
-> ドメイン別 data 抽出 -> 組み立て -> 検証。条件分岐は無い一直線のパイプライン
(ドメインごとの違いは extract_domain_data 内部の `EXTRACTORS` レジストリ参照で
吸収する。
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.ai.graph.nodes import (
    assemble_problem,
    classify_problem_type,
    extract_domain_data,
    extract_objectives_constraints,
    load_base_problem,
    validate_problem,
)
from app.ai.graph.state import GraphState


def build_structuring_workflow() -> CompiledStateGraph:
    """Structuring ワークフローのノードとエッジを組み立て、コンパイル済みグラフとして返す。"""
    workflow = StateGraph(GraphState)

    workflow.add_node("classify_problem_type", classify_problem_type)
    workflow.add_node("load_base_problem", load_base_problem)
    workflow.add_node("extract_objectives_constraints", extract_objectives_constraints)
    workflow.add_node("extract_domain_data", extract_domain_data)
    workflow.add_node("assemble_problem", assemble_problem)
    workflow.add_node("validate_problem", validate_problem)

    workflow.add_edge(START, "classify_problem_type")
    workflow.add_edge("classify_problem_type", "load_base_problem")
    workflow.add_edge("load_base_problem", "extract_objectives_constraints")
    workflow.add_edge("extract_objectives_constraints", "extract_domain_data")
    workflow.add_edge("extract_domain_data", "assemble_problem")
    workflow.add_edge("assemble_problem", "validate_problem")
    workflow.add_edge("validate_problem", END)

    return workflow.compile()


@lru_cache
def get_structuring_workflow() -> CompiledStateGraph:
    """コンパイル済みチャットワークフローをプロセス内で1つだけ生成し、以後は使い回す。"""
    return build_structuring_workflow()
