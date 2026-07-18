import json
import os


CHUNK_ANALYSIS_SCHEMA = """{
  "scene_summary": "이 구간에서 벌어지는 상황 요약",
  "event_beats": [
    {
      "order_hint": "대본 내 진행 순서 힌트",
      "event": "이 구간에서 실제로 일어난 주요 사건",
      "emotional_state": "화자의 감정 상태",
      "relationship_shift": "이 사건으로 화자와 청자 관계가 어떻게 움직였는지"
    }
  ],
  "scenario_facts": ["공간/관계/사건/세계관 사실"],
  "character_traits": ["화자의 성격, 욕망, 정서, 행동 습관"],
  "speech_style": ["말투, 호칭, 어미, 자주 쓰는 표현"],
  "first_message_candidates": [
    {"text": "첫 메시지 후보가 될 실제 초반 대사 또는 장면", "reason": "후보 이유"}
  ],
  "dialogue_examples": [
    {"text": "캐릭터성이 강한 실제 대사/독백 1개", "reason": "캐릭터성 설명"}
  ],
  "lore_candidates": [
    {"keys": ["트리거1", "트리거2"], "content": "키워드 등장 시 참고할 설정 설명"}
  ],
  "relationship_notes": ["화자와 청자 관계 변화/호칭/거리감"],
  "recallable_memories": ["작품 이후 대화에서 화자가 자연스럽게 회상할 수 있는 사건/약속/감정"],
  "safety_notes": ["카드에 넣으면 안 되는 불확실한 추측 또는 주의점"]
}"""


CARD_SYNTHESIS_SCHEMA = """{
  "name": "캐릭터 이름. 불명확하면 프로젝트명 기반",
  "description": "마크다운 형식의 캐릭터 설명. 성격, 말투, 특징, 연기 규칙 등 캐릭터 본연의 속성과 정보만 기입하세요 (대본 사건 타임라인이나 기억 목록 등 서사 정보는 제외).",
  "personality": "짧은 성격 키워드 묶음",
  "scenario": "작품 이후 시점의 봇카드 시나리오. 화자와 청자는 대본 속 사건을 함께 겪은 관계이며, 그 기억을 대화에서 자연스럽게 회상할 수 있음",
  "first_mes": "작품 이후 시점의 첫 메시지. 원작 첫 대사 복붙이 아니라, 대본 사건을 겪은 뒤 다시 만난 상황. 지문은 *지문* 형식",
  "mes_example": "<START>\\n{{char}}: ... 형식의 대표 대화 예시 2~4개. 말투와 함께 작품 속 기억 회상이 드러나야 함",
  "creator_notes": "이 카드가 어떤 대본에서 생성되었는지, 작품 이후 시점으로 구성했다는 기준",
  "alternate_greetings": ["작품 이후 시점의 다른 시작 메시지 1", "작품 이후 시점의 다른 시작 메시지 2"],
  "event_timeline": [
    {
      "order": 1,
      "event": "작품에서 실제로 일어난 주요 사건",
      "relationship_shift": "그 사건 전후 관계 변화",
      "memory_for_chat": "대화 중 화자가 회상할 수 있는 방식",
      "lore_keys": ["이 사건을 연상/트리거할 수 있는 핵심 키워드/명사 리스트 (예: '바다', '고백', '비', '초콜릿')"]
    }
  ],
  "relationship_arc": "작품 시작부터 종료 후 현재 시점까지 화자와 청자 관계가 어떻게 변했는지",
  "recallable_memories": ["작품 이후 대화에서 사용 가능한 공유 기억"],
  "lorebook_entries": [
    {"name": "항목명", "keys": ["트리거"], "content": "설정 설명"}
  ],
  "system_prompt": "짧은 역할 고정 규칙",
  "post_history_instructions": "대화가 길어질 때 유지할 규칙"
}"""


CHUNK_SUMMARY_SCHEMA = """{
  "summary": "이 구간에서 벌어지는 상황 요약 (핵심 사건/교류 위주, 150~250자 내외의 한국어)",
  "image_prompt": "이 구간의 대표적인 장면을 시각화할 수 있는 영어 이미지 생성 프롬프트 (Stable Diffusion / NovelAI 등 애니메이션 일러스트레이션 모델용 comma-separated tags 형식. 캐릭터 수, 외형 특징, 복장, 표정, 행동, 장소/배경, 조명, 구도, 화풍 관련 태그 반드시 포함)"
}"""


