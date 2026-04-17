"""Web dashboard — live transcript and alert feed via SSE."""
import json
import queue
import threading
import logging
from datetime import datetime
from flask import Flask, Response, render_template_string

log = logging.getLogger(__name__)

# Shared event queue for SSE clients
_event_queues: list[queue.Queue] = []
_lock = threading.Lock()
_transcript_history: list[dict] = []
MAX_HISTORY = 200


def push_event(event_type: str, data: dict):
    """Push an event to all connected SSE clients."""
    data["timestamp"] = datetime.now().strftime("%H:%M:%S")
    data["type"] = event_type

    if event_type in ("transcript", "alert"):
        _transcript_history.append(data)
        if len(_transcript_history) > MAX_HISTORY:
            _transcript_history.pop(0)

    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _lock:
        dead = []
        for q in _event_queues:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _event_queues.remove(q)


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Radio Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; }
        .header { background: #16213e; padding: 1rem 2rem; border-bottom: 2px solid #0f3460; display: flex; align-items: center; gap: 1rem; }
        .header h1 { font-size: 1.3rem; color: #e94560; }
        .status { font-size: 0.85rem; padding: 4px 12px; border-radius: 12px; }
        .status.connected { background: #0a3d2a; color: #4ade80; }
        .status.disconnected { background: #3d0a0a; color: #f87171; }
        .container { max-width: 900px; margin: 0 auto; padding: 1rem; }
        .stats { display: flex; gap: 1rem; margin-bottom: 1rem; }
        .stat-card { background: #16213e; padding: 1rem; border-radius: 8px; flex: 1; text-align: center; }
        .stat-card .value { font-size: 1.8rem; font-weight: bold; color: #e94560; }
        .stat-card .label { font-size: 0.8rem; color: #888; margin-top: 4px; }
        .feed { background: #16213e; border-radius: 8px; overflow: hidden; }
        .feed-header { padding: 0.8rem 1rem; background: #0f3460; font-weight: 600; font-size: 0.9rem; }
        .feed-body { max-height: 70vh; overflow-y: auto; padding: 0.5rem; }
        .entry { padding: 0.6rem 0.8rem; border-bottom: 1px solid #1a1a2e; font-size: 0.9rem; display: flex; gap: 0.8rem; }
        .entry:last-child { border-bottom: none; }
        .entry .time { color: #666; font-family: monospace; min-width: 70px; }
        .entry .text { flex: 1; }
        .entry.alert { background: #2d1525; border-left: 3px solid #e94560; }
        .entry.alert .keyword { color: #e94560; font-weight: bold; }
        .entry.transcript { border-left: 3px solid #333; }
        .empty { color: #555; text-align: center; padding: 3rem; font-style: italic; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Radio Monitor</h1>
        <span id="status" class="status disconnected">Connecting...</span>
    </div>
    <div class="container">
        <div class="stats">
            <div class="stat-card">
                <div id="alert-count" class="value">0</div>
                <div class="label">Alerts</div>
            </div>
            <div class="stat-card">
                <div id="transcript-count" class="value">0</div>
                <div class="label">Transmissions</div>
            </div>
            <div class="stat-card">
                <div id="last-alert" class="value">-</div>
                <div class="label">Last Alert</div>
            </div>
        </div>
        <div class="feed">
            <div class="feed-header">Live Feed</div>
            <div id="feed" class="feed-body">
                <div class="empty">Waiting for radio traffic...</div>
            </div>
        </div>
    </div>
    <script>
        let alertCount = 0, transcriptCount = 0;
        const feed = document.getElementById('feed');
        const statusEl = document.getElementById('status');

        function connect() {
            const es = new EventSource('/events');
            es.onopen = () => {
                statusEl.textContent = 'Listening';
                statusEl.className = 'status connected';
            };
            es.onerror = () => {
                statusEl.textContent = 'Disconnected';
                statusEl.className = 'status disconnected';
                setTimeout(connect, 3000);
            };
            es.addEventListener('transcript', (e) => {
                const data = JSON.parse(e.data);
                transcriptCount++;
                document.getElementById('transcript-count').textContent = transcriptCount;
                addEntry('transcript', data.timestamp, data.text);
            });
            es.addEventListener('alert', (e) => {
                const data = JSON.parse(e.data);
                alertCount++;
                document.getElementById('alert-count').textContent = alertCount;
                document.getElementById('last-alert').textContent = data.timestamp;
                const keywords = data.matches.map(m => m.keyword).join(', ');
                addEntry('alert', data.timestamp, data.text, keywords);
                if (Notification.permission === 'granted') {
                    new Notification('Radio: ' + keywords, { body: data.text });
                }
            });
            es.addEventListener('status', (e) => {
                const data = JSON.parse(e.data);
                statusEl.textContent = data.message;
            });
        }

        function addEntry(type, time, text, keyword) {
            const empty = feed.querySelector('.empty');
            if (empty) empty.remove();
            const div = document.createElement('div');
            div.className = 'entry ' + type;
            let html = '<span class="time">' + time + '</span><span class="text">';
            if (keyword) html += '<span class="keyword">[' + keyword + ']</span> ';
            html += text + '</span>';
            div.innerHTML = html;
            feed.insertBefore(div, feed.firstChild);
            if (feed.children.length > 200) feed.removeChild(feed.lastChild);
        }

        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }

        // Load history
        fetch('/history').then(r => r.json()).then(items => {
            items.forEach(item => {
                if (item.type === 'alert') {
                    alertCount++;
                    const keywords = item.matches ? item.matches.map(m => m.keyword).join(', ') : '';
                    addEntry('alert', item.timestamp, item.text, keywords);
                } else if (item.type === 'transcript') {
                    transcriptCount++;
                    addEntry('transcript', item.timestamp, item.text);
                }
            });
            document.getElementById('alert-count').textContent = alertCount;
            document.getElementById('transcript-count').textContent = transcriptCount;
        });

        connect();
    </script>
</body>
</html>
"""


def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config["config"] = config

    @app.route("/")
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.route("/events")
    def events():
        def stream():
            q = queue.Queue(maxsize=100)
            with _lock:
                _event_queues.append(q)
            try:
                yield "event: status\ndata: {\"message\": \"Connected\"}\n\n"
                while True:
                    try:
                        payload = q.get(timeout=30)
                        yield payload
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                with _lock:
                    if q in _event_queues:
                        _event_queues.remove(q)

        return Response(stream(), mimetype="text/event-stream")

    @app.route("/history")
    def history():
        return json.dumps(_transcript_history)

    return app
