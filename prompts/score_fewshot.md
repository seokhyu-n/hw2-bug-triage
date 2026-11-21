# Examples
판단 순서(근거 → 점수)를 보여주는 예시다. 예시의 값을 실제 입력에 옮겨 쓰지 않는다.

## Example 1 — 크래시, 앱 버전 누락
입력 요약: extraction = {device_model: "Galaxy S23", android_version: "14", app_version: null, symptom: "러닝 시작 시 앱 종료", repro_steps: ["로그인", "달리기 시작 터치"], frequency: "매번", missing_fields: ["app_version"]}, classification = bug, link = {linked_issue_id: "ISSUE-02", fixed_in: "1.2.0"}
출력:
```json
{"reasoning": "영향 범위: Android 14 사용자 전체(최신 OS라 사용자 비중이 큼). 빈도: 매번. 우회: 1.2.0에서 수정됐지만 제보자 앱 버전을 몰라 업데이트로 해결되는지 확인 불가. 데이터 손실: 러닝 자체를 시작할 수 없음. 크래시 + 다수 사용자 영향 → P1. 증상·안드로이드 버전·재현 절차는 있으나 앱 버전이 없어 환경 핵심 누락 → 완성도 1.", "completeness": 1, "priority": "P1", "questions_to_reporter": ["사용 중인 RunBuddy 앱 버전을 알려주세요(설정 > 앱 정보에서 확인할 수 있어요)."]}
```

## Example 2 — 사소한 표시 문제, 정보 충분
입력 요약: extraction = {device_model: "Pixel 8", android_version: "14", app_version: "1.2.0", symptom: "기록 상세 화면의 '페이스' 글자가 잘려 보임", repro_steps: ["기록 탭 진입", "러닝 기록 하나 선택"], frequency: "매번", missing_fields: []}, classification = bug, link = {linked_issue_id: null}
출력:
```json
{"reasoning": "영향 범위: 기록 상세 화면을 보는 사용자. 빈도: 매번. 우회: 값 자체는 다른 곳에서 확인 가능. 데이터 손실: 없음. 기능에는 영향이 없는 표시 문제 → P4. 증상·환경(OS·앱 버전)·재현 절차 모두 있음 → 완성도 2.", "completeness": 2, "priority": "P4", "questions_to_reporter": []}
```

## Example 3 — 증상 불명확
입력 요약: extraction = {모든 필드 null, symptom: "앱이 이상하게 동작함(구체적 증상 없음)", repro_steps: [], missing_fields: ["app_version", "android_version", "device_model", "repro_steps"]}, classification = bug, link = {linked_issue_id: null}
출력:
```json
{"reasoning": "영향 범위: 알 수 없음. 빈도: '자꾸'라고만 함. 우회: 알 수 없음. 데이터 손실: 언급 없음. 크래시나 데이터 손실이 확인되지 않아 원문으로 확인되는 범위에서 P3. 무엇이 잘못됐는지 알 수 없어 완성도 0.", "completeness": 0, "priority": "P3", "questions_to_reporter": ["어떤 화면에서 무엇을 했을 때 어떻게 이상했는지 구체적으로 알려주세요.", "사용 중인 RunBuddy 앱 버전을 알려주세요(설정 > 앱 정보).", "휴대폰 기종과 안드로이드 버전을 알려주세요(설정 > 휴대전화 정보).", "문제가 생기기 직전에 한 행동을 순서대로 적어 주세요."]}
```
