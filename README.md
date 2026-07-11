# PersonaASMR Studio

> **Apple Silicon GPU 로컬 가속(MLX) 기반의 상황극 대본 전문 맞춤형 번역 및 하이브리드 인스턴트 캐릭터 롤플레잉 플랫폼**

`PersonaASMR Studio`는 로컬 온디바이스 VLM/LLM을 활용하여 서브컬처 콘텐츠 특유의 섬세한 말투(페르소나)와 상황맥락을 반영하는 맞춤형 번역 도구이자, 번역 과정에서 축적된 캐릭터 자산을 활용하여 실시간 AI 캐릭터 롤플레잉(RP)을 나눌 수 있는 올인원 플랫폼입니다.

---

## 핵심 기능 (Core Features)

### 1. Apple Silicon GPU 로컬 가속 & 극한의 최적화 (`mlx-lm` / `mlx-vlm`)
* **100% 온디바이스(On-device) & 하이브리드 지원**: 외부 API 키나 네트워크 연결 없이 Mac 내부에서 로컬로 연산이 가능하며, 선택 시 외부 OpenRouter API를 연동해 하이브리드로 사용할 수도 있습니다.
* **Unified Memory 캐시 재사용 최적화**: GPU VRAM 캐시가 무효화되는 현상을 제거하여 기존 추론 및 텍스트 생성 속도를 **2배~5배 이상 비약적으로 가속**했습니다.
* **VLM Prefill 시간 절반 단축**: 불필요한 KV 캐시 압축 파라미터를 해제하고 기본 FP16 캐시 할당기를 활용하여 첫 토큰 생성 반응 속도(Prefill)를 0.79초에서 **0.38초로 2배 단축**했습니다.
* **스트리밍 속도 실시간 계측**: 첫 토큰 출력 시점부터 갱신 타임 스탬프를 다시 열어 실제 GPU 생성 속도(약 14~15 tok/s)를 왜곡 없이 정확하게 표시합니다.

### 2. 프로젝트 격리 및 데이터 보관소 일원화
* **`projects/` 보관함 신설**: 모든 번역 진행도(`progress.json`), 캐릭터 설정(`persona.json`), 채팅 내역(`chats.json`), 대표 썸네일, 추출 텍스트(`scenario.txt`) 및 분석 이미지는 오직 `./projects/[RJCode]/` 하위에만 격리하여 저장합니다.
* **`DLdata/` 완전 읽기 전용화 (Prisinte Read-Only)**: 사용자의 순수 원본 오디오 및 자원 폴더를 안전하게 지키기 위해, 앱이 `DLdata` 내부의 파일을 절대 수정하거나 덮어쓰지 않습니다.
* **자동 이전(Migration) 탑재**: 예전 버전에서 기존 `DLdata/RJXXXX/` 내에 분산 저장해 두었던 설정 파일들을 읽을 시, 새 `projects/` 폴더로 데이터를 자동 이동시켜 기존 진행을 유지해 줍니다.

### 3. 작업 생산성 극대화 UI & 스캔 기능
* **원클릭 프로젝트 완전 복원 (One-click Restore)**: 대본 입력 화면에 썸네일 카드로 배치되는 프로젝트 보관함 목록을 렌더링하여, **`[복원]`** 클릭 1초 만에 세션을 완벽히 복구합니다.
* **DLsite 썸네일 자동 다운로더**: 입력되거나 스캔된 RJ 코드를 기반으로 DLsite 이미지 CDN 서버에서 6자리(doujin) 및 8자리(serial) 매핑 룰을 추적하여 대표 고화질 썸네일을 자동으로 다운로드합니다.
* **디렉토리 구조 트리 뷰 & 파일 미리보기**:
  * 선택된 로컬 폴더의 파일 목록을 이모지(📁, 📝, 🖼️, 🎵)와 들여쓰기가 가미된 텍스트 트리 구조로 직관적으로 표시합니다.
  * 폴더 내 이미지 파일들을 UI 상에서 즉시 감상할 수 있는 미리보기 뷰어를 지원합니다.
  * 대표 썸네일로 설정할 이미지를 크롤링 결과 또는 스캔 이미지 중에서 자유롭게 커스텀 선택할 수 있습니다.

