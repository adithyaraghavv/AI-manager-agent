# Dev/Prd deployment

How the RAG agent gets from a developer's laptop to a running Azure App
Service, with a manual approval gate protecting production.

## 1. Overview

Four pieces work together:

1. **`docker-compose.yml`** — the local dev stack. One command starts the
   backend + frontend. No local Postgres/migrations service — the app
   talks to Supabase over its REST API in every environment, so a local
   Postgres container never held any real data anyway.
2. **`Makefile`** — thin wrapper around `docker compose` so developers do
   not have to memorise flags (`make up`, `make logs`, etc.).
3. **`azure-pipelines.yml`** — Azure DevOps pipeline that builds, tests,
   deploys to dev automatically, and deploys to prd behind an approval
   gate.
4. **`backend/.env.dev.example` / `backend/.env.prd.example`** — the
   dev/prd split. Dev values live in the file; prd values live in ADO
   variable groups.

## 1a. Ansible-based deploy

Above the compose stack sits a thin ansible layer that turns a bare
Ubuntu host into a running RAG agent. Two layers, one responsibility
each:

- **Ansible pushes.** From a laptop or the ADO agent, `ansible-playbook`
  ssh's into the target host(s), installs docker + the compose plugin,
  creates the app user, syncs the repo at the requested ref, renders the
  backend `.env` from ansible variables, and runs `docker compose up`.
- **docker-compose runs.** On the target host, `docker-compose.prod.yml`
  boots the single combined backend+frontend service (see
  `backend/Dockerfile.prod`) — no new orchestration primitive at runtime,
  just a compose stack, provisioned consistently. This is deliberately a
  different compose file from local dev's `docker-compose.yml` (two
  hot-reload containers) — see the comments in each for why.

### Layout

```
deploy/ansible/
├── ansible.cfg
├── site.yml                     # entry point — runs both roles
├── requirements.yml             # community.docker collection
├── inventory.dev.example.ini    # copy to inventory.dev.ini
├── inventory.prd.example.ini    # copy to inventory.prd.ini
├── vault.example.yml            # copy to vault.yml, then ansible-vault encrypt
├── group_vars/
│   ├── all.yml                  # shared non-secret defaults
│   ├── dev.yml                  # dev overrides (DEBUG logs)
│   └── prd.yml                  # prd placeholders (real values in vault)
└── roles/
    ├── host_prep/               # apt, docker engine, app user
    └── app_deploy/              # git sync, .env render, compose up
```

### Prerequisites

- `ansible >= 2.14` (installer of choice: `uv tool install ansible` or
  `pipx install ansible`).
- `ansible-galaxy collection install -r deploy/ansible/requirements.yml`
  (installs `community.docker`, which the `app_deploy` role uses to
  drive compose).
- ssh access to the target host(s) with a user that can `sudo`.

### Local trial (no target hosts required)

```bash
ansible-playbook \
  -i deploy/ansible/inventory.dev.example.ini \
  deploy/ansible/site.yml \
  --check --diff
```

`--check` puts ansible in dry-run mode — no changes hit the target. The
same command runs behind `make ansible-check`, which is what CI can call
to lint the playbook without ever needing real hosts.

### Real deploys

Populate `inventory.dev.ini` (dev hostnames) and `vault.yml` (secrets
listed in `vault.example.yml`), encrypt the vault, then:

```bash
ansible-vault encrypt deploy/ansible/vault.yml   # once, when creating it
make deploy-dev                                  # prompts for the vault pass
make deploy-prd RELEASE_REF=v1.4.2               # pins app_ref to a tag/SHA
```

The `Makefile` targets pass `--ask-vault-pass` so the password never
touches disk on the operator's machine.

### Secrets

Three ways to hand secrets to ansible; pick per environment:

1. **`ansible-vault` file** (default for local operators). Values live
   in `deploy/ansible/vault.yml`, encrypted at rest. Reference via
   `--extra-vars @vault.yml --ask-vault-pass`.
2. **`--extra-vars` on the command line** for one-off overrides.
3. **ADO secure files + secret variable** for CI (see section 4).

Never commit an unencrypted `vault.yml`. The example file is a
placeholder listing the keys `env.j2` expects — copy it, fill it, encrypt
it, then commit the encrypted version if you want the pipeline to pull
it out of the repo instead of a secure file.

## 2. Local development

Prerequisites: Docker Desktop (or any modern docker + compose plugin).

```bash
make up          # build images, start backend + frontend
make logs        # tail everything
make down        # stop
```

Then hit:

- Backend Swagger: <http://localhost:8000/docs>
- Frontend: <http://localhost:5173>

Other useful targets:

| Target             | What it does                                          |
| ------------------ | ----------------------------------------------------- |
| `make test-backend`| Run pytest inside the backend container              |

Alembic migrations and the one-off seed scripts are run manually against
a real reachable Postgres (e.g. Supabase's direct connection string via
`DATABASE_URL`) when actually needed — not part of bringing the stack up,
since the app's normal runtime path never touches Postgres directly.

## 3. Environment variables

