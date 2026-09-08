"""作業単位 2-1: ShiftSlot / ShiftData の Input Validation(Pydantic)。

対象は純粋な値オブジェクト。スタブ不要 ── 外部依存を一切呼ばない。
"""

import pytest
from pydantic import ValidationError

from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff

# 標準的な使用方法でのチェック(入力成功例)
def test_valid_slot_builds() -> None:
    ShiftSlot(id="s1", day="2026-09-01", start_hour=9, end_hour=14, required_headcount=1)


# ------------------------------------------------
# 以下、ValidationErrorが発生すればテスト成功
# ------------------------------------------------

# 終了時間 >　開始時間　でないのでエラー(エラー発生条件は　開始時間 >= 終了時間)
def test_end_hour_not_after_start_hour_is_rejected() -> None:
    with pytest.raises(ValidationError, match="end_hour"):
        ShiftSlot(id="s1", day="2026-09-01", start_hour=14, end_hour=14, required_headcount=1)

# dayのフォーマット違反によるエラー
def test_non_iso_day_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ISO date"):
        ShiftSlot(id="s1", day="Sept 1", start_hour=9, end_hour=14, required_headcount=1)

# field単体の領域外の入力
def test_start_hour_out_of_range_is_rejected() -> None:
    # 単項の値域は Field(ge/le) が担う(model_validator ではない)
    with pytest.raises(ValidationError):
        ShiftSlot(id="s1", day="2026-09-01", start_hour=-1, end_hour=14, required_headcount=1)

# slots内でのstaff.id重複禁止
def test_duplicate_slot_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="slot ids must be unique"):
        ShiftData(
            staff=[Staff(id="a", hourly_wage=1000)],
            slots=[
                ShiftSlot(
                    id="s1", day="2026-09-01", start_hour=9, end_hour=14, required_headcount=1
                ),
                ShiftSlot(
                    id="s1", day="2026-09-02", start_hour=9, end_hour=14, required_headcount=1
                ),
            ],
        )


def test_duplicate_staff_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="staff ids must be unique"):
        ShiftData(
            staff=[Staff(id="a", hourly_wage=1000), Staff(id="a", hourly_wage=1200)],
            slots=[
                ShiftSlot(
                    id="s1", day="2026-09-01", start_hour=9, end_hour=14, required_headcount=1
                )
            ],
        )
