# PersonaASMR Studio

> **Apple Silicon 로컬 가속(MLX) 및 SQLite 기반의 상황극 대본 번역 & RisuAI 캐릭터 카드 제작 도구**

`PersonaASMR Studio`는 로컬 온디바이스 VLM/LLM을 활용하여 서브컬처 콘텐츠(ASMR 대본)의 말투(페르소나)와 상황 맥락을 반영하는 스트리밍 번역 기능을 제공하며, 추출한 데이터와 사건 지도를 기반으로 RisuAI 캐릭터 카드(.charx)를 자동으로 설계 및 조립해 주는 제작 지원 도구입니다.

---

## 주요 기능 (Key Features)

### 1. 프로젝트 격리 및 SQLite 로컬 데이터베이스 연동
* **체계적인 DB 통합 관리**: 프로젝트 정보, 번역 청크 상태, 페르소나 및 용어집 데이터가 단일 로컬 데이터베이스(`asmr_studio.db`)에 통합 저장되어 데이터 정합성을 유지합니다.
* **데이터 자동 이전(Migration)**: 구 버전의 `projects/` 폴더 내에 분산 저장되어 있던 JSON 백업 데이터(`progress.json`, `persona.json` 등)가 앱 기동 시 유실 없이 자동으로 SQLite DB 테이블로 완벽히 마이그레이션됩니다.
* **로컬 파일 아카이브**: 썸네일 커버 및 원본 드롭 이미지 등 무거운 바이너리 자원은 `./projects/[RJCode]/` 경로에 안전하게 격리 보존됩니다.

### 2. 프로젝트 관리 및 스캔 UI 기능
* **프로젝트 복원 (Restore)**: 라이브러리 화면에서 이전 작업 카드의 **`[복원]`** 버튼만 누르면 데이터베이스에서 세션 상태를 복구하여 즉시 번역이나 봇카드 제작 단계로 복귀합니다.
* **DLsite 썸네일 크롤러 및 API 폴백**: 입력 또는 스캔된 RJ 코드를 기반으로 DLsite 이미지 서버 및 오픈 API에서 고화질 썸네일을 자동으로 다운로드합니다.
* **디렉토리 구조 트리 뷰 및 미리보기**:
  * 선택된 로컬 폴더의 파일 목록을 이모지(📁, 📝, 🖼️, 🎵)가 포함된 텍스트 트리 구조로 출력합니다.
  * 폴더 내 이미지 미리보기 뷰어를 지원하며 대표 썸네일을 쉽게 지정할 수 있습니다.

### 3. 봇카드 및 로어북 생성 자동화
* **RisuAI V3 맞춤형 카드 조립**: 대본 번역 과정에서 추출한 캐릭터 어조, 청자-화자의 관계, 세계관 상황을 RisuAI 캐릭터 포맷에 맞게 포매팅합니다.
* **로어북 분리 구성**: 캐릭터 성격 및 말투는 설명(`description`)에 남기고, 대본 전체 요약을 통해 도출한 서사적 사건 연대기는 별도 로어북(Character Book) 항목으로 분할 자동 배치합니다.
* **`.charx` 저장 포맷**: 브라우저 다운로드 시 확장자가 `.zip`으로 임의 변경되는 현상을 방지하기 위해 파일 MIME 타입을 `octet-stream`으로 설정합니다.

### 4. 오픈라우터(OpenRouter) API 연동
* **일일 사용량 제한**: API 호출 과다로 인한 청구 에러 방지를 위해 일일 호출 건수가 제한치(최대 900회)에 도달하면 추가 요청을 자동 차단하고 알림을 표기합니다.
* **실시간 사용량 게이지**: 사이드바에 실시간 API 사용량 게이지(Progress Bar)를 표시하여 잔여 사용 횟수를 모니터링할 수 있습니다.
* **API Key 자동 연동**: `.env` 파일에 설정된 오픈라우터 API 키를 사이드바 입력 폼에 자동으로 적용합니다.

---

## 기술적 하이라이트 (Technical Highlights)

