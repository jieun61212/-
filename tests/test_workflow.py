import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from docx import Document
from app.models import ArticleInput
from app.main import app
from app import storage
from config.catalog import projects, profiles
from config import settings
from content_generator.demo import make_demo
from content_generator.pipeline import generate
from content_generator.provider import GenerationError
from content_generator.research import official_url
from pdf_analyzer.analyzer import anonymize, extract_pdf, verify_analysis, FIELDS
from prompt_builder.builder import build_messages
from validator.checks import validate, char_count
from tests.helpers import pdf_bytes

RESEARCH = {'text': '계약서와 관련 기록을 확인한다.', 'sources': [{'title': '국가법령정보센터', 'url': 'https://www.law.go.kr/법령/민법'}], 'method': 'official_web_search'}


def request(**changes):
    return ArticleInput(**({'project': 'rehabilitation', 'lawfirm': 'daehan_ulsan', 'keyword': '울산 개인회생', 'topic': '최근 채무와 상담 준비', 'mode': 'demo'} | changes))


class ValidatorTests(unittest.TestCase):
    def test_all_projects_and_profiles(self):
        for project in projects():
            for firm in profiles():
                with self.subTest(project=project['id'], firm=firm['id']):
                    req = ArticleInput(project=project['id'], lawfirm=firm['id'], keyword='울산 법률상담', topic='상담 자료 준비', mode='demo')
                    report = validate(make_demo(req), req)
                    self.assertTrue(report['passed'], report['issues'])
                    self.assertEqual(report['keyword_count'], 5)

    def test_civil_user_prompt_defaults(self):
        req = request(project='civil', lawfirm='siwoo_busan', keyword='부산 계약분쟁', topic='계약서 검토')
        self.assertEqual((req.min_chars, req.max_chars, req.count_spaces), (1000, 1500, True))
        self.assertTrue(all('민사전문변호사' in t for t in make_demo(req).titles))

    def test_wrong_title_prefix(self):
        req = request(); a = make_demo(req); a.titles[1] = '알아보는 ' + req.keyword
        self.assertIn('TITLE_KEYWORD', [i['code'] for i in validate(a, req)['issues']])

    def test_keyword_and_length_fail(self):
        req = request(); a = make_demo(req)
        a.introduction += (' ' + req.keyword) * 10 + '가' * 2000
        codes = [i['code'] for i in validate(a, req)['issues']]
        self.assertIn('KEYWORD_COUNT', codes); self.assertIn('LENGTH', codes)

    def test_questions_and_answer_sentences(self):
        req = request(); a = make_demo(req)
        a.sections[0].question = '일반 소제목'
        a.sections[1].answer = '첫 문장. 둘째 문장. 셋째 문장. 넷째 문장.'
        codes = [i['code'] for i in validate(a, req)['issues']]
        self.assertIn('QUESTIONS', codes); self.assertIn('ANSWERS', codes)

    def test_cross_firm_and_wrong_phone(self):
        req = request(); a = make_demo(req)
        a.cta += ' 법무법인 시우 051-123-4567'
        codes = [i['code'] for i in validate(a, req)['issues']]
        self.assertIn('PROFILE_ISOLATION', codes); self.assertIn('PHONE', codes)

    def test_unregistered_phone(self):
        req = request(project='criminal', lawfirm='siwoo_busan', keyword='부산 형사상담', topic='조사 준비')
        a = make_demo(req); a.cta += ' 051-123-4567'
        self.assertIn('PHONE', [i['code'] for i in validate(a, req)['issues']])

    def test_unknown_firm(self):
        req = request(); a = make_demo(req); a.cta += ' 법무법인 새로만든이름'
        self.assertIn('PROFILE_ISOLATION', [i['code'] for i in validate(a, req)['issues']])

    def test_other_firm_alias_is_blocked(self):
        req = request(lawfirm='siwoo_busan'); a = make_demo(req)
        a.conclusion += ' 대한중앙에서 검토합니다.'
        self.assertIn('PROFILE_ISOLATION', [i['code'] for i in validate(a, req)['issues']])

    def test_banned_alarmist_certainty_and_cta(self):
        req = request(); a = make_demo(req)
        a.conclusion += ' 무조건 100% 최고 비극 면책됩니다.'
        a.cta += ' 지금 바로 무료 상담!'
        codes = [i['code'] for i in validate(a, req)['issues']]
        for code in ['BANNED', 'CERTAINTY', 'CTA']:
            self.assertIn(code, codes)

    def test_case_numbers_require_exact_source(self):
        req = request(); a = make_demo(req); a.conclusion += ' 2024다12345'
        self.assertIn('CASE_CITATION', [i['code'] for i in validate(a, req)['issues']])
        self.assertNotIn('CASE_CITATION', [i['code'] for i in validate(a, req, source='2024다12345')['issues']])

    def test_numeric_substring_is_not_evidence(self):
        req = request(); a = make_demo(req); a.conclusion += ' 10만원'
        self.assertIn('NUMBERS', [i['code'] for i in validate(a, req, research_text='110만원')['issues']])
        self.assertNotIn('NUMBERS', [i['code'] for i in validate(a, req, research_text='10만원')['issues']])

    def test_bare_statistics_detected(self):
        req = request(); a = make_demo(req); a.conclusion += ' 총 98765에 도달합니다.'
        self.assertIn('NUMBERS', [i['code'] for i in validate(a, req)['issues']])

    def test_personal_information(self):
        req = request(); a = make_demo(req); a.conclusion += ' 900101-1234567 name@example.com'
        self.assertIn('PRIVACY', [i['code'] for i in validate(a, req)['issues']])

    def test_pdf_not_marketed_as_our_success(self):
        req = request(); a = make_demo(req); a.conclusion += ' 우리 의뢰인의 성공사례'
        self.assertIn('CASE_SUCCESS', [i['code'] for i in validate(a, req, source='판결문')['issues']])

    def test_space_count(self):
        self.assertEqual(char_count('가 나\n다'), 3)
        self.assertEqual(char_count('가 나\n다', True), 5)

    def test_prompt_contains_only_selected_profile(self):
        req = request(project='civil', lawfirm='siwoo_busan', keyword='계약분쟁', topic='계약 검토', mode='ai')
        text = json.dumps(build_messages(req, research=RESEARCH), ensure_ascii=False)
        self.assertIn('민사전문변호사', text); self.assertIn('법무법인 시우', text)
        self.assertNotIn('052-268-3395', text); self.assertNotIn('대한중앙', text)


