# -*- coding: utf-8 -*-
"""
서·논술형 자동 채점 웹앱 (Streamlit)
- 1~3세트 x (서논술형1: 빈칸형 / 서논술형2: 설명방법 선택형 / 서논술형3: 시청각 연출형)
- 규칙(키워드+의미) 기반 채점: 용어가 없어도 '의미'가 담기면 인정
- 오개념(반대 방향) 자동 탐지, 설명 방법 특성 일치 여부 검증, 결론 방향 확인
"""

import re
import streamlit as st

# ------------------------------------------------------------------
# 0. 공통 유틸
# ------------------------------------------------------------------

def norm(s: str) -> str:
    """공백 제거 + 소문자화(한글은 영향 없음)로 느슨한 비교."""
    return re.sub(r"\s+", "", s or "").lower()


def contains(text: str, keyword: str) -> bool:
    return norm(keyword) in norm(text)


def group_matched(text: str, group) -> bool:
    """group(=동의어/유사표현 리스트) 중 하나라도 포함되면 True (OR 매칭)."""
    return any(contains(text, kw) for kw in group)


def any_keyword(text: str, keywords) -> bool:
    return any(contains(text, kw) for kw in keywords)


METHOD_CANON = {
    "정의": "정의", "예시": "예시", "예": "예시",
    "인과": "인과",
    "분석": "분석",
    "비교": "비교와 대조", "대조": "비교와 대조", "비교와대조": "비교와 대조", "비교와 대조": "비교와 대조",
    "분류": "분류와 구분", "구분": "분류와 구분", "분류와구분": "분류와 구분", "분류와 구분": "분류와 구분",
}

METHOD_PATTERNS = {
    "정의": ["란", "을 말한다", "라고 한다", "뜻한다", "이라고 부른다", "개념이다"],
    "예시": ["예를 들어", "예로", "예컨대", "그 예로", "와 같은"],
    "인과": ["때문에", "따라서", "그래서", "원인", "결과", "때문이다", "로 인해"],
    "분석": ["로 이루어져", "구성되어", "부분으로", "요소로"],
    "비교와 대조": ["반면", "달리", "차이", "공통점", "차이점", "비교하면", "와 달리", "과 달리", "지만"],
    "분류와 구분": ["로 나뉘", "로 나눌", "구분되", "묶이", "나뉜다", "나뉜"],
}


def extract_method(text: str):
    """문장 끝 괄호 안 설명 방법 명칭을 추출/정규화."""
    m = re.search(r"[\(（]([^\)）]+)[\)）]\s*$", (text or "").strip())
    if not m:
        return None, (text or "")
    raw = m.group(1).strip()
    canon = METHOD_CANON.get(raw.replace(" ", ""), raw)
    body = text[: m.start()].strip()
    return canon, body


# ------------------------------------------------------------------
# 1. 채점 엔진
# ------------------------------------------------------------------

def score_blank(text, cfg):
    """빈칸형(서논술형1) 단일 항목 채점."""
    text = text or ""
    groups = cfg.get("groups", [])
    flags = [group_matched(text, g) for g in groups]
    matched = sum(flags)
    total = len(groups)
    min_match = cfg.get("min_match", total)
    opposite_hit = any_keyword(text, cfg.get("opposite", []))
    exact_term = cfg.get("exact_term")
    exact_ok = contains(text, exact_term) if exact_term else True

    passed = matched >= min_match and exact_ok and not opposite_hit
    feedback = []
    if not text.strip():
        feedback.append("답안이 입력되지 않았습니다.")
    if exact_term and not exact_ok:
        feedback.append(f"❌ 필수 용어 '{exact_term}'가 정확히 포함되어야 합니다(용어 자체는 대체 불가).")
    if matched < min_match:
        feedback.append(f"❌ 필요한 의미 요소 {min_match}개 중 {matched}개만 확인됨(용어 없이 의미만 통해도 인정).")
    if opposite_hit:
        feedback.append("⚠️ 반대 방향(오개념) 표현이 감지되었습니다 — 결론/방향을 다시 확인하세요.")
    if passed:
        feedback.append("✅ 통과")
    return passed, feedback, matched, total


