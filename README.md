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

The `validate-scaffold` job in `.github/workflows/ci.yml` runs on pushes,
pull requests, and manual dispatch. It checks that the README and MIT license
are present and nonempty, and that the scaffold directories exist. It uses a
GitHub-hosted Ubuntu runner with read-only repository access and requires no
project secrets.

Run the same checks locally from the repository root:

```sh
set -eu
test -s README.md
test -s LICENSE
grep -qx 'MIT License' LICENSE
for directory in agent providers/nebius workspace verifier evaluation; do
  test -d "$directory"
done
printf 'Scaffold checks passed.\n'
```

These checks validate repository setup. Implementation and evaluation checks
will be added as the project develops.

## License

[MIT](LICENSE). Copyright (c) 2026 Jon M.
