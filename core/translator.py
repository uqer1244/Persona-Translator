import re
from typing import Optional

from core.subtitle_utils import (
    parse_lrc_line,
    parse_srt_block,
    postprocess_subtitle_chunk,
    preprocess_subtitle_chunk,
)
from core.translation_prompts import build_retranslation_prompt, build_translation_prompt


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
    chunk_text
)


class PromptCacheManager:
    """
    MLX KVCache와 토큰 히스토리를 정렬하여 중복 인코딩을 방지하는 캐시 관리 클래스
    """
    def __init__(self, model):
        from mlx_lm.utils import make_prompt_cache
        self.prompt_cache = make_prompt_cache(model)
        self.cached_tokens = []

    def get_incremental_tokens(self, formatted_prompt: str, processor) -> list[int]:
        if hasattr(processor, "tokenizer"):
            tokenizer = processor.tokenizer
        else:
            tokenizer = processor
            
        all_tokens = tokenizer.encode(formatted_prompt)
        
        # 이전 캐싱된 토큰들과 매칭되는 공통 접두사 확인
        common_len = 0
        for i in range(min(len(self.cached_tokens), len(all_tokens))):
            if self.cached_tokens[i] == all_tokens[i]:
                common_len += 1
            else:
                break
                
        # 매칭 일치도가 너무 낮으면(예: 번역 맥락이 리셋되거나 수정 등) 캐시 리셋
        if common_len < len(self.cached_tokens) * 0.9:
            self.prompt_cache.reset()
            self.cached_tokens = []
            common_len = 0
            
        # 역전 현상이 생겨도 리셋
        if common_len < len(self.cached_tokens):
            self.prompt_cache.reset()
            self.cached_tokens = all_tokens
            return all_tokens
            
        new_tokens = all_tokens[common_len:]
        self.cached_tokens.extend(new_tokens)
        return new_tokens

def stream_prompt(
    model,
    processor,
    prompt: str,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    max_tokens: int = 1500,
    cancel_token: dict = None,
    token_callback=None,
    prompt_cache_mgr: Optional[PromptCacheManager] = None,
) -> str | None:
    from core.utils import has_repetition, strip_repetition

    try:
        from core.openrouter import OpenRouterClient
        if isinstance(model, OpenRouterClient):
            messages = [{"role": "user", "content": prompt}]
            generator = model.generate_stream(messages, temp=temp, max_tokens=max_tokens)
            output = ""
            for response in generator:
                if cancel_token and cancel_token.get("cancel"):
                    return None
                output += response.text
                if token_callback:
                    token_callback(response.text, output)
                    
                if has_repetition(output):
                    print(f"[TRANSLATION WARNING] Repetition loop detected! Stopping stream.")
                    cleaned_output = strip_repetition(output)
                    raise ValueError(f"RepetitionLoopDetected:{cleaned_output}")
            return clean_markdown(output)
    except ImportError:
        pass

    # Check if the model is a VLM model
    is_vlm_model = hasattr(processor, "image_processor")

    if is_vlm_model:
        from mlx_vlm.generate import stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        messages = [{"role": "user", "content": prompt}]
        formatted_prompt = apply_chat_template(
            processor,
            model.config,
            messages,
            num_images=0,
            num_audios=0
        )
    else:
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler, make_logits_processors
        # Manually format ChatML with prefilled assistant response to steer directly to the final translation
        formatted_prompt = (
            "<|im_start|>system\n당신은 성인용(NSFW) ASMR 상황극 및 대본 전문 한국어 번역 교정가입니다. 생각(<think>)이나 분석 과정, 설명은 절대 출력하지 마십시오. 곧바로 [최종 번역 결과]를 출력하십시오.<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n[최종 번역 결과]\n"
        )

    output = ""
    if is_vlm_model:
        generator = stream_generate(
            model,
            processor,
            prompt=formatted_prompt,
            temp=temp,
            max_tokens=max_tokens,
            repetition_penalty=repetition_penalty,
            repetition_context_size=100,
            seed=42,
        )
    else:
        import mlx.core as mx
        if prompt_cache_mgr is not None:
            incremental_tokens = prompt_cache_mgr.get_incremental_tokens(formatted_prompt, processor)
            input_tokens = mx.array(incremental_tokens)
            prompt_cache_state = prompt_cache_mgr.prompt_cache
        else:
            input_tokens = formatted_prompt
            prompt_cache_state = None

        sampler = make_sampler(temp=temp)
        logits_processors = make_logits_processors(
            repetition_penalty=repetition_penalty,
            repetition_context_size=100
        )
        generator = stream_generate(
            model,
            processor,
            prompt=input_tokens,
            max_tokens=max_tokens,
            sampler=sampler,
            logits_processors=logits_processors,
            prompt_cache=prompt_cache_state,
        )

    for response in generator:
        if cancel_token and cancel_token.get("cancel"):
            return None
        output += response.text
        if token_callback:
            token_callback(response.text, output)
            
        if prompt_cache_mgr is not None and not is_vlm_model:
            if hasattr(response, "token"):
                prompt_cache_mgr.cached_tokens.append(response.token)
            
        if has_repetition(output):
            print(f"[TRANSLATION WARNING] Repetition loop detected! Stopping stream.")
            cleaned_output = strip_repetition(output)
            raise ValueError(f"RepetitionLoopDetected:{cleaned_output}")

    return clean_markdown(output)


