# Developer shortcuts for the local docker-compose stack.
# See docs/deploy-dev-prd.md for the full workflow.

.PHONY: help up down logs reset migrate psql test-backend deploy-dev deploy-prd ansible-check

help: ## Show this help
	@echo "Available targets:"
	@echo "  up             Build and start the full stack (db, migrations, backend, frontend)"
	@echo "  down           Stop the stack (keeps the pgdata volume)"
	@echo "  logs           Tail logs from all services"
	@echo "  reset          Stop AND destroy the pgdata volume (wipes the database)"
	@echo "  migrate        Run alembic upgrade head once against the running db"
	@echo "  psql           Open a psql shell against the local database"
	@echo "  test-backend   Run pytest inside the backend container"
	@echo "  deploy-dev     Run the ansible playbook against the dev inventory"
	@echo "  deploy-prd     Run the ansible playbook against the prd inventory (RELEASE_REF=<sha_or_tag>)"
	@echo "  ansible-check  Dry-run the playbook against the dev example inventory"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

# WARNING: destroys the pgdata volume. All local documents, chunks, and
# vector embeddings are lost. Use `make down` if you just want to stop.
reset:
	docker compose down -v

migrate:
	docker compose run --rm migrations

psql:
	docker compose exec db psql -U postgres rag_agent

test-backend:
	docker compose exec backend uv run pytest

# Ansible-driven deploys. See docs/deploy-dev-prd.md for the full flow and
# the required inventory / vault artifacts. `deploy-prd` expects
# RELEASE_REF to be set (a git tag or SHA) so prd is never deployed off a
# floating branch pointer.
deploy-dev:
	ansible-playbook -i deploy/ansible/inventory.dev.ini deploy/ansible/site.yml --ask-vault-pass

deploy-prd:
	ansible-playbook -i deploy/ansible/inventory.prd.ini deploy/ansible/site.yml --ask-vault-pass --extra-vars "app_ref=$(RELEASE_REF)"

# Dry-run against the checked-in example inventory. Safe for CI — needs
# no target hosts, no vault password, no secrets.
ansible-check:
	ansible-playbook -i deploy/ansible/inventory.dev.example.ini deploy/ansible/site.yml --check --diff

.DEFAULT_GOAL := help
