import re
from pypdf import PdfReader

def extract_text_from_pdf(pdf_file) -> str:
    """
    PDF 파일에서 텍스트를 추출합니다.
    """
    reader = PdfReader(pdf_file)
    text_list = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_list.append(text)
    return "\n".join(text_list)

def clean_pdf_linebreaks(text: str) -> str:
    """
    세로쓰기 또는 PDF 레이아웃 문제로 인해 잘게 쪼개진 줄바꿈을 문장 단위로 자동 병합합니다.
    """
    if not text:
        return ""
    
    # 윈도우 스타일 개행문자 통일
    text = text.replace("\r\n", "\n")
    lines = [line.strip() for line in text.split("\n")]
    result_lines = []
    current_line = ""
    
    for line in lines:
        if not line:
            # 빈 줄은 단락 구분이므로 기존 모은 라인을 배출하고 빈 줄 유지
            if current_line:
                result_lines.append(current_line)
                current_line = ""
            result_lines.append("")
            continue
            
        # 자막 타임라인이나 숫자로 시작하는 인덱스는 합치지 않고 개별 행으로 보존
        if re.match(r'^\d+$', line) or re.search(r'\d{2}:\d{2}:\d{2}', line):
            if current_line:
                result_lines.append(current_line)
                current_line = ""
            result_lines.append(line)
            continue
            
        if not current_line:
            current_line = line
        else:
            # 이전 라인이 마침표(., 。, ? , !) 또는 괄호 닫기(」, 』, ), ], })로 끝나면 새로운 문장으로 보고 줄바꿈 유지
            if re.search(r'[.!?。？！」』\)\}\]\*]$', current_line):
                result_lines.append(current_line)
                current_line = line
            else:
                # 한국어/일본어 문맥인 경우 공백 없이 합치고, 영어나 서양어 문맥이면 공백 하나를 두고 합칩니다.
                has_asian = any('\u3000' <= char <= '\u9fff' or '\uac00' <= char <= '\ud7a3' for char in current_line + line)
                if has_asian:
                    current_line += line
                else:
                    current_line += " " + line
                    
    if current_line:
        result_lines.append(current_line)
        
    # 빈 줄이 연속으로 3개 이상 나타나면 2개로 압축
    final_text = "\n".join(result_lines)
    final_text = re.sub(r'\n{3,}', '\n\n', final_text)
    return final_text

def chunk_text(text: str, chunk_size: int = 800) -> list[str]:
    """
    일반 텍스트를 문장이나 줄 단위가 깨지지 않게 단락별로 나눕니다.
    """
    text = text.replace("\r\n", "\n")
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0
    
    for para in paragraphs:
        para_len = len(para) + 1
        if current_length + para_len > chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [para]
            current_length = para_len
        else:
            current_chunk.append(para)
            current_length += para_len
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    return chunks

def chunk_srt(srt_text: str, blocks_per_chunk: int = 5) -> list[str]:
    """
    SRT 자막 파일을 빈 줄(\n\n) 기준으로 파싱하여 블록 단위로 청킹합니다.
    """
    srt_text = srt_text.replace("\r\n", "\n")
    raw_blocks = re.split(r'\n\s*\n', srt_text.strip())
    
    chunks = []
    current_blocks = []
    for block in raw_blocks:
        if block.strip():
            current_blocks.append(block.strip())
            if len(current_blocks) >= blocks_per_chunk:
                chunks.append("\n\n".join(current_blocks))
                current_blocks = []
                
    if current_blocks:
        chunks.append("\n\n".join(current_blocks))
        
    return chunks

def clean_markdown(text: str) -> str:
    """
    LLM 응답에서 마크다운 코드 블록 지시어(```srt, ```text 등)를 제거합니다.
    """
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text.strip()

