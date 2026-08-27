"""アルゴリズム層。決定論的な計算を行う純粋関数のパッケージ。

各アルゴリズムは AlgorithmStrategy プロトコル（solve(problem) -> CandidateSolution +
メタデータ）を満たす。手実装トラックと産業ソルバートラック（networkx / ortools 等）が
同一インターフェースで並ぶ。registry が problem_type → 候補アルゴリズムを持つ。

services / repositories / DB / HTTP / Redis / ai に依存してはならない
（依存してよいのは app.domain と標準ライブラリ、実務トラックのみ外部ソルバー）。

設計は textbook/Phase-0/Phase-0-4.md、実装は Phase 1（作業単位 1-2〜1-4）で行う。
"""
