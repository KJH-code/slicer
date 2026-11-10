# R&E 연구보고서 HWPX

- `RnE_report_template_2026.hwpx` — 배포 양식(.hwp)을 python-hwpx 로 HWPX 변환한 빈 양식
- `RnE_report_2026.hwpx` — 양식에 `docs/report/report_draft.md` 초안(브랜치 `claude/clever-lovelace-6cn1th`)을 채운 결과
- `content.py` — 채운 내용(초안 전사). 수식은 `$LaTeX$` 로 적고 한글 네이티브 수식(`<hp:equation>`)으로 넣는다
- `build.py` — 양식 + 그림 폴더 → 결과 HWPX
- `equations.tsv` — 수식 157개의 LaTeX 원문 ↔ 한글 수식 스크립트(EqEdit) 대응표

재생성 (hwpx-plugin 의 런타임 파이썬, python-hwpx 6.6.0):

```
python -I build.py RnE_report_template_2026.hwpx <docs/report/figures> RnE_report_2026.hwpx
```

그림 폴더는 `claude/clever-lovelace-6cn1th` 의 `docs/report/figures/` 다.
`【...】` 형광 표시는 초안의 보류 칸을 그대로 옮긴 것이다(실물 결과·대표 결과 문장·t1_regret 그림·사진).
