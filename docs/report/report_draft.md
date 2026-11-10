**1. 연구결과 요약문**

<table>
<colgroup>
<col style="width: 19%" />
<col style="width: 80%" />
</colgroup>
<thead>
<tr class="header">
<th><strong>과 제 명</strong></th>
<th>형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성
검증</th>
</tr>
<tr class="odd">
<th><p><strong>연구 필요성</strong></p>
<p><strong>및 목적</strong></p></th>
<th>원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는
다축 3D 프린팅 기법이다. 위치마다 출력 방향을 최적화하는 곡면
슬라이싱보다 설계변수가 훨씬 적어 계산이 가볍고 방사 대칭 형상에
효과적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔고, 형상에서
원뿔각을 자동으로 정하는 알고리즘은 조사 범위 내에서 확인되지 않았다. 본
연구는 STL 에서 원뿔각과 높이 구간별 각도를 자동 결정하는 알고리즘을
만들고, 그 결정의 신뢰성과 구간 개수에 따른 거동을 검증한다.</th>
</tr>
<tr class="header">
<th><p><strong>연구내용</strong></p>
<p><strong>및</strong></p>
<p><strong>결과</strong></p></th>
<th>① 원본 면 법선으로 서포트를 판정하는 해석식(유효 오버행 = 원래
오버행 − θ)과 면별 임계각 θ* = α − 45° 유도 ② 가변각의 층간격 Δz = h −
r·Δtanθ 로 층 교차 방지 조건·블렌드 최소 폭 유도 ③ 축대칭 17개 모델에서
두 균일 원뿔 기준선과 비교 <strong><mark>【보류: 대표
결과】</mark></strong> ④ 구간 수 최선해의 해석식 서포트는 단조 감소(위반
0/21)하나 N ≥ 3 에서 G-code 미지지가 커져(중앙 0 → 69mm) 밴드 수는
툴패스 검사로 상한을 둔다. 구간 분할의 고유 효과는 평균 기울기 감소(중앙
8.4°) ⑤ 판정식 독립 구현 대조 최대 차 1.42×10⁻¹⁴°, 퇴적 복원 IoU 3회
재실행 해시 일치 ⑥ 같은 판정식에서 곡면 슬라이서(S4)와 비교해 축대칭
모델의 서포트가 같거나 낮았고(구 0.0 대 0.1%, torus 10.6 대 12.5~16.3%)
계산은 약 450~1,200배 빨랐다</th>
</tr>
<tr class="odd">
<th><p><strong>향후</strong></p>
<p><strong>연구계획</strong></p>
<p><strong>(요약)</strong></p></th>
<th>제작한 5축 프린터(REP5X)로 사전 등록한 시험 출력(L0~L5)을 수행해
판정 기준과 압출 모형을 실물로 확인하고, 곡면 슬라이싱과의 정량 비교와
비축대칭 형상으로 범위를 넓힌다.</th>
</tr>
<tr class="header">
<th><p><strong>Keyword</strong></p>
<p><strong>(5개 이내)</strong></p></th>
<th>원뿔 슬라이싱, 원뿔각 자동 결정, 가변 원뿔각, 서포트 저감, 다축 3D
프린팅</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**2. 과제 수행 과정**

※ 외부 전문가 피드백, 생성형 AI 활용 표, 팀원 역할·기여도 칸은 팀이 직접
작성한다(이 초안에서 제외).

<table>
<colgroup>
<col style="width: 19%" />
<col style="width: 80%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>문제해결</strong></p>
<p><strong>과정</strong></p></th>
<th><p>① 판정 기준 선택 — 원뿔 변환은 XY 를 1/cosθ 배로 늘리는 비등각
사상이라 변환 공간의 각도는 실제 각도가 아니다(funnel: 실제 26° 에서
해결되는 벽이 변환 공간에서는 50.7° 필요). 원본 법선에서 층 방향을 직접
계산하는 해석식 하나를 판정 기준으로 정하고, 세 번 재유도와 팀원 독립
구현(약 22,000면)으로 대조하였다.</p>
<p>② 가변각 안전 조건 — 이웃 두 원뿔 층의 높이 차로 층 교차 방지 조건과
블렌드 최소 폭을 닫힌 식으로 얻고, 실제 G-code 의 층간격으로
확인하였다.</p>
<p>③ 해석의 공정성 — 평면이 아닌 균일 원뿔과 비교하고 기준선을 둘로
나누어 이득의 원천을 분리하였다. 판정 기준은 결과 전에 문서로
고정하였다.</p>
<p>④ 기계 안전 — 출력용 G-code 는 자체 사전 검사기와 팀원의 가상
프린터(독립 역기구학)를 모두 통과해야 출력하도록 하였다.</p></th>
</tr>
<tr class="odd">
<th><p><strong>과제 수행</strong></p>
<p><strong>과정에서의 학습</strong></p></th>
<th>좌표 변환과 역변환, 벡터 내적과 삼각함수 합성, 다중적분의
변수변환(야코비안), 5축 기구학(공구 중심점 제어, 역기구학)을 연구에 직접
적용하며 배웠다. G-code 와 Marlin 펌웨어 구조, PrusaSlicer 명령행,
단위·회귀 테스트로 코드를 검증하는 방법을 익혔다. 예측을 먼저 적고
계산·실물로 확인하는 절차가 결론의 신뢰도를 어떻게 바꾸는지 경험하였다.
<strong><mark>【팀 자체 평가 추가】</mark></strong></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**3. 연구보고서**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성
검증</p>
<p>저자명․저자명․저자명</p>
<p>○○과학고등학교</p>
<p>Shape-Adaptive Conical Slicing: An Automatic Cone-Angle Selection
Algorithm and Its Verification</p>
<p>author․author․author</p>
<p>○○ Science High School</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**국문 초록**

