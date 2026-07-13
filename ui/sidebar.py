import streamlit as st
import os
from core.utils import load_model_cached, unload_model, sync_chunks
from core.model_runtime import BACKEND_SPECS, wrap_model_runtime

MODELS_DIR = os.path.abspath("./models")

def render_sidebar() -> dict:
    is_batch_running = "batch_future" in st.session_state and st.session_state.batch_future is not None and not st.session_state.batch_future.done()
    is_single_running = "single_futures" in st.session_state and any(f is not None and not f.done() for f in st.session_state.single_futures.values())
    is_running = is_batch_running or is_single_running

    with st.sidebar:
        st.header("시스템 설정")
        
        # 1. 추론 엔진 선택
        engine_options = ["mlx-vlm (로컬 실행)", "OpenRouter API (원격 실행)"]
        if "inference_engine" not in st.session_state:
            st.session_state.inference_engine = "mlx-vlm (로컬 실행)"
            
        selected_engine = st.selectbox(
            "추론 엔진 선택",
            options=engine_options,
            index=engine_options.index(st.session_state.inference_engine),
            disabled=is_running
        )
        if "inference_engine" in st.session_state and selected_engine != st.session_state.inference_engine:
            unload_model()
            st.session_state.inference_engine = selected_engine
            st.rerun()
        st.session_state.inference_engine = selected_engine

        if selected_engine == "mlx-vlm (로컬 실행)":
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
                                st.session_state.model_runtime = wrap_model_runtime(
                                    model,
                                    processor,
                                    backend_key="mlx",
                                    model_id=model_path,
                                )
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
        else:
            # OpenRouter API 설정
            openrouter_key = st.text_input(
                "OpenRouter API Key",
                value=st.session_state.get("openrouter_api_key", os.environ.get("OPENROUTER_API_KEY", "")),
                type="password",
                disabled=is_running
            )
            st.session_state.openrouter_api_key = openrouter_key

            or_model_options = [
                "nvidia/nemotron-3-ultra-550b-a55b:free",
                "직접 입력..."
            ]
            
            saved_or_model = st.session_state.get("openrouter_model", "nvidia/nemotron-3-ultra-550b-a55b:free")
            default_or_idx = 0
            if saved_or_model in or_model_options:
                default_or_idx = or_model_options.index(saved_or_model)
            else:
                default_or_idx = len(or_model_options) - 1 # 직접 입력
                
            selected_or_option = st.selectbox(
                "오픈라우터 모델 선택",
                options=or_model_options,
                index=default_or_idx,
                disabled=is_running
            )
            
            if selected_or_option == "직접 입력...":
                or_model_name = st.text_input(
                    "오픈라우터 모델 ID 입력",
                    value=saved_or_model if saved_or_model not in or_model_options else "nvidia/nemotron-3-ultra-550b-a55b:free",
                    disabled=is_running
                )
            else:
                or_model_name = selected_or_option
                
            st.session_state.openrouter_model = or_model_name
            openrouter_supports_vision = st.checkbox(
                "선택한 API 모델 이미지 분석 사용",
                value=st.session_state.get("openrouter_supports_vision", False),
                help="OpenRouter 모델이 vision 입력을 지원할 때만 켜세요. 꺼져 있으면 소개 이미지는 건너뛰고 텍스트 대본만 분석합니다.",
                disabled=is_running,
            )
            st.session_state.openrouter_supports_vision = openrouter_supports_vision

            # OpenRouter Connection button
            if not st.session_state.model_loaded:
                st.markdown('<div class="status-box status-warn">API 연결 필요</div>', unsafe_allow_html=True)
                if st.button("오픈라우터 API 활성화", width="stretch", disabled=is_running):
                    if not openrouter_key.strip():
                        st.error("API Key를 입력해 주세요.")
                    else:
                        try:
                            with st.spinner("오픈라우터 API 활성화 중..."):
                                from core.openrouter import OpenRouterClient
                                client = OpenRouterClient(api_key=openrouter_key, model_name=or_model_name)
                                client.supports_vision = openrouter_supports_vision
                                st.session_state.model = client
                                st.session_state.processor = None
                                st.session_state.model_runtime = wrap_model_runtime(
                                    client,
                                    None,
                                    backend_key="openrouter",
                                    model_id=or_model_name,
                                    supports_vision=openrouter_supports_vision,
                                )
                                st.session_state.model_loaded = True
                            st.success("오픈라우터 API 연결 완료!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"연결 중 오류 발생: {e}")
            else:
                st.markdown('<div class="status-box status-ok">API 연결 완료</div>', unsafe_allow_html=True)
                st.info(f"현재 모델: {st.session_state.openrouter_model}")
                if st.button("API 연결 해제", width="stretch", disabled=is_running):
                    unload_model()
                    st.rerun()
        st.divider()
        with st.expander("모델 런타임/가속기 어댑터", expanded=False):
            st.caption("현재는 MLX와 OpenRouter만 실제 실행됩니다. 나머지는 교체 가능한 어댑터 슬롯입니다.")
            for spec in BACKEND_SPECS.values():
                state = "사용 가능" if spec.available else "준비 슬롯"
                vision = "VLM 가능" if spec.supports_vision else "LM 전용"
                st.markdown(f"- **{spec.label}**: {state}, {vision}")
                if spec.note:
                    st.caption(spec.note)
        
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
    
    if st.session_state.get("inference_engine") == "OpenRouter API (원격 실행)":
        from core.openrouter import get_openrouter_request_count, MAX_DAILY_REQUESTS
        or_count = get_openrouter_request_count()
        st.sidebar.markdown(f"**OpenRouter API 호출량** ({or_count} / {MAX_DAILY_REQUESTS}회)")
        progress_val = min(1.0, or_count / MAX_DAILY_REQUESTS)
        st.sidebar.progress(progress_val)
        if or_count >= MAX_DAILY_REQUESTS:
            st.sidebar.error("오늘의 API 호출 한도(900회)를 초과했습니다. 내일까지 대기 필요.")
        elif or_count >= 800:
            st.sidebar.warning("일일 제한 권장량 도달 임박")
        else:
            st.sidebar.caption(f"일일 무료 한도 초과 방지를 위한 일시정지선")
        st.sidebar.divider()
    
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
