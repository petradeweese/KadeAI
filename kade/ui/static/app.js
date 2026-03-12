const transcriptEl = document.getElementById('transcript');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const interpretedEl = document.getElementById('interpreted');

const MODE_TITLES = {
  overview: 'Overview Workspace',
  market: 'Market Workspace',
  trade: 'Trade Workspace',
  tracking: 'Tracking Workspace',
  review: 'Review Workspace',
  analysis: 'Analysis Workspace',
};

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
  const layoutState = payload.ui_state || {};

  document.getElementById('runtime-pill').textContent = `Runtime: ${oc.runtime?.runtime_mode || 'text_first'}`;
  document.getElementById('provider-pill').textContent = `LLM: ${oc.llm?.provider || 'mock'}`;

  document.getElementById('workspace-mode').textContent = layoutState.active_workspace_mode || 'overview';
  document.getElementById('active-symbol').textContent = layoutState.active_symbol || '-';
  document.getElementById('last-intent').textContent = layoutState.last_interpreted_intent || '-';
  document.getElementById('workspace-title').textContent = MODE_TITLES[layoutState.active_workspace_mode] || MODE_TITLES.overview;

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

  renderCard('radar-card', 'Radar Watchlist', [
    `Top signals: ${(oc.radar?.top_signals || []).length}`,
    `High-quality: ${(oc.radar?.quality_buckets?.top_quality || []).length}`,
  ], oc.radar || {});

  renderCard('movers-card', 'Movers & Watchlist', [
    `Top movers: ${(market.top_movers || []).length}`,
    `Most active: ${(market.most_active || []).length}`,
    `Watchlist: ${(premarket.watchlist_priorities || []).slice(0,3).join(', ') || 'n/a'}`,
  ], { movers: market.top_movers, active: market.most_active, watchlist: premarket.watchlist_priorities });

  renderCard('trade-idea-card', 'Trade Idea', [
    `Symbol: ${trade.symbol || layoutState.active_symbol || 'n/a'}`,
    `Stance: ${trade.stance || 'n/a'}`,
    `Entry: ${trade.entry || 'n/a'}`,
    `Target: ${trade.target || 'n/a'}`,
  ], trade);

  renderCard('target-move-card', 'Target Move Board', [
    `Candidates: ${(target.candidates || []).length}`,
    `Active symbol: ${(target.request || {}).symbol || layoutState.active_symbol || 'n/a'}`,
  ], target);

  renderCard('trade-plan-card', 'Trade Plan', [
    `Plan: ${plan.plan_id || 'n/a'}`,
    `Status: ${plan.status || 'n/a'}`,
    `Symbol: ${plan.symbol || layoutState.active_symbol || 'n/a'}`,
  ], plan);

  renderCard('tracking-card', 'Trade Plan Tracking', [
    `Tracking status: ${tracking.status_after || 'n/a'}`,
    `Plan: ${tracking.plan_id || plan.plan_id || 'n/a'}`,
  ], tracking);

  renderCard('visual-card', 'Visual Explainability', [
    `Active symbol: ${visual.active_symbol || layoutState.active_symbol || 'n/a'}`,
    `Active view: ${visual.active_view || layoutState.active_view || 'n/a'}`,
    `Charts: ${(visual.charts || []).length}`,
  ], visual);

  renderCard('strategy-card', 'Strategy Intelligence', [
    `Setups: ${(strategy.setup_archetypes || []).length}`,
    `Regime rows: ${(strategy.regime_performance || []).length}`,
    `Symbol rows: ${(strategy.symbol_performance || []).length}`,
  ], strategy);

  renderCard('execution-card', 'Execution Monitor', [
    `Lifecycle events: ${(oc.execution?.latest_lifecycle || []).length}`,
    `Trades today: ${oc.session?.trades_today ?? 0}`,
  ], oc.execution || {});

  renderCard('review-card', 'Trade Review', [
    `Latest review present: ${oc.trade_review?.latest_review ? 'yes' : 'no'}`,
    `Review history: ${(oc.trade_review?.history || []).length}`,
  ], oc.trade_review || {});

  renderCard('timeline-card', 'Timeline', [
    `Events: ${(oc.timeline?.events || []).length}`,
    `Retention: ${oc.timeline?.retention ?? 'n/a'}`,
  ], oc.timeline || {});

  renderCard('diagnostics-card', 'Provider Diagnostics', [
    `Providers: ${Object.keys(oc.providers || {}).length}`,
    `LLM summaries enabled: ${oc.llm?.narrative_summaries_enabled ? 'yes' : 'no'}`,
  ], { providers: oc.providers, llm: oc.llm });

  document.getElementById('secondary-debug').textContent = JSON.stringify({
    execution: oc.execution,
    timeline: oc.timeline,
    providers: oc.providers,
    llm: oc.llm,
    ui_state: layoutState,
  }, null, 2);

  applyLayoutState(layoutState);
}

function applyLayoutState(layoutState) {
  const priorityMap = layoutState.panel_priority_map || {};
  const collapsed = new Set(layoutState.collapsed_panels || []);
  const highlighted = new Set(layoutState.highlighted_panels || []);

  document.querySelectorAll('.panel').forEach((el) => {
    const key = el.dataset.panel;
    const order = priorityMap[key] ?? 999;
    el.style.order = String(order);
    el.classList.toggle('collapsed', collapsed.has(key));
    el.classList.toggle('highlight', highlighted.has(key));
    const deEmphasized = !highlighted.has(key) && order > 50;
    el.classList.toggle('deemphasized', deEmphasized);

    if (el.tagName.toLowerCase() === 'details') {
      el.open = !collapsed.has(key);
    }
  });
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
