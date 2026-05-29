FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code --no-audit --no-fund

# Python deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# sgmllib stub (removed in Python 3.10+, referenced by some feedparser paths).
# Copy a real stub file into site-packages — avoids fragile inline heredocs.
COPY docker/sgmllib.py /tmp/sgmllib_stub.py
RUN python3 -c "import sgmllib" 2>/dev/null \
    || cp /tmp/sgmllib_stub.py "$(python3 -c 'import site; print(site.getsitepackages()[0])')/sgmllib.py"

# App code
COPY . .

# Ensure entrypoint is executable and uses LF line endings (defensive against Windows checkouts)
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
CMD ["/bin/sh", "/app/docker-entrypoint.sh"]