def build_translation_prompt(
    current_chunk: str,
    prev_original: str,
    prev_translated: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool
) -> str:
    # 1. 페르소나 제약 사항 구성
    persona_str = f"- 말투/어조: {persona.get('tone', '자연스러운 말투')}\n"
    persona_str += f"- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}\n"
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
    if is_srt:
        format_instruction = """
[형식 규칙]
- 현재 번역할 대본은 SRT 자막 형식입니다. 
- 자막 인덱스(예: 1)와 타임코드(예: 00:00:01,000 --> 00:00:04,000)는 절대로 수정하거나 번역하지 말고 원본 그대로 유지하세요.
- 오직 자막 텍스트(대사) 부분만 번역하세요.
- 빈 줄 구조(\\n\\n)와 자막 파일의 틀을 정확하게 유지하여 출력하세요.
"""
    else:
        format_instruction = """
[형식 규칙]
- 대본의 타임스탬프(예: [00:12], 01:23)는 절대 수정하지 말고 원본 위치 그대로 유지하세요.
- 괄호 안에 들어있는 지시문(예: [whispering], (한숨), *giggles*)은 지시문 기호 형태(괄호 종류 등)를 그대로 유지하세요.
"""
        if translate_directives:
            format_instruction += "- 괄호 내부의 지시문 내용은 한국어 감정/행동 묘사로 자연스럽게 번역하세요 (예: [whispering] -> [속삭임], (sighs) -> (한숨)).\n"
        else:
            format_instruction += "- 괄호 내부의 지시문 내용은 번역하지 말고 영문 또는 원문 단어 그대로 유지하세요 (예: [whispering] -> [whispering]).\n"

    # 4. 슬라이딩 윈도우 컨텍스트 구성
    context_str = ""
    if prev_original and prev_translated:
        context_str = f"""
[이전 번역 맥락 (참고용)]
---이전 원문---
{prev_original}
---이전 번역문---
{prev_translated}
----------------
"""

    prompt = f"""
당신은 성인용(NSFW) ASMR 상황극 및 대본 전문 한국어 번역가입니다.
주어진 페르소나와 이전 번역 맥락, 용어집 번역 규칙을 참고하여 다음 대본을 번역해 주세요.

[캐릭터 페르소나]
{persona_str}
{glossary_str}
{format_instruction}
{context_str}
[번역할 대본]
{current_chunk}

[주의사항]
- 대본 번역 이외의 질문에 대한 답변, 해설, 프롬프트 지시사항의 반복 등은 절대로 출력하지 마십시오.
- 오직 번역 완료된 대본 내용만 출력하세요.
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
    translate_directives: bool
) -> str:
    # 1. 페르소나 제약 사항 구성
    persona_str = f"- 말투/어조: {persona.get('tone', '자연스러운 말투')}\n"
    persona_str += f"- 화자-청자 관계: {persona.get('relationship', '어울리는 관계')}\n"
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
    if is_srt:
        format_instruction = """
[형식 규칙]
- 현재 번역할 대본은 SRT 자막 형식입니다. 
- 자막 인덱스(예: 1)와 타임코드(예: 00:00:01,000 --> 00:00:04,000)는 절대로 수정하거나 번역하지 말고 원본 그대로 유지하세요.
- 오직 자막 텍스트(대사) 부분만 번역하세요.
- 빈 줄 구조(\\n\\n)와 자막 파일의 틀을 정확하게 유지하여 출력하세요.
"""
    else:
        format_instruction = """
[형식 규칙]
- 대본의 타임스탬프(예: [00:12], 01:23)는 절대 수정하지 말고 원본 위치 그대로 유지하세요.
- 괄호 안에 들어있는 지시문(예: [whispering], (한숨), *giggles*)은 지시문 기호 형태(괄호 종류 등)를 그대로 유지하세요.
"""
        if translate_directives:
            format_instruction += "- 괄호 내부의 지시문 내용은 한국어 감정/행동 묘사로 자연스럽게 번역하세요 (예: [whispering] -> [속삭임], (sighs) -> (한숨)).\n"
        else:
            format_instruction += "- 괄호 내부의 지시문 내용은 번역하지 말고 영문 또는 원문 단어 그대로 유지하세요 (예: [whispering] -> [whispering]).\n"

    # 4. 슬라이딩 윈도우 컨텍스트 구성
    context_str = ""
    if prev_original and prev_translated:
        context_str = f"""
[이전 번역 맥락 (참고용)]
---이전 원문---
{prev_original}
---이전 번역문---
{prev_translated}
----------------
"""

    prompt = f"""
당신은 성인용(NSFW) ASMR 상황극 및 대본 전문 한국어 번역 교정가입니다.
주어진 페르소나와 기존 번역 초안, 용어집 번역 규칙을 참고하여 다음 대본의 번역을 보완 및 수정해 주세요.

[캐릭터 페르소나]
{persona_str}
{glossary_str}
{format_instruction}
{context_str}

