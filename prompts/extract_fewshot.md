# Examples
아래 예시는 형식과 판단 기준을 보여주기 위한 것이다. 예시의 값을 실제 입력에 옮겨 쓰지 않는다.

## Example 1 — 정보가 충분한 제보
<report>
갤럭시 S21(안드로이드 13), 앱 1.1.0 씁니다. 러닝 시작하고 5km쯤 뛰었는데 기록 보니 3.2km로 나와요. 터널 지나간 뒤부터 거리가 안 늘었어요. 두 번 연속 이랬어요.
</report>
출력:
```json
{"device_model": "갤럭시 S21", "android_version": "13", "app_version": "1.1.0", "feature_area": "tracking", "symptom": "터널 통과 후 거리가 늘지 않아 총 거리가 실제보다 짧게 기록됨", "expected": "실제로 뛴 약 5km가 기록됨", "actual": "3.2km로 기록됨", "frequency": "두 번 연속", "repro_steps": ["러닝 시작", "터널을 지나며 달리기", "러닝 종료 후 기록 확인"], "missing_fields": []}
```

## Example 2 — 기기만 있고 버전이 없는 제보 (추측 금지)
<report>
픽셀 7인데 러닝 카드 저장 누르면 앱이 꺼져요.
</report>
출력:
```json
{"device_model": "픽셀 7", "android_version": null, "app_version": null, "feature_area": "card_image", "symptom": "러닝 카드 저장 시 앱 종료", "expected": null, "actual": "앱이 꺼짐", "frequency": null, "repro_steps": ["러닝 카드 저장 버튼 누르기"], "missing_fields": ["app_version", "android_version"]}
```
- "픽셀 7"에서 안드로이드 버전을 유추하지 않았다.

## Example 3 — 거의 정보가 없는 제보
<report>
앱이 자꾸 이상해요. 고쳐주세요.
</report>
출력:
```json
{"device_model": null, "android_version": null, "app_version": null, "feature_area": null, "symptom": "앱이 이상하게 동작함(구체적 증상 없음)", "expected": null, "actual": null, "frequency": "자꾸", "repro_steps": [], "missing_fields": ["app_version", "android_version", "device_model", "repro_steps"]}
```
