"""Generate and execute review notebooks; not a fabricated pre-experiment diary."""

import json
import sys
import tempfile
from pathlib import Path

import nbformat as nb
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager

from backend.database import ROOT

SETUP = """from pathlib import Path
import sys, json
import pandas as pd
import numpy as np
ROOT = Path.cwd()
if not (ROOT / 'backend').exists(): ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
from backend.database import make_engine
import matplotlib.pyplot as plt
"""
NOTEBOOKS = {
    "01_data_analysis": [
        (
            "markdown",
            "# Source audit and coverage\nExecuted review notebook generated after the data pipeline was implemented. Re-runs the real source audit, not manually entered counts.",
        ),
        ("code", SETUP),
        (
            "code",
            "from scripts.audit_data import audit\nreport = audit(ROOT/'dataset')\npd.DataFrame([{'table':n,'rows':t['rows'],'years':str(t['year_range']),'missing_cells':sum(c['missing'] for c in t['columns'].values())} for n,t in report['tables'].items()])",
        ),
        (
            "code",
            "coverage = pd.DataFrame({n:t['rows_by_year'] for n,t in report['tables'].items() if t['rows_by_year']}).fillna(0)\nax=coverage[['results','qualifying','lap_times','pit_stops']].plot(figsize=(10,4),logy=True)\nax.set_ylabel('Recorded rows (log scale)'); ax.set_xlabel('Season'); plt.tight_layout(); plt.show()",
        ),
        (
            "markdown",
            "Coverage starts do not imply complete recording. Weather and tyres are absent. The storage grain preserves historical shared-drive result records. See the audited limitations and sprint-era constructor-points finding in the repository.",
        ),
    ],
    "02_baseline": [
        (
            "markdown",
            "# Reproduce the grid baseline\nThis notebook calls production training/evaluation modules and checks the saved validation metrics. It was executed after EXP-001, not presented as an earlier diary.",
        ),
        ("code", SETUP),
        (
            "code",
            "from backend.ml.features import source_frame, baseline_frame, split_masks\nfrom scripts.train_baseline import fit_baseline\nfrom backend.ml.evaluation import metrics\nframe=baseline_frame(source_frame(make_engine()))\nmodel=fit_baseline(frame)\nvalid=frame.loc[split_masks(frame)['validation']]\nscore=metrics(valid,model.predict_proba(valid[['grid_position']])[:,1])\nsaved=json.loads((ROOT/'reports/baseline_metrics.json').read_text())['validation']\nassert abs(score['log_loss']-saved['log_loss'])<1e-10\npd.Series({k:v for k,v in score.items() if k!='calibration_bins'})",
        ),
        (
            "code",
            "grid=pd.DataFrame({'grid_position':range(1,26)})\nplt.plot(grid.grid_position,model.predict_proba(grid)[:,1]); plt.xlabel('Encoded grid position'); plt.ylabel('Podium probability'); plt.title('Fitted grid-only baseline'); plt.show()",
        ),
    ],
    "03_feature_engineering": [
        (
            "markdown",
            "# Feature audit and experiment comparison\nOutputs below inspect executed experiments and real historical feature rows. Model development lives in tested Python modules.",
        ),
        ("code", SETUP),
        (
            "code",
            "from backend.ml.features import source_frame, build_features, FEATURE_SETS\nframe=build_features(source_frame(make_engine()))\nframe.loc[(frame.year==2024)&(frame.driver_id==844),['date','race_id',*FEATURE_SETS['full']]].head()",
        ),
        (
            "code",
            "comparison=pd.read_csv(ROOT/'reports/model_comparison.csv')\ncomparison[['experiment_id','model','feature_set','log_loss','brier_score','top3_hit_rate']]",
        ),
        (
            "code",
            "ablations=json.loads((ROOT/'reports/hypothesis_ablations.json').read_text())\npd.DataFrame([{'experiment':r['experiment_id'],'validation_log_loss':r['validation']['log_loss'],'validation_brier':r['validation']['brier_score']} for r in ablations])",
        ),
        (
            "markdown",
            "Recent podium rate alone did not outperform career rate. Circuit history modestly improved the controlled team-feature comparison. These are descriptive validation comparisons, not causal claims or significance tests.",
        ),
    ],
    "04_model_evaluation": [
        (
            "markdown",
            "# Frozen model: final-test reproduction\nThe final test is already consumed. This notebook reproduces the recorded evaluation; it does not create a new untouched test or tune the model.",
        ),
        ("code", SETUP),
        (
            "code",
            "import joblib\nfrom scipy.special import expit\nfrom backend.ml.features import split_masks\nfrom backend.ml.evaluation import metrics\nframe=pd.read_csv(ROOT/'data/processed/features.csv')\ntest=frame.loc[split_masks(frame)['test']]\na=joblib.load(ROOT/'models/podium_model.joblib')\np=expit(a['calibration']['slope']*a['model'].decision_function(test[a['features']])+a['calibration']['intercept'])\nscore=metrics(test,p)\nsaved=json.loads((ROOT/'reports/final_test_metrics.json').read_text())\nassert abs(score['log_loss']-saved['selected_model']['log_loss'])<1e-10\npd.DataFrame({k:{m:v for m,v in saved[k].items() if m!='calibration_bins'} for k in ['baseline','selected_model']})",
        ),
        (
            "code",
            "for name in ['baseline','selected_model']:\n bins=pd.DataFrame(saved[name]['calibration_bins']); plt.plot(bins.mean_probability,bins.observed_rate,'o-',label=name)\nplt.plot([0,1],[0,1],'--',color='gray'); plt.xlabel('Mean predicted probability'); plt.ylabel('Observed podium rate'); plt.legend(); plt.title('2022–2024 reliability diagram'); plt.show()",
        ),
        (
            "markdown",
            "The selected model improved log loss, Brier score and ROC-AUC, but top-three hit rate was slightly lower. Independent marginals do not sum to three. No claims of perfect prediction or live point-in-time provenance are made.",
        ),
    ],
}


def main():
    with tempfile.TemporaryDirectory(prefix="f1-kernel-") as directory:
        kernel = Path(directory) / "python3"
        kernel.mkdir()
        (kernel / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "F1 project Python",
                    "language": "python",
                }
            )
        )
        manager = KernelSpecManager(kernel_dirs=[directory])
        for name, cells in NOTEBOOKS.items():
            notebook = nb.v4.new_notebook(
                cells=[
                    nb.v4.new_code_cell(body) if kind == "code" else nb.v4.new_markdown_cell(body)
                    for kind, body in cells
                ]
            )
            notebook.metadata.kernelspec = {
                "name": "python3",
                "display_name": "Python 3",
                "language": "python",
            }
            client = NotebookClient(
                notebook,
                timeout=180,
                kernel_name="python3",
                resources={"metadata": {"path": str(ROOT)}},
                kernel_spec_manager=manager,
            )
            client.execute()
            nb.write(notebook, ROOT / "notebooks" / f"{name}.ipynb")
            print(name, "executed", flush=True)


if __name__ == "__main__":
    main()
