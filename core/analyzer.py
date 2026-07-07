import json
import re

from core.progress_store import (
    load_chunk_summary,
    load_image_note,
    save_chunk_summary,
    save_image_note,
)


def _generate_text(
    model,
    processor,
    prompt: str,
    image_paths: list[str] | None = None,
    max_tokens: int = 1024,
    temp: float = 0.1,
    repetition_penalty: float = 1.1,
) -> str:
    from mlx_vlm.generate import stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from core.utils import has_repetition

    image_paths = image_paths or []
    
    # 명시적 이미지 태그 처리 (VLM 토큰 유출 및 템플릿 오류 예방)
    prompt_content = prompt
    if len(image_paths) > 0 and "<image>" not in prompt:
        prompt_content = "<image>\n" + prompt

    messages = [{"role": "user", "content": prompt_content}]
    formatted_prompt = apply_chat_template(
        processor,
        model.config,
        messages,
        num_images=len(image_paths),
        num_audios=0,
    )

    max_retries = 3
    for retry in range(max_retries):
        current_temp = temp
        current_penalty = repetition_penalty
        if retry > 0:
            current_temp = min(0.7, temp + 0.2 * retry)
            current_penalty = repetition_penalty + 0.15 * retry
            print(f"[VLM RETRY] Loop detected, retrying {retry}/{max_retries-1} with temp={current_temp:.2f}, penalty={current_penalty:.2f}")

        output = ""
        generator = stream_generate(
            model,
            processor,
            prompt=formatted_prompt,
            image=image_paths or None,
            temp=current_temp,
            max_tokens=max_tokens,
            kv_bits=3.5,
            kv_quant_scheme="turboquant",
            repetition_penalty=current_penalty,
            repetition_context_size=100,
        )

        loop_detected = False
        for response in generator:
            output += response.text
            if has_repetition(output):
                print(f"[VLM WARNING] Repetition loop detected! Stopping stream.")
                loop_detected = True
                break

        if not loop_detected:
            return output

    return output


def _clear_mlx_cache():
    try:
        import gc
        import mlx.core as mx

        mx.clear_cache()
        gc.collect()
    except Exception:
        pass


def _parse_json_response(response: str) -> dict:
    json_match = re.search(r"\{.*\}", response, re.DOTALL)
    json_str = json_match.group(0) if json_match else response

    valid_escape_pattern = re.compile(r'(\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})|\\')

    def fix_escape(match):
        if match.group(1):
            return match.group(1)
        return "\\\\"

    json_str = valid_escape_pattern.sub(fix_escape, json_str)
    return json.loads(json_str, strict=False)


def analyze_images(model, processor, image_paths: list[str] | None = None) -> str:
    """
    모든 소개 이미지를 한 장씩 VLM에 통과시켜 텍스트 분석 노트로 압축합니다.
    한 번에 여러 이미지를 넣지 않아 Metal 메모리 피크를 낮춥니다.
    """
    if not image_paths:
        return ""

    notes = []
    for idx, image_path in enumerate(image_paths, start=1):
        cached_note = load_image_note(image_path)
        if cached_note:
            notes.append(cached_note)
            continue

        prompt = """
ASMR 작품 소개 이미지 1장을 분석해 주세요.
번역 페르소나와 대본 요약에 도움이 되는 정보만 간결하게 추출하세요.

[추출 항목]
- 캐릭터 외형, 표정, 자세, 분위기
- 이미지 안에 보이는 제목/트랙/설정/관계성/키워드 텍스트
- 화자와 청자의 관계를 추정할 단서
- 말투나 번역 어조에 반영할 단서

설명은 한국어 bullet 형태로만 작성하세요.
"""
        try:
            note = _generate_text(
                model,
                processor,
                prompt,
                image_paths=[image_path],
                max_tokens=600,
                temp=0.1,
            ).strip()
            note_record = f"[이미지 {idx}: {image_path}]\n{note}"
            save_image_note(image_path, note_record)
            notes.append(note_record)
        finally:
            _clear_mlx_cache()

    return "\n\n".join(notes)


