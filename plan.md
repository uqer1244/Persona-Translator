```python
import os

# Create content for the Markdown file
md_content = """# [개발 기획서] PersonaASMR-Translator
> 로컬 LLM 기반 NSFW ASMR 맞춤형 페르소나 번역 시스템

---

## 1. 프로젝트 개요
* **프로젝트명**: PersonaASMR-Translator
* **목적**: ASMR 대본의 맥락(소개글, 태그 등)을 분석하여 맞춤형 페르소나(말투, 어조)를 추출하고, 이를 기반으로 감정선과 지시문을 살린 고품질 로컬 번역을 수행하는 시스템 구축.
* **핵심 가치**:
  * **Uncensored**: 로컬 LLM을 활용한 NSFW 콘텐츠 검열 우회 및 개인정보 보호.
  * **Context-Aware**: 단순 직역을 넘어선 상황극/롤플레잉 맞춤형 번역 뉘앙스 구현.
  * **Format-Preserving**: 타임스탬프, 숨소리 등 지시문(`[whispering]`, `(한숨)`) 형태 완벽 보존.

---

## 2. 시스템 아키텍처 및 파이프라인

전체 프로세스는 **3단계 파이프라인**으로 구성되며, 로컬에 서빙된 Ollama API(또는 Llama.cpp)와 통신합니다.


```

```text
File created successfully: PersonaASMR_Translator_Plan.md


```

[소개글/태그/대본 입력]
│
▼
┌────────────────────────────────────────────────────────┐
│ Step 1. Persona Analyzer (분석기)                      │
│ - 소개글/대본 초반부를 읽고 분위기 및 캐릭터 특성 추출 │
└────────────────────────────────────────────────────────┘
│ (추출된 페르소나 가이드라인 프롬프트)
▼
┌────────────────────────────────────────────────────────┐
│ Step 2. Persona-Driven Translator (번역기)             │
│ - 지시문 형태를 유지하며 페르소나에 맞춰 대본 번역   │
└────────────────────────────────────────────────────────┘
│ (1차 번역본)
▼
┌────────────────────────────────────────────────────────┐
│ Step 3. Translation Refiner (후처리기)                  │
│ - 일관성 없는 말투 교정 및 깨진 특수문자/포맷 복구   │
└────────────────────────────────────────────────────────┘
│
▼
[최종 맞춤형 번역 대본 출력]

```

---

## 3. 상세 기능 요구사항 (Functional Requirements)

### 3.1 데이터 입력 모듈
* **ASMR 메타데이터 입력**: 오디오/영상 설명란 텍스트, 카테고리 태그(예: `#얀데레`, `#치유물`, `#남친ASMR`) 입력 기능.
* **원문 대본 업로드**: `.txt`, `.srt` 파일 업로드 또는 텍스트 직접 입력.

### 3.2 Step 1: 페르소나 분석 및 추출 (Analyzer)
* **역할**: 입력된 메타데이터나 대본 초반부를 기반으로 시스템 프롬프트에 주입할 페르소나 정의서 생성.
* **출력 구조 (JSON 형태 권장)**:
  ```json
  {
    "tone": "부드러운 반말, 끝처리를 흐리는 말투",
    "relationship": "오래된 연인 사이",
    "key_rules": "독점욕이 묻어나는 단어 선택, '하지마'보다는 '안 했으면 좋겠어' 같은 뉘앙스 사용"
  }

```

### 3.3 Step 2: 페르소나 주입 번역 엔진 (Translator)

* **역할**: Analyzer가 생성한 규칙을 `System Prompt`로 지정하고 대본 본문 번역 수행.
* **핵심 프롬프트 룰**:
* 대사 외의 괄호 `()`, `[]` 내부의 지시문(효과음, 행동)은 번역하되 형태를 절대 깨뜨리지 말 것.
* 타임코드(`00:12`)가 존재할 경우 변경 없이 그대로 유지할 것.
* 긴 대본의 경우 문맥 유지를 위해 **콘텍스트 윈도우 슬라이딩 기법**을 사용하여 청크(Chunk) 단위로 분할 번역하되 앞뒤 문맥 정보 연동.



