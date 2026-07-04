# Borrowed Ideas From `ailab-hackathon`

This project inspected the sibling `ailab-hackathon` repository and kept only the parts that strengthen TraceWiki's core story.

## Adopted

### SourceSpan Evidence Layer

`ailab-hackathon` stores document chunks for retrieval. TraceWiki already has Wiki Cards, so copying a `documents + chunks` model would duplicate storage. Instead, TraceWiki adds `source_spans`:

```text
Wiki Card = durable human-readable knowledge
SourceSpan = precise evidence for retrieval and citation
```

### Evidence Work Graph

`ailab-hackathon` has a task/evidence/entity/draft graph. TraceWiki adapts this as:

```text
Question -> EvidenceSpan -> WikiCard -> Source -> Answer
```

This makes traceability visible without adding a full React graph frontend.

### System Operation Logs

`ailab-hackathon` records upload, retrieval, graph, and generation events. TraceWiki adds `system_logs` for:

- upload received
- source saved
- wiki card created
- retrieval completed
- answer generated
- health review completed
- preference distilled

## Not Adopted

### Full Session System

TraceWiki does not yet need full session persistence. The immediate value is evidence and operation visibility.

### Keyword Entity Graph

Keyword-to-entity nodes look good visually, but they are less important than claim/evidence/source traceability for this project.

### Duplicate Chunk Table

TraceWiki uses `source_spans`, not a separate `documents/chunks` knowledge model, to avoid parallel truth sources.

