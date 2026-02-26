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
        border-bottom: 2px solid #2563EB;
        padding-bottom: 5px;
        display: inline-block;
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
    .notice-card {
        background: white;
        padding: 20px;
        border-left: 5px solid #3b82f6;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 15px;
    }
    .timeline-date {
        font-weight: bold;
        color: #ef4444;
        font-size: 18px;
    }
    .guide-step {
        background-color: #ffffff;
        padding: 25px;
        border-radius: 12px;
        margin-bottom: 15px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 전역 변수 및 챌린지 룰 세팅
# ==========================================
# 직원 명단 하드코딩 (정약용 펀그라운드 전용)
USERS = ["김효진", "김경민", "김승섭", "이승주", "신호성", "최소연", "김재균", "정진교", "장명광", "원영길", "김미야", "한승희"]

# ==========================================
# 3. Firebase 및 OpenAI 초기화 (디버깅 강화)
# ==========================================
@st.cache_resource
def init_firebase():
    try:
        # 1. secrets에 firebase 항목이 아예 없는 경우
        if "firebase" not in st.secrets:
            return None, "Secrets 설정에 '[firebase]' 항목이 누락되었습니다."
            
        if not firebase_admin._apps:
            cred_dict = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client(), "OK"
    except Exception as e:
        # 2. 키 값이 틀렸거나 형식이 잘못된 경우 에러 반환
        return None, str(e)

db, db_error_msg = init_firebase()

def init_openai():
    try:
        return OpenAI(api_key=st.secrets["openai"]["api_key"])
    except:
        return None

client = init_openai()

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
        doc_ref = db.collection("walking_challenge").document()
        doc_ref.set(new_data)
    else:
        st.session_state.mock_db = pd.concat([st.session_state.mock_db, pd.DataFrame([new_data])], ignore_index=True)

def get_all_data():
    if db:
        docs = db.collection("walking_challenge").stream()
        data = [doc.to_dict() for doc in docs]
        df = pd.DataFrame(data) if data else pd.DataFrame(columns=["name", "department", "record_date", "month", "steps", "timestamp"])
    else:
        df = st.session_state.mock_db.copy()
        
    if not df.empty:
        if 'record_date' not in df.columns:
            df['record_date'] = "2026-03-01" 
        df = df.sort_values('timestamp').drop_duplicates(subset=['name', 'record_date'], keep='last')
        
    return df

def delete_record_by_date(name, record_date_str):
    if db:
        docs = db.collection("walking_challenge").where("name", "==", name).stream()
        for doc in docs:
            doc_dict = doc.to_dict()
            if doc_dict.get("record_date") == record_date_str:
                doc.reference.delete()
    else:
        mask = (st.session_state.mock_db['name'] == name) & (st.session_state.mock_db['record_date'] == record_date_str)
        st.session_state.mock_db = st.session_state.mock_db[~mask]

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
st.markdown('<div class="main-title">🏃 2026 사내 워킹 챌린지 (정약용 펀그라운드)</div>', unsafe_allow_html=True)

menu = st.sidebar.radio("📌 메뉴 이동", ["📢 공지사항", "📖 걸음 수 확인 가이드", "👟 걸음 수 입력", "📊 내 대시보드", "🏆 전사 리더보드"])

# DB 연결 상태 알림 및 에러 메시지 출력 (사이드바 하단)
st.sidebar.markdown("---")
if db is None:
    st.sidebar.error("⚠️ 파이어베이스 DB 연결 안됨\n\n(현재 새로고침 시 날아가는 임시 모드)")
    # 에러 원인 출력
    st.sidebar.warning(f"🔍 원인: {db_error_msg}")
else:
    st.sidebar.success("🟢 파이어베이스 DB 정상 연동됨\n\n(데이터 영구 저장 중)")

df_all = get_all_data()

# ------------------------------------------
# [페이지 0-1] 공지사항
# ------------------------------------------
if menu == "📢 공지사항":
    st.markdown('<div class="sub-title">📢 2026 사내 워킹 챌린지 공식 안내</div>', unsafe_allow_html=True)
    st.write("전 직원 '워킹 챌린지'를 추진하오니 직원 여러분의 많은 참여와 관심 바랍니다.")
    
    st.markdown("### 🏆 포상 내용 (주요 혜택)")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="notice-card">
            <h4 style="color:#2563EB;">🏅 1. 부서 워킹 대항전</h4>
            <p><b>평가방식:</b> 참여율(70점) + 3~5월 총 걸음수(30점)<br>
            <i>※ 각 그룹당 우수부서 선정 및 포상</i></p>
        </div>
        <div class="notice-card">
            <h4 style="color:#D97706;">👑 2. 워킹 King</h4>
            <p><b>선정기준:</b> 3~5월 <b>가장 많이 걸은 직원 (누적)</b><br>
            <i>※ 전사 1위~3위 선정 (총 3명)</i></p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="notice-card">
            <h4 style="color:#059669;">⭐ 3. 만보 달성자</h4>
            <p><b>선정기준:</b> 3~5월 중 <b>월 평균 10,000보 이상 달성자</b><br>
            <i>※ 달성자 중 매월 50명 무작위 추첨</i></p>
        </div>
        <div class="notice-card">
            <h4 style="color:#9333EA;">🎁 4. 행운상</h4>
            <p><b>선정기준:</b> 1회 이상 참여한 <b>전 직원 대상</b><br>
            <i>※ 캠페인 종료 후 50명 무작위 추첨</i></p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 🗓️ 향후 일정 (타임라인)")
    st.markdown("""
    <div style="background-color: white; padding: 20px; border-radius: 10px; border-left: 5px solid #10b981;">
        <p><span class="timeline-date">📍 2026. 2. 19. ~ 2. 28.</span> &nbsp;&nbsp; 워킹 챌린지 홍보 기간</p>
        <p><span class="timeline-date">📍 2026. 3. 01. ~ 5. 31.</span> &nbsp;&nbsp; <b>워킹 챌린지 본격 실시</b> (3개월간 진행)</p>
        <p><span class="timeline-date">📍 2026. 6. 한</span> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; 결과보고 및 참여자 상품 지급</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.info("💡 **참여 방법:** '삼성 헬스' 어플을 통해 측정된 걸음 수를 본 대시보드에 직접 입력! (미참여 시 걸음 수 제외)")

# ------------------------------------------
# [페이지 0-2] 걸음 수 확인 가이드
# ------------------------------------------
elif menu == "📖 걸음 수 확인 가이드":
    st.markdown('<div class="sub-title">📱 기기별 걸음 수 확인(인증) 가이드</div>', unsafe_allow_html=True)
    st.write("본인의 스마트폰 기종에 맞는 탭을 선택하여 걸음 수 확인 방법을 알아보세요.")
    
    tab_ios, tab_and = st.tabs(["🍎 아이폰 (iOS) 사용자", "🤖 삼성 / 안드로이드 사용자"])
    
    with tab_ios:
        st.markdown("""
        <div class="guide-step">
            <h3 style="color:#333;">🍎 아이폰에서 '삼성 헬스'로 참여하기</h3>
            <p>아이폰 사용자도 '삼성 헬스' 어플을 설치하여 동일하게 참여할 수 있습니다.</p>
            <hr>
            <h4>① 앱 스토어(App Store) 실행</h4>
            <p>검색창에 <b>'삼성 헬스(Samsung Health)'</b>를 검색하고 어플을 다운로드 및 설치합니다.</p>
            <br>
            <h4>② 애플 건강(Health) 앱 데이터 연동</h4>
            <p>삼성 헬스 어플을 처음 실행할 때, 아이폰의 기본 <b>'건강' 데이터 접근 권한을 '허용'</b>으로 설정합니다. (걸음 수 데이터 연동)</p>
            <br>
            <h4>③ 걸음 수 확인</h4>
            <p>매일 또는 월말에 삼성 헬스 어플을 켜서 홈 화면 상단에 표시된 <b>해당 날짜의 걸음 수</b>를 확인합니다.</p>
            <br>
            <h4>④ 대시보드 입력</h4>
            <p>확인한 걸음 수를 본 대시보드의 <b>[👟 걸음 수 입력]</b> 메뉴에 들어와 직접 등록합니다.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with tab_and:
        st.markdown("""
        <div class="guide-step">
            <h3 style="color:#333;">🤖 안드로이드 (삼성 갤럭시 등) 사용자</h3>
            <p>기본 탑재된 '삼성 헬스' 어플을 사용하여 간편하게 확인합니다.</p>
            <hr>
            <h4>① '삼성 헬스' 앱 실행</h4>
            <p>갤럭시 스마트폰에 기본으로 설치되어 있는 <b>'삼성 헬스'</b> 어플을 찾아 실행합니다.</p>
            <br>
            <h4>② 홈 화면 걸음 수 확인</h4>
            <p>어플 홈 화면 최상단에 있는 신발 모양 아이콘과 함께 표시된 <b>오늘(또는 특정 날짜)의 총 걸음 수</b>를 확인합니다.</p>
            <br>
            <h4>③ 과거 날짜 확인 필요 시</h4>
            <p>걸음 수 위젯을 터치하여 상세 페이지로 들어간 뒤, 상단의 <b>< > (좌우 화살표)</b>를 눌러 입력하고자 하는 과거 날짜의 걸음 수를 확인합니다.</p>
            <br>
            <h4>④ 대시보드 입력</h4>
            <p>확인한 걸음 수를 본 대시보드의 <b>[👟 걸음 수 입력]</b> 메뉴에 들어와 날짜 선택 후 등록합니다.</p>
        </div>
        """, unsafe_allow_html=True)

# ------------------------------------------
# [페이지 1] 걸음 수 입력
# ------------------------------------------
elif menu == "👟 걸음 수 입력":
    st.markdown('<div class="sub-title">1. 실시간 일일 걸음 수 등록</div>', unsafe_allow_html=True)
    st.info("💡 삼성 헬스 어플을 확인하시고, 측정하신 날짜와 그 날의 총 걸음 수를 입력해 주세요.")
    
    today = dt.date.today()
    start_date = dt.date(2026, 3, 1)
    end_date = dt.date(2026, 5, 31)
    
    max_allowed_date = min(today, end_date)
    if max_allowed_date < start_date:
        max_allowed_date = start_date
        st.warning("⏳ 아직 워킹 챌린지 시작 전(3월 1일 이전)입니다. 현재는 테스트 입력만 가능합니다.")

    with st.form("step_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.selectbox("직원 성명", USERS)
            department = "정약용펀그라운드" 
            st.text_input("소속 부서", value=department, disabled=True)
            
        with col2:
            record_date = st.date_input("걸음 수 측정 날짜", value=max_allowed_date, min_value=start_date, max_value=max_allowed_date)
            steps = st.number_input("해당 일자 총 걸음 수 입력", min_value=0, step=100)
            
        submit = st.form_submit_button("🚀 등록하기", use_container_width=True)
        
        if submit:
            if today < start_date and record_date == start_date:
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
    st.markdown("""
    <style>
        button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: #fbbf24 !important; 
            border: 1px solid #fbbf24;
            box-shadow: 0 0 15px rgba(251, 191, 36, 0.4), inset 0 0 10px rgba(251, 191, 36, 0.15);
            transform: scale(1.15) translateY(-5px);
            transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
            border-radius: 8px; 
            font-weight: 900;
            letter-spacing: 2px;
            padding: 15px 0;
            z-index: 10;
            position: relative;
            overflow: hidden;
        }
        button[data-testid="baseButton-primary"]::after {
            content: ''; position: absolute; top: 0; left: -100%; width: 50%; height: 100%;
            background: linear-gradient(to right, transparent, rgba(255,255,255,0.15), transparent);
            transform: skewX(-20deg); animation: shine 2.5s infinite;
        }
        @keyframes shine { 0% { left: -100%; } 20% { left: 200%; } 100% { left: 200%; } }
        button[data-testid="baseButton-secondary"] {
            background: linear-gradient(135deg, #ffffff, #f1f5f9); color: #94a3b8 !important;
            transform: scale(0.85); box-shadow: 4px 4px 10px rgba(0,0,0,0.05), -4px -4px 10px rgba(255,255,255,0.8);
            border: 1px solid #e2e8f0; transition: all 0.3s ease; border-radius: 8px; font-weight: 600; letter-spacing: 1px;
        }
        button[data-testid="baseButton-secondary"]:hover {
            transform: scale(0.95); background: linear-gradient(135deg, #f8fafc, #e2e8f0);
            color: #475569 !important; border: 1px solid #cbd5e1; box-shadow: inset 2px 2px 5px rgba(0,0,0,0.03);
        }
        .stButton { display: flex; justify-content: center; align-items: center; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sub-title">2. 나의 걸음 수 분석 및 AI 피드백</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; font-size:16px; color:#64748b; margin-bottom:25px;">👇 아래 명단에서 본인의 <b>플레이어 카드</b>를 선택하세요</p>', unsafe_allow_html=True)

    if 'dash_selected_user' not in st.session_state:
        st.session_state.dash_selected_user = None

    cols1 = st.columns(6)
    cols2 = st.columns(6)

    for i, u in enumerate(USERS):
        col = cols1[i] if i < 6 else cols2[i - 6]
        with col:
            is_selected = (st.session_state.dash_selected_user == u)
            btn_type = "primary" if is_selected else "secondary"
            icon = "✦" if is_selected else "◈"
            if st.button(f"{icon} {u}", key=f"btn_{u}", type=btn_type, use_container_width=True):
                st.session_state.dash_selected_user = u
                st.rerun()

    st.markdown("<br><hr style='margin-top:0;'>", unsafe_allow_html=True)
    search_name = st.session_state.dash_selected_user
    
    if search_name and not df_all.empty:
        user_data = df_all[df_all['name'] == search_name].copy()
        
        if not user_data.empty:
            user_monthly = user_data.groupby('month')['steps'].sum().reset_index()
            total_steps = user_monthly['steps'].sum()
            
            last_month = user_monthly['month'].max()
            last_month_data = user_data[user_data['month'] == last_month]
            last_steps = last_month_data['steps'].sum()
            
            recorded_days_count = last_month_data['record_date'].nunique()
            avg_daily = int(last_steps / recorded_days_count) if recorded_days_count > 0 else 0
            diff_to_10k = max(0, 10000 - avg_daily)
            
            ai_msg = generate_ai_message(search_name, avg_daily, diff_to_10k)
            st.success(f"🤖 **AI 건강 비서:** {ai_msg}")
            
            col1, col2, col3 = st.columns(3)
            col1.markdown(f'<div class="metric-card"><h3>총 누적 걸음</h3><h2>{total_steps:,}보</h2></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><h3>최근 ({last_month}월) 일평균</h3><h2>{avg_daily:,}보</h2><p style="font-size:12px; color:gray;">(기록일수: {recorded_days_count}일)</p></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><h3>만보까지 남은 걸음</h3><h2>{diff_to_10k:,}보/일</h2></div>', unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown('#### 📈 월별 누적 걸음 수 3D 입체 분석')
            fig = go.Figure(data=[go.Bar(
                x=[f"{m}월" for m in user_monthly['month']],
                y=user_monthly['steps'],
                marker_color=user_monthly['steps'],
                marker_colorscale='Viridis',
                text=user_monthly['steps'],
                textposition='auto',
            )])
            fig.update_layout(scene=dict(xaxis_title='월', yaxis_title='걸음 수'), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.markdown('#### ⚙️ 내 기록 관리 (삭제)')
            st.caption("💡 잘못 입력한 날짜의 기록을 선택하여 삭제할 수 있습니다.")
            user_records_sorted = user_data.sort_values('record_date', ascending=False)
            
            if not user_records_sorted.empty:
                record_options = ["선택 안 함"] + user_records_sorted.apply(lambda x: f"{x['record_date']} ({int(x['steps']):,}보)", axis=1).tolist()
                selected_to_delete = st.selectbox("🗑️ 삭제할 날짜의 기록을 선택하세요", record_options)
                
                if selected_to_delete != "선택 안 함":
                    del_date_str = selected_to_delete.split(" ")[0]
                    if st.button("🚨 해당 날짜 기록 삭제하기", type="primary"):
                        delete_record_by_date(search_name, del_date_str)
                        st.success(f"✅ {del_date_str}의 기록이 정상적으로 삭제되었습니다.")
                        st.rerun()
            else:
                st.write("저장된 기록이 없습니다.")
        else:
            st.warning("등록된 데이터가 없습니다. 먼저 걸음 수를 등록해 주세요.")
    elif not search_name:
        st.info("👆 위 명단에서 본인의 플레이어 카드를 클릭해 주세요.")

# ------------------------------------------
# [페이지 3] 전사 리더보드 (통계 & 포상)
# ------------------------------------------
elif menu == "🏆 전사 리더보드":
    st.markdown('<div class="sub-title">3. 챌린지 랭킹 및 통계</div>', unsafe_allow_html=True)
    
    if df_all.empty:
        st.info("아직 등록된 데이터가 없습니다.")
    else:
        user_total = df_all.groupby(['name', 'department'])['steps'].sum().reset_index().sort_values('steps', ascending=False)
        
        monthly_record_days = df_all.groupby(['name', 'department', 'month'])['record_date'].nunique().reset_index()
        monthly_record_days.rename(columns={'record_date': 'recorded_days'}, inplace=True)
        
        monthly_user = df_all.groupby(['name', 'department', 'month'])['steps'].sum().reset_index()
        monthly_user = pd.merge(monthly_user, monthly_record_days, on=['name', 'department', 'month'])
        
        monthly_user['daily_avg'] = monthly_user.apply(lambda row: row['steps'] / row['recorded_days'] if row['recorded_days'] > 0 else 0, axis=1)
        achievers_10k = monthly_user[monthly_user['daily_avg'] >= 10000]

        tab1, tab2 = st.tabs(["👑 워킹 King", "🎖️ 만보 달성자"])
        
        with tab1:
            st.markdown("#### 🏆 개인별 누적 걸음 수 TOP 3 (3~5월 통합)")
            top3 = user_total.head(3).reset_index(drop=True)
            cols = st.columns(3)
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