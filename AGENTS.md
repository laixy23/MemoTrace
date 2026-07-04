# TraceWiki Agent Rules

## Knowledge Organization

- Preserve user uploads under `data/raw/`.
- Write AI-organized long-term knowledge under `data/wiki/`.
- Put unverified web or model-generated additions under `data/staging/`.
- Do not overwrite raw files.
- Every wiki card must include a source section.

## Evidence Rules

- Answers must cite stored evidence whenever possible.
- If evidence is weak or missing, say so explicitly.
- Do not present unstored web knowledge as part of the user's private knowledge base until it is confirmed.

## Image Rules

- Use OCR for exact text extraction.
- Use VLM for visual layout, chart, scene, and context understanding.
- Store OCR text and VLM summary separately, then combine them into a Markdown image knowledge card.

## Personalization Rules

- User preferences may affect format, length, and examples.
- User preferences must not change facts.
- Users must be able to inspect or edit the preference profile.