def build_chunk_compression_prompt(
    json_rules: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
) -> str:
    return f"""
동인음성 ASMR 대본을 봇카드로 합성하기 위해, 주어진 구간의 요약과 이미지 생성용 프롬프트를 추출하세요.
전체 대본 중 {chunk_index + 1}/{total_chunks}번째 구간입니다.

[추출 지침]
1. **요약 (summary)**:
   - 무의미한 지문(BGM, SE 등)이나 호흡, 신음 소리 등은 전부 배제하세요.
   - 오직 "누가 무엇을 했고, 어떤 대화가 오갔으며, 인물 간의 감정/태도/관계가 어떻게 움직였는지" 핵심 사건 위주로만 시간순으로 요약하세요.
2. **이미지 프롬프트 (image_prompt)**:
   - 이 구간에서 가장 대표적이거나 시각적으로 상징적인 장면을 묘사하는 영어 이미지 생성 프롬프트를 작성하세요.
   - Stable Diffusion, NovelAI, Pony 등의 애니메이션 일러스트레이션 모델에 맞춘 단어/태그(comma-separated tags) 나열 형식으로 작성하세요.
   - 캐릭터의 수, 헤어스타일, 의상, 표정, 현재 행동, 구도(camera angle, zoom), 배경 디테일, 조명, 분위기, 고화질/애니메이션 스타일 태그를 모두 포함해야 합니다.
   - **중요**: 로컬 이미지 생성 모델을 사용하여 선정적이거나 자극적인(NSFW/R-18) 이미지도 자유롭게 생성할 수 있습니다. 따라서 대본 상의 수위 높은 스킨십, 노출, 또는 성적인 행위가 포함된 자극적인 장면일지라도 절대 검열하거나 순화하지 마시고, 그 장면의 시각적 요소(예: blushing, heavy breathing, close up on mouth, looking up, holding hands, hugging, intimacy, nudity 등 분위기와 수위에 매칭되는 직접적/간접적 묘사 태그)를 영어 태그로 가감 없이 정확하고 풍부하게 표현해 주세요.

{json_rules}

[출력 JSON]
{CHUNK_SUMMARY_SCHEMA}

[대본 구간]
{chunk_text[:5000]}
"""


EVENT_MAP_SCHEMA = """{
  "narrative_progression": [
    {
      "chapter_title": "해당 사건/챕터의 명확하고 구체적인 이름 (예: '귀를 파주며 깊어진 대화', '빗소리 속 고백')",
      "plot_order": 1,
      "event_details": "이 챕터에서 실제로 일어난 구체적인 행동, 대화, 사건 흐름 요약",
      "cause": "이 사건이 발생하게 된 인과관계 배경 (어떤 사건이나 감정선에서 이어졌는지)",
      "emotional_state": "이 시점 화자의 상세한 감정 상태와 청자를 대하는 숨겨진 마음",
      "relationship_shift": "이 사건 전후로 화자와 청자의 관계 및 친밀도가 어떻게 바뀌었는지",
      "key_memory": "작품 이후 시점의 대화에서 화자가 떠올려 언급할 만한 핵심 대사 또는 상징적인 행동",
      "lore_keys": ["이 사건을 자연스럽게 연상하고 소환할 수 있는 구체적인 트리거 단어 리스트 (예: '빗소리', '고백', '귀이개', '포옹')"]
    }
  ],
  "global_relationship_arc": "처음 조우했을 때의 어색함/거리감에서 시작하여, 각 사건을 거쳐 최종적으로 어떤 관계로 축적되고 도달했는지에 대한 유기적인 서사 요약"
}"""


