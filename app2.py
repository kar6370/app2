import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import random
import datetime as dt
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from openai import OpenAI

# ==========================================
# 1. 페이지 설정 및 커스텀 CSS (UI/UX)
# ==========================================
st.set_page_config(page_title="2026 워킹 챌린지 정약용 펀그라운드", page_icon="🏃", layout="wide")

st.markdown("""
<style>
    /* 전체 배경 및 폰트 설정 */
    .stApp {
        background-color: #f4f7f6;
    }
    .main-title {
        font-size: 40px;
        font-weight: 800;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 30px;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    .sub-title {
        font-size: 24px;
        font-weight: 600;
        color: #2563EB;
        margin-bottom: 15px;
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
    }
    .highlight-text {
        color: #E11D48;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 전역 변수 및 챌린지 룰 세팅
# ==========================================
# 직원 명단 하드코딩 (정약용 펀그라운드 전용)
USERS = ["김효진", "김경민", "김승섭", "이승주", "신호성", "최소연", "김재균", "정진교", "장명광", "원영길", "김미야", "한승희"]

# ==========================================
# 3. Firebase 및 OpenAI 초기화
# ==========================================
@st.cache_resource
def init_firebase():
    try:
        if not firebase_admin._apps:
            # Streamlit Cloud 배포 시 st.secrets["firebase"] 에 json 내용을 넣어야 합니다.
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        # 키가 없을 경우를 대비한 로컬 테스트용 모드
        return None

db = init_firebase()

def init_openai():
    try:
        return OpenAI(api_key=st.secrets["openai"]["api_key"])
    except:
        return None

client = init_openai()

# 로컬 Mock 데이터 (Firebase 연결 실패 시 사용)
if 'mock_db' not in st.session_state:
    st.session_state.mock_db = pd.DataFrame(columns=["name", "department", "record_date", "month", "steps", "timestamp"])

# ==========================================
# 4. 데이터 처리 헬퍼 함수
# ==========================================
def save_steps(name, department, record_date_obj, month, steps):
    timestamp = datetime.now()
    record_date_str = record_date_obj.strftime("%Y-%m-%d")
    
    new_data = {
        "name": name, 
        "department": department, 
        "record_date": record_date_str,
        "month": month,
        "steps": steps, 
        "timestamp": timestamp
    }
    
    if db:
        # Firebase에 저장
        doc_ref = db.collection("walking_challenge").document()
        doc_ref.set(new_data)
    else:
        # Mock DB에 저장
        st.session_state.mock_db = pd.concat([st.session_state.mock_db, pd.DataFrame([new_data])], ignore_index=True)

def get_all_data():
    if db:
        docs = db.collection("walking_challenge").stream()
        data = [doc.to_dict() for doc in docs]
        df = pd.DataFrame(data) if data else pd.DataFrame(columns=["name", "department", "record_date", "month", "steps", "timestamp"])
    else:
        df = st.session_state.mock_db.copy()
        
    if not df.empty:
        # 과거 데이터 호환성 유지 (record_date가 없는 경우)
        if 'record_date' not in df.columns:
            df['record_date'] = "2026-03-01" 
        
        # 중복 방지: 같은 사람이 같은 날짜에 여러 번 입력하면 가장 마지막 기록만 남김
        df = df.sort_values('timestamp').drop_duplicates(subset=['name', 'record_date'], keep='last')
        
    return df

def generate_ai_message(name, avg_steps, goal_diff):
    if not client:
        return f"💪 {name}님, 오늘도 힘찬 발걸음 응원합니다! (AI 연동 대기중)"
    
    prompt = f"직원이름: {name}, 하루 평균 걸음수: {avg_steps}보, 만보목표까지 남은걸음: {goal_diff}보. 이 직원을 위해 친근하고 위트있는 1~2문장의 건강 격려 메시지를 작성해줘."
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        return response.choices[0].message.content
    except:
        return f"💪 {name}님, 오늘도 파이팅입니다!"

# ==========================================
# 5. UI 및 페이지 뷰
# ==========================================
st.markdown('<div class="main-title">🏃 2026 사내 워킹 챌린지 정약용 펀그라운드</div>', unsafe_allow_html=True)

menu = st.sidebar.radio("📌 메뉴 이동", ["👟 걸음 수 입력", "📊 내 대시보드", "🏆 전사 리더보드 (통계)"])

df_all = get_all_data()

# ------------------------------------------
# [페이지 1] 걸음 수 입력
# ------------------------------------------
if menu == "👟 걸음 수 입력":
    st.markdown('<div class="sub-title">1. 실시간 일일 걸음 수 등록</div>', unsafe_allow_html=True)
    st.info("💡 삼성 헬스 어플을 확인하시고, 측정하신 날짜와 그 날의 총 걸음 수를 입력해 주세요.")
    
    # 날짜 제한 설정 (3.1 ~ 5.31) & 미래 날짜 선택 방지
    today = dt.date.today()
    start_date = dt.date(2026, 3, 1)
    end_date = dt.date(2026, 5, 31)
    
    max_allowed_date = min(today, end_date)
    # 만약 현재 날짜가 3월 1일 이전이라면, 에러 방지를 위해 달력 최대값을 3월 1일로 고정
    if max_allowed_date < start_date:
        max_allowed_date = start_date
        st.warning("⏳ 아직 워킹 챌린지 시작 전(3월 1일 이전)입니다. 현재는 테스트 입력만 가능합니다.")

    with st.form("step_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("직원 성명", USERS)
            # 소속 부서는 정약용펀그라운드로 자동 고정 (UI에선 숨기거나 비활성화 느낌으로 표시)
            department = "정약용펀그라운드" 
            st.text_input("소속 부서", value=department, disabled=True)
            
        with col2:
            record_date = st.date_input(
                "걸음 수 측정 날짜", 
                value=max_allowed_date, 
                min_value=start_date, 
                max_value=max_allowed_date
            )
            steps = st.number_input("해당 일자 총 걸음 수 입력", min_value=0, step=100)
            
        submit = st.form_submit_button("🚀 등록하기", use_container_width=True)
        
        if submit:
            if today < start_date and record_date == start_date:
                 # 테스트 허용 로직 통과
                 pass
            elif record_date > today:
                st.error("미래 날짜의 걸음 수는 미리 입력할 수 없습니다!")
                st.stop()
                
            input_month = record_date.month
            save_steps(name, department, record_date, input_month, steps)
            st.success(f"🎉 {name}님의 {record_date.strftime('%m월 %d일')} 걸음 수({steps:,}보)가 성공적으로 저장되었습니다!")
            st.balloons()

# ------------------------------------------
# [페이지 2] 개인 대시보드
# ------------------------------------------
elif menu == "📊 내 대시보드":
    # 대시보드 전용 3D 유저 버튼 스타일 적용
    st.markdown("""
    <style>
        /* 선택된 사용자 (Primary) - 3D 입체 효과, 크기 확대, 색상 활성화 */
        button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            color: white !important;
            transform: scale(1.15);
            box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.5), inset 0 3px 6px rgba(255, 255, 255, 0.4);
            border: none;
            transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
            border-radius: 18px;
            font-weight: 800;
            padding: 15px 0;
            z-index: 10;
            position: relative;
        }
        /* 비활성 사용자 (Secondary) - 회색조, 크기 축소, 평면 효과 */
        button[data-testid="baseButton-secondary"] {
            background: #f8fafc;
            color: #94a3b8 !important;
            transform: scale(0.85);
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #e2e8f0;
            transition: all 0.3s ease;
            border-radius: 15px;
            filter: grayscale(100%) opacity(0.6);
        }
        button[data-testid="baseButton-secondary"]:hover {
            transform: scale(0.95);
            filter: grayscale(0%) opacity(1);
            background: #f1f5f9;
            color: #475569 !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        /* 버튼 컨테이너 정렬 보정 */
        .stButton {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-bottom: 15px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sub-title">2. 나의 걸음 수 분석 및 AI 피드백</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; font-size:16px; color:#64748b; margin-bottom:20px;">👇 인포그래픽에서 본인의 아이콘을 클릭하세요</p>', unsafe_allow_html=True)

    # 세션 상태에 선택된 사용자 저장 (초기값 설정)
    if 'dash_selected_user' not in st.session_state:
        st.session_state.dash_selected_user = None

    # 12명의 직원을 2줄(6명씩)로 배치하여 인포그래픽 갤러리 구현
    cols1 = st.columns(6)
    cols2 = st.columns(6)

    for i, u in enumerate(USERS):
        col = cols1[i] if i < 6 else cols2[i - 6]
        with col:
            is_selected = (st.session_state.dash_selected_user == u)
            btn_type = "primary" if is_selected else "secondary"
            icon = "🏃" if is_selected else "👤"

            # 버튼 클릭 시 해당 사용자로 상태 변경 후 새로고침
            if st.button(f"{icon} {u}", key=f"btn_{u}", type=btn_type, use_container_width=True):
                st.session_state.dash_selected_user = u
                st.rerun()

    st.markdown("<br><hr style='margin-top:0;'>", unsafe_allow_html=True)
    
    search_name = st.session_state.dash_selected_user
    
    if search_name and not df_all.empty:
        user_data = df_all[df_all['name'] == search_name].copy()
        
        if not user_data.empty:
            # 월별 걸음수 합산 (동일 일자 중복은 get_all_data에서 이미 제거됨)
            user_monthly = user_data.groupby('month')['steps'].sum().reset_index()
            total_steps = user_monthly['steps'].sum()
            
            # AI 메시지 생성용 데이터 (최근 기록 기준)
            last_month = user_monthly['month'].max()
            last_month_data = user_data[user_data['month'] == last_month]
            last_steps = last_month_data['steps'].sum()
            
            # (수정) 일평균 = 해당 월의 총 걸음 수 / 걸음을 '기록한' 일수
            recorded_days_count = last_month_data['record_date'].nunique()
            if recorded_days_count > 0:
                avg_daily = int(last_steps / recorded_days_count)
            else:
                avg_daily = 0
                
            diff_to_10k = max(0, 10000 - avg_daily)
            
            # OpenAI 메시지
            ai_msg = generate_ai_message(search_name, avg_daily, diff_to_10k)
            st.success(f"🤖 **AI 건강 비서:** {ai_msg}")
            
            # 주요 지표
            col1, col2, col3 = st.columns(3)
            col1.markdown(f'<div class="metric-card"><h3>총 누적 걸음</h3><h2>{total_steps:,}보</h2></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><h3>최근 ({last_month}월) 일평균</h3><h2>{avg_daily:,}보</h2><p style="font-size:12px; color:gray;">(기록일수: {recorded_days_count}일)</p></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><h3>만보까지 남은 걸음</h3><h2>{diff_to_10k:,}보/일</h2></div>', unsafe_allow_html=True)
            
            st.markdown("---")
            # 3D 차트 시각화 (Plotly)
            st.markdown('#### 📈 월별 누적 걸음 수 3D 입체 분석')
            fig = go.Figure(data=[go.Bar(
                x=[f"{m}월" for m in user_monthly['month']],
                y=user_monthly['steps'],
                marker_color=user_monthly['steps'],
                marker_colorscale='Viridis',
                text=user_monthly['steps'],
                textposition='auto',
            )])
            fig.update_layout(
                scene=dict(xaxis_title='월', yaxis_title='걸음 수'),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("등록된 데이터가 없습니다. 먼저 걸음 수를 등록해 주세요.")
            
    elif not search_name:
        st.info("👆 위 인포그래픽에서 본인의 이름을 클릭해 주세요.")

# ------------------------------------------
# [페이지 3] 전사 리더보드 (통계 & 포상)
# ------------------------------------------
elif menu == "🏆 전사 리더보드 (통계)":
    st.markdown('<div class="sub-title">3. 챌린지 랭킹 및 통계</div>', unsafe_allow_html=True)
    
    if df_all.empty:
        st.info("아직 등록된 데이터가 없습니다.")
    else:
        # 데이터 전처리
        # 1. 개인별 총합 (워킹 King 산출용)
        user_total = df_all.groupby(['name', 'department'])['steps'].sum().reset_index().sort_values('steps', ascending=False)
        
        # 2. 월평균 만보 달성자 필터링 (수정: 걸음을 기록한 날짜 기준)
        monthly_record_days = df_all.groupby(['name', 'department', 'month'])['record_date'].nunique().reset_index()
        monthly_record_days.rename(columns={'record_date': 'recorded_days'}, inplace=True)
        
        monthly_user = df_all.groupby(['name', 'department', 'month'])['steps'].sum().reset_index()
        monthly_user = pd.merge(monthly_user, monthly_record_days, on=['name', 'department', 'month'])
        
        monthly_user['daily_avg'] = monthly_user.apply(lambda row: row['steps'] / row['recorded_days'] if row['recorded_days'] > 0 else 0, axis=1)
        achievers_10k = monthly_user[monthly_user['daily_avg'] >= 10000]

        # ----------------- UI 렌더링 -----------------
        # (수정) 불필요한 탭(부서 대항전, 행운상) 삭제
        tab1, tab2 = st.tabs(["👑 워킹 King", "🎖️ 만보 달성자"])
        
        with tab1:
            st.markdown("#### 🏆 개인별 누적 걸음 수 TOP 3 (3~5월 통합)")
            top3 = user_total.head(3).reset_index(drop=True)
            cols = st.columns(3)
            # 금액 삭제
            medals = ["🥇 1위", "🥈 2위", "🥉 3위"]
            for i in range(min(3, len(top3))):
                with cols[i]:
                    st.markdown(f"""
                    <div class="metric-card" style="border-top: 5px solid #F59E0B;">
                        <h3>{medals[i]}</h3>
                        <h2 style="color:#D97706;">{top3.loc[i, 'name']}</h2>
                        <p>{top3.loc[i, 'department']}</p>
                        <h4>{int(top3.loc[i, 'steps']):,} 보</h4>
                    </div>
                    """, unsafe_allow_html=True)

        with tab2:
            st.markdown("#### ⭐ 월평균 10,000보 달성자 명단")
            st.caption("※ 평균 걸음 수 계산 = 해당 월의 총 걸음 수 / 걸음을 등록한 일수")
            if not achievers_10k.empty:
                achievers_show = achievers_10k[['month', 'department', 'name', 'daily_avg']].copy()
                achievers_show['daily_avg'] = achievers_show['daily_avg'].astype(int)
                achievers_show.columns = ['달성 월', '소속 부서', '성명', '일평균 걸음수']
                st.dataframe(achievers_show.sort_values(by=['달성 월', '일평균 걸음수'], ascending=[True, False]), use_container_width=True, hide_index=True)
            else:
                st.info("아직 만보 달성자가 없습니다. 분발해주세요!")