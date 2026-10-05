"""AI Incident Copilot: Alertmanager webhook -> gather evidence -> LLM root cause
-> (optional, guard-railed) self-healing action -> verify."""
import json, os, sys, time
import requests
from fastapi import BackgroundTasks, Body, FastAPI
from kubernetes import client, config

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
from common.llm import ask_json

PROM = os.getenv("PROMETHEUS_URL", "http://monitoring-kube-prometheus-prometheus.monitoring.svc:9090")
REMEDIATE = os.getenv("REMEDIATE", "false").lower() == "true"   # OFF by default: human-in-the-loop first
ALLOWED_NS = os.getenv("ALLOWED_NAMESPACES", "default").split(",")
MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", "4"))
SLACK = os.getenv("SLACK_WEBHOOK_URL")
INCIDENTS: list = []

app = FastAPI(title="AI Incident Copilot")
try:
    config.load_incluster_config()
except Exception:
    try:
        config.load_kube_config()
    except Exception:
        print("[warn] no kubeconfig found; k8s evidence will be unavailable")

SYSTEM = """You are an SRE assistant. Given an alert and evidence (metrics, pod status, logs),
respond ONLY with JSON:
{"root_cause":"...","confidence":"low|medium|high","summary":"...","suggested_fix":"...",
 "action":"none|restart|scale","reason":"..."}
Use only the evidence. Choose restart/scale only if the evidence supports it, else "none"."""


def prom(q):
    try:
        res = requests.get(f"{PROM}/api/v1/query", params={"query": q}, timeout=8).json()["data"]["result"]
        return [float(r["value"][1]) for r in res]
    except Exception as e:
        return f"unavailable: {e}"


def gather(labels):
    ns, name = labels.get("namespace", "default"), labels.get("app", "demo-app")
    ev = {"metrics": {
        "error_rate_per_s": prom('sum(rate(app_requests_total{status="500"}[2m]))'),
        "p95_latency_s": prom("histogram_quantile(0.95, sum(rate(app_request_seconds_bucket[2m])) by (le))"),
        "restarts_1h": prom(f'sum(increase(kube_pod_container_status_restarts_total{{namespace="{ns}",pod=~"{name}.*"}}[1h]))'),
    }, "pods": [], "logs": {}}
    try:
        core = client.CoreV1Api()
        for p in core.list_namespaced_pod(ns, label_selector=f"app={name}").items:
            cs = p.status.container_statuses or []
            ev["pods"].append({
                "name": p.metadata.name, "phase": p.status.phase,
                "ready": bool(cs) and all(c.ready for c in cs),
                "restarts": sum(c.restart_count for c in cs),
                "last_terminated": [c.last_state.terminated.reason for c in cs
                                    if c.last_state and c.last_state.terminated],
            })
            ev["logs"][p.metadata.name] = core.read_namespaced_pod_log(p.metadata.name, ns, tail_lines=60)[-3000:]
    except Exception as e:
        ev["k8s_error"] = str(e)
    return ev


def rule_based(ev):
    logs = " ".join(ev["logs"].values()).lower()
    if "exhausted" in logs or "timeout" in logs:
        return {"root_cause": "Backend/DB connection pool exhaustion (timeouts in logs)", "confidence": "medium",
                "summary": "Errors correlate with connection timeouts.", "suggested_fix":
                "Check DB health, raise pool size, add replicas.", "action": "scale", "reason": "rule: timeouts"}
    if any(p["restarts"] for p in ev["pods"]):
        return {"root_cause": "Pod crash loop", "confidence": "low", "summary": "Pods restarting.",
                "suggested_fix": "Inspect `kubectl describe pod` and previous logs.", "action": "none", "reason": "rule"}
    return {"root_cause": "unknown", "confidence": "low", "summary": "Not enough evidence.",
            "suggested_fix": "Investigate manually.", "action": "none", "reason": "rule"}


def verify(ns, dep, timeout=90):
    apps, end = client.AppsV1Api(), time.time() + timeout
    while time.time() < end:
        d = apps.read_namespaced_deployment(dep, ns)
        if (d.status.ready_replicas or 0) == d.spec.replicas and (d.status.updated_replicas or 0) == d.spec.replicas:
            return "recovered"
        time.sleep(5)
    return "NOT recovered - escalate to a human"


def remediate(action, ns, dep):
    apps = client.AppsV1Api()
    if action == "restart":
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        apps.patch_namespaced_deployment(dep, ns, {"spec": {"template": {"metadata": {
            "annotations": {"kubectl.kubernetes.io/restartedAt": stamp}}}}})
    elif action == "scale":
        n = min(apps.read_namespaced_deployment(dep, ns).spec.replicas + 1, MAX_REPLICAS)
        apps.patch_namespaced_deployment_scale(dep, ns, {"spec": {"replicas": n}})
    else:
        return "no action"
    return verify(ns, dep)


def notify(rec):
    print(json.dumps(rec, indent=2, default=str))
    if SLACK:
        d = rec["diagnosis"]
        text = f"*{rec['alert']}*: {d['root_cause']} ({d['confidence']})\nFix: {d['suggested_fix']}\nAuto-action: {rec['remediation']}"
        requests.post(SLACK, json={"text": text}, timeout=10)


def handle(alert):
    labels = alert.get("labels", {})
    if labels.get("alertname") in ("Watchdog", "InfoInhibitor"):
        return
    ns, dep = labels.get("namespace", "default"), labels.get("app", "demo-app")
    ev = gather(labels)
    diag = ask_json(SYSTEM, json.dumps({"alert": alert, "evidence": ev}, default=str)[:12000]) or rule_based(ev)
    rec = {"time": time.strftime("%F %T"), "alert": labels.get("alertname"), "diagnosis": diag, "remediation": None}
    if REMEDIATE and diag.get("action") in ("restart", "scale") and ns in ALLOWED_NS:
        try:
            rec["remediation"] = {"action": diag["action"], "result": remediate(diag["action"], ns, dep)}
        except Exception as e:
            rec["remediation"] = {"action": diag["action"], "result": f"failed: {e}"}
    INCIDENTS.append(rec)
    notify(rec)


@app.post("/alert")
def alert(bg: BackgroundTasks, payload: dict = Body(...)):
    for a in payload.get("alerts", []):
        bg.add_task(handle, a)          # return fast so Alertmanager doesn't time out
    return {"accepted": len(payload.get("alerts", []))}


@app.get("/incidents")
def incidents():
    return INCIDENTS


@app.get("/health")
def health():
    return {"status": "ok"}
