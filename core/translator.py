import re
from pypdf import PdfReader


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


def parse_srt_block(block: str):
    lines = block.strip().split("\n")
    timecode_idx = -1
    for i, line in enumerate(lines):
        if "-->" in line:
            timecode_idx = i
            break
            
    if timecode_idx == -1:
        return None, block
        
    header_lines = lines[:timecode_idx+1]
    dialog_lines = lines[timecode_idx+1:]
    
    header = "\n".join(header_lines)
    dialog = "\n".join(dialog_lines)
    return header, dialog


def parse_lrc_line(line: str):
    match = re.match(r'^(\[\d{2}:\d{2}[:\.]\d{2,3}\])(.*)', line.strip())
    if match:
        return match.group(1), match.group(2)
    return None, line


def preprocess_subtitle_chunk(chunk_text: str, start_index: int = 1, file_name: str = "") -> tuple[str, dict, int]:
    is_vtt = file_name.lower().endswith(".vtt") or "WEBVTT" in chunk_text
    is_srt = file_name.lower().endswith(".srt") or "-->" in chunk_text
    is_lrc = file_name.lower().endswith(".lrc") or (not is_srt and not is_vtt and re.search(r'^\[\d{2}:\d{2}', chunk_text, re.MULTILINE))

    headers_map = {}
    simplified_blocks = []
    current_idx = start_index

    if is_srt or is_vtt:
        chunk_text = chunk_text.replace("\r\n", "\n")
        raw_blocks = chunk_text.split("\n\n")
        
        for block in raw_blocks:
            if not block.strip():
                continue
            
            if block.strip() == "WEBVTT":
                headers_map["WEBVTT"] = "WEBVTT"
                simplified_blocks.append("[#WEBVTT]")
                continue
                
            header, dialog = parse_srt_block(block)
            if header:
                headers_map[str(current_idx)] = header
                simplified_blocks.append(f"[#{current_idx}] {dialog}")
                current_idx += 1
            else:
                simplified_blocks.append(dialog)
                
        simplified_text = "\n\n".join(simplified_blocks)
        
    elif is_lrc:
        chunk_text = chunk_text.replace("\r\n", "\n")
        lines = chunk_text.split("\n")
        
        for line in lines:
            if not line.strip():
                simplified_blocks.append("")
                continue
            header, dialog = parse_lrc_line(line)
            if header:
                headers_map[str(current_idx)] = header
                simplified_blocks.append(f"[#{current_idx}] {dialog}")
                current_idx += 1
            else:
                simplified_blocks.append(line)
                
        simplified_text = "\n".join(simplified_blocks)
        
    else:
        simplified_text = chunk_text

    return simplified_text, headers_map, current_idx


def postprocess_subtitle_chunk(llm_output: str, headers_map: dict, file_name: str = "") -> str:
    if not headers_map:
        return llm_output

    is_vtt = file_name.lower().endswith(".vtt")
    is_lrc = file_name.lower().endswith(".lrc")

    pattern = re.compile(r'\[#(\w+)\]\s*(.*?)(?=\[#\w+\]|$)', re.DOTALL)
    matches = pattern.findall(llm_output)

    reconstructed_blocks = []
    matched_indices = set()

    for idx_str, text in matches:
        idx_str = idx_str.strip()
        text = text.strip()
        
        if idx_str == "WEBVTT":
            reconstructed_blocks.append("WEBVTT")
            matched_indices.add("WEBVTT")
            continue
            
        if idx_str in headers_map:
            header = headers_map[idx_str]
            if is_lrc:
                reconstructed_blocks.append(f"{header}{text}")
            else:
                reconstructed_blocks.append(f"{header}\n{text}")
            matched_indices.add(idx_str)

    # Sequential mapping fallback if tags are missing or incorrect
    if len(matched_indices) < len(headers_map):
        cleaned_text = re.sub(r'\[#\w+\]', '', llm_output).strip()
        
        if is_lrc:
            llm_blocks = [b.strip() for b in cleaned_text.split("\n") if b.strip()]
        else:
            llm_blocks = [b.strip() for b in cleaned_text.split("\n\n") if b.strip()]
            
        reconstructed_blocks = []
        sorted_keys = sorted([k for k in headers_map.keys() if k != "WEBVTT"], key=lambda x: int(x))
        if "WEBVTT" in headers_map:
            reconstructed_blocks.append("WEBVTT")
            
        for i, key in enumerate(sorted_keys):
            header = headers_map[key]
            trans_block = llm_blocks[i] if i < len(llm_blocks) else ""
            if is_lrc:
                reconstructed_blocks.append(f"{header}{trans_block}")
            else:
                reconstructed_blocks.append(f"{header}\n{trans_block}")
                
    if is_lrc:
        return "\n".join(reconstructed_blocks)
    else:
        return "\n\n".join(reconstructed_blocks)


