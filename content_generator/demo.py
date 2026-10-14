from app.models import Article
from config.catalog import profile_by_id, project_by_id
from validator.checks import char_count

# Offline samples are explicitly marked in the UI and exports. These paragraphs
# exercise the workflow without inventing cases, legal deadlines or statistics.
TOPICS = {
 'rehabilitation': ('소득과 재산은 어떻게 확인하나요?', '최근 채무와 변제 계획은 무엇을 살펴보나요?', '면책 가능성을 검토할 때 어떤 자료가 필요한가요?',
                    '소득 자료와 재산 목록', '채무 발생 경위와 최근 거래 내역', '생활비 지출과 변제 계획'),
 'civil': ('계약관계와 증거는 어떻게 정리하나요?', '입증책임과 청구 가능성은 무엇을 살펴보나요?', '소송 전에 어떤 대응을 준비해야 하나요?',
           '계약서와 이행 내역', '당사자별 주장과 객관적인 증거', '청구 취지와 상대방의 대응'),
 'family': ('이혼사유와 증거는 어떻게 정리하나요?', '재산분할과 양육 문제는 무엇을 살펴보나요?', '가사 사건 상담 전에 무엇을 준비해야 하나요?',
            '혼인 경위와 관련 자료', '재산 형성 내역과 자녀의 생활 환경', '위자료와 재산분할의 쟁점'),
 'criminal': ('범죄 성립요건과 증거는 어떻게 확인하나요?', '경찰과 검찰 조사 전에 무엇을 살펴보나요?', '합의와 양형 자료는 어떻게 준비하나요?',
              '사건 경위와 객관적 증거', '수사 단계와 진술 내용', '합의 경과와 양형 관련 자료'),
}

EXPANSIONS = [
 '자료를 검토할 때는 작성 시점과 작성자를 함께 확인하는 것이 좋습니다. 같은 내용이라도 사건 전후의 맥락이 다르면 의미가 달라질 수 있으므로, 원본을 보관하고 필요한 부분을 따로 정리해 두면 설명에 도움이 됩니다.',
 '상대방의 입장을 예상하여 불리한 자료를 숨기거나 내용을 고치는 방법은 적절하지 않습니다. 확인된 사실과 아직 확인되지 않은 부분을 구별하고, 자료가 없는 부분은 그 한계를 명확히 밝혀 검토를 받는 편이 바람직합니다.',
 '상담을 준비할 때는 원하는 결론만 적기보다 실제로 있었던 일과 그 시점을 차례로 정리해 보세요. 서로 다른 문서의 내용이 맞지 않으면 어떤 차이가 있는지 표시하고, 기억에 의존한 설명과 기록에 남은 사실도 구별하는 것이 좋습니다.',
 '같은 종류의 문제라도 당사자의 관계와 자료의 범위에 따라 검토 방향이 달라질 수 있습니다. 다른 사람의 경험을 그대로 적용하기보다 자신의 상황에서 확인할 내용이 무엇인지 살펴보고, 추가 자료가 필요한 부분을 먼저 정리해 두세요.',
 '자료가 여러 곳에 흩어져 있다면 종류별로 분류하고 사건 경위와 연결해 보는 방법이 도움이 됩니다. 문서 제목과 내용이 다르게 이해될 여지가 있는 경우에는 해당 부분을 표시하여 상담 과정에서 함께 확인할 수 있도록 준비해 보세요.',
 '절차를 진행하기 전에는 원하는 대응과 그 이유를 명확히 설명할 수 있어야 합니다. 현재 확인한 자료만으로 판단하기 어려운 부분은 단정하지 말고, 추가로 확인할 사항을 질문 목록으로 만들어 개별 상황에 맞는 검토를 받으세요.',
]