원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는
방법으로, 곡면 슬라이싱보다 설계변수가 적어 계산이 가볍고 방사 대칭
형상에 효과적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔다. 본
연구는 STL 의 면 법선에서 서포트 필요 여부를 닫힌 식으로 판정하고, 이를
바탕으로 원뿔각과 높이 구간별 각도를 자동 결정하는 알고리즘을 제안한다.
각도를 높이에 따라 바꿀 때 층이 교차하거나 벌어지지 않는 조건을 유도해
알고리즘에 넣었다. 축대칭 17개 모델에서 **<span class="mark">【보류:
대표 결과】</span>**. 구간 수를 늘린 최선해의 해석식 서포트는 단조
감소했지만 세 구간 이상에서는 실제 G-code 의 미지지가 커졌고, 구간
분할의 고유 효과는 평균 기울기를 줄이는 것이었다. 판정식은 독립 구현과
10⁻¹⁴° 수준에서 일치했고, 퇴적 복원 IoU 는 반복 실행에서 재현되었다.

주제어: 원뿔 슬라이싱, 원뿔각 자동 결정, 가변 원뿔각, 서포트 저감, 다축
3D 프린팅

**Ⅰ. 서론**

FDM 3D 프린팅은 모델을 수평면으로 잘라 아래층부터 쌓기 때문에, 아래로
45° 이상 기운 면에는 서포트가 필요하다. 서포트는 재료와 시간을 늘리고
표면을 손상시킨다. 다축 3D 프린팅은 출력 방향을 바꾸어 이를 푼다. 곡면
슬라이싱\[3,4\]은 위치마다 출력 방향을 최적화해 효율이 높지만 설계변수가
위치마다 있어 자유도가 매우 크고 대규모 최적화나 신경망 학습이 필요하다.
원뿔 슬라이싱\[1,2\]은 층 전체를 원뿔 반각 θ 하나로 기술해 계산이
가볍고, 기존 평면 슬라이서를 그대로 쓰며, 방사 대칭 형상의 오버행에
효과적이다(Table 1).

그러나 원뿔각은 지금까지 사람이 정했다. RotBot\[1\]은 45° 고정각을,
3축용 원뿔 슬라이서\[5,6\]는 사용자가 입력한 상수각을 쓴다. CNC
Kitchen\[7\]은 구역마다 이상적인 각도를 자동으로 고르는 알고리즘을 다음
과제로 꼽았다. 조사 범위 내에서 원뿔 슬라이싱 계열에서 원뿔각을
형상으로부터 자동 결정하고 정량 비교한 연구는 확인되지 않았다. 본 연구는
이 알고리즘을 만들고 세 질문에 답한다. **RQ1** STL 만으로 원뿔각을 자동
결정할 수 있는가. **RQ2** 그 결정은 믿을 만한가. **RQ3** 높이
구간(밴드)의 개수를 늘리면 어떻게 되며 몇 개를 써야 하는가. 평면 대비
감소는 원뿔 슬라이싱 일반의 성과이므로 비교 기준은 균일 원뿔(모델 전체에
각도 하나)로 한다.

**Table 1. Comparison of multi-axis slicing approaches**

| **방법**                                 | **층의 형태** | **설계변수**            | **방향·각도 결정** | **계산 비용** |
|------------------------------------------|---------------|-------------------------|--------------------|---------------|
| 곡면(S³-Slicer\[3\], Neural Slicer\[4\]) | 임의 곡면     | 위치마다 방향(3차원 장) | 자동(최적화·학습)  | 큼            |
| 원뿔(RotBot\[1\], Slicer4RTN\[5\])       | 원뿔면        | θ 1개                   | 사용자 지정        | 작음          |
| 본 연구                                  | 높이별 원뿔면 | 구간별 θ N개            | 자동               | 작음          |

**Ⅱ. 이론적 배경**

**1. 원뿔 변환\[1\]**

R = r / cosθ, φ′ = φ, Z′ = z + c·r·tanθ (c = +1 outward, −1 inward) (1)

변환한 모델을 평면 슬라이서가 Z′ = 상수로 자르고 되돌리면 층은 z = Z′ −
c·r·tanθ 인 원뿔면이 된다(Fig. 1).

<img src="media/162d1fab40de41b1e350cbb607b7098dff2eef1c.png"
style="width:4.91667in;height:2.91667in" />

**\[Fig. 1\] Actual layers of generated G-code on the r–z section: (a)
uniform 22°, (b) band 22°→0°**

**2. 서포트 판정식**