def analyze_persona(model, processor, metadata_text: str, script_preview: str, image_paths: list[str] = None) -> dict:
    """
    메타데이터, 대본 일부, 소개 이미지 분석 노트를 기반으로 페르소나와 용어집만 반환합니다.
    대본 요약은 analyze_script_summary에서 별도 실행합니다.
    """
    image_notes = analyze_images(model, processor, image_paths)
    image_section = f"\n[소개 이미지 분석 노트]\n{image_notes}\n" if image_notes else ""

    prompt = f"""
ASMR 대본의 설명란 텍스트(메타데이터), 대본 본문 일부, 소개 이미지 분석 노트를 종합하여 상황극 번역에 필요한 캐릭터 페르소나 정보와 주요 고유 명사/호칭 용어집만 추출해주세요.
대본 전체 요약은 작성하지 마세요.
결과는 반드시 아래의 JSON 형식으로만 작성해야 하며, 다른 설명이나 인삿말은 생략하세요.

[JSON 형식]
{{
  "tone": "캐릭터의 말투와 어조 (예: 부드러운 반말, 끝처리를 흐리는 말투, 독점욕 있는 어조 등)",
  "relationship": "화자와 청자의 관계 (예: 오래된 연인 사이, 소꿉친구 등)",
  "situation": "전체 배경 상황 및 스토리 맥락 요약 (예: 주인공이 청자를 간호하며 위로해주는 상황)",
  "key_rules": [
    "번역 시 반드시 지켜야 할 어조 및 단어 선택 규칙 1",
    "규칙 2",
    "규칙 3 (최대 5개)"
  ],
  "glossary": [
    {{"source": "대본 내 자주 등장하거나 번역 고정이 필요한 주요 호칭/단어 원어", "target": "제안할 번역어"}},
    {{"source": "Onii-chan", "target": "오빠"}}
  ]
}}

[JSON 형식 엄격 준수 규칙]
1. 모든 문자열 값 내부에서 일반 큰따옴표를 쓰지 말고 작은따옴표 또는 한국어 따옴표를 사용하세요.
2. JSON 형식을 제외한 그 어떤 다른 텍스트도 출력하지 마십시오.

[입력 데이터]
메타데이터:
{metadata_text}
{image_section}
대본 본문 일부:
{script_preview}
"""

    response = ""
    try:
        response = _generate_text(model, processor, prompt, max_tokens=1024, temp=0.1)
        return _parse_json_response(response)
    except Exception as e:
        print(f"[ERROR] Persona JSON parsing failed: {e}")
        print(f"[DEBUG] Raw LLM Response:\n{response}")
        return {
            "tone": "일반적인 상황극 말투",
            "relationship": "상황극 캐릭터와 청자",
            "situation": "상황극 대본의 배경 상황",
            "key_rules": [
                "대본의 맥락을 살려 자연스럽게 번역해주세요.",
                "지시문 및 타임스탬프 형태를 유지해주세요.",
            ],
            "glossary": [],
        }
    finally:
        _clear_mlx_cache()


def summarize_script_chunks(
    model,
    processor,
    file_name: str,
    chunks: list[str],
    metadata_text: str = "",
) -> list[str]:
    summaries = []
    summary_units = []
    for chunk_idx, chunk in enumerate(chunks):
        if len(chunk) <= 500:
            summary_units.append((chunk_idx, chunk))
            continue
        for part_start in range(0, len(chunk), 500):
            summary_units.append((chunk_idx, chunk[part_start:part_start + 500]))

    for idx, (source_chunk_idx, chunk) in enumerate(summary_units):
        cached_summary = load_chunk_summary(file_name, idx, chunk)
        if cached_summary:
            summaries.append(cached_summary)
            continue

        prompt = f"""
ASMR 대본의 일부 청크를 짧게 요약하세요.
이 단계는 최종 요약을 만들기 위한 중간 요약입니다.

[작성 규칙]
- 대사 흐름, 행동, 감정 변화, 관계 변화만 정리하세요.
- 인물 이름/호칭/고유명사는 보이면 유지하세요.
- 5개 이하 bullet로 간결하게 작성하세요.
- 해설 문구 없이 요약만 출력하세요.

[메타데이터 참고]
{metadata_text[:1500]}

[원본 청크 {source_chunk_idx + 1} / 요약 조각 {idx + 1}]
{chunk}
"""
        try:
            summary = _generate_text(model, processor, prompt, max_tokens=200, temp=0.1).strip()
            save_chunk_summary(file_name, idx, chunk, summary)
            summaries.append(summary)
        finally:
            _clear_mlx_cache()

    return summaries