[기존 번역 초안 (참고용 - 말투 및 오역 수정 대상)]
{existing_translation}

[수정할 원문 대본]
{current_chunk}

[주의사항]
- 기존 번역 초안에서 잘못 지정된 호칭이나 페르소나에 맞지 않는 말투를 발견하면, [캐릭터 페르소나] 및 [용어집 번역 규칙]에 따라 철저히 수정해 주세요.
- 기존 번역의 장점을 살리되, 어조 규칙 및 지정어 규칙이 위배된 부분을 정교하게 보정하세요.
- 대본 번역 이외의 질문에 대한 답변, 해설, 프롬프트 지시사항의 반복 등은 절대로 출력하지 마십시오.
- 오직 번역이 완료된 대본 내용만 출력하세요.
"""
    return prompt

def translate_script(
    model,
    processor,
    script: str,
    persona: dict,
    glossary: dict,
    is_srt: bool,
    translate_directives: bool,
    chunk_size: int = 800,
    temp: float = 0.3,
    repetition_penalty: float = 1.1,
    existing_translations: list[str] = None,
    cancel_token: dict = None,
    progress_callback=None
) -> str:
    """
    대본을 청크 단위로 분할하여 슬라이딩 윈도우 방식으로 번역을 진행하며 진행 상황을 콜백으로 호출합니다.
    이미 번역된 청크(existing_translations)는 건너뛰며 흐름을 이어갑니다.
    중단 요청(cancel_token)이 감지되면 즉시 중지합니다.
    """
    # GPU 스트림 스레드 충돌 방지를 위해 함수 내부에서 로컬 임포트 수행
    from mlx_vlm.generate import stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template

    if is_srt:
        chunks = chunk_srt(script)
    else:
        chunks = chunk_text(script, chunk_size=chunk_size)
        
    translated_chunks = []
    total_chunks = len(chunks)
    
    prev_original = ""
    prev_translated = ""
    
    for idx, chunk in enumerate(chunks):
        # 중단 토큰 확인
        if cancel_token and cancel_token.get("cancel"):
            break

        # 이미 번역된 결과가 존재하는 청크는 LLM 호출을 건너뛰고 컨텍스트만 업데이트
        if existing_translations and idx < len(existing_translations) and existing_translations[idx].strip():
            chunk_translation_clean = existing_translations[idx]
            translated_chunks.append(chunk_translation_clean)
            prev_original = chunk
            prev_translated = chunk_translation_clean
            if progress_callback:
                # UI 갱신을 위해 콜백 전달 (이미 번역 완료됨 표시)
                progress_callback("", idx, total_chunks, chunk_translation_clean, True)
            continue

        prompt = build_translation_prompt(
            current_chunk=chunk,
            prev_original=prev_original,
            prev_translated=prev_translated,
            persona=persona,
            glossary=glossary,
            is_srt=is_srt,
            translate_directives=translate_directives
        )
        
        messages = [{"role": "user", "content": prompt}]
        formatted_prompt = apply_chat_template(
            processor,
            model.config,
            messages,
            num_images=0,
            num_audios=0
        )
        
        chunk_translation = ""
        
        # MLX VLM 스트리밍 생성
        generator = stream_generate(
            model,
            processor,
            prompt=formatted_prompt,
            temp=temp,
            max_tokens=1500,
            kv_bits=3.5,
            kv_quant_scheme="turboquant",
            repetition_penalty=repetition_penalty,
            repetition_context_size=100
        )
        
        aborted = False
        for response in generator:
            if cancel_token and cancel_token.get("cancel"):
                aborted = True
                break
            token_text = response.text
            chunk_translation += token_text
            if progress_callback:
                progress_callback(token_text, idx, total_chunks, chunk_translation, False)
                
        if aborted:
            break
            
        chunk_translation_clean = clean_markdown(chunk_translation)
        translated_chunks.append(chunk_translation_clean)
        
        prev_original = chunk
        prev_translated = chunk_translation_clean
        
        if progress_callback:
            progress_callback("", idx, total_chunks, chunk_translation_clean, True)
        
        # GPU 메모리 캐시 비우기 및 가비지 컬렉션 실행 (OOM 방지)
        import mlx.core as mx
        import gc
        mx.metal.clear_cache()
        gc.collect()
        
    if is_srt:
        return "\n\n".join(translated_chunks)
    else:
        return "\n".join(translated_chunks)
