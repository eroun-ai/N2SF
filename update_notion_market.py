#!/usr/bin/env python3
"""
미림미디어램 파트너 마켓현황 노션 업데이트 스크립트
사용법: python3 update_notion_market.py
"""

import urllib.request
import json
import ssl
import os
from datetime import datetime

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "29ab98c5e2588010bcc6df63abc8e7dc")
NOTION_VERSION = "2022-06-28"

if not NOTION_TOKEN:
    print("오류: NOTION_TOKEN 환경변수를 설정해주세요.")
    print("  export NOTION_TOKEN='your_notion_token_here'")
    exit(1)

# 미림미디어램 마켓현황 데이터 (2026-03-24 슬랙 기반)
MARKET_DATA = {
    "partner": "미림미디어램",
    "date": datetime.now().strftime("%Y-%m-%d"),
    "summary": """[대학]
• 예산 아직 안 내려옴
• 견적서 다 뿌려놓음 - 우리쪽으로 연락오도록 밑작업
• 초/중/고 - 교육세는 이쪽으로 (교육감이 컨트롤), 물건은 차고 넘어서 물품구매는 막고 있는 추세
  - 일부 몇 조는 고등교육/특수교육으로 배부해서 쓰는 구조
  - 넘어오면 바로 쓰는 구조, 예년에도 비슷한 상황 (대학은 2월말 결산, 11월에 예산 배부하는 경우도 있었음)
  - 돈 안들어와서 사전공고도 다 회수됨
  - 2학기부터 움직이지 않을까 싶음
• 미림 K-Univ (외국인 학생 대상 대학교 유학 사이트 오픈 예정)
  - 유학원 비용이 비싸서 나온 사업모델
  - 전체 유학생 10~15%, 서류 처리 할 것 많다
  - 8년 후면 국내학생/유학생 비율이 비슷해 질 듯
  - 알바 행정처리도 해결 예정

[공공]
• 공공 여력 있나? 작더라도 뿌려 놓는것이 중요하다

[기업]
• 하이서울 바우처
• 클로드 - 업무 프로세스 개선""",
}


def notion_request(method, endpoint, data=None):
    """노션 API 요청"""
    url = f"https://api.notion.com/v1/{endpoint}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    ctx = ssl.create_default_context()
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read().decode("utf-8"))


def get_database_schema():
    """데이터베이스 스키마 조회"""
    print("1. 데이터베이스 스키마 조회 중...")
    db = notion_request("GET", f"databases/{DATABASE_ID}")
    print(f"   데이터베이스: {db.get('title', [{}])[0].get('plain_text', 'N/A')}")
    print(f"   프로퍼티 목록:")
    for name, prop in db.get("properties", {}).items():
        print(f"     - {name} ({prop['type']})")
    return db


def find_existing_page(partner_name):
    """기존 페이지 검색"""
    print(f"\n2. '{partner_name}' 기존 페이지 검색 중...")
    filter_data = {
        "filter": {
            "or": [
                {
                    "property": "이름",
                    "title": {"contains": partner_name},
                },
                {
                    "property": "Name",
                    "title": {"contains": partner_name},
                },
                {
                    "property": "파트너",
                    "rich_text": {"contains": partner_name},
                },
                {
                    "property": "파트너명",
                    "rich_text": {"contains": partner_name},
                },
            ]
        }
    }

    try:
        result = notion_request(
            "POST", f"databases/{DATABASE_ID}/query", filter_data
        )
        pages = result.get("results", [])
        if pages:
            print(f"   기존 페이지 발견: {pages[0]['id']}")
            return pages[0]
    except Exception:
        pass

    # 필터 없이 전체 조회 후 수동 검색
    try:
        result = notion_request("POST", f"databases/{DATABASE_ID}/query", {})
        for page in result.get("results", []):
            for prop_name, prop_val in page.get("properties", {}).items():
                prop_type = prop_val.get("type", "")
                text = ""
                if prop_type == "title":
                    text = "".join(
                        t.get("plain_text", "")
                        for t in prop_val.get("title", [])
                    )
                elif prop_type == "rich_text":
                    text = "".join(
                        t.get("plain_text", "")
                        for t in prop_val.get("rich_text", [])
                    )
                if partner_name in text:
                    print(f"   기존 페이지 발견 ('{prop_name}' 필드): {page['id']}")
                    return page
    except Exception as e:
        print(f"   검색 오류: {e}")

    print("   기존 페이지 없음 - 새로 생성합니다.")
    return None


