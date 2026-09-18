import re

from core.subtitle_utils import (
    parse_lrc_line,
    parse_srt_block,
    postprocess_subtitle_chunk,
    preprocess_subtitle_chunk,
)
from core.translation_prompts import build_retranslation_prompt, build_translation_prompt, prompt_to_messages


def extract_final_translation(text: str) -> str:
    """
    Extracts only the final translation part from the VLM output by stripping the thinking process.
    """
    if not text:
        return ""

    # Strip <think>...</think> block if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip unclosed <think> block during streaming
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)

    markers = ["[최종 번역 결과]", "[최종 번역 대본]", "[최종 번역]", "[번역 결과]", "[최종 번역본]"]
    for marker in markers:
        if marker in text:
            parts = text.split(marker)
            return parts[-1].strip()
            
    # If no final marker is present yet, but it contains "[대본 분석]" or "[대본 분석", hide it during streaming
    if "[대본 분석]" in text or "[대본 분석" in text or "요소 분류" in text or "번역 계획" in text:
        return ""
        
    return text.strip()


from core.document import (
    extract_text_from_pdf,
    clean_pdf_linebreaks,
    clean_markdown,
    chunk_srt,
    chunk_text,
)


def stream_prompt(
    model,
    processor,
    prompt: str,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    max_tokens: int = 1500,
    cancel_token: dict = None,
    token_callback=None,
) -> str | None:
    try:
        from core.openai_compat import OpenAICompatClient
        if isinstance(model, OpenAICompatClient):
            messages = prompt_to_messages(prompt)
            generator = model.generate_stream(messages, temp=temp, max_tokens=max_tokens)
            output = ""
            for response in generator:
                if cancel_token and cancel_token.get("cancel"):
                    return None
                output += response.text
                if token_callback:
                    token_callback(response.text, output)
            return clean_markdown(output)
    except ImportError:
        pass
    raise RuntimeError("8502 웹 서비스는 OpenAI 호환 API 서버에만 연결할 수 있습니다.")


def translate_one_chunk(
    model,
    processor,
    prompt: str,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    cancel_token: dict = None,
    token_callback=None,
) -> str | None:
    try:
        from core.openai_compat import OpenAICompatClient
        is_or = isinstance(model, OpenAICompatClient)
    except ImportError:
        is_or = False

    return stream_prompt(
        model,
        processor,
        prompt,
        temp=temp,
        repetition_penalty=repetition_penalty,
        max_tokens=3000 if is_or else 1500,
        cancel_token=cancel_token,
        token_callback=token_callback,
    )


def translate_script(
    model,
    processor,
    script: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool,
    chunk_size: int = 400,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    existing_translations: list[str] = None,
    cancel_token: dict = None,
    progress_callback=None,
    file_name: str = ""
) -> str:
    """
    대본을 청크 단위로 분할하여 슬라이딩 윈도우 방식으로 번역을 진행하며 진행 상황을 콜백으로 호출합니다.
    이미 번역된 청크(existing_translations)는 건너뛰며 흐름을 이어갑니다.
    중단 요청(cancel_token)이 감지되면 즉시 중지합니다.
    """
    is_subtitle = is_srt or file_name.endswith(".vtt") or file_name.endswith(".lrc")
    is_api_backend = False
    try:
        from core.openai_compat import OpenAICompatClient
        if isinstance(model, OpenAICompatClient):
            is_api_backend = True
    except ImportError:
        pass

    if is_srt or file_name.endswith(".vtt"):
        chunks = chunk_srt(script, target_chunk_size=chunk_size)
    else:
        chunks = chunk_text(script, chunk_size=chunk_size)
        
    translated_chunks = []
    total_chunks = len(chunks)
    
    prev_original = ""
    prev_translated = ""
    sub_index = 1
    
    for idx, chunk in enumerate(chunks):
        # 중단 토큰 확인
        if cancel_token and cancel_token.get("cancel"):
            break

        if is_subtitle:
            simplified_chunk, headers_map, next_sub_index = preprocess_subtitle_chunk(chunk, sub_index, file_name)
            sub_index = next_sub_index
        else:
            simplified_chunk = chunk
            headers_map = {}

        # 이미 번역된 결과가 존재하는 청크는 LLM 호출을 건너뛰고 컨텍스트만 업데이트
        if existing_translations and idx < len(existing_translations) and isinstance(existing_translations[idx], str) and existing_translations[idx].strip():
            chunk_translation_reconstructed = existing_translations[idx]
            translated_chunks.append(chunk_translation_reconstructed)
            prev_original = chunk
            prev_translated = chunk_translation_reconstructed
            if progress_callback:
                # UI 갱신을 위해 콜백 전달 (이미 번역 완료됨 표시)
                progress_callback("", idx, total_chunks, chunk_translation_reconstructed, True)
            continue

        if is_subtitle:
            prev_orig_simplified, _, _ = preprocess_subtitle_chunk(prev_original, 1, file_name)
            prev_trans_simplified, _, _ = preprocess_subtitle_chunk(prev_translated, 1, file_name)
        else:
            prev_orig_simplified = prev_original
            prev_trans_simplified = prev_translated

        prompt = build_translation_prompt(
            current_chunk=simplified_chunk,
            prev_original=prev_orig_simplified,
            prev_translated=prev_trans_simplified,
            persona=persona,
            glossary=glossary,
            is_srt=is_srt,
            translate_directives=translate_directives,
            file_name=file_name
        )
        
        def on_token(token_text, chunk_translation):
            if progress_callback:
                progress_callback(token_text, idx, total_chunks, chunk_translation, False)

        chunk_translation_clean = translate_one_chunk(
            model,
            processor,
            prompt,
            temp=temp,
            repetition_penalty=repetition_penalty,
            cancel_token=cancel_token,
            token_callback=on_token,
        )

        if chunk_translation_clean is None:
            if cancel_token and cancel_token.get("cancel"):
                break
            chunk_translation_clean = f"[번역 실패 - 원문 대체] {chunk}"
            chunk_translation_reconstructed = chunk_translation_clean
        else:
            chunk_translation_clean = extract_final_translation(chunk_translation_clean)
            if is_subtitle:
                chunk_translation_reconstructed = postprocess_subtitle_chunk(chunk_translation_clean, headers_map, file_name)
            else:
                chunk_translation_reconstructed = chunk_translation_clean

        translated_chunks.append(chunk_translation_reconstructed)
        
        prev_original = chunk
        prev_translated = chunk_translation_reconstructed
        
        if progress_callback:
            progress_callback("", idx, total_chunks, chunk_translation_reconstructed, True)
        
    is_vtt = file_name.lower().endswith(".vtt")
    if is_srt or is_vtt:
        return "\n\n".join(translated_chunks)
    else:
        return "\n".join(translated_chunks)
