# ARIA agent pack

Everything an AI coding agent or developer needs to start building the voice-powered office assistant.

Start with `AGENTS.md`.

What is in the pack:

- `docs/PRD.md` product requirements
- `docs/TECH_SPEC.md` technical specification
- `docs/ROADMAP.md` phases, gates and the parallel work map
- `docs/API_CONTRACT.md` events and REST between UI and agent
- `docs/PROMPTS.md` prompt templates for the model
- `docs/TESTING.md` named unit tests, e2e scenarios and evaluations
- `docs/CICD.md` GitHub workflows
- `docs/DECISIONS.md` running decision log
- `agents/backend-ai.md`, `agents/frontend.md` role guides
- A small working skeleton: contract models, a mock agent, a tool base class, a pure router function and a gateway with auth and a spending cap, all with passing tests
- `.github/workflows` ready to run
- `tests/e2e/scenarios` starter scenario files

## Quick start

```
git init && git add . && git commit -m "Initial pack"
cd services/agent && pip install -e ".[dev]" && pytest tests/unit
cd ../gateway && pip install -e ".[dev]" && pytest tests/unit
cd ../.. && python scripts/gen_contract.py
cd services/agent && python -m agent.mock --scenario policy_question
```

Then start a coding agent in the repo folder. It will ask which role you are working as.