def score_slot(text, cfg, other_method=None):
    """서논술형2 - 문장 슬롯(설명 방법 + 내용) 채점."""
    method, body = extract_method(text)
    feedback = []
    if method is None:
        feedback.append("❌ 문장 끝 괄호에 사용한 설명 방법 명칭이 없습니다. 예: (예시)")
        method_ok = False
    else:
        pattern_ok = any_keyword(body, METHOD_PATTERNS.get(method, [])) if method in METHOD_PATTERNS else True
        content_groups = cfg.get("content_groups", [])
        content_flags = [group_matched(body, g) for g in content_groups]
        content_matched = sum(content_flags)
        content_min = cfg.get("content_min", len(content_groups))
        content_ok = content_matched >= content_min

        cross_hit = any_keyword(body, cfg.get("forbidden", []))

        method_declared_known = method in METHOD_PATTERNS
        if not method_declared_known:
            feedback.append(f"⚠️ '{method}'는 1쪽에 제시된 6가지 설명 방법 목록에 없는 명칭입니다. (인정 여부 사전 확정 필요)")
        elif not pattern_ok:
            feedback.append(f"❌ 선택한 설명 방법 '{method}'의 특성(예: {', '.join(METHOD_PATTERNS[method][:3])} 등)이 문장에 드러나지 않습니다.")
        else:
            feedback.append(f"✅ 설명 방법 '{method}'의 특성이 문장에 드러남")

        if not content_ok:
            feedback.append(f"❌ 이 문장에 필요한 핵심 내용 요소 {content_min}개 중 {content_matched}개만 확인됨.")
        else:
            feedback.append("✅ 필요한 내용 요소 충족")

        if cross_hit:
            feedback.append("⚠️ 오개념 의심: 반대/다른 대상에 해당하는 표현이 섞여 있습니다(개념 혼동 가능).")

        if other_method and method == other_method:
            feedback.append(f"❌ (1)과 (2)에 같은 설명 방법('{method}')을 중복 사용했습니다. 서로 다른 방법이어야 합니다.")

        method_ok = method_declared_known and pattern_ok and content_ok and not cross_hit and not (other_method and method == other_method)

    return method_ok, feedback, method


def score_av(text, cfg):
    """서논술형3 - 시각/청각 요소+효과 채점."""
    text = text or ""
    groups = cfg.get("groups", [])
    flags = [group_matched(text, g) for g in groups]
    matched = sum(flags)
    min_match = cfg.get("min_match", len(groups))
    opposite_hit = any_keyword(text, cfg.get("opposite", []))
    passed = matched >= min_match and not opposite_hit
    feedback = []
    if not text.strip():
        feedback.append("답안이 입력되지 않았습니다.")
    if matched < min_match:
        feedback.append(f"❌ 필요한 의미 요소 {min_match}개 중 {matched}개만 확인됨(구체적 소재는 자유, 의미만 통하면 인정).")
    if opposite_hit:
        feedback.append("❌ 대비 실패: 앞 장면(반대 상황)의 이미지/소리를 재사용했거나 방향이 반대입니다.")
    if passed:
        feedback.append("✅ 통과 (지문 근거 반영 확인)")
    return passed, feedback, matched, len(groups)


# ------------------------------------------------------------------
# 2. 문항별 채점 기준 설정 (앞서 정리한 표 반영)
# ------------------------------------------------------------------

