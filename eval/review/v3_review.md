# dataset_v3 정답 검토 목록

새 사례 130건 중 판단이 갈릴 수 있는 정답. 사람이 확인하고 바꿀 것이 있으면 `eval/new_cases_v3_<part>.py`를 고친 뒤
`python -m eval.new_cases_v3_<part>` → `python -m eval.build_dataset_v3`로 다시 만든다(저장된 예측으로 재채점 가능).

| 사례 | 묶음 | 판단이 갈리는 이유 |
|---|---|---|
| E-125 | a | 카운트다운 없이 바로 시작: 정상 동작과 달라 bug로 봤지만 기록 자체는 되므로 P3/P4 경계, 설정 존재 여부에 따라 question일 수도 있음 |
| E-131 | a | '저장 실패'로 그 러닝 기록이 남지 않음: 루브릭 P2 예시(기록 저장이 안 됨, 앱은 살아 있음)를 따랐으나 러닝 기록 유실(P1)로 볼 여지 |
| E-133 | a | 전송 버튼 비활성: 유료·별도 가입 정책이면 question, 로그인된 상태라 고장으로 보고 bug+question |
| E-136 | a | 주간 보기 빈 화면: 기록 조회(핵심)로 P2, 월간 보기로 우회 가능하다고 보면 P3 |
| E-137 | a | 러닝하지 않을 때의 배터리 소모: ISSUE-03(러닝 중)과 다름. 우선순위 P2 vs P3, 연결 안 함 |
| E-143 | a | 자정 넘긴 러닝의 월 귀속: 정책 문의로 봤지만 시작 시간 기준이 맞다고 보면 bug |
| E-145 | a | 카드 사진 정사각형 크롭: 설계로 보고 question, 찌그러짐(E-045)처럼 표시 결함이나 개선 요청으로 볼 여지 |
| E-160 | a | '자동 일시정지가 안 돼요': 기능이 없다는 전제(E-086 요청)로 feature_request, 분류 프롬프트에 기능 존재 여부가 명시되지 않아 bug로 볼 여지 |
| E-165 | a | 다른 기기 로그인 시 기록 없음: 기록이 기기 저장(E-021)이라 보고 question+feature_request, 서버 동기화가 있어야 한다면 데이터 유실 bug(P1) |
| E-167 | b | ISSUE-01 crash on Android 7.0 but app version unstated: P1 (fixed version not confirmed by text, as E-064) vs P2 (old-OS issue already fixed). |
| E-170 | b | Linked to ISSUE-02 with no app version; the user only says they have not updated for months. Linking is allowed (app_version null) but a strict linker may refuse. |
| E-172 | b | Battery drained until the phone switched off mid-run: P2 (battery, as E-015) vs P1 (run possibly lost). No crash tag since the app did not crash. |
| E-177 | b | Phrased as 'where is the weight menu?' but claims calories are too high: labelled bug+question linked to ISSUE-05; could be read as question/feature_request (cf. E-117 near miss). |
| E-183 | b | Card crash on a Galaxy S7 (old device) with no versions: P1 because neither the fixed version nor the old OS is confirmed by the text; P2 is arguable via 'specific old device'. |
| E-188 | b | Login impossible matched to fixed ISSUE-11 on app 1.0: P2 following E-057 precedent, though Android 12 is not an old OS so a strict P1 rule could apply. E-189 (no versions) is P1. |
| E-196 | b | Straight-line course on 1.1.1 (after ISSUE-06 fix): P2 following E-071 (course route), P3 arguable as map display. |
| E-199 | b | High-res photo card crash on Android 11 / app 1.0: not linked because ISSUE-08 lists Android 7-9 only, although the app version is affected and the cause is plausibly the same. |
| E-204 | b | Session not kept (logout on every restart): login still works, so P3; P2 arguable because login is a core feature. |
| E-207 | b | '안드14' names the known issue, not the user's OS, and One UI 6.1 is not an Android version, so android_version is null; app_version is the installed 1.1.1, not the 1.2.0 asked about. |
| E-212 | c | 기록 유실을 본인도 확신하지 못함('것 같기도'). 유실이 적혀 있다고 보면 P1, 확인된 범위만 보면 P2/P3 |
| E-223 | c | 루브릭 예시 '기록 저장이 안 됨(앱은 살아 있음)'=P2이지만 '3번째 날렸네요'는 기록 유실로도 읽혀 P1 여지 |
| E-225 | c | 앱 재시작으로 기록이 다시 보이는 우회가 있어 P3로 볼 여지(데이터는 남아 있음) |
| E-226 | c | 다시 누르면 될 때도 있어 '우회 가능'(P3) 여지. 핵심 기능(러닝 시작) 불안정으로 P2 |
| E-228 | c | 기록 목록 조회(핵심) 오동작으로 P2. 상세 화면 문제(부가)로 보면 P3 |
| E-229 | c | 안드로이드 버전 없음. ISSUE-08 연결 결과(Android 7~9 한정, 1.0.1 수정)와 구형 기기 S9로 P2. 원문만으로 구형 OS 확인 불가로 보면 P1 |
| E-237 | c | 로그인은 되지만 20초 지연. 핵심 기능(로그인) 오동작이면 P2, 우회·사용 가능이면 P3 |
| E-239 | c | 핵심(GPS 추적) 오동작이지만 설정 변경으로 해결돼 P3. 기본 설정에서 발생하므로 P2 여지 |
| E-242 | c | 증상 불명확이라 완성도 0, 우선순위는 확인된 범위로 P3. '숫자'가 거리·페이스면 P2 |
| E-246 | c | 글씨가 '이상함'만으로 증상 불명확(0). 표시 문제라 P4로 뒀지만 증상 불명 버그 관례(P3)와 충돌 가능 |
