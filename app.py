import os
import json
import logging
import struct
import zlib
from datetime import datetime, timezone
from flask import Flask, request, Response

app = Flask(__name__)

# --- logging setup ---
LOG_DIR = os.environ.get("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_file_path = os.path.join(LOG_DIR, "events.jsonl")

file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

logger = logging.getLogger("tracker")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


# 1x1 transparent PNG (binary, minimal)
_TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def get_real_ip() -> str:
    """Получить реальный IP с учётом проксей Railway/CDN."""
    for header in ("X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"):
        val = request.headers.get(header)
        if val:
            return val.split(",")[0].strip()
    return request.remote_addr or ""


KNOWN_PARAMS = [
    "event_name", "of_id", "affiliate_id", "currency", "brand",
    "sub_id1", "sub_id2", "sub_id3", "sub_id4", "sub_id5",
    "sub_id6", "sub_id7", "sub_id8", "sub_id9", "sub_id10",
    "random", "user_id", "pixel_placement", "auth_status", "time", "ua",
]


def track():
    args = request.args

    event = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "ip": get_real_ip(),
        "ua_header": request.headers.get("User-Agent", ""),
        "referer": request.headers.get("Referer", ""),
    }

    for p in KNOWN_PARAMS:
        event[p] = args.get(p, "")

    # ua из параметра приоритетнее заголовка, если передан
    if event.get("ua"):
        event["ua_header"] = event.pop("ua")
    else:
        event.pop("ua", None)

    # Дополнительные (неизвестные) параметры — всё равно сохраняем
    extra = {k: v for k, v in args.items() if k not in KNOWN_PARAMS}
    if extra:
        event["extra_params"] = extra

    logger.info(json.dumps(event, ensure_ascii=False))

    resp = Response(_TRANSPARENT_PNG, status=200, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# Принимаем оба пути: /pb.php (совместимость с GTM) и /track
app.add_url_rule("/pb.php", "track_php", track, methods=["GET", "HEAD"])
app.add_url_rule("/track",  "track",     track, methods=["GET", "HEAD"])


@app.route("/health")
def health():
    return {"status": "ok", "log": log_file_path}, 200


@app.route("/")
def index():
    return {"service": "event-tracker", "endpoints": ["/pb.php", "/track", "/health"]}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
