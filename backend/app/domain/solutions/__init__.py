"""解解の表現パッケージ。公開窓口(re-export + __all__)"""

from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.project_manager import ProjectSolution, ScheduledTask  # (Phase 8-3)
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import (
    AlgorithmFamily,
    AlgorithmMeta,
    CandidateSolution,
    ConstraintViolation,
    SolutionData,
    SolutionStatus,
)
from app.domain.solutions.travel_planner import TravelSolution
from app.domain.solutions.logistics import LogisticsSolution, VehicleRoute

__all__ = [
    "AlgorithmFamily",
    "AlgorithmMeta",
    "CandidateSolution",
    "ConstraintViolation",
    "NetworkDesignSolution",
    "ProjectSolution",
    "RouteSolution",
    "ScheduledTask",
    "ShiftSolution",
    "SolutionData",
    "SolutionStatus",
    "TravelSolution",
    "VehicleRoute",
    "LogisticsSolution",
]
