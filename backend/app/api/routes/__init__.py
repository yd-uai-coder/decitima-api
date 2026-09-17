from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.solve import router as solve_router 
from app.api.routes.algorithms import router as algorithms_router
from app.api.routes.solutions import router as solutions_router
from app.api.routes.verify import router as verify_router
from app.api.routes.benchmark import router as benchmark_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.simulate import router as simulate_router
from app.api.routes.structure import router as structure_router  # (Phase 11-7)

# 各機能別ルーターを1つのAPIRouterに集約し、main.pyから一括でincludeできるようにする。
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(solve_router) 
api_router.include_router(algorithms_router)
api_router.include_router(solutions_router)
api_router.include_router(verify_router)
api_router.include_router(benchmark_router) 
api_router.include_router(jobs_router)
api_router.include_router(simulate_router)
api_router.include_router(structure_router)