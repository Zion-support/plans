"""Deterministic contracts and real GET/redirect regression tests (stdlib only)."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request

import catalog_health as health

HOME = '''<html><h1>Managed IT, Autonomous Agents, FinOps</h1>
<a href="/discovery/">Start <b>Free AI Discovery</b> now</a>
<a href="/apps/finops-scenario-estimator.html">FinOps</a>
<a href="/autonomous-ai-agents/">Agents</a></html>'''
CONFIG = json.dumps(dict(outputs=['a', 'b', 'c', 'd'], locale='en-US', pending='Wait', error='Invalid', noPayback='None'))
FORM = ('<html><h1>FinOps</h1><form id="finops-scenario-form">' +
        ''.join(f'<input type="number" id="{key}">' for key in
                ('baseline', 'reduction', 'recurring', 'implementation', 'months')) +
        '<button type="submit">Calculate</button></form><div id="finops-scenario-result"></div>' +
        '<script id="finops-scenario-copy" type="application/json">' + CONFIG + '</script>' +
        '<script defer src="/assets/js/finops-scenario.js"></script></html>')
JS = "function calculate(v){}; 'finops-scenario-form finops-scenario-copy finops-scenario-result'; form.addEventListener('submit', f);"
ALIAS = '<html><link rel="canonical" href="https://ziontechgroup.com/autonomous-ai-agents/"><meta http-equiv="refresh" content="0; url=/autonomous-ai-agents/"><a href="/autonomous-ai-agents/">Continue</a></html>'

def fixtures():
    result = {p: '<html><h1>Service</h1></html>' for p in health.ROUTES}
    result.update({p: FORM for p in health.ESTIMATORS})
    result.update({'/': HOME, '/agents/': ALIAS, '/discovery/': '<html><h1>Free Discovery</h1></html>', health.SCRIPT: JS})
    return result

class Contracts(unittest.TestCase):
    def run_check(self, pages):
        self.messages = []
        return health.check(getter=lambda u: (u, pages[urlsplit(u).path]), emit=self.messages.append)

    def test_healthy_current_contract(self):
        self.assertEqual(self.run_check(fixtures()), 0)

    def test_missing_markers_do_not_pass_from_comments_or_scripts(self):
        pages = fixtures()
        pages['/'] = '<html><h1>Home</h1><!-- Managed IT Agents Discovery FinOps --><script>' + HOME + '</script></html>'
        self.assertEqual(self.run_check(pages), 1)

    def test_free_cta_wrong_destination(self):
        pages = fixtures(); pages['/'] = HOME.replace('href="/discovery/"', 'href="https://other.test/discovery/"')
        self.assertEqual(self.run_check(pages), 1)

    def test_paid_discovery_contradiction(self):
        pages = fixtures(); pages['/'] += '<a href="/discovery">Discovery $99 (Deep Dive)</a>'
        self.assertEqual(self.run_check(pages), 1)

    def test_every_finops_dom_dependency(self):
        for old in ['<form id="finops-scenario-form">', 'id="finops-scenario-result"',
                    'id="finops-scenario-copy"', 'id="baseline"', 'type="submit"', health.SCRIPT]:
            with self.subTest(old=old):
                pages = fixtures(); pages[health.ESTIMATORS[0]] = FORM.replace(old, '')
                self.assertEqual(self.run_check(pages), 1)

    def test_all_five_languages_checked(self):
        for path in health.ESTIMATORS:
            pages = fixtures(); pages[path] = '<html><h1>FinOps</h1><p>Placeholder</p></html>'
            self.assertEqual(self.run_check(pages), 1)

    def test_disconnected_inputs_and_submit(self):
        pages = fixtures(); pages[health.ESTIMATORS[0]] = FORM.replace('<form id="finops-scenario-form">', '<form id="finops-scenario-form"></form>')
        self.assertEqual(self.run_check(pages), 1)

    def test_invalid_config(self):
        pages = fixtures(); pages[health.ESTIMATORS[0]] = FORM.replace(CONFIG, '{}')
        self.assertEqual(self.run_check(pages), 1)

    def test_alias_wrong_target_or_link_only(self):
        for source in [ALIAS.replace('/autonomous-ai-agents/', '/'), '<html><a href="/autonomous-ai-agents/">Agents</a></html>']:
            pages = fixtures(); pages['/agents/'] = source
            self.assertEqual(self.run_check(pages), 1)

    def test_soft_404_and_html_as_script(self):
        for path in ['/services/', health.SCRIPT]:
            pages = fixtures(); pages[path] = '<html><h1>404 Page not found</h1></html>'
            self.assertEqual(self.run_check(pages), 1)

    def test_transport_failure_continues_and_exits_nonzero(self):
        messages = []
        def fail(url):
            raise health.ProbeError('HTTP 404: ' + url)
        self.assertEqual(health.check(getter=fail, emit=messages.append), 1)
        self.assertEqual(sum(m.startswith('FAIL ') for m in messages), len(health.ROUTES) + len(health.ESTIMATORS) + 1)

class Origins(unittest.TestCase):
    def test_normalized_default_ports(self):
        self.assertEqual(health.origin('https://ZIONTECHGROUP.com/'),
                         health.origin('https://ziontechgroup.com:443/path'))
        self.assertEqual(health.origin('http://localhost/'), health.origin('http://localhost:80/'))

    def test_internal_rejects_other_scheme_host_and_port(self):
        doc = health.Document('')
        base = 'https://ziontechgroup.com/'
        self.assertTrue(doc.internal('https://ziontechgroup.com:443/discovery/', '/discovery/', base))
        for href in ['http://ziontechgroup.com/discovery/',
                     'ftp://ziontechgroup.com/discovery/',
                     'https://ziontechgroup.com:8443/discovery/',
                     'https://other.test/discovery/']:
            with self.subTest(href=href):
                self.assertFalse(doc.internal(href, '/discovery/', base))

    def test_redirect_rejects_downgrade_and_non_web_scheme_without_network(self):
        handler = health.BoundedRedirects()
        request = Request('https://ziontechgroup.com/agents/')
        for target in ['http://ziontechgroup.com/agents/',
                       'ftp://ziontechgroup.com/agents/',
                       'https://ziontechgroup.com:8443/agents/']:
            with self.subTest(target=target), self.assertRaisesRegex(health.ProbeError, 'left monitored origin'):
                handler.redirect_request(request, None, 302, 'Found', {}, target)
        redirect = handler.redirect_request(request, None, 302, 'Found', {},
                                            'https://ziontechgroup.com:443/autonomous-ai-agents/')
        self.assertEqual(redirect.full_url, 'https://ziontechgroup.com:443/autonomous-ai-agents/')

class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.methods = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                cls.methods.append('GET')
                if self.path in ['/redirect', '/broken', '/loop', '/external']:
                    target = {'/redirect': '/ok', '/broken': '/missing', '/loop': '/loop', '/external': 'https://example.com/'}[self.path]
                    self.send_response(302); self.send_header('Location', target); self.end_headers()
                else:
                    self.send_response(200 if self.path == '/ok' else 404)
                    self.end_headers(); self.wfile.write(b'<html><h1>OK</h1></html>')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def test_get_follows_redirect_and_reads_body(self):
        final, body = health.fetch(self.base + '/redirect')
        self.assertEqual(final, self.base + '/ok'); self.assertIn('<h1>OK', body)
        self.assertTrue(all(m == 'GET' for m in self.methods))

    def test_404_after_redirect_loop_and_cross_origin_fail(self):
        for path in ['/broken', '/loop', '/external']:
            with self.subTest(path=path), self.assertRaises(health.ProbeError):
                health.fetch(self.base + path)

if __name__ == '__main__':
    unittest.main()
