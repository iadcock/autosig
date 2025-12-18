"""
Flask dashboard for trading bot reporting and broker smoke tests.
Provides a simple UI to generate reports and test broker connections.
"""

import os
from flask import Flask, send_file, render_template_string, request, jsonify

from report_docx import generate_report
from broker_smoke_tests import alpaca_smoke_test, tradier_smoke_test
from env_loader import diagnose_env
from signal_to_intent import build_trade_intent, classify_signal_type, resolve_exit_to_trade_intent, has_complete_leg_details
from execution_plan import build_execution_plan, log_execution_plan, get_latest_signal_entry, get_executable_signal
from execution.router import execute_trade

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Dashboard</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 20px;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 40px;
            max-width: 800px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            margin-top: 20px;
        }
        h1 {
            color: #1a1a2e;
            font-size: 28px;
            margin-bottom: 10px;
            text-align: center;
        }
        h2 {
            color: #1a1a2e;
            font-size: 20px;
            margin: 30px 0 15px 0;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .btn {
            display: inline-block;
            padding: 16px 24px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s, background 0.3s;
            margin-bottom: 15px;
            margin-right: 10px;
            min-width: 200px;
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            cursor: not-allowed;
            opacity: 0.7;
        }
        .btn-secondary {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        .btn-secondary:hover:not(:disabled) {
            box-shadow: 0 10px 30px rgba(17, 153, 142, 0.4);
        }
        .btn-block {
            display: block;
            width: 100%;
            margin-right: 0;
        }
        
        /* Smoke test button states */
        .btn-test {
            background: linear-gradient(135deg, #4a4a4a 0%, #6a6a6a 100%);
            position: relative;
        }
        .btn-test.running {
            background: linear-gradient(135deg, #888 0%, #999 100%);
            cursor: wait;
        }
        .btn-test.success {
            background: linear-gradient(135deg, #28a745 0%, #34ce57 100%);
        }
        .btn-test.failure {
            background: linear-gradient(135deg, #dc3545 0%, #e85464 100%);
        }
        
        /* Spinner */
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
            margin-right: 8px;
            vertical-align: middle;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .info {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }
        .info h3 {
            color: #1a1a2e;
            font-size: 16px;
            margin-bottom: 10px;
        }
        .info ul {
            list-style: none;
            padding: 0;
        }
        .info li {
            color: #666;
            font-size: 14px;
            padding: 5px 0;
            border-bottom: 1px solid #eee;
        }
        .info li:last-child {
            border-bottom: none;
        }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-active {
            background: #d4edda;
            color: #155724;
        }
        
        /* Results table */
        .results-container {
            margin-top: 20px;
        }
        .results-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            margin-top: 10px;
        }
        .results-table th, .results-table td {
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }
        .results-table th {
            background: #f8f9fa;
            font-weight: 600;
            color: #1a1a2e;
        }
        .results-table tr:nth-child(even) {
            background: #fafafa;
        }
        .step-ok {
            color: #28a745;
            font-weight: 600;
        }
        .step-fail {
            color: #dc3545;
            font-weight: 600;
        }
        .step-warn {
            color: #ffc107;
            font-weight: 600;
        }
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .results-header h4 {
            margin: 0;
            color: #1a1a2e;
        }
        .results-timestamp {
            font-size: 12px;
            color: #666;
        }
        .button-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        /* Review Queue Styles */
        .review-queue {
            margin-top: 20px;
        }
        .review-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 15px;
        }
        .review-table th, .review-table td {
            padding: 8px 6px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .review-table th {
            background: #f5f5f5;
            font-weight: 600;
            color: #333;
        }
        .review-table tr:hover {
            background: #f9f9f9;
        }
        .review-table .ticker {
            font-weight: 600;
            color: #1a1a2e;
        }
        .badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
        }
        .badge-entry { background: #d4edda; color: #155724; }
        .badge-exit { background: #fff3cd; color: #856404; }
        .badge-unknown { background: #e2e3e5; color: #383d41; }
        .badge-executed { background: #cce5ff; color: #004085; }
        .badge-pass { background: #d4edda; color: #155724; }
        .badge-block { background: #f8d7da; color: #721c24; }
        .badge-pending { background: #e2e3e5; color: #383d41; }
        
        .btn-sm {
            padding: 4px 8px;
            font-size: 11px;
            min-width: auto;
            margin: 2px;
        }
        .btn-paper { background: linear-gradient(135deg, #17a2b8 0%, #20c997 100%); }
        .btn-live { background: linear-gradient(135deg, #dc3545 0%, #e85464 100%); }
        .btn-reject { background: linear-gradient(135deg, #6c757d 0%, #868e96 100%); }
        .btn-sm:hover:not(:disabled) {
            transform: translateY(-1px);
        }
        
        .detail-panel {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
            display: none;
        }
        .detail-panel.visible {
            display: block;
        }
        .detail-section {
            margin-bottom: 15px;
        }
        .detail-section h4 {
            margin: 0 0 8px 0;
            color: #495057;
            font-size: 13px;
        }
        .detail-section pre {
            background: #fff;
            border: 1px solid #dee2e6;
            padding: 10px;
            border-radius: 4px;
            font-size: 11px;
            overflow-x: auto;
            margin: 0;
        }
        .checks-table {
            width: 100%;
            font-size: 11px;
        }
        .checks-table td {
            padding: 4px 8px;
        }
        .check-pass { color: #28a745; }
        .check-fail { color: #dc3545; }
        
        .refresh-btn {
            background: #6c757d;
            padding: 8px 16px;
            font-size: 12px;
            min-width: auto;
        }
        .empty-state {
            text-align: center;
            padding: 30px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Bot Dashboard</h1>
        <p class="subtitle">Victory Trades Alert Processing</p>
        
        <a href="/report" class="btn btn-block">
            Generate Last 24 Hours Report
        </a>
        
        <a href="/report?hours=48" class="btn btn-secondary btn-block">
            Generate Last 48 Hours Report
        </a>
        
        <h2>Broker Smoke Tests</h2>
        <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
            Test connectivity and API access for each broker.
        </p>
        
        <div class="button-row">
            <button id="btn-alpaca" class="btn btn-test" onclick="runTest('alpaca')">
                Run Alpaca Test
            </button>
            <button id="btn-tradier" class="btn btn-test" onclick="runTest('tradier')">
                Run Tradier Test
            </button>
        </div>
        
        <div id="results-alpaca" class="results-container" style="display: none;"></div>
        <div id="results-tradier" class="results-container" style="display: none;"></div>
        
        <h2>Paper Trading</h2>
        <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
            Execute the last parsed signal in paper (simulated) mode.
        </p>
        
        <button id="btn-paper-execute" class="btn btn-test" onclick="executePaperSignal()">
            Execute Last Executable Signal (Paper)
        </button>
        
        <div id="results-paper" class="results-container" style="display: none;"></div>
        
        <h2>Review Queue</h2>
        <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
            Review recent signals and approve for paper or live execution, or reject.
        </p>
        
        <button class="btn refresh-btn" onclick="loadReviewQueue()">
            Refresh Queue
        </button>
        
        <div id="review-queue-container">
            <div class="empty-state">Loading signals...</div>
        </div>
        
        <div id="review-detail-panel" class="detail-panel"></div>
        
        <div class="info">
            <h3>Report Contents</h3>
            <ul>
                <li>Summary metrics (alerts, signals, executions)</li>
                <li>Table of all trading signals parsed</li>
                <li>Execution plans with contract details</li>
                <li>Non-signal alerts with reasons</li>
            </ul>
        </div>
        
        <div class="info" style="margin-top: 15px;">
            <h3>Status</h3>
            <ul>
                <li>Bot Status: <span class="status status-active">Running</span></li>
                <li>Report Format: Microsoft Word (.docx)</li>
                <li>Default Range: Last 24 hours</li>
            </ul>
        </div>
    </div>
    
    <script>
        function runTest(broker) {
            const btn = document.getElementById('btn-' + broker);
            const resultsDiv = document.getElementById('results-' + broker);
            
            // Set running state
            btn.disabled = true;
            btn.className = 'btn btn-test running';
            btn.innerHTML = '<span class="spinner"></span>Testing...';
            resultsDiv.style.display = 'none';
            
            fetch('/test/' + broker, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                // Set success/failure state
                if (data.success) {
                    btn.className = 'btn btn-test success';
                    btn.innerHTML = '✓ Success';
                } else {
                    btn.className = 'btn btn-test failure';
                    btn.innerHTML = '✗ Failed';
                }
                
                // Render results table
                renderResults(broker, data);
                
                // Re-enable button after 2 seconds
                setTimeout(() => {
                    btn.disabled = false;
                    btn.className = 'btn btn-test';
                    btn.innerHTML = 'Run ' + broker.charAt(0).toUpperCase() + broker.slice(1) + ' Test';
                }, 2000);
            })
            .catch(error => {
                btn.className = 'btn btn-test failure';
                btn.innerHTML = '✗ Error';
                
                resultsDiv.innerHTML = `
                    <div class="info" style="background: #f8d7da; border: 1px solid #f5c6cb;">
                        <h3 style="color: #721c24;">Network Error</h3>
                        <p style="color: #721c24;">${error.message}</p>
                    </div>
                `;
                resultsDiv.style.display = 'block';
                
                setTimeout(() => {
                    btn.disabled = false;
                    btn.className = 'btn btn-test';
                    btn.innerHTML = 'Run ' + broker.charAt(0).toUpperCase() + broker.slice(1) + ' Test';
                }, 2000);
            });
        }
        
        function renderResults(broker, data) {
            const resultsDiv = document.getElementById('results-' + broker);
            
            let tableRows = '';
            for (const step of data.steps) {
                let okClass, okText;
                if (step.status === 'SKIPPED_SANDBOX') {
                    okClass = 'step-warn';
                    okText = '⚠️';
                } else if (step.ok) {
                    okClass = 'step-ok';
                    okText = '✓';
                } else {
                    okClass = 'step-fail';
                    okText = '✗';
                }
                tableRows += `
                    <tr>
                        <td>${step.name}</td>
                        <td class="${okClass}">${okText}</td>
                        <td>${step.status || '-'}</td>
                        <td>${step.summary}</td>
                        <td>${step.details || '-'}</td>
                    </tr>
                `;
            }
            
            const brokerName = broker.charAt(0).toUpperCase() + broker.slice(1);
            const isSandbox = data.is_sandbox ? ' (Sandbox)' : '';
            const statusClass = data.success ? 'step-ok' : 'step-fail';
            const statusText = data.success ? 'PASSED' : 'FAILED';
            
            resultsDiv.innerHTML = `
                <div class="results-header">
                    <h4>${brokerName}${isSandbox} Test Results: <span class="${statusClass}">${statusText}</span></h4>
                    <span class="results-timestamp">${data.timestamp}</span>
                </div>
                <table class="results-table">
                    <thead>
                        <tr>
                            <th>Step</th>
                            <th>OK</th>
                            <th>Status</th>
                            <th>Summary</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
            `;
            resultsDiv.style.display = 'block';
        }
        
        function executePaperSignal() {
            const btn = document.getElementById('btn-paper-execute');
            const resultsDiv = document.getElementById('results-paper');
            
            btn.disabled = true;
            btn.className = 'btn btn-test running';
            btn.innerHTML = '<span class="spinner"></span>Executing...';
            resultsDiv.style.display = 'none';
            
            fetch('/execute/paper/last_signal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    btn.className = 'btn btn-test success';
                    btn.innerHTML = '✓ Executed';
                } else {
                    btn.className = 'btn btn-test failure';
                    btn.innerHTML = '✗ Failed';
                }
                
                renderPaperResults(data);
                
                setTimeout(() => {
                    btn.disabled = false;
                    btn.className = 'btn btn-test';
                    btn.innerHTML = 'Execute Last Executable Signal (Paper)';
                }, 3000);
            })
            .catch(error => {
                btn.className = 'btn btn-test failure';
                btn.innerHTML = '✗ Error';
                
                resultsDiv.innerHTML = `
                    <div class="info" style="background: #f8d7da; border: 1px solid #f5c6cb;">
                        <h3 style="color: #721c24;">Network Error</h3>
                        <p style="color: #721c24;">${error.message}</p>
                    </div>
                `;
                resultsDiv.style.display = 'block';
                
                setTimeout(() => {
                    btn.disabled = false;
                    btn.className = 'btn btn-test';
                    btn.innerHTML = 'Execute Last Executable Signal (Paper)';
                }, 2000);
            });
        }
        
        function renderPaperResults(data) {
            const resultsDiv = document.getElementById('results-paper');
            
            if (!data.success) {
                resultsDiv.innerHTML = `
                    <div class="info" style="background: #f8d7da; border: 1px solid #f5c6cb;">
                        <h3 style="color: #721c24;">Execution Failed</h3>
                        <p style="color: #721c24;">${data.message}</p>
                    </div>
                `;
                resultsDiv.style.display = 'block';
                return;
            }
            
            const statusClass = data.execution_result?.status === 'SIMULATED' ? 'step-ok' : 'step-fail';
            const statusText = data.execution_result?.status || 'UNKNOWN';
            const signalType = data.signal_type || 'UNKNOWN';
            const signalTypeClass = signalType === 'ENTRY' ? 'step-ok' : (signalType === 'EXIT' ? 'step-warn' : '');
            const matchedPositionId = data.matched_position_id || null;
            
            let positionInfo = '';
            if (matchedPositionId) {
                positionInfo = `<div class="info" style="margin-top: 10px; background: #fff3cd; border: 1px solid #ffc107;">
                    <h3 style="color: #856404;">Matched Open Position</h3>
                    <p style="font-family: monospace; font-size: 12px;">${matchedPositionId}</p>
                </div>`;
            }
            
            resultsDiv.innerHTML = `
                <div class="results-header">
                    <h4>Paper Execution: <span class="${statusClass}">${statusText}</span></h4>
                    <span class="results-timestamp">${data.timestamp || ''}</span>
                </div>
                
                <div class="info" style="margin-top: 10px;">
                    <h3>Signal Type: <span class="${signalTypeClass}" style="font-weight: bold;">${signalType}</span></h3>
                </div>
                
                <div class="info" style="margin-top: 10px;">
                    <h3>Signal Excerpt</h3>
                    <p style="font-family: monospace; white-space: pre-wrap; font-size: 12px; background: #f0f0f0; padding: 10px; border-radius: 4px; max-height: 100px; overflow-y: auto;">${escapeHtml(data.raw_excerpt || '')}</p>
                </div>
                
                ${positionInfo}
                
                <div class="info" style="margin-top: 10px;">
                    <h3>Parsed Signal</h3>
                    <pre style="font-size: 11px; background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto;">${JSON.stringify(data.parsed_signal || {}, null, 2)}</pre>
                </div>
                
                <div class="info" style="margin-top: 10px;">
                    <h3>Trade Intent</h3>
                    <pre style="font-size: 11px; background: #e8f4e8; padding: 10px; border-radius: 4px; overflow-x: auto;">${JSON.stringify(data.trade_intent || {}, null, 2)}</pre>
                </div>
                
                <div class="info" style="margin-top: 10px;">
                    <h3>Execution Result</h3>
                    <pre style="font-size: 11px; background: #e8e8f4; padding: 10px; border-radius: 4px; overflow-x: auto;">${JSON.stringify(data.execution_result || {}, null, 2)}</pre>
                </div>
            `;
            resultsDiv.style.display = 'block';
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Review Queue Functions
        let reviewSignals = [];
        
        function loadReviewQueue() {
            const container = document.getElementById('review-queue-container');
            container.innerHTML = '<div class="empty-state">Loading signals...</div>';
            
            fetch('/review')
                .then(response => response.json())
                .then(data => {
                    if (!data.success || !data.signals || data.signals.length === 0) {
                        container.innerHTML = '<div class="empty-state">No signals found</div>';
                        return;
                    }
                    
                    reviewSignals = data.signals;
                    renderReviewTable(data.signals);
                })
                .catch(error => {
                    container.innerHTML = `<div class="empty-state" style="color: #dc3545;">Error loading signals: ${error.message}</div>`;
                });
        }
        
        function renderReviewTable(signals) {
            const container = document.getElementById('review-queue-container');
            
            let html = `
                <table class="review-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Ticker</th>
                            <th>Type</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            for (const sig of signals) {
                const time = sig.ts_iso ? new Date(sig.ts_iso).toLocaleString() : '-';
                const ticker = sig.ticker || sig.parsed_signal?.ticker || '-';
                const signalType = sig.signal_type || 'UNKNOWN';
                const isSignal = sig.classification === 'SIGNAL';
                const executed = sig.already_executed;
                
                const typeBadge = signalType === 'ENTRY' ? 'badge-entry' : 
                                  signalType === 'EXIT' ? 'badge-exit' : 'badge-unknown';
                
                let statusHtml = '';
                if (executed) {
                    statusHtml = '<span class="badge badge-executed">EXECUTED</span>';
                } else if (!isSignal) {
                    statusHtml = '<span class="badge badge-unknown">NOT SIGNAL</span>';
                } else {
                    statusHtml = '<span class="badge badge-pending">PENDING</span>';
                }
                
                const postId = sig.post_id || '';
                const canApprove = isSignal && !executed;
                
                html += `
                    <tr data-post-id="${escapeHtml(postId)}">
                        <td style="font-size: 11px;">${escapeHtml(time)}</td>
                        <td class="ticker">${escapeHtml(ticker)}</td>
                        <td><span class="badge ${typeBadge}">${signalType}</span></td>
                        <td>${statusHtml}</td>
                        <td>
                            <button class="btn btn-sm btn-paper" onclick="approveSignal('${escapeHtml(postId)}', 'paper')" ${canApprove ? '' : 'disabled'}>
                                Paper
                            </button>
                            <button class="btn btn-sm btn-live" onclick="approveSignal('${escapeHtml(postId)}', 'live')" ${canApprove ? '' : 'disabled'}>
                                Live
                            </button>
                            <button class="btn btn-sm btn-reject" onclick="rejectSignal('${escapeHtml(postId)}')" ${isSignal && !executed ? '' : 'disabled'}>
                                Reject
                            </button>
                            <button class="btn btn-sm" onclick="showDetails('${escapeHtml(postId)}')" style="background: #6c757d;">
                                Details
                            </button>
                        </td>
                    </tr>
                `;
            }
            
            html += '</tbody></table>';
            container.innerHTML = html;
        }
        
        function approveSignal(postId, mode) {
            const btns = document.querySelectorAll(`tr[data-post-id="${postId}"] button`);
            btns.forEach(btn => btn.disabled = true);
            
            const detailPanel = document.getElementById('review-detail-panel');
            detailPanel.innerHTML = '<div style="padding: 20px; text-align: center;">Processing...</div>';
            detailPanel.classList.add('visible');
            
            fetch('/review/approve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ post_id: postId, mode: mode })
            })
            .then(response => response.json())
            .then(data => {
                renderApprovalResult(data, mode);
                if (data.success) {
                    loadReviewQueue();
                } else {
                    btns.forEach(btn => btn.disabled = false);
                }
            })
            .catch(error => {
                detailPanel.innerHTML = `<div style="color: #dc3545; padding: 20px;">Error: ${error.message}</div>`;
                btns.forEach(btn => btn.disabled = false);
            });
        }
        
        function renderApprovalResult(data, mode) {
            const detailPanel = document.getElementById('review-detail-panel');
            
            const statusClass = data.success ? 'check-pass' : 'check-fail';
            const statusIcon = data.success ? '✓' : '✗';
            
            let checksHtml = '';
            if (data.preflight_result && data.preflight_result.checks) {
                checksHtml = '<table class="checks-table">';
                for (const check of data.preflight_result.checks) {
                    const checkClass = check.ok ? 'check-pass' : 'check-fail';
                    const icon = check.ok ? '✓' : '✗';
                    checksHtml += `<tr><td class="${checkClass}">${icon}</td><td>${escapeHtml(check.name)}</td><td>${escapeHtml(check.summary)}</td></tr>`;
                }
                checksHtml += '</table>';
            }
            
            let warningsHtml = '';
            if (data.preflight_result && data.preflight_result.warnings && data.preflight_result.warnings.length > 0) {
                warningsHtml = '<div style="background: #fff3cd; padding: 8px; border-radius: 4px; margin-top: 10px;">';
                for (const w of data.preflight_result.warnings) {
                    warningsHtml += `<div style="color: #856404;">⚠ ${escapeHtml(w)}</div>`;
                }
                warningsHtml += '</div>';
            }
            
            detailPanel.innerHTML = `
                <div class="detail-section">
                    <h4>Approval Result: <span class="${statusClass}">${statusIcon} ${data.success ? 'SUCCESS' : 'FAILED'}</span></h4>
                    <p>${escapeHtml(data.message || '')}</p>
                    ${data.blocked_reason ? `<p style="color: #dc3545;"><strong>Blocked:</strong> ${escapeHtml(data.blocked_reason)}</p>` : ''}
                </div>
                
                ${checksHtml ? `<div class="detail-section"><h4>Preflight Checks</h4>${checksHtml}${warningsHtml}</div>` : ''}
                
                ${data.trade_intent ? `<div class="detail-section"><h4>Trade Intent</h4><pre>${JSON.stringify(data.trade_intent, null, 2)}</pre></div>` : ''}
                
                ${data.execution_result ? `<div class="detail-section"><h4>Execution Result</h4><pre>${JSON.stringify(data.execution_result, null, 2)}</pre></div>` : ''}
            `;
            detailPanel.classList.add('visible');
        }
        
        function rejectSignal(postId) {
            const notes = prompt('Enter rejection reason:');
            if (!notes || notes.trim() === '') {
                alert('Rejection reason is required');
                return;
            }
            
            fetch('/review/reject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ post_id: postId, notes: notes })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Signal rejected');
                    loadReviewQueue();
                } else {
                    alert('Error: ' + (data.message || 'Unknown error'));
                }
            })
            .catch(error => {
                alert('Error: ' + error.message);
            });
        }
        
        function showDetails(postId) {
            const signal = reviewSignals.find(s => s.post_id === postId);
            if (!signal) {
                alert('Signal not found');
                return;
            }
            
            const detailPanel = document.getElementById('review-detail-panel');
            
            let executionInfo = '';
            if (signal.already_executed && signal.execution_info) {
                executionInfo = `
                    <div class="detail-section">
                        <h4>Execution Info (Already Executed)</h4>
                        <pre>${JSON.stringify(signal.execution_info, null, 2)}</pre>
                    </div>
                `;
            }
            
            detailPanel.innerHTML = `
                <div class="detail-section">
                    <h4>Post ID</h4>
                    <p style="font-family: monospace; font-size: 11px; word-break: break-all;">${escapeHtml(signal.post_id || '')}</p>
                </div>
                
                <div class="detail-section">
                    <h4>Raw Excerpt</h4>
                    <pre style="white-space: pre-wrap;">${escapeHtml(signal.raw_excerpt || '')}</pre>
                </div>
                
                <div class="detail-section">
                    <h4>Parsed Signal</h4>
                    <pre>${JSON.stringify(signal.parsed_signal || {}, null, 2)}</pre>
                </div>
                
                <div class="detail-section">
                    <h4>Classification</h4>
                    <p><span class="badge ${signal.classification === 'SIGNAL' ? 'badge-entry' : 'badge-unknown'}">${escapeHtml(signal.classification || 'UNKNOWN')}</span>
                    &nbsp;&nbsp;Signal Type: <span class="badge ${signal.signal_type === 'ENTRY' ? 'badge-entry' : signal.signal_type === 'EXIT' ? 'badge-exit' : 'badge-unknown'}">${escapeHtml(signal.signal_type || 'UNKNOWN')}</span></p>
                </div>
                
                ${executionInfo}
            `;
            detailPanel.classList.add('visible');
        }
        
        // Load review queue on page load
        document.addEventListener('DOMContentLoaded', function() {
            loadReviewQueue();
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    """Dashboard home page."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/health")
def health():
    """Health check endpoint."""
    return "ok"


@app.route("/report")
def download_report():
    """Generate and download the trading report."""
    hours = request.args.get("hours", 24, type=int)
    
    hours = max(1, min(hours, 168))
    
    try:
        filepath = generate_report(hours)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=os.path.basename(filepath),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except Exception as e:
        return f"Error generating report: {str(e)}", 500


@app.route("/test/alpaca", methods=["POST"])
def test_alpaca():
    """Run Alpaca smoke test and return JSON results."""
    result = alpaca_smoke_test()
    return jsonify(result)


@app.route("/test/tradier", methods=["POST"])
def test_tradier():
    """Run Tradier smoke test and return JSON results."""
    result = tradier_smoke_test()
    return jsonify(result)


@app.route("/debug/env")
def debug_env():
    """
    Diagnostic endpoint to check environment variable visibility.
    Does NOT expose actual secret values.
    """
    keys_to_check = [
        "TRADIER_TOKEN",
        "TRADIER_BASE_URL",
        "TRADIER_ACCOUNT_ID",
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "ALPACA_PAPER_BASE_URL"
    ]
    result = diagnose_env(keys_to_check)
    return jsonify(result)


@app.route("/execute/paper/last_signal", methods=["POST"])
def execute_paper_last_signal():
    """
    Execute the best executable signal in paper (simulated) mode.
    
    Smart signal selection:
    1. Prefer ENTRY signals (most recent first)
    2. Consider EXIT signals with complete leg details
    3. Consider EXIT signals resolvable via open positions
    4. Skip if no executable signal found
    
    Returns JSON with results including signal_type and matched_position_id.
    """
    from datetime import datetime
    
    # Use smart signal selection
    signal_entry, signal_type, skip_reason = get_executable_signal()
    
    if not signal_entry:
        # Log the skip
        execution_plan = build_execution_plan(
            trade_intent=None,
            execution_result=None,
            source_post_id="none",
            action="SKIP",
            reason=skip_reason,
            signal_type=signal_type
        )
        log_execution_plan(execution_plan)
        
        return jsonify({
            "success": False,
            "message": skip_reason or "No executable signals found",
            "signal_type": signal_type,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    parsed_signal = signal_entry.get("parsed_signal", {})
    post_id = signal_entry.get("post_id", "unknown")
    raw_excerpt = signal_entry.get("raw_excerpt", "")
    
    try:
        trade_intent = None
        matched_position_id = None
        
        if signal_type == "EXIT":
            # Check if EXIT has complete leg details
            if has_complete_leg_details(parsed_signal):
                trade_intent = build_trade_intent(parsed_signal, execution_mode="PAPER")
            else:
                # Resolve via open positions
                trade_intent, matched_position_id, error = resolve_exit_to_trade_intent(
                    parsed_signal, execution_mode="PAPER"
                )
                if not trade_intent:
                    # Log skip
                    execution_plan = build_execution_plan(
                        trade_intent=None,
                        execution_result=None,
                        source_post_id=post_id,
                        action="SKIP",
                        reason=error or "Could not resolve EXIT to open position",
                        signal_type=signal_type
                    )
                    log_execution_plan(execution_plan)
                    
                    return jsonify({
                        "success": False,
                        "message": error or "Could not resolve EXIT signal",
                        "signal_type": signal_type,
                        "selected_post_id": post_id,
                        "raw_excerpt": raw_excerpt[:200],
                        "parsed_signal": parsed_signal,
                        "timestamp": datetime.utcnow().isoformat()
                    })
        else:
            # ENTRY or other - build normally
            trade_intent = build_trade_intent(parsed_signal, execution_mode="PAPER")
        
        # Add source_post_id to metadata for position tracking
        if trade_intent.metadata:
            trade_intent.metadata["source_post_id"] = post_id
        
        execution_result = execute_trade(trade_intent)
        
        execution_plan = build_execution_plan(
            trade_intent=trade_intent,
            execution_result=execution_result,
            source_post_id=post_id,
            action="PLACE_ORDER",
            signal_type=signal_type,
            matched_position_id=matched_position_id
        )
        log_execution_plan(execution_plan)
        
        intent_dict = {
            "id": trade_intent.id,
            "execution_mode": trade_intent.execution_mode,
            "instrument_type": trade_intent.instrument_type,
            "underlying": trade_intent.underlying,
            "action": trade_intent.action,
            "order_type": trade_intent.order_type,
            "limit_price": trade_intent.limit_price,
            "quantity": trade_intent.quantity,
            "legs": [
                {
                    "side": leg.side,
                    "quantity": leg.quantity,
                    "strike": leg.strike,
                    "option_type": leg.option_type,
                    "expiration": leg.expiration
                }
                for leg in trade_intent.legs
            ]
        }
        
        result_dict = {
            "status": execution_result.status,
            "broker": execution_result.broker,
            "order_id": execution_result.order_id,
            "message": execution_result.message,
            "fill_price": execution_result.fill_price,
            "filled_quantity": execution_result.filled_quantity
        }
        
        return jsonify({
            "success": True,
            "signal_type": signal_type,
            "matched_position_id": matched_position_id,
            "selected_post_id": post_id,
            "raw_excerpt": raw_excerpt[:500],
            "parsed_signal": parsed_signal,
            "trade_intent": intent_dict,
            "execution_result": result_dict,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Execution error: {str(e)}",
            "signal_type": signal_type,
            "selected_post_id": post_id,
            "raw_excerpt": raw_excerpt[:200],
            "parsed_signal": parsed_signal,
            "timestamp": datetime.utcnow().isoformat()
        })


@app.route("/review")
def get_review_queue():
    """
    Get list of recent parsed signals for review.
    Returns JSON with signal metadata and execution status.
    """
    from review_queue import list_recent_signals
    
    signals = list_recent_signals(limit=25)
    return jsonify({
        "success": True,
        "signals": signals,
        "count": len(signals)
    })


@app.route("/review/approve", methods=["POST"])
def approve_signal():
    """
    Approve and execute a signal in paper or live mode.
    
    Body: { "post_id": "...", "mode": "paper" | "live" }
    """
    from datetime import datetime
    from review_queue import list_recent_signals, build_intent_and_preflight, record_review_action
    from dedupe_store import is_executed, mark_executed
    from trade_intent import TradeIntent, OptionLeg
    
    data = request.get_json() or {}
    post_id = data.get("post_id", "")
    mode = data.get("mode", "paper").lower()
    
    if not post_id:
        return jsonify({
            "success": False,
            "message": "Missing post_id"
        }), 400
    
    if mode not in ("paper", "live"):
        return jsonify({
            "success": False,
            "message": "Mode must be 'paper' or 'live'"
        }), 400
    
    if is_executed(post_id):
        return jsonify({
            "success": False,
            "message": "Signal already executed (duplicate)",
            "blocked_reason": "Duplicate execution blocked"
        })
    
    signals = list_recent_signals(limit=100)
    entry = None
    for sig in signals:
        if sig.get("post_id") == post_id:
            entry = sig
            break
    
    if not entry:
        return jsonify({
            "success": False,
            "message": f"Signal not found: {post_id[:30]}..."
        }), 404
    
    result = build_intent_and_preflight(entry, mode)
    
    trade_intent_dict = result.get("trade_intent")
    intent_error = result.get("trade_intent_error")
    preflight_result = result.get("preflight_result")
    matched_position_id = result.get("matched_position_id")
    
    if not trade_intent_dict:
        action_type = "APPROVE_LIVE" if mode == "live" else "APPROVE_PAPER"
        record_review_action(
            post_id=post_id,
            action=action_type,
            mode=mode,
            notes=f"Failed to build intent: {intent_error}",
            preflight=None,
            result=None,
            ticker=entry.get("ticker", "")
        )
        return jsonify({
            "success": False,
            "message": intent_error or "Could not build TradeIntent",
            "preflight_result": None,
            "trade_intent": None
        })
    
    if preflight_result and not preflight_result.get("ok"):
        action_type = "APPROVE_LIVE" if mode == "live" else "APPROVE_PAPER"
        record_review_action(
            post_id=post_id,
            action=action_type,
            mode=mode,
            notes=f"Preflight blocked: {preflight_result.get('blocked_reason')}",
            preflight=preflight_result,
            result=None,
            ticker=entry.get("ticker", "")
        )
        return jsonify({
            "success": False,
            "message": "Preflight checks failed",
            "blocked_reason": preflight_result.get("blocked_reason"),
            "preflight_result": preflight_result,
            "trade_intent": trade_intent_dict
        })
    
    try:
        legs = [
            OptionLeg(
                side=leg["side"],
                quantity=leg["quantity"],
                strike=leg["strike"],
                option_type=leg["option_type"],
                expiration=leg["expiration"]
            )
            for leg in trade_intent_dict.get("legs", [])
        ]
        
        trade_intent = TradeIntent(
            id=trade_intent_dict.get("id"),
            execution_mode=trade_intent_dict.get("execution_mode", mode.upper()),
            instrument_type=trade_intent_dict.get("instrument_type", "option"),
            underlying=trade_intent_dict.get("underlying", ""),
            action=trade_intent_dict.get("action", "BUY_TO_OPEN"),
            order_type=trade_intent_dict.get("order_type", "MARKET"),
            limit_price=trade_intent_dict.get("limit_price"),
            quantity=trade_intent_dict.get("quantity", 1),
            legs=legs,
            raw_signal=trade_intent_dict.get("raw_signal", ""),
            metadata=trade_intent_dict.get("metadata", {})
        )
        
        execution_result = execute_trade(trade_intent)
        
        mark_executed(
            post_id=post_id,
            execution_mode=mode,
            trade_intent_id=trade_intent.id,
            result_status=execution_result.status,
            underlying=trade_intent.underlying,
            action=trade_intent.action
        )
        
        execution_plan = build_execution_plan(
            trade_intent=trade_intent,
            execution_result=execution_result,
            source_post_id=post_id,
            action="PLACE_ORDER",
            signal_type=entry.get("signal_type", "UNKNOWN"),
            matched_position_id=matched_position_id
        )
        log_execution_plan(execution_plan)
        
        action_type = "APPROVE_LIVE" if mode == "live" else "APPROVE_PAPER"
        result_dict = {
            "status": execution_result.status,
            "broker": execution_result.broker,
            "order_id": execution_result.order_id,
            "message": execution_result.message,
            "fill_price": execution_result.fill_price,
            "filled_quantity": execution_result.filled_quantity
        }
        
        record_review_action(
            post_id=post_id,
            action=action_type,
            mode=mode,
            notes="Executed successfully",
            trade_intent_id=trade_intent.id,
            preflight=preflight_result,
            result=result_dict,
            ticker=trade_intent.underlying
        )
        
        return jsonify({
            "success": True,
            "message": f"Executed in {mode} mode",
            "trade_intent": trade_intent_dict,
            "preflight_result": preflight_result,
            "execution_result": result_dict,
            "matched_position_id": matched_position_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Execution error: {str(e)}",
            "trade_intent": trade_intent_dict,
            "preflight_result": preflight_result
        })


@app.route("/review/reject", methods=["POST"])
def reject_signal():
    """
    Reject a signal with notes.
    
    Body: { "post_id": "...", "notes": "..." }
    """
    from review_queue import record_review_action, list_recent_signals
    
    data = request.get_json() or {}
    post_id = data.get("post_id", "")
    notes = data.get("notes", "").strip()
    
    if not post_id:
        return jsonify({
            "success": False,
            "message": "Missing post_id"
        }), 400
    
    if not notes:
        return jsonify({
            "success": False,
            "message": "Notes are required for rejection"
        }), 400
    
    signals = list_recent_signals(limit=100)
    ticker = ""
    for sig in signals:
        if sig.get("post_id") == post_id:
            ticker = sig.get("ticker", "")
            break
    
    record_review_action(
        post_id=post_id,
        action="REJECT",
        mode=None,
        notes=notes,
        ticker=ticker
    )
    
    return jsonify({
        "success": True,
        "message": "Signal rejected",
        "post_id": post_id,
        "notes": notes
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
