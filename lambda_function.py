import json
import os
import re
from collections import Counter
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from datetime import datetime, timezone

import boto3
from kiwipiepy import Kiwi

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
REGION_CODE = os.environ.get("REGION_CODE", "KR")
S3_BUCKET = os.environ.get("S3_BUCKET", "pj-kmucd1-08-s3-trending-keywords")
S3_KEY = os.environ.get("S3_KEY", "words.json")
S3_TRENDING_KEY = os.environ.get("S3_TRENDING_KEY", "trending.json")
MAX_RESULTS = 50
PAGES = 4
TOP_N = 100

NOUN_TAGS = {"NNG", "NNP", "NNB"}
MIN_KEYWORD_LEN = 2

STOPWORDS = {
    "구독", "채널", "광고", "문의", "가입", "멤버십", "후원", "댓글", "알림",
    "좋아요", "싫어요", "공유", "저장", "시청", "조회", "링크", "클릭",
    "유튜브", "브금", "아프리카", "트위치", "인스타", "인스타그램",
    "트위터", "페이스북", "네이버", "카페", "블로그", "홈페이지",
    "이메일", "메일", "업로드", "콘텐츠", "컨텐츠", "주소",
    "제공", "포함", "제작", "편집", "출처", "사용", "설정", "관련",
    "비즈니스", "공식", "문의처", "강의", "추천", "리뷰", "업데이트",
    "영상", "방송", "생방송", "방송국", "감사", "시작", "정보",
    "가능", "경우", "부분", "이상", "이하", "정도", "대상",
    "전체", "확인", "부탁", "각종", "이동", "진행", "개인",
    "오늘", "내용", "정리", "소식", "저녁", "시간", "사랑",
    "바람", "마음", "노래", "음악", "사람", "모습", "세계",
}

CATEGORY_IDS = {
    "1": "영화 / 애니메이션", "2": "자동차 / 교통", "10": "음악",
    "15": "반려동물", "17": "스포츠", "19": "여행 / 이벤트",
    "20": "게임", "22": "인물 / 블로그", "23": "코미디",
    "24": "엔터테인먼트", "25": "뉴스 / 정치", "26": "노하우 / 스타일",
    "27": "교육", "28": "과학 / 기술",
}

kiwi = Kiwi()
s3 = boto3.client("s3")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def call_gemini(prompt):
    """Gemini API 호출"""
    if not GEMINI_API_KEY:
        return ""
    try:
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        req = Request(f"{GEMINI_URL}?key={GEMINI_API_KEY}", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""


def yt_api(endpoint, params):
    params["key"] = API_KEY
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urlencode(params)}"
    with urlopen(Request(url)) as resp:
        return json.loads(resp.read())


