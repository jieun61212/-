# Repository guidance

- This is a Korean legal blog writing MVP. Preserve the user's existing writing workflow.
- Keep writing instructions in config/prompts/, project defaults in project_rules/rules.json, and firm data in lawfirm_profiles/profiles.json.
- Civil rules include the user's original prompt: 1,000–1,500 characters including spaces, 민사전문변호사 in titles, and no fear-provoking language.
- Never mix firm profiles, invent phone numbers, add unsupported judgment facts or guarantee legal outcomes.
- AI mode uses official web search and a separate semantic review in addition to deterministic validation. Do not call offline samples legally verified.
- Do not expose or export a manuscript after required validation fails.
- Do not log credentials, raw PDFs, prompts, sources or manuscript content.
- Each cloud task is already isolated. Use the existing checkout; create a Git worktree only if the user explicitly asks.
- Setup: bash scripts/setup.sh; start: bash scripts/start.sh.
- Required code checks: .venv/bin/python -m unittest discover -v.
- UI changes: also run python -m tests.browser_smoke with available Playwright and Chromium, or the documented dev dependency setup.
- Use temporary databases for tests; do not overwrite user history.

- With a PDF, automatically choose main/subkeywords and topic; never require users to redact the source or confirm privacy. Remove private identities in analysis and manuscripts. Never claim measured search volumes without actual volume data.
