from core.document import chunk_text, clean_markdown
from core.model_manager import clear_mlx_cache as _clear_mlx_cache


def _refine_chunk(model, processor, translated_text: str, persona: dict, chunk_idx: int, total_chunks: int) -> str:
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    prompt = f"""
당신은 대본 번역의 완성도를 높이는 교정 에디터입니다.
아래 번역 청크만 교정하세요. 전체 대본 중 {chunk_idx + 1}/{total_chunks}번째 청크입니다.

[캐릭터 페르소나]
- 말투/어조: {persona.get('tone', '일관된 말투')}
- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}

[교정 기준]
1. 말투가 갑자기 존댓말에서 반말로, 혹은 반말에서 존댓말로 바뀌는 어조 불일치를 교정하세요.
2. 괄호가 중간에 열려있고 닫히지 않은 경우 등 포맷 오류를 정상적으로 닫아주세요.
3. 지시문 포맷(괄호, 타임스탬프)은 그대로 유지하고 텍스트만 올바르게 수정하세요.
4. 앞뒤 청크에 대한 해설, 인사말, 변경 설명 없이 교정된 청크 텍스트만 출력하세요.

[교정할 번역 청크]
{translated_text}
"""
    messages = [{"role": "user", "content": prompt}]
    formatted_prompt = apply_chat_template(
        processor,
        model.config,
        messages,
        num_images=0,
        num_audios=0,
    )

    try:
        refined_output_obj = generate(
            model,
            processor,
            prompt=formatted_prompt,
            temp=0.2,
            max_tokens=600,
            kv_bits=3.5,
            kv_quant_scheme="turboquant",
            repetition_penalty=1.1,
            repetition_context_size=100,
            seed=42,
        )
        return clean_markdown(refined_output_obj.text)
    finally:
        _clear_mlx_cache()


def refine_translation(model, processor, translated_text: str, persona: dict, chunks: list[str] | None = None) -> str:
    """
    번역 결과를 청크 단위로 교정합니다.
    전체 대본을 한 번에 넣지 않아 Metal/KV cache 피크를 낮춥니다.
    """
    source_chunks = [chunk for chunk in (chunks or []) if chunk and chunk.strip()]
    if not source_chunks:
        source_chunks = chunk_text(translated_text, chunk_size=700)

    refine_units = []
    for chunk in source_chunks:
        if len(chunk) <= 600:
            refine_units.append(chunk)
            continue
        for part_start in range(0, len(chunk), 600):
            refine_units.append(chunk[part_start:part_start + 600])

    total_chunks = len(refine_units)
    refined_chunks = []
    for idx, chunk in enumerate(refine_units):
        refined_chunks.append(_refine_chunk(model, processor, chunk, persona, idx, total_chunks))

    return "\n\n".join(refined_chunks)
