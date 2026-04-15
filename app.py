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


@app.route("/logs")
def logs():
    n = request.args.get("n", 50, type=int)
    try:
        with open(log_file_path, "r") as f:
            lines = f.readlines()
        events = [json.loads(l) for l in lines[-n:] if l.strip()]
        events.reverse()  # последние сверху
        return {"count": len(events), "events": events}, 200
    except FileNotFoundError:
        return {"count": 0, "events": []}, 200


@app.route("/test")
def test_page():
    """HTML-страница, которая запускает тот же скрипт что и GTM-тег.
    Параметры из URL прокидываются в страницу как sub_id1, user_id и т.д."""
    host = request.host_url.rstrip("/")
    endpoint = host + "/pb.php"
    # передаём query-параметры страницы как дефолты для скрипта
    qs = dict(request.args)
    qs_json = json.dumps(qs)
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Tracker test</title></head>
<body>
<h3>Tracker test page</h3>
<p>Firing pixel to: <code>{endpoint}</code></p>
<p>Check <a href="/logs?n=5" target="_blank">/logs</a> after a second.</p>
<pre id="out">Sending...</pre>
<script>
(function(){{
  var ENDPOINT = "{endpoint}";
  var EVENT_NAME = "plr";
  var BRAND_VALUE = "crwn";
  var overrides = {qs_json};

  function safe(v){{ return v===null||v===undefined?"":String(v); }}
  function trim(v){{ return safe(v).trim(); }}
  function getCurrentUrl(){{ try{{return String(location.href);}}catch(e){{return "";}} }}
  function getParamFromUrl(name,urlStr){{
    try{{
      var u=new URL(String(urlStr||getCurrentUrl()),getCurrentUrl());
      return u.searchParams.get(name)||"";
    }}catch(e){{
      var m=String(urlStr||getCurrentUrl()).match(new RegExp("[?&]"+name+"=([^&#]+)","i"));
      return m?decodeURIComponent(m[1]):"";
    }}
  }}
  function getCookie(name){{
    try{{
      var m=document.cookie.match(new RegExp('(?:^|; )'+name.replace(/[-[\\]{{}}()*+?.,\\\\^$|#\\s]/g,'\\\\$&')+'=([^;]*)'));
      return m?decodeURIComponent(m[1]):"";
    }}catch(e){{return "";}}
  }}
  function getLS(key){{ try{{return localStorage.getItem(key)||"";}}catch(e){{return "";}} }}
  function getFromAll(name){{
    return overrides[name]||getParamFromUrl(name)||getCookie(name)||getLS(name)||"";
  }}
  function buildUrl(params){{
    var q=[];
    for(var k in params){{
      if(!Object.prototype.hasOwnProperty.call(params,k)) continue;
      q.push(encodeURIComponent(k)+"="+encodeURIComponent(safe(params[k])));
    }}
    return ENDPOINT+"?"+q.join("&");
  }}

  var rawSub3=trim(getFromAll("sub_id3"));
  var subId3=/^hs[a-z0-9]{{10,}}/i.test(rawSub3)?rawSub3:"hs0000000000";

  var params={{
    event_name: EVENT_NAME,
    of_id: trim(getFromAll("of_id"))||trim(getFromAll("offer_id")),
    affiliate_id: trim(getFromAll("affiliate_id"))||trim(getFromAll("partner_id"))||trim(getFromAll("aff_id")),
    currency: (trim(getFromAll("currency"))||"INR").toUpperCase(),
    brand: BRAND_VALUE,
    sub_id1: trim(getFromAll("sub_id1")),
    sub_id2: trim(getFromAll("sub_id2")),
    sub_id3: subId3,
    sub_id4: trim(getFromAll("sub_id4"))||trim(getFromAll("bonus_id")),
    sub_id5: trim(getFromAll("sub_id5")),
    sub_id6: "",
    sub_id7: trim(getFromAll("sub_id7")),
    sub_id8: trim(getFromAll("sub_id8")),
    sub_id9: trim(getFromAll("sub_id9")),
    sub_id10: trim(getFromAll("sub_id10")),
    random: Math.floor(Math.random()*1000000)+1,
    user_id: trim(getFromAll("user_id"))||trim(getFromAll("custom1")),
    pixel_placement: "test",
    auth_status: "true",
    time: Math.floor(Date.now()/1000),
    ip: "",
    ua: navigator.userAgent
  }};

  var url=buildUrl(params);
  document.getElementById("out").textContent="URL:\\n"+url;

  var img=new Image();
  img.onload=function(){{ document.getElementById("out").textContent+="\\n\\nSent OK (200)"; }};
  img.onerror=function(){{ document.getElementById("out").textContent+="\\n\\nError sending pixel"; }};
  img.src=url;
}})();
</script>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/")
def index():
    return {"service": "event-tracker", "endpoints": ["/pb.php", "/track", "/health", "/logs?n=50", "/test"]}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
