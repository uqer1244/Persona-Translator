import streamlit as st
import os
import json
import re
from core.chat_engine import ChatEngine
from core.progress_store import list_saved_personas, safe_project_name, BACKUP_ROOT

def save_chat_history(project_name: str, history: list):
    if not project_name:
        return
    project_dir = os.path.join(BACKUP_ROOT, project_name)
    if os.path.exists(project_dir):
        path = os.path.join(project_dir, "chats.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[save_chat_history] 에러: {e}")

def load_chat_history(project_name: str) -> list | None:
    if not project_name:
        return None
    path = os.path.join(BACKUP_ROOT, project_name, "chats.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def format_action_brackets(text: str) -> str:
    """
    대괄호로 감싸진 행동 지시문 [...]을 마크다운 이탤릭 *[...]* 스타일로 변환합니다.
    """
    if not text:
        return ""
    # 중첩 괄호나 특수 표기를 고려해 간단히 치환
    return re.sub(r'\[([^\]]+)\]', r'*[\1]*', text)

def render_tab_chat(params: dict):
    # 1. 세션 상태 초기화
    if "chat_engine" not in st.session_state:
        st.session_state.chat_engine = ChatEngine()
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
        
    if "last_rag_hits" not in st.session_state:
        st.session_state.last_rag_hits = []
        
    if "chat_loaded_project" not in st.session_state:
        st.session_state.chat_loaded_project = ""

    if "suggestion_chips" not in st.session_state:
        st.session_state.suggestion_chips = []

    chat_engine = st.session_state.chat_engine

    # 사이드바에서 로드된 모델 동적 공유
    chat_engine.model = st.session_state.model
    chat_engine.processor = st.session_state.processor
    chat_engine.model_loaded = st.session_state.model_loaded

    # 수동 로딩으로 전환 (프로젝트 로드 버튼 클릭 시에만 로드 및 AI 분석을 수행)

    # 2. 레이아웃 분할 (채팅 영역 2 : 정보 사이드바 1)
    col_chat, col_info = st.columns([2, 1])

    # 3. 우측 정보 영역 (캐릭터 카드 및 용어집)
    with col_info:
        st.subheader("캐릭터 카드 & 용어집")
        
        # 프로젝트 선택 및 로드
        saved_projects = list_saved_personas()
        if not saved_projects:
            st.info("로드 가능한 캐릭터 프로젝트가 없습니다. 대본을 번역하여 페르소나를 먼저 빌드해 주세요.")
            selected_project = None
        else:
            # 현재 번역 중인 프로젝트명을 기본값으로 설정 시도
            current_project = safe_project_name(st.session_state.file_name)
            default_index = 0
            if current_project in saved_projects:
                default_index = saved_projects.index(current_project)
                
            selected_project = st.selectbox(
                "채팅할 대상 프로젝트", 
                options=saved_projects, 
                index=default_index,
                help="번역이 완료되어 페르소나(persona.json)가 저장된 폴더 목록입니다."
            )
            
            # 프로젝트 로드 버튼
            load_col1, load_col2 = st.columns([1, 1])
            with load_col1:
                if st.button("대화 페르소나 생성 및 로드", width='stretch'):
                    if not st.session_state.model_loaded:
                        st.error("모델이 로드되지 않았습니다. 먼저 사이드바에서 모델을 로드해주세요!")
                    else:
                        with st.spinner("프로젝트 페르소나 및 RAG 코퍼스 구축 중..."):
                            chat_engine.load_project(selected_project)
                            st.session_state.chat_loaded_project = selected_project
                            
                            # 기존 저장된 대화 로그가 있다면 복원
                            saved_history = load_chat_history(selected_project)
                            if saved_history:
                                st.session_state.chat_history = saved_history
                            else:
                                st.session_state.chat_history = [
                                    {
                                        "role": "assistant",
                                        "content": f"안녕하세요! 저는 **'{selected_project}'** 대본 속 캐릭터입니다. 어떤 대화나 상황극을 시작할까요? [방긋 웃으며 시선을 맞춘다]"
                                    }
                                ]
                            st.session_state.last_rag_hits = []
                            
                            # 대본 전체 요약 분석 및 캐싱
                            if not chat_engine.script_summary and chat_engine.rag_items:
                                from core.analyzer import analyze_script_summary
                                with st.spinner("전체 대본 줄거리 및 상황을 AI가 요약 분석 중입니다..."):
                                    try:
                                        preview_chunks = [item["translated"] for item in chat_engine.rag_items]
                                        summary = analyze_script_summary(
                                            chat_engine.model,
                                            chat_engine.processor,
                                            metadata_text=st.session_state.get("metadata_text", ""),
                                            script_preview="",
                                            image_paths=None,
                                            file_name=st.session_state.file_name or "script.txt",
                                            chunks=preview_chunks
                                        )
                                        chat_engine.script_summary = summary
                                        project_dir = os.path.join(BACKUP_ROOT, selected_project)
                                        persona_path = os.path.join(project_dir, "persona.json")
                                        if os.path.exists(persona_path):
                                            with open(persona_path, "r", encoding="utf-8") as f:
                                                p_data = json.load(f)
                                            p_data["script_summary"] = summary
                                            with open(persona_path, "w", encoding="utf-8") as f:
                                                json.dump(p_data, f, ensure_ascii=False, indent=2)
                                    except Exception as e:
                                        print(f"대본 요약 자동 분석 실패: {e}")
                            
                            # 추천 대화 칩(Suggestion Chips) 리스트 관리
                            suggestions = chat_engine.persona.get("suggestions", [])
                            if not suggestions and chat_engine.rag_items:
                                from core.analyzer import generate_suggestion_chips
                                with st.spinner("작품 맞춤형 추천 질문을 분석하는 중..."):
                                    try:
                                        preview = "\n".join([f"{item['translated']}" for item in chat_engine.rag_items[:5]])[:4000]
                                        suggestions = generate_suggestion_chips(chat_engine.model, chat_engine.processor, preview)
                                        chat_engine.persona["suggestions"] = suggestions
                                        project_dir = os.path.join(BACKUP_ROOT, selected_project)
                                        persona_path = os.path.join(project_dir, "persona.json")
                                        if os.path.exists(persona_path):
                                            with open(persona_path, "r", encoding="utf-8") as f:
                                                p_data = json.load(f)
                                            if "persona" not in p_data:
                                                p_data["persona"] = {}
                                            p_data["persona"]["suggestions"] = suggestions
                                            with open(persona_path, "w", encoding="utf-8") as f:
                                                json.dump(p_data, f, ensure_ascii=False, indent=2)
                                    except Exception as e:
                                        print(f"추천 칩 생성 실패: {e}")
                            
                            if not suggestions:
                                suggestions = [
                                    "[조심스럽게 옆에 앉으며] 오늘 하루는 어땠어?",
                                    "[가만히 눈을 맞추며] 네가 해주는 이야기를 듣고 싶어.",
                                    "[머리를 쓰다듬어 달라는 듯이] 나 조금 피곤한데, 같이 있어줄래?",
                                    "[미소를 지으며] 너랑 이렇게 단둘이 이야기하니까 정말 좋다."
                                ]
                            st.session_state.suggestion_chips = suggestions
                            
                            st.success(f"'{selected_project}' 로드 완료 및 페르소나 준비 완료!")
                            st.rerun()
            with load_col2:
                if st.button("대화 초기화", width='stretch'):
                    if st.session_state.chat_loaded_project:
                        st.session_state.chat_history = [
                            {
                                "role": "assistant",
                                "content": f"대화가 초기화되었습니다. **'{st.session_state.chat_loaded_project}'** 상황극을 다시 이어갑니다. [정돈된 자세로 준비한다]"
                            }
                        ]
                        save_chat_history(st.session_state.chat_loaded_project, st.session_state.chat_history)
                    else:
                        st.session_state.chat_history = [
                            {
                                "role": "assistant",
                                "content": "안녕하세요! 대상 프로젝트를 로드한 뒤 대화 및 상황극을 시작해 보세요. [정중하게 고개 숙여 인사한다]"
                            }
                        ]
                    st.session_state.last_rag_hits = []
                    st.rerun()

        # 캐릭터 카드 시각화 (Glassmorphism 대체 카드로 깔끔하게 마크다운 구성)
        if st.session_state.chat_loaded_project and chat_engine.persona:
            st.markdown("---")
            st.markdown("### 🎭 캐릭터 페르소나")
            
            tone = chat_engine.persona.get("tone", "-")
            relationship = chat_engine.persona.get("relationship", "-")
            situation = chat_engine.persona.get("situation", "-")
            key_rules = chat_engine.persona.get("key_rules", [])

            st.markdown(f"**말투 및 어조**\n> {tone}")
            st.markdown(f"**화자-청자 관계**\n> {relationship}")
            st.markdown(f"**상황 정보**\n> {situation}")
            
            if key_rules:
                st.markdown("**주요 연기 규칙**")
                for rule in key_rules:
                    st.markdown(f"- {rule}")
            
            # 마스터 단어장 시각화
            valid_glossaries = [g for g in chat_engine.glossary_list if g.get("원어 (Source)") and g.get("번역어 (Target)")]
            if valid_glossaries:
                st.markdown("---")
                st.markdown("### 📖 적용된 마스터 단어장")
                glossary_html = ""
                for g in valid_glossaries[:10]: # 최대 10개만 표시
                    src = g["원어 (Source)"]
                    tgt = g["번역어 (Target)"]
                    ctx = g.get("설명/뉘앙스 (Context)", "")
                    ctx_str = f" *({ctx})*" if ctx else ""
                    glossary_html += f"- **{src}** ➡️ **{tgt}**{ctx_str}\n"
                if len(valid_glossaries) > 10:
                    glossary_html += f"\n*외 {len(valid_glossaries) - 10}개의 용어가 추가 적용됨*"
                st.markdown(glossary_html)

            # 서사 제어 모니터 렌더링
            st.markdown("---")
            st.markdown("### 🧭 서사 제어 상태")
            mode = chat_engine.last_steered_mode
            score = chat_engine.last_max_score
            
            if "레일 추종" in mode:
                st.markdown(f"**상태**: <span style='color:#4CAF50; font-weight:bold;'>🟢 {mode}</span>", unsafe_allow_html=True)
                st.caption(f"대본 매칭도: `{score:.3f}` (임계값 0.15 이상)")
            elif "탈레일" in mode:
                st.markdown(f"**상태**: <span style='color:#FF9800; font-weight:bold;'>🟡 {mode}</span>", unsafe_allow_html=True)
                st.caption(f"대본 매칭도: `{score:.3f}` (대본 이탈 - 애드립 및 복귀 유도)")
            else:
                st.markdown(f"**상태**: `대기 중` (첫 대화 대기)")
        else:
            st.markdown("---")
            st.info("👈 위의 '캐릭터 정보 로드' 버튼을 눌러 페르소나 카드와 단어장 정보를 표시하세요.")

    # 4. 좌측 채팅 영역
    with col_chat:
        st.subheader("실시간 AI 롤플레잉 챗")
        
        # 4.1 모델 로드 확인 문구
        if not st.session_state.model_loaded:
            st.markdown(
                '<div class="status-box status-warn">⚠️ 사이드바에서 로컬 VLM 모델을 먼저 로드해 주세요!</div>', 
                unsafe_allow_html=True
            )
        elif st.session_state.chat_loaded_project:
            st.markdown(
                f'<div class="status-box status-ok">✅ 캐릭터 <b>{st.session_state.chat_loaded_project}</b>와 대화할 준비가 되었습니다. (VRAM 공유 상태)</div>', 
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="status-box status-info">💡 대화할 캐릭터 프로젝트를 오른쪽에서 먼저 로드해 주세요.</div>', 
                unsafe_allow_html=True
            )

        # 4.2 대화 내역 출력
        chat_container = st.container()
        with chat_container:
            # 대화 이력이 비어있을 경우 초기 메시지 주입
            if not st.session_state.chat_history:
                if st.session_state.chat_loaded_project:
                    st.session_state.chat_history = [
                        {
                            "role": "assistant",
                            "content": f"안녕하세요! 저는 **'{st.session_state.chat_loaded_project}'** 대본 속 캐릭터입니다. 어떤 대화나 상황극을 시작할까요? [방긋 웃으며 시선을 맞춘다]"
                        }
                    ]
                else:
                    st.session_state.chat_history = [
                        {
                            "role": "assistant",
                            "content": "안녕하세요! 왼쪽 컨트롤 패널에서 번역 완료된 프로젝트와 모델을 로드하여 대화 및 상황극을 시작해 보세요. [정중하게 고개 숙여 인사한다]"
                        }
                    ]

            # 메시지 루프 렌더링
            for message in st.session_state.chat_history:
                role = message["role"]
                with st.chat_message(role):
                    formatted = format_action_brackets(message["content"])
                    st.markdown(formatted)

        # RAG 검색 매칭 결과 패널 (현재 메시지와 관련된 대본 정보 인용)
        if st.session_state.last_rag_hits:
            st.markdown("---")
            with st.expander("💡 대본 맥락 인용 정보 (RAG MATCH)", expanded=True):
                for hit in st.session_state.last_rag_hits:
                    st.markdown(
                        f"- **원문 대사**: {hit['original']}\n"
                        f"  - **번역 대사**: *{hit['translated']}* (Score: `{hit['score']:.2f}`)"
                    )
            st.markdown("---")

        # 4.3 추천 대화 칩 렌더링
        if st.session_state.chat_loaded_project and st.session_state.suggestion_chips:
            st.markdown("<div style='margin-bottom: 5px; font-weight: bold;'>💬 추천 대화 선택지 (클릭 시 즉시 전송)</div>", unsafe_allow_html=True)
            cols = st.columns(len(st.session_state.suggestion_chips))
            for idx, chip in enumerate(st.session_state.suggestion_chips):
                with cols[idx]:
                    if st.button(chip, key=f"sug_chip_{idx}", width='stretch'):
                        st.session_state.temp_user_input = chip
                        st.rerun()
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # 4.4 사용자 입력창 제어
        input_disabled = not st.session_state.model_loaded or not st.session_state.chat_loaded_project
        placeholder_text = "대화를 입력하세요..." if not input_disabled else "VLM 모델과 캐릭터 정보가 모두 로드되어야 입력할 수 있습니다."
        
        user_query = None
        if st.session_state.get("temp_user_input"):
            user_query = st.session_state.pop("temp_user_input")
            
        if not user_query:
            user_query = st.chat_input(placeholder_text, disabled=input_disabled)
            
        if user_query:
            # 1. 사용자 메시지 즉시 렌더링 및 추가
            with st.chat_message("user"):
                st.markdown(format_action_brackets(user_query))
            st.session_state.chat_history.append({"role": "user", "content": user_query})

            # 2. 어시스턴트 스트리밍 영역 사전 배치
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                
                # 3. 비동기/동기 스트리밍 호출
                temp = params.get("temperature", 0.7)
                rep_penalty = params.get("repetition_penalty", 1.15)
                
                # generate_chat_response_stream은 JSON Line 제너레이터
                stream_generator = chat_engine.generate_chat_response_stream(
                    user_message=user_query,
                    history=st.session_state.chat_history[:-1], # 직전 내역까지
                    temp=temp,
                    repetition_penalty=rep_penalty
                )
                
                full_response = ""
                rag_hits = []
                
                import time
                start_time = None
                token_count = 0
                LIVE_STATUS = st.session_state.get("LIVE_STATUS")
                
                for chunk in stream_generator:
                    try:
                        event_data = json.loads(chunk.strip())
                        event = event_data.get("event")
                        data = event_data.get("data")
                        
                        if event == "rag_hits":
                            rag_hits = data
                            st.session_state.last_rag_hits = rag_hits
                        elif event == "token":
                            if token_count == 0:
                                start_time = time.time()
                            full_response += data
                            token_count += 1
                            if start_time is not None:
                                elapsed = time.time() - start_time
                                if elapsed > 0:
                                    speed = (token_count - 1) / elapsed
                                    if LIVE_STATUS:
                                        LIVE_STATUS.token_speed = speed
                            # 실시간으로 행동 지시문 변환하여 렌더링
                            message_placeholder.markdown(format_action_brackets(full_response) + "▌")
                        elif event == "error":
                            st.error(f"대화 생성 오류: {data}")
                    except Exception:
                        pass
                
                message_placeholder.markdown(format_action_brackets(full_response))
                st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                save_chat_history(st.session_state.chat_loaded_project, st.session_state.chat_history)
                st.rerun()