CONFIG = {
    ("1", "1"): {
        "type": "blank",
        "context": "사회적 촉진/억제 — 과제 특성에 따른 학습 전략",
        "blanks": [
            {"key": "㉠", "label": "㉠ 과제의 특성(쉬운 과제)",
             "groups": [["쉬운", "노력이 적게", "간단한", "가벼운", "취미"]],
             "opposite": ["어려운", "도전이 필요"]},
            {"key": "㉡", "label": "㉡ 효율적 환경 및 방법(어려운 과제)",
             "groups": [["연습", "익숙"], ["혼자", "단독"], ["차분", "집중"]],
             "min_match": 2,
             "opposite": ["커피숍", "도서관", "모임", "함께"]},
            {"key": "㉢", "label": "㉢ 관련 심리 현상", "exact_term": "사회적 억제",
             "groups": [["사회적 억제"]], "opposite": ["사회적 촉진"]},
        ],
        "model": {"㉠": "비교적 쉬운 취미 생활이나 큰 노력을 들일 필요가 없는 과제",
                  "㉡": "충분히 연습하며 익숙해질 때까지 차분하게 혼자 집중하는 시간을 가짐",
                  "㉢": "사회적 억제"},
    },
    ("1", "2"): {
        "type": "dual_method",
        "context": "쉬운 과제 vs 어려운 과제의 학습 전략 설명문",
        "slot1": {"label": "(1) 쉬운 과제 관련 문장",
                  "content_groups": [["도서관", "커피숍", "모임", "함께", "다른 사람들과"]],
                  "content_min": 1,
                  "forbidden": ["혼자", "차분", "연습하며 익숙"]},
        "slot2": {"label": "(2) 어려운 과제 관련 문장",
                  "content_groups": [["혼자", "단독"], ["연습", "익숙"], ["차분", "집중"]],
                  "content_min": 2,
                  "forbidden": ["도서관", "커피숍", "모임"]},
        "model": {
            "기본 조합(예시+비교와 대조)": [
                "예를 들어, 비교적 쉬운 과제를 할 때는 도서관이나 커피숍에서 하거나 공부 모임을 만들어 다른 사람들과 함께 하는 것이 효율적이다.(예시)",
                "반면 지나치게 어렵거나 도전이 필요한 과제는 충분히 연습하여 익숙해질 때까지 혼자 차분하게 집중하는 시간을 갖는 것이 효율적이라는 차이가 있다.(비교와 대조)"],
            "대안 조합(정의+인과)": [
                "사회적 촉진이란 타인의 존재가 수행을 돕는 현상을 말한다.(정의)",
                "어려운 과제는 타인의 존재가 오히려 부담이 되기 때문에 혼자 연습하는 것이 효율적이다.(인과)"],
        },
    },
    ("1", "3"): {
        "type": "av",
        "context": "장면2(어려운 과제) 연출",
        "A": {"label": "시각 요소(Ⓐ)+효과",
              "groups": [["혼자", "1인", "단독"], ["조용", "차분", "집중"]],
              "min_match": 2, "opposite": ["함께", "여러 사람", "밝은", "미소"]},
        "B": {"label": "청각 요소(Ⓑ)+효과",
              "groups": [["정적", "조용", "무음", "소음", "고요"]],
              "min_match": 1, "opposite": ["경쾌", "배경음악", "리듬감"]},
        "model": {"A": "조용한 1인 열람실에서 학생이 문제집에 몰두하는 모습을 클로즈업 — 타인의 시선이 없는 몰입 상태를 강조해 어려운 과제일수록 혼자 집중하는 환경이 필요함을 전달.",
                  "B": "배경음악 없이 시계 초침 소리만 들리게 함 — 외부 자극을 최소화해 고요한 환경의 필요성을 강조."},
    },

    ("2", "1"): {
        "type": "blank",
        "context": "정전기의 특징",
        "blanks": [
            {"key": "㉠", "label": "㉠ 물의 상태에 비유",
             "groups": [["고여 있는", "고인"]], "opposite": ["흐르는 물"]},
            {"key": "㉡", "label": "㉡ 전하의 상태",
             "groups": [["이동하지 않", "머물러", "정지 상태", "안 움직"]],
             "opposite": ["전압이 높", "전압만"]},
            {"key": "㉢", "label": "㉢ 위험성",
             "groups": [["위험하지 않", "안전", "피해가 없"]], "opposite": ["위험하다", "위험함", "감전"]},
        ],
        "model": {"㉠": "높은 곳에 고여 있는 물", "㉡": "전하가 이동하지 않고 머물러 있음", "㉢": "위험하지 않음(별 피해가 없음)"},
    },
    ("2", "2"): {
        "type": "dual_method",
        "context": "정전기의 특징 설명문",
        "slot1": {"label": "(1) 정전기의 정의/어원 관련 문장",
                  "content_groups": [["정지 상태", "변화하지 않"], ["정(靜)", "정", "한자"]],
                  "content_min": 1, "forbidden": ["고여 있는 물", "흐르는 물"]},
        "slot2": {"label": "(2) 비유/비교 관련 문장",
                  "content_groups": [["흐르는 물", "고여 있는 물", "고인 물"], ["전압", "위험하지 않", "안전"]],
                  "content_min": 2, "forbidden": ["위험하다"]},
        "model": {
            "기본 조합(정의+비교와 대조)": [
                "정전기란 전하가 정지 상태로 있어 그 분포가 시간적으로 변화하지 않는 전기로, 머물러 있다는 뜻에서 '정(靜)'이라는 한자를 사용한 이름이 붙었다.(정의)",
                "이는 실생활 전기가 '흐르는 물'이라면 정전기는 '고여 있는 물'과 같아서, 전압은 높지만 이동하지 않아 위험하지 않다는 차이가 있다.(비교와 대조)"],
            "대안 조합(인과+예시)": [
                "전하가 이동하지 않고 머물러 있기 때문에 정전기는 감전과 같은 위험이 없다.(인과)",
                "예를 들어 겨울철 문손잡이를 만질 때 찌릿함을 느끼는 것도 이런 정전기 현상의 예이다.(예시)"],
        },
    },
    ("2", "3"): {
        "type": "av",
        "context": "장면2(정전기=고인 물) 연출",
        "A": {"label": "시각 요소(Ⓐ)+효과",
              "groups": [["고여", "멈춰", "정지", "머물러"]], "min_match": 1,
              "opposite": ["흐르는", "폭포", "물레방아", "콸콸"]},
        "B": {"label": "청각 요소(Ⓑ)+효과",
              "groups": [["정적", "고요", "소리 없", "무음"]], "min_match": 1,
              "opposite": ["웅장", "큰 소리", "콸콸", "부딪히는"]},
        "model": {"A": "높은 곳의 저수지에 물이 고요하게 고여 있는 모습을 정지된 카메라로 보여줌 — 전하가 이동하지 않고 머물러 있는 상태를 시각화.",
                  "B": "짧은 마찰음 한 번 외에는 정적을 유지 — 전압은 높지만 위험하지 않다는 점을 앞 장면의 큰 소리와 대비해 전달."},
    },

    ("3", "1"): {
        "type": "blank",
        "context": "인공지능 그림의 예술적 가치",
        "blanks": [
            {"key": "㉠", "label": "㉠ 올림픽 경기에 비유(또는 제작 방식)",
             "groups": [["피겨 스케이팅", "로봇", "데이터", "알고리즘", "학습"]], "opposite": []},
            {"key": "㉡", "label": "㉡ 예술로 볼 수 있는가(근거 포함)",
             "groups": [["예술로 보기 어렵", "예술이 아니"], ["감정", "느끼지 못"], ["철학", "이야기 없"]],
             "min_match": 2, "opposite": ["예술이다"]},
            {"key": "㉢", "label": "㉢ 예술로서의 가치",
             "groups": [["감동을 주지 못", "울리지 못"], ["미술계", "변화", "범주", "확장", "상징적", "의미가 있"]],
             "min_match": 2, "opposite": ["가치가 전혀 없", "가치 없음"]},
        ],
        "model": {"㉠": "로봇의 완벽한 피겨 스케이팅(비유) / 1만 5,000점의 데이터를 학습해 제작",
                  "㉡": "감정도 느끼지 못하고 독자적인 철학이나 이야기가 없으므로 예술로 보기 어렵다",
                  "㉢": "감상자에게 남다른 감동을 주지는 못하지만 미술계에 변화를 가져오고 예술의 범주를 확장한다는 상징적 가치가 있음"},
    },
    ("3", "2"): {
        "type": "dual_method",
        "context": "인공지능 그림을 바라보는 시각",
        "slot1": {"label": "(1) 예시 등 관련 문장",
                  "content_groups": [["에드몽", "데이터", "알고리즘", "학습"], ["감정", "철학", "이야기 없"]],
                  "content_min": 1, "forbidden": ["가치가 전혀 없"]},
        "slot2": {"label": "(2) 비교/비유 관련 문장",
                  "content_groups": [["피겨 스케이팅", "로봇"], ["감동", "울리지 못"], ["상징적", "가치", "범주", "확장"]],
                  "content_min": 2, "forbidden": ["예술이다"]},
        "model": {
            "기본 조합(예시+비교와 대조)": [
                "예를 들어 「에드몽 드 벨라미」처럼 데이터를 학습해 그려진 그림은 감정이나 철학이 없어 진정한 예술로 보기는 어렵다.(예시)",
                "그러나 로봇의 피겨 스케이팅이 감동을 주지 못하는 것처럼 인공지능 그림도 감동을 주지는 못하지만, 미술계에 변화를 가져온다는 점에서 상징적 가치를 지닌다는 차이가 있다.(비교와 대조)"],
            "대안 조합(인과+분석)": [
                "인공지능은 감정과 철학이 없기 때문에 예술로 인정받기 어렵다.(인과)",
                "인공지능 그림의 가치는 미술계에 준 변화와 예술 범주의 확장이라는 두 측면으로 나누어 볼 수 있다.(분석)"],
        },
    },
    ("3", "3"): {
        "type": "av",
        "context": "장면2(인간 예술) 연출",
        "A": {"label": "시각 요소(Ⓐ)+효과",
              "groups": [["화가", "인간"], ["감정", "눈물", "표정"], ["경험", "과정", "수정", "흔적"]],
              "min_match": 2, "opposite": ["로봇", "완벽하게", "실수 없이"]},
        "B": {"label": "청각 요소(Ⓑ)+효과",
              "groups": [["숨소리", "붓", "자연스러운"], ["감정", "잔잔", "선율"]],
              "min_match": 1, "opposite": ["기계음", "메트로놈", "일정한 박자"]},
        "model": {"A": "화가가 수정 흔적이 남은 캔버스 앞에서 감정을 드러내는 모습을 보여줌 — 작가의 경험과 감정이 담긴 인간 예술의 특성을 시각화.",
                  "B": "붓질 소리와 감정이 담긴 잔잔한 선율을 사용 — 기계음과 대비되는 인간적 감동을 청각적으로 전달."},
    },
}

