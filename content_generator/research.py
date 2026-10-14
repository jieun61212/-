from urllib.parse import urlsplit
import httpx
from config import settings
from content_generator.provider import GenerationError
from prompt_builder.builder import prompt


def official_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https':
        return False
    host = (parsed.hostname or '').lower()
    return host == 'law.go.kr' or host.endswith('.law.go.kr') or host == 'scourt.go.kr' or host.endswith('.scourt.go.kr')


async def research(request):
    if not settings.API_KEY:
        raise GenerationError('AI API 키가 필요합니다. 서버 환경변수 LEGAL_BLOG_API_KEY를 설정하세요.')
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post('https://api.openai.com/v1/responses',
                headers={'Authorization': f'Bearer {settings.API_KEY}'},
                json={'model': settings.MODEL,
                      'instructions': prompt('research.md'),
                      'input': f'주제: {request.topic}\n메인키워드: {request.keyword}',
                      'tools': [{'type': 'web_search', 'filters': {'allowed_domains': ['law.go.kr', 'scourt.go.kr']}}],
                      'tool_choice': 'required', 'max_output_tokens': 2500})
        if response.status_code != 200:
            raise GenerationError(f'공식 자료 검색에 실패했습니다 ({response.status_code}). 웹 검색을 지원하는 모델과 API 권한을 확인하세요.')
        payload = response.json()
        if payload.get('status') != 'completed':
            raise GenerationError('공식 자료 검색이 완료되지 않았습니다.')
        searched = any(o.get('type') == 'web_search_call' and o.get('status') == 'completed' for o in payload.get('output', []))
        texts, sources = [], []
        for item in payload.get('output', []):
            for part in item.get('content', []):
                if part.get('type') == 'output_text':
                    texts.append(part['text'])
                    for citation in part.get('annotations', []):
                        if citation.get('type') == 'url_citation' and official_url(citation.get('url', '')):
                            sources.append({'title': citation.get('title', '공식 자료'), 'url': citation['url']})
        if not searched or not sources or not texts:
            raise GenerationError('인용 가능한 공식 자료를 찾지 못했습니다. 주제나 키워드를 구체화해 주세요. 검증 없는 원고는 최종본으로 제공하지 않습니다.')
        unique = {s['url']: s for s in sources}
        return {'text': '\n'.join(texts), 'sources': list(unique.values()), 'method': 'official_web_search'}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise GenerationError('공식 자료 검색 응답을 처리하지 못했습니다. 연결을 확인해 주세요.') from exc
