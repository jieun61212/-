import json
from content_generator.provider import complete, GenerationError
from prompt_builder.builder import prompt
from config.catalog import profile_by_id


async def review(article, request, source='', analysis=None, research=None):
    result = await complete([
        {'role': 'system', 'content': prompt('review.md')},
        {'role': 'user', 'content': json.dumps({'article': article.model_dump(), 'input': request.model_dump(),
         'profile': profile_by_id(request.lawfirm), 'pdf_source': source, 'analysis': analysis, 'research': research}, ensure_ascii=False)},
    ], 2500)
    if not isinstance(result, dict) or set(result) != {'issues'} or not isinstance(result['issues'], list):
        raise GenerationError('독립 검수 응답 형식이 올바르지 않습니다.')
    for issue in result['issues']:
        if not isinstance(issue, dict) or not isinstance(issue.get('code'), str) or not isinstance(issue.get('message'), str):
            raise GenerationError('독립 검수 항목이 올바르지 않습니다.')
    return result['issues']
