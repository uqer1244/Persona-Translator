import json
import re

def analyze_persona(model, processor, metadata_text: str, script_preview: str, image_paths: list[str] = None) -> dict:
    """
    메타데이터, 대본 일부, 그리고 업로드된 소개 이미지(있는 경우)를 기반으로 페르소나를 분석하고 JSON 객체로 반환합니다.
    """
    # GPU 스트림 스레드 충돌 방지를 위해 함수 내부에서 로컬 임포트 수행
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    image_note = ""
    if image_paths and len(image_paths) > 0:
        image_note = "\n- 제공된 소개 이미지(들)를 함께 분석하여 일러스트 내 캐릭터의 분위기, 표정, 소개 텍스트 및 상세 설정을 페르소나 및 상황 분석에 반영하세요."

    prompt = f"""
ASMR 대본의 설명란 텍스트(메타데이터), 대본 초반부, 그리고 제공된 소개 이미지를 종합적으로 분석하여 상황극 번역에 필요한 캐릭터 페르소나 정보, 주요 고유 명사/호칭에 대한 용어집, 그리고 전체 대본 요약(스토리 요약 포함)을 추출해주세요.{image_note}
결과는 반드시 아래의 JSON 형식으로만 작성해야 하며, 다른 설명이나 인삿말은 생략하세요.

[JSON 형식]
{{
  "tone": "캐릭터의 말투와 어조 (예: 부드러운 반말, 끝처리를 흐리는 말투, 독점욕 있는 어조 등)",
  "relationship": "화자와 청자의 관계 및 상황 (예: 오래된 연인 사이, 소꿉친구, 간호사와 환자 등)",
  "key_rules": [
    "번역 시 반드시 지켜야 할 어조 및 단어 선택 규칙 1",
    "규칙 2",
    "규칙 3 (최대 5개)"
  ],
  "glossary": [
    {{"source": "대본 내 자주 등장하거나 번역 고정이 필요한 주요 호칭/단어 원어 (예: Darling)", "target": "제안할 번역어 (예: 자기야)"}},
    {{"source": "Onii-chan", "target": "오빠"}}
  ],
  "summary": {{
    "speaker_name": "화자(상황극 주인공)의 이름이나 주요 호칭 (예: 선배, 얀데레 여자친구, 사쿠라 등)",
    "listener_role": "청자(듣는 사람)의 역할이나 주요 호칭 (예: 후배, 청취자, 연인 등)",
    "situation": "전체 상황극의 주요 상황 및 배경 설정 요약 (1~2문장)",
    "story": "초반 대본 및 소개글에서 유추할 수 있는 대략적인 스토리 흐름 및 전개 줄거리"
  }}
}}

[입력 데이터]
메타데이터 (소개글, 태그):
{metadata_text}

대본 초반부:
{script_preview}
"""

    messages = [{"role": "user", "content": prompt}]
    num_images = len(image_paths) if image_paths else 0
    formatted_prompt = apply_chat_template(
        processor,
        model.config,
        messages,
        num_images=num_images,
        num_audios=0
    )
    
    # mlx-vlm generate
    response_obj = generate(
        model,
        processor,
        prompt=formatted_prompt,
        image=image_paths,
        temp=0.1,
        max_tokens=1200, # 요약 추가를 고려해 max_tokens 약간 상향
        kv_bits=3.5,
        kv_quant_scheme="turboquant"
    )
    response = response_obj.text
    
    # 응답에서 JSON 파싱
    try:
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            return json.loads(json_str)
        else:
            return json.loads(response)
    except Exception as e:
        # 파싱 실패 시 기본값 반환
        return {
            "tone": "일반적인 상황극 말투",
            "relationship": "상황극 캐릭터와 청자",
            "key_rules": [
                "대본의 맥락을 살려 자연스럽게 번역해주세요.",
                "지시문 및 타임스탬프 형태를 유지해주세요."
            ],
            "summary": {
                "speaker_name": "미분석",
                "listener_role": "미분석",
                "situation": "대본의 정보가 부족하거나 파싱에 실패했습니다.",
                "story": "대본 분석 전입니다."
            }
        }
