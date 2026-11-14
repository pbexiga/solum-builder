# Solum Builder: one image with native ngspice, the Python backend and the web UI (D-006).
ARG BASE=docker.io/library/python:3.12-slim-trixie

# ngspice 44.2 built from the release tarball without fused multiply-add, the same on
# x86-64, arm64 and the Mac app (D-327): fused multiply-add stops some op-amp transients on arm64.
# Built here so the runtime image gets no compiler; scripts/ngspice_build.sh owns the recipe.
FROM ${BASE} AS ngspice
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ make curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY scripts/ngspice_build.sh /tmp/
RUN /tmp/ngspice_build.sh /opt/ngspice /tmp/ngspice \
 && strip --strip-unneeded /opt/ngspice/lib/libngspice.so.0 /opt/ngspice/bin/ngspice /opt/ngspice/lib/ngspice/*.cm

FROM ${BASE} AS runtime

# Pango, HarfBuzz and the DejaVu fonts are WeasyPrint's, for the build package's PDFs (D-205).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
# The shared library, XSPICE's code models and spinit (which names them by these paths).
COPY --from=ngspice /opt/ngspice/lib/ /opt/ngspice/lib/
COPY --from=ngspice /opt/ngspice/share/ngspice/ /opt/ngspice/share/ngspice/
RUN echo /opt/ngspice/lib > /etc/ld.so.conf.d/ngspice.conf && ldconfig

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
RUN pip install ".[dev]" \
 && python -m playwright install --with-deps chromium-headless-shell
# The ngspice program too (dev only): exported netlists are tested in plain ngspice, as a
# builder would run them (D-206).
COPY --from=ngspice /opt/ngspice/bin/ngspice /usr/local/bin/ngspice
WORKDIR /src
