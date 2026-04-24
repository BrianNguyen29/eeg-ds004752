"""V5.6 benchmark/control-first scaffolding.

This package intentionally exposes only contract and policy helpers.
It does not implement training, model selection, or efficacy claims.
"""

from .benchmark import V56BenchmarkError, V56ReadinessError
from .controls import V56ControlPolicyError
from .leaderboard import V56LeaderboardError
from .splits import V56SplitPolicyError

__all__ = [
    "V56BenchmarkError",
    "V56ControlPolicyError",
    "V56LeaderboardError",
    "V56ReadinessError",
    "V56SplitPolicyError",
]
