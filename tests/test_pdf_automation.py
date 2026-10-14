import unittest
from unittest.mock import AsyncMock, patch
from app.models import ArticleInput
from content_generator.demo import make_demo
from content_generator.pipeline import generate
from content_generator.provider import GenerationError
from pdf_analyzer.privacy import fingerprints, remove_identities, clean_output
from pdf_analyzer.keywords import suggest, BASIS
from validator.checks import validate


def req():
    return ArticleInput(project='civil', lawfirm='daehan_ulsan', mode='ai')


def plan():
    return {'keyword': '울산 대여금 반환', 'candidates': ['울산 대여금 반환', '울산 대여금 소송', '울산 민사상담'],
            'topic': '빌려준 돈은 어떤 증거로 청구하나요?',
            'subkeywords': [{'keyword': term, 'evidence': quote} for term, quote in [('대여금', '대여금 반환'), ('입증책임', '입증책임은 원고'), ('계좌이체', '계좌이체 내역')]],
            'selection_basis': '검색량을 임의로 지어낸 설명'}

SOURCE = '대여금 반환 사건에서 입증책임은 원고에게 있다. 계좌이체 내역을 제출하였다.'


class PdfAutomationTests(unittest.IsolatedAsyncioTestCase):
    async def test_keyword_subkeywords_grounded_and_basis_not_fabricated(self):
        with patch('pdf_analyzer.keywords.complete', AsyncMock(return_value=plan())):
            result = await suggest(SOURCE, {}, req())
        self.assertEqual(result['keyword'], '울산 대여금 반환')
        self.assertEqual(len(result['subkeywords']), 3)
        self.assertEqual(result['selection_basis'], BASIS)

    async def test_fabricated_subkeyword_evidence_blocks_selection(self):
        raw = plan(); raw['subkeywords'][0]['evidence'] = '원문에 없는 판결'
        with patch('pdf_analyzer.keywords.complete', AsyncMock(return_value=raw)):
            with self.assertRaises(GenerationError):
                await suggest(SOURCE, {}, req())

    async def test_party_name_not_accepted_as_search_keyword(self):
        r = req(); r.privacy_identities = fingerprints('원고 김철수\n')
        raw = plan(); raw['keyword'] = '김철수 대여금'; raw['candidates'][0] = raw['keyword']
        with patch('pdf_analyzer.keywords.complete', AsyncMock(return_value=raw)):
            with self.assertRaises(GenerationError):
                await suggest(SOURCE, {}, r)

    async def test_bare_party_name_removed_before_final_validation(self):
        r = req(); r.keyword = '울산 대여금 반환'; r.topic = '대여금 반환 자료 준비'
        r.privacy_identities = fingerprints('원고 김철수\n')
        article = make_demo(r); article.conclusion += ' 김철수는 기록을 준비했습니다.'
        with patch('content_generator.pipeline.complete', AsyncMock(return_value=article.model_dump())), \
             patch('content_generator.pipeline.find_sources', AsyncMock(return_value={'text': '', 'sources': []})), \
             patch('content_generator.pipeline.review', AsyncMock(return_value=[])):
            final, report, *_ = await generate(r)
        self.assertTrue(report['passed'], report['issues'])
        self.assertNotIn('김철수', final.text)
        self.assertIn('052-268-3395', final.text)

    async def test_hashed_name_with_spaces_is_removed(self):
        hashes = fingerprints('원고 김철수\n')
        self.assertNotIn('김철수', str(hashes))
        self.assertEqual(remove_identities('김 철 수의 주장', hashes), '[당사자]의 주장')

    async def test_addresses_identifiers_and_private_contact_removed(self):
        text = '주소지: 울산 남구 어느로 123\n원고 김철수\n900101-1234567\n010-1234-5678\n법무법인 대한중앙 울산분사무소 연락처: 052-268-3395'
        result = clean_output(text, fingerprints(text), '052-268-3395')
        for token in ['김철수', '어느로', '900101', '010-1234']:
            self.assertNotIn(token, result)
        self.assertIn('052-268-3395', result)

    async def test_generic_lawyer_word_not_treated_as_private_name(self):
        self.assertEqual(clean_output('민사전문변호사 상담 전 확인할 사항'), '민사전문변호사 상담 전 확인할 사항')
