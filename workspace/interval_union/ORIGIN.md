# Interval union fixture origin

This synthetic task, its specification, visible cases, and independent checker
were newly authored for Nemotron Repair Trial on October 25, 2026. No private
upstream source or external benchmark task was copied into the fixture.

The baseline deliberately shrinks an interval when a later interval is nested
inside it. Keep that baseline unchanged; model candidates belong in each run's
separate workspace. The reference implementation in the harness unit tests
tests the checker and is never supplied as the model's candidate.

The repository's MIT license covers these files.
