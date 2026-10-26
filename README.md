# Nemotron Repair Trial

A coding-agent hackathon project for Nebius/NVIDIA model execution, repair cycles,
and independent repair evaluation.

## Current status

The first trial harness makes one bounded Nebius Nemotron request for a synthetic
interval-merging repair and independently verifies the returned candidate.
The deliberately broken baseline remains unchanged for reproducible trials.

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

Python 3.10 or later and Git are required. There are no third-party Python
dependencies. Run all local checks with `sh scripts/check.sh`.

## Run one repair trial

Configure `NEBIUS_API_KEY` in the environment using an existing Token Factory
credential. Optionally set `NEBIUS_MODEL` and `NEBIUS_BASE_URL`; the defaults are
`nvidia/Nemotron-3_5-Lightning` and `https://api.tokenfactory.nebius.com/v1`.
Only the documented Nebius HTTPS hosts are accepted.

Start from a clean committed checkout and use a new evidence directory:

```sh
python3 -B -m agent.run_trial --output ../../evidence-local/nemotron-first-run
```

The harness confirms model availability, then makes one chat-completion request
with a 4,096-token output cap and no automatic retry. The model sees only the
task specification, buggy file, and visible examples. Its only authorized output
is the replacement `task.py` source in a JSON object.

The independent verifier checks the three visible cases, all 2,025 ordered
interval pairs with integer endpoints from -4 through 4, and 24 selected triple
permutations. Its oracle enumerates occupied integer cells rather than using the
candidate's merging algorithm. Every case also checks for input mutation.

Evidence includes the request, sanitized response, model identity and usage,
source and candidate Git revisions, file digests, replayable candidate patch,
baseline and candidate check results, and an `ACCEPT`, `HOLD`, or `UNKNOWN` verdict.
Raw evidence stays outside this repository. Exit code zero means `ACCEPT`;
`HOLD` and `UNKNOWN` return a nonzero exit code.

Candidates run in a separate process after a restricted Python syntax check,
with a wall timeout. This is not an OS security sandbox. Acceptance establishes
correctness only for this finite synthetic check set, not general repair quality.

To replay the verifier independently:

```sh
python3 -B -m verifier.check ../../evidence-local/nemotron-first-run/candidate.py
```

The verifier exits with code 0 for `ACCEPT`, 1 for `HOLD`, and 2 for `UNKNOWN`.

## Continuous integration

Local validation is the primary check path. Hosted GitHub CI is unavailable
under the project cost policy; the retained Actions workflow is manual-only and
does not run automatically on pushes or pull requests.

Run from the repository root:

```sh
sh scripts/check.sh
```

The command checks repository setup and runs the harness tests without network
access or project secrets. The optional manual workflow runs this same script;
it is not required for local readiness.

The local suite verifies candidate scope, independent checking, source integrity,
and patch replay using a test-only response. A live trial requires the separate
run command above; test doubles are never reported as live model evidence.

## License

[MIT](LICENSE). Copyright (c) 2026 Jon M.
