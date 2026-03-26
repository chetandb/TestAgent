# Website Functional Test Agent

A lightweight agent in Python that:
- Accepts a URL input from the user
- Explores the site (crawl links, collect forms, detect buttons)
- Generates functional test cases (page status, link health, form requirements)
- Executes generated test cases and writes a JSON report

## Getting started

1. Create and activate Python virtualenv:
   - `python -m venv .venv`
   - `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (macOS/Linux)

2. Install dependencies:
   - `pip install -r requirements.txt`
   - `playwright install`

3. Run agent:
   - `python test_agent.py --url https://example.com --max-pages 10 --output report.txt --output-format text`
   - `python test_agent.py --url https://example.com --max-pages 10 --output report.html --output-format html`
   - `python test_agent.py --url https://example.com --max-pages 10 --output report.txt --output-format text --smart` (includes form/button interaction tests)

4. Inspect generated report for pass/fail details.

## Behavior

- Crawls up to `--max-pages` within the same host
- Checks HTTP status for pages & links
- Detects forms and required fields
- Detects button presence

## Notes

- This agent is a starting point; expand test generation with domain-specific heuristics, payload strategies, and security checks.
