# AppMentor Prompt Registry

This folder contains all AI prompts used by AppMentor agents.
Prompts are stored as YAML files — separate from Python code.

## How to update a prompt (no Python knowledge needed)

1. Open the relevant .yaml file in any text editor
2. Edit the `system` or `user_template` section
3. Update the `version` number (e.g. 1.2 → 1.3)
4. Add an entry to `changelog` with date and what changed
5. Record what you tested it against in `tested_on`
6. Save the file — changes take effect on next run

## How to test a prompt before full ingestion

Copy the system and user_template text into Claude.ai chat.
Replace {placeholders} with a real code sample.
Read the output and judge quality.
Adjust and repeat until satisfied.
Then update the yaml file and run with --max-functions 20
before triggering full ingestion.

## Files in this folder

| File | Language | Status |
|------|----------|--------|
| commentary_python.yaml | Python/ERPNext | Tested and approved |
| commentary_abap.yaml | SAP ABAP | Placeholder — needs testing |
| commentary_fiori.yaml | SAP Fiori UI5 | Placeholder — needs testing |
