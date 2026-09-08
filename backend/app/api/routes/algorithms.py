"""GET /api/v1/algorithms ── registry に登録されたアルゴリズムの一覧。
認証必須(MVP は統一。公開が必要になったら緩める)。
"""

from collections import defaultdict

from fastapi import APIRouter

from app.algorithms.registry import all_strategies
from app.api.deps import CurrentUserDep
from app.schemas.optimization import AlgorithmInfo, AlgorithmListResponse

router = APIRouter(prefix="/algorithms", tags=["algorithms"])


@router.get("", response_model=AlgorithmListResponse)
async def list_algorithms(_current_user: CurrentUserDep) -> AlgorithmListResponse:
    """(name, implementation) ごとに、登録されている problem_type をまとめて返す。"""
    # (name, implementation) をキーに problem_type を集約する
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    meta_by_key: dict[tuple[str, str], AlgorithmInfo] = {}
    for problem_type, strategy in all_strategies():
        key = (strategy.meta.name, strategy.meta.implementation)
        grouped[key].add(problem_type)
        meta_by_key[key] = AlgorithmInfo(
            name=strategy.meta.name,
            family=strategy.meta.family,
            implementation=strategy.meta.implementation,
            problem_types=[],
            time_complexity=strategy.meta.time_complexity,
        )

    algorithms = [
        info.model_copy(update={"problem_types": sorted(grouped[key])})
        for key, info in meta_by_key.items()
    ]
    return AlgorithmListResponse(algorithms=algorithms)
