# 보고서 그림 (`docs/report/figures/`)

모든 그림은 저장소의 실제 코드·데이터·G-code 에서 계산해 그린다. 그림마다 스크립트 하나,
결과는 `docs/report/figures/<slug>.png` 와 `manifest.json`(데이터 출처·커밋·핵심 수치).

```bash
apt-get install -y fonts-nanum && rm -rf ~/.cache/matplotlib   # NanumGothic 필요
export PYTHONPATH=. MPLBACKEND=Agg
for s in conical_layers_lamp g_theta_funnel critical_angle_hist support_vs_angle spacing_heatmap \
         extrusion_ratio baseline_bars tilt_reduction dof_ladder toolpath_3d theta_star_check \
         layer_spacing_measured; do python3 tools/report_figs/$s.py; done
# 팀 저장소 데이터가 필요한 그림 하나
git clone https://github.com/26037-arch/R-E-second-presentation.git ../R-E-second-presentation
python3 tools/report_figs/iou_angle.py --ext ../R-E-second-presentation
```

공통 스타일은 `style.py`(9pt, 300dpi, 폭 16 / 7.8cm, 그림 안 제목 없음, tab10, 패널 라벨 (a)(b)).
G-code 읽기는 `gcodeio.py`, `gap_sample_results.json` 읽기와 `docs/gap_audit.md` §9.3 표 대조는 `gapdata.py`.
