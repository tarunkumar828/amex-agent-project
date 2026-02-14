### Diagrams (Mermaid)

This folder contains the architecture and flow diagrams for the UCAOA codebase in **Mermaid** format.

#### How to view

- **GitHub**: Mermaid renders automatically in Markdown code blocks.
- **Cursor / VS Code**: use a Mermaid preview extension (or Markdown preview if supported).
- **mermaid-cli (mmdc)**: use the `.mmd` files in this folder (they contain **raw Mermaid**, no Markdown).

#### Files

- `architecture.md`: system-level architecture (boundaries + components)
- `architecture.mmd`: raw Mermaid for CLI/renderers that don’t parse Markdown
- `orchestration_graph.md`: LangGraph state machine flow
- `orchestration_graph.mmd`: raw Mermaid
- `request_flow_sequence.md`: end-to-end request execution sequence
- `request_flow_sequence.mmd`: raw Mermaid
- `hitl_resume_sequence.md`: HITL interrupt resume sequence
- `hitl_resume_sequence.mmd`: raw Mermaid

