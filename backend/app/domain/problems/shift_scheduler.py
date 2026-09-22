"""Shift Scheduler の問題固有データ(葉モジュール)。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal
from datetime import date

class Staff(BaseModel):
    """シフト問題のスタッフ1人。時給・スキル・勤務可能スロット・希望休。"""

    id: str
    name: str | None = None
    hourly_wage: float = Field(ge=0)
    skills: list[str] = Field(default_factory=list)
    available_slot_ids: list[str] = Field(default_factory=list)  # 勤務可能なスロット id
    requested_days_off: list[str] = Field(default_factory=list)  # 希望休の日付(soft 制約と連動)


class ShiftSlot(BaseModel):
    """シフト問題の勤務スロット1つ。日付・時間帯・必要人数・必要スキル。"""

    id: str
    day: str  # "2026-09-01" など
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)
    required_headcount: int = Field(ge=1)
    required_skills: list[str] = Field(default_factory=list)

    @field_validator("day")
    @classmethod
    def _day_is_iso_date(cls, value: str) -> str:
        # 単項フィールドの値チェック → field_validator。日付として解釈できなければ弾く
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"day must be an ISO date (YYYY-MM-DD), got {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _end_after_start(self) -> ShiftSlot:
        # start_hour / end_hour は個別には Field(ge/le) 済み。ここは 2 つの関係を見る
        if self.end_hour <= self.start_hour:
            raise ValueError(
                f"end_hour ({self.end_hour}) must be greater than start_hour ({self.start_hour})"
            )
        return self


class ShiftData(BaseModel):
    """Shift Scheduler の問題固有データ。スタッフ・スロット・全体上限。"""

    problem_type: Literal["shift_scheduling"] = "shift_scheduling"
    staff: list[Staff]
    slots: list[ShiftSlot]
    max_weekly_hours: float = 40
    max_consecutive_days: int = 5

    @model_validator(mode="after")
    def _unique_ids(self) -> ShiftData:
        # スロット id / スタッフ id の重複は「明らかに壊れた入力」としてここで弾く
        slot_ids = [s.id for s in self.slots]
        staff_ids = [s.id for s in self.staff]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("slot ids must be unique")
        if len(staff_ids) != len(set(staff_ids)):
            raise ValueError("staff ids must be unique")
        return self