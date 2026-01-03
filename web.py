"""
AutoSig v1.0 - Web Service Entry Point

This file exists solely to provide a Flask app for Gunicorn.
The actual Flask application and routes are defined in dashboard.py.

Railway Web Service:
- Start command: gunicorn web:app
- Purpose: Serve UI, health checks, API endpoints
- Must NOT run the ingestion worker
"""

from dashboard import app

# Export app for Gunicorn
# Gunicorn will look for 'app' in this module
__all__ = ['app']