축을 지나는 단면에서 원뿔 층의 위쪽 단위 방향 b = (c·sinθ, cosθ) 와 면
법선 n 의 내적:

g(θ) = n_z·cosθ + c·n_r·sinθ, 서포트 필요 ⇔ g(θ) \< κ = −sin45° (2)

오버행 각 α 인 면은 n = (cosα, −sinα) 이므로

g(θ) = −sin(α − c·θ) ⇒ 유효 오버행 = α − θ, θ\* = α − 45° (3)

funnel 벽(α = 70.3°)은 θ = 26° 에서 44.3° 로 통과한다. 변환 공간에서
재면 같은 벽이 θ = 50.7° 에서야 통과한다(Fig. 2b) — 판정을 식 (2) 하나로
통일한 이유이다. 구현은 식 (2) 를 그대로 옮긴 세 줄이다.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<tbody>
<tr class="odd">
<td><p>def overhang_score(mesh, angle_deg, direction, radial=None):</p>
<p>nz = mesh.face_normals[:, 2]</p>
<p>nr = radial_normal(mesh) if radial is None else radial</p>
<p>d = _dir_sign(direction)</p>
<p>a = np.radians(angle_deg)</p>
<p>return nz * np.cos(a) + d * nr * np.sin(a) # 식 (2)</p>
<p><em>conical/analytic.py</em></p></td>
</tr>
</tbody>
</table>

<img src="media/ec4f9d9ad32e83be9776fb83091f52d67626ad01.png"
style="width:4.91667in;height:2.14583in" />

**\[Fig. 2\] (a) g(θ) for overhang faces and the threshold −sin45°; (b)
effective overhang vs. overhang measured in the warped space (funnel
wall)**

검산: 닫힌 식 θ\* 와 0~90° 전수 탐색이 무작위 면 423개에서 불일치 0,
팀원 독립 구현과 약 22,000면에서 최대 차 1.42×10⁻¹⁴°, 실제 원뿔 층
법선으로 잰 유효 오버행과 α − θ 의 차는 40,000점에서 최대 1.2×10⁻⁷°
였다.

<img src="media/2c99ed509ef4dc2c862cfaafe4ec5972a473e5be.png"
style="width:4.91667in;height:2.14583in" />

**\[Fig. 3\] (a) Effective overhang measured from actual cone-layer
normals vs. α − θ; (b) difference (×10⁻⁷°)**

**정확한 최적 각도.** 면마다 g 는 θ 의 연속함수이므로 서포트 면적 S(θ)
는 g = κ 가 되는 근에서만 바뀌는 계단함수이다. 근 사이에서 J = S(0) −
S(θ) − k·θ 는 −k·θ 로 감소하므로

θ̂ ∈ {0°} ∪ {면이 고쳐지는 근 θ\* = asin(κ/R) − atan2(n_z, c·n_r)} (4)

이다. 격자 없이 이 후보만 평가하면 최적이 정확히 나온다(Fig. 4).

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<tbody>
<tr class="odd">
<td><p>R = np.hypot(nz, b) # b = c·n_r</p>
<p>valid = R &gt; abs(kappa) * (1.0 + 1e-12) # R ≤ |κ| 면은 근 없음</p>
<p>s = np.arcsin(kappa / R[idx])</p>
<p>delta = np.arctan2(nz[idx], b[idx])</p>
<p>for base in (s - delta, math.pi - s - delta): # 첫 근, 둘째 근</p>
<p>...</p>
<p>gp = -nz[f] * np.sin(r) + b[f] * np.cos(r) # g'(근) &gt; 0 → 면이
고쳐짐</p>
<p><em>conical/exact_angle.py · face_roots</em></p></td>
</tr>
</tbody>
</table>

검산(33개 모델, 사전 기준 전부 통과): 0.001° 미세 격자 88,002점 중
정확해를 넘는 점 0, 반환 각도에서 해석식 재측정 차 2.8×10⁻¹³%. 2° 격자
대비 J 상승 32/33(torus +2.27: 최적 계단 폭 0.27° 를 격자가 밟지 못함),
계산 시간 1~4ms 대 3~78ms(합 0.09s 대 1.69s).

<img src="media/c96864e09be29bac7ddd96e5e2188ec96d64bf23.png"
style="width:4.91667in;height:1.90625in" />

**\[Fig. 4\] (a) Step-shaped support area S(θ) and the roots where faces
become supported; (b) J(θ) with the exact and 2° grid optima (waist r =
2 mm)**

**3. 가변 원뿔각과 층간격**

층 k 를 z_k(r) = Z′\_k − c·r·tanθ_k 로 두면 같은 반경에서 이웃 층 간격은

Δz(r) = h − c·r·(tanθ\_{k+1} − tanθ_k), m = Δz / h (5)

