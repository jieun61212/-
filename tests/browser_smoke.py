"""Optional browser smoke test. Starts its own server with isolated temporary data."""
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect
from tests.helpers import pdf_bytes

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as temporary:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        environment = os.environ.copy()
        environment.pop('LEGAL_BLOG_API_KEY', None)
        environment.pop('OPENAI_API_KEY', None)
        environment['LEGAL_BLOG_DATA_DIR'] = temporary
        server = subprocess.Popen(
            [str(ROOT / '.venv/bin/python'), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(60):
                try:
                    with urlopen(base + '/api/health', timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('server failed')
                    time.sleep(.1)
            else:
                raise RuntimeError('server did not start')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
                context = browser.new_context(viewport={'width': 1440, 'height': 1100}, accept_downloads=True,
                                              permissions=['clipboard-read', 'clipboard-write'])
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base)
                expect(page.locator('#generate')).to_be_enabled()
                expect(page.locator('.project-card')).to_have_count(4)
                assert page.locator('#mode').input_value() == 'demo'
                page.screenshot(path='/tmp/legal-studio-empty.png', full_page=True)
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                page.locator('input[value="civil"]').check()
                assert page.locator('#min-chars').input_value() == '1000'
                assert page.locator('#count-spaces').is_checked()
                page.locator('#lawfirm').select_option('siwoo_busan')
                page.locator('#keyword').fill('부산 계약분쟁')
                page.locator('#topic').fill('대금 지급 청구 준비')
                page.locator('#generate').click()
                expect(page.locator('#draft-result')).to_be_visible()
                expect(page.locator('#output-status')).to_have_text('예시')
                expect(page.locator('#manuscript h1')).to_contain_text('민사전문변호사')
                text = page.locator('#manuscript').inner_text()
                assert '법무법인 시우' in text and '법무법인 대한중앙' not in text and '052-268-3395' not in text
                expect(page.locator('#notice')).to_contain_text('법률 자료 검색')
                page.screenshot(path='/tmp/legal-studio-result.png', full_page=True)
                for extension in ['txt', 'docx']:
                    with page.expect_download() as download:
                        page.locator('#save-' + extension).click()
                    location = Path(temporary) / ('draft.' + extension)
                    download.value.save_as(location)
                    assert location.stat().st_size > 1000
                    if extension == 'txt':
                        assert '예시 모드' in location.read_text('utf-8-sig')
                    else:
                        assert location.read_bytes().startswith(b'PK')
                page.locator('#copy').click()
                clipboard = page.evaluate('navigator.clipboard.readText()')
                assert '예시 모드' in clipboard and '법무법인 시우' in clipboard
                page.locator('#validate').click()
                expect(page.locator('#progress')).to_be_hidden()
                expect(page.locator('#draft-result')).to_be_visible()
                page.locator('#topic').fill('입력 변경 테스트')
                expect(page.locator('#notice')).to_contain_text('입력이 변경')
                page.locator('#again').click()
                expect(page.locator('#progress')).to_be_hidden()
                expect(page.locator('#notice')).to_contain_text('입력이 변경')
                page.locator('#history-open').click()
                page.locator('#history-query').fill('대금 청구')
                expect(page.locator('.history-item')).to_have_count(2)
                page.locator('.history-load').first.click()
                expect(page.locator('#history-dialog')).not_to_be_visible()
                assert page.locator('#topic').input_value() == '대금 지급 청구 준비'
                page.locator('#pdf').set_input_files({'name': 'judgment.pdf', 'mimeType': 'application/pdf',
                    'buffer': pdf_bytes('The court dismissed the claim. The parties disputed the contract and evidence.')})
                page.locator('#pdf-preview').click()
                expect(page.locator('#pdf-dialog')).to_be_visible()
                assert 'dismissed' in page.locator('#pdf-redacted').input_value()
                page.locator('#pdf-accept').click()
                expect(page.locator('#pdf-confirm')).to_be_enabled()
                page.locator('#pdf-confirm').check()
                page.locator('#generate').click()
                expect(page.locator('#error')).to_contain_text('예시 모드는 PDF')
                page.locator('#pdf-remove').click()
                page.set_viewport_size({'width': 390, 'height': 844})
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                page.screenshot(path='/tmp/legal-studio-mobile.png', full_page=True)
                assert not errors, errors
                browser.close()
                print('Browser smoke PASS: project defaults, firm isolation, generation, review, regeneration, history, clipboard, exports, PDF preview, responsive layout; no JS errors.')
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == '__main__':
    main()
