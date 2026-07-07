import streamlit as st
import os
from core.utils import EXECUTOR, LiveStatus, colorize_directives, save_progress_backup
from core.progress_store import save_progress, get_backup_path
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
        st.info(f"전체 {total_chunks}개 청크 중 {translated_count}개 청크의 번역이 완료(임시저장)되었습니다.")

    # 3. 일괄 번역 진행바 및 중지 컨트롤
    if is_batch_running:
        curr_idx = LIVE_STATUS.current_chunk_idx
        if curr_idx < 0:
            curr_idx = 0
        progress_val = min(1.0, max(0.0, (curr_idx) / total_chunks))
        
        st.progress(progress_val)
        st.subheader(f"⏳ 전체 번역 진행 중 (청크 {curr_idx + 1} / {total_chunks})")
        
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
            colorized_stream = colorize_directives(LIVE_STATUS.current_streaming_text)
            st.markdown(
                f'<div style="border: 1px solid #ff4b4b; padding: 15px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 15px;">{colorized_stream}</div>',
                unsafe_allow_html=True
            )
            
    else:
        # 번역 미실행 시 메인 컨트롤 노출
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            start_btn = st.button("번역 실행 / 이어서 번역", type="primary", width="stretch", disabled=is_single_running)
        with col_act2:
            reset_btn = st.button("번역 진행 상태 초기화", width="stretch", disabled=is_single_running)
            
        if reset_btn:
            if total_chunks > 0:
                st.session_state.translated_chunks = [""] * total_chunks
                st.session_state.translated_script = ""
                for idx in range(total_chunks):
                    st.session_state[f"chunk_trans_{idx}"] = ""
                backup_path = get_backup_path(st.session_state.file_name)
                if os.path.exists(backup_path):
                    try:
                        import shutil
                        shutil.rmtree(os.path.dirname(backup_path))
                    except Exception:
                        pass
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
                
                file_name_captured = st.session_state.file_name
                original_chunks_captured = list(st.session_state.chunks)
                translated_chunks_snapshot = list(st.session_state.translated_chunks)
                
                def update_progress(token_text, chunk_idx, total_chunks, current_chunk_translation, is_finished):
                    LIVE_STATUS.current_chunk_idx = chunk_idx
                    LIVE_STATUS.current_streaming_text = current_chunk_translation
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
                                    translated_chunks_snapshot,
                                )
                        except Exception:
                            pass

                    # Real-time Streamlit UI rerun trigger
                    import time
                    now = time.time()
                    if not hasattr(LIVE_STATUS, '_last_rerun_time'):
                        LIVE_STATUS._last_rerun_time = 0
                    if now - LIVE_STATUS._last_rerun_time > 0.1 or is_finished:
                        LIVE_STATUS._last_rerun_time = now
                        try:
                            from streamlit.runtime import get_instance
                            runtime = get_instance()
                            session_info = runtime._session_mgr.get_active_session_info(ctx.session_id)
                            if session_info:
                                session_info.session.request_rerun(None)
                        except Exception:
                            pass

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
        from core.translator import clean_markdown
        temp_chunks[LIVE_STATUS.current_chunk_idx] = clean_markdown(LIVE_STATUS.current_streaming_text)
    
    full_text = "\n\n".join([c for c in temp_chunks if c])
    st.markdown(
        f'<div style="border: 1px solid #31333f; padding: 20px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 14px; height: 300px; overflow-y: auto;">{colorize_directives(full_text)}</div>',
        unsafe_allow_html=True
    )

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
                            st.info("⏳ 번역 진행 중")
                        elif has_translation:
                            st.success("✅ 번역 완료")
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
                                            translate_directives=translate_directives
                                        )
                                    else:
                                        prompt = build_translation_prompt(
                                            current_chunk=st.session_state.chunks[idx],
                                            prev_original=prev_orig,
                                            prev_translated=prev_trans,
                                            persona=st.session_state.persona,
                                            glossary=glossary_dict,
                                            is_srt=is_srt,
                                            translate_directives=translate_directives
                                        )
                                        
                                    def run_single_task(model, processor, prompt, chunk_idx, cancel_token, ctx):
                                        from core.translator import translate_one_chunk
                                        import threading
                                        add_script_run_ctx(threading.current_thread(), ctx)

                                        max_retries = 3
                                        clean_txt = None
                                        for retry in range(max_retries):
                                            current_temp = temperature
                                            current_penalty = repetition_penalty
                                            if retry > 0:
                                                current_temp = min(0.8, temperature + 0.15 * retry)
                                                current_penalty = repetition_penalty + 0.1 * retry
                                                LIVE_STATUS.single_streaming_text[chunk_idx] = f"[반복 루프 감지 - 재시도 {retry}/{max_retries-1}...]\n"

                                            def on_token(_token_text, current_text):
                                                LIVE_STATUS.single_streaming_text[chunk_idx] = current_text
                                                import time
                                                now = time.time()
                                                if not hasattr(LIVE_STATUS, '_last_rerun_time'):
                                                    LIVE_STATUS._last_rerun_time = 0
                                                if now - LIVE_STATUS._last_rerun_time > 0.1:
                                                    LIVE_STATUS._last_rerun_time = now
                                                    try:
                                                        from streamlit.runtime import get_instance
                                                        runtime = get_instance()
                                                        session_info = runtime._session_mgr.get_active_session_info(ctx.session_id)
                                                        if session_info:
                                                            session_info.session.request_rerun(None)
                                                    except Exception:
                                                        pass

                                            clean_txt = translate_one_chunk(
                                                model,
                                                processor,
                                                prompt,
                                                temp=current_temp,
                                                repetition_penalty=current_penalty,
                                                cancel_token=cancel_token,
                                                token_callback=on_token,
                                            )
                                            if clean_txt == "__REPETITION_ERROR__":
                                                if retry < max_retries - 1:
                                                    continue
                                                else:
                                                    clean_txt = None
                                                    break
                                            elif clean_txt is None:
                                                break
                                            else:
                                                break

                                        if clean_txt is None:
                                            return None

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
            st.session_state.translated_chunks,
        )
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