The split is deliberate:

- **`backend/.env.dev.example`** — checked in. Contains local defaults
  (`DEBUG` logs, blank `DATABASE_URL` — only needed for the one-off
  Alembic/seed scripts, not the running app). Copy to `backend/.env.dev`
  if you need overrides; both are wired into compose via `env_file`.
- **`backend/.env.prd.example`** — checked in as a *template* only. The
  file explicitly says "do not put real secrets here". The real values
  live in the ADO variable group `rag-agent-prd` and get injected at
  deploy time as App Service application settings.

**Adding a new variable:**

1. Add the key (with a safe placeholder) to both `.env.dev.example` and
   `.env.prd.example`.
2. Add the real dev value to the `rag-agent-dev` ADO variable group.
3. Add the real prd value to the `rag-agent-prd` ADO variable group,
   marking it as a secret if it is one.
4. If it needs to reach the App Service at runtime, add it to the
   `AzureWebApp@1` app settings block (or use the App Service
   configuration UI; the variable group values are already exposed to the
   pipeline via `$(varName)`).

Never commit real secrets. `.env.dev` (unsuffixed) is what a developer
overrides locally — add it to `.gitignore` if you introduce one.

## 4. Azure DevOps setup

The pipeline is a scaffold. Before the first run, configure:

### Service connections

Under Project Settings -> Service connections, create two ARM service
connections (one per subscription/RG):

- `sc-rag-agent-dev`
- `sc-rag-agent-prd`

Store the connection *name* in the corresponding variable group as
`azureServiceConnectionDev` / `azureServiceConnectionPrd`.

### Variable groups

Under Pipelines -> Library, create two variable groups:

**`rag-agent-dev`** (values):

- `azureServiceConnectionDev` — name of the dev ARM connection above
- `webAppNameDev` — the dev App Service name
- `staticWebAppTokenDev` — deployment token for the dev Static Web App
  (mark as secret)
- `ANSIBLE_VAULT_PASS` — the password used to encrypt `vault.yml` for
  dev (mark as secret). Used by the ansible-based deploy stage.
- Any app-level env: `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, …

**`rag-agent-prd`**: same shape, but with prd values (all secrets marked
as secret) — including its own `ANSIBLE_VAULT_PASS`.

### Secure files (ansible-driven deploy)

Under Pipelines -> Library -> Secure files, upload:

- `inventory.dev.ini` — the dev inventory (real hostnames + `ansible_user`).
- `inventory.prd.ini` — the prd inventory.
- `vault.yml` — the ansible-vault-encrypted secrets file (one per env;
  the pipeline pulls the right one per stage). Encrypted with the
  matching `ANSIBLE_VAULT_PASS` from the variable group.

The `Deploy_Dev` / `Deploy_Prd` stages in `azure-pipelines.yml`
download these files, run `ansible-playbook` against them, and unlock
the vault with `ANSIBLE_VAULT_PASS`. Grant each stage's environment
permission to use the secure files (secure files default to
per-pipeline authorization).

### Environments

Under Pipelines -> Environments, create:

- `rag-agent-dev` — no approval needed
- `rag-agent-prd` — **add an approval and check** listing whoever should
  sign off on production deploys. This is what enforces the gate; the
  YAML only *references* the environment.

### App Services

Provision two App Services (Python 3.13, Linux) and two Static Web Apps —
one pair per environment. Wire the App Service names into
`webAppNameDev` / `webAppNamePrd` in the variable groups.

## 5. Promotion flow

```
developer PR to main
        │
        ▼
Build_Test  (pytest + vite build; runs on the PR too)
        │
        ▼
merge to main
        │
        ▼
Build_Test  (again, on the merge commit)
        │
        ▼
Deploy_Dev  (auto — no approval)
        │
        ▼
Deploy_Prd  (waits for approval on the `rag-agent-prd` environment)
        │
        ▼
production
```

PR runs stop at Build_Test — the deploy stages are conditioned on
`Build.SourceBranch == refs/heads/main`.

## 6. Troubleshooting

**Backend starts but crashes on first request.** Check that
`backend/.env.dev.example` still matches the config keys the app reads.
If a required key was added and not backfilled here, the container will
boot but fail on use.

**Pipeline: `The pipeline is not valid. Variable group 'rag-agent-dev'
could not be found`.** You have not created the variable group yet, or
the pipeline does not have permission to use it. Open the variable group
in the Library and grant access to the pipeline.

**Pipeline: dev deploys but prd is skipped silently.** The
`Deploy_Prd` stage is conditioned on the source branch being
`refs/heads/main`. Manual runs from a feature branch will skip it
by design.

**Pipeline: prd stage runs without waiting for approval.** The approval
lives on the *environment*, not the YAML. Confirm `rag-agent-prd` under
Pipelines -> Environments actually has an approval check configured.

**Frontend container exits immediately.** The frontend Dockerfile runs
`npm run dev:frontend`, not the top-level `npm run dev` (which would try
to spawn its own uvicorn inside the node container). If someone changes
`package.json` scripts, keep this invariant.
