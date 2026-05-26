# YouTube 실시간 트렌드 데이터 수집

YouTube Data API v3 + AWS Bedrock를 활용하여 한국 인기 급상승 동영상에서 트렌드 키워드를 추출하고, 트렌드 페이지용 데이터를 생성하는 AWS Lambda 서비스입니다.

## 아키텍처

```
EventBridge (1시간마다 자동 실행)
    ↓
AWS Lambda (Python 3.14)
    ├── YouTube Data API → 인기 동영상 200개 수집
    ├── kiwipiepy 형태소 분석 → 명사 키워드 추출
    ├── 조회수 가중치 기반 TOP 100 산출
    ├── 음악 차트 국내/글로벌 수집
    ├── 카테고리별 1위 영상 수집
    ├── 해시태그 빈도 집계
    ├── AWS Bedrock (Claude Haiku) → AI 트렌드 요약 + 인기 이유 분석
    └── S3에 words.json + trending.json 저장
```

## S3 출력 파일

### words.json (기존)

키워드 TOP 100 (워드클라우드용)

```json
[
  {"text": "게임", "value": 6059913},
  {"text": "리그 오브 레전드", "value": 3295535}
]
```

### trending.json (신규)

트렌드 페이지 전체 데이터

```json
{
  "updatedAt": "2026-05-26T14:34:00+00:00",
  "aiSummary": "오늘 유튜브에서 뭐가 뜨고 있는지 AI 2~3문장 요약",
  "popularVideos": [
    {
      "rank": 1,
      "videoId": "...",
      "title": "영상 제목",
      "thumbnailUrl": "https://i.ytimg.com/vi/.../mqdefault.jpg",
      "videoUrl": "https://www.youtube.com/watch?v=...",
      "channelTitle": "채널명",
      "hashtags": ["태그1", "태그2"],
      "aiAnalysis": "인기 이유 한 줄",
      "views": 74695,
      "publishedAt": "2026-05-25T09:00:03Z"
    }
  ],
  "musicChartKR": [
    {"title": "노래 제목", "artist": "가수", "videoUrl": "https://..."}
  ],
  "musicChartGlobal": [
    {"title": "Song Title", "artist": "Artist", "videoUrl": "https://..."}
  ],
  "categoryTop1": [
    {
      "categoryId": "20",
      "categoryName": "게임",
      "videoId": "...",
      "title": "영상 제목",
      "thumbnailUrl": "https://...",
      "videoUrl": "https://...",
      "channelTitle": "채널명",
      "hashtags": ["태그1"],
      "aiAnalysis": "인기 이유 한 줄",
      "views": 123456,
      "publishedAt": "2026-05-25T12:00:00Z"
    }
  ],
  "hotKeywords": [
    {"text": "게임", "value": 6059913}
  ],
  "hotHashtags": [
    {"text": "shorts", "value": 5000000}
  ]
}
```

## AWS 리소스

| 리소스 | 이름 | 리전 |
|--------|------|------|
| Lambda | `pj-kmucd1-08-youtube-trending` | us-east-1 |
| S3 | `pj-kmucd1-08-s3-trending-keywords` | us-east-1 |
| API Gateway | `pj-kmucd1-08-youtube-trending-api` | us-east-1 |
| EventBridge | `youtube-trending-keywords-hourly` | us-east-1 |

### Lambda 환경 변수

| 변수 | 설명 |
|------|------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 키 |
| `S3_BUCKET` | `pj-kmucd1-08-s3-trending-keywords` |
| `REGION_CODE` | `KR` (기본값) |
| `S3_KEY` | `words.json` (기본값) |
| `S3_TRENDING_KEY` | `trending.json` (기본값) |

### Lambda 설정

- 런타임: Python 3.14
- 메모리: 512MB
- 제한 시간: 120초
- IAM 역할: `SafeRole-pj-kmucd1-08` (Bedrock + S3 접근)
- 트리거: EventBridge (1시간마다 자동 실행)

## API 할당량 (1회 실행당)

| API 호출 | 유닛 |
|---------|------|
| 인기 동영상 200개 (4페이지) | 4 units |
| 음악 차트 국내 | 1 unit |
| 음악 차트 글로벌 | 1 unit |
| 카테고리별 1위 (14개) | 14 units |
| **합계** | **20 units** |
| 1시간 간격 실행 시 일일 | **480 units** |

AI 비용 (Bedrock Claude Haiku):
- 인기 동영상 5개 × 인기 이유 = 5회
- 카테고리별 1위 12~14개 × 인기 이유 = 14회
- 트렌드 요약 1회
- **합계: ~20회/시간, ~$0.04/시간, ~$1/일**

## 배포 방법

1. 의존성 패키징:
```bash
pip install kiwipiepy -t ./package
cd package && zip -r9 /tmp/lambda-deploy.zip . && cd ..
zip -g /tmp/lambda-deploy.zip lambda_function.py
```

2. S3 업로드:
```bash
aws s3 cp /tmp/lambda-deploy.zip s3://pj-kmucd1-08-s3-trending-keywords/lambda-deploy.zip
```

3. Lambda 콘솔 → "코드" 탭 → "다음에서 업로드" → "Amazon S3 위치" → `s3://pj-kmucd1-08-s3-trending-keywords/lambda-deploy.zip`

## 변경 이력

### 2026-05-26
- **trending.json 생성 추가**
  - 인기 동영상 TOP5 (썸네일, URL, 제목, 해시태그, 조회수, 업로드 날짜)
  - 음악 차트 국내/글로벌 TOP10 (제목, 가수, URL)
  - 카테고리별 1위 영상 (14개 카테고리)
  - 핫 해시태그 TOP20 (태그 빈도 집계)
  - AI 트렌드 요약 (Bedrock Claude Haiku)
  - AI 인기 이유 분석 (인기 동영상 + 카테고리별 1위)
- **Gemini → Bedrock 변경** (Gemini 무료 할당량 초과 문제)

### 2026-05-14
- 초기 구현: 인기 동영상 200개에서 키워드 TOP 100 추출 → words.json
