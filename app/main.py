import logging, os, random, time
from flask import Flask, Response, jsonify
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("demo-app")

REQS = Counter("app_requests_total", "Total requests", ["path", "status"])
LAT = Histogram("app_request_seconds", "Request latency", ["path"])


@app.get("/")
def index():
    REQS.labels("/", "200").inc()
    return jsonify(message="hello", version=os.getenv("APP_VERSION", "dev"))


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/slow")
def slow():
    with LAT.labels("/slow").time():
        time.sleep(random.uniform(1, 3))
    REQS.labels("/slow", "200").inc()
    return jsonify(message="that was slow")


@app.get("/error")
def error():
    log.error("DB connection pool exhausted: timeout after 30s waiting for connection")
    REQS.labels("/error", "500").inc()
    return jsonify(error="internal"), 500


@app.get("/crash")
def crash():
    log.critical("Fatal: simulated crash")
    os._exit(1)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
