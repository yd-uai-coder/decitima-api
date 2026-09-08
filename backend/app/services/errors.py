from typing import ClassVar       

from app.core.errors import (
    AppError,
    BadGatewayError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    TooManyRequestsError,
    UnauthorizedError,
)

# ---------------------------------------
# 汎用
# ---------------------------------------

class InvalidCredentialsError(UnauthorizedError):
    """メールアドレスまたはパスワードが誤っている、もしくは無効化済みユーザーの場合に送出する。"""


class InvalidTokenError(UnauthorizedError):
    """JWTが不正・期限切れ、またはRedis上で失効済みの場合に送出する。"""


class UserAlreadyExistsError(ConflictError):
    """登録しようとしたメールアドレスが既に別ユーザーで使用されている場合に送出する。"""


class ConversationNotFoundError(NotFoundError):
    """指定した会話IDが存在しない、または他ユーザーが所有する会話である場合に送出する。"""


class RateLimitExceededError(TooManyRequestsError):
    """Redisで管理するレート制限の上限（時間/日単位など）を超過した場合に送出する。"""


class GenerationFailedError(BadGatewayError):
    """LLM呼び出しが規定回数のリトライ後も失敗し続けた場合に送出する。"""


# ---------------------------------------
# Decisima
# ---------------------------------------

class ProblemValidationError(BadRequestError):
    """OptimizationProblem がセマンティック検査に通らなかった場合に送出する(HTTP 400)。"""

class InfeasibleProblemError(BadRequestError):
    """条件を満たす解が原理的に存在しないと Validation 段階で判明した場合に送出する(HTTP 400)。"""

class NoAlgorithmError(BadRequestError):
    """registry に該当アルゴリズムが無い場合に送出する(HTTP 400)。

    problem_type が未対応、または requested のアルゴリズム名が登録されていないとき。
    """

class SolveTimeoutError(AppError):
    """アルゴリズムの実行が規定時間を超えた場合に送出する(HTTP 504)。"""

    status_code: ClassVar[int] = 504