def build_properties(db_schema, data):
    """데이터베이스 스키마에 맞춰 프로퍼티 구성"""
    props = {}
    db_props = db_schema.get("properties", {})

    # 제목(title) 프로퍼티 찾기
    title_prop = None
    for name, prop in db_props.items():
        if prop["type"] == "title":
            title_prop = name
            break

    if title_prop:
        props[title_prop] = {
            "title": [{"text": {"content": data["partner"]}}]
        }

    # 날짜 프로퍼티 찾기
    for name, prop in db_props.items():
        if prop["type"] == "date" and any(
            k in name.lower() for k in ["날짜", "date", "일자", "업데이트"]
        ):
            props[name] = {"date": {"start": data["date"]}}
            break

    # 마켓현황/내용 프로퍼티 찾기 (rich_text)
    content_keywords = ["마켓", "현황", "내용", "메모", "비고", "노트", "note", "content", "summary", "status"]
    for name, prop in db_props.items():
        if prop["type"] == "rich_text" and any(
            k in name.lower() for k in content_keywords
        ):
            props[name] = {
                "rich_text": [{"text": {"content": data["summary"][:2000]}}]
            }
            break
    else:
        # 일치하는 것 없으면 첫 번째 rich_text 프로퍼티에 넣기
        for name, prop in db_props.items():
            if prop["type"] == "rich_text":
                props[name] = {
                    "rich_text": [
                        {"text": {"content": data["summary"][:2000]}}
                    ]
                }
                break

    return props


def update_page(page_id, properties):
    """기존 페이지 업데이트"""
    print(f"\n3. 페이지 업데이트 중... ({page_id})")
    # title 프로퍼티는 업데이트에서 제외 (이미 존재하는 페이지)
    update_props = {k: v for k, v in properties.items() if "title" not in v}
    if not update_props:
        update_props = properties

    result = notion_request("PATCH", f"pages/{page_id}", {"properties": update_props})
    print("   업데이트 완료!")
    return result


def create_page(db_id, properties):
    """새 페이지 생성"""
    print("\n3. 새 페이지 생성 중...")
    data = {"parent": {"database_id": db_id}, "properties": properties}
    result = notion_request("POST", "pages", data)
    print(f"   페이지 생성 완료! ID: {result['id']}")
    return result


def main():
    print("=" * 50)
    print("미림미디어램 마켓현황 노션 업데이트")
    print(f"날짜: {MARKET_DATA['date']}")
    print("=" * 50)

    try:
        # 1. DB 스키마 조회
        db_schema = get_database_schema()

        # 2. 기존 페이지 검색
        existing = find_existing_page(MARKET_DATA["partner"])

        # 3. 프로퍼티 구성
        properties = build_properties(db_schema, MARKET_DATA)
        print(f"\n   설정할 프로퍼티: {list(properties.keys())}")

        # 4. 업데이트 또는 생성
        if existing:
            update_page(existing["id"], properties)
        else:
            create_page(DATABASE_ID, properties)

        print("\n" + "=" * 50)
        print("완료! 노션에서 확인해주세요.")
        print("=" * 50)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.read else ""
        print(f"\nAPI 오류 ({e.code}): {error_body}")
        if e.code == 401:
            print("→ 토큰이 만료되었거나 잘못되었습니다. 토큰을 확인해주세요.")
        elif e.code == 404:
            print("→ 데이터베이스를 찾을 수 없습니다. ID를 확인하고 통합이 연결되어 있는지 확인해주세요.")
        elif e.code == 400:
            print("→ 프로퍼티 구조가 맞지 않습니다. 데이터베이스 스키마를 확인해주세요.")
    except Exception as e:
        print(f"\n오류 발생: {e}")


if __name__ == "__main__":
    main()
