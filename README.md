# My-Agent

LangGraph-based agent project.

## Project Structure

```
src/
├── agents/       # Agent definitions and graph
├── tools/        # Tool calling implementations
├── memory/       # Memory and state management
├── storage/      # Persistence layer
└── guardrails/   # Safety and filtering
```

## Development Rules

1. `main` branch is always runnable
2. Each capability = one `feature/*` branch
3. LangGraph nodes are developed separately (agent / tools / memory / router)
4. Tool Calling is encapsulated independently, not in agent core
5. All changes must be reversible (clean commits + runnable before merge)
