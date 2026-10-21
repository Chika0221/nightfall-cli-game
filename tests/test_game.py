import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

from nightfall import content as c
from nightfall.admin import practice
from nightfall.engine import Engine, Incomplete, MIB
from nightfall.fs import UnsafePath


class GameTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        self.private = Path(self.temp.name) / 'private'
        self.game = Engine(self.root, self.private)

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def send(self, op, **kwargs):
        result = self.game.handle(dict(op=op, **kwargs))
        self.assertTrue(result['ok'], result)
        return result['result']

    def fail(self, op, **kwargs):
        result = self.game.handle(dict(op=op, **kwargs))
        self.assertFalse(result['ok'], result)
        return result['message']

    def to(self, stage):
        practice(self.game, stage)

    def submit_files(self, final=False, **changes):
        files = {'staging/' + name: value for name, value in c.EVIDENCE.items()}
        if final:
            files['staging/directive.txt'] = c.DIRECTIVE.encode()
        names = [p.removeprefix('staging/') for p in files]
        files.update({'staging/manifest.txt': '\n'.join(names) + '\n', 'staging/report.txt': c.REPORT, 'staging/READY': b''})
        files.update(changes)
        self.game.fs.write('home/contractor/submission/evidence.tar.gz', c.archive(files))
        return files

    def clean_cache(self):
        self.game.fs.remove('home/contractor/transfer-cache/old')
        for name in ('part-1.tmp', 'part-2.tmp'):
            self.game.fs.remove('home/contractor/transfer-cache/' + name)

    def test_full_game_with_real_unix_packaging_and_restart(self):
        self.assertFalse(self.game.fs.exists('home/contractor/.contact'))
        self.assertIn('現在地', self.send('current'))
        self.fail('unlock', area='core', answer='ember-204')
        self.fail('check', answer='GLASS')
        self.send('check', answer=' foothold\n')
        self.assertTrue(self.game.fs.exists('home/contractor/.contact'))
        self.send('check', answer='nightjar')
        self.send('check', answer='GLASS')
        log = self.game.fs.read('srv/nightfall/logs/access.log').decode()
        matches = [line for line in log.splitlines() if 'user=aoki ' in line and 'project=GLASS ' in line and 'status=OK' in line]
        self.assertEqual(matches, [c.ACCESS_LINE.strip()])
        self.assertEqual(len(log.splitlines()), 3000)
        self.send('check', answer='/srv/nightfall/backups/glass-maintenance.tar.gz')
        self.fail('unlock', area='archive', answer='CINDER-47')
        self.send('unlock', area='archive', answer='cinder-47')
        self.send('unlock', area='archive', answer='irrelevant')
        self.send('check', answer='NF-204')
        self.send('check', answer='relay-07')
        self.fail('recover')
        self.game.fs.write('home/contractor/recovery/recovery.conf', 'TARGET=relay-07\nOUTPUT=/home/contractor/recovery/output\n')
        self.fail('recover')
        script = self.root / 'home/contractor/recovery/recover.sh'
        script.chmod(0o744)
        self.send('recover')
        self.send('recover')
        self.send('check')
        home = self.root / 'home/contractor'
        # Exercise ordinary Unix tools, rather than generating the accepted tar with our helper.
        subprocess.run(['bash', '-eu', '-c', '''
mkdir -p staging
cp recovery/output/access-evidence.txt staging/
mv staging/access-evidence.txt staging/access.txt
cp recovery/output/report-diff.txt staging/changes.txt
cp recovery/output/destination-counts.txt staging/destinations.txt
cp recovery/output/relay-receipt.txt staging/receipt.txt
printf '%s\\n' access.txt changes.txt destinations.txt receipt.txt > staging/manifest.txt
echo CASE=NF-204 > staging/report.txt
echo TARGET=relay-07 >> staging/report.txt
touch staging/READY
rm transfer-cache/*.tmp
rmdir transfer-cache/old
tar -czf submission/evidence.tar.gz staging
'''], cwd=home, check=True)
        self.send('check')
        self.assertEqual(self.game.state['stage'], 10)
        self.game.close()
        self.game = Engine(self.root, self.private)
        self.assertEqual(self.game.state['stage'], 10)
        self.fail('submit')
        self.send('unlock', area='core', answer='ember-204')
        self.fail('submit')
        subprocess.run(['bash', '-eu', '-c', '''
cp "$1/srv/nightfall/core/directive.txt" staging/directive.txt
echo directive.txt >> staging/manifest.txt
tar -czf submission/evidence.tar.gz -C . staging
''', 'test', str(self.root)], cwd=home, check=True)
        self.assertIn('MISSION COMPLETE', self.send('submit'))
        before = self.game.state.copy()
        self.send('submit')
        self.send('check')
        self.send('unlock', area='core', answer='ignored')
        self.assertEqual(self.game.state, before)
        self.assertEqual(self.game.state['cleared'], list(range(1, 11)))

    def test_s8_reset_preserves_previous_evidence(self):
        self.to(8)
        original = self.game.fs.read(c.OUT + '/access-evidence.txt')
        self.game.fs.write('home/contractor/recovery/recovery.conf', 'TARGET=relay-07\nOUTPUT=/home/contractor/recovery/output\n')
        (self.root / 'home/contractor/recovery/recover.sh').chmod(0o744)
        self.send('recover')
        confirmation = self.send('reset')
        self.assertIn('recover.sh', confirmation['confirm'])
        self.send('reset', confirmed=True)
        self.assertFalse(self.game.state['collected'])
        self.assertFalse(self.game.fs.exists(c.OUT + '/.keys/final.key'))
        self.assertEqual(self.game.fs.read(c.OUT + '/access-evidence.txt'), original)
        self.assertEqual(self.game.fs.info('home/contractor/recovery/recover.sh').st_mode & 0o777, 0o644)

    def test_s9_reset_preserves_key_and_originals(self):
        self.to(9)
        key = self.game.fs.read(c.OUT + '/.keys/final.key')
        self.clean_cache()
        self.submit_files()
        self.send('reset', confirmed=True)
        self.assertEqual(self.game.fs.read(c.OUT + '/.keys/final.key'), key)
        self.assertFalse(self.game.fs.exists('home/contractor/submission/evidence.tar.gz'))
        self.assertEqual(len(self.game.fs.read('home/contractor/transfer-cache/part-1.tmp')), MIB)
        self.assertEqual(self.game.state['cleared'], list(range(1, 9)))

    def test_s10_reset_restores_accepted_s9_archive_even_without_staging(self):
        self.to(9)
        self.clean_cache()
        self.submit_files()
        # S9 is based on submitted contents, not on the choice of packaging tools.
        self.send('check')
        self.send('unlock', area='core', answer='ember-204')
        self.submit_files(final=True)
        self.send('reset', confirmed=True)
        self.assertTrue(self.game.state['core'])
        self.assertFalse(self.game.fs.exists('home/contractor/staging/directive.txt'))
        self.assertEqual(self.game.fs.read('home/contractor/staging/report.txt'), c.REPORT)
        self.game.validate_submission()
        self.fail('submit')

    def test_report_overwrite_failure_then_repair(self):
        self.to(9)
        self.clean_cache()
        self.submit_files(**{'staging/report.txt': b'CASE=NF-204\n'})
        self.assertIn('TARGET', self.fail('check'))
        self.submit_files(**{'staging/report.txt': c.REPORT.rstrip(b'\n')})
        self.send('check')

    def test_manifest_crlf_and_order_are_accepted(self):
        self.to(9)
        self.clean_cache()
        self.submit_files(**{'staging/manifest.txt': '\r\n'.join(reversed(c.EVIDENCE)) + '\r\n'})
        self.send('check')

    def test_size_and_missing_originals(self):
        self.to(9)
        self.submit_files()
        self.assertIn('old', self.fail('check'))
        self.game.fs.remove('home/contractor/transfer-cache/old')
        self.assertIn('1 MiB', self.fail('check'))
        self.clean_cache()
        self.game.fs.remove(c.OUT + '/report-diff.txt')
        self.assertIn('環境エラー', self.fail('check'))

    def test_fake_receipt_is_insufficient(self):
        self.to(8)
        self.game.fs.write('home/contractor/recovery/recovery.conf', 'TARGET=relay-07\nOUTPUT=/home/contractor/recovery/output\n')
        (self.root / 'home/contractor/recovery/recover.sh').chmod(0o744)
        self.game.fs.write(c.OUT + '/relay-receipt.txt', c.RECEIPT)
        self.assertIn('記録されていません', self.fail('check'))

    def test_config_is_data_not_executable(self):
        self.to(8)
        marker = Path(self.temp.name) / 'SHOULD-NOT-EXIST'
        self.game.fs.write('home/contractor/recovery/recovery.conf', f'TARGET=$(touch {marker})\nOUTPUT=/home/contractor/recovery/output\n')
        self.fail('recover')
        self.assertFalse(marker.exists())
        self.game.fs.write('home/contractor/recovery/recovery.conf', 'TARGET=relay-07\nTARGET=relay-07\nOUTPUT=/home/contractor/recovery/output\n')
        self.fail('recover')

    def test_transition_interruption_can_be_retried(self):
        self.to(4)
        original = self.game.fs.write
        def broken(path, data, *args, **kwargs):
            if path.endswith('access-evidence.txt'):
                raise OSError('simulated disk failure')
            return original(path, data, *args, **kwargs)
        with mock.patch.object(self.game.fs, 'write', side_effect=broken):
            self.fail('check', answer='glass-maintenance.tar.gz')
        self.assertEqual(self.game.state['stage'], 4)
        self.game.close()
        self.game = Engine(self.root, self.private)
        self.assertEqual(self.game.state['stage'], 5)
        self.assertEqual(self.game.fs.read(c.OUT + '/access-evidence.txt'), c.EVIDENCE['access.txt'])
        self.assertEqual(self.game.state['cleared'], [1, 2, 3, 4])

    def test_reset_is_resumable_and_operator_rebuild_restores_home(self):
        self.to(9)
        self.game.state['pending'] = {'kind': 'reset'}
        self.game.save()
        self.game.fs.remove('home/contractor/transfer-cache')
        self.game.close()
        self.game = Engine(self.root, self.private)
        self.assertTrue(self.game.fs.exists('home/contractor/transfer-cache/old'))
        self.game.fs.remove('home/contractor')
        self.game.state['pending'] = {'kind': 'rebuild'}
        self.game.save()
        self.game.resume()
        self.assertEqual(self.game.fs.read(c.OUT + '/.keys/final.key'), b'ember-204\n')

    def test_hints_replay_and_stale_answers(self):
        self.send('hint')
        self.send('hint')
        self.send('hint')
        self.send('hint')
        self.assertEqual(len(self.game.state['hints']['1']), 3)
        self.send('check', answer='foothold', stage=1)
        self.fail('check', answer='nightjar', stage=1)
        self.fail('replay', number=10)
        before = self.game.state.copy()
        self.send('replay', number=1)
        self.assertEqual(self.game.state, before)
        self.assertEqual(json.loads((self.private / 'replay-request.json').read_text()), {'stage': 1})

    def test_published_modes_are_correct_under_private_service_umask(self):
        old = os.umask(0o077)
        try:
            self.game.fs.write('home/contractor/recovery/recover.sh', c.RECOVER, 0o644)
            self.game.fs.mkdir('home/contractor/new-directory')
        finally:
            os.umask(old)
        self.assertEqual(self.game.fs.info('home/contractor/recovery/recover.sh').st_mode & 0o777, 0o644)
        self.assertEqual(self.game.fs.info('home/contractor/new-directory').st_mode & 0o777, 0o755)

    def test_public_symlinks_never_reach_private_or_outside_files(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        marker = outside / 'secret'
        marker.write_text('untouched')
        self.game.fs.remove('home/contractor/inbox')
        (self.root / 'home/contractor/inbox').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.game.fs.write('home/contractor/inbox/secret', 'bad')
        with self.assertRaises(OSError):
            self.game.fs.read('home/contractor/inbox/secret')
        self.send('reset', confirmed=True)
        self.assertEqual(marker.read_text(), 'untouched')
        self.assertFalse((self.root / 'home/contractor/inbox').is_symlink())
        (self.root / 'home/contractor/link').symlink_to(marker)
        with self.assertRaises(OSError):
            self.game.fs.read('home/contractor/link')

    def test_all_practice_stages_have_start_snapshots(self):
        self.game.close()
        for n in range(1, 11):
            with self.subTest(n=n), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / 'root'
                root.mkdir()
                game = Engine(root, Path(folder) / 'private')
                practice(game, n)
                self.assertEqual(game.state['stage'], n)
                self.assertEqual(game.state['cleared'], list(range(1, n)))
                self.assertTrue(game.load_snapshot(n))
                game.close()
        self.game = Engine(self.root, self.private)


class ArchiveTest(unittest.TestCase):
    def tar(self, members):
        import gzip
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as tf:
            for member, data in members:
                tf.addfile(member, io.BytesIO(data) if data else None)
        return gzip.compress(buf.getvalue())

    def test_reject_unsafe_paths_types_duplicates_and_extra_dirs(self):
        for name in ['/etc/passwd', '../escape', 'staging/../../escape', 'staging/../access.txt', 'other/file', 'staging/deep/file', 'staging\\file']:
            with self.subTest(path=name):
                member = tarfile.TarInfo(name)
                with self.assertRaises(Incomplete):
                    Engine.archive_members(self.tar([(member, b'')]))
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE]:
            with self.subTest(kind=kind):
                member = tarfile.TarInfo('staging/access.txt')
                member.type = kind
                member.linkname = '/etc/passwd'
                with self.assertRaises(Incomplete):
                    Engine.archive_members(self.tar([(member, b'')]))
        member = tarfile.TarInfo('staging/access.txt')
        with self.assertRaises(Incomplete):
            Engine.archive_members(self.tar([(member, b''), (member, b'')]))
        member = tarfile.TarInfo('staging/extra')
        member.type = tarfile.DIRTYPE
        with self.assertRaises(Incomplete):
            Engine.archive_members(self.tar([(member, b'')]))

    def test_bombs_limits_corruption_and_entry_count(self):
        member = tarfile.TarInfo('staging/access.txt')
        member.size = 8 * MIB + 1
        with self.assertRaises(Incomplete):
            Engine.archive_members(self.tar([(member, b'x' * member.size)]))
        with self.assertRaises(Incomplete):
            Engine.archive_members(b'x' * (MIB + 1))
        with self.assertRaises(Incomplete):
            Engine.archive_members(b'not a gzip')
        members = [(tarfile.TarInfo(f'staging/item-{n}'), b'') for n in range(101)]
        with self.assertRaises(Incomplete):
            Engine.archive_members(self.tar(members))


if __name__ == '__main__':
    unittest.main()