> • 층 교차 없음: 모든 r ≤ r_max 에서 Δz \> 0
>
> • tanθ 를 Z′ 에 선형 보간(블렌드 폭 w, 총 변화 ΔT) ⇒ m = 1 − c·r·ΔT /
> w 가 블렌드 안에서 일정 → θ 가 아닌 tanθ 를 보간하는 이유
>
> • 1/1.5 ≤ m ≤ 1.5 ⇒ w ≥ 2·r_b·\|ΔT\| (팽창), w ≥ 3·r_b·\|ΔT\| (압축)
>
> • 상수각(ΔT = 0) ⇒ m ≡ 1 : 균일 원뿔에는 없고 가변각에서만 생기는 제약

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<tbody>
<tr class="odd">
<td><p>def spacing_factor(self, zw, r, direction="outward"):</p>
<p>c = 1.0 if direction == "outward" else -1.0</p>
<p>return 1.0 - c * np.asarray(r, dtype=float) * self.slope_at(zw) # 식
(5)</p>
<p><em>conical/profile.py · AngleProfile</em></p></td>
</tr>
</tbody>
</table>

검산: 17개 모델의 블렌드 실제 최대 m = 1.47~1.50(한계 1.5 위반 0/17).
생성 G-code 에서 같은 반경의 이웃 층 간격을 직접 재면 측정/예측 비가
블렌드 안 11,764쌍에서 중앙값 1.0000, 95% 구간 \[0.9969, 1.0030\]
이었다(예측 간격이 h 의 0.68~1.46배로 변하는 구간 포함, 상수각 대조군
16,533쌍 \[0.9974, 1.0026\]).

밴드2(22°→0°) 의 블렌드 기울기 s = −0.378/mm 에서 m = 1.5 가 되는 반경은
1.32mm 이고, 실제 G-code 압출점의 m 최대는 1.379 였다(Fig. 5).

<img src="media/2990ed3fe7d23b1534e378f6929eb662ae2ab8ef.png"
style="width:4.91667in;height:2.76042in" />

**\[Fig. 5\] Layer-spacing factor m(r, z) of a two-band profile with the
limits 1/1.5 and 1.5**

<img src="media/d9326d9ed673300714413fcfd8b6a1577feeef5b.png"
style="width:4.91667in;height:2.45833in" />

**\[Fig. 6\] (a) Measured vs. predicted layer spacing from generated
G-code; (b) ratio distribution**

**4. 압출량 보정**

dV / dV′ = cos²θ · m (6)

역변환 시 압출량에 식 (6) 을 곱한다. 단독 벽에서는 1mm 당 압출비가 cosθ
가 되며, 생성 G-code 의 측정값은 22° 에서 0.9272 = cos22° 이고, 0~30° 전
구간에서 cosθ 와의 차가 1.5×10⁻⁵ 이하이다(Fig. 7). 실물 모형 판정은 L4
출력으로 한다.

<img src="media/58e9b25152923bc60eda736486389a83cdd79ba9.png"
style="width:3.54167in;height:2.8125in" />

**\[Fig. 7\] Extrusion per mm of a single wall vs. cone angle: measured
from generated G-code and cosθ**

**Ⅲ. 연구 방법 및 절차**

**1. 알고리즘**

θ̂ = argmax_θ J(θ), J(θ) = ΔS(θ) − k·\|θ\| (k = 0.2 %p/°) (7)

> ① STL 축 정렬 → ② 면별 g(θ) → ③ 균일각: 식 (7), 방향은 outward/inward
> 중 큰 J
>
> ④ 밴드: 높이 N 구간마다 θ, 블렌드는 식 (5) 의 최소 폭, J 에서 블렌드
> 면적 비용 차감
>
> ⑤ 변환 → 평면 슬라이서 → 역변환(식 (6) 압출 보정, 경로 오차 ≤ 0.05mm)
>
> ⑥ 5축: B = θ(Z′), C = 방위각, 회전 속도 상한, 베드 안전각 22.8° → ⑦
> 사전 검사 통과 시 출력

<img src="media/9a2aa3f47ec14acea2c0c42a9629368fd96f7373.png"
style="width:4.91667in;height:2.61458in" />

**\[Fig. 8\] Generated 5-axis toolpath colored by head tilt B, and B per
layer**

**2. 검증 계층과 실험 조건**

**Table 2. Verification layers**

| **계층**       | **측정량**                                              | **보장 범위**                          |
|----------------|---------------------------------------------------------|----------------------------------------|
| 해석식         | 면 법선으로 서포트 면적 %                               | 기하 판정(45° 문턱)                    |
| 툴패스 검사기  | G-code 비드 아래 앞 층 유무, 진짜 오버행 미지지 길이 mm | 실제 경로, 중력·냉각 없음              |
| 퇴적 복원      | 복원 형상 대 원본 IoU                                   | 형상 일치, 실물 아님                   |
| 기계 사전 검사 | 축 범위·베드 간섭·회전 속도, 독립 역기구학 대조         | 치수 일부 추정                         |
| 실물           | 사전 등록 시험 출력 L0~L5                               | **<span class="mark">【보류】</span>** |

**Table 3. Experimental conditions**

