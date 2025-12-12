"""
Flask dashboard for trading bot reporting.
Provides a simple UI to generate and download reports.
"""

import os
from flask import Flask, send_file, render_template_string, request

from report_docx import generate_report

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
            align-items: center;
            padding: 20px;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }
        h1 {
            color: #1a1a2e;
            font-size: 28px;
            margin-bottom: 10px;
            text-align: center;
        }
        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .btn {
            display: block;
            width: 100%;
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
            transition: transform 0.2s, box-shadow 0.2s;
            margin-bottom: 15px;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .btn-secondary {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        .btn-secondary:hover {
            box-shadow: 0 10px 30px rgba(17, 153, 142, 0.4);
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
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Bot Dashboard</h1>
        <p class="subtitle">Victory Trades Alert Processing</p>
        
        <a href="/report" class="btn">
            Generate Last 24 Hours Report
        </a>
        
        <a href="/report?hours=48" class="btn btn-secondary">
            Generate Last 48 Hours Report
        </a>
        
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
</body>
</html>
"""


@app.route("/")
def index():
    """Dashboard home page."""
    return render_template_string(HTML_TEMPLATE)


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
