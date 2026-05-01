"""Experiment Report Generator.

Generates a Markdown document from experiment data, then converts it
to Word (.docx) via the existing DocumentConverter pipeline.

The Markdown contains:
- Experiment summary
- Ranked runs leaderboard table
- Parameter comparison (what changed between top runs)
- Snapshot info (if any runs are snapshots)
- Lineage information per run
"""

import logging
import os
import tempfile
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from app.managers.mlflow_manager import MlflowManager

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates experiment comparison reports as Markdown -> Word."""

    def __init__(self, mlflow_manager: MlflowManager | None = None):
        self._mlflow = mlflow_manager or MlflowManager()

    def generate(self, experiment_id: str, top_n: int = 10,
                 sort_by: str = '', sort_order: str = 'asc',
                 format: str = 'word') -> Path:
        """Generate an experiment report.

        Args:
            experiment_id: MLflow experiment ID
            top_n: Number of top runs to include
            sort_by: Metric key to sort by (empty = by start time)
            sort_order: 'asc' or 'desc'
            format: 'word' or 'markdown'

        Returns:
            Path to the generated file (.docx or .md)
        """
        # Fetch experiment data
        experiments = self._mlflow.list_experiments()
        exp = next((e for e in experiments if e['experiment_id'] == experiment_id), None)
        if not exp:
            raise FileNotFoundError(f"Experiment not found: {experiment_id}")

        exp_name = exp['name']

        # Fetch all runs
        runs = self._mlflow.search_runs(
            experiment_ids=[experiment_id],
            max_results=200,
        )

        if not runs:
            raise ValueError(f"No runs found in experiment {experiment_id}")

        # Collect all metric and param keys
        all_metric_keys = sorted(set(k for r in runs for k in r.get('metrics', {})))
        all_param_keys = sorted(set(k for r in runs for k in r.get('params', {})))

        # Sort runs
        if sort_by and sort_by in all_metric_keys:
            reverse = sort_order.lower() == 'desc'
            runs.sort(
                key=lambda r: r.get('metrics', {}).get(sort_by, float('inf') if not reverse else float('-inf')),
                reverse=reverse,
            )

        top_runs = runs[:top_n]

        # Generate Markdown
        md = self._build_markdown(exp_name, experiment_id, runs, top_runs,
                                   all_metric_keys, all_param_keys, sort_by)

        # Write to temp file
        tmp_dir = Path(tempfile.mkdtemp(prefix='noted_report_'))
        safe_name = exp_name.replace(':', '_').replace('/', '_').replace(' ', '_')

        # Generate charts
        chart_refs = self._generate_charts(tmp_dir, top_runs, all_metric_keys, experiment_id)

        # Append chart references to markdown
        if chart_refs:
            md += '\n' + chart_refs

        md_path = tmp_dir / f'{safe_name}_report.md'
        md_path.write_text(md, encoding='utf-8')

        if format == 'markdown':
            return md_path

        # Convert to Word via DocumentConverter
        from app.managers.document_converter import DocumentConverter
        converter = DocumentConverter(
            doc_title=f'Experiment Report: {exp_name}',
            include_toc=True,
            text_align='left',
        )
        result = converter.convert(md_path, output_dir=tmp_dir)

        if result.docx and result.docx.exists():
            return result.docx

        # Fallback to markdown if conversion fails
        logger.warning("Word conversion failed, returning Markdown")
        return md_path

    def _build_markdown(self, exp_name: str, exp_id: str, all_runs: list,
                         top_runs: list, metric_keys: list, param_keys: list,
                         sort_by: str) -> str:
        """Build the Markdown content for the report."""
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        lines = []

        # Title
        lines.append(f'# Experiment Report: {exp_name}')
        lines.append('')
        lines.append(f'Generated: {now}')
        lines.append('')

        # Summary
        lines.append('## Summary')
        lines.append('')
        lines.append(f'- **Experiment ID:** {exp_id}')
        lines.append(f'- **Total Runs:** {len(all_runs)}')
        finished = sum(1 for r in all_runs if r.get('status') == 'FINISHED')
        lines.append(f'- **Finished Runs:** {finished}')
        snapshots = [r for r in all_runs if r.get('tags', {}).get('noted.snapshot') == 'true']
        if snapshots:
            lines.append(f'- **Snapshots:** {len(snapshots)}')
        if sort_by:
            lines.append(f'- **Sorted by:** {sort_by}')

        # Date range
        start_times = [r['start_time'] for r in all_runs if r.get('start_time')]
        if start_times:
            lines.append(f'- **First Run:** {min(start_times)[:19]}')
            lines.append(f'- **Last Run:** {max(start_times)[:19]}')
        lines.append('')

        # Leaderboard table
        lines.append(f'## Run Leaderboard (Top {len(top_runs)})')
        lines.append('')

        # Build table header
        headers = ['Run', 'Status']
        if metric_keys:
            headers.extend(metric_keys[:8])  # Limit to 8 metrics for readability
        table_header = '| ' + ' | '.join(headers) + ' |'
        table_sep = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
        lines.append(table_header)
        lines.append(table_sep)

        for run in top_runs:
            name = run.get('run_name', run['run_id'][:8])
            is_snap = run.get('tags', {}).get('noted.snapshot') == 'true'
            name_display = f'**{name}** *' if is_snap else name
            status = run.get('status', '')

            row = [name_display, status]
            for mk in metric_keys[:8]:
                v = run.get('metrics', {}).get(mk)
                if v is not None:
                    row.append(f'{v:.6f}' if isinstance(v, float) else str(v))
                else:
                    row.append('-')

            lines.append('| ' + ' | '.join(row) + ' |')

        lines.append('')
        if snapshots:
            lines.append('\\* = Snapshot')
            lines.append('')

        # Parameters comparison
        lines.append('## Parameters')
        lines.append('')

        # Find which params vary across runs
        varying_params = []
        for pk in param_keys:
            values = set(str(r.get('params', {}).get(pk, '')) for r in top_runs)
            if len(values) > 1:
                varying_params.append(pk)

        if varying_params:
            lines.append(f'### Varying Parameters ({len(varying_params)})')
            lines.append('')
            headers = ['Parameter'] + [r.get('run_name', r['run_id'][:6]) for r in top_runs[:6]]
            lines.append('| ' + ' | '.join(headers) + ' |')
            lines.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

            for pk in varying_params:
                row = [f'`{pk}`']
                for run in top_runs[:6]:
                    row.append(str(run.get('params', {}).get(pk, '-')))
                lines.append('| ' + ' | '.join(row) + ' |')
            lines.append('')

        # Constant params
        constant_params = [pk for pk in param_keys if pk not in varying_params]
        if constant_params and top_runs:
            lines.append(f'### Constant Parameters ({len(constant_params)})')
            lines.append('')
            for pk in constant_params:
                val = top_runs[0].get('params', {}).get(pk, '-')
                lines.append(f'- `{pk}`: {val}')
            lines.append('')

        # Snapshot details
        if snapshots:
            lines.append('## Snapshots')
            lines.append('')
            for snap in snapshots:
                tags = snap.get('tags', {})
                snap_name = tags.get('noted.snapshot_name', 'unnamed')
                snap_branch = tags.get('noted.snapshot_branch', '')
                git_commit = tags.get('noted.git_commit', '')[:7]
                desc = tags.get('noted.snapshot_description', '')

                lines.append(f'### {snap_name}')
                lines.append('')
                lines.append(f'- **Run:** {snap.get("run_name", snap["run_id"][:8])}')
                if snap_branch:
                    lines.append(f'- **Branch:** `{snap_branch}`')
                if git_commit:
                    lines.append(f'- **Commit:** `{git_commit}`')
                if desc:
                    lines.append(f'- **Description:** {desc}')

                # Key metrics
                metrics = snap.get('metrics', {})
                if metrics:
                    metric_strs = [f'{k}: {v:.4f}' if isinstance(v, float) else f'{k}: {v}'
                                   for k, v in sorted(metrics.items())]
                    lines.append(f'- **Metrics:** {", ".join(metric_strs)}')
                lines.append('')

        # Lineage info
        lines.append('## Lineage')
        lines.append('')
        lines.append('| Run | Data Hash | Config Hash | Git Commit |')
        lines.append('| --- | --- | --- | --- |')
        for run in top_runs[:10]:
            name = run.get('run_name', run['run_id'][:8])
            tags = run.get('tags', {})
            params = run.get('params', {})
            data_hash = tags.get('dvc.data_hash', params.get('dvc_data_hash', '-'))
            config_hash = tags.get('hydra.config_hash', params.get('hydra_config_hash', '-'))
            git_commit = tags.get('noted.git_commit', '-')
            if data_hash and len(data_hash) > 12:
                data_hash = data_hash[:12] + '...'
            if config_hash and len(config_hash) > 16:
                config_hash = config_hash[:16] + '...'
            if git_commit and len(git_commit) > 7:
                git_commit = git_commit[:7]
            lines.append(f'| {name} | `{data_hash}` | `{config_hash}` | `{git_commit}` |')
        lines.append('')

        # Footer
        lines.append('---')
        lines.append('')
        lines.append(f'*Report generated by noted - {now}*')

        return '\n'.join(lines)

    def _generate_charts(self, output_dir: Path, runs: list,
                          metric_keys: list, experiment_id: str) -> str:
        """Generate metric charts as PNG files and return Markdown image references."""
        if not runs or not metric_keys:
            return ''

        lines = []
        lines.append('## Metric Charts')
        lines.append('')

        # Style setup
        plt.rcParams.update({
            'figure.facecolor': 'white',
            'axes.facecolor': '#fafafa',
            'axes.edgecolor': '#cccccc',
            'axes.grid': True,
            'grid.alpha': 0.3,
            'grid.color': '#cccccc',
            'font.family': 'sans-serif',
            'font.size': 10,
            'axes.titlesize': 12,
            'axes.labelsize': 10,
        })

        # Chart 1: Metric comparison bar chart (top runs side by side)
        chart_path = self._generate_metrics_bar_chart(output_dir, runs, metric_keys)
        if chart_path:
            lines.append(f'### Metrics Comparison')
            lines.append('')
            lines.append(f'![Metrics Comparison]({chart_path.name})')
            lines.append('')

        # Chart 2: Per-metric convergence (if metric history available)
        for mk in metric_keys[:4]:  # Limit to 4 most important metrics
            chart_path = self._generate_metric_history_chart(output_dir, runs, mk, experiment_id)
            if chart_path:
                lines.append(f'### {mk} - Convergence')
                lines.append('')
                lines.append(f'![{mk} History]({chart_path.name})')
                lines.append('')

        plt.rcParams.update(plt.rcParamsDefault)  # Reset to defaults
        return '\n'.join(lines)

    def _generate_metrics_bar_chart(self, output_dir: Path, runs: list,
                                      metric_keys: list) -> Path | None:
        """Generate a grouped bar chart comparing final metrics across top runs."""
        try:
            import numpy as np

            # Limit to top 6 runs and 6 metrics for readability
            top_runs = runs[:6]
            top_metrics = metric_keys[:6]

            if not top_runs or not top_metrics:
                return None

            run_names = [r.get('run_name', r['run_id'][:6]) for r in top_runs]
            n_runs = len(run_names)
            n_metrics = len(top_metrics)

            fig, axes = plt.subplots(1, n_metrics, figsize=(3.5 * n_metrics, 4), squeeze=False)
            colors = ['#42a5f5', '#66bb6a', '#ef5350', '#ff9800', '#ab47bc', '#26a69a']

            for j, mk in enumerate(top_metrics):
                ax = axes[0][j]
                values = []
                for r in top_runs:
                    v = r.get('metrics', {}).get(mk)
                    values.append(v if v is not None else 0)

                bars = ax.bar(range(n_runs), values, color=colors[:n_runs], width=0.6, edgecolor='white', linewidth=0.5)
                ax.set_title(mk, fontweight='600', fontsize=10)
                ax.set_xticks(range(n_runs))
                ax.set_xticklabels(run_names, rotation=45, ha='right', fontsize=8)
                ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.4f'))
                ax.tick_params(axis='y', labelsize=8)

                # Highlight best value
                if values:
                    is_higher_better = 'r2' in mk or 'accuracy' in mk or 'f1' in mk
                    best_idx = values.index(max(values) if is_higher_better else min(values))
                    bars[best_idx].set_edgecolor('#333333')
                    bars[best_idx].set_linewidth(1.5)

            fig.tight_layout(pad=2.0)
            chart_path = output_dir / 'metrics_comparison.png'
            fig.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            return chart_path

        except Exception as e:
            logger.warning("Failed to generate metrics bar chart: %s", e)
            return None

    def _generate_metric_history_chart(self, output_dir: Path, runs: list,
                                         metric_key: str, experiment_id: str) -> Path | None:
        """Generate a line chart showing metric history across epochs for top runs."""
        try:
            # Fetch metric history for each run
            histories = {}
            for run in runs[:5]:  # Top 5 runs
                try:
                    history = self._mlflow.get_metric_history(run['run_id'], metric_key)
                    if history and len(history) > 1:
                        steps = [p['step'] for p in history]
                        values = [p['value'] for p in history]
                        name = run.get('run_name', run['run_id'][:6])
                        histories[name] = (steps, values)
                except Exception:
                    pass

            if not histories:
                return None

            fig, ax = plt.subplots(figsize=(8, 4))
            colors = ['#42a5f5', '#66bb6a', '#ef5350', '#ff9800', '#ab47bc']

            for i, (name, (steps, values)) in enumerate(histories.items()):
                color = colors[i % len(colors)]
                ax.plot(steps, values, label=name, color=color, linewidth=1.5, alpha=0.85)

            ax.set_xlabel('Step', fontsize=10)
            ax.set_ylabel(metric_key, fontsize=10)
            ax.set_title(f'{metric_key} - Training Convergence', fontweight='600', fontsize=11)
            ax.legend(fontsize=8, loc='best', framealpha=0.9)
            ax.tick_params(labelsize=8)

            fig.tight_layout(pad=1.5)
            safe_key = metric_key.replace('/', '_').replace(' ', '_')
            chart_path = output_dir / f'history_{safe_key}.png'
            fig.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            return chart_path

        except Exception as e:
            logger.warning("Failed to generate history chart for %s: %s", metric_key, e)
            return None