def translate_one_chunk(
    model,
    processor,
    prompt: str,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    cancel_token: dict = None,
    token_callback=None,
    prompt_cache_mgr: Optional[PromptCacheManager] = None,
) -> str | tuple[str, str] | None:
    try:
        from core.openrouter import OpenRouterClient
        is_or = isinstance(model, OpenRouterClient)
    except ImportError:
        is_or = False

    try:
        result = stream_prompt(
            model,
            processor,
            prompt,
            temp=temp,
            repetition_penalty=repetition_penalty,
            max_tokens=3000 if is_or else 1500,
            cancel_token=cancel_token,
            token_callback=token_callback,
            prompt_cache_mgr=prompt_cache_mgr,
        )
    except ValueError as e:
        err_msg = str(e)
        if err_msg.startswith("RepetitionLoopDetected:"):
            clean_part = err_msg[len("RepetitionLoopDetected:"):]
            return ("__REPETITION_ERROR__", clean_part)
        elif err_msg == "RepetitionLoopDetected":
            return "__REPETITION_ERROR__"
        raise e

    import mlx.core as mx
    import gc
    mx.clear_cache()
    gc.collect()
    return result


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
    is_vlm_model = hasattr(processor, "image_processor")
    
    is_openrouter = False
    try:
        from core.openrouter import OpenRouterClient
        if isinstance(model, OpenRouterClient):
            is_openrouter = True
    except ImportError:
        pass
        
    prompt_cache_mgr = None
    if not is_vlm_model and not is_openrouter:
        prompt_cache_mgr = PromptCacheManager(model)

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
        
        max_retries = 3
        chunk_translation_clean = None
        best_fallback_text = ""
        
        for retry in range(max_retries):
            current_temp = temp
            current_penalty = repetition_penalty
            if retry > 0:
                current_temp = min(0.8, temp + 0.15 * retry)
                current_penalty = repetition_penalty + 0.1 * retry
                if progress_callback:
                    progress_callback(f"\n[반복 루프 감지 - 재시도 {retry}/{max_retries-1}...]\n", idx, total_chunks, "", False)

            def on_token(token_text, chunk_translation):
                if progress_callback:
                    progress_callback(token_text, idx, total_chunks, chunk_translation, False)

            res = translate_one_chunk(
                model,
                processor,
                prompt,
                temp=current_temp,
                repetition_penalty=current_penalty,
                cancel_token=cancel_token,
                token_callback=on_token,
                prompt_cache_mgr=prompt_cache_mgr,
            )

            if isinstance(res, tuple) and res[0] == "__REPETITION_ERROR__":
                clean_part = res[1]
                if len(clean_part) > len(best_fallback_text):
                    best_fallback_text = clean_part
                
                if retry < max_retries - 1:
                    continue
                else:
                    chunk_translation_clean = clean_markdown(best_fallback_text) if best_fallback_text.strip() else None
                    break
            elif res == "__REPETITION_ERROR__":
                if retry < max_retries - 1:
                    continue
                else:
                    chunk_translation_clean = None
                    break
            elif res is None:
                # Cancelled
                chunk_translation_clean = None
                break
            else:
                chunk_translation_clean = res
                break

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
