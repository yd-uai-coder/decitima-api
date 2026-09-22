from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings


@lru_cache
def get_gemini_llm(*, temperature: float = 0.7) -> ChatGoogleGenerativeAI:
    """設定値から構築したChatGoogleGenerativeAIクライアントを、温度パラメータ単位でキャッシュして返す。"""
    if settings.E2E_TESTING:
        # テスト専用モジュールは E2E のときだけ読み込む(本番のプロセスには載せない)。
        from app.ai.llm.e2e_fixture import E2eFakeLLM

        # E2E 用フェイクは ChatGoogleGenerativeAI のサブクラスではない(Phase 15-9)。
        # 呼び出し側が使う invoke / ainvoke / with_structured_output だけ互換なので型だけ許容する
        return E2eFakeLLM()  # pyright: ignore[reportReturnType]

    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
    )
