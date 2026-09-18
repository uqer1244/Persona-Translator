# Persona Translator

> **oMLX 등 OpenAI 호환 추론 서버 기반의 상황극 대본 페르소나 번역 도구**

Persona Translator는 외부 oMLX/OpenAI 호환 서버에 연결해 대본 전체의 번역 페르소나를 먼저 분석한 뒤, 청크 단위 스트리밍 번역과 부분 재번역을 제공하는 FastAPI 웹 애플리케이션입니다. 이 프로젝트의 8502 포트 서비스는 모델을 직접 로드하지 않습니다.

## 주요 기능

### 전체 대본 페르소나 분석

- 번역 전에 LLM이 전체 대본을 읽고 말투, 화자-청자 관계, 상황, 호칭, 핵심 번역 규칙을 분석합니다.
- 분석 결과는 모든 청크와 부분 재번역 프롬프트에 적용됩니다.
- 모델이 JSON이 아닌 일반 텍스트나 잘린 응답을 반환해도 번역 작업을 중단하지 않는 best-effort 처리를 사용합니다.

### OpenAI 호환 추론 서버

- `POST /v1/chat/completions` 스트리밍 번역
- `GET /v1/models` 연결 테스트와 모델 목록 확인
- oMLX Base URL, API Key, 모델명 설정
- 모델 서버가 처리하는 입력·출력 한도에 맞춰 고정 청크와 출력 상한을 사용

### 청크 작업과 부분 재번역

- `.txt`, `.srt`, `.vtt`, `.lrc`, `.pdf` 텍스트 처리 기반
- 자막 타임코드와 원본 줄 구조 보존
- 전체 번역 및 개별 청크 재번역
- SSE를 통한 토큰 단위 진행 상태 표시
- 번역 설정은 브라우저 `localStorage`에 저장

## 설치 및 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8502
```

브라우저에서 `http://127.0.0.1:8502`를 열고 모델 연결 패널에 oMLX의 OpenAI 호환 Base URL을 입력합니다. 기본값은 `http://127.0.0.1:8000/v1`입니다. 로컬 oMLX 서버는 일반적으로 API Key를 비워 둡니다.

## API 개요

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/health` | 서비스 상태 확인 |
| `POST` | `/api/connection/test` | `/v1/models` 연결 및 모델 확인 |
| `POST` | `/api/projects` | 대본 프로젝트 생성 |
| `GET` | `/api/projects/{id}` | 프로젝트 상태 조회 |
| `PATCH` | `/api/projects/{id}` | 페르소나·용어집 수정 |
| `POST` | `/api/projects/{id}/analyze-persona` | 전체 대본 페르소나 분석 |
| `POST` | `/api/projects/{id}/translate` | 전체 청크 번역 |
| `POST` | `/api/projects/{id}/chunks/{index}/translate` | 단일 청크 번역 |
| `GET` | `/api/projects/{id}/events` | SSE 진행 이벤트 |

## 프로젝트 구조

```text
ASMR_ADV/
├── app.py                     # FastAPI 진입점
├── web_server.py              # API, 작업 큐, SSE 이벤트 스트림
├── web/
│   └── index.html             # 반응형 번역 작업 UI
├── core/
│   ├── document.py            # 문서 추출, 토큰 추정, 청킹
│   ├── json_repair.py         # 분석 응답의 JSON 보정
│   ├── openai_compat.py       # OpenAI 호환 스트리밍 클라이언트
│   ├── subtitle_utils.py      # 자막 파싱과 결과 재조립
│   ├── translation_prompts.py # 번역·재번역 프롬프트
│   └── translator.py          # 청크 번역 엔진
└── requirements.txt
```

현재 프로젝트와 번역 결과는 FastAPI 프로세스 메모리에 보관됩니다. 프로세스를 재시작하면 활성 프로젝트가 사라지므로, 장기 운영 시 SQLite 또는 별도 저장소를 추가해야 합니다.

## 라이선스

이 프로젝트는 **MIT License**에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
