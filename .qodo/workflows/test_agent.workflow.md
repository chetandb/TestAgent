---
name: website-test-agent-workflow
version: 1.0.0
description: "Workflow to execute the website test agent and collect report output."
steps:
  - name: run-test-agent
    agent: website-test-agent
    input:
      url: "{{input.url}}"
      max_pages: "{{input.max_pages}}"
      output: "{{input.output}}"
outputs:
  - name: report
    type: file
    value: "{{steps.run-test-agent.output.report}}"
---

# Test Agent Workflow

This workflow runs the `website-test-agent` agent with a URL and stores report output.
