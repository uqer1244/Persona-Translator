from core.translator import clean_markdown

def refine_translation(model, processor, translated_text: str, persona: dict) -> str:
    """
    1차 번역이 완료된 텍스트를 검증 및 다듬습니다. 말투 일관성 및 깨진 포맷(괄호)을 복구합니다.
    """
    # GPU 스트림 스레드 충돌 방지를 위해 함수 내부에서 로컬 임포트 수행
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    prompt = f"""
당신은 대본 번역의 완성도를 높이는 교정 에디터입니다.
다음은 1차 번역이 완료된 ASMR 대본과, 적용해야 하는 페르소나 정보입니다.
아래의 [교정 기준]에 맞춰 번역문을 다듬어 출력해주세요.

[캐릭터 페르소나]
- 말투/어조: {persona.get('tone', '일관된 말투')}
- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}

[교정 기준]
1. 말투가 갑자기 존댓말에서 반말로, 혹은 반말에서 존댓말로 바뀌는 등의 어조 불일치를 교정하고 페르소나 어조로 통일하세요.
2. 괄호가 중간에 열려있고 닫히지 않은 경우 등 (예: "[whispering", "(한숨") 포맷 오류를 정상적으로 닫아주세요.
3. 지시문 포맷(괄호, 타임스탬프)은 그대로 유지하고 텍스트만 올바르게 수정하세요.
4. 오직 교정된 최종 대본만 출력해야 하며, 설명이나 인사말은 포함하지 마세요.

[교정할 번역 대본]
{translated_text}
"""
    messages = [{"role": "user", "content": prompt}]
    formatted_prompt = apply_chat_template(
        processor,
        model.config,
        messages,
        num_images=0,
        num_audios=0
    )
    
    # mlx-vlm generate
    refined_output_obj = generate(
        model,
        processor,
        prompt=formatted_prompt,
        temp=0.2,
        max_tokens=2000,
        kv_bits=3.5,
        kv_quant_scheme="turboquant",
        repetition_penalty=1.1,
        repetition_context_size=100
    )
    return clean_markdown(refined_output_obj.text)
