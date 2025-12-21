/**
 * Shared JavaScript helpers for Trading Bot Dashboard
 */

// Show spinner on button
function showSpinner(btn, text) {
    btn.disabled = true;
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span>' + (text || 'Loading...');
}

// Reset button to original state
function resetButton(btn) {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.originalText || 'Button';
}

// Show success state on button
function showSuccess(btn, text) {
    btn.disabled = false;
    btn.classList.add('btn-secondary');
    btn.innerHTML = text || 'Success';
    setTimeout(() => {
        resetButton(btn);
        btn.classList.remove('btn-secondary');
    }, 2000);
}

// Show error state on button
function showError(btn, text) {
    btn.disabled = false;
    btn.classList.add('btn-danger');
    btn.innerHTML = text || 'Error';
    setTimeout(() => {
        resetButton(btn);
        btn.classList.remove('btn-danger');
    }, 2000);
}

// Generic fetch wrapper with error handling
async function fetchJSON(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options
        });
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

// POST JSON data
async function postJSON(url, data) {
    return fetchJSON(url, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

// Format timestamp for display
function formatTimestamp(ts) {
    if (!ts) return '-';
    const date = new Date(ts);
    return date.toLocaleString();
}

// Create status badge HTML
function statusBadge(status, text) {
    const classes = {
        'success': 'status-success',
        'warning': 'status-warning',
        'danger': 'status-danger',
        'info': 'status-info'
    };
    return `<span class="status-badge ${classes[status] || ''}">${text}</span>`;
}

// Build results table HTML
function buildResultsTable(steps) {
    if (!steps || steps.length === 0) {
        return '<p class="text-muted">No results</p>';
    }
    
    let html = '<table class="table"><thead><tr><th>Step</th><th>Status</th><th>Details</th></tr></thead><tbody>';
    
    for (const step of steps) {
        const statusClass = step.status === 'OK' ? 'result-ok' : 
                           step.status === 'FAIL' ? 'result-fail' : 'result-warn';
        html += `<tr>
            <td>${step.step || step.name || '-'}</td>
            <td class="${statusClass}">${step.status}</td>
            <td>${step.message || step.details || '-'}</td>
        </tr>`;
    }
    
    html += '</tbody></table>';
    return html;
}

// Truncate text with ellipsis
function truncate(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Show/hide element
function show(el) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (el) el.classList.remove('hidden');
}

function hide(el) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (el) el.classList.add('hidden');
}

// Toggle element visibility
function toggle(el) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (el) el.classList.toggle('hidden');
}

// Status Row functionality
async function refreshStatusRow() {
    try {
        const resp = await fetch('/status');
        if (!resp.ok) return;
        const data = await resp.json();
        
        updateServiceStatus('whop', data.whop);
        updateServiceStatus('alpaca', data.alpaca);
        updateServiceStatus('tradier', data.tradier);
        updateModeStatus(data.mode);
        updateRiskStatus(data.risk_mode);
    } catch (e) {
        console.error('Failed to refresh status:', e);
    }
}

function updateServiceStatus(service, info) {
    const el = document.getElementById('status-' + service);
    if (!el || !info) return;
    
    const dot = el.querySelector('.status-dot');
    if (dot) {
        dot.className = 'status-dot';
        const statusMap = {
            'ok': 'status-ok',
            'fail': 'status-fail',
            'warn': 'status-warn',
            'unknown': 'status-unknown'
        };
        dot.classList.add(statusMap[info.status] || 'status-unknown');
    }
    
    let tooltip = service.toUpperCase() + ': ';
    tooltip += info.summary || 'Unknown';
    if (info.last_checked) {
        tooltip += ' (checked: ' + formatTimestamp(info.last_checked) + ')';
    }
    el.title = tooltip;
}

function updateModeStatus(mode) {
    const badge = document.getElementById('modeBadge');
    if (!badge || !mode) return;
    
    const effective = mode.effective || 'paper';
    badge.textContent = effective.toUpperCase();
    badge.className = 'mode-badge';
    
    if (effective === 'live') {
        badge.classList.add('mode-live');
    } else if (effective === 'dual') {
        badge.classList.add('mode-dual');
    } else {
        badge.classList.add('mode-paper');
    }
    
    const statusEl = document.getElementById('status-mode');
    if (statusEl) {
        const tooltips = {
            'paper': 'Paper trading only - no real money at risk',
            'live': 'LIVE TRADING - Real money at risk!',
            'dual': 'DUAL MODE - Live trading + paper mirror'
        };
        statusEl.title = tooltips[effective] || 'Execution Mode';
    }
}

async function setExecutionMode(mode) {
    try {
        const resp = await fetch('/mode/set', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await resp.json();
        if (data.mode) {
            updateModeStatus(data.mode);
        }
        return data;
    } catch (e) {
        console.error('Failed to set mode:', e);
        throw e;
    }
}

async function getExecutionMode() {
    try {
        const resp = await fetch('/mode');
        return await resp.json();
    } catch (e) {
        console.error('Failed to get mode:', e);
        return null;
    }
}

function updateRiskStatus(riskMode) {
    const badge = document.getElementById('riskBadge');
    if (!badge) return;
    
    const mode = riskMode || 'balanced';
    badge.textContent = mode.toUpperCase();
    badge.className = 'risk-badge';
    badge.classList.add('risk-' + mode);
    
    const el = document.getElementById('status-risk');
    if (el) {
        const descriptions = {
            'conservative': 'Conservative: Spreads only, 1% max risk',
            'balanced': 'Balanced: Stocks + options, 2% max risk',
            'aggressive': 'Aggressive: All trades, 5% max risk'
        };
        el.title = descriptions[mode] || 'Risk Mode';
    }
}
