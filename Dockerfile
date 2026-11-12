# Solum Builder: one image with native ngspice, the Python backend and the web UI (D-006).
ARG BASE=docker.io/library/python:3.12-slim-trixie

# libngspice0 ships no XSPICE code models or spinit, and the ngspice CLI package
# drags in X11. Take only the code models (libc-only) and spinit from it.
FROM ${BASE} AS ngspice-extras
RUN apt-get update \
 && cd /tmp && apt-get download ngspice \
 && dpkg-deb -x ngspice_*.deb /extract

FROM ${BASE} AS runtime

# libngspice0 is the ngspice shared library (Debian trixie: ngspice 44.2). Pango, HarfBuzz
# and the DejaVu fonts are WeasyPrint's, for the build package's PDFs (D-205).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libngspice0 \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ngspice-extras /extract/usr/lib/ /usr/lib/
COPY --from=ngspice-extras /extract/usr/share/ngspice/ /usr/share/ngspice/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DATA_DIR=/data \
    CACHE_DIR=/cache \
    LIBRARY_DIR=/app/library \
    WEB_DIR=/app/web \
    GUIDE_DIR=/app/docs/guide \
    PORT=8000

WORKDIR /app
COPY pyproject.toml ./
COPY solum ./solum
RUN pip install .
COPY library ./library
COPY web ./web
COPY docs/guide ./docs/guide

VOLUME ["/data", "/cache"]
EXPOSE 8000
CMD ["solum", "serve"]

# Development image: adds test and lint tools. Never shipped (D-020).
FROM runtime AS dev
# Browsers live outside $HOME: `make` runs tests with HOME=/tmp.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
# The ngspice program too (with its X11 libraries, dev only): exported netlists are tested
# in plain ngspice, as a builder would run them (D-206).
RUN pip install ".[dev]" \
 && python -m playwright install --with-deps chromium-headless-shell \
 && apt-get update && apt-get install -y --no-install-recommends ngspice \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
