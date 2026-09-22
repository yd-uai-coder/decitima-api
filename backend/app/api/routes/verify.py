"""POST /api/v1/verify ── 問題 + 解を受け取り、検証だけして結果を返す。

solve と同じくルートは薄い: サービスを呼ぶ → スキーマに詰めて返すだけ。
解が制約に違反していても「エラー」ではない ── 200 で status="invalid" を返す
"""

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, RedisDep
from app.schemas.optimization import VerifyRequest, VerifyResponse
from app.services.verify_request import VerifyService

router = APIRouter(prefix="/verify", tags=["verify"])


@router.post("", response_model=VerifyResponse)
async def verify(
    payload: VerifyRequest,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> VerifyResponse:
    """クライアントが持ち込んだ候補解を、その問題の制約に照らして検証する。"""
    verified = await VerifyService(redis).verify(
        user_id=current_user.id,
        request=payload,
        bypass_rate_limit=current_user.is_superuser,
    )
    return VerifyResponse(
        status=verified.status,
        violations=verified.violations,
        metrics=verified.metrics,
    )
