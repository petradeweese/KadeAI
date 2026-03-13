const transcriptEl = document.getElementById('transcript');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const interpretedEl = document.getElementById('interpreted');
const chatMetaEl = document.getElementById('chat-meta');
const chartState = { symbol: null, timeframe: '5m' };

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
  const list = rows.map((r) => `<div class="metric">${r}</div>`).join('');
  el.innerHTML = `<h3>${title}</h3>${list}<details><summary>Show raw</summary><pre>${escapeHtml(JSON.stringify(raw || {}, null, 2))}</pre></details>`;
}

function renderVisualCard(id, visual, layoutState) {
  const el = document.getElementById(id);
  const firstChart = (visual.charts || [])[0] || {};
  const chartSummary = firstChart.summary || visual.summary || {};
  const overlays = firstChart.overlays || [];
  const symbol = visual.active_symbol || layoutState.active_symbol || firstChart.symbol || 'SPY';
  const timeframe = chartState.timeframe || layoutState.active_timeframe || firstChart.timeframe || '5m';
  const fallback = visual.fallback || { available: true };
  const disconnected = !fallback.available && ['provider_unavailable', 'mock_provider'].includes(fallback.reason);
  const entry = overlayValue(overlays, 'entry');
  const invalidation = overlayValue(overlays, 'invalidation');
  const target = overlayValue(overlays, 'target');
  const vwap = overlayValue(overlays, 'vwap');

  el.innerHTML = `
    <h3>Visual Explainability</h3>
    <div class="visual-head">
      <div><strong>${symbol}</strong></div>
      <div>${timeframe} • ${(visual.active_view || layoutState.active_workspace_mode || 'trade')}</div>
    </div>
    <div class="tf-controls">
      ${['1m', '5m', '15m'].map((tf) => `<button class="tf-btn ${tf === timeframe ? 'active' : ''}" data-timeframe="${tf}">${tf}</button>`).join('')}
    </div>
    <div class="chart-status ${fallback.available ? 'ready' : 'warn'}">${fallback.available ? 'Live chart feed connected' : (disconnected ? 'Chart feed disconnected — real candlesticks unavailable' : 'Waiting for bars from data feed')}</div>
    <div id="chart-surface" class="chart-surface"></div>
    <div class="levels-grid">
      <div class="level-chip">Entry <span>${entry}</span></div>
      <div class="level-chip">Invalidation <span>${invalidation}</span></div>
      <div class="level-chip">Target <span>${target}</span></div>
      <div class="level-chip">VWAP <span>${vwap}</span></div>
    </div>
    <div class="chart-summary">
      <div class="metric"><strong>Thesis:</strong> ${escapeHtml(chartSummary.thesis || 'Context aligned for deterministic setup review.')}</div>
      <div class="metric"><strong>Path:</strong> ${escapeHtml(chartSummary.reasoning || '')}</div>
    </div>
    <div class="visual-empty ${fallback.available ? 'hidden' : ''}">
      <strong>${symbol}</strong>
      <p>${fallback.message || `Chart data unavailable for ${symbol} right now.`}</p>
      <p>Kade is ready to map entry, invalidation, target, and VWAP once real market data is available.</p>
    </div>
    <details><summary>Show raw</summary><pre>${escapeHtml(JSON.stringify(visual || {}, null, 2))}</pre></details>
  `;

  chartState.symbol = symbol;
  chartState.timeframe = timeframe;
  bindTimeframeControls();
  renderCandles({ bars: firstChart.bars || [], overlays, timeframe, fallback });
}

async function fetchChart(symbol, timeframe) {
  const params = new URLSearchParams({ symbol, timeframe });
  const res = await fetch(`/api/chart?${params.toString()}`);
  return res.json();
}

function bindTimeframeControls() {
  document.querySelectorAll('.tf-btn').forEach((btn) => {
    btn.onclick = async () => {
      const timeframe = btn.dataset.timeframe;
      const symbol = chartState.symbol || 'SPY';
      const surface = document.getElementById('chart-surface');
      if (surface) surface.classList.add('loading');
      const payload = await fetchChart(symbol, timeframe);
      const syntheticVisual = {
        active_symbol: payload.symbol,
        active_view: payload.active_view?.mode,
        charts: [{ symbol: payload.symbol, timeframe: payload.timeframe, bars: payload.bars, overlays: payload.overlays, summary: payload.summary }],
        fallback: payload.fallback,
        summary: payload.summary,
      };
      renderVisualCard('visual-card', syntheticVisual, { active_workspace_mode: payload.active_view?.mode || 'trade', active_symbol: payload.symbol, active_timeframe: payload.timeframe });
    };
  });
}

