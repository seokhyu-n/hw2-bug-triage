"""45 hard known-issue linking / extraction-trap cases (E-166..E-210) for dataset_v3, part B.

Run once to (re)write eval/dataset_v3_new_b.jsonl:
    venv\\Scripts\\python.exe -m eval.new_cases_v3_b
Labels follow prompts/classify.md, prompts/extract.md (null unless stated; device/version strings are
literal substrings of the report), prompts/link.md (link only when symptom, Android version and app
version all fit data/known_issues.json) and prompts/score_rubric.md.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dataset_v3_new_b.jsonl"


def ex(area, symptom, *, device=None, android=None, app=None, expected=None, actual=None, freq=None, steps=()):
    return {"device_model": device, "android_version": android, "app_version": app, "feature_area": area,
            "symptom": symptom, "expected": expected, "actual": actual, "frequency": freq,
            "repro_steps": list(steps)}


def case(cid, text, tags, category, labels, extraction, completeness, priority, link=None):
    return {"id": cid, "text": text, "hard": True, "tags": tags,
            "expected": {"category": category, "labels": labels, "extraction": extraction,
                         "completeness": completeness, "priority": priority, "linked_issue_id": link}}


M, FIX, VV, CR, MISS = "known_issue_match", "already_fixed_version", "version_variant", "crash", "missing"
NM = "known_issue_near_miss"

CASES = [
    # ===== true matches, described in users' own words =====
    # ISSUE-01: Android 7.x crash at run start (fixed in 1.1.0)
    case("E-166", "갤럭시 노트5 쓰는데요 (안드 7.1.2) 앱 1.0.1 깔고 뛰러 나가서 스타트 누르는 순간 '앱이 중지됨' 팝업 뜨면서 "
                  "홈화면으로 튕겨나감. 세 번 해봤는데 세 번 다 그래요",
         [M, FIX, VV, CR], "bug", ["bug"],
         ex("tracking", "러닝 스타트를 누르는 순간 앱이 중지되며 종료됨", device="갤럭시 노트5", android="7.1.2",
            app="1.0.1", actual="'앱이 중지됨' 팝업 후 홈화면으로 종료", freq="세 번 다", steps=["스타트 누름"]),
         2, "P2", "ISSUE-01"),
    case("E-167", "누가 7.0 폰(LG X스크린) 씁니다. 운동 시작만 누르면 꺼져요. 앱 버전은 모르겠고 플레이스토어에서 받은 지 좀 됐어요",
         [M, CR], "bug", ["bug"],
         ex("tracking", "운동 시작을 누르면 앱이 꺼짐", device="LG X스크린", android="7.0", actual="앱이 꺼짐",
            steps=["운동 시작 누름"]),
         1, "P1", "ISSUE-01"),
    # ISSUE-02: Android 14 crash at run start (fixed in 1.2.0)
    case("E-168", "S23 울트라 / 안드14 / v1.1.0\n달리기 탭에서 START 누르면 카운트다운도 안 뜨고 바로 앱이 닫혀버려요. 위치는 '항상 허용' 해놨어요",
         [M, FIX, VV, CR], "bug", ["bug"],
         ex("tracking", "러닝 START를 누르면 카운트다운 없이 앱이 바로 닫힘", device="S23 울트라", android="14",
            app="1.1.0", actual="앱이 바로 닫힘", steps=["달리기 탭 열기", "START 누름"]),
         2, "P1", "ISSUE-02"),
    case("E-169", "픽셀8 프로 쓰고 안드로이드 14.0 이에요. 앱은 1.0.1. 러닝 시작하면 화면이 한 번 깜빡하더니 앱이 통째로 꺼짐ㅠ",
         [M, FIX, VV, CR], "bug", ["bug"],
         ex("tracking", "러닝 시작 시 화면이 깜빡한 뒤 앱이 종료됨", device="픽셀8 프로", android="14.0", app="1.0.1",
            actual="앱이 꺼짐", steps=["러닝 시작"]),
         2, "P1", "ISSUE-02"),
    case("E-170", "폰을 안드로이드 14로 올리고 나서부터 러닝 기록 시작이 안 돼요. 시작 누르면 앱이 그냥 사라짐. 앱 업데이트는 몇 달째 안 했어요",
         [M, CR], "bug", ["bug"],
         ex("tracking", "OS 업데이트 후 러닝 시작을 누르면 앱이 종료됨", android="14", actual="앱이 사라짐",
            steps=["안드로이드 14로 업데이트", "러닝 시작 누름"]),
         1, "P1", "ISSUE-02"),
    # ISSUE-03: battery drain / heat (open)
    case("E-171", "한 시간 뛰고 오니까 폰이 손난로 됨ㅋㅋ 배터리도 반토막 나 있고요. 갤노트10 / 안드11 / 1.2.0",
         [M, VV], "bug", ["bug"],
         ex("tracking", "한 시간 러닝 후 폰이 뜨거워지고 배터리가 절반가량 소모됨", device="갤노트10", android="11",
            app="1.2.0", actual="폰 발열, 배터리 반토막", steps=["한 시간 러닝"]),
         2, "P2", "ISSUE-03"),
    case("E-172", "하프 연습하는데 15km쯤에서 폰이 꺼졌어요. 출발할 때 100%였는데 배터리가 다 나가서요. 다른 러닝앱 쓸 땐 이런 적 없음. 픽셀7 안드로이드 13",
         [M], "bug", ["bug"],
         ex("tracking", "러닝 중 배터리가 빠르게 소모되어 15km 지점에서 폰이 꺼짐", device="픽셀7", android="13",
            actual="배터리 방전으로 폰 꺼짐", steps=["배터리 100%로 하프 연습 러닝"]),
         1, "P2", "ISSUE-03"),
    # ISSUE-04: total distance too short (open)
    case("E-173", "트레드밀 아니고 운동장 트랙이에요. 가민 시계로는 5.0인데 앱은 4.3 찍혀요. 안드 12, 앱 v1.1.1, 매번 그래요",
         [M, VV], "bug", ["bug"],
         ex("tracking", "트랙 러닝 거리가 시계보다 짧게 기록됨", android="12", app="1.1.1", expected="5.0km",
            actual="4.3km", freq="매번", steps=["운동장 트랙에서 러닝"]),
         2, "P2", "ISSUE-04"),
    case("E-174", "지하차도 하나 지나는 코스인데 그 구간이 통째로 빠져서 기록돼요. 매번 400m 정도 손해 봄ㅡㅡ",
         [M, MISS], "bug", ["bug"],
         ex("tracking", "지하차도 구간 거리가 기록에서 빠짐", actual="약 400m 누락", freq="매번",
            steps=["지하차도를 지나는 코스로 러닝"]),
         1, "P2", "ISSUE-04"),
    case("E-175", "스프린트 훈련(100m 전력질주 10개) 하면 거리가 절반밖에 안 찍혀요. 천천히 조깅할 땐 멀쩡하고요. 갤럭시 A54 / One UI 6.1 / 앱 1.2.0",
         [M, VV], "bug", ["bug"],
         ex("tracking", "빠르게 달리면 거리가 절반 정도만 기록됨", device="갤럭시 A54", app="1.2.0", expected="1km",
            actual="절반만 기록", steps=["100m 전력질주 10회"]),
         1, "P2", "ISSUE-04"),
    # ISSUE-05: calories ignore body weight (open)
    case("E-176", "와이프랑 같이 5km 뛰었는데 저(85kg)랑 와이프(48kg) 소모 kcal이 소수점까지 똑같아요. 이게 말이 되나요ㅋㅋ 1.1.0 버전, 안드로이드 10",
         [M, VV], "bug", ["bug"],
         ex("tracking", "체중이 크게 다른 두 사람의 소모 칼로리가 똑같이 표시됨", android="10", app="1.1.0",
            actual="두 사람 칼로리가 소수점까지 같음", steps=["두 사람이 같이 5km 러닝", "소모 칼로리 비교"]),
         2, "P3", "ISSUE-05"),
    case("E-177", "몸무게 바꾸는 메뉴는 어디 있나요? 저 52킬로인데 칼로리가 너무 높게 나와서 고치려고 하는데 프로필에도 설정에도 없네요",
         [M, MISS, "mixed_labels", "boundary_bug_question"], "bug", ["bug", "question"],
         ex("tracking", "칼로리가 실제 체중보다 높게 계산되고 체중을 바꿀 곳이 없음", actual="칼로리가 너무 높게 나옴"),
         1, "P3", "ISSUE-05"),
    # ISSUE-06: course route drawn like transit / straight line (fixed in 1.1.1)
    case("E-178", "코스 추천 받은 거 눌러보면 경로가 지하철 노선도처럼 꺾여서 역 앞으로 돌아가게 나와요ㅋㅋ 앱 1.0, 안드로이드 9, 갤럭시 A7",
         [M, FIX], "bug", ["bug"],
         ex("map", "추천 코스 경로가 지하철 노선처럼 역을 거쳐 돌아가게 표시됨", device="갤럭시 A7", android="9",
            app="1.0", actual="역 앞으로 돌아가는 경로", steps=["추천 코스 누름"]),
         2, "P3", "ISSUE-06"),
    case("E-179", "지도에서 코스 고르면 출발점이랑 도착점을 자로 그은 것처럼 이어놔요. 골목이고 건물이고 다 관통함. 1.1.0 / 안드13",
         [M, FIX, VV], "bug", ["bug"],
         ex("map", "코스 경로가 출발점과 도착점을 잇는 직선으로 표시됨", android="13", app="1.1.0",
            actual="건물을 관통하는 직선 경로", steps=["지도에서 코스 선택"]),
         2, "P3", "ISSUE-06"),
    # ISSUE-07: record list slow with many records (fixed in 1.1.0, Android <= 10)
    case("E-180", "기록 탭 누르면 화면이 하얗게 몇 초 굳었다가 나와요. 4년치 쌓여서 그런가.. 갤럭시 S7 엣지, 안드로이드 8.0, 1.0.1",
         [M, FIX], "bug", ["bug"],
         ex("record", "기록이 많아 기록 탭 진입 시 몇 초간 화면이 멈춤", device="갤럭시 S7 엣지", android="8.0",
            app="1.0.1", actual="몇 초간 하얀 화면", steps=["기록 탭 누름"]),
         2, "P3", "ISSUE-07"),
    case("E-181", "기록 리스트 내릴 때 칸마다 작은 지도 그림 뜨는 동안 렉이 엄청 걸려요. 안드 10 / 앱 1.0",
         [M, FIX, VV], "bug", ["bug"],
         ex("record", "기록 목록 스크롤 시 경로 썸네일 로딩 때문에 버벅임", android="10", app="1.0",
            actual="스크롤 렉", steps=["기록 리스트 스크롤"]),
         2, "P3", "ISSUE-07"),
    # ISSUE-08: large photo -> card creation OOM crash (fixed in 1.0.1, Android 7-9)
    case("E-182", "러닝 끝나고 인증 카드 만들려고 DSLR로 찍은 사진(20MB짜리) 넣으면 앱이 죽어버려요. 안드로이드 9 / 1.0",
         [M, FIX, CR], "bug", ["bug"],
         ex("card_image", "대용량 사진으로 러닝 카드를 만들면 앱이 종료됨", android="9", app="1.0",
            actual="앱 종료", steps=["러닝 종료", "카드 만들기에서 20MB 사진 선택"]),
         2, "P2", "ISSUE-08"),
    case("E-183", "카드 배경으로 사진 고르는 순간 튕겨요. 카톡으로 받은 작은 사진은 괜찮고 폰카 원본만 그래요. 갤럭시 S7",
         [M, CR, MISS], "bug", ["bug"],
         ex("card_image", "카드 배경으로 원본 고화질 사진을 고르면 앱이 튕김", device="갤럭시 S7", actual="앱 튕김",
            steps=["카드 배경으로 폰카 원본 사진 선택"]),
         1, "P2", "ISSUE-08"),  # human review 11-24: old device
    # ISSUE-09: card not saved to gallery on Android <= 9 (open)
    case("E-184", "카드 '저장' 누르면 저장됐다는 토스트는 뜨는데 앨범 앱에서 아무리 찾아도 없음. 공유하기로 카톡 보내는 건 돼요. 안드로이드 8.1.0, 앱 1.2.0",
         [M, VV], "bug", ["bug"],
         ex("card_image", "러닝 카드 저장 완료 메시지가 뜨지만 앨범에 이미지가 없음", android="8.1.0", app="1.2.0",
            expected="앨범에 카드 저장", actual="토스트만 뜨고 앨범에 없음", steps=["카드 '저장' 누름", "앨범 앱 확인"]),
         2, "P3", "ISSUE-09"),
    case("E-185", "갤럭시 S9+ 안드 9 쓰는데 러닝카드 다운로드가 안 돼요. 사진첩 폴더에도 내 파일에도 없어요",
         [M], "bug", ["bug"],
         ex("card_image", "러닝카드를 다운로드해도 사진첩·내 파일 어디에도 없음", device="갤럭시 S9+", android="9",
            actual="저장된 파일 없음", steps=["러닝카드 다운로드", "사진첩과 내 파일 확인"]),
         1, "P3", "ISSUE-09"),
    # ISSUE-10: no start/stop voice without Korean TTS (fixed in 1.1.1)
    case("E-186", "뛰기 시작할 때 다른 사람들은 '러닝을 시작합니다' 멘트 나온다는데 저는 한 번도 안 나와요. 화웨이 폰이라 구글 음성 엔진이 없는데 그거 때문인가요? 앱 1.0.1 / 안드로이드 10",
         [M, FIX, "mixed_labels", "boundary_bug_question"], "bug", ["bug", "question"],
         ex("voice", "러닝 시작 음성 멘트가 한 번도 나오지 않음", android="10", app="1.0.1",
            expected="'러닝을 시작합니다' 음성", actual="음성 없음", steps=["러닝 시작"]),
         2, "P3", "ISSUE-10"),
    case("E-187", "음성 코칭 소리가 아예 안 남. 미디어 볼륨 만땅이고 유튜브는 소리 잘 나옴. v1.1.0",
         [M, FIX, VV, MISS], "bug", ["bug"],
         ex("voice", "음성 안내 소리가 전혀 나지 않음", app="1.1.0", actual="무음"),
         1, "P3", "ISSUE-10"),
    # ISSUE-11: password with surrounding space -> cannot log in (fixed in 1.0.1)
    case("E-188", "회원가입할 때 비번을 메모장에서 복붙했는데 끝에 띄어쓰기가 딸려갔나 봐요. 그 뒤로 로그인하면 계속 비밀번호 불일치래요. 앱 1.0 / 안드로이드 12",
         [M, FIX], "bug", ["bug"],
         ex("login", "복사한 비밀번호 끝 공백 때문에 가입 후 로그인이 안 됨", android="12", app="1.0",
            actual="비밀번호 불일치", steps=["메모장에서 비밀번호를 복사해 회원가입", "같은 비밀번호로 로그인"]),
         2, "P2", "ISSUE-11"),
    case("E-189", "가입 완료까지 떴는데 바로 로그인하니까 비번 틀렸대요. 비번 맨 앞에 스페이스 하나 넣었었거든요(보안상ㅎ). 갤럭시 퀀텀2",
         [M, MISS], "bug", ["bug"],
         ex("login", "앞에 공백이 있는 비밀번호로 가입 후 로그인이 안 됨", device="갤럭시 퀀텀2", actual="비밀번호가 틀렸다고 표시",
            steps=["앞에 공백이 있는 비밀번호로 가입", "바로 로그인"]),
         1, "P1", "ISSUE-11"),
    # ISSUE-12: AI coach first reply cold start (fixed in 1.2.0)
    case("E-190", "AI 코치 화면 열고 첫 질문 보내면 뱅글뱅글만 돌다가 '응답 시간이 초과되었습니다'. 1분쯤 있다 다시 보내면 정상이에요. 앱 1.1.1, 안드로이드 12",
         [M, FIX], "bug", ["bug"],
         ex("ai_chat", "AI 코치 첫 질문에 응답 시간 초과 오류가 뜨고 재전송하면 정상", android="12", app="1.1.1",
            actual="'응답 시간이 초과되었습니다'", steps=["AI 코치 화면 열기", "첫 질문 보내기", "1분 뒤 다시 보내기"]),
         2, "P3", "ISSUE-12"),
    case("E-191", "아침에 처음 코치한테 말 걸면 무조건 에러 나요. 매일 아침 그래요. 오후엔 잘 됨ㅋㅋ 1.0.1 버전",
         [M, FIX, VV], "bug", ["bug"],
         ex("ai_chat", "하루 첫 AI 코치 메시지에 오류가 남", app="1.0.1", actual="에러", freq="매일 아침",
            steps=["아침에 AI 코치에게 첫 메시지 보내기"]),
         1, "P3", "ISSUE-12"),

    # ===== near misses: same-looking symptom, but no known issue fits =====
    # already fixed: app version >= fixed_in
    case("E-192", "1.1.1 버전인데요, 갤러리에서 4천만 화소 사진 고르면 카드 만들기 화면에서 앱이 꺼집니다. 안드로이드 9, 갤럭시 S10",
         [NM, FIX, CR, VV], "bug", ["bug"],
         ex("card_image", "고화질 사진을 고르면 카드 만들기 화면에서 앱이 꺼짐", device="갤럭시 S10", android="9",
            app="1.1.1", actual="앱 종료", steps=["카드 만들기 화면에서 4천만 화소 사진 선택"]),
         2, "P1"),
    case("E-193", "기록이 1000개 넘으니까 기록 탭 열 때 2~3초 멈칫해요. 못 쓸 정도는 아닌데 신경 쓰여서요. 안드로이드 9 / 앱 1.1.0",
         [NM, FIX], "bug", ["bug"],
         ex("record", "기록이 많아 기록 탭을 열 때 2~3초 멈춤", android="9", app="1.1.0", actual="2~3초 멈춤",
            steps=["기록 탭 열기"]),
         2, "P3"),
    case("E-194", "1.1.1로 업데이트했는데도 러닝 시작할 때 음성이 여전히 안 나와요. TTS 한국어 데이터도 받아놨어요. 안드 13",
         [NM, FIX, VV], "bug", ["bug"],
         ex("voice", "업데이트와 한국어 TTS 설치 후에도 러닝 시작 음성이 나오지 않음", android="13", app="1.1.1",
            actual="음성 없음", steps=["1.1.1로 업데이트", "TTS 한국어 데이터 설치", "러닝 시작"]),
         2, "P3"),
    case("E-195", "앱 1.2.0, 안드 14. AI 코치에게 첫 메시지 보내면 30초 넘게 '입력 중...'만 보이다가 전송 실패로 바뀝니다",
         [NM, FIX], "bug", ["bug"],
         ex("ai_chat", "AI 코치 첫 메시지가 30초 넘게 대기하다 전송 실패", android="14", app="1.2.0",
            actual="'입력 중...' 후 전송 실패", steps=["AI 코치에게 첫 메시지 보내기"]),
         2, "P3"),
    case("E-196", "1.1.1 업데이트 받았는데도 코스 경로가 여전히 직선으로 쭉 그어져요. 길 따라 안 그려짐. 안드로이드 10",
         [NM, FIX], "bug", ["bug"],
         ex("map", "업데이트 후에도 코스 경로가 직선으로 표시됨", android="10", app="1.1.1", expected="길을 따라 그려진 경로",
            actual="직선 경로", steps=["1.1.1로 업데이트", "코스 경로 보기"]),
         2, "P2"),
    # Android version outside the affected list
    case("E-197", "LG G7 씽큐 / 안드로이드 8.0 / 앱 1.0.1\n러닝 시작 누르면 바로 '앱이 중지되었습니다' 떠요. 구형폰 문제라는 글 봤는데 제 건 7 버전 아니에요",
         [NM, CR], "bug", ["bug"],
         ex("tracking", "러닝 시작을 누르면 앱이 중지됨", device="LG G7 씽큐", android="8.0", app="1.0.1",
            actual="'앱이 중지되었습니다'", steps=["러닝 시작 누름"]),
         2, "P1"),
    case("E-198", "다른 폰(안드14)은 업데이트하면 된다고 해서 했다던데 제 폰은 안드로이드 13이에요. 근데 저도 앱 1.1.1에서 러닝 시작 누르면 튕깁니다. 갤럭시 A53",
         [NM, CR, VV], "bug", ["bug"],
         ex("tracking", "러닝 시작을 누르면 앱이 튕김", device="갤럭시 A53", android="13", app="1.1.1", actual="앱 튕김",
            steps=["러닝 시작 누름"]),
         2, "P1"),
    case("E-199", "안드11 / 1.0 쓰는 중. 러닝 카드에 폰으로 찍은 고화질 사진 넣으면 카드 만드는 도중에 튕겨요",
         [NM, CR, VV], "bug", ["bug"],
         ex("card_image", "고화질 사진으로 러닝 카드를 만들 때 앱이 튕김", android="11", app="1.0", actual="앱 튕김",
            steps=["러닝 카드에 고화질 사진 넣기", "카드 만들기"]),
         2, "P1"),
    case("E-200", "기록 목록 열면 한참 걸려요. 기록 150개 정도밖에 없는데. 안드로이드 12, 앱 1.0",
         [NM], "bug", ["bug"],
         ex("record", "기록 목록을 열 때 오래 걸림", android="12", app="1.0", actual="로딩이 한참 걸림",
            steps=["기록 목록 열기"]),
         2, "P3"),
    # opposite symptom
    case("E-201", "신호 대기로 가만히 서 있는데도 거리가 계속 올라가요. 횡단보도에서 3분 기다리는 동안 0.3km 늘어남. 안드로이드 13 / 1.2.0",
         [NM], "bug", ["bug"],
         ex("tracking", "멈춰 있는 동안에도 거리가 늘어남", android="13", app="1.2.0", expected="정지 중 거리 변화 없음",
            actual="3분 동안 0.3km 증가", steps=["러닝 중 횡단보도에서 3분 대기"]),
         2, "P2"),
    case("E-202", "러닝 시작하면 '러닝을 시작합니다'가 두 번 겹쳐서 나와요. 메아리처럼ㅋㅋ 끝낼 때도 두 번. 1.2.0, 안드로이드 12",
         [NM], "bug", ["bug"],
         ex("voice", "러닝 시작·종료 음성 안내가 두 번 겹쳐 나옴", android="12", app="1.2.0", expected="한 번 안내",
            actual="두 번 겹쳐 나옴", steps=["러닝 시작", "러닝 종료"]),
         2, "P3"),
    # same feature, different symptom
    case("E-203", "AI 코치랑 얘기하다가 앱 껐다 켜면 이전 대화가 싹 사라져 있어요. 처음부터 다시 설명해야 함. 1.1.1 / 안드 12",
         [NM, VV], "bug", ["bug"],
         ex("ai_chat", "앱을 다시 켜면 AI 코치 이전 대화가 사라짐", android="12", app="1.1.1", actual="대화 내역 없음",
            steps=["AI 코치와 대화", "앱 종료 후 다시 실행"]),
         2, "P3"),
    case("E-204", "로그인은 되는데 앱 껐다 켤 때마다 로그아웃돼 있어서 매번 다시 쳐야 해요. 1.0 버전, 안드로이드 9",
         [NM, VV], "bug", ["bug"],
         ex("login", "앱을 다시 켤 때마다 로그아웃되어 있음", android="9", app="1.0", expected="로그인 유지",
            actual="매번 로그아웃", steps=["로그인", "앱 종료 후 다시 실행"]),
         2, "P2"),  # human review 11-24: login is core
    case("E-205", "지도에서 제 위치 파란 점이 실제보다 한 블록씩 늦게 따라와요. 경로 선은 멀쩡함. 앱 1.0.1 / 안드로이드 11",
         [NM], "bug", ["bug"],
         ex("map", "지도의 현재 위치 표시가 실제보다 늦게 따라옴", android="11", app="1.0.1",
            actual="파란 점이 한 블록 뒤처짐", steps=["러닝 중 지도 확인"]),
         2, "P3"),
    case("E-206", "안드로이드 7.0 / 앱 1.0.1\n러닝 시작은 잘 되는데 끝내기 누르는 순간 꺼져서 방금 뛴 기록이 날아가요",
         [NM, CR], "bug", ["bug"],
         ex("tracking", "러닝 종료를 누르면 앱이 꺼지고 기록이 사라짐", android="7.0", app="1.0.1",
            actual="앱 종료, 기록 유실", steps=["러닝 시작", "끝내기 누름"]),
         2, "P1"),

    # ===== extraction traps without a link =====
    case("E-207", "S23 울트라(One UI 6.1) 쓰고 지금 깔린 게 1.1.1 버전이에요. 안드14에서 러닝 시작하면 꺼지는 문제 있다던데 1.2.0으로 올리면 해결되는 거 맞죠? 저는 아직 한 번도 안 꺼졌어요",
         [VV, "boundary_bug_question"], "question", ["question"],
         ex("tracking", "1.2.0 업데이트로 안드로이드 14 러닝 시작 크래시 문제가 해결되는지 문의", device="S23 울트라",
            app="1.1.1"),
         None, "P4"),
    case("E-208", "픽셀8 최신 버전 쓰는데 요즘 업데이트 이후로 러닝 중에 일시정지 버튼이 안 눌려요. 여러 번 눌러야 겨우 멈춤",
         [VV, MISS], "bug", ["bug"],
         ex("tracking", "러닝 중 일시정지 버튼이 잘 눌리지 않음", device="픽셀8", expected="한 번에 일시정지",
            actual="여러 번 눌러야 멈춤", steps=["러닝 중 일시정지 버튼 누름"]),
         1, "P2"),
    case("E-209", "v1.2.0 잘 쓰고 있어요(안드 13). 일주일 러닝 기록을 주간 리포트로 메일 보내주는 기능 있으면 좋겠어요",
         [VV], "feature_request", ["feature_request"],
         ex("record", "주간 러닝 기록 리포트 메일 발송 기능 요청", android="13", app="1.2.0"),
         None, "P4"),
    case("E-210", "갤노트10+ / 안드로이드 12 / 앱 1.1.1. 러닝 카드 만들면 날짜가 'Nov 3'처럼 영어로 찍혀요. 폰 언어는 한국어예요",
         [VV], "bug", ["bug"],
         ex("card_image", "러닝 카드 날짜가 한국어 설정인데 영어로 표시됨", device="갤노트10+", android="12", app="1.1.1",
            expected="한국어 날짜", actual="'Nov 3' 영어 날짜", steps=["러닝 카드 만들기"]),
         2, "P4"),
]

REVIEW = [
    ("E-167", "ISSUE-01 crash on Android 7.0 but app version unstated: P1 (fixed version not confirmed by text, as E-064) vs P2 (old-OS issue already fixed)."),
    ("E-170", "Linked to ISSUE-02 with no app version; the user only says they have not updated for months. Linking is allowed (app_version null) but a strict linker may refuse."),
    ("E-172", "Battery drained until the phone switched off mid-run: P2 (battery, as E-015) vs P1 (run possibly lost). No crash tag since the app did not crash."),
    ("E-177", "Phrased as 'where is the weight menu?' but claims calories are too high: labelled bug+question linked to ISSUE-05; could be read as question/feature_request (cf. E-117 near miss)."),
    ("E-183", "Card crash on a Galaxy S7 (old device) with no versions: P1 because neither the fixed version nor the old OS is confirmed by the text; P2 is arguable via 'specific old device'."),
    ("E-188", "Login impossible matched to fixed ISSUE-11 on app 1.0: P2 following E-057 precedent, though Android 12 is not an old OS so a strict P1 rule could apply. E-189 (no versions) is P1."),
    ("E-196", "Straight-line course on 1.1.1 (after ISSUE-06 fix): P2 following E-071 (course route), P3 arguable as map display."),
    ("E-199", "High-res photo card crash on Android 11 / app 1.0: not linked because ISSUE-08 lists Android 7-9 only, although the app version is affected and the cause is plausibly the same."),
    ("E-204", "Session not kept (logout on every restart): login still works, so P3; P2 arguable because login is a core feature."),
    ("E-207", "'안드14' names the known issue, not the user's OS, and One UI 6.1 is not an Android version, so android_version is null; app_version is the installed 1.1.1, not the 1.2.0 asked about."),
]


def main() -> None:
    ids = [f"E-{n:03d}" for n in range(166, 211)]
    assert sorted(c["id"] for c in CASES) == ids, "ids must be E-166..E-210"
    OUT.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in sorted(CASES, key=lambda c: c["id"])),
                   encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(CASES)} cases)")


if __name__ == "__main__":
    main()
