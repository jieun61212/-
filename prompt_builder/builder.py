import json
from config.settings import ROOT
from config.catalog import project_by_id, profile_by_id


def prompt(name):
    return (ROOT / 'config/prompts' / name).read_text('utf-8')


def build_messages(request, source='', analysis=None, research=None):
    rule = project_by_id(request.project)
    instructions = prompt('system.md') + '\n' + prompt(rule['prompt'])
    instructions += '\n글자 수 계산: ' + ('공백 포함' if request.count_spaces else '공백 제외')
    if source:
        instructions += '\n' + prompt('pdf_article.md')
    data = {
        '입력': request.model_dump(exclude={'mode', 'privacy_identities'}),
        '선택된_법무법인_유일한_프로필': profile_by_id(request.lawfirm),
        '익명화된_판결문': source,
        '판결문_분석': analysis,
        '공식_법률자료_검색': research,
    }
    return [{'role': 'system', 'content': instructions},
            {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}]