function renderCandles(chartData) {
  const container = document.getElementById('chart-surface');
  if (!container) return;
  const bars = chartData.bars || [];
  const overlays = chartData.overlays || [];

  if (!window.LightweightCharts) {
    container.innerHTML = '<div class="chart-stage">Chart library unavailable.</div>';
    return;
  }

  if (!bars.length) {
    container.innerHTML = `<div class="chart-stage chart-empty"><strong>No bars yet</strong><span>${escapeHtml(chartData.fallback?.message || 'Waiting for market data...')}</span></div>`;
    return;
  }

  container.innerHTML = '';
  const toEpoch = (timestamp) => Math.floor(new Date(timestamp).getTime() / 1000);
  const candleData = bars.map((b) => ({
    time: toEpoch(b.timestamp),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));

  const chart = window.LightweightCharts.createChart(container, {
    autoSize: true,
    layout: { background: { color: '#ffffff' }, textColor: '#334155' },
    grid: { vertLines: { color: '#e2e8f0' }, horzLines: { color: '#e2e8f0' } },
    rightPriceScale: { borderColor: '#cbd5e1', scaleMargins: { top: 0.1, bottom: 0.12 } },
    timeScale: { borderColor: '#cbd5e1', timeVisible: true, secondsVisible: false, rightOffset: 6, barSpacing: 9 },
    crosshair: { mode: 0 },
  });

  const series = addSeriesCompat(chart, 'candlestick', {
    upColor: '#16a34a',
    downColor: '#dc2626',
    borderUpColor: '#16a34a',
    borderDownColor: '#dc2626',
    borderVisible: true,
    wickUpColor: '#16a34a',
    wickDownColor: '#dc2626',
    wickVisible: true,
    priceLineVisible: false,
  });
  if (!series) {
    container.innerHTML = '<div class="chart-stage">Chart series API unavailable.</div>';
    return;
  }
  series.setData(candleData);

  overlays.forEach((overlay) => {
    if (typeof overlay.price !== 'number') return;
    const line = addSeriesCompat(chart, 'line', {
      color: overlay.color || '#2563eb',
      lineWidth: overlay.type === 'vwap' ? 1 : 2,
      lineStyle: overlay.type === 'vwap' ? 2 : 0,
      lastValueVisible: true,
      priceLineVisible: true,
      title: overlay.label || overlay.type,
    });
    if (!line) return;
    line.setData(candleData.map((bar) => ({ time: bar.time, value: overlay.price })));
  });

  chart.timeScale().fitContent();
  series.priceScale().applyOptions({ autoScale: true });
}

function addSeriesCompat(chart, type, options) {
  const lwc = window.LightweightCharts || {};
  const legacyMethod = type === 'candlestick' ? 'addCandlestickSeries' : 'addLineSeries';
  if (typeof chart[legacyMethod] === 'function') {
    return chart[legacyMethod](options);
  }

  if (typeof chart.addSeries !== 'function') {
    return null;
  }

  const ctorByType = {
    candlestick: lwc.CandlestickSeries || lwc.SeriesType?.Candlestick,
    line: lwc.LineSeries || lwc.SeriesType?.Line,
  };
  const seriesType = ctorByType[type];
  if (!seriesType) {
    return null;
  }
  return chart.addSeries(seriesType, options);
}

function overlayValue(overlays, type) {
  const item = overlays.find((o) => o.type === type || o.overlay_type === type);
  if (!item) return 'n/a';
  const value = item.price ?? item.value;
  if (typeof value === 'number') return value.toFixed(2);
  return value ?? 'n/a';
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

  const runtimeMode = oc.runtime?.runtime_mode || 'text_first';
  const llmProvider = oc.providers?.llm_provider || {};
  const marketProvider = oc.providers?.market_data_provider || {};
  const llmName = llmProvider.provider_name || oc.llm?.provider || 'mock';
  const llmState = llmProvider.state || 'unknown';

  document.getElementById('runtime-pill').textContent = `Runtime: ${runtimeMode}`;
  document.getElementById('provider-pill').textContent = `LLM: ${llmName} (${llmState})`;
  const marketPill = document.getElementById('market-pill');
  if (marketPill) {
    const marketName = marketProvider.provider || 'unconfigured';
    const marketMode = marketProvider.mode || 'unknown';
    marketPill.textContent = `Market: ${marketName} (${marketMode})`;
  }

  document.getElementById('workspace-mode').textContent = layoutState.active_workspace_mode || 'overview';
  document.getElementById('active-symbol').textContent = layoutState.active_symbol || '-';
  document.getElementById('active-direction').textContent = layoutState.active_direction || '-';
  document.getElementById('active-horizon').textContent = String(layoutState.active_horizon || '-');
  document.getElementById('last-intent').textContent = layoutState.last_interpreted_intent || '-';
  document.getElementById('workspace-title').textContent = MODE_TITLES[layoutState.active_workspace_mode] || MODE_TITLES.overview;

  renderCard('market-context-card', 'Market Context Strip', [
    `Symbol: ${layoutState.active_symbol || trade.symbol || 'n/a'}`,
    `Direction: ${layoutState.active_direction || trade.direction || 'n/a'}`,
    `Regime: ${market.regime?.label || 'unknown'}`,
    `Breadth/Posture: ${premarket.market_posture?.posture_label || 'mixed'}`,
  ], { layoutState, market: market.regime, posture: premarket.market_posture });

  renderCard('trade-idea-card', 'Trade Idea', [
    `Symbol: ${trade.symbol || layoutState.active_symbol || 'n/a'}`,
    `Stance: ${trade.stance || trade.direction || layoutState.active_direction || 'n/a'}`,
    `Trigger: ${trade.entry || 'n/a'}`,
    `Invalidation: ${trade.invalidation || 'n/a'}`,
    `Target: ${trade.target || 'n/a'}`,
  ], trade);

  renderCard('target-move-card', 'Target Move Board', [
    `Candidates: ${(target.candidates || []).length}`,
    `Best candidate: ${target.candidates?.[0]?.symbol || 'n/a'}`,
    `Symbol: ${(target.request || {}).symbol || layoutState.active_symbol || 'n/a'}`,
  ], target);

  renderCard('trade-plan-card', 'Trade Plan', [
    `Symbol: ${plan.symbol || layoutState.active_symbol || 'n/a'}`,
    `Entry/Trigger: ${plan.trigger || 'n/a'}`,
    `Stop/Invalidation: ${plan.invalidation || 'n/a'}`,
    `Target: ${plan.target || 'n/a'}`,
    `Checklist: ${(plan.checklist || []).slice(0, 2).join(', ') || 'n/a'}`,
  ], plan);

  renderVisualCard('visual-card', visual, layoutState);

  renderCard('market-card', 'Market Intelligence', [
    `Regime: ${market.regime?.label || 'unknown'}`,
    `News: ${(market.key_news || []).length}`,
    `Movers: ${(market.top_movers || []).length}`,
  ], market);

  renderCard('premarket-card', 'Premarket Gameplan', [
    `Posture: ${premarket.market_posture?.posture_label || 'mixed'}`,
    `Catalysts: ${(premarket.key_catalysts || []).slice(0, 2).join(', ') || 'n/a'}`,
    `Risks: ${(premarket.risks || []).slice(0, 2).join(', ') || 'n/a'}`,
  ], premarket);

  renderCard('radar-card', 'Radar Watchlist', [
    `Top signals: ${(oc.radar?.top_signals || []).length}`,
    `High-quality: ${(oc.radar?.quality_buckets?.top_quality || []).length}`,
  ], oc.radar || {});

  renderCard('movers-card', 'Movers & Watchlist', [
    `Top movers: ${(market.top_movers || []).length}`,
    `Most active: ${(market.most_active || []).length}`,
    `Watchlist: ${(premarket.watchlist_priorities || []).slice(0, 3).join(', ') || 'n/a'}`,
  ], { movers: market.top_movers, active: market.most_active, watchlist: premarket.watchlist_priorities });

  renderCard('tracking-card', 'Trade Plan Tracking', [
    `Tracking status: ${tracking.status_after || 'n/a'}`,
    `Plan: ${tracking.plan_id || plan.plan_id || 'n/a'}`,
  ], tracking);

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
    `Latest summary type: ${oc.llm?.latest_summary?.summary_type || 'none'}`,
    `Latest summary provider: ${oc.llm?.latest_summary?.provider_name || llmName}` ,
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
    el.classList.toggle('deemphasized', !highlighted.has(key) && order > 50);

    if (el.tagName.toLowerCase() === 'details') {
      el.open = !collapsed.has(key);
    }
  });
}

async function postJson(path, payload) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  return res.json();
}

function addMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.innerHTML = `<span class="speaker">${role === 'user' ? 'You' : 'Kade'}</span><span class="message-text">${escapeHtml(text)}</span>`;
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
  const data = await postJson(path, { [key]: text });

  if (path === '/api/chat') {
    interpretedEl.textContent = `${data.interpreted_action?.intent || 'n/a'}`;
    if (chatMetaEl) {
      chatMetaEl.textContent = `${data.interpreted_action?.source || 'heuristic'} · confidence ${data.interpreted_action?.confidence ?? 'n/a'}`;
    }
    addMessage('kade', data.reply || 'Done');
    renderDashboard(data.dashboard);
  } else {
    interpretedEl.textContent = `command:${data.result?.intent || 'n/a'}`;
    if (chatMetaEl) {
      chatMetaEl.textContent = 'Explicit deterministic command';
    }
    addMessage('kade', data.result?.formatted_response || 'Done');
    renderDashboard(data.dashboard);
  }
});

document.getElementById('refresh-btn').addEventListener('click', loadDashboard);

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

loadDashboard();
