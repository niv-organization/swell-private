# -*- mode: yaml -*-

manifest:
  version: 1.0

automations:
  ai_code_review:
    if:
      - true
    run:
      - action: code-review@v1
