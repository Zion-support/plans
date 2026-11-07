#!/usr/bin/env python3
"""Read-only production contract checks. No dependency on the retired catalog JS."""
import argparse
import json
import re
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = 'https://ziontechgroup.com/'
SCRIPT = '/assets/js/finops-scenario.js'
ESTIMATORS = [f'/{lang}apps/finops-scenario-estimator.html' for lang in ('', 'pt/', 'es/', 'fr/', 'de/')]
ROUTES = ['/', '/services/', '/agents/', '/autonomous-ai-agents/', '/plans/',
          '/discovery/', '/booking/', '/cpa/', '/free-ai-it-tools/', '/academy/',
          '/blog/', '/telegram/', '/pricing/', '/finops-consulting/', '/zion-app-network/']

class ProbeError(Exception):
    pass

def origin(url):
    """Compare web origins, including scheme and normalized default ports."""
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    port = parsed.port if parsed.port is not None else {'http': 80, 'https': 443}.get(scheme)
    return (scheme, parsed.hostname, port)

class BoundedRedirects(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if origin(newurl) != origin(req.full_url):
            raise ProbeError('HTTP redirect left monitored origin: ' + newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(url):
    try:
        with build_opener(BoundedRedirects()).open(
                Request(url, headers={'User-Agent': 'Zion-Catalog-Health/2'}), timeout=20) as response:
            if response.status != 200:
                raise ProbeError(f'HTTP {response.status}: {url}')
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ProbeError('HTTP body exceeds 4 MB: ' + url)
            return response.url, raw.decode('utf-8', errors='replace')
    except HTTPError as error:
        raise ProbeError(f'HTTP {error.code}: {url} ({error.reason})') from error
    except (URLError, TimeoutError, OSError) as error:
        raise ProbeError(f'TRANSPORT: {url} ({error})') from error

class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.form = None
        self.form_nodes = []
        self.links = []
        self.text = []
        self.active_link = None
        self.script = None
        self.scripts = {}
        self.hidden_depth = 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.nodes.append((tag, attrs))
        if tag == 'form':
            self.form = attrs.get('id')
        if self.form == 'finops-scenario-form':
            self.form_nodes.append((tag, attrs))
        if tag in ('script', 'style'):
            self.hidden_depth += 1
        if tag == 'script':
            self.script = attrs.get('id')
            if self.script:
                self.scripts[self.script] = ''
        if tag == 'a':
            self.active_link = [attrs.get('href', ''), '']
            self.links.append(self.active_link)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden_depth = max(0, self.hidden_depth - 1)
        if tag == 'script':
            self.script = None
        if tag == 'form':
            self.form = None
        if tag == 'a':
            self.active_link = None

    def handle_data(self, data):
        if self.script:
            self.scripts[self.script] += data
        if not self.hidden_depth:
            self.text.append(data)
            if self.active_link is not None:
                self.active_link[1] += data

    def has(self, tag, **attrs):
        return any(t == tag and all(a.get(k) == v for k, v in attrs.items()) for t, a in self.nodes)

    def internal(self, href, path, base):
        resolved = urlsplit(urljoin(base, href))
        return origin(resolved.geturl()) == origin(base) and resolved.path.rstrip('/') == path.rstrip('/')

    def linked(self, path, base):
        return any(self.internal(href, path, base) for href, _ in self.links)

def require(condition, message):
    if not condition:
        raise ProbeError('CONTENT: ' + message)

def homepage(doc, base):
    text = ' '.join(doc.text).lower()
    for marker in ('managed it', 'agents', 'discovery', 'finops'):
        require(marker in text, 'homepage missing offering: ' + marker)
    require(any(doc.internal(h, '/discovery/', base) and
                re.search(r'free\s+(?:ai\s+)?discovery', t, re.I)
                for h, t in doc.links), 'homepage missing Free Discovery CTA to /discovery/')
    for href, label in doc.links:
        if doc.internal(href, '/discovery/', base):
            require(not re.search(r'\$\s*[1-9]\d*', label), 'paid Discovery CTA: ' + label)
    require(doc.linked(ESTIMATORS[0], base), 'homepage missing current FinOps estimator link')
    require(doc.linked('/ai-services/ai-agents-autonomous-workflows/', base) or
            doc.linked('/autonomous-ai-agents/', base), 'homepage missing agents destination')

def estimator(doc, base):
    require(doc.has('form', id='finops-scenario-form'), 'FinOps form missing')
    require(any(a.get('id') == 'finops-scenario-result' for _, a in doc.nodes), 'FinOps output missing')
    for field in ('baseline', 'reduction', 'recurring', 'implementation', 'months'):
        require(any(t == 'input' and a.get('id') == field and a.get('type') == 'number'
                    for t, a in doc.form_nodes), 'FinOps numeric input missing from form: ' + field)
    require(any(t == 'button' and a.get('type') == 'submit' for t, a in doc.form_nodes),
            'FinOps submit missing from form')
    require(doc.has('script', id='finops-scenario-copy', type='application/json'), 'FinOps config missing')
    try:
        copy = json.loads(doc.scripts.get('finops-scenario-copy', ''))
        require(isinstance(copy, dict) and len(copy.get('outputs', [])) == 4 and
                all(copy.get(k) for k in ('locale', 'pending', 'error', 'noPayback')), 'FinOps config incomplete')
    except (ValueError, TypeError) as error:
        raise ProbeError('CONTENT: invalid FinOps JSON config') from error
    require(any(t == 'script' and doc.internal(a.get('src', ''), SCRIPT, base)
                for t, a in doc.nodes), 'FinOps script disconnected')

def alias(doc, final, base):
    if doc.internal(final, '/autonomous-ai-agents/', base):
        return
    require(any(t == 'meta' and a.get('http-equiv', '').lower() == 'refresh' and
                re.search(r'url\s*=\s*[\"\']?[^\s]+', a.get('content', ''), re.I) and
                doc.internal(re.split(r'url\s*=\s*', a['content'], flags=re.I)[-1].strip(' \"\''),
                             '/autonomous-ai-agents/', base) for t, a in doc.nodes),
            '/agents/ must redirect to /autonomous-ai-agents/')
    require(doc.linked('/autonomous-ai-agents/', base), 'agents alias missing usable fallback link')
    require(any(t == 'link' and a.get('rel') == 'canonical' and
                doc.internal(a.get('href', ''), '/autonomous-ai-agents/', base)
                for t, a in doc.nodes), 'agents alias missing correct canonical')

def check(base=BASE, getter=fetch, emit=print):
    failures = []
    for path in ROUTES + ESTIMATORS + [SCRIPT]:
        url = urljoin(base, path)
        try:
            final, source = getter(url)
            if path == SCRIPT:
                require(not source.lstrip().startswith('<'), 'FinOps JS returned HTML')
                for marker in ('function calculate(', 'finops-scenario-form', 'finops-scenario-copy',
                               'finops-scenario-result', "addEventListener('submit'"):
                    require(marker in source, 'FinOps script missing: ' + marker)
            else:
                doc = Document(source)
                require(doc.has('html'), path + ' is not HTML')
                require(not re.search(r'\b(?:404|page not found)\b', ' '.join(doc.text[:12]), re.I), path + ' is a soft 404')
                # Redirecting every route to the homepage is not successful availability.
                if path != '/agents/':
                    require(doc.internal(final, path, base), path + ' redirected to unrelated route: ' + final)
                if path == '/':
                    homepage(doc, base)
                elif path in ESTIMATORS:
                    estimator(doc, base)
                elif path == '/agents/':
                    alias(doc, final, base)
                else:
                    require(doc.has('h1'), path + ' missing page heading')
                    if path == '/discovery/':
                        require(re.search(r'free\s+(?:ai\s+)?discovery', ' '.join(doc.text), re.I), 'Discovery missing free offer')
            emit('OK ' + path)
        except ProbeError as error:
            failures.append(path + ': ' + str(error))
            emit('FAIL ' + failures[-1])
    emit(f'Watchdog: {len(failures)} failure(s), {len(ROUTES) + len(ESTIMATORS) + 1} checks.')
    return 1 if failures else 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=BASE)
    sys.exit(check(parser.parse_args().base_url))
