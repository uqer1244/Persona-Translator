# PersonaASMR Translator

> **Apple Silicon 로컬 가속(MLX) 및 OpenAI 호환 API 기반의 상황극 대본 페르소나 번역 도구**

`PersonaASMR Translator`는 로컬 온디바이스 VLM/LLM 또는 OpenAI 호환 API를 활용하여, 서브컬처 콘텐츠(ASMR 대본)의 말투(페르소나)와 상황 맥락을 반영한 스트리밍 번역을 제공하는 도구입니다. 소개 이미지와 대본 본문을 함께 분석해 화자의 어조·관계·상황을 추출하고, 이를 번역 프롬프트에 지속적으로 주입해 일관된 화자 톤을 유지합니다.

---

## 주요 기능 (Key Features)

### 1. 이중 추론 백엔드 (Dual Inference Backend)
* **mlx-vlm (로컬 실행)**: `models/` 디렉토리를 자동 스캔해 MLX 포맷 로컬 모델 목록을 제공하며, 선택한 모델을 Unified Memory에 로드/언로드합니다. 메모리 부족으로 프로세스가 강제 종료되는 것을 막기 위해 8bit 12B급 모델은 별도 확인 절차를 거쳐야 로딩됩니다.
* **OpenAI 호환 API (원격/로컬 서버)**: `/v1/chat/completions` 규격을 따르는 모든 엔드포인트에 연결합니다. OpenAI 공식 API뿐 아니라 `llama.cpp`의 `llama-server` 같은 로컬 서버(`http://localhost:8080/v1`)도 동일한 클라이언트로 처리하며, Base URL·API Key·모델명을 사이드바에서 직접 지정합니다.
* **Vision 지원 여부 분기**: API 모델이 이미지 입력을 지원하지 않는 경우 체크박스를 꺼두면 소개 이미지 분석 단계를 자동으로 건너뛰고 텍스트 대본만 처리하여 호환성 오류를 예방합니다.

### 2. 페르소나 및 용어집 자동 추출
* **페르소나 분석**: 소개 이미지와 대본 도입부를 종합해 화자의 어조(tone), 청자와의 관계(relationship), 상황(situation), 번역 시 지켜야 할 핵심 규칙(key_rules)을 JSON으로 추출합니다.
* **용어집(Glossary) 자동 생성 및 마스터 병합**: 대본에서 고유명사·반복 표현을 뽑아 용어집을 구성하고, 프로젝트별 용어집을 전역 마스터 용어집과 병합해 시리즈물 간 번역 표기를 통일합니다.
* **고유명사 분류 및 이미지 노트**: 추출된 항목의 고유명사 여부를 판별하고, 드롭한 이미지별 분석 노트를 저장해 이후 번역 맥락으로 재사용합니다.

### 3. 자막 포맷 인식 스트리밍 번역
* **다중 포맷 입력**: `.txt`, `.srt`, `.vtt`, `.lrc`, `.pdf` 파일을 지원하며 여러 파일을 한 번에 업로드해 하나의 대본으로 병합할 수 있습니다.
* **타임코드 보존 청킹**: 업로드한 파일이 전부 자막 포맷이면 자막 모드로 전환되어, 타임코드 블록 단위로 청크를 나누고 번역 결과에도 원본 타임코드를 그대로 유지합니다.
* **개별/일괄 번역 및 실시간 채색**: 청크 단위 개별 재번역과 전체 일괄 번역을 모두 지원하며, 지시문·화자 하이라이트 채색을 실시간으로 적용합니다.

### 4. 프로젝트 격리 및 SQLite 로컬 데이터베이스 연동
* **체계적인 DB 통합 관리**: 프로젝트 정보, 번역 청크 상태, 페르소나 및 용어집, 이미지 노트가 단일 로컬 데이터베이스(`asmr_studio.db`)의 `projects` / `chunks` / `glossary` / `image_notes` 테이블에 통합 저장됩니다.
* **데이터 자동 이전(Migration)**: 구 버전의 `projects/` 폴더에 분산 저장되어 있던 JSON 백업 데이터(`progress.json`, `persona.json` 등)가 앱 기동 시 유실 없이 자동으로 SQLite 테이블로 마이그레이션됩니다.
* **DLsite 썸네일 크롤러 및 API 폴백**: 파일명·경로에서 RJ 코드를 추출해 DLsite 이미지 서버와 오픈 API에서 고화질 썸네일을 자동으로 내려받습니다.
* **로컬 파일 아카이브**: 썸네일 커버 및 원본 드롭 이미지 등 무거운 바이너리 자원은 `./projects/[RJCode]/` 경로에 격리 보존됩니다.

---

## 기술적 하이라이트 (Technical Highlights)

### 1. Apple Silicon MLX 로컬 가속 (`mlx-lm` / `mlx-vlm`)
* **100% 온디바이스(On-device) 로컬 연산**: 외부 API나 네트워크 연결 없이 Mac 로컬 환경에서 연산하며, Unified Memory 캐시 재사용 최적화를 통해 캐시 무효화를 방지하고 추론 및 생성 속도를 개선했습니다.
* **Gemma 4 MLX 패치**: 최신 Gemma 4 모델 구동 시 발생하는 `mlx_vlm` 시그니처 오류 및 Conv 가중치 전치 차원 불일치 버그를 런타임에 동적으로 후킹 우회(`core/patches.py`) 처리하여 구동합니다.
* **프롬프트 캐시 관리자**: `PromptCacheManager`가 청크 간 공통 프리픽스(페르소나·용어집 등 시스템 프롬프트)의 KV 캐시를 유지해 매 청크마다 발생하던 Prefill 재연산을 제거합니다.
* **모델 계열 자동 판별**: 로드된 모델의 계열(Gemma / Qwen 등)을 판별해 채팅 템플릿과 JSON 출력 규칙 프롬프트를 자동으로 전환합니다.

