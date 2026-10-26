import json
from pathlib import Path
import shutil
import tempfile
import unittest

from demo.replay import replay, validate_bundle

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def copy_bundle(self, destination):
        manifest = json.loads((ROOT / 'demo/manifest.json').read_text())
        for name in ['demo/manifest.json', *manifest['files']]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_offline_replay_reproduces_recorded_candidate_and_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            result = replay(Path(temp) / 'output')
            self.assertEqual(result['acceptance_state'], 'ACCEPT')
            self.assertTrue(result['patch_matches_recorded_candidate'])
            self.assertEqual(result['baseline']['targeted'], {'passed': 2, 'failed': 1})
            self.assertEqual(result['candidate']['regression'], {'passed': 2049, 'failed': 0})
            self.assertEqual(result['mode'], 'offline_recorded_replay')
            self.assertTrue((Path(temp) / 'output/transcript.txt').is_file())

    def test_demo_exposes_authored_visible_passing_overfit(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'output'
            result = replay(output)
            control = result['overfit_control']
            self.assertEqual(control['origin'], 'authored_negative_control')
            self.assertEqual(control['acceptance_state'], 'HOLD')
            self.assertEqual(control['targeted'], {'passed': 3, 'failed': 0})
            self.assertGreater(control['regression']['failed'], 0)
            self.assertEqual(control['counterexample']['input'], [[1, 3], [2, 4]])
            self.assertEqual(control['counterexample']['expected'], [[1, 4]])
            self.assertEqual(result['candidate']['extended']['failed'], 0)
            self.assertIn('AUTHORED OVERFIT CONTROL', (output / 'transcript.txt').read_text())

    def test_tampered_candidate_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'source'
            self.copy_bundle(root)
            candidate = root / 'demo/evidence/candidate.py'
            candidate.write_text('raise RuntimeError("must not run")\n')
            with self.assertRaisesRegex(ValueError, 'digest'):
                replay(Path(temp) / 'output', root=root)
            self.assertFalse((Path(temp) / 'output').exists())

    def test_missing_trusted_checker_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'source'
            self.copy_bundle(root)
            (root / 'verifier/check.py').unlink()
            with self.assertRaises(ValueError):
                validate_bundle(root)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'existing'
            output.mkdir()
            marker = output / 'important.txt'
            marker.write_text('keep')
            with self.assertRaises(FileExistsError):
                replay(output)
            self.assertEqual(marker.read_text(), 'keep')

    def test_replay_from_source_archive_needs_no_git_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'archive'
            self.copy_bundle(root)
            result = replay(Path(temp) / 'output', root=root)
            self.assertEqual(result['acceptance_state'], 'ACCEPT')
            self.assertFalse((root / '.git').exists())


if __name__ == '__main__':
    unittest.main()
