"""ドメイン層。最適化問題・制約・目的・解の「型と意味」を定義する純粋なパッケージ。

DeciTima の共通スキーマ（OptimizationProblem など）と、それに付随する
制約チェッカー・目的関数の評価をここに置く。services / repositories / DB /
HTTP / Redis / ai に依存してはならない（依存してよいのは標準ライブラリと Pydantic のみ）。

設計は textbook/Phase-0/Phase-0-2.md、実装は Phase 1（作業単位 1-1）で行う。
"""