| **항목**       | **조건**                                                                                                               |
|----------------|------------------------------------------------------------------------------------------------------------------------|
| 표본           | 축대칭 17개: 구 1, 허리형 r = 1·2·3·4·5·7mm 6, 허리형 XY 배율 λ = 1.1~2 5, 로브 변형 5 / 데모: funnel, torus, mushroom |
| 층고·지지 모형 | 0.3, 0.4mm / 낙관 지지(처진 비드도 지지로 셈)                                                                          |
| 지표           | 미지지 길이 mm(0.5mm 이내 무승부), 평균 \|θ\|                                                                          |
| 기준선         | \(a\) J 가 고른 균일각 (b) 밴드 아래 구간 각도와 같은 균일각                                                           |
| 기계 제약      | 베드 안전각 적용/미적용 두 판                                                                                          |
| 사전 등록      | 판정 기준을 결과 전에 문서로 고정                                                                                      |

**Ⅳ. 연구 결과**

**1. 원뿔각 자동 결정 (RQ1)**

funnel 에서 고른 각도는 2° 격자 26°, 정확 탐색 25.26° 로 식 (3) 의 θ\* =
25.3° 와 일치하며, 서포트 51.5% → 0% 였다(구 14.7% → 0%).

**Table 4. Band2 vs. uniform baselines, 17 models (band2 wins · uniform
wins · ties, unsupported length)**

| **기준선**                       | **층고 0.4mm** | **층고 0.3mm** | **베드 안전각 (0.4 / 0.3)** |
|----------------------------------|----------------|----------------|-----------------------------|
| \(a\) J 가 고른 균일             | 5 · 3 · 9      | 5 · 0 · 12     | 3 · 1 · 13 / 3 · 0 · 14     |
| \(b\) 아래 구간 각도와 같은 균일 | 0 · 2 · 15     | 0 · 0 · 17     | 0 · 1 · 16 / 0 · 0 · 17     |

> • (a) 의 우세 5개 = 모두 밴드 아래 구간 각도 \> 균일각인 모델 (26 대
> 16°, 28 대 20°, 30 대 24°, 24 대 22°, 26 대 20°)
>
> • 평균 \|θ\| 감소: 기준선 (b) 대비 중앙 8.4° (1.0~11.1°, 17/17), (a)
> 대비 중앙 7.9° (1.0~9.4°, 12/17)
>
> • 램프(층고 0.3): 균일(J) 24° 17.8mm / 밴드 \[30°, 0°\] 0.0mm / 균일
> 30° 0.0mm

**<span class="mark">【보류: 결과 문장의 기준선】</span>**

<img src="media/76e762f02ccc153a207a0e5d3e6a1ce4ce4c6c44.png"
style="width:4.91667in;height:4in" />

**\[Fig. 9\] Unsupported length of 17 models: uniform (J), band2 and
uniform at band2's bottom angle; (a) 0.4 mm, (b) 0.3 mm layers**

<table>
<colgroup>
<col style="width: 50%" />
<col style="width: 50%" />
</colgroup>
<tbody>
<tr class="odd">
<td><p><img src="media/be89a372d5c139717c2617e0c8c864dc111a1249.png"
style="width:3.14583in;height:2.26042in" /></p>
<p><strong>[Fig. 10] Mean |θ| of uniform and band2 per
model</strong></p></td>
<td><p><strong><mark>【그림 대기: t1_regret.png】</mark></strong></p>
<p><strong>[Fig. 11] Regret of fixed conventional angles and automatic
selection</strong></p></td>
</tr>
</tbody>
</table>

**2. 구간(밴드) 개수 (RQ3)**

𝒫_N ⊂ 𝒫\_{N+1} ⇒ S\*\_{N+1} ≤ S\*\_N, S\*\_N → S\*\_∞ (N → ∞) (8)

N 구간 프로필은 한 구간을 같은 각도로 둘로 나누어 N+1 구간으로도
표현되므로 최선해 S\*\_N 은 단조 감소·수렴한다. 측정:

> • 각도 비용 k = 0 이면 밴드의 해석식 서포트 이득 = 0 (17/17) → 구간
> 분할의 값은 기울기 감소
>
> • N 을 J 로 고르면 오버행이 달성 가능한 최소보다 나쁨 (7/7)
>
> • 전수 최선해(21 모델, N = 1~4, N=3 에서 모델당 약 11만 후보): 식 (8)
> 위반 0/21. 평균 \|θ\| 중앙 44.0 → 16.8 → 10.8 → 9.7°
>
> • 같은 최선해의 G-code 미지지 중앙(층고 0.4): N = 1, 2, 3 에서 0.0 →
> 1.3 → 68.9mm. N ≥ 3 의 블렌드가 바닥 오버행 위에 놓여 층간격 팽창(m ≤
> 1.5)이 미지지를 만든다 — 식 (2) 에는 m 이 없다

**Table 5. Saturation band count N\* of the analytic optimum (21 models,
layer 0.3 mm)**

| **목적**                     | **N\* = 1** | **N\* = 2** | **N\* = 3** | **N\* ≥ 4** |
|------------------------------|-------------|-------------|-------------|-------------|
| ① 서포트 최소                | 1           | 1           | 2           | 17          |
| ② 같은 서포트에서 \|θ\| 최소 | 1           | 9           | 7           | 4           |

N\* = N → N+1 에서 미지지 감소 \< 0.5mm 이고 평균 \|θ\| 감소 \< 1° 인 첫
N. N\* = 1 은 mushroom.

