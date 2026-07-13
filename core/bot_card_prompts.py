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
  "description": "마크다운 형식의 캐릭터 설명. 성격, 말투, 작품에서 청자와 겪은 주요 사건, 관계 변화, 연기 규칙 포함",
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
      "memory_for_chat": "대화 중 화자가 회상할 수 있는 방식"
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


def build_chunk_analysis_prompt(
    json_rules: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
    metadata_text: str = "",
) -> str:
    return f"""
동인음성 ASMR 대본을 RisuAI 봇카드로 변환하기 위한 청크 분석을 수행하세요.
전체 대본 중 {chunk_index + 1}/{total_chunks}번째 구간입니다. 이 구간 안에 실제로 드러난 정보만 추출하고, 없는 내용은 추측하지 마세요.
최종 봇은 작품 이후 시점에서 청자와 대화할 예정입니다. 따라서 이 구간에서 나중에 회상 가능한 사건, 감정 변화, 관계 변화가 있으면 반드시 event_beats와 recallable_memories에 기록하세요.

{json_rules}

[출력 JSON]
{CHUNK_ANALYSIS_SCHEMA}

[메타데이터]
{metadata_text[:1200]}

[대본 구간]
{chunk_text[:6000]}
"""


def build_card_synthesis_prompt(
    json_rules: str,
    analyses: list[dict],
    persona_data: dict,
    metadata_text: str = "",
) -> str:
    persona = persona_data.get("persona", {})
    glossary = persona_data.get("glossary_data", [])
    script_summary = persona_data.get("script_summary", {})
    compact_analyses = json.dumps(analyses, ensure_ascii=False)[:24000]

    return f"""
아래는 동인음성 대본 전체를 청크별로 분석한 결과입니다.
RisuAI/Character Card v3에 넣을 봇카드 필드를 생성하세요.
중요: 카드에는 대본 전체 이해가 녹아 있어야 하지만, 원문을 길게 복붙하지 말고 핵심 설정/말투/관계/장면만 압축하세요.
중요: 이 봇카드는 작품 도입부를 재현하는 카드가 아니라, 작품 이후 시점에서 청자와 다시 대화하는 캐릭터 카드입니다.
화자와 청자는 대본 속 사건을 함께 겪은 관계로 설정하세요. first_mes, scenario, mes_example에는 이 공유 기억과 관계 변화가 자연스럽게 반영되어야 합니다.
대본에 없는 사건은 만들지 말고, 불확실한 내용은 확정하지 마세요.

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
{metadata_text[:2000]}

[청크별 분석 결과]
{compact_analyses}
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
