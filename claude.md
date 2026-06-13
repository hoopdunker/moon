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

## Infrastructure
Terraform code has been moved to `/Users/chiraag/dev/infra/` for reuse across projects.
- Development: `cd ../infra/apps/moon && terraform plan`
- State backend: S3 (`moon-tfstate-489922706493`), key: `moon/terraform.tfstate`
- To apply changes: work in infra directory, never from moon