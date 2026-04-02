FROM python:3.12-slim AS build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir . && \
    apt-get purge -y --auto-remove gcc

FROM build AS test

COPY tests/ tests/
RUN pip install --no-cache-dir ".[dev]"

ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests/", "-v"]

FROM build AS production

RUN ln -s "$(which dji-flightlog-parser)" /usr/local/bin/dji-log

ENTRYPOINT ["dji-flightlog-parser"]
