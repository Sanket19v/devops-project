# Project 1 — AI-Powered CI/CD Pipeline

Git push → tests → security scan → AI code review → build image → human approval → deploy → auto-rollback.

**You learn:** Docker, GitHub Actions, DevSecOps (Bandit, Trivy), registries (GHCR), Kubernetes deploys, rollbacks.

```
project-1-ai-cicd/
├── app/                    sample Flask app + tests + Dockerfile
├── k8s/app.yaml            Deployment + Service
├── ai_review.py            AI PR review, risk gate, release notes
├── requirements-ai.txt
├── common/llm.py           LLM helper (falls back to rules if no key)
└── .github/workflows/ci-cd.yml
```

## Run locally
```bash
cd app && pip install -r requirements.txt && pytest -q && python main.py
docker build -t demo-app:local app
```

## Run the pipeline
1. Make **this folder** the root of a new GitHub repo (GitHub only reads `.github/` at the repo root).
2. Repo secrets: `ANTHROPIC_API_KEY` (optional), `KUBE_CONFIG_B64` (`base64 -w0 ~/.kube/config`).
3. Settings → Environments → create `production`, add *required reviewers* (your approval gate).
4. Open a PR → tests, Bandit, Trivy, AI review comment.
   Test it: add `password = "abc123"` to a file → flagged **HIGH**, check fails.
5. Merge to main → build → approve → deploy. Break the image on purpose to see the rollback.

Note: GitHub runners can't reach a local kind cluster. Use a cloud VM/cluster, or a self-hosted runner.
