# DeciTima samples │ Phase 3
"""作業単位 3-8: analysis.plots(スモークテスト)。

対象 = `plot_comparison` / `plot_input_size_curve`。「Figure を返す」ことだけ確認する
(見た目は検証しない)。ヘッドレスで動くよう Agg バックエンドを先に設定。
**スタブ不要**。
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from analysis.plots import plot_comparison, plot_input_size_curve  # noqa: E402


def test_plot_comparison_returns_figure() -> None:
    report = pd.DataFrame(
        {"algorithm": ["dijkstra", "brute_force"], "elapsed_ms_median": [0.1, 0.5]}
    )
    fig = plot_comparison(report)
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_plot_input_size_curve_returns_figure_with_log_axis() -> None:
    curve = pd.DataFrame(
        {"size": [4, 8, 16], "dijkstra": [3, 7, 15], "brute_force": [6, 200, 9000]}
    )
    fig = plot_input_size_curve(curve, log=True)
    assert isinstance(fig, Figure)
    assert fig.axes[0].get_yscale() == "log"
    plt.close(fig)
