# Evaluations

| Task | Entry point |
| --- | --- |
| Verify the fictional qualification fixture offline | [D1 fixture guide](fixtures/development/D1-qualification/README.md) |
| Check the Decisions benchmark offline or audit saved PUB retrieval | [PUB screening guide](fixtures/development/PUB-screening/README.md) |

The API tests use the D1 inputs and mock responses under `fixtures/`. The [answer key](answer-keys/D1-qualification.json) is for scoring and must stay out of model input.

Historical milestone reports and retired runners are in the local `evals/archive/m1/` directory. Put generated reports in the ignored `output/` directory. The app and tests use the ignored `evals/runs/local/` directory for local credentials and runtime artifacts.
