---
name: website-test-agent
version: 1.0.0
description: "Crawl a website by URL, generate functional test cases, run checks, and produce a JSON report."
author: "Test Architect"
entrypoint: "python test_agent.py --url {url} --max-pages {max_pages} --output {output}"
inputs:
  - name: url
    type: string
    required: true
    description: "Root URL to test"
  - name: max_pages
    type: integer
    required: false
    default: 10
    description: "Maximum pages to crawl"
  - name: output
    type: string
    required: false
    default: report.json
    description: "Output report path"
outputs:
  - name: report
    type: file
    description: "Generated JSON test report"
---

# Website Test Agent

Use this agent to run full workflow testing against a site.

## Execution
1. Ensure Python virtualenv is active
2. `pip install -r requirements.txt`
3. `python -m playwright install`
4. Run with:
   `python test_agent.py --url <URL> --max-pages <N> --output <report.json>`

## Sample invocation

`python test_agent.py --url https://example.com --max-pages 5 --output report_example.json`
