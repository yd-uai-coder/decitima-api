from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.solve import router as solve_router 
from app.api.routes.algorithms import router as algorithms_router
from app.api.routes.solutions import router as solutions_router
from app.api.routes.verify import router as verify_router
from app.api.routes.benchmark import router as benchmark_router

# 各機能別ルーターを1つのAPIRouterに集約し、main.pyから一括でincludeできるようにする。
# chat_router（app/api/routes/chat.py）はDeciTimaではPhase 10まで無効化している。
# コード自体は残してあり、Phase 10でDeciTima用ワークフローに作り替える土台とする。
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(solve_router) 
api_router.include_router(algorithms_router)
api_router.include_router(solutions_router)
api_router.include_router(verify_router)
api_router.include_router(benchmark_router) 