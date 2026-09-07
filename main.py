from datetime import datetime
import pandas as pd
import requests
import streamlit as st
import pytz

# 페이지 기본 설정
st.set_page_config(page_title="일별 박스오피스 조회", layout="wide")


# 1시간 동안 API 결과를 메모리에 저장(캐싱)하여 중복 요청을 방지합니다.
@st.cache_data(ttl=3600)
def fetch_daily_boxoffice(api_key, target_date):
    """KOBIS API를 통해 지정된 날짜의 일별 박스오피스 데이터를 가져옵니다."""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 1. API 오류 응답 처리 (인증키 오류 등)
        if "faultInfo" in data:
            error_msg = data["faultInfo"].get(
                "message", "API 오류가 발생했습니다."
            )
            return None, f"KOBIS API 오류: {error_msg}"

        # 2. 데이터 구조 확인
        boxoffice_result = data.get("boxOfficeResult", {})
        movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

        if not movie_list:
            return None, "그날은 아직 집계 전입니다."

        return movie_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


# --- 앱 화면 구현 ---
st.title("🎬 날짜별 박스오피스 조회")

# Streamlit Secrets에서 API 키 불러오기
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 API 키가 설정되지 않았습니다.")
    st.info(
        "Streamlit Cloud의 App Settings > Secrets에서 `KOBIS_KEY`를 등록해 주세요."
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 한국 시간(KST) 기준 '어제' 날짜 계산 (달력의 최대 선택 기준일)
kst = pytz.timezone("Asia/Seoul")
yesterday_kst = (datetime.now(kst) - pd.Timedelta(days=1)).date()

# 달력을 통해 조회 날짜 선택 (최대 어제 날짜까지만 선택 가능)
selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday_kst,
    max_value=yesterday_kst,
    help="오늘 날짜 이후는 집계 전이므로 선택할 수 없습니다.",
)

# API 요청용 yyyymmdd 포맷 변환
target_dt = selected_date.strftime("%Y%m%d")
formatted_date = selected_date.strftime("%Y년 %m월 %d일")

st.caption(f"📅 조회 기준일: {formatted_date}")

# 데이터 요청
movie_data, error_message = fetch_daily_boxoffice(api_key, target_dt)

# 오류 또는 데이터가 없을 때 안내
if error_message:
    st.warning(f"⚠️ {error_message}")
    if "API 오류" in error_message or "네트워크" in error_message:
        st.markdown(
            """
        ---
        **💡 오류 해결 방법:**
        1. Streamlit Secrets에 `KOBIS_KEY`가 올바르게 입력되었는지 확인하세요.
        2. KOBIS 개발자 센터 키의 활성화 여부를 확인해 주세요.
        """
        )
    st.stop()

# Pandas DataFrame 전환 및 숫자 변환
df = pd.DataFrame(movie_data)

numeric_columns = [
    "rank",
    "rankInten",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "showCnt",
]
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 관객수 높은 순(내림차순) 정렬
df = df.sort_values("audiCnt", ascending=False)

# 1. 누적 관객수 100만 이상 트로피 🏆 표시
df["movieNm_display"] = df.apply(
    lambda x: f"🏆 {x['movieNm']}" if x["audiAcc"] >= 1_000_000 else x["movieNm"],
    axis=1,
)

# 2. 순위 증감 화살표 기호 조합 (rankInten)
def format_rank_inten(val):
    if val > 0:
        return f"🔺 +{val}"
    elif val < 0:
        return f"🔹 {val}"
    return "-"


df["rankChange"] = df["rankInten"].apply(format_rank_inten)

# 1위 영화 지표 카드 (Metrics)
top_1 = df.iloc[0]
st.subheader(f"🥇 관객수 1위: {top_1['movieNm_display']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="일일 관객수",
        value=f"{top_1['audiCnt']:,} 명",
        delta=top_1["rankChange"],
    )
with col2:
    st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")
with col3:
    st.metric(label="스크린수", value=f"{top_1['scrnCnt']:,} 개")

st.divider()

# 관객수 높은 순 상위 5편 막대그래프
top_5_df = df.head(5).copy()

# 차트 범주 순서 고정 (가나다순 재정렬 방지)
top_5_df["movieNm_display"] = pd.Categorical(
    top_5_df["movieNm_display"],
    categories=top_5_df["movieNm_display"],
    ordered=True,
)

st.subheader("📊 관객수 상위 5개 영화 (관객수 높은 순)")
st.bar_chart(data=top_5_df, x="movieNm_display", y="audiCnt", color="#FF4B4B")

st.divider()

# 전체 박스오피스 순위 표
st.subheader("📋 전체 순위 (관객수 높은 순)")

display_df = df[
    [
        "rank",
        "rankChange",
        "movieNm_display",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()
display_df.columns = [
    "순위",
    "순위변동",
    "영화명",
    "개봉일",
    "일일 관객수",
    "누적 관객수",
    "스크린수",
]

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "일일 관객수": st.column_config.NumberColumn(format="%d 명"),
        "누적 관객수": st.column_config.NumberColumn(format="%d 명"),
        "스크린수": st.column_config.NumberColumn(format="%d 개"),
    },
)
