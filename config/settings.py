import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv('LEGAL_BLOG_DATA_DIR', str(ROOT / 'data')))
API_KEY = os.getenv('LEGAL_BLOG_API_KEY') or os.getenv('OPENAI_API_KEY', '')
MODEL = os.getenv('LEGAL_BLOG_MODEL', 'gpt-4.1-mini')
API_URL = 'https://api.openai.com/v1/chat/completions'
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_SOURCE_CHARS = 40000
MAX_REPAIRS = 3