### 4. 고속 번역 및 스마트 컨텍스트 윈도우
* **Chain-of-Thought 단계 축소**: 번역 시작 시 15~20줄의 토큰 연산 낭비를 부르던 `[대본 분석]` CoT 단계를 제거하여, 번역 시작 및 전체 작업 속도를 **2배 이상 향상**시켰습니다.
* **슬라이딩 컨텍스트 최적화**: 흐름의 부드러움을 유지하기 위해 전송하던 이전 청크 맥락을 **직전 대사 3줄**로 최적 Trimming하여 프롬프트 토큰 크기를 절감하고 추론 대기 시간을 극소화했습니다.

### 5. 대본 기반 몰입형 AI 캐릭터 챗 & 롤플레잉
* **미번역 상태 선제 채팅**: 번역이 개시되기 전이라도 대본만 불러오면 프로젝트를 즉각 선개방하여 캐릭터와의 대화 롤플레잉을 나눌 수 있습니다.
* **구체적 사건 기반 질문 추천**: 뻔한 질문 추천 대신, 대본 내의 실제 사건과 묘사(예: "아까 나한테 끓여준 코코아...")를 직접 인용하며 캐릭터에게 말을 거는 **대본 연동 추천 질문**이 탑재됩니다.

### 6. 오픈라우터(OpenRouter) API 완벽 통합
* **일일 사용량 보호 제한**: 무료 모델 등 사용 시 한도 초과 에러 방지를 위해 일일 호출 건수를 제한하며, **최대 900회** 도달 시 자동으로 추가 요청을 차단하고 알림을 띄웁니다.
* **실시간 한도 표시 게이지**: 사이드바에 실시간 API 사용량 게이지(Progress Bar)를 추가하여 잔여 횟수를 시각적으로 직관적이게 모니터링합니다.
* **자동 API Key 연동**: `.env` 파일에 키를 작성해 두면 Streamlit 로딩 시 자동으로 사이드바 폼에 적용되어 편리한 개발 환경을 선사합니다.
* **출력 토큰 3000개 대폭 확장**: 원격 API 번역 요청에 한하여 최대 출력 토큰을 3000개로 대폭 확장하여 긴 대사나 복잡한 청크도 잘림 없이 번역됩니다.
* **멀티모달 자동 우회 (VLM Bypass)**: 텍스트 전용 API 모델 사용 시 이미지 요약/분석을 자동으로 우회(Skip)하여 호환성 에러를 완벽하게 예방합니다.

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

### 2. 환경변수 및 API 설정 (선택사항)
오픈라우터 API를 이용해 번역/채팅을 수행하려면, 프로젝트 루트에 `.env` 파일을 생성하고 오픈라우터 API 키를 입력합니다.
```text
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### 3. 로컬 VLM/LLM 모델 준비
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

### 4. 애플리케이션 실행
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
├── .env                  # 환경 변수 설정 파일 (API Key 등)
├── core/                 # VLM 분석, 번역 및 RAG 코어 엔진
│   ├── analyzer.py
│   ├── chat_engine.py
│   ├── model_manager.py
│   ├── openrouter.py     # 오픈라우터 API 통신 모듈
│   ├── progress_store.py
│   └── translator.py
├── ui/                   # 3분할 워크플로우 개별 탭 GUI 컴포넌트
│   ├── sidebar.py
│   ├── tab_script.py
│   ├── tab_persona.py
│   ├── tab_translate.py
│   └── tab_chat.py
├── projects/             # 번역/페르소나/채팅 히스토리 격리 보관소
├── DLdata/               # 원본 오디오 및 시나리오 리소스 (Read-Only)
├── models/               # 로컬 LLM / VLM 모델 보존 디렉토리
└── plans/                # 마스터 기획 사양서
```

---

## 라이선스
이 프로젝트는 **MIT License**에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고해 주세요.
