import io
import re
from pypdf import PdfReader
from config.settings import MAX_PDF_BYTES, MAX_SOURCE_CHARS
from content_generator.provider import complete, GenerationError
from prompt_builder.builder import prompt

FIELDS = {'case_type': '사건 유형', 'background': '사건 경위', 'issues': '핵심 쟁점',
          'decision': '법원의 판단', 'outcome': '결과', 'implications': '실무상 의미'}


def anonymize(text, remove_names=True):
    patterns = [
        (r'\b\d{6}\s*[-–]\s*[1-4]\d{6}\b', '[주민등록번호 삭제]'),
        (r'(?<!\d)(?:01[016789]|0[2-6][1-5]?)\s*[-.)]\s*\d{3,4}\s*[-.]\s*\d{4}(?!\d)', '[전화번호 삭제]'),
        (r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[이메일 삭제]'),
        (r'(?<!\d)\d{2,6}-\d{2,6}-\d{3,8}(?!\d)', '[계좌·개인번호 삭제]'),
        (r'\d{4}[.년/-]\s*\d{1,2}[.월/-]\s*\d{1,2}[.일]?\s*(?:생|출생)', '[생년월일 삭제]'),
        (r'(?:계좌(?:번호)?|주민등록번호|생년월일|연락처|전화번호)[ \t]*[:：][ \t]*[^\n]+', '[개인정보 항목 삭제]'),
        (r'(?:주소|주소지|거주지|소재지)[ \t]*[:：][ \t]*[^\n]+', '[주소 삭제]'),
        (r'(?<![가-힣])(?:서울|부산|울산|대구|광주|대전|인천|세종|경기|강원|충청|전라|경상|제주)[가-힣]*(?:특별시|광역시|특별자치도|도)?\s+[가-힣]+(?:시|군|구)\s+[^\n,]+', '[주소 삭제]'),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    if not remove_names:
        return text
    # Collect identified names, then remove repeated occurrences throughout the text.
    names = set()
    pattern = r'(?:원고|피고|피고인|신청인|채무자|채권자|고소인|피해자|성명|이름|대표자|증인|변호사)\s*[:：]?\s*([가-힣]{2,4})(?=\s|[,.(（\n]|$)'
    excluded = {'주장', '청구', '신청', '대리인', '소송', '주문', '등은', '또는', '대하여', '에게', '사이에'}
    for match in re.finditer(pattern, text):
        if match.group(1) not in excluded:
            names.add(match.group(1))
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, '[인명 삭제]')
    # Spaced role/name headings commonly found in Korean PDF judgments.
    text = re.sub(r'(원\s+고|피\s+고|피\s*고\s*인)\s*[:：]?\s*([가-힣](?:[ \t]+[가-힣]){1,3})(?=\s*\n|$)', r'\1 [인명 삭제]', text)
    return text


def extract_pdf(data):
    if len(data) > MAX_PDF_BYTES:
        raise ValueError('PDF는 10MB 이하만 지원합니다.')
    if not data.startswith(b'%PDF-'):
        raise ValueError('유효한 PDF 파일을 첨부하세요.')
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ValueError('암호화된 PDF는 지원하지 않습니다. 암호를 해제한 사본을 사용하세요.')
        if len(reader.pages) > 100:
            raise ValueError('PDF는 100쪽 이하만 지원합니다.')
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('PDF를 읽을 수 없습니다. 손상 여부를 확인하세요.') from exc
    if len(text.strip()) < 50:
        raise ValueError('추출 가능한 텍스트가 없습니다. 스캔 PDF는 OCR 후 첨부하세요.')
    if len(text) > MAX_SOURCE_CHARS:
        raise ValueError('판결문 텍스트가 40,000자를 넘습니다. 관련 판결 부분만 포함한 PDF를 사용하세요.')
    from pdf_analyzer.privacy import fingerprints, remove_identities
    identities = fingerprints(text)
    return {'privacy_identities': identities, 'text': remove_identities(anonymize(text), identities), 'pages': len(reader.pages), 'privacy_note': '인명·주소·연락처 등 패턴 기반 1차 익명화 후 AI에서 재검수합니다. 스캔·비정형 문서는 지원이 제한됩니다.'}


def verify_analysis(data, source):
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise GenerationError('판결문 분석 형식이 올바르지 않습니다.')
    for key in FIELDS:
        item = data[key]
        if not isinstance(item, dict) or set(item) != {'summary', 'evidence'} or not all(isinstance(v, str) for v in item.values()):
            raise GenerationError('판결문 분석 항목 형식이 올바르지 않습니다.')
        if not item['evidence']:
            if item['summary'] != '판결문에서 확인되지 않음':
                raise GenerationError('판결문 분석에 인용 근거가 없는 내용이 있습니다.')
        elif item['evidence'] not in source or len(item['evidence'].strip()) < 4:
            raise GenerationError('판결문 분석의 인용 근거가 원문과 일치하지 않습니다.')
        if anonymize(item['summary']) != item['summary']:
            raise GenerationError('판결문 분석에서 개인정보가 감지됐습니다.')
    return data


async def analyze_pdf(source):
    messages = [{'role': 'system', 'content': prompt('pdf_analysis.md')}, {'role': 'user', 'content': source}]
    # One focused retry provides concrete evidence failures to the analyzer.
    for attempt in range(2):
        result = await complete(messages, 3500)
        try:
            return verify_analysis(result, source)
        except GenerationError as exc:
            if attempt:
                raise
            messages.extend([{'role': 'assistant', 'content': __import__('json').dumps(result, ensure_ascii=False)},
                             {'role': 'user', 'content': prompt('evidence_repair.md') + '\n검증 오류: ' + str(exc)}])
