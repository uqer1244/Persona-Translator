# PersonaASMR Studio

> **Apple Silicon GPU 로컬 가속(MLX) 기반의 상황극 대본 전문 맞춤형 번역 및 하이브리드 인스턴트 캐릭터 롤플레잉 플랫폼**

`PersonaASMR Studio`는 로컬 온디바이스 VLM/LLM을 활용하여 서브컬처 콘텐츠 특유의 섬세한 말투(페르소나)와 상황맥락을 반영하는 맞춤형 번역 도구이자, 번역 과정에서 축적된 캐릭터 자산을 활용하여 실시간 AI 캐릭터 롤플레잉(RP)을 나눌 수 있는 올인원 플랫폼입니다.

---

## 핵심 기능 (Core Features)

### 1. Apple Silicon GPU 로컬 가속 (`mlx-lm` / `mlx-vlm`)
* **100% 온디바이스(On-device)**: 외부 API 키나 네트워크 연결 없이 Mac 내부에서 로컬로 연산이 이루어집니다. 개인 프라이버시가 완벽히 보존됩니다.
* **통합 메모리 최적화**: KV Cache 및 최적화 설정을 탑재하여 VRAM이 제한적인 16GB RAM 기기에서도 끊김 없고 쾌적하게 번역과 채팅을 구동합니다.

### 2. 단계별 워크플로우 (Streamlit Dashboard)
사용자의 인지 과부하를 줄이기 위해 깔끔하고 미려하게 정돈된 단일 UI 대시보드 구조를 제공합니다.
* **1단계: 데이터 로드 (Script/Visual Input)**: 원문 대본(`.txt`)과 캐릭터 일러스트를 로드합니다. 작품별 코드를 기반으로 프로젝트 디렉토리를 격리 보존합니다.
* **2단계: 맥락 추출 & 페르소나 카드 생성**: 캐릭터의 말투 특징, 화자-청자 관계, 고정 번역 단어장을 정밀 구축합니다.
* **3단계: 단어장(Glossary) 정제**: 서브컬처 고유의 고유명사를 강력하게 고정(`Proper_Noun`)하여 번역 및 채팅 시 다른 단어로 오번역되는 것을 원천 차단합니다.
* **4단계: 스마트 청크 번역**: SRT 자막이나 대본 포맷이 깨지지 않도록 맥락을 보존하며 문장 단위로 고속 번역을 수행합니다.
* **5단계: AI 캐릭터 롤플레잉**: 번역된 정보를 즉각 계승하여 몰입형 캐릭터 챗봇을 빌드하고 롤플레잉을 즐깁니다.

### 3. 자가 치료 모니터링 시스템 (Self-Healing Loop)
* 로컬 LLM 특유의 동일 토큰 무한 루프 에러를 스스로 감지합니다. 이상 현상 감지 시 백엔드에서 추론 파라미터(Temperature, Penalty 등)를 가변 조절하여 해당 청크를 자동으로 다시 수선하고 재번역합니다.

### 4. 하이브리드 듀얼 RAG (BM25 Contextual RAG)
* 캐릭터 롤플레잉 중 사용자의 입력과 대본 간 유사도를 로컬 고속 검색하여 대사 및 에피소드를 영리하게 인용합니다.
* **1:1 대칭 정렬 컨텍스트**: 원문 지시문(`[...]`)과 한국어 말투 데이터를 대칭 피딩하여 원작 성우의 섬세한 뉘앙스를 한국어 문체에 완벽히 입혀 출력합니다.

---

## 기술 스택 (Tech Stack)

* **Core Engine**: `mlx-vlm`, `mlx-lm`, `transformers`
* **Framework**: `Streamlit` (번역 및 채팅 통합 GUI 대시보드)
* **Design & UI**: Vanilla CSS (Glassmorphism & Neon Glow UI), Custom Google Fonts (`Inter`, `Outfit`)
* **Data & Logic**: `torch`, `pypdf`, `jinja2`, `huggingface_hub`

---

## 시작 가이드 (Quick Start)

### 1. 가상환경 및 패키지 설치
Python 3.11+ 환경 사용을 권장합니다.

```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 2. 로컬 VLM/LLM 모델 준비
다운로드받은 MLX 포맷 모델 폴더를 프로젝트 하위의 `models/` 디렉토리에 저장합니다.

```text
ASMR_ADV/
└── models/
    └── <모델명>/  <-- 다운로드한 모델 폴더
        ├── config.json
        ├── model.safetensors
        ├── chat_template.jinja
        └── tokenizer.json
```

### 3. 애플리케이션 실행
단 하나의 명령어로 번역, 정제, 채팅 롤플레잉까지 한 번에 구동할 수 있습니다.

```bash
streamlit run app.py
```
* 구동 완료 시 자동으로 웹 브라우저(`http://localhost:8501`)가 열립니다.
* 메모리가 넉넉지 않을 경우, 채팅 탭 상단의 `[모델 해제 (Unload)]` 기능을 활용해 메모리를 즉각 회수할 수 있습니다.

---

## 프로젝트 구조 (Directory Structure)

```text
ASMR_ADV/
├── app.py                # Streamlit 메인 진입점
├── core/                 # VLM 분석, 번역 및 RAG 코어 엔진
│   ├── analyzer.py
│   ├── chat_engine.py
│   ├── model_manager.py
│   ├── progress_store.py
│   └── translator.py
├── ui/                   # 3분할 워크플로우 개별 탭 GUI 컴포넌트
│   ├── sidebar.py
│   ├── tab_script.py
│   ├── tab_persona.py
│   ├── tab_translate.py
│   └── tab_chat.py
├── models/               # 로컬 LLM / VLM 모델 보존 디렉토리
└── plans/                # 마스터 기획 사양서
```

---

## 라이선스
이 프로젝트는 **MIT License**에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고해 주세요.