from core.document import (
    extract_text_from_pdf,
    clean_pdf_linebreaks,
    clean_markdown,
    chunk_srt,
    chunk_text
)

def build_translation_prompt(
    current_chunk: str,
    prev_original: str,
    prev_translated: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool,
    file_name: str = ""
) -> str:
    # 1. 페르소나 제약 사항 구성
    persona_str = f"- 말투/어조: {persona.get('tone', '자연스러운 말투')}\n"
    persona_str += f"- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}\n"
    if persona.get("situation"):
        persona_str += f"- 배경 상황 및 스토리 맥락: {persona.get('situation')}\n"
    if persona.get("key_rules"):
        rules = "\n".join([f"  * {rule}" for rule in persona["key_rules"]])
        persona_str += f"- 주요 규칙:\n{rules}"
        
    # 2. 용어집(Word Mapping) 제약 구성
    glossary_str = ""
    if glossary:
        glossary_items = []
        for src, tgt in glossary.items():
            if src.strip() and tgt.strip():
                glossary_items.append(f"  * '{src}' -> '{tgt}'")
        if glossary_items:
            glossary_str = "\n[용어집 번역 규칙 (반드시 준수)]\n" + "\n".join(glossary_items) + "\n"
            
    # 3. 형식 가이드라인 구성
    is_vtt = file_name.lower().endswith(".vtt")
    is_lrc = file_name.lower().endswith(".lrc")

    if is_srt or is_vtt or is_lrc:
        file_format_name = "SRT/WebVTT 자막" if (is_srt or is_vtt) else "LRC 가사/대사"
        format_instruction = f"""
[형식 규칙]
- 현재 번역할 대본은 {file_format_name} 형식에서 시간 정보를 간소화한 상태입니다.
- 각 블록 맨 앞에 표기된 블록 태그(예: [#1], [#2], [#WEBVTT] 등)는 절대로 수정하거나 번역하지 말고, 출력 결과에서도 동일한 위치에 그대로 유지하세요.
- 오직 블록 태그 뒷부분의 대사/텍스트 내용만 자연스러운 한국어로 번역하세요.
- 원본의 빈 줄 구조와 형식을 정확히 유지하여 출력하세요.
"""
    else:
        format_instruction = """
[형식 규칙]
- 대본의 타임스탬프(예: [00:12], 01:23)는 절대 수정하지 말고 원본 위치 그대로 유지하세요.
- 괄호 안에 들어있는 지시문(예: [whispering], (한숨), *giggles* 및 전각 기호 ［속삭임］, （한숨）, ＊소곤소곤＊)은 지시문 기호 형태(괄호 종류 등)를 그대로 유지하세요.
- 원본 대본의 행 단위 구조(라인 바이 라인)를 철저히 지키십시오. 절대 대본을 소설이나 줄글(예: '히로인이 한숨을 쉬며 말했다' 등)로 통합하여 문장 형태로 풀어서 쓰지 말고, 원본의 '화자: 대사' 구조를 그대로 유지해야 합니다.
"""
        if translate_directives:
            format_instruction += "- 괄호 내부의 지시문 내용은 한국어 감정/행동 묘사로 자연스럽게 번역하세요 (예: [whispering] -> [속삭임], (sighs) -> (한숨), ［whispering］ -> ［속삭임］).\n"
        else:
            format_instruction += "- 괄호 내부의 지시문 내용은 번역하지 말고 영문 또는 원문 단어 그대로 유지하세요 (예: [whispering] -> [whispering]).\n"

    # 4. 슬라이딩 윈도우 컨텍스트 구성 (마지막 3줄만 슬라이딩하여 컨텍스트 토큰 최적화)
    context_str = ""
    if prev_original and prev_translated:
        prev_orig_lines = prev_original.splitlines()
        prev_trans_lines = prev_translated.splitlines()
        
        prev_orig_trimmed = "\n".join(prev_orig_lines[-3:])
        prev_trans_trimmed = "\n".join(prev_trans_lines[-3:])
        
        if len(prev_orig_lines) > 3:
            prev_orig_trimmed = "...\n" + prev_orig_trimmed
        if len(prev_trans_lines) > 3:
            prev_trans_trimmed = "...\n" + prev_trans_trimmed
            
        context_str = f"""
[이전 번역 맥락 (참고용 - 직전 대사 3줄)]
---이전 원문---
{prev_orig_trimmed}
---이전 번역문---
{prev_trans_trimmed}
----------------
"""

    prompt = f"""
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
    return prompt

def build_retranslation_prompt(
    current_chunk: str,
    existing_translation: str,
    prev_original: str,
    prev_translated: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool,
    file_name: str = ""
) -> str:
    # 1. 페르소나 제약 사항 구성
    persona_str = f"- 말투/어조: {persona.get('tone', '자연스러운 말투')}\n"
    persona_str += f"- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}\n"
    if persona.get("situation"):
        persona_str += f"- 배경 상황 및 스토리 맥락: {persona.get('situation')}\n"
    if persona.get("key_rules"):
        rules = "\n".join([f"  * {rule}" for rule in persona["key_rules"]])
        persona_str += f"- 주요 규칙:\n{rules}"
        
    # 2. 용어집(Word Mapping) 제약 구성
    glossary_str = ""
    if glossary:
        glossary_items = []
        for src, tgt in glossary.items():
            if src.strip() and tgt.strip():
                glossary_items.append(f"  * '{src}' -> '{tgt}'")
        if glossary_items:
            glossary_str = "\n[용어집 번역 규칙 (반드시 준수)]\n" + "\n".join(glossary_items) + "\n"
            
    # 3. 형식 가이드라인 구성
    is_vtt = file_name.lower().endswith(".vtt")
    is_lrc = file_name.lower().endswith(".lrc")

    if is_srt or is_vtt or is_lrc:
        file_format_name = "SRT/WebVTT 자막" if (is_srt or is_vtt) else "LRC 가사/대사"
        format_instruction = f"""