TOTAL_POINTS = {"1": 3, "2": 6, "3": 6}

# ------------------------------------------------------------------
# 3. Streamlit UI
# ------------------------------------------------------------------

st.set_page_config(page_title="서논술형 자동 채점기", page_icon="📝", layout="centered")
st.title("📝 서·논술형 자동 채점기 (해냄연수 대비)")
st.caption("규칙 기반 채점: 용어가 없어도 의미가 통하면 인정 · 오개념/방향 오류 자동 탐지 · 설명 방법 특성 검증")

with st.sidebar:
    st.header("문항 선택")
    set_no = st.radio("세트", ["1", "2", "3"],
                       format_func=lambda x: f"{x}세트 " + {"1": "(사회적 촉진/억제)", "2": "(정전기)", "3": "(AI 그림)"}[x])
    q_no = st.radio("문항", ["1", "2", "3"], format_func=lambda x: f"서·논술형 {x}")
    st.divider()
    st.caption("※ '지문 내용만 활용했는지'(외부지식 여부)는 자동 판별이 어려워 참고용 표시만 제공합니다.")

cfg = CONFIG[(set_no, q_no)]
st.subheader(f"{set_no}세트 · 서·논술형 {q_no}")
st.info(f"맥락: {cfg['context']}")

# ---------------- 서논술형 1: 빈칸형 ----------------
if cfg["type"] == "blank":
    inputs = {}
    for b in cfg["blanks"]:
        inputs[b["key"]] = st.text_input(b["label"], key=f"{set_no}{q_no}{b['key']}")

    if st.button("채점하기", type="primary"):
        total_pass = 0
        for b in cfg["blanks"]:
            passed, feedback, matched, total = score_blank(inputs[b["key"]], b)
            total_pass += int(passed)
            with st.container(border=True):
                st.markdown(f"**{b['label']}**")
                st.write(f"입력: {inputs[b['key']] or '(미입력)'}")
                for f in feedback:
                    st.write(f)
        pts = round(total_pass / len(cfg["blanks"]) * TOTAL_POINTS[q_no], 1)
        st.success(f"### 총점(추정): {pts} / {TOTAL_POINTS[q_no]}점  ({total_pass}/{len(cfg['blanks'])}개 항목 통과)")

    with st.expander("모범 답안 보기"):
        for k, v in cfg["model"].items():
            st.write(f"**{k}**: {v}")

