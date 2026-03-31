FROM python:3.13-slim

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Tailwind CSS standalone CLI
ARG TARGETARCH
RUN ARCH="${TARGETARCH:-amd64}" \
    && if [ "$ARCH" = "amd64" ]; then TAILWIND_ARCH="x64"; else TAILWIND_ARCH="$ARCH"; fi \
    && curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-${TAILWIND_ARCH}" \
        -o /usr/local/bin/tailwindcss \
    && chmod +x /usr/local/bin/tailwindcss

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x compose/local/entrypoint.sh

ENTRYPOINT ["/usr/src/app/compose/local/entrypoint.sh"]
