"""
Flask dashboard for trading bot reporting and broker smoke tests.
Provides a simple UI to generate reports and test broker connections.
"""

import os
from flask import Flask, send_file, render_template_string, request, jsonify

from report_docx import generate_report
from broker_smoke_tests import alpaca_smoke_test, tradier_smoke_test

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
                const okClass = step.ok ? 'step-ok' : 'step-fail';
                const okText = step.ok ? '✓' : '✗';
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
            const statusClass = data.success ? 'step-ok' : 'step-fail';
            const statusText = data.success ? 'PASSED' : 'FAILED';
            
            resultsDiv.innerHTML = `
                <div class="results-header">
                    <h4>${brokerName} Test Results: <span class="${statusClass}">${statusText}</span></h4>
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