# ---------------- 서논술형 2: 설명 방법 선택형 ----------------
elif cfg["type"] == "dual_method":
    st.caption("각 문장 끝에 사용한 설명 방법을 괄호로 표기하세요. 예: ...공부하는 것이 효율적이다.(예시)")
    t1 = st.text_area(cfg["slot1"]["label"], key=f"{set_no}{q_no}slot1", height=90)
    t2 = st.text_area(cfg["slot2"]["label"], key=f"{set_no}{q_no}slot2", height=90)

    if st.button("채점하기", type="primary"):
        m1, fb1, method1 = score_slot(t1, cfg["slot1"])
        m2, fb2, method2 = score_slot(t2, cfg["slot2"], other_method=method1)
        # (1)에서도 (2)와 같은 방법 중복 여부 재확인 표시는 slot2 체크에서 처리됨
        with st.container(border=True):
            st.markdown(f"**{cfg['slot1']['label']}**")
            for f in fb1:
                st.write(f)
        with st.container(border=True):
            st.markdown(f"**{cfg['slot2']['label']}**")
            for f in fb2:
                st.write(f)

        both_filled = bool((t1 or "").strip()) and bool((t2 or "").strip())
        passed_count = int(m1) + int(m2)
        pts = round(passed_count / 2 * TOTAL_POINTS[q_no], 1)
        if not both_filled:
            st.warning("두 문장을 모두 입력해야 정확히 채점됩니다.")
        st.success(f"### 총점(추정): {pts} / {TOTAL_POINTS[q_no]}점")

    with st.expander("선택 가능한 설명 방법 조합별 모범 답안"):
        st.caption("실제 선택지는 없지만, 서로 다른 설명 방법 조합을 고르는 것이 문항 구조이므로 대표 조합들을 예시로 제공합니다.")
        for combo_name, sentences in cfg["model"].items():
            st.markdown(f"**{combo_name}**")
            for s in sentences:
                st.write(f"- {s}")

