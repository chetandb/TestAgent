import unittest
from unittest.mock import patch
from test_agent import WebsiteTestAgent

class DummyResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

class TestWebsiteTestAgent(unittest.TestCase):
    def test_normalize_and_start_url(self):
        a = WebsiteTestAgent("example.com")
        self.assertTrue(a.start_url.startswith("https://"))
        # calling _normalize_url on an http url preserves path
        self.assertEqual(a._normalize_url("http://example.com/path"), "http://example.com/path")

    def test_same_domain(self):
        a = WebsiteTestAgent("https://example.com")
        self.assertTrue(a._same_domain("https://example.com/about"))
        self.assertFalse(a._same_domain("https://otherdomain.com/"))

    def test_generate_test_cases_from_explored_pages(self):
        a = WebsiteTestAgent("https://example.com")
        a.explored_pages = {
            "https://example.com/": {
                "links": ["https://example.com/about", "https://other.com/"],
                "forms": [{"action": "/submit", "method": "post", "fields": [{"name":"email","type":"email","required":True}] }],
                "buttons": [{"text": "Click me"}],
            }
        }
        cases = a.generate_test_cases()
        # should at least include load-start-url and one page-status and an internal link and a form and buttons case
        types = {c['type'] for c in cases}
        self.assertIn('load', types)
        self.assertIn('http-status', types)
        self.assertIn('link-check', types)
        self.assertIn('form-required', types)
        self.assertIn('buttons-existence', types)

    @patch('test_agent.requests.get')
    def test_run_test_cases_http_checks(self, mock_get):
        # simulate various status codes
        mock_get.return_value = DummyResponse(200)
        a = WebsiteTestAgent("https://example.com")
        cases = [
            {"id": "c1", "description": "load", "type": "load", "target": "https://example.com/"},
            {"id": "c2", "description": "link", "type": "link-check", "target": "https://example.com/about"},
            {"id": "c3", "description": "forbidden", "type": "http-status", "target": "https://example.com/forbidden"},
        ]
        a.run_test_cases(cases)
        self.assertEqual(len(a.test_results), 3)
        for r in a.test_results:
            self.assertIn(r['status'], ['passed', 'failed', 'error'])

    def test_format_text_report(self):
        a = WebsiteTestAgent("https://example.com")
        a.test_results = [
            {"id":"t1","status":"passed","description":"ok","target":"https://example.com/","passed":True,"details":None}
        ]
        summary = a.report()
        text = a.format_text_report(summary)
        self.assertIn("Website Test Report for:", text)
        self.assertIn("Pages explored:", text)

if __name__ == '__main__':
    unittest.main()