def make_demo(request):
    profile = profile_by_id(request.lawfirm)
    q1, q2, q3, focus1, focus2, focus3 = TOPICS[request.project]
    phrase = project_by_id(request.project).get('required_title_phrase', '')
    extra = '' if phrase in request.keyword else (' ' + phrase if phrase else '')
    data = {
        'titles': [request.keyword + extra + ' 상담 전 확인할 핵심 쟁점', request.keyword + extra + ' 자료 준비는 어떻게 할까요?', request.keyword + extra + ' 대응 방향을 정리하는 방법'],
        'selected_title_index': 0,
        'introduction': '안녕하세요. 법률 문제를 마주하면 어떤 자료부터 준비할지 막막할 수 있습니다. ' + request.topic + '에 관해 살펴볼 때에도 당사자의 주장과 자료가 일치하는지 차분하게 확인하는 과정이 필요합니다.\n\n초기에는 사실관계와 쟁점을 구별하고 관련 기록을 보존하는 것이 중요합니다. 이 글은 자료 정리와 상담 준비를 위한 일반적인 설명이며, 개별 사건의 판단은 확인된 사실과 적용 법률을 함께 살펴야 합니다.',
        'sections': [
            {'question': q1, 'answer': focus1 + '를 먼저 정리해 사실관계를 확인하는 것이 출발점입니다. 사건의 경위를 시간 순서대로 정리하면 검토할 쟁점을 구별하는 데 도움이 됩니다.', 'explanation': '당사자의 설명만으로 모든 사정을 파악하기는 어렵습니다. 관련 문서와 대화 기록을 함께 살펴보고 서로 일치하는 부분과 다른 부분을 구분해 두세요. 자료를 수집할 때는 적법한 방법인지 확인하고 타인의 개인정보를 불필요하게 포함하지 않도록 주의해야 합니다.'},
            {'question': q2, 'answer': focus2 + '를 함께 검토해야 합니다. 한 가지 자료만으로 결론을 정하기보다 적용되는 법적 기준과 개별 사정을 연결해 살펴보는 과정이 필요합니다.', 'explanation': '사실관계가 다르면 검토할 조건과 예외도 달라질 수 있습니다. 자신의 주장에 유리한 내용뿐 아니라 상대방의 설명과 관련 기록도 함께 정리하는 편이 좋습니다. 확인되지 않은 부분은 추측으로 채우지 말고 별도의 확인 사항으로 남겨 두세요.'},
            {'question': q3, 'answer': focus3 + '를 중심으로 질문과 자료를 준비해 보세요. 현재 상황에서 가능한 대응은 사건 기록을 바탕으로 개별적으로 검토해야 합니다.', 'explanation': '자료가 부족하면 법적 평가를 구체화하기 어려울 수 있습니다. 사건 진행 단계와 확보한 자료의 범위를 정리해 전달하고, 추가로 확인할 부분을 상담에서 질문해 보세요. 다른 사건의 결과가 자신의 사건에도 그대로 적용된다고 기대하기보다 차이를 확인하는 것이 중요합니다.'},
        ],
        'checklist': ['사건 경위를 시간 순서대로 정리했는지 확인하기', '관련 자료의 원본과 작성 시점 확인하기', '확인된 사실과 추측을 구별하기', '상담에서 물어볼 쟁점 정리하기'],
        'conclusion': '법률 문제의 대응 방향은 자료와 사실관계에 따라 달라질 수 있습니다. 쟁점과 확인할 내용을 정리한 뒤 법률 전문가의 검토를 받아 자신의 상황에 맞는 대응을 검토해 보세요.',
        'cta': f"{profile['name']} ({profile['region']})에 자료 검토와 상담 가능 여부를 문의할 수 있습니다." + (f" 연락처: {profile['phone']}." if profile['phone'] else ' 연락처는 프로필에 등록되지 않았습니다.'),
    }
    # Spread keyword occurrences across existing paragraphs, without repeated padding.
    locations = [('introduction', None), ('question', 0), ('question', 1), ('question', 2), ('conclusion', None),
                 ('explanation', 0), ('explanation', 1), ('explanation', 2), ('answer', 0), ('answer', 1), ('answer', 2), ('cta', None)]
    for name, index in locations[:request.keyword_target]:
        prefix = request.keyword + (' 관련 ' if name == 'question' else '에 관해서는 ')
        if index is None:
            data[name] = prefix + data[name]
        else:
            data['sections'][index][name] = prefix + data['sections'][index][name]
    # Select full optional paragraphs within the requested budget.
    for paragraph in EXPANSIONS:
        if char_count(Article.model_validate(data).body, request.count_spaces) >= request.min_chars:
            break
        for section in data['sections']:
            trial = section['explanation'] + '\n\n' + paragraph
            old = section['explanation']
            section['explanation'] = trial
            if char_count(Article.model_validate(data).body, request.count_spaces) <= request.max_chars:
                break
            section['explanation'] = old
    # Small budgets use condensed explanations, still preserving answers and structure.
    if char_count(Article.model_validate(data).body, request.count_spaces) > request.max_chars:
        for section in reversed(data['sections']):
            section['explanation'] = section['explanation'].split('. ')[0] + '.'
            if char_count(Article.model_validate(data).body, request.count_spaces) <= request.max_chars:
                break
    return Article.model_validate(data)
