import {query, readInput, encodeInput} from './api.js';
import {el, evidence, table} from './table.js';

const byId = id => document.getElementById(id);
const SLOTS = [
  ['original', '原票'],
  ['correction_a', '产权更正一'],
  ['correction_b', '产权更正二'],
];
const DEMO = {
  key: 'P1',
  book: '表决议案,外部记录值(平方米)\nP1,100\n',
  slots: {
    original: {kind: '一般', estate: 'A:50:甲=100;B:50:乙=100', ballot: '甲:赞成;乙:赞成'},
    correction_a: {kind: '一般', estate: 'A:50:甲=100;B:50:乙=100', ballot: '甲:赞成;乙:反对'},
    correction_b: {kind: '一般', estate: 'A:60:甲=100;B:40:乙=100', ballot: '甲:赞成;乙:赞成'},
  },
};
let current = null;
let reviewVersion = 0;
let bookUpload = null;

function notice(message, error = false) {
  const node = byId('corr-notice');
  node.value = message;
  node.classList.toggle('problem', error);
}

function buildForm() {
  const root = byId('corr-slots');
  for (const [slot, label] of SLOTS) {
    const fieldset = el('fieldset');
    fieldset.className = 'corr-slot';
    fieldset.append(el('legend', label));
    for (const [name, text, rows] of [['kind', '议案类别（一般/特别）', null],
                                      ['estate', '产权单元 房屋:面积:业主=份额;…', 2],
                                      ['ballot', '表决票 业主:赞成/反对/弃权;…', 2]]) {
      const wrap = el('label');
      wrap.append(el('span', text));
      const control = rows ? el('textarea') : el('input');
      control.id = `corr-${slot}-${name}`;
      control.maxLength = name === 'kind' ? 8 : 4000;
      if (rows) control.rows = rows;
      wrap.append(control);
      fieldset.append(wrap);
    }
    root.append(fieldset);
  }
}

function payload() {
  const key = byId('corr-key').value.trim();
  const pack = {key, original: null, correction_a: null, correction_b: null};
  for (const [slot] of SLOTS) {
    pack[slot] = {
      key,
      kind: byId(`corr-${slot}-kind`).value.trim(),
      estate: byId(`corr-${slot}-estate`).value.trim(),
      ballot: byId(`corr-${slot}-ballot`).value.trim(),
    };
  }
  const text = byId('corr-book-csv').value;
  if (bookUpload && text === bookUpload.text) pack.book_base64 = encodeInput(bookUpload.bytes);
  else if (text.length) pack.book = text;
  return pack;
}

function statusTag(report) {
  const stable = report.status === '结论不变';
  return el('span', report.status, stable ? 'state' : 'state problem');
}

function bookTag(row) {
  if (!row) return el('span', '未参与对账', 'state problem');
  const bad = row.code !== 'MATCH';
  const text = bad ? `${row.code} Δ${row.delta}` : `对账一致 Δ${row.delta}`;
  return el('span', text, bad ? 'state problem' : 'state');
}

function showProof(variant) {
  const panel = byId('corr-signal');
  byId('corr-evidence-key').textContent = variant.label;
  if (!variant.ok) {
    panel.replaceChildren(el('p', `${variant.code} · ${variant.detail}`, 'empty problem'));
    return;
  }
  const content = el('dl');
  for (const item of variant.proof) {
    content.append(el('dt', item.metric), el('dd', item.unit ? `${item.value} ${item.unit}` : item.value));
  }
  panel.replaceChildren(content);
}

function render(report) {
  current = report;
  const cid = report.manifest.correction_id;
  byId('corr-run-id').textContent = cid.slice(0, 9);
  byId('corr-run-id').title = cid;
  byId('corr-export').href = `/api/corrections/${cid}/export`;
  const columns = [
    ['路别', 'label'],
    ['议案', 'key'],
    ['赞成面积', row => (row.ok ? `${row.amount} ${row.unit}` : '—')],
    ['双门槛', row => (row.ok ? el('span', row.metrics['双门槛'],
                                   row.passed ? 'state' : 'state problem')
                              : el('span', row.code, 'state problem'))],
    ['外部账', row => bookTag(row.book)],
    ['依据', row => {
      const cell = el('div');
      const button = el('button', '查看依据', 'btn');
      button.type = 'button';
      button.addEventListener('click', () => showProof(row));
      cell.append(button, evidence('录入字段', row.raw.map(String)));
      return cell;
    }],
  ];
  const head = el('div');
  head.className = 'corr-verdict';
  head.append(statusTag(report), el('span', `议案 ${report.key} · ${report.reason}`));
  const grid = byId('corr-grid');
  grid.replaceChildren(head);
  table(grid, columns, report.variants);
  grid.prepend(head);
  if (report.flips.length) {
    grid.append(evidence('结论翻转', report.flips.map(item => item.detail)));
  }
  showProof(report.variants[0]);
}

async function refreshReview() {
  if (!current) return;
  const cid = current.manifest.correction_id;
  const timeline = await query(`/api/corrections/${cid}/reviews`);
  reviewVersion = timeline[0]?.version || 0;
  byId('corr-review').hidden = false;
  const select = byId('corr-decision');
  select.querySelector('option').textContent = current.stable ? '确认' : '确认（结论不变时可用）';
  if (timeline.length) {
    const history = evidence('已登记复核', timeline.map(item =>
      `v${item.version} ${item.decision} ${item.note}`));
    byId('corr-grid').append(history);
  }
}

export function mount() {
  buildForm();
  byId('corr-demo').addEventListener('click', () => {
    byId('corr-key').value = DEMO.key;
    byId('corr-book-csv').value = DEMO.book;
    bookUpload = null;
    for (const [slot] of SLOTS) {
      for (const name of ['kind', 'estate', 'ballot']) {
        byId(`corr-${slot}-${name}`).value = DEMO.slots[slot][name];
      }
    }
    notice('已载入互斥更正样例：更正一会使结论由通过变为未通过');
  });
  byId('corr-book-file').addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      const [text, bytes] = await readInput(file);
      byId('corr-book-csv').value = text;
      bookUpload = {text, bytes};
      notice(`已读取外部账 ${file.name}`);
    } catch (error) {
      event.target.value = '';
      notice(error.message, true);
    }
  });
  byId('correction-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const report = await query('/api/corrections', payload());
      render(report);
      await refreshReview();
      notice(report.stable ? '三路结论一致，可直接确认' : '结论打架或存在隔离，须留待核实');
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId('corr-review').addEventListener('submit', async event => {
    event.preventDefault();
    const cid = current.manifest.correction_id;
    const note = byId('corr-review-note');
    try {
      await query(`/api/corrections/${cid}/reviews`,
                  {version: reviewVersion, decision: byId('corr-decision').value, note: note.value});
      note.value = '';
      notice('复核已登记');
      await refreshReview();
    } catch (error) {
      notice(error.message, true);
      if (error.status === 409) await refreshReview();
    }
  });
}

export function activate(active) {
  byId('correction-desk').hidden = !active;
}
