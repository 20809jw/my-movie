from datetime import datetime
import pandas as pd
import requests
import streamlit as st
import pytz

# 페이지 기본 설정
st.set_page_config(page_title="어제 박스오피스", layout="wide")


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
            return (
                None,
                "해당 날짜의 데이터가 비어있거나 아직 집계되지 않았습니다.",
            )

        return movie_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


# --- 앱 화면 구현 ---
st.title("🎬 어제 일별 박스오피스 순위")

# Streamlit Secrets에서 API 키 불러오기
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 API 키가 설정되지 않았습니다.")
    st.info(
        "Streamlit Cloud의 App Settings > Secrets에서 `KOBIS_KEY`를 등록해 주세요."
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 배포 서버 시계와 상관없이 한국 시간(KST) 기준 '어제' 날짜 계산
kst = pytz.timezone("Asia/Seoul")
yesterday_kst = datetime.now(kst) - pd.Timedelta(days=1)
target_dt = yesterday_kst.strftime("%Y%m%d")
formatted_date = yesterday_kst.strftime("%Y년 %m월 %d일")

st.caption(f"기준일: {formatted_date}")

# 데이터 요청
movie_data, error_message = fetch_daily_boxoffice(api_key, target_dt)

# 오류 처리 안내 화면
if error_message:
    st.error(error_message)
    st.markdown(
        """
    ---
    **💡 오류 해결 방법:**
    1. Streamlit Secrets에 `KOBIS_KEY` 값이 정확히 입력되었는지 확인해 주세요.
    2. KOBIS 개발자 센터에서 발급받은 키가 활성화 상태인지 확인해 주세요.
    3. 네트워크 상태를 확인하고 잠시 후 페이지를 새로고침 해보세요.
    """
    )
    st.stop()

# Pandas DataFrame으로 데이터 전환 및 숫자 형변환
df = pd.DataFrame(movie_data)

# API 응답 결과가 문자열 형태로 오므로 수치 연산 및 정렬을 위해 정수로 변환
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

# 순위 기준 재정렬
df = df.sort_values("rank")

# 1위 영화 지표 카드 (Metrics)
top_1 = df.iloc[0]
st.subheader(f"🥇 1위: {top_1['movieNm']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="어제 관객수",
        value=f"{top_1['audiCnt']:,} 명",
        delta=f"{top_1['rankInten']} 위" if top_1["rankInten"] != 0 else None,
    )
with col2:
    st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")
with col3:
    st.metric(label="스크린수", value=f"{top_1['scrnCnt']:,} 개")

st.divider()

# 관객수 상위 5편 막대그래프
st.subheader("📊 관객수 상위 5개 영화")
top_5_df = df.head(5)

# Streamlit 내장 막대그래프 활용
st.bar_chart(data=top_5_df, x="movieNm", y="audiCnt", color="#FF4B4B")

st.divider()

# 박스오피스 전체 순위 표
st.subheader("📋 박스오피스 전체 순위")

# 표 출력을 위한 컬럼 재구성 및 명칭 변경
display_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = [
    "순위",
    "영화명",
    "개봉일",
    "어제 관객수",
    "누적 관객수",
    "스크린수",
]

# 화면 출력
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "어제 관객수": st.column_config.NumberColumn(format="%d 명"),
        "누적 관객수": st.column_config.NumberColumn(format="%d 명"),
        "스크린수": st.column_config.NumberColumn(format="%d 개"),
    },
)