→ 해석식 최선해는 기울기를 계속 줄이므로 포화하지 않지만(17/21 이 N\* ≥
4) 그 이득은 G-code 미지지로 되돌아온다. 밴드 수는 해석식이 아니라
툴패스 검사로 상한을 둔다(이 표본에서 N ≤ 2).

<img src="media/c45df8aadf8312f6ab69dbe31d5edc758edcd346.png"
style="width:4.91667in;height:2.15625in" />

**\[Fig. 12\] (a) Toolpath unsupported length and (b) area-weighted mean
\|θ\| of the analytic optimum vs. number of bands N; stars mark N\***

**가정.** 축대칭 곡면 층 z = Z′ − f(r) 의 1차 근사가 원뿔이며 오차는

\|f(r) − f(r₀) − f′(r₀)(r − r₀)\| ≈ ½·\|f″\|·(r − r₀)² (9)

이므로 층의 경선 곡률 f″ 가 작으면 원뿔족 극한(N → ∞)이 곡면 슬라이싱에
가깝다. 수치 확인: 2차 층에서 로그-로그 기울기 2.00000, 오차가 층고
0.3mm 를 넘는 거리는 b = 0.01/mm 에서 약 5.5mm, 0.05/mm 에서 약 2.4mm.
곡면 슬라이서 S4 를 같은 판정식으로 재면(Table 5): 구는 균일 원뿔 0.0%
대 S4 0.1%, torus 는 밴드 10.6% 대 S4 16.3%(수렴·뒤집힘 0 인 실행,
해상도에 따라 12.5~16.3%) 로 원뿔족이 같거나 나았다. S4 층의 경선
곡률(κ·r 중앙)은 구 0.086, torus 0.59 로, 곡률이 작은 구에서 S4 ≈
천장(+0.1%p)이었고 곡률이 큰 torus 에서도 곡면의 추가 자유도가 서포트
감소로 이어지지 않았다(천장 대비 +1.9~+5.7%p). funnel(54~61° 요구)과
mushroom(65~88° 요구)은 S4 변형에서 사면체가 뒤집혀(60여 개, 17%) 결과가
무효였다. mushroom 의 수평 아래면은 g = −cosθ 라 θ ≥ 45° 가 필요하여
원뿔 허용 범위(≤ 44°, 베드 안전각 22.8°) 밖이다.

**Table 6. Support area (%) along the degree-of-freedom ladder (same
criterion, eq. 2)**

| **모델** | **평면** | **균일** | **밴드** | **원뿔족 천장** | **곡면(S4)**      |
|----------|----------|----------|----------|-----------------|-------------------|
| sphere   | 14.7     | 0.0      | 0.0      | 0.0             | 0.1 (0.0~0.4)     |
| funnel   | 51.5     | 0.0      | 0.0      | 0.0             | 무효\*            |
| torus    | 25.0     | 18.6     | 10.6     | 10.6            | 16.3† (12.5~16.3) |
| mushroom | 27.5     | 27.5     | 27.5     | 27.5            | 무효\*            |

S4 범위 = 해상도 2 × 파라미터 2 실행. † 변형 4,000회로 수렴·뒤집힌
사면체 0 인 실행(1,000회와 같은 값). \* 변형 미수렴·사면체 뒤집힘(funnel
60여 개, mushroom 17%) — 무효. mushroom 은 회전체 합집합 메시.

<img src="media/2f303ea6cf5b2e8843351c642cef2a40d47b1358.png"
style="width:4.91667in;height:2.14583in" />

**\[Fig. 13\] Support area from planar to the cone-family ceiling and
curved slicing (S4); (a) all faces, (b) excluding bed-contact faces; ×
marks invalid S4 runs**

<img src="media/6361cfcee3b0894652abff5e48a46c523cce5ea3.png"
style="width:4.13542in;height:2.79167in" />

**\[Fig. 14\] Curved (S4) layers vs. cone-family layers on the r–z
section**

<img src="media/96123937e50082e1fb99606c901454ad63c822ec.png"
style="width:4.91667in;height:2.14583in" />

**\[Fig. 15\] (a) Curved layer and its tangent cone; (b) height error
vs. r on log–log axes (slope 2)**

**3. 결정의 신뢰성 (RQ2)**

퇴적 복원 IoU = 평균 교집합 / 평균 합집합(복셀당 측정점 4개, 복셀
0.3mm). mushroom_03, 46개 각도 후보:

**Table 7. Deposition-reconstruction IoU (mushroom_03)**

| **각도**     | **IoU**     | **3회 재실행** | **비고**                      |
|--------------|-------------|----------------|-------------------------------|
| 0°           | 0.9262      | 해시·IoU 일치  |                               |
| 10°          | 0.9317      | 해시·IoU 일치  | 측정 최대                     |
| 12°          | 0.9267      | 해시·IoU 일치  |                               |
| 이웃 각도 차 | 평균 0.57%p | —              | 0~12° 순위는 해상도로 못 가림 |

<img src="media/fff59045ff311ee4758d92ffc2aefd9f14003b8b.png"
style="width:4.91667in;height:2.09375in" />

**\[Fig. 16\] Deposition-reconstruction IoU over 46 cone-angle
candidates (mushroom_03) with three re-runs**

