# Persona-Translator

> **Apple Silicon GPU 로컬 가속(MLX) 환경에 최적화된 상황극 및 ASMR 대본 전문 맞춤형 번역 & AI 롤플레잉(RP) 통합 시스템**

`Persona-Translator`는 로컬 오프라인 VLM(Gemma 4 12B)을 활용하여 서브컬처 콘텐츠 특유의 섬세한 말투(페르소나)와 상황맥락을 반영하는 맞춤형 번역 도구입니다. 

이에 더해, 번역 완료된 페르소나와 단어장 및 대본 자산을 100% 재활용하는 **독자적인 AI 롤플레잉(RP) 채팅 익스텐션**을 제공하여 상황극 속 주인공과의 실시간 인터랙션 경험을 선사합니다.

---

## 주요 기능

### 1. Apple Silicon GPU 로컬 가속 (`mlx-vlm` / `mlx-lm`)
- 외부 API 키나 네트워크 연결 없이 Mac 내부에서 100% 온디바이스(On-device) 작동하여 기밀 대본 유출 우려가 전혀 없습니다.
- **TurboQuant (KV Cache 3.5-bit)** 및 메모리 최적화 설정을 탑재하여 16GB RAM 사양의 기기에서도 VRAM 부족(OOM) 현상 없이 쾌적하게 번역 및 채팅이 가능합니다.

### 2. 스마트 자막 청킹 및 장면 인지형 장면 경계 분할
- SRT 자막의 타임라인 포맷이 깨지지 않도록 동적으로 자막 블록을 글자 수 단위(기본 800자)로 묶어 처리함으로써 번역 속도를 4배 이상 향상했습니다.
- 대본 내의 사운드 이펙트 지시문(`[SE: ...]`, `[BGM: ...]`), 트랙 구분선 등을 스스로 감지하여 장면 경계(Scene-aware Boundary)를 쪼개어 맥락 보존율을 극대화합니다.

### 3. 작품 일러스트 다중 분석 (VLM 멀티모달)
- 작품 홍보 일러스트나 DLsite 트랙 디테일 컷 등 이미지를 업로드하면, Gemma 4 VLM 모델이 비주얼 데이터와 텍스트를 연계 분석하여 성격, 눈빛, 분위기 등을 추출해 뉘앙스 설정에 정교하게 투영합니다.

### 4. 페르소나 및 마스터 단어장 공유 라이브러리
- 말투 특징, 화자-청자 관계, 고정 번역 규칙 등을 편집할 수 있으며, 입력 즉시 `persona.json`에 **실시간 자동 저장(Autosave)**됩니다.
- 이전 프로젝트에서 빌드한 페르소나 데이터를 원클릭으로 현재 프로젝트에 이식하는 **페르소나 공유 기능**을 제공하여 시리즈물의 통일감을 유지합니다.

### 5.  AI 롤플레잉(RP) 익스텐션 Web
- **데이터 플라이휠**: 번역하면서 축적된 페르소나 설정 및 단어장 정보를 100% 계승하여 인스턴트 캐릭터 챗봇을 즉각 빌드합니다.
- **Contextual RAG (BM25)**: 사용자 입력 메시지와 대본 번역문 간의 텍스트 유사도를 로컬에서 고속 검색하여, 캐릭터가 원작 대본 속 구절이나 에피소드를 영리하게 기억하고 인용하게 만드는 Hidden Prompt 장치를 갖추었습니다.
---

## 기술 스택

* **Core Engine**: `mlx-vlm`, `mlx-lm`
* **Frameworks**: `Streamlit` (번역 대시보드), `FastAPI` (비동기 채팅 API)
* **Frontend**: HTML5, Vanilla CSS (Glassmorphism & Neon Glow UI), Javascript (Fetch Stream)
* **AI & Data Processing**: `transformers`, `torch`, `torchvision`, `pypdf`, `pandas`, `huggingface_hub`

---

## 시작 가이드

### 1. 가상환경 및 의존성 패키지 설치 (Python 3.11 권장)
터미널을 열고 프로젝트 폴더 루트에서 가상환경을 활성화한 뒤 패키지를 설치합니다.
```bash
# 가상환경 생성 및 활성화
python3.11 -m venv .venv
source .venv/bin/activate

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 2. 로컬 VLM 모델 준비
다운로드받은 MLX 포맷 모델 폴더(예: `Gemma4_12B_4bit_mlx` 등)를 프로젝트 하위의 `models/` 디렉토리에 저장합니다.
```
ASMR_ADV/
└── models/
    └── Gemma4_12B_4bit_mlx/  <-- 다운로드한 모델 폴더
        ├── config.json
        ├── model.safetensors
        ├── processor_config.json
        └── tokenizer.json
```

### 3. 애플리케이션 실행

#### [번역 대시보드 구동]
```bash
streamlit run app.py
```
- 구동이 완료되면 자동으로 웹 브라우저(`http://localhost:8501`)가 열리며 번역 및 VLM 분석을 가동할 수 있습니다.

#### [AI 롤플레잉 익스텐션 구동]
```bash
uvicorn app_chat:app --host 0.0.0.0 --port 8000 --reload
```
- 구동 후 웹 브라우저에서 `http://localhost:8000`에 접속하여 로딩된 프로젝트 캐릭터와 실시간 채팅을 나눌 수 있습니다.
- 대화가 끝나면 UI의 `[모델 VRAM 해제 (Unload)]` 기능을 활용해 VRAM을 즉시 회수할 수 있습니다.

---

## 라이선스

이 프로젝트는 **MIT License**에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고해 주세요.
