# Single entry point for tests and checks (AGENTS.md).
# By default everything runs inside the dev image (Python 3.12 + libngspice + tools),
# so nothing is installed on the host. `make LOCAL=1 <target>` runs directly instead.

CONTAINER ?= $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
DEV_IMAGE ?= solum-builder:dev

ifdef LOCAL
RUN :=
else
# Docker runs as root by default; keep files written to the repo owned by you.
USER_FLAG := $(if $(findstring docker,$(CONTAINER)),--user $(shell id -u):$(shell id -g),)
# `:z` relabels the mount for SELinux (Fedora); only Linux has it, so a Mac mounts plainly.
MOUNT_OPT := $(if $(filter Linux,$(shell uname -s)),:z,)
RUN := $(CONTAINER) run --rm $(USER_FLAG) -v $(CURDIR):/src$(MOUNT_OPT) -w /src \
	-e PYTHONPATH=/src -e HOME=/tmp -e LIBRARY_DIR=/src/library -e WEB_DIR=/src/web \
	$(DEV_IMAGE)
endif

PYTEST := $(RUN) python -m pytest
# The Python ruff checks: the app, the tests, the scripts and the agent skills (worked/ excluded in pyproject.toml).
PY_DIRS := solum tests scripts .claude/skills
# Tests run on every core (pytest-xdist, D-166); `make JOBS=0 ACCEPT_JOBS=0 ...` runs them one at a time.
# Acceptance and UI tests run on fewer workers, a test file to each: the browsers and audio
# renders time out when 16 share the CPU.
JOBS ?= auto
ACCEPT_JOBS ?= 4
PAR := -n $(JOBS)
ACCEPT_PAR := -n $(ACCEPT_JOBS) --dist loadfile

.PHONY: help dev-image image image-tar run test ruff jslint lint check accept bench hooks schema mac-app

help:
	@echo "make dev-image  build the dev image (do this first, and after changing dependencies)"
	@echo "make image      build the runtime image solum-builder:latest"
	@echo "make run CMD=.. any command in the dev image (make run CMD=\"python scripts/prof.py ts808\")"
	@echo "make test       unit tests (fast, no ngspice)"
	@echo "make ruff       ruff lint + format check (app, tests, scripts, skills)"
	@echo "make jslint     the browser code's static check (undefined names, unused and wrong imports)"
	@echo "make lint       ruff + jslint + mypy --strict"
	@echo "make check      lint + unit, sim, rules, parity tests + coverage (before every commit)"
	@echo "make accept     acceptance + UI tests (before ending a session)"
	@echo "make bench      solum bench in the runtime image"
	@echo "make image-tar  save the runtime image to dist/ for copying to the NAS"
	@echo "make hooks      install the git pre-commit hook"
	@echo "make schema     regenerate docs/circuit.schema.json from the Pydantic models"
	@echo "make mac-app    build the Mac app into dist/ (on an Apple Silicon Mac; docs/maintain/mac-app.md)"

dev-image:
	$(CONTAINER) build --target dev -t $(DEV_IMAGE) .

image:
	$(CONTAINER) build --target runtime -t solum-builder:latest .

# Any command in the dev image, from the repo's top folder: make run CMD="python scripts/prof.py ts808"
run:
	$(RUN) $(CMD)

test:
	$(PYTEST) -q $(PAR) tests/unit

ruff:
	$(RUN) sh -c "ruff check $(PY_DIRS) && ruff format --check $(PY_DIRS)"

# The browser code: names never declared or imported, unused and wrong imports (D-286).
jslint:
	$(RUN) scripts/jscheck.sh

lint: ruff jslint
	$(RUN) mypy

check: lint
	$(PYTEST) -q $(PAR) -m "not timing" tests/unit tests/sim tests/rules tests/parity \
		--cov --cov-report=term-missing

# Exit code 5 means "no tests collected": fine until Phase 1 adds acceptance circuits.
# Timing tests run on their own after the rest, so the other tests' load can't slow them.
accept:
	$(PYTEST) -q $(ACCEPT_PAR) -m "not timing" tests/acceptance tests/ui; status=$$?; \
		if [ $$status -eq 5 ]; then echo "(no acceptance/UI tests yet)"; exit 0; fi; \
		if [ $$status -ne 0 ]; then exit $$status; fi; \
		$(PYTEST) -q -m timing tests/sim tests/acceptance tests/ui; status=$$?; \
		if [ $$status -eq 5 ]; then exit 0; fi; exit $$status

# The cache timings need the disk the app's cache is on (D-126 hid on tmpfs): compose's
# default ./cache, or `make BENCH_CACHE=/path/to/cache bench`.
BENCH_CACHE ?= $(CURDIR)/cache
bench:
	mkdir -p $(BENCH_CACHE)
	$(CONTAINER) run --rm -v $(BENCH_CACHE):/cache$(if $(filter Linux,$(shell uname -s)),:z,) \
		solum-builder:latest solum bench

# Image as a file, for hosts that don't build (the NAS): docker load -i <file>
image-tar: image
	mkdir -p dist
	$(CONTAINER) save solum-builder:latest | gzip > dist/solum-builder-image.tar.gz
	@ls -lh dist/solum-builder-image.tar.gz

hooks:
	install -m 755 scripts/pre-commit .git/hooks/pre-commit

# The circuit JSON Schema is generated from solum/circuit/schema.py (D-032).
schema:
	$(RUN) python -m solum.circuit.schema > docs/circuit.schema.json

# The Mac app (D-326): outside the dev image, on the Mac itself. It brings its own Python,
# ngspice and libraries into build/mac/ and runs the tests against them.
mac-app:
	scripts/mac_app.sh
