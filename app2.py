import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import random
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from openai import OpenAI

# ==========================================
# 1. 페이지 설정 및 커스텀 CSS (UI/UX)
# ==========================================
st.set_page_config(page_title="2026 워킹 챌린지 대시보드", page_icon="🏃", layout="wide")

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
MONTHS = {3: 31, 4: 30, 5: 31} # 3~5월 및 해당 월의 일수 (만보 계산용)

# 부서별 그룹 하드코딩
GROUP_1 = ["개발사업1부", "감사팀", "전략기획부", "사업기획부", "개발사업2부", "개발사업3부", "인사성과부", "안전경영팀", "경영지원부", "펀그라운드수동"]
GROUP_2 = ["기획조정부", "주차시설부", "펀그라운드진접", "정약용펀그라운드", "비전센터", "주차운영부", "철도안전부", "철도운영부", "철도지원부", "에코랜드운영부"]
GROUP_3 = ["화도푸른물센터", "청소년수련관", "진접센터", "화도센터", "와부센터", "오남센터", "별내센터", "호평센터", "남양주센터", "평내센터"]
ALL_DEPTS = GROUP_1 + GROUP_2 + GROUP_3

# 부서별 현원 (참여율 70점 계산을 위한 임시 데이터 - 실제 부서 현원으로 수정 필요)
# 구현을 위해 임의로 각 부서 현원을 20명으로 세팅합니다.
DEPT_HEADCOUNT = {dept: 20 for dept in ALL_DEPTS}

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
    st.session_state.mock_db = pd.DataFrame(columns=["name", "department", "month", "steps", "timestamp"])

# ==========================================
# 4. 데이터 처리 헬퍼 함수
# ==========================================
def save_steps(name, department, month, steps):
    timestamp = datetime.now()
    if db:
        # Firebase에 저장
        doc_ref = db.collection("walking_challenge").document()
        doc_ref.set({
            "name": name, "department": department, "month": month,
            "steps": steps, "timestamp": timestamp
        })
    else:
        # Mock DB에 저장
        new_row = {"name": name, "department": department, "month": month, "steps": steps, "timestamp": timestamp}
        st.session_state.mock_db = pd.concat([st.session_state.mock_db, pd.DataFrame([new_row])], ignore_index=True)

def get_all_data():
    if db:
        docs = db.collection("walking_challenge").stream()
        data = [doc.to_dict() for doc in docs]
        return pd.DataFrame(data) if data else pd.DataFrame(columns=["name", "department", "month", "steps", "timestamp"])
    else:
        return st.session_state.mock_db

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
st.markdown('<div class="main-title">🏃 2026 사내 워킹 챌린지 대시보드</div>', unsafe_allow_html=True)

menu = st.sidebar.radio("📌 메뉴 이동", ["👟 걸음 수 입력", "📊 내 대시보드", "🏆 전사 리더보드 (통계)"])

df_all = get_all_data()