메시 예측 대 G-code 측정: 균일 0~44°(12각)의 해석식 서포트 순위와 툴패스
미지지 순위의 모델별 스피어만 ρ 중앙값 0.956(층고 0.3), 0.998(0.4),
20모델. 0.8 미만은 안·바깥 두 방향 오버행을 가진 torus 하나(−0.73 /
0.01), mushroom 은 해석식이 모든 각에서 28.27% 로 상수라 ρ 가 정의되지
않는다.

<img src="media/f8d24f2e83c3c3b0de986ce07936489b504fa10c.png"
style="width:4.91667in;height:2.16667in" />

**\[Fig. 17\] Analytic prediction vs. toolpath measurement with
per-model Spearman ρ**

**4. 실물 출력**

**Table 8. Pre-registered predictions for the test ladder**

| **단계** | **출력물**                     | **예측**                   | **실측**                               |
|----------|--------------------------------|----------------------------|----------------------------------------|
| L1       | 원기둥 r10 × 8, B = 0          | 지름 20.0mm                | **<span class="mark">【보류】</span>** |
| L4a/b    | 단벽 원기둥 B = 0 / 22°        | 벽 두께비 0.927 (식 6)     | **<span class="mark">【보류】</span>** |
| L5       | 오버행 계단 40~65°, 평면       | 50° 단부터 처짐(식 2)      | **<span class="mark">【보류】</span>** |
| L2p/L2   | 벽 60° 원뿔대: 평면 / 균일 15° | 49.87%p / 0.00%p           | **<span class="mark">【보류】</span>** |
| L3a/b    | 램프: 균일 22° / 밴드 22°→0°   | 0.53 / 0.58%p (구별 안 됨) | **<span class="mark">【보류】</span>** |

| **<span class="mark">【사진 대기: 개조한 REP5X 프린터 전경 · 헤드(B/C축) 근접】</span>** |
|------------------------------------------------------------------------------------------|

**\[Fig. 18\] The modified 5-axis printer (REP5X on Ender-3 V3 SE)**

| **<span class="mark">【사진 대기: L1~L5 출력물 — 같은 조명·배경·스케일, 4방향 + 위】</span>** |
|-----------------------------------------------------------------------------------------------|

**\[Fig. 19\] Printed test ladder L1–L5**

**5. 계산 비용**

균일각 결정: 정확 탐색 1~4ms(33개 모델 합 0.09s), 2° 격자 3~78ms. 같은
사면체 메시(1.2~4.0만 개)에서 원뿔 각도 결정(균일+밴드+천장) 0.12~0.27s
대 S4 68~334s(변형 단계가 절반 이상) — 약 450~1,200배.
**<span class="mark">【보류: 메시 크기별 — T7】</span>**

<table>
<colgroup>
<col style="width: 50%" />
<col style="width: 50%" />
</colgroup>
<tbody>
<tr class="odd">
<td><p><strong><mark>【그림 대기: t7_scaling.png】</mark></strong></p>
<p><strong>[Fig. 20] Run time vs. number of faces
(log–log)</strong></p></td>
<td><p><img src="media/61b7ce565629644311225a4ced387e9caf590540.png"
style="width:3.14583in;height:1.375in" /></p>
<p><strong>[Fig. 21] Run time: cone-angle selection vs. S4
stages</strong></p></td>
</tr>
</tbody>
</table>

**Ⅴ. 고찰**

> • **이득의 원천**: (a) 대비 우세 5/17 은 전부 아래 구간 각도 차이, (b)
> 대비 0/17 → 자동 결정의 이득 = 형상에 맞는 아래 구간 각도 선택. 구간
> 분할의 고유 효과 = 평균 \|θ\| 중앙 8.4° 감소(실물 가치는 L3 로 판정).
> **<span class="mark">【보류: 베드 램프 결과 포함 여부】</span>**
>
> • **기울기 감소의 한계**: 8.4° 는 J 가 고른 밴드2 에서 잰 값이다.
> 기울기를 최대로 줄인 최선해(평균 \|θ\| 중앙 4.6°)는 해석식 서포트가
> 같아도 G-code 에서 16~20/21 모델이 균일에 졌다 — 해석식이 층간격을
> 모르기 때문이다
>
> • **자유도를 줄인 대가**: 같은 판정식에서 S4 대비 구 −0.1%p, torus
> −1.9~−5.7%p(원뿔족이 나음), 계산 450~1,200배 빠름. S4 층도 사실상
> 축대칭(접선 성분 평균 ≤ 0.051)이어서 이 표본에서는 곡면도 경선 곡선
> 하나를 고르는 문제였다. 단 사전 기준을 모두 통과한 조건은 없고(구: 1만
> 3천 개 중 사면체 1개 뒤집힘, torus: 변형 4,000회 실행만 수렴·뒤집힘 0)
> 유효 표본 2개라 경향으로만 쓴다
>
> • **적용 범위**: 수평 아래면(mushroom)은 θ ≥ 45° 가 필요해 허용 범위
> 밖 — 원뿔족이 풀 수 없고 S4 도 유효한 해를 내지 못했다
>
> • **한계**: 축대칭 표본 17개, 45° 문턱 기하 판정(중력·냉각 없음),
> 핫엔드 치수·베드 안전각 22.8° 는 공개 자료 기반 추정, 실물 결과
> **<span class="mark">【보류】</span>**

