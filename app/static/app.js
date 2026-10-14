'use strict';

const $ = id => document.getElementById(id);
const state = {config: null, draft: null, busy: false, redacted: '', snapshot: '', pdfFile: null};
const labels = {case_type: '사건 유형', background: '사건 경위', issues: '핵심 쟁점', decision: '법원의 판단', outcome: '결과', implications: '실무상 의미'};
const statuses = {final: '최종본', demo: '예시', failed: '검수·생성 실패', generating: '생성 중'};
let toastTimer, searchTimer, historyVersion = 0;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : '입력 또는 요청을 처리할 수 없습니다.');
  }
  return data;
}
function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}
function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3000);
}
function dateText(value) {
  return new Intl.DateTimeFormat('ko-KR', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul'}).format(new Date(value));
}
function selectedProject() {
  return document.querySelector('input[name="project"]:checked')?.value;
}
function inputValues() {
  return {
    project: selectedProject(), lawfirm: $('lawfirm').value,
    keyword: $('keyword').value.trim(), topic: $('topic').value.trim(),
    subkeywords: $('subkeywords').value.trim(), region: $('region').value.trim(),
    institution: $('institution').value.trim(), lawyer: $('lawyer').value.trim(),
    references: $('references').value.trim(),
    min_chars: Number($('min-chars').value), max_chars: Number($('max-chars').value),
    keyword_target: Number($('keyword-target').value), count_spaces: $('count-spaces').checked,
    pdf_privacy_confirmed: $('pdf-confirm').checked, mode: $('mode').value
  };
}
function inputFingerprint(values) {
  // Key ordering differs between browser inputs and Pydantic responses.
  return JSON.stringify(Object.keys(values).filter(k => k !== 'pdf_privacy_confirmed').sort().map(k => [k, values[k]]));
}
function fingerprint() {
  return inputFingerprint(inputValues()) + '|' + ($('pdf').files[0]?.name || '') + '|' + state.redacted;
}
function refreshNotice() {
  if (!state.draft) return;
  const messages = [];
  if (state.draft.status === 'demo') messages.push('예시 모드 원고입니다. AI 생성·공식 법률 자료 검색·의미 검수는 실행하지 않았습니다.');
  if (state.draft.pdf_used && !$('pdf').files.length) messages.push('저장된 판결문 원고입니다. ‘다시 생성’은 저장된 익명화 원문을 사용합니다. 새 입력으로 생성하려면 PDF를 다시 첨부하세요.');
  if (state.snapshot !== fingerprint()) messages.push('입력이 변경되었습니다. 오른쪽은 이전에 저장된 원고입니다. ‘원고 생성’으로 새 입력을 적용하세요.');
  $('notice').textContent = messages.join('\n');
  $('notice').hidden = !messages.length;
}
function updateMode() {
  const isDemo = $('mode').value === 'demo';
  $('mode-note').textContent = isDemo
    ? '예시 원고로 검수·이력·내보내기를 확인합니다. 실제 사건 및 PDF 생성은 AI 모드를 사용하세요.'
    : state.config.ai_available
      ? '공식 법령·법원 자료를 검색한 뒤 별도로 검수합니다. API 사용 비용이 발생할 수 있습니다.'
      : 'API 키 미설정: 서버에 LEGAL_BLOG_API_KEY를 설정하고 재시작해야 AI 원고를 생성할 수 있습니다.';
}
function applyDefaults() {
  const project = state.config.projects.find(p => p.id === selectedProject());
  $('min-chars').value = project.defaults.min_chars;
  $('max-chars').value = project.defaults.max_chars;
  $('keyword-target').value = project.defaults.keyword_target;
  $('count-spaces').checked = project.defaults.count_spaces;
  if (project.id === 'civil') toast('울(민) 지침 적용: 공백 포함 1,000~1,500자 · 민사전문변호사 제목');
  refreshNotice();
}
function updateFirm() {
  const firm = state.config.profiles.find(p => p.id === $('lawfirm').value);
  $('firm-info').replaceChildren(el('span', firm.region), el('span', firm.phone || '연락처 미등록'));
}
function setBusy(busy, title = '원고를 준비하고 있습니다') {
  state.busy = busy;
  $('input-fields').disabled = busy;
  $('generate').disabled = busy;
  $('history-open').disabled = busy;
  $('progress-title').textContent = title;
  $('progress').hidden = !busy;
  $('empty-state').hidden = busy || Boolean(state.draft);
  $('draft-result').hidden = busy || !state.draft;
  for (const id of ['again', 'validate', 'copy', 'save-txt', 'save-docx']) $(id).disabled = busy || !state.draft;
  $('output-status').textContent = busy ? '처리 중' : state.draft ? statuses[state.draft.status] : '작성 전';
}
function renderDraft(draft) {
  if (!draft.article || !draft.report?.passed) throw new Error('검수를 통과한 최종 원고가 아닙니다.');
  state.draft = draft;
  state.snapshot = inputFingerprint(draft.request) + '|' + ($('pdf').files[0]?.name || '') + '|' + state.redacted;
  const article = draft.article, report = draft.report;
  $('output-status').textContent = statuses[draft.status];
  $('output-status').className = 'pill ' + (draft.status === 'demo' ? 'demo' : 'complete');
  const project = state.config.projects.find(p => p.id === draft.request.project);
  const firm = state.config.profiles.find(p => p.id === draft.request.lawfirm);
  $('metrics').replaceChildren();
  for (const [label, value] of [
    ['프로젝트', project.name], ['법인', firm.name], [report.count_spaces ? '공백 포함' : '공백 제외', report.chars + '자'],
    ['키워드', report.keyword_count + '회'], ['자동 수정', draft.repairs + '회']
  ]) {
    const metric = el('span', label, 'metric');
    metric.append(el('strong', value));
    $('metrics').append(metric);
  }
  $('title-list').replaceChildren();
  article.titles.forEach((title, index) => {
    const item = el('li', title, index === article.selected_title_index ? 'selected' : '');
    if (index === article.selected_title_index) item.append(el('span', '선정', 'selected-tag'));
    $('title-list').append(item);
  });
  const doc = $('manuscript');
  doc.replaceChildren(el('h1', article.titles[article.selected_title_index]));
  for (const paragraph of article.introduction.split('\n\n')) doc.append(el('p', paragraph));
  for (const section of article.sections) {
    doc.append(el('h2', section.question), el('p', section.answer, 'answer'));
    for (const paragraph of section.explanation.split('\n\n')) doc.append(el('p', paragraph));
  }
  doc.append(el('h2', '핵심 체크리스트'));
  const list = el('ul');
  article.checklist.forEach(item => list.append(el('li', item)));
  doc.append(list, el('h2', '결론'), el('p', article.conclusion), el('p', article.cta, 'cta'));
  $('review-list').replaceChildren();
  report.checks.forEach(check => {
    const item = el('li');
    item.append(el('strong', (check.passed ? '✓ ' : '✕ ') + check.label), el('small', check.detail));
    $('review-list').append(item);
  });
  $('review-summary').textContent = report.checks.length + '개 항목 통과' + (draft.status === 'demo' ? ' · 규칙 검수만' : ' · AI 대조 포함');
  $('pdf-analysis').hidden = !draft.analysis;
  $('analysis-content').replaceChildren();
  if (draft.analysis) {
    for (const [key, value] of Object.entries(draft.analysis)) {
      const item = el('div', undefined, 'analysis-item');
      item.append(el('strong', labels[key] || key), el('p', value.summary));
      if (value.evidence) item.append(el('blockquote', value.evidence));
      $('analysis-content').append(item);
    }
  }
  $('research-detail').hidden = !draft.research;
  $('research-content').replaceChildren();
  if (draft.research) {
    $('research-content').append(el('p', draft.research.text, 'research-note'));
    for (const source of draft.research.sources) {
      try {
        const url = new URL(source.url);
        if (url.protocol !== 'https:' || !/(^|\.)((law|scourt)\.go\.kr)$/.test(url.hostname)) continue;
        const link = el('a', source.title, 'source-link');
        link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        $('research-content').append(link);
      } catch (_) { /* Ignore malformed citation URLs. */ }
    }
  }
  $('saved-info').textContent = dateText(draft.updated_at) + ' · 이력 #' + draft.id + ' 저장';
  $('empty-state').hidden = true;
  $('draft-result').hidden = false;
  refreshNotice();
}
async function perform(action, title) {
  if (state.busy) return;
  $('error').hidden = true;
  setBusy(true, title);
  try {
    renderDraft(await action());
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
    refreshNotice();
  }
}
$('draft-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!state.config || state.busy) return;
  const values = inputValues();
  if (values.max_chars - values.min_chars < 100) return showError('최대 글자 수는 최소 글자 수보다 100자 이상 커야 합니다.');
  if (values.mode === 'ai' && !state.config.ai_available) return showError('AI API 키가 없습니다. 서버 환경변수 LEGAL_BLOG_API_KEY를 설정하고 서버를 재시작하세요.');
  if ($('pdf').files.length && !values.pdf_privacy_confirmed) return showError('익명화 원문을 확인하고 개인정보 검토 완료를 체크하세요.');
  if ($('pdf').files.length && values.mode === 'demo') return showError('예시 모드는 PDF 원고를 지원하지 않습니다. AI 모드를 선택하거나 첨부를 해제하세요.');
  const form = new FormData();
  form.append('payload', JSON.stringify(values));
  if ($('pdf').files[0]) {
    form.append('pdf', $('pdf').files[0]);
    form.append('pdf_text', state.redacted);
  }
  perform(() => api('/api/generate', {method: 'POST', body: form}), values.mode === 'demo' ? '예시 원고와 검수 결과를 준비합니다' : '근거 자료를 확인하고 원고를 작성합니다');
});
$('again').addEventListener('click', () => {
  const id = state.draft?.id;
  if (!id) return;
  perform(() => api('/api/drafts/' + id + '/regenerate', {method: 'POST'}), '저장된 동일 입력으로 다시 작성합니다');
});
$('validate').addEventListener('click', () => {
  const id = state.draft?.id;
  if (!id) return;
  perform(async () => {
    try { return await api('/api/drafts/' + id + '/validate', {method: 'POST'}); }
    catch (error) {
      // A failed revalidation revokes the old final. Never leave it exportable.
      const latest = await api('/api/drafts/' + id);
      if (latest.status === 'failed') {
        state.draft = null;
        $('draft-result').hidden = true;
        $('notice').hidden = true;
        $('output-status').className = 'pill';
      }
      throw error;
    }
  }, '저장된 원고를 독립 검수하고 수정합니다');
});
$('copy').addEventListener('click', async () => {
  if (!state.draft) return;
  const text = (state.draft.status === 'demo' ? '[예시 모드 · AI 생성 및 법률 사실 검증 미실행]\n\n' : '') + state.draft.text;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const area = el('textarea', text);
      area.style.position = 'fixed'; area.style.opacity = '0';
      document.body.append(area); area.select();
      const copied = document.execCommand('copy'); area.remove();
      if (!copied) throw new Error('copy failed');
    }
    toast('원고를 복사했습니다.');
  } catch (_) { showError('브라우저가 복사를 허용하지 않습니다. txt 저장을 사용하세요.'); }
});
for (const format of ['txt', 'docx']) {
  $('save-' + format).addEventListener('click', async () => {
    if (!state.draft) return;
    try {
      const response = await fetch('/api/drafts/' + state.draft.id + '/export/' + format);
      if (!response.ok) throw new Error('최종 원고를 내보낼 수 없습니다.');
      const url = URL.createObjectURL(await response.blob());
      const link = el('a'); link.href = url; link.download = '법률원고-' + state.draft.id + '.' + format;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { showError(error.message); }
  });
}
function resetPdf() {
  state.redacted = ''; state.pdfFile = null;
  $('pdf-confirm').checked = false; $('pdf-confirm').disabled = true;
}
function onPdfChange() {
  resetPdf();
  const file = $('pdf').files[0];
  if (file && (!file.name.toLowerCase().endsWith('.pdf') || file.size > 10 * 1024 * 1024)) {
    $('pdf').value = ''; showError('10MB 이하의 PDF를 선택하세요.');
  }
  const current = $('pdf').files[0];
  state.pdfFile = current || null;
  $('pdf-label').textContent = current ? current.name : '판결문 PDF 첨부';
  $('pdf-actions').hidden = !current;
  refreshNotice();
}
$('pdf').addEventListener('change', onPdfChange);
$('pdf-remove').addEventListener('click', () => { $('pdf').value = ''; onPdfChange(); });
$('pdf-preview').addEventListener('click', async () => {
  const file = $('pdf').files[0];
  if (!file) return;
  $('pdf-preview').disabled = true;
  try {
    if (!state.redacted) {
      const form = new FormData(); form.append('pdf', file);
      const result = await api('/api/pdf/preview', {method: 'POST', body: form});
      // Do not attach a slow response to a different file selected meanwhile.
      if ($('pdf').files[0] !== file) return;
      state.redacted = result.text;
    }
    $('pdf-redacted').value = state.redacted;
    $('pdf-dialog').showModal();
  } catch (error) { showError(error.message); }
  finally { $('pdf-preview').disabled = false; }
});
$('pdf-accept').addEventListener('click', () => {
  const text = $('pdf-redacted').value.trim();
  if (text.length < 50) return toast('판결문 텍스트는 최소 50자가 필요합니다.');
  state.redacted = text;
  $('pdf-confirm').disabled = false; $('pdf-confirm').checked = false;
  $('pdf-dialog').close();
  toast('원문을 적용했습니다. 개인정보 검토 완료를 체크하세요.');
});
const box = $('upload-box');
for (const name of ['dragenter', 'dragover']) {
  box.addEventListener(name, event => { event.preventDefault(); if (!state.busy) box.classList.add('dragging'); });
}
box.addEventListener('dragleave', () => box.classList.remove('dragging'));
box.addEventListener('drop', event => {
  event.preventDefault(); box.classList.remove('dragging');
  if (state.busy || !event.dataTransfer.files.length) return;
  const transfer = new DataTransfer(); transfer.items.add(event.dataTransfer.files[0]);
  $('pdf').files = transfer.files; onPdfChange();
});
function restoreInputs(request) {
  document.querySelector('input[name="project"][value="' + request.project + '"]').checked = true;
  for (const name of ['lawfirm', 'keyword', 'topic', 'subkeywords', 'region', 'institution', 'lawyer', 'references', 'mode']) $(name).value = request[name] || '';
  $('min-chars').value = request.min_chars; $('max-chars').value = request.max_chars;
  $('keyword-target').value = request.keyword_target; $('count-spaces').checked = request.count_spaces;
  $('pdf').value = ''; onPdfChange(); updateFirm(); updateMode();
}
async function loadHistory() {
  const version = ++historyVersion;
  const params = new URLSearchParams({q: $('history-query').value, project: $('history-project').value, lawfirm: $('history-firm').value});
  try {
    const result = await api('/api/history?' + params);
    if (version !== historyVersion) return;
    $('history-items').replaceChildren();
    if (!result.items.length) $('history-items').append(el('p', '일치하는 작성 이력이 없습니다.', 'help'));
    for (const item of result.items) {
      const row = el('div', undefined, 'history-item');
      const load = el('button', undefined, 'history-load');
      load.type = 'button';
      load.append(el('strong', item.title || item.topic));
      const project = state.config.projects.find(p => p.id === item.project)?.name || item.project;
      const firm = state.config.profiles.find(p => p.id === item.lawfirm)?.name || item.lawfirm;
      load.append(el('small', [dateText(item.created_at), project, firm, statuses[item.status], item.pdf_used ? 'PDF 사용' : '정보성'].join(' · ')));
      load.addEventListener('click', async () => {
        if (!['final', 'demo'].includes(item.status)) return toast('이 원고는 최종 검수를 완료하지 못했습니다.');
        try {
          const draft = await api('/api/drafts/' + item.id);
          restoreInputs(draft.request);
          renderDraft(draft);
          setBusy(false);
          $('history-dialog').close();
        } catch (error) { toast(error.message); }
      });
      const remove = el('button', '삭제', 'button small subtle'); remove.type = 'button';
      remove.addEventListener('click', async () => {
        if (!confirm('이 원고와 저장된 익명화 자료를 삭제할까요?')) return;
        try {
          await api('/api/drafts/' + item.id, {method: 'DELETE'});
          if (state.draft?.id === item.id) {
            state.draft = null; $('notice').hidden = true; setBusy(false);
          }
          loadHistory();
        } catch (error) { toast(error.message); }
      });
      row.append(load, remove); $('history-items').append(row);
    }
  } catch (error) { toast(error.message); }
}
$('history-open').addEventListener('click', () => { $('history-dialog').showModal(); loadHistory(); });
$('history-query').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadHistory, 250); });
for (const id of ['history-project', 'history-firm']) $(id).addEventListener('change', loadHistory);
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
$('draft-form').addEventListener('input', refreshNotice);
$('lawfirm').addEventListener('change', updateFirm);
$('mode').addEventListener('change', updateMode);

async function initialize() {
  try {
    state.config = await api('/api/config');
    for (const [index, project] of state.config.projects.entries()) {
      const label = el('label', undefined, 'project-card');
      const radio = document.createElement('input');
      radio.type = 'radio'; radio.name = 'project'; radio.value = project.id; radio.checked = index === 0; radio.required = true;
      radio.addEventListener('change', applyDefaults);
      label.append(radio, el('strong', project.name), el('small', project.description));
      $('project-options').append(label);
      $('history-project').append(new Option(project.name, project.id));
    }
    for (const profile of state.config.profiles) {
      $('lawfirm').append(new Option(profile.name, profile.id));
      $('history-firm').append(new Option(profile.name, profile.id));
    }
    $('mode').value = state.config.ai_available ? 'ai' : 'demo';
    applyDefaults(); updateFirm(); updateMode(); setBusy(false);
  } catch (error) { showError('설정을 불러오지 못했습니다. ' + error.message); }
}
initialize();
