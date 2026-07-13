def build_persona_section(persona: dict) -> str:
    persona_str = f"- 말투/어조: {persona.get('tone', '자연스러운 말투')}\n"
    persona_str += f"- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}\n"
    if persona.get("situation"):
        persona_str += f"- 배경 상황 및 스토리 맥락: {persona.get('situation')}\n"
    if persona.get("key_rules"):
        rules = "\n".join([f"  * {rule}" for rule in persona["key_rules"]])
        persona_str += f"- 주요 규칙:\n{rules}"
    return persona_str


def build_glossary_section(glossary: dict) -> str:
    if not glossary:
        return ""

    glossary_items = []
    for src, tgt in glossary.items():
        if src.strip() and tgt.strip():
            glossary_items.append(f"  * '{src}' -> '{tgt}'")

    if not glossary_items:
        return ""

    return "\n[용어집 번역 규칙 (반드시 준수)]\n" + "\n".join(glossary_items) + "\n"


def build_format_instruction(is_srt: bool, translate_directives: bool, file_name: str = "") -> str:
    is_vtt = file_name.lower().endswith(".vtt")
    is_lrc = file_name.lower().endswith(".lrc")

    if is_srt or is_vtt or is_lrc:
        file_format_name = "SRT/WebVTT 자막" if (is_srt or is_vtt) else "LRC 가사/대사"
        return f"""
[형식 규칙]
- 현재 번역할 대본은 {file_format_name} 형식에서 시간 정보를 간소화한 상태입니다.
- 각 블록 맨 앞에 표기된 블록 태그(예: [#1], [#2], [#WEBVTT] 등)는 절대로 수정하거나 번역하지 말고, 출력 결과에서도 동일한 위치에 그대로 유지하세요.
- 오직 블록 태그 뒷부분의 대사/텍스트 내용만 자연스러운 한국어로 번역하세요.
- 원본의 빈 줄 구조와 형식을 정확히 유지하여 출력하세요.
"""

    instruction = """
[형식 규칙]
- 대본의 타임스탬프(예: [00:12], 01:23)는 절대 수정하지 말고 원본 위치 그대로 유지하세요.
- 괄호 안에 들어있는 지시문(예: [whispering], (한숨), *giggles* 및 전각 기호 ［속삭임］, （한숨）, ＊소곤소곤＊)은 지시문 기호 형태(괄호 종류 등)를 그대로 유지하세요.
- 원본 대본의 행 단위 구조(라인 바이 라인)를 철저히 지키십시오. 절대 대본을 소설이나 줄글(예: '히로인이 한숨을 쉬며 말했다' 등)로 통합하여 문장 형태로 풀어서 쓰지 말고, 원본의 '화자: 대사' 구조를 그대로 유지해야 합니다.
"""
    if translate_directives:
        instruction += "- 괄호 내부의 지시문 내용은 한국어 감정/행동 묘사로 자연스럽게 번역하세요 (예: [whispering] -> [속삭임], (sighs) -> (한숨), ［whispering］ -> ［속삭임］).\n"
    else:
        instruction += "- 괄호 내부의 지시문 내용은 번역하지 말고 영문 또는 원문 단어 그대로 유지하세요 (예: [whispering] -> [whispering]).\n"
    return instruction


def build_context_section(prev_original: str, prev_translated: str) -> str:
    if not prev_original or not prev_translated:
        return ""

    prev_orig_lines = prev_original.splitlines()
    prev_trans_lines = prev_translated.splitlines()

    prev_orig_trimmed = "\n".join(prev_orig_lines[-3:])
    prev_trans_trimmed = "\n".join(prev_trans_lines[-3:])

    if len(prev_orig_lines) > 3:
        prev_orig_trimmed = "...\n" + prev_orig_trimmed
    if len(prev_trans_lines) > 3:
        prev_trans_trimmed = "...\n" + prev_trans_trimmed

    return f"""
[이전 번역 맥락 (참고용 - 직전 대사 3줄)]
---이전 원문---
{prev_orig_trimmed}
---이전 번역문---
{prev_trans_trimmed}
----------------
"""