# ------------------------------------------
# [페이지 1] 걸음 수 입력
# ------------------------------------------
if menu == "👟 걸음 수 입력":
    st.markdown('<div class="sub-title">1. 실시간 걸음 수 등록</div>', unsafe_allow_html=True)
    st.info("💡 삼성 헬스 어플을 확인하시고, 해당 월의 총 걸음 수를 입력해 주세요.")
    
    with st.form("step_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("직원 성명")
            department = st.selectbox("소속 부서", ALL_DEPTS)
        with col2:
            month = st.selectbox("해당 월", [3, 4, 5], format_func=lambda x: f"2026년 {x}월")
            steps = st.number_input("월간 총 걸음 수 입력", min_value=0, step=1000)
            
        submit = st.form_submit_button("🚀 등록하기", use_container_width=True)
        
        if submit:
            if name.strip() == "":
                st.error("성명을 입력해 주세요!")
            else:
                save_steps(name, department, month, steps)
                st.success(f"🎉 {name}님의 {month}월 걸음 수({steps:,}보)가 성공적으로 저장되었습니다!")
                st.balloons()

# ------------------------------------------
# [페이지 2] 개인 대시보드
# ------------------------------------------
elif menu == "📊 내 대시보드":
    st.markdown('<div class="sub-title">2. 나의 걸음 수 분석 및 AI 피드백</div>', unsafe_allow_html=True)
    search_name = st.text_input("🔍 성명을 입력하여 내 기록을 확인하세요")
    
    if search_name and not df_all.empty:
        user_data = df_all[df_all['name'] == search_name].copy()
        
        if not user_data.empty:
            # 월별 걸음수 합산 (중복 입력 방지용)
            user_monthly = user_data.groupby('month')['steps'].sum().reset_index()
            total_steps = user_monthly['steps'].sum()
            
            # AI 메시지 생성용 데이터 (최근 기록 기준)
            last_month = user_monthly['month'].max()
            last_steps = user_monthly[user_monthly['month'] == last_month]['steps'].values[0]
            days_in_month = MONTHS[last_month]
            avg_daily = int(last_steps / days_in_month)
            diff_to_10k = max(0, 10000 - avg_daily)
            
            # OpenAI 메시지
            ai_msg = generate_ai_message(search_name, avg_daily, diff_to_10k)
            st.success(f"🤖 **AI 건강 비서:** {ai_msg}")
            
            # 주요 지표
            col1, col2, col3 = st.columns(3)
            col1.markdown(f'<div class="metric-card"><h3>총 누적 걸음</h3><h2>{total_steps:,}보</h2></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><h3>최근 ({last_month}월) 일평균</h3><h2>{avg_daily:,}보</h2></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><h3>만보까지 남은 걸음</h3><h2>{diff_to_10k:,}보/일</h2></div>', unsafe_allow_html=True)
            
            st.markdown("---")
            # 3D 차트 시각화 (Plotly)
            st.markdown('#### 📈 월별 걸음 수 3D 입체 분석')
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

# ------------------------------------------
# [페이지 3] 전사 리더보드 (통계 & 포상)
# ------------------------------------------
elif menu == "🏆 전사 리더보드 (통계)":
    st.markdown('<div class="sub-title">3. 전사 통계 및 챌린지 랭킹</div>', unsafe_allow_html=True)
    
    if df_all.empty:
        st.info("아직 등록된 데이터가 없습니다.")
    else:
        # 데이터 전처리
        # 1. 개인별 총합 (워킹 King 산출용)
        user_total = df_all.groupby(['name', 'department'])['steps'].sum().reset_index().sort_values('steps', ascending=False)
        
        # 2. 월평균 만보 달성자 필터링
        monthly_user = df_all.groupby(['name', 'department', 'month'])['steps'].sum().reset_index()
        monthly_user['days'] = monthly_user['month'].map(MONTHS)
        monthly_user['daily_avg'] = monthly_user['steps'] / monthly_user['days']
        achievers_10k = monthly_user[monthly_user['daily_avg'] >= 10000]

        # 3. 부서 대항전 로직 (참여율 70 + 걸음수 30)
        dept_stats = df_all.groupby('department').agg(
            total_steps=('steps', 'sum'),
            participants=('name', 'nunique')
        ).reset_index()
        
        # 각 부서별 점수 계산
        dept_stats['headcount'] = dept_stats['department'].map(DEPT_HEADCOUNT).fillna(20)
        dept_stats['participation_rate'] = (dept_stats['participants'] / dept_stats['headcount']) * 100
        # 참여율 점수 (최대 70점) - 100%일때 70점
        dept_stats['score_participate'] = (dept_stats['participation_rate'] / 100) * 70
        dept_stats['score_participate'] = dept_stats['score_participate'].clip(upper=70)
        
        # 걸음수 점수 (최대 30점) - 가장 많이 걸은 부서 기준 상대평가
        max_dept_steps = dept_stats['total_steps'].max()
        dept_stats['score_steps'] = (dept_stats['total_steps'] / max_dept_steps) * 30 if max_dept_steps > 0 else 0
        
        dept_stats['total_score'] = dept_stats['score_participate'] + dept_stats['score_steps']
        
        # 그룹 매핑
        def get_group(dept):
            if dept in GROUP_1: return "1그룹"
            elif dept in GROUP_2: return "2그룹"
            elif dept in GROUP_3: return "3그룹"
            return "기타"
        dept_stats['group'] = dept_stats['department'].apply(get_group)

        # ----------------- UI 렌더링 -----------------
        tab1, tab2, tab3, tab4 = st.tabs(["👑 워킹 King", "💯 부서 대항전", "🎖️ 만보 달성자", "🍀 행운상 추첨"])
        
        with tab1:
            st.markdown("#### 🏆 개인별 누적 걸음 수 TOP 3 (3~5월 통합)")
            top3 = user_total.head(3).reset_index(drop=True)
            cols = st.columns(3)
            medals = ["🥇 1위 (10만원)", "🥈 2위 (5만원)", "🥉 3위 (3만원)"]
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
            st.markdown("#### 🏢 부서 그룹별 우수부서 현황")
            st.caption("※ 평가 방식: 참여율(70점) + 총 걸음수(30점)")
            
            for grp in ["1그룹", "2그룹", "3그룹"]:
                st.markdown(f"##### 🎯 {grp} 리더보드")
                grp_df = dept_stats[dept_stats['group'] == grp].sort_values('total_score', ascending=False)
                if not grp_df.empty:
                    # 소수점 1자리 포맷팅
                    display_df = grp_df[['department', 'participation_rate', 'total_steps', 'total_score']].copy()
                    display_df.columns = ['부서명', '참여율(%)', '총 걸음수', '종합 점수']
                    display_df['참여율(%)'] = display_df['참여율(%)'].round(1)
                    display_df['종합 점수'] = display_df['종합 점수'].round(2)
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.write(f"{grp}에 아직 등록된 데이터가 없습니다.")

        with tab3:
            st.markdown("#### ⭐ 월평균 10,000보 달성자 (월별 50명 추첨 대상)")
            st.caption("3개월(3~5월) 중 1개월 기준 평균 걸음 수 만보 이상 달성자 목록입니다.")
            if not achievers_10k.empty:
                achievers_show = achievers_10k[['month', 'department', 'name', 'daily_avg']].copy()
                achievers_show['daily_avg'] = achievers_show['daily_avg'].astype(int)
                achievers_show.columns = ['달성 월', '소속 부서', '성명', '일평균 걸음수']
                st.dataframe(achievers_show.sort_values(by=['달성 월', '일평균 걸음수'], ascending=[True, False]), use_container_width=True, hide_index=True)
            else:
                st.info("아직 만보 달성자가 없습니다. 분발해주세요!")

        with tab4:
            st.markdown("#### 🎁 전 직원 대상 무작위 50명 행운상 추첨")
            st.write("1회 이상 참여한 전 직원을 대상으로 커피쿠폰(5천원)을 드립니다.")
            
            unique_participants = df_all['name'].unique().tolist()
            st.write(f"현재 총 참여자 수: **{len(unique_participants)}명**")
            
            if st.button("🎰 행운상 추첨하기", use_container_width=True):
                if len(unique_participants) > 0:
                    draw_count = min(50, len(unique_participants))
                    winners = random.sample(unique_participants, draw_count)
                    st.success(f"🎉 축하합니다! {draw_count}명의 행운상 당첨자가 추첨되었습니다.")
                    
                    # 당첨자 예쁘게 출력
                    winner_df = pd.DataFrame(winners, columns=["당첨자 성명"])
                    st.dataframe(winner_df, use_container_width=True)
                    st.balloons()
                else:
                    st.warning("추첨할 대상자가 없습니다.")