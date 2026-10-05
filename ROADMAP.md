# 10-Week AI DevOps Lab Roadmap (8–10 hrs/week)

| Week | Focus | You Build / Learn | Done When |
|---|---|---|---|
| **1** | Linux, Git, Docker | Run `app/` locally, write the Dockerfile, build container | `docker run` serves `/health` |
| **2** | CI (GitHub Actions) | `test`, `security` jobs (pytest, Bandit, Trivy) | PR shows all green checks |
| **3** | Kubernetes Basics | Kind cluster, Deployment, Service, probes (`k8s/app.yaml`) | `kubectl get pods` healthy; kill pod & watch it heal |
| **4** | **Project 1 Done** | `ai-review` job, image build to GHCR, gated deploy + rollback | Open a PR with hard-coded secret → AI flags HIGH |
| **5** | Observability | kube-prometheus-stack, Grafana dashboard, custom alert rules | Alert fires when hitting `/error` |
| **6** | **Project 2 Done** | Run copilot, inspect diagnosis, enable `REMEDIATE=true` | Hit `/error` → watch it diagnose + scale/restart + verify |
| **7** | Cloud Fundamentals (AWS) | IAM (least privilege), EC2, EBS, CloudWatch, AWS CLI | Can explain every line of Terraform infrastructure |
| **8** | **Project 3 Core** | Terraform deploy → `optimizer.py` on AWS metrics | Report identifies orphan volume & idle instances |
| **9** | Close the Loop | Optimizer `--apply` with plan + human approval | Safely downsizes infrastructure with zero downtime |
| **10** | Polish & Showcase | Comprehensive READMEs, architecture diagrams, live demo | Anyone can run it cleanly from the documentation |

---

## Stretch Goals (Beyond the Core)

- **LangGraph Integration**: Rewrite the incident copilot flow as a multi-step LangGraph agent (gather → analyse → approve → act → verify).
- **Interactive ChatOps**: Add automated rollback as a remediation action with Slack approve/reject buttons.
- **Distributed Tracing**: Add **Loki** for log aggregation and **Tempo** for distributed tracing.
- **Project 4 (Security Engine)**: CloudTrail logs → OpenSearch → LLM security triage.

---

## Rules That Keep You Safe

1. **Set an AWS Budget Alert ($5)** before creating any cloud resources. Always run `terraform destroy` when done.
2. **Never commit secrets**: Use GitHub Secrets and Kubernetes Secrets (`kubectl create secret`).
3. **Autonomous remediation stays OFF** until you have verified diagnoses in advisory mode.
4. **LLM output is an advisory suggestion**: The code enforces strict action whitelisting, never running raw model-generated commands.
