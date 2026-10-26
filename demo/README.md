# Reproduce the recorded Nemotron repair

For maintainers reviewing generated patches, this demo compares a broken
baseline, an authored visible-passing overfit control, and a real saved repair.
It replays a real Nebius Token Factory response from October 25,
2026 Pacific time. It does not simulate a fresh model call. Python 3.10 or later
and Git are the only requirements; no API key, installation, or project secrets
are needed.

## Run from a clone or source archive

From the extracted project directory:

```sh
sh scripts/check.sh
python3 -B -m demo.replay --output /tmp/nemotron-demo-first
```

Choose a new output directory for every run. Exit zero means that the replay
reproduced both the expected baseline rejection and candidate acceptance.
`review.md`, `transcript.txt`, the replayed source, and complete verification reports are saved
in the chosen directory.

## What the demo checks

1. Check the evidence and trusted verifier file digests in `manifest.json`.
2. Match the candidate bytes to the returned `task.py` in the response summary.
3. Confirm that the unchanged baseline returns HOLD: 2 of 3 visible cases and
   1,785 of 2,049 independent cases pass.
4. Check an explicitly authored overfit control: all three visible examples pass,
   but independent checking returns HOLD with an overlapping-interval counterexample.
5. Apply the saved patch to a temporary baseline copy using Git.
6. Match the patched file digest to the captured candidate.
7. Run the independent verifier again: all 3 visible and 2,049 independent
   cases pass, including input-preservation checks.
8. Recheck the same saved candidate on 321 longer-list cases added after the live
   model run: lengths 4 through 19, deterministic seed 20261025. All pass. This
   extension is separate from the original recorded 2,049-case result.

The overfit control is authored adversarial input, not a second Nemotron output.
The review report makes the maintainer decision concrete: HOLD the visible-green
control, then inspect the exact patch and ACCEPT the captured repair on the
bounded checks.

## Captured evidence

`evidence/recorded-run.json` records the provider, model, response identifier,
source and candidate revisions, token usage, and measured case counts.
`request.json` is the captured synthetic task request. `response-summary.json`
retains the model identity, token usage, and returned candidate; the full raw
response and reasoning remain in the local program evidence store.

The recorded model is `nvidia/Nemotron-3_5-Lightning`, served by Nebius Token
Factory. The run used 374 prompt tokens and 2,943 completion tokens.

The fixture and verifier were newly authored for this project. The model saw the
specification and visible tests; the independent checker uses a different
occupied-cell algorithm. This is one successful synthetic repair demonstration,
not a comparative model benchmark or a proof for arbitrary interval inputs.

## Make a new live attempt

See the repository README for the separate `agent.run_trial` command and Nebius
environment setup. Live inference is optional for replaying this demo.
