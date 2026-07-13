import streamlit as st
import os
import re
from core.utils import get_backup_dir, list_saved_images, decode_text, natural_sort_key
from core.progress_store import get_image_note_path, load_image_note, BACKUP_ROOT

def render_tab_script():
    st.header("대본 및 메타데이터 입력")
    script_chars = len(st.session_state.original_script.strip())
    image_count = len(st.session_state.temp_image_paths)
    glossary_count = len([item for item in st.session_state.glossary_data if item.get("원어 (Source)")])
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    col_stat1.metric("대본 글자 수", f"{script_chars:,}")
    col_stat2.metric("청크 수", f"{len(st.session_state.chunks):,}")
    col_stat3.metric("소개 이미지", f"{image_count:,}")
    col_stat4.metric("적용 용어", f"{glossary_count:,}")

    with st.container(border=True):
        st.subheader("작품 기본 정보")
        # PDF 줄바꿈 보정용 체크박스 (공용 옵션)
        clean_pdf_breaks = st.checkbox(
            "PDF 추출 시 줄바꿈 자동 보정",
            value=True,
            help="세로쓰기 등으로 인해 잘게 조각난 줄바꿈을 지능적으로 병합하여 번역 품질을 높입니다."
        )

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            # Meta description
            st.session_state.metadata_text = st.text_area(
                "ASMR 메타데이터 (소개글, 태그 등)",
                value=st.session_state.metadata_text,
                placeholder="소개글이나 태그 등을 입력해 주세요.",
                height=120
            )
        with col_m2:
            # RJ Code manually input
            st.session_state.rj_code = st.text_input(
                "DLsite 작품 RJ 코드 (선택사항, 예: RJ123456)",
                value=st.session_state.rj_code,
                help="프로젝트 백업 폴더를 RJ 번호 단위로 관리하여 다른 파일명 대본들과 꼬이지 않도록 분류합니다."
            )
            st.caption("RJ 코드를 입력하면 백업 폴더가 해당 코드로 분리되어 프로젝트 관리가 용이해집니다.")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("수동 파일 업로드")
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            # File Uploader
            uploaded_files = st.file_uploader("대본 파일 업로드 (.txt, .srt, .pdf, .vtt, .lrc)", type=["txt", "srt", "pdf", "vtt", "lrc"], accept_multiple_files=True)
        with col_u2:
            # Image Uploader
            uploaded_images = st.file_uploader(
                "ASMR 소개 이미지 업로드 (선택사항)",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True
            )

    # 소개 이미지 저장 및 세션 스테이트 반영
    if uploaded_images:
        project_dir = get_backup_dir(st.session_state.file_name, create=True)
        images_dir = os.path.join(project_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        temp_image_paths = []
        sorted_uploaded_images = sorted(uploaded_images, key=lambda x: natural_sort_key(x.name))
        for idx, img_file in enumerate(sorted_uploaded_images):
            raw_image = img_file.read()
            import hashlib

            image_hash = hashlib.sha256(raw_image).hexdigest()[:12]
            image_stem = os.path.splitext(img_file.name)[0]
            safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in image_stem)
            img_path = os.path.join(images_dir, f"img_{idx}_{safe_stem}_{image_hash}.jpg")
            try:
                from PIL import Image
                import io

                image = Image.open(io.BytesIO(raw_image)).convert("RGB")
                image.thumbnail((768, 768))
                image.save(img_path, format="JPEG", quality=82, optimize=True)
            except Exception:
                with open(img_path, "wb") as f:
                    f.write(raw_image)
            temp_image_paths.append(img_path)

        st.session_state.temp_image_paths = temp_image_paths

        # 이미지 미리보기 레이아웃
        st.markdown("**업로드된 소개 이미지 미리보기**")
        max_cols_per_row = 4
        num_images = len(uploaded_images)
        for i in range(0, num_images, max_cols_per_row):
            row_images = uploaded_images[i:i + max_cols_per_row]
            cols = st.columns(len(row_images))
            for idx, img_file in enumerate(row_images):
                cols[idx].image(img_file, caption=img_file.name, width="stretch")
    elif st.session_state.temp_image_paths:
        # Filter out non-existent image paths to prevent crashes
        st.session_state.temp_image_paths = [p for p in st.session_state.temp_image_paths if os.path.exists(p)]
        if st.session_state.temp_image_paths:
            # 이미 백업 폴더에 저장되어 있는 이미지 표시
            st.markdown("**불러온 백업 소개 이미지 미리보기**")
            max_cols_per_row = 4
            num_images = len(st.session_state.temp_image_paths)
            for i in range(0, num_images, max_cols_per_row):
                row_paths = st.session_state.temp_image_paths[i:i + max_cols_per_row]
                cols = st.columns(len(row_paths))
                for idx, img_path in enumerate(row_paths):
                    cols[idx].image(img_path, caption=os.path.basename(img_path), width="stretch")



    if uploaded_files:
        if st.button("업로드된 대본 파일 파싱 및 불러오기", type="primary", width="stretch"):
            sorted_files = sorted(uploaded_files, key=lambda f: natural_sort_key(f.name))
            combined_text = []
            srt_count = sum(1 for f in sorted_files if f.name.endswith('.srt'))
            vtt_count = sum(1 for f in sorted_files if f.name.endswith('.vtt'))
            lrc_count = sum(1 for f in sorted_files if f.name.endswith('.lrc'))
            is_srt_mode = srt_count == len(sorted_files)
            is_vtt_mode = vtt_count == len(sorted_files)
            is_lrc_mode = lrc_count == len(sorted_files)
            is_subtitle_mode = is_srt_mode or is_vtt_mode

            for idx, file in enumerate(sorted_files):
                file_name = file.name
                if file_name.lower().endswith('.pdf'):
                    from core.document import extract_text_from_pdf, clean_pdf_linebreaks
                    extracted_text = extract_text_from_pdf(file)
                    if clean_pdf_breaks:
                        extracted_text = clean_pdf_linebreaks(extracted_text)
                else:
                    raw_data = file.read()
                    extracted_text = decode_text(raw_data)

                # 여러 대본을 합칠 때 경계 마크 추가
                if len(sorted_files) > 1:
                    if is_subtitle_mode:
                        combined_text.append(extracted_text.strip())
                    else:
                        track_name = f'Track {idx + 1}'
                        num_match = re.search(r'\d+', file_name)
                        if num_match:
                            track_name = f'Track {num_match.group(0)}'
                        combined_text.append(f'[{track_name} ({file_name})]\n{extracted_text.strip()}')
                else:
                    combined_text.append(extracted_text.strip())

            sep = '\n\n' if is_subtitle_mode else '\n\n\n'
            st.session_state.original_script = sep.join(combined_text)

            # RJ 코드 자동 추출 반영
            from core.progress_store import extract_rj_code
            rj = extract_rj_code(st.session_state.file_name)
            if not rj:
                rj = extract_rj_code(st.session_state.original_script)
            if not rj:
                rj = extract_rj_code(st.session_state.metadata_text)
            if rj:
                st.session_state.rj_code = rj

            if len(sorted_files) == 1:
                st.session_state.file_name = sorted_files[0].name
            else:
                first_name, _ = os.path.splitext(sorted_files[0].name)
                ext = '.srt' if is_srt_mode else ('.vtt' if is_vtt_mode else ('.lrc' if is_lrc_mode else '.txt'))
                st.session_state.file_name = f'{first_name}_외_{len(sorted_files)-1}개' + ext

            # Save progress and persona immediately so it registers as a project, and download thumbnail
            from core.progress_store import save_progress, save_persona_backup, get_backup_dir
            if is_subtitle_mode:
                from core.document import chunk_srt
                st.session_state.chunks = chunk_srt(st.session_state.original_script)
            else:
                from core.document import chunk_text
                st.session_state.chunks = chunk_text(st.session_state.original_script)
            
            st.session_state.translated_chunks = [""] * len(st.session_state.chunks)
            save_progress(st.session_state.file_name, st.session_state.chunks, st.session_state.translated_chunks)
            save_persona_backup(st.session_state.file_name, {}, [])
            
            # Download thumbnail
            if st.session_state.rj_code:
                project_dir = get_backup_dir(st.session_state.file_name, create=True)
                from core.progress_store import download_dlsite_thumbnail
                download_dlsite_thumbnail(st.session_state.rj_code, project_dir)

            # 마스터 단어장에서 용어 자동 매칭 (Scan & 선탑재)
            from core.progress_store import load_master_glossary
            master = load_master_glossary()
            matched_glossary = []
            script_lower = st.session_state.original_script.lower()
            for item in master:
                src = item.get("원어 (Source)", "").strip()
                tgt = item.get("번역어 (Target)", "").strip()
                if src and src.lower() in script_lower:
                    matched_glossary.append({
                        "원어 (Source)": src,
                        "번역어 (Target)": tgt,
                        "설명/뉘앙스 (Context)": item.get("설명/뉘앙스 (Context)", "")
                    })
            if matched_glossary:
                # Merge matched glossary into current glossary_data without duplicates
                current_keys = {str(item.get("원어 (Source)", "")).strip() for item in st.session_state.glossary_data if item.get("원어 (Source)")}
                for item in matched_glossary:
                    if item["원어 (Source)"] not in current_keys:
                        st.session_state.glossary_data.append(item)
                st.toast(f"마스터 단어장에서 {len(matched_glossary)}개 용어를 자동으로 감지해 탑재했습니다!")

            st.success(f"총 {len(sorted_files)}개 대본 파일에서 텍스트를 추출하고 병합했습니다! ({len(st.session_state.original_script)} 자)")
            st.rerun()

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("대본 본문")
        # Text input area
        st.session_state.original_script = st.text_area(
            "대본 원문 내용",
            value=st.session_state.original_script,
            placeholder="번역할 대본 본문을 직접 붙여넣거나 파일을 업로드해 주세요.",
            height=350,
            label_visibility="collapsed"
        )
        st.caption(f"현재 본문 {len(st.session_state.original_script.strip()):,}자 · 사이드바 청크 크기 기준 {len(st.session_state.chunks):,}개 청크로 번역됩니다.")

    # 수동 줄바꿈 정제 실행 버튼
    if st.button(
        "수동 줄바꿈 정제 실행",
        help="현재 본문 내의 과도한 줄바꿈을 문장 단위로 병합합니다. (세로쓰기 시나리오를 직접 붙여넣었을 때 유용합니다)",
        disabled=not st.session_state.original_script.strip()
    ):
        if st.session_state.original_script.strip():
            from core.document import clean_pdf_linebreaks
            cleaned = clean_pdf_linebreaks(st.session_state.original_script)
            st.session_state.original_script = cleaned
            st.success("대본 본문의 줄바꿈 정제를 완료했습니다!")
            st.rerun()
