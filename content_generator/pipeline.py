import json
from pydantic import ValidationError
from app.models import Article
from config.catalog import profile_by_id
from pdf_analyzer.privacy import clean_structure
from config.settings import MAX_REPAIRS
from content_generator.provider import complete, GenerationError
from content_generator.research import research as find_sources
from content_generator.demo import make_demo
from pdf_analyzer.analyzer import analyze_pdf
from prompt_builder.builder import build_messages, prompt
from validator.checks import validate
from validator.reviewer import review


async def generate(request, source='', previous=None, previous_analysis=None, previous_research=None):
    if request.mode == 'demo':
        if source:
            raise GenerationError('예시 모드에서는 판결문 기반 원고를 생성하지 않습니다. AI 모드를 선택하고 API 키를 설정하세요.')
        article = previous or make_demo(request)
        report = validate(article, request)
        if not report['passed']:
            article = make_demo(request)
            report = validate(article, request)
        if not report['passed']:
            raise GenerationError('이 입력으로는 예시 원고가 검수를 통과하지 못했습니다. 기본 설정을 사용하거나 AI 모드로 생성하세요.')
        return article, report, None, None, 0

    analysis = previous_analysis or (await analyze_pdf(source) if source else None)
    if analysis:
        analysis = clean_structure(analysis, request.privacy_identities)
    research = previous_research or await find_sources(request)
    messages = build_messages(request, source, analysis, research)
    article = previous
    for attempt in range(MAX_REPAIRS + 1):
        if article is None:
            raw = await complete(messages, max(6000, request.max_chars * 3))
            try:
                article = Article.model_validate(clean_structure(raw, request.privacy_identities, profile_by_id(request.lawfirm).get('phone')))
            except ValidationError:
                if attempt == MAX_REPAIRS:
                    raise GenerationError('원고 구조가 요구 형식을 충족하지 못했습니다. 최종본을 제공하지 않습니다.')
                messages.extend([{'role': 'assistant', 'content': json.dumps(raw, ensure_ascii=False)},
                                 {'role': 'user', 'content': prompt('repair.md') + '\n' + prompt('structure_repair.md')}])
                continue
        article = Article.model_validate(clean_structure(article.model_dump(), request.privacy_identities, profile_by_id(request.lawfirm).get('phone')))
        report = validate(article, request, source, research['text'])
        semantic = await review(article, request, source, analysis, research)
        report['checks'].append({'code': 'AI_REVIEW', 'label': '공식 근거·판결문 대조 검수', 'passed': not semantic,
                                 'detail': '독립 AI 검수: ' + (str(len(semantic)) + '개 문제' if semantic else '추가 지적 없음')})
        report['issues'].extend(semantic)
        report['passed'] = not report['issues']
        if report['passed']:
            return article, report, analysis, research, attempt
        if attempt == MAX_REPAIRS:
            raise GenerationError('자동 수정 후에도 검수 문제가 남았습니다. 최종본을 제공하지 않습니다. ' + '; '.join(i['message'] for i in report['issues'][:4]))
        messages.extend([{'role': 'assistant', 'content': article.model_dump_json()},
                         {'role': 'user', 'content': prompt('repair.md') + '\n수정할 문제: ' + json.dumps(report['issues'], ensure_ascii=False)}])
        article = None
    raise GenerationError('원고 검수가 완료되지 않았습니다.')
