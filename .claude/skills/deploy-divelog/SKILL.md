---
name: deploy-divelog
description: Parse the newest Shearwater export and publish the dive log viewer by running scripts/deploy.sh.
argument-hint: "[--dry-run | --skip-parse] [DB]"
disable-model-invocation: true
allowed-tools: Bash(scripts/deploy.sh:*)
---

Run the deploy script from the repository root, passing through any arguments the user gave:

```bash
scripts/deploy.sh $ARGUMENTS
```

The script parses the newest `.db` in `raw/` (unless `--skip-parse`, `--dry-run`, or a specific DB path changes that), rsyncs `web/` and `data/` to the divelog server, and checks that `data/dives.json` is served.

Then report the outcome briefly:
- On success, give the URL from the `==> Done:` line and how many files rsync changed (lines from `--itemize-changes`), or say nothing changed.
- On a dry run, summarize what would be sent or deleted.
- On failure, show the relevant error output and which step failed (parse, rsync, or the HTTP check). Do not retry or change anything without asking.
