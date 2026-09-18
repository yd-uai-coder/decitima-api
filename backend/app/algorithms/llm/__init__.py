"""LLM Only 戦略(LLM vs Algorithm Comparison)。

`app/algorithms/` の6つ目のサブパッケージ(`AlgorithmMeta.family = "llm"` と1対1、
Phase-0-2.md 以来の「family は app/algorithms/ のサブパッケージと1対1」を Phase 14 でも
維持する)。ここに置く戦略は `AlgorithmStrategy` Protocol を満たすが、本番 `REGISTRY`
(`app/algorithms/registry.py`)には**登録しない** ── `/solve` の既定選択に一切影響させず、
`app/services/comparison.py::ComparisonService` が比較専用に直接インスタンス化する。

- `common.py` … 6 ドメイン共通のプロンプト部品(目的・制約の自然言語化)と共有 `AlgorithmMeta`
- `route_llm.py` / `network_llm.py` / `shift_llm.py` / `travel_llm.py` / `project_llm.py` /
  `logistics_llm.py` … ドメインごとの `LlmOnly*Strategy`。出力スキーマは既存の
  `RouteSolution`/…をそのまま使う(新スキーマを作らない ── 変換コード無しで既存の
  `SolutionVerificationService` にそのまま通せる、Phase 14 の設計の核)。
"""
