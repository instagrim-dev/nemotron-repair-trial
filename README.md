# Nemotron Repair Trial

A coding-agent hackathon project for Nebius/NVIDIA model execution, repair cycles,
and independent repair evaluation.

## Current status

This repository contains the initial project scaffold.
The agent, model provider integration, verifier, and evaluation runs are still
to be implemented.

## Repository layout

| Directory | Purpose |
| --- | --- |
| `agent/` | Coding-agent repair loop |
| `providers/nebius/` | Nebius model provider integration |
| `workspace/` | Task workspaces and candidate changes |
| `verifier/` | Independent checks of candidate repairs |
| `evaluation/` | Evaluation runs and matched comparisons |

## Get started

```sh
git clone https://github.com/instagrim-dev/nemotron-repair-trial.git
cd nemotron-repair-trial
```

There are no application dependencies or runnable application yet.

## Continuous integration

Local validation is the primary check path. Hosted GitHub CI is unavailable
under the project cost policy; the retained Actions workflow is manual-only and
does not run automatically on pushes or pull requests.

Run from the repository root:

```sh
sh scripts/check.sh
```

The command checks the README, MIT license, and scaffold directories without
network access or project secrets. The optional manual workflow runs this same
script; it is not required for local readiness.

These checks validate repository setup. Implementation and evaluation checks
will be added as the project develops.

## License

[MIT](LICENSE). Copyright (c) 2026 Jon M.