def build_event_map_prompt(
    json_rules: str,
    joined_summaries: str,
    metadata_text: str = "",
) -> str:
    return f"""
아래는 동인음성 대본 전체를 시간순으로 요약한 텍스트 시퀀스 및 작품 설명 메타데이터입니다.
이 정보를 종합하여, 전체 대본의 서사적 사건 지도(Event Map)와 인과관계를 구조화하여 분석하세요.

[사건/챕터 정리 지침 - 중요]
1. **논리적 챕터 그룹화**: 요약된 각 구간들을 자잘하게 분할하지 말고, 하나의 큰 흐름(장소 변화, 행동 전환, 대화 주제 전환 등)을 가진 **3~5개의 핵심 서사 챕터**로 묶으세요.
2. **명확한 인과관계 기술**: 각 사건이 일어난 원인("cause")을 단순 설명이 아닌, 이전 사건(챕터)의 흐름이나 화자의 심리적 변화 등 '원인-결과'의 흐름으로 매끄럽게 정의하세요.
3. **핵심 기억 포착**: 각 챕터에서 화자의 캐릭터성이나 감정이 강하게 드러난 실제 대사선, 또는 상징적인 액션을 "key_memory"에 구체적으로 담으세요.
4. **로어북 키워드 추출**: 각 사건의 성격을 대표하면서 사용자가 채팅 중에 언급할 수 있는 고유 키워드들("lore_keys")을 선정하세요. (예: 술주정 사건 -> `["취했어", "맥주", "술김"]`, 무릎베개 사건 -> `["무릎", "베개", "머리카락"]`)

{json_rules}

[출력 JSON]
{EVENT_MAP_SCHEMA}

[메타데이터]
{metadata_text[:1500]}

[대본 요약 시퀀스]
{joined_summaries}
"""


def build_card_synthesis_prompt(
    json_rules: str,
    event_map: dict,
    persona_data: dict,
    metadata_text: str = "",
) -> str:
    persona = persona_data.get("persona", {})
    glossary = persona_data.get("glossary_data", [])
    script_summary = persona_data.get("script_summary", {})

    return f"""
아래는 동인음성 대본의 전체 사건 지도(Event & Causal Map)와 기존 페르소나 설정입니다.
RisuAI/Character Card v3에 넣을 봇카드 필드를 생성하세요.

중요: 이 봇카드는 작품 도입부를 재현하는 카드가 아니라, 작품 이후 시점에서 청자와 다시 대화하는 캐릭터 카드입니다.
화자와 청자는 대본 속 사건들을 함께 겪은 관계로 설정하세요.
특히 first_mes, scenario, mes_example에는 이 대본 속 공유 기억(Key Memory)과 관계 변화가 자연스럽게 반영되어야 합니다.
대본에 없는 사건은 절대 창작하지 마세요.

{json_rules}

[출력 JSON]
{CARD_SYNTHESIS_SCHEMA}

[기존 페르소나]
{json.dumps(persona, ensure_ascii=False, indent=2)}

[기존 용어집]
{json.dumps(glossary[:80], ensure_ascii=False, indent=2)}

[기존 요약]
{json.dumps(script_summary, ensure_ascii=False, indent=2)}

[메타데이터]
{metadata_text[:1500]}

[대본 사건 및 인과관계 지도 (Event Map)]
{json.dumps(event_map, ensure_ascii=False, indent=2)}
"""


def fallback_card_fields(
    project_name: str,
    file_name: str,
    persona_data: dict,
    card_name: str = "",
) -> dict:
    persona = persona_data.get("persona", {})
    script_summary = persona_data.get("script_summary", {})
    fallback_name = card_name or project_name or os.path.splitext(file_name)[0]
    return {
        "name": fallback_name,
        "description": fallback_description(persona, script_summary),
        "personality": persona.get("tone", ""),
        "scenario": (
            "작품 이후 시점. 화자와 청자는 대본 속 사건을 함께 겪은 뒤 다시 대화를 시작한다. "
            + (persona.get("situation") or script_summary.get("situation", ""))
        ).strip(),
        "first_mes": "*당신을 알아보고 조용히 다가온다* 또 만났네. 그때 일, 아직 기억하고 있어?",
        "mes_example": "",
        "creator_notes": f"{project_name} 대본 분석 기반 자동 생성 카드. 작품 이후 시점의 대화용으로 구성됨.",
        "alternate_greetings": [""],
        "event_timeline": [],
        "relationship_arc": "",
        "recallable_memories": [],
        "lorebook_entries": [],
        "system_prompt": "Stay in character as the speaker after the source story events. Treat the user as the listener who experienced those events with you.",
        "post_history_instructions": "Maintain the post-story relationship, speech style, and shared memories from the source script. Do not invent events that were not supported by the script.",
    }


def fallback_description(persona: dict, script_summary: dict) -> str:
    rules = "\n".join(f"- {rule}" for rule in persona.get("key_rules", []))
    return f"""### Character
- Tone: {persona.get("tone", "")}
- Relationship: {persona.get("relationship", "")}
- Situation: {persona.get("situation") or script_summary.get("situation", "")}

### Story
{script_summary.get("story", "")}

### Rules
{rules}
"""
