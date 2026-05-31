---
description: A workflow describing the process of updating documentation and AI guidelines.
---

# Documentation Update Workflow

Follow this procedure when performing documentation updates or aligning files with codebase revisions:

1. **Research Changes**: Check recent git commits, pull requests, or conversation logs from the provided reference point.
2. **Compact AI Sub-Guides**: All sub-guides under `.agents/rules/` must remain highly compacted and focused strictly on high-level architectural design principles and *why*.
3. **Move Low-Level Rules to Code**: Highly specific code rules, class parameters, environment variables, and local constraints must reside directly inside the code as code comments rather than in sub-guides.
4. **Mermaid Diagram Isolation**: Only the root `README.md` is permitted to host the system topology Mermaid graph. Do NOT include Mermaid graphs in other sub-guides to avoid redundancy and drift.
5. **Update Indexing**: Ensure all directory index lists (such as inside `doc-style-guide.md` and root `README.md`) are kept synchronized with active rule files.
6. **Plan & Propose**: You must always write an implementation plan and obtain explicit user approval before execution.
