import streamlit as st
import os
from core.utils import load_model_cached, unload_model, sync_chunks

MODELS_DIR = os.path.abspath("./models")

def render_sidebar() -> dict:
    is_batch_running = "batch_future" in st.session_state and st.session_state.batch_future is not None and not st.session_state.batch_future.done()
    is_single_running = "single_futures" in st.session_state and any(f is not None and not f.done() for f in st.session_state.single_futures.values())
    is_running = is_batch_running or is_single_running

    with st.sidebar:
        st.header("시스템 설정")
        st.markdown(f"**추론 엔진**: `mlx-vlm`")
        
        # Scan for local model subdirectories in ./models/
        local_models = []
        if os.path.exists(MODELS_DIR):
            for d in os.listdir(MODELS_DIR):
                full_path = os.path.join(MODELS_DIR, d)
                if os.path.isdir(full_path) and d != "hf_cache" and not d.startswith("."):
                    local_models.append(os.path.join("models", d))
        local_models.sort(key=lambda path: ("8bit" in path.lower(), "4bit" not in path.lower(), path.lower()))
                    
        # Model Selection UI
        options = local_models + ["직접 경로 입력..."]
        selected_option = st.selectbox(
            "로컬 모델 선택",
            options=options,
            index=0 if local_models else len(options)-1,
            disabled=is_running
        )
        
        if selected_option == "직접 경로 입력...":
            model_path = st.text_input(
                "모델 폴더 절대 경로 또는 Hugging Face ID", 
                value=os.path.abspath("./models/Gemma4_12B_4bit_mlx"),
                disabled=is_running
            )
        else:
            model_path = os.path.abspath(selected_option)
            
        st.markdown(f"**로드할 경로**: `{model_path}`")
        is_high_memory_model = "8bit" in model_path.lower()
        allow_high_memory_model = False
        if is_high_memory_model:
            st.warning("8bit 12B 모델은 메모리 부족으로 Python 프로세스가 종료될 수 있습니다. 가능하면 4bit 모델을 먼저 사용하세요.")
            allow_high_memory_model = st.checkbox("위험을 이해하고 8bit 모델 로딩 허용", value=False, disabled=is_running)
        
        # Model load button
        if not st.session_state.model_loaded:
            st.markdown('<div class="status-box status-warn">모델 로드 필요</div>', unsafe_allow_html=True)
            if st.button("로컬 모델 메모리에 로딩", width="stretch", disabled=is_running):
                if is_high_memory_model and not allow_high_memory_model:
                    st.error("메모리 보호를 위해 8bit 모델 로딩을 막았습니다. 4bit 모델을 선택하거나 허용 체크박스를 켜 주세요.")
                elif not os.path.exists(model_path) and not "/" in model_path:
                    st.error("지정한 로컬 경로가 존재하지 않습니다. 올바른 경로를 입력해 주세요.")
                else:
                    try:
                        with st.spinner("지정한 경로에서 모델을 불러오는 중입니다..."):
                            model, processor = load_model_cached(model_path)
                            st.session_state.model = model
                            st.session_state.processor = processor
                            st.session_state.model_loaded = True
                        st.success("모델 로드 성공!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"모델 로드 중 오류 발생: {e}")
        else:
            st.markdown('<div class="status-box status-ok">모델 준비 완료</div>', unsafe_allow_html=True)
            st.info(f"현재 로드된 모델: {model_path}")
            if st.button("모델 메모리 언로드", width="stretch", disabled=is_running):
                unload_model()
                st.rerun()
                
        st.divider()
        
        # Translation parameters
        st.header("하이퍼파라미터")
        temperature = st.slider("Temperature (창의성/자유도)", 0.1, 1.0, 0.3, step=0.1, disabled=is_running)
        repetition_penalty = st.slider("Repetition Penalty (반복 억제력)", 1.0, 1.5, 1.1, step=0.05, disabled=is_running)
        chunk_size = st.slider("청크 크기 (글자 수 기준)", 300, 1500, 400, step=50, disabled=is_running)
        translate_directives = st.checkbox("괄호 안 지시문 번역 ([whispering] -> [속삭임])", value=True, disabled=is_running)
        enable_coloring = st.checkbox("실시간 대본 채색 활성화 (지시문/화자 하이라이트)", value=True)

    # Sync chunks with original script
    sync_chunks(chunk_size)

    # 📈 실시간 리소스 및 성능 리포트
    st.sidebar.divider()
    st.sidebar.subheader("📈 실시간 시스템 및 성능")
    
    from core.utils import get_memory_stats
    mem = get_memory_stats()
    
    # RAM 사용량 표시
    st.sidebar.markdown(f"**시스템 RAM 사용량** ({mem['ram_percent']:.1f}%)")
    st.sidebar.progress(mem['ram_percent'] / 100.0)
    st.sidebar.caption(f"{mem['ram_used_gb']:.2f} GB / {mem['ram_total_gb']:.2f} GB 사용 중")
    
    # MLX Unified Memory 사용량 표시
    if mem['mlx_active_gb'] > 0 or mem['mlx_peak_gb'] > 0:
        st.sidebar.markdown(f"**Unified GPU 메모리 (MLX)**")
        st.sidebar.caption(f"Active: {mem['mlx_active_gb']:.2f} GB / Peak: {mem['mlx_peak_gb']:.2f} GB")
        ratio = min(1.0, mem['mlx_active_gb'] / mem['mlx_peak_gb']) if mem['mlx_peak_gb'] > 0 else 0.0
        st.sidebar.progress(ratio)
        if mem['mlx_cache_gb'] > 0:
            st.sidebar.caption(f"Cached Memory: {mem['mlx_cache_gb']:.2f} GB")
    else:
        st.sidebar.caption("Unified GPU 메모리 정보 (대기 중)")

    # 실시간 추론 속도 표시
    token_speed = 0.0
    if "LIVE_STATUS" in st.session_state and hasattr(st.session_state.LIVE_STATUS, "token_speed"):
        token_speed = st.session_state.LIVE_STATUS.token_speed
    st.sidebar.metric("실시간 토큰 생성 속도", f"{token_speed:.2f} tok/s")
    
    return {
        "temperature": temperature,
        "repetition_penalty": repetition_penalty,
        "chunk_size": chunk_size,
        "translate_directives": translate_directives,
        "enable_coloring": enable_coloring
    }
