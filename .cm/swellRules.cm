# -*- mode: yaml -*-

manifest:
  version: 1.0

automations:
  ai_code_review:
    on:
      - pr_created
      - commit
    if:
      - {{ pr.draft == false }}
    run:
      - action: code-review@v1
