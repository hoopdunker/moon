# Moon

Multi-agent security orchestration system. Coordinator LLM selects 
runbooks and resources, stateless agents execute steps.

## Principles
- No agent frameworks (no LangChain, no CrewAI, nothing)
- Use anthropic SDK directly for all LLM calls
- All agent state is passed explicitly, never persisted between steps
- Tools use mock responses until explicitly told to implement real ones
- Runbooks are dumb — just natural language steps
- Coordinator is smart — it reasons about what each step needs