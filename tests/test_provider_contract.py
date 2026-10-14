import unittest
from unittest.mock import AsyncMock, patch
import httpx
from app.models import ArticleInput
from content_generator.provider import complete, GenerationError
from content_generator.research import research


def fake_client(payload, status=200):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = httpx.Response(status, json=payload,
        request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
    return client


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_writer_json_response(self):
        client = fake_client({'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]})
        with patch('config.settings.API_KEY', 'test-only'), patch('httpx.AsyncClient', return_value=client):
            result = await complete([{'role': 'user', 'content': 'test'}])
        self.assertEqual(result, {'ok': True})
        self.assertEqual(client.post.call_args.kwargs['json']['response_format'], {'type': 'json_object'})

    async def test_truncated_response_blocked(self):
        client = fake_client({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]})
        with patch('config.settings.API_KEY', 'test-only'), patch('httpx.AsyncClient', return_value=client):
            with self.assertRaisesRegex(GenerationError, '길이 제한'):
                await complete([])

    async def test_provider_error_does_not_echo_secret_or_body(self):
        client = fake_client({'error': 'private source and test-only secret'}, 401)
        with patch('config.settings.API_KEY', 'test-only'), patch('httpx.AsyncClient', return_value=client):
            with self.assertRaises(GenerationError) as caught:
                await complete([])
        self.assertNotIn('private source', str(caught.exception)); self.assertNotIn('test-only', str(caught.exception))

    async def test_search_requires_completed_call_and_official_citation(self):
        payload = {'status': 'completed', 'output': [
            {'type': 'web_search_call', 'status': 'completed'},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': '공식 자료 메모',
                'annotations': [{'type': 'url_citation', 'title': '민법', 'url': 'https://www.law.go.kr/법령/민법'}]}]}]}
        client = fake_client(payload)
        req = ArticleInput(project='civil', lawfirm='siwoo_busan', keyword='계약분쟁', topic='계약 이행')
        with patch('config.settings.API_KEY', 'test-only'), patch('httpx.AsyncClient', return_value=client):
            result = await research(req)
        self.assertEqual(result['sources'][0]['title'], '민법')
        self.assertEqual(client.post.call_args.kwargs['json']['tools'][0]['filters']['allowed_domains'], ['law.go.kr', 'scourt.go.kr'])

    async def test_search_without_real_search_call_rejected(self):
        client = fake_client({'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '검색한 척한 내용',
            'annotations': [{'type': 'url_citation', 'url': 'https://law.go.kr/'}]}]}]})
        req = ArticleInput(project='civil', lawfirm='siwoo_busan', keyword='계약분쟁', topic='계약 이행')
        with patch('config.settings.API_KEY', 'test-only'), patch('httpx.AsyncClient', return_value=client):
            with self.assertRaisesRegex(GenerationError, '공식 자료'):
                await research(req)

    async def test_unofficial_citation_rejected(self):
        client = fake_client({'status': 'completed', 'output': [
            {'type': 'web_search_call', 'status': 'completed'},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': '비공식 메모',
                'annotations': [{'type': 'url_citation', 'url': 'https://law.go.kr.fake.example/'}]}]}]})
        req = ArticleInput(project='civil', lawfirm='siwoo_busan', keyword='계약분쟁', topic='계약 이행')
        with patch('config.settings.API_KEY', 'test-only'), patch('httpx.AsyncClient', return_value=client):
            with self.assertRaises(GenerationError):
                await research(req)