# ---------------- 서논술형 3: 시청각 연출형 ----------------
else:
    a_text = st.text_area(cfg["A"]["label"], key=f"{set_no}{q_no}A", height=100,
                           placeholder="시각 요소와 그 효과를 함께 작성하세요.")
    b_text = st.text_area(cfg["B"]["label"], key=f"{set_no}{q_no}B", height=100,
                           placeholder="청각 요소와 그 효과를 함께 작성하세요.")

    if st.button("채점하기", type="primary"):
        pa, fa, ma, ta = score_av(a_text, cfg["A"])
        pb, fb, mb, tb = score_av(b_text, cfg["B"])
        with st.container(border=True):
            st.markdown(f"**{cfg['A']['label']}**")
            for f in fa:
                st.write(f)
        with st.container(border=True):
            st.markdown(f"**{cfg['B']['label']}**")
            for f in fb:
                st.write(f)
        pts = round((int(pa) + int(pb)) / 2 * TOTAL_POINTS[q_no], 1)
        st.success(f"### 총점(추정): {pts} / {TOTAL_POINTS[q_no]}점")

    with st.expander("모범 답안 보기"):
        st.write(f"**시각 요소(Ⓐ)**: {cfg['model']['A']}")
        st.write(f"**청각 요소(Ⓑ)**: {cfg['model']['B']}")

st.divider()
st.caption("⚠️ 이 채점기는 키워드/패턴 기반 보조 도구입니다. '지문 근거만 활용했는가', '문장 표현의 완성도' 등은 "
           "교사의 최종 검토가 필요합니다. 특히 3세트 ㉠(비유 vs 사실정보 인정 범위)은 채점 전 기준 확정을 권장합니다.")