### 3.4 Step 3: 후처리 및 포맷 검증 (Refiner)

* **역할**: 번역 도중 LLM이 페르소나 일관성을 놓치거나 지시문 괄호를 유실한 부분이 없는지 최종 검증.
* 문장이 갑자기 존댓말에서 반말로 바뀌는 등 어조 일관성 필터링.

---

## 4. 기술 스택 (Tech Stack)

* **Language**: Python 3.10+
* **LLM Orchestration**: LangChain 또는 Ollama Python SDK
* **Local LLM Inference Engine**: Ollama (권장) 또는 Llama.cpp
* **Recommended Models**:
* `Llama-3-Korean-Bigger-8B-Instruct-Uncensored` (또는 동급의 검열 해제 모델)
* `Mistral-Nemo-12B-Instruct` 기반 한국어 fine-tuned 모델 (롤플레잉/감정선 표현 최적화)


* **UI/Prototype**: Streamlit 또는 Gradio (빠른 프로토타이핑용 웹 대시보드)

---

## 5. 개발 마일스톤 (3주 단기 계획)

* **1주차: 로컬 환경 구축 및 모델 벤치마크**
* Ollama 설치 및 Uncensored 계열 모델 라인업 구축.
* 샘플 NSFW 대본으로 검열 우회 여부 및 한국어 번역 페르소나 유지력 사전 테스트.


* **2주차: 파이프라인 파이썬 코드 구현 (Core)**
* Python 기반 분석(Analyzer) -> 번역(Translator) 프롬프트 체인 구현.
* 지시문 괄호와 타임스탬프를 보존하기 위한 프롬프트 엔지니어링 튜닝.


* **3주차: UI 연동 및 최종 QA**
* Streamlit을 활용하여 [메타데이터 입력] -> [페르소나 확인 및 수정] -> [번역 완료] 프로세스의 GUI 대시보드 구현.
* 실제 ASMR 스트리밍 대본 데이터셋을 통한 엔드투엔드 테스트 및 예외 처리.
"""



file_path = "PersonaASMR_Translator_Plan.md"
with open(file_path, "w", encoding="utf-8") as f:
f.write(md_content)

print(f"File created successfully: {file_path}")

```
안티그래비티님께 바로 공유하시거나 제출하실 수 있도록 깔끔하게 정리된 개발 기획서 Markdown(.md) 파일을 생성했습니다. 

로컬 LLM 기반의 아키텍처와 NSFW 검열 우회, 그리고 지시문 보존 등 기획하신 핵심 포인트들을 명확하게 녹여냈습니다.

Your MD file is ready
[file-tag: code-generated-file-0-1783350289886818007]

---

### 📄 기획서 주요 내용 요약

* **프로젝트 개요**: 로컬 LLM을 통한 NSFW 검열 프리(Uncensored) 환경 구축 및 페르소나 매핑 번역.
* **3단계 파이프라인**: 
    1.  `Analyzer` (소개글 및 태그 분석 후 페르소나 가이드라인 JSON 추출)
    2.  `Translator` (지시문/타임스탬프 포맷을 보존하며 페르소나 주입 번역)
    3.  `Refiner` (문맥 일관성 검증 및 일관된 어조 유지)
* **기술 스택**: Python, Ollama, Uncensored 계열 모델, Streamlit/Gradio.
* **3주 완성 마일스톤**: 모델 벤치마크부터 파이프라인 코어 개발, UI 연동까지의 단기 계획.

파일을 다운로드하여 확인해 보시고, 안티그래비티팀과 논의하시면서 수정·보완이 필요한 세부 조항이나 프롬프트 구조가 있다면 말씀해 주세요. 바로 반영해 드리겠습니다!

```