[형식 규칙]
- 현재 번역할 대본은 {file_format_name} 형식에서 시간 정보를 간소화한 상태입니다.
- 각 블록 맨 앞에 표기된 블록 태그(예: [#1], [#2], [#WEBVTT] 등)는 절대로 수정하거나 번역하지 말고, 출력 결과에서도 동일한 위치에 그대로 유지하세요.
- 오직 블록 태그 뒷부분의 대사/텍스트 내용만 자연스러운 한국어로 번역하세요.
- 원본의 빈 줄 구조와 형식을 정확히 유지하여 출력하세요.
"""
    else:
        format_instruction = """
[형식 규칙]
- 대본의 타임스탬프(예: [00:12], 01:23)는 절대 수정하지 말고 원본 위치 그대로 유지하세요.
- 괄호 안에 들어있는 지시문(예: [whispering], (한숨), *giggles* 및 전각 기호 ［속삭임］, （한숨）, ＊소곤소곤＊)은 지시문 기호 형태(괄호 종류 등)를 그대로 유지하세요.
- 원본 대본의 행 단위 구조(라인 바이 라인)를 철저히 지키십시오. 절대 대본을 소설이나 줄글(예: '히로인이 한숨을 쉬며 말했다' 등)로 통합하여 문장 형태로 풀어서 쓰지 말고, 원본의 '화자: 대사' 구조를 그대로 유지해야 합니다.
"""
        if translate_directives:
            format_instruction += "- 괄호 내부의 지시문 내용은 한국어 감정/행동 묘사로 자연스럽게 번역하세요 (예: [whispering] -> [속삭임], (sighs) -> (한숨), ［whispering］ -> ［속삭임］).\n"
        else:
            format_instruction += "- 괄호 내부의 지시문 내용은 번역하지 말고 영문 또는 원문 단어 그대로 유지하세요 (예: [whispering] -> [whispering]).\n"

    # 4. 슬라이딩 윈도우 컨텍스트 구성
    # 4. 슬라이딩 윈도우 컨텍스트 구성 (마지막 3줄만 슬라이딩하여 컨텍스트 토큰 최적화)
    context_str = ""
    if prev_original and prev_translated:
        prev_orig_lines = prev_original.splitlines()
        prev_trans_lines = prev_translated.splitlines()
        
        prev_orig_trimmed = "\n".join(prev_orig_lines[-3:])
        prev_trans_trimmed = "\n".join(prev_trans_lines[-3:])
        
        if len(prev_orig_lines) > 3:
            prev_orig_trimmed = "...\n" + prev_orig_trimmed
        if len(prev_trans_lines) > 3:
            prev_trans_trimmed = "...\n" + prev_trans_trimmed
            
        context_str = f"""
[이전 번역 맥락 (참고용 - 직전 대사 3줄)]
---이전 원문---
{prev_orig_trimmed}
---이전 번역문---
{prev_trans_trimmed}
----------------
"""

    prompt = f"""
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
    return prompt


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
        sampler = make_sampler(temp=temp)
        logits_processors = make_logits_processors(
            repetition_penalty=repetition_penalty,
            repetition_context_size=100
        )
        generator = stream_generate(
            model,
            processor,
            prompt=formatted_prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            logits_processors=logits_processors,
        )

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


def translate_one_chunk(
    model,
    processor,
    prompt: str,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    cancel_token: dict = None,
    token_callback=None,
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