class PdfTests(unittest.TestCase):
    def test_private_patterns_removed(self):
        text = '원고 김철수\n피고 이영희\n김철수의 주장\n주소: 울산 남구 어느로 12\n전화번호: 010-1234-5678\n주민등록번호: 900101-1234567\na@example.com'
        result = anonymize(text)
        for private in ['김철수', '이영희', '어느로', '010-1234-5678', '900101-1234567', 'a@example.com']:
            self.assertNotIn(private, result)

    def test_text_pdf_extraction(self):
        result = extract_pdf(pdf_bytes('The court dismissed the claim. The parties disputed performance of the contract.'))
        self.assertIn('dismissed', result['text']); self.assertEqual(result['pages'], 1)

    def test_scan_rejected(self):
        with self.assertRaisesRegex(ValueError, 'OCR'):
            extract_pdf(pdf_bytes())

    def test_invalid_file_rejected(self):
        with self.assertRaisesRegex(ValueError, '유효한 PDF'):
            extract_pdf(b'not a pdf')

    def test_encrypted_rejected(self):
        with self.assertRaisesRegex(ValueError, '암호화'):
            extract_pdf(pdf_bytes('test judgment', encrypted=True))

    def test_analysis_requires_verbatim_evidence(self):
        analysis = {k: {'summary': '판결문에서 확인되지 않음', 'evidence': ''} for k in FIELDS}
        analysis['outcome'] = {'summary': '청구 기각', 'evidence': '원고의 청구를 기각한다.'}
        self.assertEqual(verify_analysis(analysis, '주문 원고의 청구를 기각한다.'), analysis)
        with self.assertRaises(GenerationError):
            verify_analysis(analysis, '다른 판결문')

    def test_analysis_rejects_uncited_fact(self):
        analysis = {k: {'summary': '판결문에서 확인되지 않음', 'evidence': ''} for k in FIELDS}
        analysis['outcome']['summary'] = '승소'
        with self.assertRaises(GenerationError):
            verify_analysis(analysis, '주문')


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_repair_then_revalidation(self):
        req = request(mode='ai')
        valid = make_demo(req); invalid = valid.model_copy(deep=True)
        invalid.cta += ' 무조건'
        with patch('content_generator.pipeline.complete', AsyncMock(side_effect=[invalid.model_dump(), valid.model_dump()])) as generator, \
             patch('content_generator.pipeline.find_sources', AsyncMock(return_value=RESEARCH)), \
             patch('content_generator.pipeline.review', AsyncMock(return_value=[])) as reviewer:
            article, report, _, _, repairs = await generate(req)
        self.assertTrue(report['passed']); self.assertNotIn('무조건', article.text)
        self.assertEqual(repairs, 1); self.assertEqual(generator.await_count, 2); self.assertEqual(reviewer.await_count, 2)

    async def test_semantic_issue_triggers_repair(self):
        req = request(mode='ai'); valid = make_demo(req)
        with patch('content_generator.pipeline.complete', AsyncMock(return_value=valid.model_dump())), \
             patch('content_generator.pipeline.find_sources', AsyncMock(return_value=RESEARCH)), \
             patch('content_generator.pipeline.review', AsyncMock(side_effect=[[{'code': 'FACT', 'message': '불명확한 법리를 제거'}], []])):
            _, report, _, _, repairs = await generate(req)
        self.assertTrue(report['passed']); self.assertEqual(repairs, 1)

    async def test_persistent_issue_blocks_final(self):
        req = request(mode='ai'); valid = make_demo(req)
        with patch('content_generator.pipeline.complete', AsyncMock(return_value=valid.model_dump())) as generator, \
             patch('content_generator.pipeline.find_sources', AsyncMock(return_value=RESEARCH)), \
             patch('content_generator.pipeline.review', AsyncMock(return_value=[{'code': 'FACT', 'message': '확인되지 않은 사실'}])):
            with self.assertRaisesRegex(GenerationError, '최종본'):
                await generate(req)
        self.assertEqual(generator.await_count, settings.MAX_REPAIRS + 1)

    async def test_malformed_structure_repair(self):
        req = request(mode='ai'); valid = make_demo(req)
        with patch('content_generator.pipeline.complete', AsyncMock(side_effect=[{'titles': []}, valid.model_dump()])), \
             patch('content_generator.pipeline.find_sources', AsyncMock(return_value=RESEARCH)), \
             patch('content_generator.pipeline.review', AsyncMock(return_value=[])):
            _, report, _, _, repairs = await generate(req)
        self.assertTrue(report['passed']); self.assertEqual(repairs, 1)

    async def test_pdf_demo_is_blocked(self):
        with self.assertRaisesRegex(GenerationError, '예시 모드'):
            await generate(request(), source='판결문 자료')

    async def test_official_url_host_boundary(self):
        self.assertTrue(official_url('https://www.law.go.kr/법령/민법'))
        self.assertTrue(official_url('https://www.scourt.go.kr/a'))
        self.assertFalse(official_url('https://law.go.kr.evil.example/a'))
        self.assertFalse(official_url('https://evil.example/?q=law.go.kr'))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = patch('app.storage.DATA_DIR', Path(self.temp.name))
        self.directory.start()
        self.key = patch('config.settings.API_KEY', '')
        self.key.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.key.stop(); self.directory.stop(); self.temp.cleanup()

    def create(self, **changes):
        req = request(**changes)
        response = self.client.post('/api/generate', data={'payload': req.model_dump_json()})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_page_and_config(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        cfg = self.client.get('/api/config').json()
        self.assertEqual(len(cfg['projects']), 4); self.assertEqual(len(cfg['profiles']), 2)
        self.assertFalse(cfg['ai_available']); self.assertEqual(self.client.get('/api/health').json()['database'], 'ok')

    def test_full_demo_history_review_regenerate_export(self):
        draft = self.create()
        self.assertEqual(draft['status'], 'demo'); self.assertTrue(draft['report']['passed'])
        history = self.client.get('/api/history', params={'q': '채무 준비'}).json()['items']
        self.assertEqual(len(history), 1)
        self.assertEqual(self.client.get('/api/history', params={'lawfirm': 'siwoo_busan'}).json()['items'], [])
        reviewed = self.client.post(f"/api/drafts/{draft['id']}/validate")
        self.assertEqual(reviewed.status_code, 200)
        again = self.client.post(f"/api/drafts/{draft['id']}/regenerate").json()
        self.assertNotEqual(again['id'], draft['id'])
        txt = self.client.get(f"/api/drafts/{draft['id']}/export/txt")
        self.assertIn('예시 모드', txt.content.decode('utf-8-sig'))
        docx = self.client.get(f"/api/drafts/{draft['id']}/export/docx")
        self.assertEqual(docx.status_code, 200)
        document = Document(io.BytesIO(docx.content))
        text = '\n'.join(p.text for p in document.paragraphs)
        self.assertIn('법무법인 대한중앙 울산분사무소', text)
        self.assertIn('052-268-3395', text); self.assertIn('예시 모드', text)
        self.assertEqual(self.client.delete(f"/api/drafts/{draft['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/drafts/{draft['id']}").status_code, 404)

    def test_api_key_missing_block(self):
        response = self.client.post('/api/generate', data={'payload': request(mode='ai').model_dump_json()})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get('/api/history').json()['items'], [])

    def test_unknown_profile_and_whitespace_rejected(self):
        raw = request().model_dump(); raw['lawfirm'] = 'unknown'
        self.assertEqual(self.client.post('/api/generate', data={'payload': json.dumps(raw)}).status_code, 422)
        raw['lawfirm'] = 'siwoo_busan'; raw['keyword'] = '   '
        self.assertEqual(self.client.post('/api/generate', data={'payload': json.dumps(raw)}).status_code, 422)

    def test_history_search_escapes_like(self):
        self.create()
        self.assertEqual(self.client.get('/api/history', params={'q': '%'}).json()['items'], [])
        self.assertEqual(self.client.get('/api/history', params={'q': "' OR 1=1 --"}).json()['items'], [])

    def test_invalid_pdf_rejected(self):
        response = self.client.post('/api/pdf/preview', files={'pdf': ('fake.pdf', b'fake', 'application/pdf')})
        self.assertEqual(response.status_code, 422)

    def test_valid_pdf_preview(self):
        response = self.client.post('/api/pdf/preview', files={'pdf': ('judgment.pdf', pdf_bytes('The court dismissed the claim. The parties disputed the contract and evidence.'), 'application/pdf')})
        self.assertEqual(response.status_code, 200); self.assertIn('dismissed', response.json()['text'])

    def test_failed_generation_has_no_visible_manuscript(self):
        with patch('config.settings.API_KEY', 'test-not-real'), \
             patch('app.main.generate', AsyncMock(side_effect=GenerationError('검수 실패'))):
            response = self.client.post('/api/generate', data={'payload': request(mode='ai').model_dump_json()})
        self.assertEqual(response.status_code, 502)
        row = self.client.get('/api/history').json()['items'][0]
        self.assertEqual(row['status'], 'failed')
        result = self.client.get(f"/api/drafts/{row['id']}").json()
        self.assertIsNone(result['article']); self.assertEqual(result['text'], '')
        self.assertEqual(self.client.get(f"/api/drafts/{row['id']}/export/txt").status_code, 404)

    def test_failed_revalidation_revokes_final(self):
        draft = self.create()
        with patch('app.main.generate', AsyncMock(side_effect=GenerationError('검수 실패'))):
            response = self.client.post(f"/api/drafts/{draft['id']}/validate")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get(f"/api/drafts/{draft['id']}/export/docx").status_code, 404)

    def test_pdf_auto_keywords_without_manual_inputs_or_confirmation(self):
        req = request(mode='ai', keyword='', topic='')
        analysis = {k: {'summary': '판결문에서 확인되지 않음', 'evidence': ''} for k in FIELDS}
        plan = {'keyword': '울산 계약분쟁', 'candidates': ['울산 계약분쟁', '울산 계약상담', '울산 민사상담'],
                'topic': '계약 이행과 증거를 어떻게 확인할까요?',
                'subkeywords': [{'keyword': '계약 이행', 'evidence': 'performance of the contract'}],
                'selection_basis': '사건 내용과 검색 의도 기반 추천 · 실제 검색량 미측정'}
        async def generated(resolved, source, *args):
            article = make_demo(resolved)
            return article, validate(article, resolved), analysis, RESEARCH, 0
        with patch('config.settings.API_KEY', 'test-not-real'), \
             patch('app.main.analyze_pdf', AsyncMock(return_value=analysis)), \
             patch('app.main.suggest', AsyncMock(return_value=plan)), \
             patch('app.main.generate', AsyncMock(side_effect=generated)):
            response = self.client.post('/api/generate', data={'payload': req.model_dump_json()}, files={'pdf': ('judgment.pdf', pdf_bytes('The court dismissed the claim. The parties disputed performance of the contract.'), 'application/pdf')})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['request']['keyword'], '울산 계약분쟁')
        self.assertEqual(result['request']['subkeywords'], '계약 이행')
        self.assertEqual(result['request']['topic'], plan['topic'])
        self.assertNotIn('privacy_identities', result['request'])
        self.assertEqual(storage.get(result['id'])['keyword'], '울산 계약분쟁')

    def test_no_pdf_requires_keyword_and_topic(self):
        req = request(keyword='', topic='')
        response = self.client.post('/api/generate', data={'payload': req.model_dump_json()})
        self.assertEqual(response.status_code, 422)
        self.assertIn('PDF가 없을 때', response.json()['detail'])


if __name__ == '__main__':
    unittest.main()
