# Examples
경계 사례를 보여주는 예시다. 판단 근거를 그대로 적용하되, 예시 문장을 실제 입력에 옮겨 쓰지 않는다.

## Example 1 — 버그 (기존 기능의 오동작)
<report>
러닝 중에 GPS 기록이 자꾸 끊겨요. 지도 보면 중간에 경로가 비어 있어요.
</report>
출력:
```json
{"category": "bug", "labels": ["bug"], "reason": "이미 있는 GPS 경로 기록 기능이 '끊긴다'고 고장을 말하므로 버그다."}
```

## Example 2 — 문의 (질문형, 고장 주장 없음)
<report>
기록 내보내기 되나요? 다른 앱으로 옮기고 싶어서요.
</report>
출력:
```json
{"category": "question", "labels": ["question"], "reason": "'내보내기 되나요?'는 기능 존재 여부를 묻는 질문이고 고장을 말하지 않는다."}
```

## Example 3 — 개선 요청 (없는 기능)
<report>
칼로리가 정확하게 나오게 체중 설정 넣어주세요.
</report>
출력:
```json
{"category": "feature_request", "labels": ["feature_request"], "reason": "체중 설정이라는 새 기능을 추가해 달라는 요청이다."}
```

## Example 4 — 복합 (버그 + 개선 요청)
<report>
카드 저장이 안 되는데 공유 기능도 있으면 좋겠어요.
</report>
출력:
```json
{"category": "bug", "labels": ["bug", "feature_request"], "reason": "'카드 저장이 안 된다'는 기존 기능의 고장(버그)이고, '공유 기능'은 새 기능 요청이다. 버그가 섞여 있으므로 주 라벨은 bug."}
```

## Example 5 — 질문형이지만 버그
<report>
왜 음성 안내가 안 나오죠? 설정은 켜 놨어요.
</report>
출력:
```json
{"category": "bug", "labels": ["bug"], "reason": "질문 형태지만 켜 둔 음성 안내가 나오지 않는다는 고장을 말하므로 버그다."}
```

## Example 6 — 버그 + 별도 질문
<report>
러닝 끝나면 폰이 뜨끈해요. 30분 뛰면 이 정도 열나는 게 정상인가요? 다른 앱 켤 땐 안 그래요.
</report>
출력:
```json
{"category": "bug", "labels": ["bug", "question"], "reason": "다른 앱과 달리 발열이 심하다는 이상 증상(버그)에 더해 '이 정도가 정상인가요?'라는 별도 질문이 있다."}
```

## Example 7 — 요청형 문장이지만 고장
<report>
기록 공유 버튼 좀 되게 해 주세요. 눌러도 아무 창이 안 떠요.
</report>
출력:
```json
{"category": "bug", "labels": ["bug"], "reason": "이미 있는 공유 버튼이 반응하지 않는 고장이다. '되게 해 주세요'는 고쳐 달라는 말이지 새 기능 요청이 아니다."}
```