def build_translation_prompt(
    current_chunk: str,
    prev_original: str,
    prev_translated: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool,
    file_name: str = "",
) -> str:
    persona_str = build_persona_section(persona)
    glossary_str = build_glossary_section(glossary)
    format_instruction = build_format_instruction(is_srt, translate_directives, file_name)
    context_str = build_context_section(prev_original, prev_translated)

    return f"""
당신은 성인용(NSFW) ASMR 상황극 및 대본 전문 한국어 번역가입니다.
주어진 페르소나와 이전 번역 맥락, 용어집 번역 규칙을 참고하여 다음 대본을 번역해 주세요.

[캐릭터 페르소나]
{persona_str}
{glossary_str}
{format_instruction}

[출력 형식 가이드라인 (중요 - 반드시 아래 출력 형식을 엄격히 준수하십시오)]
다른 해설, 인삿말, 혹은 대본 분석글은 일절 배제하고, 오직 [최종 번역 결과] 마커 아래에 대본 번역 본문만 출력하십시오.

[최종 번역 결과]
- 원본 대본의 행 단위 구조(라인 바이 라인) 및 줄바꿈 구조, 특수 문자, 화자 콜론 기호(: 또는 ：), 괄호 지시문 기호 형태를 그대로 완벽하게 유지하여 한국어로 번역하십시오.
- 절대 대본을 소설 서술형 문장(예: ~라고 속삭였다)으로 풀거나 합치지 말고, 대본 형식 그대로 번역하십시오.
- **[경고 - 절대 준수] 일본어 원문은 절대 출력에 포함하지 마십시오. 오직 번역된 한국어 텍스트만 한 줄씩 출력해야 합니다. 일본어 원문과 한국어 번역문을 위아래로 동시에 나열하는 행위는 절대로 금지됩니다.**

{context_str}
[번역할 대본]
{current_chunk}

[주의사항]
- 대본 번역 본문 이외의 어떠한 설명, 질문에 대한 답변, 프롬프트의 반복 출력도 허용되지 않습니다.
- 오직 번역이 완료된 대본 내용만 출력하세요.
"""


def build_retranslation_prompt(
    current_chunk: str,
    existing_translation: str,
    prev_original: str,
    prev_translated: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool,
    file_name: str = "",
) -> str:
    persona_str = build_persona_section(persona)
    glossary_str = build_glossary_section(glossary)
    format_instruction = build_format_instruction(is_srt, translate_directives, file_name)
    context_str = build_context_section(prev_original, prev_translated)

    return f"""
당신은 성인용(NSFW) ASMR 상황극 및 대본 전문 한국어 번역 교정가입니다.
주어진 페르소나와 기존 번역 초안, 용어집 번역 규칙을 참고하여 다음 대본의 번역을 보완 및 수정해 주세요.

[캐릭터 페르소나]
{persona_str}
{glossary_str}
{format_instruction}

[출력 형식 가이드라인 (중요 - 반드시 아래 출력 형식을 엄격히 준수하십시오)]
다른 해설, 인삿말, 혹은 대본 분석글은 일절 배제하고, 오직 [최종 번역 결과] 마커 아래에 수정 완료된 대본 번역 본문만 출력하십시오.

[최종 번역 결과]
- 원본 대본의 행 단위 구조(라인 바이 라인) 및 줄바꿈 구조, 특수 문자, 화자 콜론 기호(: 또는 ：), 괄호 지시문 기호 형태를 그대로 완벽하게 유지하여 한국어로 번역 및 교정하십시오.
- 절대 대본을 소설 서술형 문장(예: ~라고 속삭였다)으로 풀거나 합치지 말고, 대본 형식 그대로 번역하십시오.
- **[경고 - 절대 준수] 일본어 원문은 절대 출력에 포함하지 마십시오. 오직 번역된 한국어 텍스트만 한 줄씩 출력해야 합니다. 일본어 원문과 한국어 번역문을 위아래로 동시에 나열하는 행위는 절대로 금지됩니다.**

{context_str}

[기존 번역 초안 (참고용 - 말투 및 오역 수정 대상)]
{existing_translation}

[수정할 원문 대본]
{current_chunk}

[주의사항]
- 기존 번역 초안에서 잘못 지정된 호칭이나 페르소나에 맞지 않는 말투를 발견하면, [캐릭터 페르소나] 및 [용어집 번역 규칙]에 따라 철저히 수정해 주세요.
- 기존 번역의 장점을 살리되, 어조 규칙 및 지정어 규칙이 위배된 부분을 정교하게 보정하세요.
- 대본 번역 본문 이외의 어떠한 설명, 질문에 대한 답변, 프롬프트의 반복 출력도 허용되지 않습니다.
- 오직 번역이 완료된 대본 내용만 출력하세요.
"""
