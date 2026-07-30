# run_scheduler.py
import time
from dotenv import load_dotenv
load_dotenv()

from market_service.app.market.background_refresher import start_scheduler

import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Healthcheck server listening on port {port}...")
    server.serve_forever()

if __name__ == "__main__":
    print("============================================================")
    print("INDICATOR AI — STANDALONE BACKGROUND SCHEDULER")
    print("============================================================")
    print("This script runs the daily market refresher completely")
    print("independent of the web workers. It prevents duplicate runs")
    print("and Gunicorn worker timeouts.")
    print("============================================================")
    print("Starting scheduler... (Press Ctrl+C to exit)\n")
    
    start_scheduler()
    
    # Start a dummy HTTP server to satisfy Cloud Run's port requirement
    start_health_server()
