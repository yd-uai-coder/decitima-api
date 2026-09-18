# DeciTima samples │ 作業単位 15-1
"""性能テスト共通のフィクスチャ。"""

from collections.abc import Callable
from typing import TypeVar

import pytest

from app.services.measurement import Measurement, measure_call

T = TypeVar("T")


@pytest.fixture
def measure() -> Callable[[Callable[[], T], int], tuple[T, Measurement]]:
    """`measure_call` をそのまま返す薄いフィクスチャ。

    Phase 3 の計測コアを性能テストでも再利用する(スタブ不要 ── measure_call 自体が
    対象の callable を直接実行する薄いラッパーで、独自の外部依存を持たないため)。
    """
    return measure_call
