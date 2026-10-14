import re
from config.catalog import profile_by_id, profiles, project_by_id

BANNED = ['무조건', '100%', '반드시 성공', '기각 없음', '전국 1위', '최고', '무조건 면책', '무조건 승소']
ALARMIST = ['비극', '충격', '끔찍', '인생 끝', '파멸', '절망', '공포']
PHONE = re.compile(r'(?<!\d)(?:01[016789]|0\d{1,2})[- .]\d{3,4}[- .]\d{4}(?!\d)')
CASE = re.compile(r'(?<!\d)\d{2,4}\s*(?:다|도|두|가합|가단|고합|고단|고정|구합|구단|나|누|드합|드단|므|모|카합|카단|헌바|헌마)\s*\d+')
STAT = re.compile(r'\d[\d,.]*\s*(?:%|퍼센트|명|건|원|만원|억원|개월|년|일|배|위|조|항|호)')
DEFINITE = ['승소할 수밖에', '면책됩니다', '반드시 인용', '확실히 승소', '처벌받지 않습니다', '전액 받을 수 있습니다', '틀림없이', '보장합니다']
AD_CTA = ['지금 바로', '놓치지 마', '무료', '할인', '혜택', '최저', '최상', '유일', '즉시 연락', '성공률', '실적']


def char_count(body, count_spaces=False):
    return len(body) if count_spaces else len(re.sub(r'\s', '', body))


def validate(article, request, source='', research_text=''):
    profile = profile_by_id(request.lawfirm)
    rule = project_by_id(request.project)
    issues = []
    checks = []
    def check(code, label, passed, detail):
        checks.append({'code': code, 'label': label, 'passed': bool(passed), 'detail': detail})
        if not passed:
            issues.append({'code': code, 'message': detail})

    # Validate every candidate, since they are displayed with the final manuscript.
    check('TITLE_KEYWORD', '제목 앞부분 메인키워드', all(t.strip().startswith(request.keyword) for t in article.titles), '제목 후보 3개 모두 메인키워드로 시작해야 합니다.')
    phrase = rule.get('required_title_phrase', '')
    check('PROJECT_TITLE', '프로젝트별 제목 규칙', not phrase or all(phrase in t for t in article.titles), f'제목 후보에 {phrase or "프로젝트 필수 문구"}가 필요합니다.')
    count = article.body.count(request.keyword)
    check('KEYWORD_COUNT', '본문 키워드 횟수', max(1, request.keyword_target-1) <= count <= request.keyword_target+1,
          f'본문 {count}회 / 목표 {request.keyword_target}회 (허용 ±1회).')
    chars = char_count(article.body, request.count_spaces)
    check('LENGTH', '본문 글자 수', request.min_chars <= chars <= request.max_chars,
          f'{"공백 포함" if request.count_spaces else "공백 제외"} {chars}자 / {request.min_chars}~{request.max_chars}자.')
    check('QUESTIONS', '질문형 소제목', 3 <= len(article.sections) <= 4 and all(s.question.rstrip().endswith('?') for s in article.sections), '본론에 물음표로 끝나는 질문형 소제목 3~4개가 필요합니다.')
    answer_ok = all(s.answer.strip() and 1 <= len([p for p in re.split(r'(?<=[.!?。])\s+|\n+', s.answer.strip()) if p]) <= 3 for s in article.sections)
    check('ANSWERS', '질문 아래 핵심 답', answer_ok, '각 질문의 핵심 답변은 비어 있지 않은 1~3문장이어야 합니다.')
    all_text = '\n'.join(article.titles) + '\n' + article.body
    check('FIRM_NAME', '법무법인명', profile['name'] in article.cta, 'CTA에 선택된 법무법인명을 정확히 기재해야 합니다.')
    phones = PHONE.findall(all_text)
    allowed_phone = profile.get('phone')
    phone_ok = (not phones if not allowed_phone else all(p == allowed_phone for p in phones) and allowed_phone in article.cta)
    check('PHONE', '연락처 일치', phone_ok, '선택 프로필의 연락처만 허용하며, 미등록 연락처를 만들 수 없습니다.')
    other_names = [p['name'] for p in profiles() if p['id'] != request.lawfirm
                   and any(name in all_text for name in [p['name'], *p.get('aliases', [])])]
    scrubbed = all_text.replace(profile['name'], '')
    unknown_firm = bool(re.search(r'법무법인\s+[가-힣A-Za-z]{2,}', scrubbed))
    check('PROFILE_ISOLATION', '다른 법무법인 정보 혼입', not other_names and not unknown_firm, '다른 법무법인 이름 또는 미등록 법무법인명이 포함됐습니다.')
    check('PROFILE_REGION', '법무법인 소재지', profile['region'] in article.cta, 'CTA에 선택된 법무법인의 등록 지역을 포함해야 합니다.')
    forbidden = [w for w in BANNED + ALARMIST if w in all_text]
    check('BANNED', '금지·자극 표현', not forbidden, '금지 표현: ' + ', '.join(forbidden))
    evidence = source + '\n' + research_text + '\n' + request.references
    cases = CASE.findall(all_text)
    evidence_cases = {re.sub(r'\s', '', c) for c in CASE.findall(evidence)}
    unsupported_cases = [c for c in cases if re.sub(r'\s', '', c) not in evidence_cases]
    # Citation shorthand or a court-specific invented precedent must be sourced too.
    court_claims = re.findall(r'(?:대법원|고등법원|지방법원).{0,30}(?:선고|판결)', all_text)
    check('CASE_CITATION', '판례·사건번호 근거', not unsupported_cases and not any(c not in evidence for c in court_claims), '제공·검색 자료에 없는 사건번호나 판례 인용이 있습니다.')
    numeric_text = all_text.replace(allowed_phone or '\0', '')
    for c in cases:
        numeric_text = numeric_text.replace(c, '')
    numbers = STAT.findall(numeric_text)
    evidence_numbers = {re.sub(r'\s', '', n) for n in STAT.findall(evidence)}
    unsupported_numbers = [n for n in numbers if re.sub(r'\s', '', n) not in evidence_numbers]
    bare_numbers = set(re.findall(r'\d+(?:[.,]\d+)*', numeric_text))
    evidence_digits = set(re.findall(r'\d+(?:[.,]\d+)*', evidence))
    unsupported_numbers += sorted(bare_numbers - evidence_digits)
    check('NUMBERS', '수치·통계 근거', not unsupported_numbers, '근거를 확인할 수 없는 수치: ' + ', '.join(unsupported_numbers))
    certainty = [w for w in DEFINITE if w in all_text]
    check('CERTAINTY', '지나친 단정', not certainty, '결과를 단정하는 표현: ' + ', '.join(certainty))
    advertising = [w for w in AD_CTA if w in article.cta]
    check('CTA', 'CTA 광고성', not advertising and article.cta.count('!') == 0, 'CTA에 과도한 광고·강요 표현이 있습니다: ' + ', '.join(advertising))
    personal = bool(re.search(r'\b\d{6}-[1-4]\d{6}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', all_text))
    check('PRIVACY', '개인정보 패턴', not personal, '원고에 주민등록번호 또는 이메일이 있습니다.')
    if source:
        success = any(w in all_text for w in ['성공사례', '성공 사례', '승소사례', '승소 사례', '우리 의뢰인', '수임한 사건'])
        check('CASE_SUCCESS', '사례 성과 단정', not success, '제공 판결문을 법무법인의 수임·성공사례로 표현할 수 없습니다.')
    return {'passed': not issues, 'issues': issues, 'checks': checks, 'chars': chars, 'keyword_count': count, 'count_spaces': request.count_spaces}
