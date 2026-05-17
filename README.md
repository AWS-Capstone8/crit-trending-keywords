# YouTube 실시간 키워드 TOP 100

YouTube Data API v3를 활용하여 한국 인기 급상승 동영상에서 트렌드 키워드를 추출하는 AWS Lambda 서비스입니다.

## 아키텍처

```
EventBridge (1시간마다 자동 실행)
    ↓
AWS Lambda (Python 3.14, 컨테이너 이미지)
    ├── YouTube Data API → 인기 동영상 200개 수집
    ├── kiwipiepy 형태소 분석 → 명사 키워드 추출
    ├── 조회수 가중치 기반 TOP 100 산출
    └── S3에 words.json 저장 + JSON 응답 반환
    
API Gateway (HTTP GET /words) → 외부에서 수동 호출 시 사용
```

## API 엔드포인트

```
GET https://t31dwqr9m5.execute-api.us-east-1.amazonaws.com/words
```

### 응답 형식

```json
[
  { "text": "게임", "value": 4422776 },
  { "text": "리그 오브 레전드", "value": 3071670 },
  { "text": "에스파", "value": 1940025 },
  ...
]
```

- `text`: 키워드
- `value`: 조회수 가중치 (해당 키워드가 등장한 동영상들의 조회수 합계)

## 키워드 추출 방식

1. YouTube Data API `videos.list(chart=mostPopular, regionCode=KR)`로 인기 동영상 최대 200개 수집
2. 각 동영상의 **제목 + 설명 + 태그**에서 텍스트 추출
3. **kiwipiepy** 형태소 분석기로 명사(NNG, NNP, NNB) 추출
4. 유튜브 보일러플레이트 불용어 필터링 (구독, 채널, 광고 등 60개 이상)
5. 키워드별로 등장한 동영상의 **조회수를 합산**하여 가중치 산출
6. 가중치 상위 100개를 반환

## AWS 리소스

| 리소스 | 이름 | 리전 |
|--------|------|------|
| Lambda | `youtube-trending-keywords` | us-east-1 |
| S3 | `pj-kmucd1-08-s3-trending-keywords` | us-east-1 |
| API Gateway | `pj-kmucd1-08-youtube-trending-api` | us-east-1 |
| EventBridge | `youtube-trending-keywords-hourly` | us-east-1 |
| ECR | `youtube-trending-keywords` | us-east-1 |

### Lambda 환경 변수

| 변수 | 값 |
|------|-----|
| `YOUTUBE_API_KEY` | YouTube Data API v3 키 |
| `S3_BUCKET` | `pj-kmucd1-08-s3-trending-keywords` |
| `REGION_CODE` | `KR` (기본값) |
| `S3_KEY` | `words.json` (기본값) |

### Lambda 설정

- 런타임: Python 3.14 (컨테이너 이미지)
- 메모리: 512MB
- 제한 시간: 60초
- IAM 역할: `SafeRole-pj-kmucd1-08`
- 트리거: EventBridge (1시간마다 자동 실행)

## 프로젝트 구조

```
crit-trending-keywords/
├── lambda_function.py   # Lambda 핸들러
├── Dockerfile           # 컨테이너 이미지 빌드용
├── requirements.txt     # kiwipiepy==0.23.1
├── deploy.sh            # 배포 스크립트 (ECR + Lambda + EventBridge 자동 설정)
└── README.md
```

## 배포 방법

### 자동 배포 (deploy.sh)

Docker + AWS CLI가 설치된 환경에서 실행:

```bash
export YOUTUBE_API_KEY=your_key_here
./deploy.sh
```

deploy.sh가 수행하는 작업:
1. S3 버킷 생성
2. ECR 리포지토리 생성
3. Docker 이미지 빌드 (linux/amd64) 및 ECR 푸시
4. Lambda 함수 생성 (컨테이너 이미지 기반)
5. EventBridge 스케줄 생성 (1시간마다 자동 실행)

### 코드만 업데이트 시

```bash
docker build --platform linux/amd64 -t youtube-trending-keywords .
docker tag youtube-trending-keywords:latest {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/youtube-trending-keywords:latest
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com
docker push {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/youtube-trending-keywords:latest

aws lambda update-function-code \
  --function-name youtube-trending-keywords \
  --image-uri {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/youtube-trending-keywords:latest \
  --region us-east-1
```

## 동작 확인

```bash
# API Gateway로 수동 호출
curl https://t31dwqr9m5.execute-api.us-east-1.amazonaws.com/words

# S3에서 직접 확인
aws s3 cp s3://pj-kmucd1-08-s3-trending-keywords/words.json - | head
```

## API 할당량

- `videos.list`: 호출당 1 unit (snippet + statistics)
- 1회 실행: 4 API 호출 = 4 units
- YouTube Data API 일일 기본 할당량: 10,000 units
- 1시간 간격 실행 시: 하루 96 units 소모 (쿼터의 1% 미만)