def analyze_script_summary(
    model,
    processor,
    metadata_text: str,
    script_preview: str,
    image_paths: list[str] = None,
    file_name: str = "script.txt",
    chunks: list[str] | None = None,
) -> dict:
    """
    메타데이터, 대본 구조, 소개 이미지 분석 노트를 기반으로 대본 요약만 반환합니다.
    """
    image_notes = analyze_images(model, processor, image_paths)
    image_section = f"\n[소개 이미지 분석 노트]\n{image_notes}\n" if image_notes else ""
    source_chunks = chunks if chunks else [script_preview]
    chunk_summaries = summarize_script_chunks(
        model,
        processor,
        file_name,
        source_chunks,
        metadata_text=metadata_text,
    )
    summary_blocks = []
    total_chars = 0
    for idx, summary in enumerate(chunk_summaries):
        clipped_summary = summary[:450]
        block = f"[청크 {idx + 1} 요약]\n{clipped_summary}"
        if total_chars + len(block) > 5000:
            summary_blocks.append("... (중간 요약이 많아 일부 후반 청크는 최종 요약 입력에서 생략됨) ...")
            break
        summary_blocks.append(block)
        total_chars += len(block)
    chunk_summary_text = "\n\n".join(summary_blocks)

    prompt = f"""
ASMR 대본의 설명란 텍스트, 청크별 중간 요약, 소개 이미지 분석 노트를 종합하여 대본 상황 및 스토리 요약만 작성해주세요.
페르소나 규칙이나 용어집은 작성하지 마세요.
결과는 반드시 아래 JSON 형식으로만 작성해야 합니다.

[JSON 형식]
{{
  "speaker_name": "화자(상황극 주인공)의 이름이나 주요 호칭",
  "listener_role": "청자(듣는 사람)의 역할이나 주요 호칭",
  "situation": "전체 상황극의 배경 상황 및 상세 설정 요약",
  "story": "트랙별 흐름, 행동, 감정 변화, 관계 변화를 마크다운 형식으로 정리한 상세 줄거리"
}}

[JSON 형식 엄격 준수 규칙]
1. 모든 문자열 값 내부에서 일반 큰따옴표를 쓰지 말고 작은따옴표 또는 한국어 따옴표를 사용하세요.
2. JSON 형식을 제외한 다른 텍스트는 출력하지 마십시오.

[입력 데이터]
메타데이터:
{metadata_text}
{image_section}
청크별 중간 요약:
{chunk_summary_text}
"""

    response = ""
    try:
        response = _generate_text(model, processor, prompt, max_tokens=700, temp=0.1)
        return _parse_json_response(response)
    except Exception as e:
        print(f"[ERROR] Summary JSON parsing failed: {e}")
        print(f"[DEBUG] Raw LLM Response:\n{response}")
        return {
            "speaker_name": "미분석",
            "listener_role": "미분석",
            "situation": "대본의 정보가 부족하거나 파싱에 실패했습니다.",
            "story": "대본 요약에 실패했습니다.",
        }
    finally:
        _clear_mlx_cache()


def generate_image_generation_prompt(
    model,
    processor,
    metadata_text: str,
    script_preview: str,
    persona: dict,
    script_summary: dict,
    image_paths: list[str] = None,
) -> str:
    image_notes = analyze_images(model, processor, image_paths)
    key_rules = "\n".join(f"- {rule}" for rule in persona.get("key_rules", []))
    prompt = f"""
당신은 이미지 생성 모델(SDXL, Midjourney 등)용 전문 프롬프트 디렉터입니다.
ASMR 작품의 소개 이미지 분석, 대본 요약, 페르소나를 바탕으로 새로운 고품질 일러스트 대표 이미지를 만들기 위한 상세한 프롬프트를 작성하세요.

[작성 규칙]
1. Positive prompt는 매우 구체적이고 예술적이어야 합니다. 캐릭터의 외형(헤어스타일, 눈빛, 표정 등), 복장, 자세, 분위기에 매칭되는 조명 효과, 상세한 배경 소품, 카메라 앵글, 그리고 전체적인 화풍/스타일까지 꼼꼼하게 묘사하는 풍부한 영문 프롬프트(단어/구 절 형태 및 완성형 문장 혼용)로 작성해주세요.
2. Negative prompt는 절대 작성하지 마십시오. ("Negative prompt:" 항목도 완전히 제거하세요).
3. 결과물은 오직 아래 두 개의 항목으로만 작성해서 출력해야 합니다.

[출력 형식]
Positive prompt:
(여기에 영어 이미지 생성 프롬프트를 세부적으로 채워 넣으세요. 마스터피스, 고품질 일러스트 스타일 관련 태그들도 풍부하게 추가)

Korean brief:
(한국어로 3문장 이내의 이미지 연출 및 시각적 구도 의도 설명)

[페르소나]
- 말투/어조: {persona.get('tone', '')}
- 관계: {persona.get('relationship', '')}
{key_rules}

[대본 요약]
- 화자: {script_summary.get('speaker_name', '')}
- 청자: {script_summary.get('listener_role', '')}
- 상황: {script_summary.get('situation', '')}
- 스토리: {script_summary.get('story', '')[:2000]}

[소개 이미지 분석 노트]
{image_notes}

[메타데이터]
{metadata_text[:2000]}

[대본 일부]
{script_preview[:2500]}
"""
    try:
        return _generate_text(model, processor, prompt, max_tokens=700, temp=0.3).strip()
    finally:
        _clear_mlx_cache()
