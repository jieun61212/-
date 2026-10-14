import asyncio
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from app.models import ArticleInput, Article
from app import storage
from config import settings
from config.catalog import projects, profiles
from content_generator.pipeline import generate
from content_generator.provider import GenerationError
from pdf_analyzer.analyzer import extract_pdf, anonymize
from exporter.files import txt_bytes, docx_bytes

logger = logging.getLogger('legal_blog')
# Deliberately log lifecycle metadata only; no sources, prompts, keys or manuscripts.
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
work_slots = asyncio.Semaphore(2)
active_ids = set()


@asynccontextmanager
async def lifespan(app):
    storage.connect().close()
    yield


app = FastAPI(title='법률 원고 스튜디오', lifespan=lifespan)
static = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=static), name='static')


@app.get('/')
def index():
    return FileResponse(static / 'index.html')


@app.get('/api/health')
def health():
    with storage.connect() as db:
        db.execute('SELECT 1').fetchone()
    return {'status': 'ok', 'database': 'ok'}


@app.get('/api/config')
def configuration():
    return {'projects': projects(), 'profiles': profiles(), 'ai_available': bool(settings.API_KEY),
            'model': settings.MODEL, 'max_pdf_mb': settings.MAX_PDF_BYTES // (1024 * 1024)}


async def read_pdf(pdf):
    if not pdf or not pdf.filename:
        return None
    try:
        if not pdf.filename.lower().endswith('.pdf'):
            raise ValueError('PDF 파일만 첨부할 수 있습니다.')
        data = await pdf.read(settings.MAX_PDF_BYTES + 1)
        return await asyncio.to_thread(extract_pdf, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await pdf.close()


@app.post('/api/pdf/preview')
async def preview_pdf(pdf: UploadFile = File(...)):
    result = await read_pdf(pdf)
    if not result:
        raise HTTPException(422, 'PDF를 첨부하세요.')
    return result


def response_for(row):
    is_final = row['status'] in ('final', 'demo')
    return {'id': row['id'], 'created_at': row['created_at'], 'updated_at': row['updated_at'],
            'status': row['status'], 'request': json.loads(row['request_json']),
            'article': json.loads(row['article_json']) if is_final else None,
            'text': row['final_text'] if is_final else '',
            'analysis': json.loads(row['analysis_json'] or 'null') if is_final else None,
            'research': json.loads(row['research_json'] or 'null') if is_final else None,
            'report': json.loads(row['report_json'] or 'null') if is_final else None,
            'repairs': row['repairs'], 'pdf_used': bool(row['pdf_used'])}


async def run_generation(draft_id, request, source='', previous=None, analysis=None, research=None):
    if draft_id in active_ids:
        raise HTTPException(409, '이미 생성 또는 검수 중인 원고입니다.')
    active_ids.add(draft_id)
    try:
        async with work_slots:
            article, report, analyzed, researched, repairs = await generate(request, source, previous, analysis, research)
        storage.finish(draft_id, article, report, analyzed, researched, repairs, request.mode)
        logger.info('draft=%s status=%s repairs=%s', draft_id, request.mode, repairs)
        return response_for(storage.get(draft_id))
    except GenerationError as exc:
        storage.fail(draft_id)
        logger.warning('draft=%s generation_failed', draft_id)
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        storage.fail(draft_id)
        logger.error('draft=%s internal_error type=%s', draft_id, type(exc).__name__)
        raise HTTPException(500, '원고 처리를 완료하지 못했습니다. 서버 설정을 확인해 주세요.') from exc
    finally:
        active_ids.discard(draft_id)


@app.post('/api/generate')
async def create_draft(payload: str = Form(..., max_length=24000), pdf: UploadFile | None = File(None),
                       pdf_text: str = Form('', max_length=40000)):
    try:
        request = ArticleInput.model_validate_json(payload)
    except ValidationError as exc:
        # ValidationError may echo the complete input; report only human-readable reasons.
        raise HTTPException(422, '; '.join(str(e['msg']) for e in exc.errors(include_input=False))) from exc
    if request.mode == 'ai' and not settings.API_KEY:
        raise HTTPException(503, 'AI API 키가 없습니다. 서버 환경변수 LEGAL_BLOG_API_KEY를 설정한 뒤 서버를 재시작하세요.')
    if request.mode == 'demo' and pdf and pdf.filename:
        raise HTTPException(422, '판결문 기반 생성은 AI 모드에서만 지원합니다. 예시 모드에서는 PDF 첨부를 해제하세요.')
    if pdf and pdf.filename and not request.pdf_privacy_confirmed:
        raise HTTPException(422, '익명화된 판결문을 확인하고 개인정보 검토 완료를 체크하세요.')
    extracted = await read_pdf(pdf)
    source = extracted['text'] if extracted else ''
    if extracted and pdf_text:
        if len(pdf_text.strip()) < 50:
            raise HTTPException(422, '익명화 후 판결문은 최소 50자의 텍스트가 필요합니다.')
        source = anonymize(pdf_text)
    request.references = anonymize(request.references)
    draft_id = storage.create(request, source)
    return await run_generation(draft_id, request, source)


@app.post('/api/drafts/{draft_id}/validate')
async def validate_draft(draft_id: int):
    row = storage.get(draft_id)
    if not row or row['status'] not in ('final', 'demo'):
        raise HTTPException(404, '검수 가능한 최종 원고가 없습니다.')
    request = ArticleInput.model_validate_json(row['request_json'])
    return await run_generation(draft_id, request, row['source'], Article.model_validate_json(row['article_json']),
                                json.loads(row['analysis_json'] or 'null'), json.loads(row['research_json'] or 'null'))


@app.post('/api/drafts/{draft_id}/regenerate')
async def regenerate_draft(draft_id: int):
    row = storage.get(draft_id)
    if not row or row['status'] not in ('final', 'demo'):
        raise HTTPException(404, '다시 생성할 원고가 없습니다.')
    request = ArticleInput.model_validate_json(row['request_json'])
    new_id = storage.create(request, row['source'])
    return await run_generation(new_id, request, row['source'])


@app.get('/api/history')
def history(q: str = Query('', max_length=200), project: str = '', lawfirm: str = ''):
    return {'items': storage.history(q.strip(), project, lawfirm)}


@app.get('/api/drafts/{draft_id}')
def get_draft(draft_id: int):
    row = storage.get(draft_id)
    if not row:
        raise HTTPException(404, '원고가 없습니다.')
    return response_for(row)


@app.delete('/api/drafts/{draft_id}')
def delete_draft(draft_id: int):
    if draft_id in active_ids:
        raise HTTPException(409, '처리 중인 원고는 삭제할 수 없습니다.')
    if not storage.delete(draft_id):
        raise HTTPException(404, '원고가 없습니다.')
    return {'deleted': True}


@app.get('/api/drafts/{draft_id}/export/{filetype}')
def export_draft(draft_id: int, filetype: str):
    row = storage.get(draft_id)
    if not row or row['status'] not in ('final', 'demo'):
        raise HTTPException(404, '내보낼 수 있는 최종 원고가 없습니다.')
    article = Article.model_validate_json(row['article_json'])
    if filetype == 'txt':
        data, mime = txt_bytes(article, row['status'] == 'demo'), 'text/plain; charset=utf-8'
    elif filetype == 'docx':
        data, mime = docx_bytes(article, row['status'] == 'demo'), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        raise HTTPException(422, 'txt 또는 docx만 지원합니다.')
    return Response(data, media_type=mime, headers={'Content-Disposition': f'attachment; filename="legal-blog-{draft_id}.{filetype}"'})
