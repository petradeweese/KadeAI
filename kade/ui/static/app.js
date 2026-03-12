const transcriptEl = document.getElementById('transcript');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const interpretedEl = document.getElementById('interpreted');

async function loadDashboard() {
  const res = await fetch('/api/dashboard');
  const data = await res.json();
  renderDashboard(data);
}

function renderCard(id, title, rows, raw) {
  const el = document.getElementById(id);
  const list = rows.map(r => `<div class="metric">${r}</div>`).join('');
  el.innerHTML = `<h3>${title}</h3>${list}<details><summary>Show raw</summary><pre>${escapeHtml(JSON.stringify(raw || {}, null, 2))}</pre></details>`;
}

function renderDashboard(payload) {
  const oc = payload.operator_console || {};
  const market = oc.market_intelligence || {};
  const premarket = oc.premarket_gameplan || {};
  const trade = oc.trade_idea_opinion || {};
  const target = oc.target_move_board || {};
  const plan = oc.trade_plan || {};
  const tracking = oc.trade_plan_tracking || {};
  const visual = oc.visual_explainability || {};
  const strategy = oc.strategy_intelligence || {};

  document.getElementById('runtime-pill').textContent = `Runtime: ${oc.runtime?.runtime_mode || 'text_first'}`;
  document.getElementById('provider-pill').textContent = `LLM: ${oc.llm?.provider || 'mock'}`;

  renderCard('market-card', 'Market Intelligence', [
    `Regime: ${market.regime?.label || 'unknown'}`,
    `News: ${(market.key_news || []).length}`,
    `Movers: ${(market.top_movers || []).length}`,
  ], market);

  renderCard('premarket-card', 'Premarket Gameplan', [
    `Posture: ${premarket.market_posture?.posture_label || 'mixed'}`,
    `Catalysts: ${(premarket.key_catalysts || []).slice(0,2).join(', ') || 'n/a'}`,
    `Risks: ${(premarket.risks || []).slice(0,2).join(', ') || 'n/a'}`,
  ], premarket);

  renderCard('trade-idea-card', 'Trade Idea', [
    `Symbol: ${trade.symbol || 'n/a'}`,
    `Stance: ${trade.stance || 'n/a'}`,
    `Entry: ${trade.entry || 'n/a'}`,
    `Target: ${trade.target || 'n/a'}`,
  ], trade);

  renderCard('target-move-card', 'Target Move Board', [
    `Candidates: ${(target.candidates || []).length}`,
    `Active symbol: ${(target.request || {}).symbol || 'n/a'}`,
  ], target);

  renderCard('trade-plan-card', 'Trade Plan', [
    `Plan: ${plan.plan_id || 'n/a'}`,
    `Status: ${plan.status || 'n/a'}`,
    `Symbol: ${plan.symbol || 'n/a'}`,
  ], plan);

  renderCard('tracking-card', 'Tracking & Review', [
    `Tracking status: ${tracking.status_after || 'n/a'}`,
    `Review history: ${(oc.trade_review?.history || []).length}`,
  ], {tracking, review: oc.trade_review});

  renderCard('visual-card', 'Visual Explainability', [
    `Active symbol: ${visual.active_symbol || 'n/a'}`,
    `Active view: ${visual.active_view || 'n/a'}`,
    `Charts: ${(visual.charts || []).length}`,
  ], visual);

  renderCard('strategy-card', 'Strategy Intelligence', [
    `Setups: ${(strategy.setup_archetypes || []).length}`,
    `Regime rows: ${(strategy.regime_performance || []).length}`,
  ], strategy);

  document.getElementById('secondary-debug').textContent = JSON.stringify({
    execution: oc.execution,
    timeline: oc.timeline,
    providers: oc.providers,
    llm: oc.llm,
  }, null, 2);

  const symbol = payload.ui_state?.last_active_symbol;
  document.querySelectorAll('.highlightable').forEach(el => el.classList.remove('highlight'));
  if (symbol) {
    ['trade-idea-card','target-move-card','trade-plan-card','visual-card'].forEach(id => document.getElementById(id)?.classList.add('highlight'));
  }
}

async function postJson(path, payload) {
  const res = await fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
  return res.json();
}

function addMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.textContent = `${role === 'user' ? 'You' : 'Kade'}: ${text}`;
  transcriptEl.appendChild(el);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  addMessage('user', text);

  const path = /^\w+(\s+\w+=\S+)?$/.test(text) || text.startsWith('trade_') ? '/api/command' : '/api/chat';
  const key = path === '/api/command' ? 'command' : 'message';
  const data = await postJson(path, {[key]: text});

  if (path === '/api/chat') {
    interpretedEl.textContent = `Interpreted action: ${data.interpreted_action?.intent || 'n/a'} (${data.interpreted_action?.source || 'heuristic'})`;
    addMessage('kade', data.reply || 'Done');
    renderDashboard(data.dashboard);
  } else {
    interpretedEl.textContent = `Command intent: ${data.result?.intent || 'n/a'}`;
    addMessage('kade', data.result?.formatted_response || 'Done');
    renderDashboard(data.dashboard);
  }
});

document.getElementById('refresh-btn').addEventListener('click', loadDashboard);

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}

loadDashboard();
