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

# sgmllib stub (removed in Python 3.11, still needed by feedparser)
RUN python3 -c "import sgmllib" 2>/dev/null || python3 -c "
import site, os
stub = '''import re
from html.parser import HTMLParser
class SGMLParseError(Exception): pass
class SGMLParser(HTMLParser): pass
entityref = re.compile(r\"&([a-zA-Z][-.a-zA-Z0-9]*)[^-a-zA-Z0-9]\")
incomplete = re.compile(r\"&[a-zA-Z#]\")
interesting = re.compile(r\"&|<\")
shorttag = re.compile(r\"<([a-zA-Z][-.a-zA-Z0-9]*)\/([^\/]*)/\")
shorttagopen = re.compile(r\"<([a-zA-Z][-.a-zA-Z0-9]*)/\")
starttagopen = re.compile(r\"<[>a-zA-Z]\")
endbracket = re.compile(r\"[<>]\")
'''
path = os.path.join(site.getsitepackages()[0], 'sgmllib.py')
open(path, 'w').write(stub)
print('sgmllib stub installed at', path)
"

# App code
COPY . .

# Ensure entrypoint is executable and uses LF line endings (defensive against Windows checkouts)
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
CMD ["/bin/sh", "/app/docker-entrypoint.sh"]
