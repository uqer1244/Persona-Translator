import streamlit as st
import time
from core.utils import EXECUTOR, LiveStatus, colorize_directives, save_progress_backup
from core.progress_store import save_progress
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

def render_tab_translate(params: dict):
    temperature = params["temperature"]
    repetition_penalty = params["repetition_penalty"]
    chunk_size = params["chunk_size"]
    translate_directives = params["translate_directives"]
    
    st.header("대본 번역 실행 및 실시간 진행 상태")
    
    total_chunks = len(st.session_state.chunks)
    translated_count = sum(1 for c in st.session_state.translated_chunks if c.strip())
    
    LIVE_STATUS = st.session_state.LIVE_STATUS
    
    # 1. 스레드 동기화 (백그라운드에서 완료된 번역이 있다면 메인 세션에 커밋)
    new_saved = False
    for idx, trans_text in list(LIVE_STATUS.completed_translations.items()):
        if idx < len(st.session_state.translated_chunks):
            st.session_state.translated_chunks[idx] = trans_text
            st.session_state[f"chunk_trans_{idx}"] = trans_text
            new_saved = True
            if idx in LIVE_STATUS.completed_translations:
                del LIVE_STATUS.completed_translations[idx]
    if new_saved:
        save_progress_backup()
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
        
    new_single_saved = False
    for idx, trans_text in list(LIVE_STATUS.single_completed_translations.items()):
        if idx < len(st.session_state.translated_chunks):
            st.session_state.translated_chunks[idx] = trans_text
            st.session_state[f"chunk_trans_{idx}"] = trans_text
            new_single_saved = True
            if idx in st.session_state.single_futures:
                st.session_state.single_futures[idx] = None
            if idx in LIVE_STATUS.single_streaming_text:
                del LIVE_STATUS.single_streaming_text[idx]
            if idx in LIVE_STATUS.single_completed_translations:
                del LIVE_STATUS.single_completed_translations[idx]
    if new_single_saved:
        save_progress_backup()
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])

    # 2. 번역 실행 상태 점검 및 에러 처리
    if st.session_state.batch_future is not None and st.session_state.batch_future.done():
        try:
            exc = st.session_state.batch_future.exception()
            if exc:
                import traceback
                print("[ERROR] Batch translation thread crashed:")
                traceback.print_exception(type(exc), exc, exc.__traceback__)
                st.error(f"일괄 번역 중 오류가 발생했습니다: {exc}")
                with st.expander("상세 에러 로그 보기", expanded=True):
                    st.code("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), language="python")
        except Exception as e:
            print(f"[ERROR] Failed to extract batch thread exception: {e}")
        st.session_state.batch_future = None
        LIVE_STATUS.current_chunk_idx = -1
        LIVE_STATUS.current_streaming_text = ""

    for idx, f in list(st.session_state.single_futures.items()):
        if f is not None and f.done():
            try:
                exc = f.exception()
                if exc:
                    import traceback
                    print(f"[ERROR] Single translation thread for chunk {idx+1} crashed:")
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
                    st.error(f"청크 {idx+1} 번역 중 오류가 발생했습니다: {exc}")
                    with st.expander("상세 에러 로그 보기", expanded=True):
                        st.code("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), language="python")
            except Exception as e:
                print(f"[ERROR] Failed to extract single thread exception for chunk {idx+1}: {e}")
            st.session_state.single_futures[idx] = None
            if idx in LIVE_STATUS.single_streaming_text:
                del LIVE_STATUS.single_streaming_text[idx]

    is_batch_running = st.session_state.batch_future is not None and not st.session_state.batch_future.done()
    is_single_running = any(f is not None and not f.done() for f in st.session_state.single_futures.values())

    if total_chunks > 0:
        progress_ratio = translated_count / total_chunks
        st.progress(progress_ratio)
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("전체 청크", f"{total_chunks:,}")
        col_p2.metric("번역 완료", f"{translated_count:,}")
        col_p3.metric("남은 청크", f"{total_chunks - translated_count:,}")
    else:
        st.info("아직 번역할 청크가 없습니다. 1번 탭에서 대본을 입력하거나 파일을 불러오면 번역 준비 상태가 표시됩니다.")

    # 3. 일괄 번역 진행바 및 중지 컨트롤
    if is_batch_running:
        curr_idx = LIVE_STATUS.current_chunk_idx
        if curr_idx < 0:
            curr_idx = 0
        progress_val = min(1.0, max(0.0, (curr_idx) / total_chunks))
        
        st.progress(progress_val)
        st.subheader(f"전체 번역 진행 중 (청크 {curr_idx + 1} / {total_chunks})")
        
        # 시간 경과 및 ETA 계산
        elapsed_sec = 0.0
        eta_str = "계산 중..."
        speed_str = "계산 중..."
        
        if hasattr(LIVE_STATUS, "translate_start_time"):
            elapsed_sec = time.time() - LIVE_STATUS.translate_start_time
            if curr_idx > 0:
                sec_per_chunk = elapsed_sec / curr_idx
                speed_str = f"{sec_per_chunk:.1f}초/청크"
                remaining_chunks = total_chunks - curr_idx
                remaining_sec = sec_per_chunk * remaining_chunks
                if remaining_sec > 60:
                    eta_str = f"{int(remaining_sec // 60)}분 {int(remaining_sec % 60)}초"
                else:
                    eta_str = f"{int(remaining_sec)}초"
            else:
                speed_str = "첫 청크 처리 중..."
                eta_str = "대기 중..."
                
        if elapsed_sec > 60:
            elapsed_str = f"{int(elapsed_sec // 60)}분 {int(elapsed_sec % 60)}초"
        else:
            elapsed_str = f"{int(elapsed_sec)}초"
            
        col_time1, col_time2, col_time3 = st.columns(3)
        with col_time1:
            st.metric("진행 시간", elapsed_str)
        with col_time2:
            st.metric("번역 속도", speed_str)
        with col_time3:
            st.metric("남은 시간 (예상)", eta_str)
        
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        
        col_abort1, col_abort2 = st.columns([3, 1])
        with col_abort1:
            st.warning("일괄 번역이 실행 중입니다. 중지 버튼을 누르면 현재 진행 중인 구역의 작업은 저장되지 않고 멈춥니다.")
        with col_abort2:
            if st.button("일괄 번역 중지", key="stop_batch_btn", type="primary", width="stretch"):
                st.session_state.batch_cancel_token["cancel"] = True
                st.session_state.batch_future = None
                LIVE_STATUS.current_chunk_idx = -1
                LIVE_STATUS.current_streaming_text = ""
                st.warning("중지하는 중...")
                st.rerun()

        col_orig_live, col_trans_live = st.columns(2)
        with col_orig_live:
            st.markdown("##### 현재 번역 중인 원문 청크")
            curr_orig_text = st.session_state.chunks[curr_idx] if curr_idx < len(st.session_state.chunks) else ""
            st.info(curr_orig_text)
        with col_trans_live:
            st.markdown("##### 실시간 로컬 LLM 스트리밍")
            import html
            raw_stream = LIVE_STATUS.current_streaming_text
            if params.get("enable_coloring", True):
                display_stream = colorize_directives(raw_stream)
            else:
                display_stream = html.escape(raw_stream)
            st.markdown(
                f'<div style="border: 1px solid #ff4b4b; padding: 15px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 15px;">{display_stream}</div>',
                unsafe_allow_html=True
            )
            
    else:
        # 번역 미실행 시 메인 컨트롤 노출
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            start_btn = st.button("번역 실행 / 이어서 번역", type="primary", width="stretch", disabled=is_single_running or total_chunks == 0)
        with col_act2:
            reset_btn = st.button("번역 진행 상태 초기화", width="stretch", disabled=is_single_running or translated_count == 0)
            
        if reset_btn:
            if total_chunks > 0:
                st.session_state.translated_chunks = [""] * total_chunks
                st.session_state.translated_script = ""
                for idx in range(total_chunks):
                    st.session_state[f"chunk_trans_{idx}"] = ""
                save_progress(
                    st.session_state.file_name,
                    st.session_state.chunks,
                    st.session_state.translated_chunks)
                st.success("진행 상태가 초기화되었습니다.")
                st.rerun()

        if start_btn:
            if not st.session_state.model_loaded:
                st.error("먼저 사이드바에서 모델을 로드해주세요!")
            elif not st.session_state.original_script.strip():
                st.error("번역할 대본이 없습니다. '1. 대본 입력' 탭에서 대본을 추가해 주세요.")
            else:
                from core.translator import translate_script
                import threading
                
                ctx = get_script_run_ctx()
                
                def translate_with_context(ctx, *args, **kwargs):
                    add_script_run_ctx(threading.current_thread(), ctx)
                    return translate_script(*args, **kwargs)
                
                is_srt = st.session_state.file_name.endswith(".srt")
                
                glossary_dict = {}
                for item in st.session_state.glossary_data:
                    src = item.get("원어 (Source)", "")
                    tgt = item.get("번역어 (Target)", "")
                    if src and tgt:
                        glossary_dict[str(src).strip()] = str(tgt).strip()
                
                st.session_state.batch_cancel_token = {"cancel": False}
                LIVE_STATUS.current_chunk_idx = -1
                LIVE_STATUS.current_streaming_text = ""
                LIVE_STATUS.completed_translations = {}
                LIVE_STATUS.translate_start_time = time.time()
                LIVE_STATUS.translate_token_count = 0
                LIVE_STATUS.token_speed = 0.0
                
                file_name_captured = st.session_state.file_name
                original_chunks_captured = list(st.session_state.chunks)
                translated_chunks_snapshot = list(st.session_state.translated_chunks)
                
                def update_progress(token_text, chunk_idx, total_chunks, current_chunk_translation, is_finished):
                    if not hasattr(LIVE_STATUS, 'last_chunk_idx'):
                        LIVE_STATUS.last_chunk_idx = -1
                    if LIVE_STATUS.last_chunk_idx != chunk_idx:
                        LIVE_STATUS.last_chunk_idx = chunk_idx
                        LIVE_STATUS.chunk_start_time = None
                        LIVE_STATUS.chunk_token_count = 0
                        
                    LIVE_STATUS.current_chunk_idx = chunk_idx
                    LIVE_STATUS.current_streaming_text = current_chunk_translation
                    
                    if token_text:
                        if LIVE_STATUS.chunk_token_count == 0:
                            LIVE_STATUS.chunk_start_time = time.time()
                        LIVE_STATUS.chunk_token_count += 1
                        if LIVE_STATUS.chunk_start_time is not None:
                            elapsed = time.time() - LIVE_STATUS.chunk_start_time
                            if elapsed > 0:
                                LIVE_STATUS.token_speed = (LIVE_STATUS.chunk_token_count - 1) / elapsed
                            
                    if is_finished:
                        from core.translator import clean_markdown
                        clean_txt = clean_markdown(current_chunk_translation)
                        LIVE_STATUS.completed_translations[chunk_idx] = clean_txt
                        
                        try:
                            if chunk_idx < len(translated_chunks_snapshot):
                                translated_chunks_snapshot[chunk_idx] = clean_txt
                                save_progress(
                                    file_name_captured,
                                    original_chunks_captured,
                                    translated_chunks_snapshot)
                        except Exception:
                            pass

                    # Real-time Streamlit UI rerun trigger
                    now = time.time()
                    if not hasattr(LIVE_STATUS, '_last_rerun_time'):
                        LIVE_STATUS._last_rerun_time = 0
                    if now - LIVE_STATUS._last_rerun_time > 0.1 or is_finished:
                        LIVE_STATUS._last_rerun_time = now
                        from core.utils import trigger_streamlit_rerun
                        trigger_streamlit_rerun(ctx)

                st.session_state.batch_future = EXECUTOR.submit(
                    translate_with_context,
                    ctx,
                    st.session_state.model,
                    st.session_state.processor,
                    st.session_state.original_script,
                    st.session_state.persona,
                    glossary_dict,
                    is_srt=is_srt,
                    translate_directives=translate_directives,
                    chunk_size=chunk_size,
                    temp=temperature,
                    repetition_penalty=repetition_penalty,
                    existing_translations=st.session_state.translated_chunks,
                    cancel_token=st.session_state.batch_cancel_token,
                    progress_callback=update_progress
                )
                st.rerun()

    # 4. 실시간 전체 텍스트 렌더링
    st.markdown("#### 지금까지 번역된 전체 텍스트")
    temp_chunks = list(st.session_state.translated_chunks)
    if is_batch_running and 0 <= LIVE_STATUS.current_chunk_idx < len(temp_chunks):
        from core.translator import clean_markdown, extract_final_translation
        temp_chunks[LIVE_STATUS.current_chunk_idx] = extract_final_translation(clean_markdown(LIVE_STATUS.current_streaming_text))
    
    full_text = "\n\n".join([c for c in temp_chunks if c])
    if full_text.strip():
        if params.get("enable_coloring", True):
            st.markdown(
                f'<div style="border: 1px solid #31333f; padding: 20px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 14px; height: 300px; overflow-y: auto;">{colorize_directives(full_text)}</div>',
                unsafe_allow_html=True
            )
        else:
            import html
            st.markdown(
                f'<div style="border: 1px solid #31333f; padding: 20px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 14px; height: 300px; overflow-y: auto;">{html.escape(full_text)}</div>',
                unsafe_allow_html=True
            )
    else:
        st.caption("번역이 시작되면 이 영역에 누적 결과가 표시됩니다.")

    # 5. 개별 청크 상세 관리 및 부분 번역/재번역
    if total_chunks > 0:
        st.divider()
        with st.expander("개별 청크 상세 관리 및 부분 번역", expanded=True):
            st.caption("각 번역 조각의 진행상황을 확인하고 개별적으로 번역/재번역을 지시하거나 중단할 수 있습니다.")
            is_srt = st.session_state.file_name.endswith(".srt")
            
            glossary_dict = {}
            for item in st.session_state.glossary_data:
                src = item.get("원어 (Source)", "")
                tgt = item.get("번역어 (Target)", "")
                if src and tgt:
                    glossary_dict[str(src).strip()] = str(tgt).strip()
            
            for idx in range(total_chunks):
                is_this_single_active = idx in st.session_state.single_futures and st.session_state.single_futures[idx] is not None and not st.session_state.single_futures[idx].done()
                is_batch_active_on_this = is_batch_running and LIVE_STATUS.current_chunk_idx == idx
                
                with st.container():
                    col_c1, col_c2, col_c3 = st.columns([5, 5, 2])
                    with col_c1:
                        st.text_area(f"청크 {idx+1} 원문", st.session_state.chunks[idx], height=120, key=f"chunk_orig_{idx}", disabled=True)
                    
                    # 개별 청크 번역 필드
                    with col_c2:
                        if is_this_single_active:
                            stream_val = LIVE_STATUS.single_streaming_text.get(idx, "")
                            st.text_area(f"청크 {idx+1} 번역 (실시간 스트리밍...)", stream_val, height=120, key=f"chunk_trans_stream_{idx}", disabled=True)
                        elif is_batch_active_on_this:
                            stream_val = LIVE_STATUS.current_streaming_text
                            st.text_area(f"청크 {idx+1} 번역 (실시간 스트리밍...)", stream_val, height=120, key=f"chunk_trans_stream_{idx}", disabled=True)
                        else:
                            # Ensure the key exists in session state before rendering to prevent default value warnings
                            if f"chunk_trans_{idx}" not in st.session_state:
                                st.session_state[f"chunk_trans_{idx}"] = st.session_state.translated_chunks[idx]
                            new_trans = st.text_area(f"청크 {idx+1} 번역", key=f"chunk_trans_{idx}", height=120)
                            if new_trans != st.session_state.translated_chunks[idx]:
                                st.session_state.translated_chunks[idx] = new_trans
                                save_progress_backup()
                                if is_srt:
                                    st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                                else:
                                    st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                    
                    # 액션 및 상태 영역
                    with col_c3:
                        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                        
                        has_translation = bool(st.session_state.translated_chunks[idx].strip())
                        
                        # 3. 진행 상황 확인 (상태 라벨 표시)
                        if is_this_single_active or is_batch_active_on_this:
                            st.info("번역 진행 중")
                        elif has_translation:
                            st.success("번역 완료")
                        else:
                            st.light = st.caption("대기 중")
                            
                        # 4. 액션 버튼 배치
                        if is_this_single_active:
                            if st.button("번역 중지", key=f"cancel_btn_{idx}", type="primary", width="stretch"):
                                if idx in st.session_state.single_cancel_tokens:
                                    st.session_state.single_cancel_tokens[idx]["cancel"] = True
                                    st.session_state.single_futures[idx] = None
                                    if idx in LIVE_STATUS.single_streaming_text:
                                        del LIVE_STATUS.single_streaming_text[idx]
                                st.warning("중지됨")
                                st.rerun()
                        elif is_batch_active_on_this:
                            st.caption("일괄 번역 실행 중")
                        else:
                            btn_label = "부분 재번역" if has_translation else "부분 번역"
                            if st.button(btn_label, key=f"retrans_btn_{idx}", width="stretch", disabled=is_batch_running):
                                if not st.session_state.model_loaded:
                                    st.error("모델 로드 필요!")
                                else:
                                    # 단일 청크 번역 등록 및 시작
                                    st.session_state.single_cancel_tokens[idx] = {"cancel": False}
                                    LIVE_STATUS.single_streaming_text[idx] = ""
                                    if idx in LIVE_STATUS.single_completed_translations:
                                        del LIVE_STATUS.single_completed_translations[idx]
                                    
                                    prev_orig = st.session_state.chunks[idx-1] if idx > 0 else ""
                                    prev_trans = st.session_state.translated_chunks[idx-1] if idx > 0 else ""
                                    
                                    from core.translator import build_translation_prompt, build_retranslation_prompt
                                    if has_translation:
                                        prompt = build_retranslation_prompt(
                                            current_chunk=st.session_state.chunks[idx],
                                            existing_translation=st.session_state.translated_chunks[idx],
                                            prev_original=prev_orig,
                                            prev_translated=prev_trans,
                                            persona=st.session_state.persona,
                                            glossary=glossary_dict,
                                            is_srt=is_srt,
                                            translate_directives=translate_directives,
                                            file_name=st.session_state.file_name
                                        )
                                    else:
                                        prompt = build_translation_prompt(
                                            current_chunk=st.session_state.chunks[idx],
                                            prev_original=prev_orig,
                                            prev_translated=prev_trans,
                                            persona=st.session_state.persona,
                                            glossary=glossary_dict,
                                            is_srt=is_srt,
                                            translate_directives=translate_directives,
                                            file_name=st.session_state.file_name
                                        )
                                        
                                    def run_single_task(model, processor, prompt, chunk_idx, cancel_token, ctx):
                                        from core.translator import translate_one_chunk
                                        import threading
                                        add_script_run_ctx(threading.current_thread(), ctx)

                                        max_retries = 3
                                        clean_txt = None
                                        best_fallback_text = ""
                                        for retry in range(max_retries):
                                            current_temp = temperature
                                            current_penalty = repetition_penalty
                                            if retry > 0:
                                                current_temp = min(0.8, temperature + 0.15 * retry)
                                                current_penalty = repetition_penalty + 0.1 * retry
                                                LIVE_STATUS.single_streaming_text[chunk_idx] = f"[반복 루프 감지 - 재시도 {retry}/{max_retries-1}...]\n"

                                            def on_token(_token_text, current_text):
                                                LIVE_STATUS.single_streaming_text[chunk_idx] = current_text
                                                now = time.time()
                                                if not hasattr(LIVE_STATUS, '_last_rerun_time'):
                                                    LIVE_STATUS._last_rerun_time = 0
                                                if now - LIVE_STATUS._last_rerun_time > 0.1:
                                                    LIVE_STATUS._last_rerun_time = now
                                                    from core.utils import trigger_streamlit_rerun
                                                    trigger_streamlit_rerun(ctx)

                                            res = translate_one_chunk(
                                                model,
                                                processor,
                                                prompt,
                                                temp=current_temp,
                                                repetition_penalty=current_penalty,
                                                cancel_token=cancel_token,
                                                token_callback=on_token)
                                            if isinstance(res, tuple) and res[0] == "__REPETITION_ERROR__":
                                                clean_part = res[1]
                                                if len(clean_part) > len(best_fallback_text):
                                                    best_fallback_text = clean_part
                                                
                                                if retry < max_retries - 1:
                                                    continue
                                                else:
                                                    from core.translator import clean_markdown
                                                    clean_txt = clean_markdown(best_fallback_text) if best_fallback_text.strip() else None
                                                    break
                                            elif res == "__REPETITION_ERROR__":
                                                if retry < max_retries - 1:
                                                    continue
                                                else:
                                                    clean_txt = None
                                                    break
                                            elif res is None:
                                                clean_txt = None
                                                break
                                            else:
                                                clean_txt = res
                                                break

                                        if clean_txt is None:
                                            if cancel_token and cancel_token.get("cancel"):
                                                return None
                                            clean_txt = f"[번역 실패 - 원문 대체] {st.session_state.chunks[chunk_idx]}"
                                        else:
                                            from core.translator import extract_final_translation
                                            clean_txt = extract_final_translation(clean_txt)

                                        LIVE_STATUS.single_completed_translations[chunk_idx] = clean_txt
                                        return clean_txt

                                    single_ctx = get_script_run_ctx()
                                    st.session_state.single_futures[idx] = EXECUTOR.submit(
                                        run_single_task,
                                        st.session_state.model,
                                        st.session_state.processor,
                                        prompt,
                                        idx,
                                        st.session_state.single_cancel_tokens[idx],
                                        single_ctx
                                    )
                                    st.rerun()
                                    
                            if has_translation:
                                st.button(
                                    "번역 지우기",
                                    key=f"clear_btn_{idx}",
                                    width="stretch",
                                    disabled=is_batch_running,
                                    on_click=clear_chunk_callback,
                                    args=(idx,)
                                )
                st.divider()

    # 7. 비동기 테스크 실행 중일 때 자동 리프레시 루프 가동
    # 백그라운드 스레드에서 직접 100ms 단위로 request_rerun을 트리거하므로, 메인 스레드 무한 대기 루프는 OOM 방지를 위해 제거합니다.
    if is_batch_running or is_single_running:
        pass
        
def clear_chunk_callback(idx):
    if "translated_chunks" in st.session_state and idx < len(st.session_state.translated_chunks):
        st.session_state.translated_chunks[idx] = ""
        st.session_state[f"chunk_trans_{idx}"] = ""
        save_progress(
            st.session_state.file_name,
            st.session_state.chunks,
            st.session_state.translated_chunks)
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
