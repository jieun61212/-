import json
import httpx
from config import settings


class GenerationError(Exception):
    pass


async def complete(messages, max_tokens=6000):
    if not settings.API_KEY:
        raise GenerationError('AI API 키가 설정되지 않았습니다. 서버 환경변수 LEGAL_BLOG_API_KEY를 설정하거나 예시 모드를 사용하세요.')
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(settings.API_URL, headers={
                'Authorization': f'Bearer {settings.API_KEY}',
                'Content-Type': 'application/json',
            }, json={'model': settings.MODEL, 'messages': messages, 'temperature': 0.35,
                     'max_tokens': max_tokens, 'response_format': {'type': 'json_object'}})
        if response.status_code != 200:
            # Provider bodies may echo user data; never expose them or keys.
            reasons = {401: 'API 인증 실패', 403: 'API 접근 권한 또는 네트워크 정책 확인 필요',
                       429: 'API 사용 한도 또는 요청량 초과'}
            raise GenerationError(reasons.get(response.status_code, f'AI 서비스 오류 ({response.status_code})'))
        result = response.json()['choices'][0]
        if result.get('finish_reason') == 'length':
            raise GenerationError('AI 응답 길이 제한에 도달했습니다. 요청 글자 수를 줄여 주세요.')
        return json.loads(result['message']['content'])
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        raise GenerationError('AI 응답을 처리할 수 없습니다. 연결과 모델 설정을 확인하고 다시 시도하세요.') from exc
