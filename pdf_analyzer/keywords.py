import json
from pydantic import BaseModel, Field, ConfigDict
from content_generator.provider import complete, GenerationError
from config.catalog import profile_by_id
from pdf_analyzer.privacy import clean_structure
from prompt_builder.builder import prompt

BASIS = '사건 내용과 검색 의도 기반 추천 · 실제 검색량 미측정'


class Term(BaseModel):
    model_config = ConfigDict(extra='forbid')
    keyword: str = Field(min_length=2, max_length=40)
    evidence: str = Field(min_length=4, max_length=600)


class KeywordPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    keyword: str = Field(min_length=2, max_length=60)
    candidates: list[str] = Field(min_length=3, max_length=3)
    topic: str = Field(min_length=2, max_length=200)
    subkeywords: list[Term] = Field(min_length=3, max_length=6)
    selection_basis: str


async def suggest(source, analysis, request):
    data = {'project': request.project, 'region': request.region or profile_by_id(request.lawfirm)['region'],
            'analysis': analysis, 'source': source}
    messages = [{'role': 'system', 'content': prompt('keywords.md')},
                {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}]
    for attempt in range(2):
        raw = await complete(messages, 2500)
        try:
            plan = KeywordPlan.model_validate(raw)
            if plan.keyword not in plan.candidates or any(not 2 <= len(c) <= 60 for c in plan.candidates):
                raise ValueError('후보와 선정 키워드 불일치')
            if any(term.evidence not in source for term in plan.subkeywords):
                raise ValueError('서브키워드 원문 인용 불일치')
            cleaned = clean_structure(plan.model_dump(), request.privacy_identities)
            if cleaned != plan.model_dump():
                raise ValueError('키워드에 개인정보 포함')
            plan.selection_basis = BASIS
            return plan.model_dump()
        except ValueError:
            if attempt:
                raise GenerationError('판결문 키워드의 근거·개인정보 검수가 완료되지 않았습니다.')
            messages.append({'role': 'user', 'content': prompt('keywords_repair.md')})
