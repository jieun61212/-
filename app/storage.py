import json
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from config.settings import DATA_DIR


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA_DIR / 'history.sqlite3', timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('''CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        project TEXT NOT NULL, lawfirm TEXT NOT NULL, keyword TEXT NOT NULL, topic TEXT NOT NULL,
        pdf_used INTEGER NOT NULL, status TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
        final_text TEXT NOT NULL DEFAULT '', request_json TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT '', analysis_json TEXT, research_json TEXT,
        article_json TEXT, report_json TEXT, repairs INTEGER NOT NULL DEFAULT 0
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS drafts_keyword ON drafts(keyword)')
    return con


def now():
    return datetime.now(timezone.utc).isoformat()


def create(request, source=''):
    with connect() as db:
        cursor = db.execute('''INSERT INTO drafts
            (created_at,updated_at,project,lawfirm,keyword,topic,pdf_used,status,request_json,source)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (now(), now(), request.project, request.lawfirm, request.keyword, request.topic,
             bool(source), 'generating', request.model_dump_json(), source))
        return cursor.lastrowid


def finish(draft_id, article, report, analysis, research, repairs, mode):
    with connect() as db:
        db.execute('''UPDATE drafts SET updated_at=?, status=?, title=?, final_text=?,
            article_json=?, report_json=?, analysis_json=?, research_json=?, repairs=? WHERE id=?''',
            (now(), 'demo' if mode == 'demo' else 'final', article.title, article.text,
             article.model_dump_json(), json.dumps(report, ensure_ascii=False),
             json.dumps(analysis, ensure_ascii=False), json.dumps(research, ensure_ascii=False), repairs, draft_id))


def fail(draft_id):
    with connect() as db:
        db.execute('UPDATE drafts SET status=?,updated_at=? WHERE id=?', ('failed', now(), draft_id))


def get(draft_id):
    with connect() as db:
        row = db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
        return dict(row) if row else None


def delete(draft_id):
    with connect() as db:
        return db.execute('DELETE FROM drafts WHERE id=?', (draft_id,)).rowcount


def history(query='', project='', lawfirm=''):
    conditions, values = [], []
    for field, value in [('project', project), ('lawfirm', lawfirm)]:
        if value:
            conditions.append(field + '=?')
            values.append(value)
    if query:
        tokens = [query] + query.split()
        clauses = []
        for token in tokens[:8]:
            escaped = token.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(keyword LIKE ? ESCAPE '\\' OR topic LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')")
            values.extend(['%' + escaped + '%'] * 3)
        conditions.append('(' + ' OR '.join(clauses) + ')')
    sql = 'SELECT id,created_at,updated_at,project,lawfirm,keyword,topic,pdf_used,status,title FROM drafts'
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    sql += ' ORDER BY id DESC LIMIT 100'
    with connect() as db:
        rows = [dict(row) for row in db.execute(sql, values).fetchall()]
    if query:
        rows.sort(key=lambda row: max(SequenceMatcher(None, query, row['keyword']).ratio(), SequenceMatcher(None, query, row['topic']).ratio()), reverse=True)
    return rows
