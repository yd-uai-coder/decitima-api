"""分析トラック ── benchmark_runs / solutions に貯まった実測を pandas で集計・可視化する。

`app/` からは import されない(`tests/` と同じく app の「上」に立つ)。`app.models` /
`app.core.config` への依存は可。逆(`app → analysis`)は禁止。

DB との結合は「エクスポート → ファイル読み」の一方向のみ(decitima-ui の `src/db/` と同型):

    python -m analysis.export benchmark_runs analysis/data/benchmark_runs.jsonl
    loaders.load_benchmark_runs(path) -> pd.DataFrame

依存は `pyproject.toml` の `[dependency-groups].analysis`(pandas / matplotlib)。
runtime(`[project].dependencies`)には入れない。

ロードマップ:
- Phase 3(この単位): benchmark 分析 ── `benchmark_report.py` / `plots.py`
- Phase 5: 手実装 vs OR-Tools の破綻境界・Pareto ── `analysis/shift_analysis.py`(予定)
- Phase 9: Sensitivity Analysis ── `analysis/sensitivity.py`(予定)
- Phase 11: 蓄積 benchmark からアルゴリズム推薦の決定表を導出
- Phase 13: LLM vs Algorithm の実験フレームワーク ── `analysis/experiment.py`(予定)
- Phase 14: CI 性能回帰の検知
"""