**Ⅵ. 결론**

본 연구는 원뿔 슬라이싱의 원뿔각을 STL 에서 자동으로 결정하는 알고리즘을
만들었다. RQ1: 원본 면 법선만으로 서포트를 판정하는 해석식을 유도하고,
원뿔각과 방향, 구간별 각도를 자동으로 결정하였다.
**<span class="mark">【보류: 대표 결과 한 문장】</span>** RQ2: 판정식은
독립 구현과 일치했고, 선택한 각도의 G-code 는 퇴적 복원에서 재현되었다.
RQ3: 구간 수를 늘린 최선해의 해석식 서포트는 단조 감소하지만, 세 구간
이상에서는 블렌드의 층간격 팽창이 실제 G-code 의 미지지를 키웠다. 따라서
구간 수는 J 나 해석식이 아니라 툴패스 검사로 상한을 두어야 하며, 이
표본에서는 두 구간이 한계였다. 또한 곡면 슬라이서와 같은 판정식으로
비교했을 때 축대칭 모델에서 원뿔족은 서포트에서 뒤지지 않으면서 계산이
수백 배 가벼워, 자유도를 줄인 선택의 근거가 되었다. 향후 제작한 5축
프린터로 사전 등록한 시험 출력을 수행하고, 곡면 슬라이싱과의 정량 비교와
비축대칭 형상으로 연구를 넓힐 것이다.

**연구 신뢰성 정리**

**Table 9. Summary of reliability evidence**

| **무엇을 믿게 하나**       | **근거**                                                                                          | **범위·단서**                                    |
|----------------------------|---------------------------------------------------------------------------------------------------|--------------------------------------------------|
| 판정식 구현                | 재유도 3회(최대 차 7.6×10⁻¹⁴°), 팀원 독립 구현 약 22,000면(1.42×10⁻¹⁴°), 전수 탐색 423면 불일치 0 | 45° 문턱 가정은 공유                             |
| 정답을 아는 입력           | 수직 원기둥·직육면체 0%p, 60° 원뿔 판정 일치                                                      |                                                  |
| 예측 단계가 G-code 를 대표 | 해석식 대 툴패스 순위상관 ρ 중앙 0.956(층고 0.3)·0.998(0.4), 20모델                               | 두 방향 오버행(torus)·수평 아래면(mushroom) 제외 |
| 유도한 식                  | 증명 9개 식, 저장소 코드 없이 독립 수치 검산(야코비안 상대오차 1.1×10⁻⁷ 등)                       | 식의 일치, 물리 검증 아님                        |
| 기존 방식과의 일치         | 상수 프로필 = RotBot 고정각(회귀 테스트, 왕복 오차 10⁻¹⁴ 수준)                                    |                                                  |
| 코드 전체                  | 단위·회귀 테스트 230개 통과, 정적 검사 0건                                                        |                                                  |
| 기계 안전                  | 자체 사전 검사 + 팀원 가상 프린터(독립 역기구학), 시험 출력 파일 치명 결함 0                      | 핫엔드 치수·축 부호 실측 전                      |
| 재현성                     | 같은 입력 → 바이트 단위로 같은 G-code, 퇴적 복원 3회 해시 일치                                    |                                                  |
| 해석의 공정성              | 판정 기준 사전 등록                                                                               |                                                  |
| 독립성의 한계              | 검증 계층 일부가 같은 AI 도구로 작성됨                                                            | 완전 독립 아님                                   |

**■ 참고문헌**

\[1\] Wüthrich, M., Gubser, M., Elspass, W. J., & Jaeger, C. (2021). A
novel slicing strategy to print overhangs without support material.
Applied Sciences, 11(18), 8760.

\[2\] Coupek, D., Friedrich, J., Battran, D., & Riedel, O. (2018).
Reduction of support structures and building time by optimized path
planning algorithms in multi-axis additive manufacturing. Procedia CIRP,
67, 221–226. **<span class="mark">【서지 원문 확인 필요】</span>**

\[3\] Zhang, T., Fang, G., Huang, Y., Dutta, N., Lefebvre, S., Kilic, Z.
M., & Wang, C. C. L. (2022). S³-Slicer: A general slicing framework for
multi-axis 3D printing. ACM Transactions on Graphics, 41(6), 277.

\[4\] Liu, T., Zhang, T., Chen, Y., Huang, Y., & Wang, C. C. L. (2024).
Neural slicer for multi-axis 3D printing. ACM Transactions on Graphics,
43(4), 85.

\[5\] Slicer4RTN. https://xyzdims.com/3d-printing/slicer4rtn/ (접속일
기입)

\[6\] CNC Kitchen. ConicalSlicer.
https://github.com/CNCKitchen/ConicalSlicer (접속일 기입)

\[7\] CNC Kitchen. Conical Slicing: A different angle of 3D printing.
https://www.cnckitchen.com/blog/conical-slicing-a-different-angle-of-3d-printing
(접속일 기입)

\[8\] Klappe, D. Rep5x. https://github.com/dennisklappe/Rep5x (접속일
기입)