### 1. Apple Silicon MLX 로컬 가속 (`mlx-lm` / `mlx-vlm`)
* **100% 온디바이스(On-device) 로컬 연산**: 외부 API나 네트워크 연결 없이 Mac 로컬 환경에서 연산하며, Unified Memory 캐시 재사용 최적화를 통해 캐시 무효화를 방지하고 기존 추론 및 생성 속도를 개선했습니다.
* **Gemma 4 MLX 패치**: 최신 Gemma 4 모델 구동 시 발생하는 `mlx_vlm` 시그니처 오류 및 Conv 가중치 전치 차원 불일치 버그를 런타임에 동적으로 후킹 우회([core/patches.py](file:///Users/a0000/Documents/py/ASMR_ADV/core/patches.py)) 처리하여 완벽히 구동합니다.
* **VLM Prefill 시간 단축**: KV 캐시 압축 파라미터 최적화와 FP16 캐시 할당기 활용을 통해 첫 토큰 생성(Prefill) 반응 속도를 약 0.38초 수준으로 단축했습니다.

### 2. 고속 번역 및 스마트 컨텍스트 윈도우
* **Chain-of-Thought 단계 축소**: 번역 개시 시 발생하던 `[대본 분석]` CoT 단계를 생략하여 번역 프로세스 시작 대기 시간을 줄였습니다.
* **슬라이딩 컨텍스트 최적화**: 문맥 보존을 위한 이전 청크의 맥락을 직전 대사 3줄로 제한하여 프롬프트 토큰 사용량과 추론 대기 시간을 줄였습니다.

### 3. Map-Reduce 기반 계층적 압축 및 컨텍스트 최적화
* **Map (청크 요약)**: 전체 대본을 3,500자 단위의 청크로 분할한 뒤, 각 구간을 150~250자 수준의 핵심 요약문으로 LLM을 통해 압축하고 캐싱하여 메모리(OOM) 부하를 방지합니다.
* **Reduce (사건 지도 추출)**: 요약된 시퀀스를 결합해 인과관계가 구조화된 '사건 및 인과관계 지도(Event Map)'를 1회 추론으로 추출하여 긴 대본 분석 시의 정보 누락을 방지하고 봇카드 로어북에 바인딩합니다.

### 4. 하이브리드 통신 및 외부 API 최적화
* **출력 토큰 제한 확장**: OpenRouter API 연동 시 최대 출력 토큰을 3,000개로 늘려 긴 텍스트 번역 시의 잘림 현상을 예방합니다.
* **멀티모달 자동 우회 (VLM Bypass)**: 텍스트 전용 API 모델을 호출할 때는 이미지 요약 및 분석 단계를 자동으로 생략하여 호환성 오류를 예방합니다.

---

## 기술 스택 (Tech Stack)

* **Core Engine**: `mlx-vlm`, `mlx-lm`, `transformers`
* **Database**: `sqlite3` (프로젝트 정보, 청크 상태, 용어집 데이터 관리)
* **Framework**: `Streamlit` (번역 및 RisuAI 캐릭터 카드 제작 GUI 대시보드)
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
오픈라우터 API를 이용해 번역/카드 생성을 수행하려면, 프로젝트 루트에 `.env` 파일을 생성하고 오픈라우터 API 키를 입력합니다.
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

```bash
streamlit run app.py
```
* 실행 시 자동으로 웹 브라우저(`http://localhost:8501`)가 열립니다.

---

## 프로젝트 구조 (Directory Structure)

```text
ASMR_ADV/
├── app.py                # Streamlit 메인 진입점
├── asmr_studio.db        # 로컬 SQLite 데이터베이스 (git 제외)
├── .env                  # 환경 변수 설정 파일 (API Key 등)
├── core/                 # VLM 분석, 번역, 봇카드 생성 코어 엔진
│   ├── analyzer.py       # VLM 이미지 분석 및 요약 엔진
│   ├── bot_card.py       # 봇카드 생성 오케스트레이터 (Map-Reduce)
│   ├── bot_card_prompts.py # 봇카드 합성 및 사건 지도 추출용 프롬프트
│   ├── bot_card_storage.py # 봇카드 캐시 및 백업 데이터 입출력
│   ├── database.py       # SQLite DB 초기화 및 thread-safe 쿼리 제어
│   ├── document.py       # 대본 텍스트/SRT/PDF 로드 및 줄바꿈 보정
│   ├── event_mapper.py   # 대본 슬라이싱, 1차 압축(Map) 및 사건 지도 추출(Reduce)
│   ├── json_repair.py    # LLM JSON 출력 복구 라이브러리
│   ├── model_generation.py # LLM 로컬/오픈라우터 호출 및 추론 인터페이스
│   ├── model_manager.py  # 로컬 MLX 모델 로딩 및 메모리 해제(Unload)
│   ├── model_runtime.py  # VLM 프로세서 및 모델 패치 제어
│   ├── openrouter.py     # 오픈라우터 API 통신 모듈
│   ├── progress_store.py # 프로젝트 SQLite DB 입출력 위임 및 로컬 복원
│   ├── refiner.py        # 대본 정제 가공 모듈
│   ├── risu_card.py      # RisuAI V3 규격 맞춤형 카드 조립 및 Lorebook 빌드
│   └── translator.py     # 로컬 가속 스트리밍 번역 엔진
├── ui/                   # 6단계 워크플로우 개별 탭 GUI 컴포넌트
│   ├── sidebar.py
│   ├── tab_library.py    # 0. 라이브러리 탭
│   ├── tab_script.py     # 1. 대본불러오기 탭
│   ├── tab_persona.py    # 2. 페르소나, 단어장, 이미지 분석 탭
│   ├── tab_translate.py  # 3. 번역 탭
│   ├── tab_refine.py     # 4. 저장 탭
│   └── tab_botcard.py    # 5. 봇카드 만들기 탭
├── projects/             # 미디어 파일 및 원본 이미지 격리 아카이브 (RJCode별)
├── DLdata/               # 원본 오디오 및 시나리오 리소스 (Read-Only)
├── models/               # 로컬 LLM / VLM 모델 보존 디렉토리
└── plans/                # 마스터 기획 사양서 및 마이그레이션 기획
```

---

## 라이선스
이 프로젝트는 **MIT License**에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고해 주세요.