### 2. 고속 번역 및 스마트 컨텍스트 윈도우
* **Chain-of-Thought 단계 축소**: 번역 개시 시 발생하던 `[대본 분석]` CoT 단계를 생략하여 번역 프로세스 시작 대기 시간을 줄였습니다.
* **슬라이딩 컨텍스트 최적화**: 문맥 보존을 위한 이전 청크의 맥락을 직전 대사 3줄로 제한하여 프롬프트 토큰 사용량과 추론 대기 시간을 줄였습니다.
* **LLM JSON 출력 복구**: 모델이 뱉은 깨진 JSON(트레일링 콤마, 미닫힌 괄호, 코드펜스 혼입 등)을 `core/json_repair.py`에서 복구해 분석 단계가 단발성 출력 오류로 실패하지 않도록 합니다.

### 3. 런타임 어댑터 및 리소스 모니터링
* **백엔드 어댑터 추상화**: `core/model_runtime.py`의 `RuntimeBackendSpec`이 백엔드별 가용 여부와 Vision 지원 여부를 기술하고, 상위 로직은 래핑된 런타임 인터페이스만 호출하도록 분리했습니다.
* **실시간 리소스 게이지**: 사이드바에서 시스템 RAM 사용량, MLX Unified Memory의 Active / Peak / Cached 용량, 그리고 실시간 토큰 생성 속도(tok/s)를 함께 모니터링합니다.

---

## 기술 스택 (Tech Stack)

* **Core Engine**: `mlx-vlm`, `mlx-lm`, `transformers`
* **Remote Backend**: `requests` (OpenAI 호환 `/v1/chat/completions` 스트리밍 클라이언트)
* **Database**: `sqlite3` (프로젝트 정보, 청크 상태, 용어집, 이미지 노트 관리)
* **Framework**: `Streamlit` (3단계 워크플로우 GUI 대시보드)
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
OpenAI 호환 API로 번역을 수행하려면, 프로젝트 루트에 `.env` 파일을 생성하고 API 키를 입력합니다. 사이드바의 API Key 입력란에 자동으로 채워집니다.

```text
OPENAI_API_KEY=sk-your-key-here
```

`llama.cpp`의 `llama-server` 등 로컬 서버에 붙는 경우에는 API Key가 필요 없으므로 이 단계를 건너뛰고, 사이드바에서 Base URL만 `http://localhost:8080/v1` 형태로 지정하면 됩니다.

### 3. 로컬 VLM/LLM 모델 준비
로컬(MLX) 백엔드를 사용할 때만 필요합니다. 다운로드받은 MLX 포맷 모델 폴더를 프로젝트 하위의 `models/` 디렉토리에 저장하면 사이드바 목록에 자동으로 나타납니다.

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

```bash
streamlit run app.py
```
* 실행 시 자동으로 웹 브라우저(`http://localhost:8501`)가 열립니다.

---

## 프로젝트 구조 (Directory Structure)

```text
ASMR_ADV/
├── app.py                     # Streamlit 메인 진입점
├── asmr_studio.db             # 로컬 SQLite 데이터베이스 (git 제외)
├── .env                       # 환경 변수 설정 파일 (API Key 등)
├── core/                      # VLM 분석 및 번역 코어 엔진
│   ├── analyzer.py            # VLM 이미지 분석, 페르소나 / 용어집 추출
│   ├── database.py            # SQLite DB 초기화, thread-safe 쿼리, 레거시 마이그레이션
│   ├── document.py            # PDF 텍스트 추출, 줄바꿈 보정, 일반/자막 청킹
│   ├── env.py                 # .env 파일 파싱 및 환경 변수 주입
│   ├── json_repair.py         # LLM JSON 출력 복구 모듈
│   ├── model_generation.py    # 로컬 / API 공통 추론 인터페이스 및 모델 계열 판별
│   ├── model_manager.py       # 로컬 MLX 모델 로딩 및 메모리 해제(Unload)
│   ├── model_runtime.py       # 백엔드 어댑터 스펙 및 런타임 래퍼
│   ├── openai_compat.py       # OpenAI 호환 /v1/chat/completions 스트리밍 클라이언트
│   ├── patches.py             # Gemma 4 mlx_vlm 런타임 후킹 패치
│   ├── progress_store.py      # 진행 상황 저장 위임, DLsite 썸네일, 용어집 백업
│   ├── session_state.py       # Streamlit 세션 상태 초기화
│   ├── subtitle_utils.py      # 자막 타임코드 파싱 및 번역 결과 재조립
│   ├── translation_prompts.py # 번역 프롬프트 템플릿
│   └── translator.py          # 로컬 가속 스트리밍 번역 엔진 및 프롬프트 캐시
├── ui/                        # 3단계 워크플로우 GUI 컴포넌트
│   ├── app_shell.py           # 페이지 설정, 전역 CSS, 탭 구성
│   ├── sidebar.py             # 백엔드 선택, 모델 로딩, 하이퍼파라미터, 리소스 게이지
│   ├── tab_script.py          # 1. 대본불러오기 탭
│   ├── tab_persona.py         # 2. 페르소나, 단어장, 이미지 분석 탭
│   └── tab_translate.py       # 3. 번역 탭
├── projects/                  # 미디어 파일 및 원본 이미지 격리 아카이브 (RJCode별)
├── DLdata/                    # 원본 오디오 및 시나리오 리소스 (Read-Only)
└── models/                    # 로컬 LLM / VLM 모델 보존 디렉토리
```

---

## 라이선스
이 프로젝트는 **MIT License**에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고해 주세요.