def fetch_trending_videos():
    """인기 동영상 최대 200개 수집"""
    videos = []
    page_token = None
    for _ in range(PAGES):
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": REGION_CODE,
            "maxResults": MAX_RESULTS,
        }
        if page_token:
            params["pageToken"] = page_token
        data = yt_api("videos", params)
        for item in data.get("items", []):
            sn = item["snippet"]
            st = item.get("statistics", {})
            videos.append({
                "videoId": item["id"],
                "title": sn.get("title", ""),
                "description": sn.get("description", ""),
                "tags": sn.get("tags", []),
                "channelTitle": sn.get("channelTitle", ""),
                "thumbnailUrl": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "publishedAt": sn.get("publishedAt", ""),
                "categoryId": sn.get("categoryId", ""),
                "views": int(st.get("viewCount", 0)),
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return videos


def fetch_music_chart(region_code=None):
    """음악 카테고리 인기 영상 TOP10"""
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "videoCategoryId": "10",
        "maxResults": 10,
    }
    if region_code:
        params["regionCode"] = region_code
    data = yt_api("videos", params)
    chart = []
    for item in data.get("items", []):
        sn = item["snippet"]
        chart.append({
            "title": sn.get("title", ""),
            "artist": sn.get("channelTitle", ""),
            "videoUrl": f"https://www.youtube.com/watch?v={item['id']}",
        })
    return chart


def fetch_category_top1():
    """카테고리별 1위 영상"""
    results = []
    for cat_id, cat_name in CATEGORY_IDS.items():
        try:
            params = {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "videoCategoryId": cat_id,
                "regionCode": REGION_CODE,
                "maxResults": 1,
            }
            data = yt_api("videos", params)
            items = data.get("items", [])
            if items:
                item = items[0]
                sn = item["snippet"]
                st = item.get("statistics", {})
                tags = sn.get("tags", [])
                results.append({
                    "categoryId": cat_id,
                    "categoryName": cat_name,
                    "videoId": item["id"],
                    "title": sn.get("title", ""),
                    "thumbnailUrl": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                    "videoUrl": f"https://www.youtube.com/watch?v={item['id']}",
                    "channelTitle": sn.get("channelTitle", ""),
                    "hashtags": [t for t in tags[:5] if t],
                    "aiAnalysis": call_gemini(f"유튜브 {cat_name} 카테고리 1위 영상 \"{sn.get('title','')}\"이 인기 있는 이유를 한국어 한 줄(30자 이내)로. 이유만 출력."),
                    "views": int(st.get("viewCount", 0)),
                    "publishedAt": sn.get("publishedAt", ""),
                })
        except Exception:
            pass
    return results


def extract_keywords_from_text(text):
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[#@]", " ", text)
    keywords = set()
    for token in kiwi.tokenize(text):
        word = token.form.strip()
        if token.tag in NOUN_TAGS and len(word) >= MIN_KEYWORD_LEN and word not in STOPWORDS:
            keywords.add(word)
    return keywords


def extract_keywords(videos):
    scores = Counter()
    for v in videos:
        text = v["title"] + "\n" + v["description"] + "\n" + "\n".join(v["tags"])
        for kw in extract_keywords_from_text(text):
            scores[kw] += v["views"]
    return scores.most_common(TOP_N)


def extract_hashtags(videos):
    """태그에서 해시태그 빈도 집계 TOP20"""
    tag_scores = Counter()
    for v in videos:
        for tag in v["tags"]:
            tag_clean = tag.strip().replace("#", "")
            if len(tag_clean) >= 2:
                tag_scores[tag_clean] += v["views"]
    return [{"text": t, "value": s} for t, s in tag_scores.most_common(20)]


def build_top5_videos(videos):
    """인기 동영상 TOP5 (순위 그대로) + AI 인기 이유"""
    top5 = []
    titles_for_summary = []
    for v in videos[:5]:
        reason = call_gemini(
            f"유튜브 영상 \"{v['title']}\" (조회수 {v['views']:,}, 채널: {v['channelTitle']})이 인기 있는 이유를 한국어 한 줄(30자 이내)로 설명해줘. 이유만 출력해.")
        top5.append({
            "rank": len(top5) + 1,
            "videoId": v["videoId"],
            "title": v["title"],
            "thumbnailUrl": v["thumbnailUrl"],
            "videoUrl": f"https://www.youtube.com/watch?v={v['videoId']}",
            "channelTitle": v["channelTitle"],
            "hashtags": [t.replace("#", "") for t in v["tags"][:5] if t],
            "aiAnalysis": reason,
            "views": v["views"],
            "publishedAt": v["publishedAt"],
        })
        titles_for_summary.append(v["title"])
    return top5, titles_for_summary


def build_ai_trend_summary(titles, keywords):
    """오늘의 AI 트렌드 요약"""
    prompt = f"""오늘 유튜브 한국 인기 영상 제목: {', '.join(titles[:5])}
인기 키워드: {', '.join([k['text'] for k in keywords[:10]])}

위 정보를 종합해서 "오늘 유튜브에서 뭐가 뜨고 있는지" 한국어 2~3문장으로 요약해줘. 요약만 출력해."""
    return call_gemini(prompt)


def lambda_handler(event, context):
    if not API_KEY:
        return {"statusCode": 400, "body": json.dumps({"error": "YOUTUBE_API_KEY not set"})}

    # 1. 인기 동영상 수집 (기존 로직)
    videos = fetch_trending_videos()

    # 2. 키워드 추출 (기존 로직 → words.json)
    keywords = extract_keywords(videos)
    words = [{"text": kw, "value": score} for kw, score in keywords]
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY,
                  Body=json.dumps(words, ensure_ascii=False),
                  ContentType="application/json")

    # 3. 트렌드 데이터 구성 → trending.json
    popular_videos, top_titles = build_top5_videos(videos)
    hot_keywords = words[:20]
    ai_summary = build_ai_trend_summary(top_titles, hot_keywords)

    trending = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "aiSummary": ai_summary,
        "popularVideos": popular_videos,
        "musicChartKR": fetch_music_chart("KR"),
        "musicChartGlobal": fetch_music_chart(None),
        "categoryTop1": fetch_category_top1(),
        "hotKeywords": hot_keywords,
        "hotHashtags": extract_hashtags(videos),
    }

    s3.put_object(Bucket=S3_BUCKET, Key=S3_TRENDING_KEY,
                  Body=json.dumps(trending, ensure_ascii=False),
                  ContentType="application/json")

    return {"statusCode": 200, "body": json.dumps({"keywords": len(words), "trending": "ok"})}
