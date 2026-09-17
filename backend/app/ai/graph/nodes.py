"""Structuring ワークフローの各ノード。"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.ai.graph.state import GraphState
from app.ai.llm.gemini import get_gemini_llm



from typing import cast

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ValidationError

from app.ai.graph.state import GraphState
from app.ai.llm.gemini import get_gemini_llm
from app.domain.problems.base_problems import get_base_problem
from app.domain.problems.problem import OptimizationProblem
from app.schemas.structuring import ProblemTypeClassification, ObjectivesConstraintsExtraction
from app.services.errors import ProblemValidationError
from app.services.simulation import apply_overrides
from app.services.structuring import (
    EXTRACTORS,
    build_overrides,
    catalog_entries,
    catalog_ids,
    ground_references,
)
from app.services.validation import ProblemValidationService


# problem_type ごとの短い説明。分類プロンプトに埋め込む(ドメイン知識を1箇所に集約)。
_PROBLEM_TYPE_DESCRIPTIONS: dict[str, str] = {
    "route_planning": "地図上の2地点間の最短経路・最短時間を求める問題",
    "network_design": "複数拠点を最小コストで結ぶネットワーク(通信網・配線等)を設計する問題",
    "shift_scheduling": "スタッフをシフト(勤務枠)に割り当てる問題",
    "travel_planning": "予算・時間内で訪問先を選び、周遊プランを立てる問題",
    "project_scheduling": "依存関係と資源制約の下でタスクをスケジューリングする問題",
    "logistics_planning": "複数車両で配送先を巡回する配送計画(CVRP)問題",
}


def _classify_prompt(text: str) -> str:
    """problem_type 分類用プロンプトを組み立てる。"""
    domains = "\n".join(f"- {key}: {desc}" for key, desc in _PROBLEM_TYPE_DESCRIPTIONS.items())
    return (
        "次のユーザーの要求が、以下のどの問題種別に最も近いか分類してください。\n\n"
        f"{domains}\n\nユーザーの要求:\n{text}"
    )

def classify_problem_type(state: GraphState) -> dict:
    """自然言語から problem_type を分類する(Structured Output、Literal[6種]で誤答不能)。"""
    llm = get_gemini_llm(temperature=0).with_structured_output(ProblemTypeClassification)
    prompt = _classify_prompt(state["text"])
    # with_structured_output() の戻り型は dict | BaseModel(include_raw=False の既定では
    # 常に指定した Pydantic モデルが返るが、langchain の型定義はそこまで絞り込めない)。
    result = cast(ProblemTypeClassification, llm.invoke([HumanMessage(content=prompt)]))
    return {"problem_type": result.problem_type}


def load_base_problem(state: GraphState) -> dict:
    """problem_type からベース問題を複製して読み込む(純粋、LLM 呼び出しなし)。"""
    problem_type = state["problem_type"]
    assert problem_type is not None  # classify_problem_type が必ず先に走る
    return {"base_problem": get_base_problem(problem_type)}

def _objectives_prompt(text: str, base_problem: OptimizationProblem) -> str:
    """objectives/constraints 抽出用プロンプトを組み立てる。base_problem のカタログを
    (id, name)で埋め込み、「制約で要素を参照するときは必ず id を使う」ことを徹底させる
    (grounding の第一防衛線。最後の砦は services/structuring.py::ground_references)。"""
    catalog_lines = "\n".join(
        f"- {id_}" + (f": {name}" if name else "") for id_, name in catalog_entries(base_problem)
    )
    return (
        "以下はユーザーの自然言語の要求です。目的(objectives)と制約(constraints)を"
        "抽出してください。制約で特定の要素を参照する場合は、必ず下記の id を使ってください"
        "(名前ではなく id)。該当する id が無ければ、その要素についての制約は生成しないで"
        "ください。\n\n"
        f"利用可能な id 一覧:\n{catalog_lines}\n\nユーザーの要求:\n{text}"
    )


def extract_objectives_constraints(state: GraphState) -> dict:
    """objectives/constraints をドメイン非依存の1スキーマで抽出する(README「Constraint/
    Objective Extraction」の本体)。全 problem_type 共通で満たす部分。"""
    llm = get_gemini_llm(temperature=0).with_structured_output(ObjectivesConstraintsExtraction)
    base_problem = state["base_problem"]
    assert base_problem is not None  # load_base_problem が必ず先に走る
    prompt = _objectives_prompt(state["text"], base_problem)
    result = cast(ObjectivesConstraintsExtraction, llm.invoke([HumanMessage(content=prompt)]))
    return {"objectives_patch": result.objectives, "constraints_patch": result.constraints}

def _data_prompt(text: str, base_problem: OptimizationProblem) -> str:
    """data のトップレベル・スカラー抽出用プロンプトを組み立てる(§ _objectives_prompt と
    同じ grounding の徹底)。"""
    catalog_lines = "\n".join(
        f"- {id_}" + (f": {name}" if name else "") for id_, name in catalog_entries(base_problem)
    )
    return (
        "以下はユーザーの自然言語の要求です。指定されたスキーマのフィールドのうち、"
        "要求文から読み取れるものだけを埋めてください。読み取れないフィールドは触れずに"
        "そのままにしてください。id を書く場合は必ず下記の一覧から選んでください。\n\n"
        f"利用可能な id 一覧:\n{catalog_lines}\n\nユーザーの要求:\n{text}"
    )


def extract_domain_data(state: GraphState) -> dict:
    """`EXTRACTORS` レジストリで problem_type に応じた Data Patch スキーマへディスパッチする。
    パッチスキーマが無い(= トップレベル・スカラーを持たない)ドメインは LLM を呼ばず
    空 dict を返す(network_design)。"""
    problem_type = state["problem_type"]
    assert problem_type is not None  # classify_problem_type が必ず先に走る
    schema = EXTRACTORS.get(problem_type)
    if schema is None:
        return {"data_patch": {}}

    base_problem = state["base_problem"]
    assert base_problem is not None  # load_base_problem が必ず先に走る
    llm = get_gemini_llm(temperature=0).with_structured_output(schema)
    prompt = _data_prompt(state["text"], base_problem)
    patch = cast(BaseModel, llm.invoke([HumanMessage(content=prompt)]))
    return {"data_patch": patch.model_dump(exclude_unset=True)}


def assemble_problem(state: GraphState) -> dict:
    """objectives_patch/constraints_patch/data_patch を overrides dict に変換し、
    `apply_overrides`(Phase 10)でベース問題にマージする。objectives_patch が空なら
    (`build_overrides` の判断で)ベースの objectives を維持する ── 抽出失敗で目的が
    空欄消失するのを防ぐ非自明な判断なので、その旨を notes に記録する。"""
    base_problem = state["base_problem"]
    assert base_problem is not None  # load_base_problem が必ず先に走る
    overrides = build_overrides(
        state["objectives_patch"], state["constraints_patch"], state["data_patch"]
    )
    notes: list[str] = []
    if not state["objectives_patch"]:
        notes.append(
            "目的(objectives)を要求文から抽出できなかったため、ベース問題の既定目的を使用しました"
        )
    try:
        problem = apply_overrides(base_problem, overrides)
    except (ValidationError, ValueError) as exc:
        # LLM の抽出結果がベース問題のカタログと矛盾する場合(例: place id ではない値)。
        # 入力起因でリトライしても解消しないため ProblemValidationError に変換し、
        # _invoke_with_retry の即時伝播(400)経路に乗せる(Phase 10 の _SCENARIO_ERRORS と同じ判断)。
        raise ProblemValidationError(str(exc)) from exc
    return {"problem": problem, "notes": notes}


def validate_problem(state: GraphState) -> dict:
    """Semantic Validation(既存、Phase 0〜9)+ グラウンディング検査(Phase 11 専用)を通す。
    NG は例外をそのまま呼び出し元へ伝播させる(state に error フィールドを持たせない ──
    app/services/solve.py と同じ方針)。"""
    problem = state["problem"]
    base_problem = state["base_problem"]
    assert problem is not None  # assemble_problem が必ず先に走る
    assert base_problem is not None  # load_base_problem が必ず先に走る

    ProblemValidationService().validate(problem)

    issues = ground_references(problem, catalog_ids(base_problem))
    if issues:
        raise ProblemValidationError("; ".join(issues))
    return {}
