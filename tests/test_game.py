import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from nightfall import content as c
from nightfall.admin import practice
from nightfall.engine import Engine, Incomplete, MIB


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

    def clean_cache(self):
        self.game.fs.remove(c.HOME + '/transfer-cache/old')
        for name in ('part-1.tmp', 'part-2.tmp'):
            self.game.fs.remove(c.HOME + '/transfer-cache/' + name)

    def decoy(self, **changes):
        files = {'staging/plan.txt': c.PLAN, 'staging/READY': b''}
        files.update(changes)
        self.game.fs.write(c.HOME + '/submission/decoy.tar.gz', c.archive(files))

    def submit_files(self, **changes):
        evidence = dict(c.EVIDENCE, **{'directive.txt': c.DIRECTIVE.encode()})
        files = {'staging/' + name: body for name, body in evidence.items()}
        files.update({'staging/manifest.txt': '\n'.join(evidence) + '\n',
                      'staging/report.txt': c.REPORT, 'staging/READY': b''})
        files.update(changes)
        self.game.fs.write(c.HOME + '/submission/evidence.tar.gz', c.archive(files))
        return files

    def restart(self):
        self.game.close()
        self.game = Engine(self.root, self.private)

    def shell(self, script):
        return subprocess.run(['bash', '-eu', '-c', script, 'playtest', str(self.root)],
                              cwd=self.root / c.HOME, text=True, capture_output=True, check=True)

    def test_full_investigation_with_real_unix_tools_and_restart(self):
        current = self.send('current')
        for spoiler in ('[S1', '密告', '三人', '次は', '回答'):
            self.assertNotIn(spoiler, current)
        result = self.shell("grep -R 'N-000' \"$1/srv/nightfall/public/facilities\"")
        self.assertEqual(len(result.stdout.splitlines()), 3)
        self.send('fetch', ref='NOAH-R7')
        self.send('fetch', ref='BKP-0210')
        self.shell('mkdir -p work/backup\ntar -xzf "$1/srv/nightfall/backups/night-maintenance.tar.gz" -C work/backup')
        self.assertIn('ARCHIVE_PASSWORD=cinder-47', (self.root / c.HOME / 'work/backup/maintenance/config/archive.env').read_text())
        self.send('unlock', area='archive', answer=c.PASSWORD)
        self.send('fetch', ref='D-204')  # Independent documents can be explored out of order.
        self.send('fetch', ref='MAIL-0216')
        diff = subprocess.run(['diff', '-u', str(self.root / c.BASE / 'vault/reports/before.txt'),
                               str(self.root / c.BASE / 'vault/reports/after.txt')], text=True, capture_output=True)
        self.assertEqual(diff.returncode, 1)
        self.assertIn('-TERMINAL=E5-03', diff.stdout)
        self.send('fetch', ref='TERM-E5-03')
        count = self.shell('sort "$1/srv/nightfall/vault/net/destinations.log" | uniq -c | sort -nr')
        self.assertEqual(count.stdout.splitlines()[0].split(), ['24', 'liaison-04'])
        self.send('fetch', ref='LIAISON-04')
        self.assertEqual(self.game.state['stage'], 8)
        self.fail('recover')
        self.shell("printf '%s\\n' TARGET=liaison-04 OUTPUT=/home/contractor/recovery/output > recovery/recovery.conf\nchmod u+x recovery/recover.sh")
        self.send('recover')
        self.assertIn('ren.txt', self.send('current'))
        self.fail('unlock', area='core', answer=c.KEY)
        self.shell("""
printf '%s\\n' SOURCE=C-17 MEETING_POINT=EAST-4 MEETING_TIME=03:10 > staging/plan.txt
touch staging/READY
rm transfer-cache/*.tmp
rmdir transfer-cache/old
tar -czf submission/decoy.tar.gz staging
""")
        self.send('check')
        self.restart()
        self.assertEqual(self.game.state['stage'], 10)
        self.assertEqual(self.game.fs.read(c.OUT + '/.keys/final.key'), (c.KEY + '\n').encode())
        self.send('unlock', area='core', answer=c.KEY)
        self.shell("""
rm staging/plan.txt
cp "$1/srv/nightfall/records/mail/0216.txt" staging/meeting.txt
cp "$1/srv/nightfall/records/terminals/E5-03.txt" staging/assignment.txt
cp "$1/srv/nightfall/records/dependents/D-204.txt" staging/dependent.txt
cp recovery/output/orders.txt staging/orders.txt
cp "$1/srv/nightfall/core/directive.txt" staging/directive.txt
printf '%s\\n' meeting.txt assignment.txt dependent.txt orders.txt directive.txt > staging/manifest.txt
printf '%s\\n' VEHICLE=MX-5 GATE=WEST-2 DEPARTURE=03:26 PASSENGERS=R-12,R-31,R-08,D-204 > staging/report.txt
tar -czf submission/evidence.tar.gz -C . staging
""")
        self.assertIn('乗員数: 5', self.send('submit'))
        self.assertEqual(self.game.fs.read(c.HOME + '/inbox/last-message.txt'), c.COMPLETE.encode())
        before = json.dumps(self.game.state, sort_keys=True)
        self.send('submit')
        self.send('check')
        self.send('unlock', area='core', answer='ignored')
        self.assertEqual(json.dumps(self.game.state, sort_keys=True), before)
        self.assertEqual(self.game.state['cleared'], list(range(1, 11)))

    def test_fetch_permissions_idempotence_and_no_quiz(self):
        self.fail('fetch', ref='../private')
        self.fail('fetch', ref=[])
        self.fail('fetch', ref='D-204')
        self.fail('unlock', area='archive', answer=c.PASSWORD)
        self.send('check', answer='foothold')
        self.assertEqual(self.game.state['stage'], 1)
        self.send('fetch', ref='BKP-0210')
        self.send('fetch', ref='BKP-0210')
        self.assertEqual(self.game.state['stage'], 2)
        self.fail('unlock', area='archive', answer='CINDER-47')
        self.send('unlock', area='archive', answer=c.PASSWORD)
        self.send('fetch', ref='D-204')
        self.send('fetch', ref='NOAH-R7')
        self.assertEqual(self.game.state['stage'], 5)
        self.assertEqual(len(self.game.state['records']), 3)

    def test_decoy_rejects_wrong_route_and_intelligence_attachment(self):
        self.to(9)
        self.clean_cache()
        self.decoy(**{'staging/plan.txt': c.PLAN.replace(b'EAST-4', b'WEST-2')})
        self.assertIn('配置表', self.fail('check'))
        self.assertFalse(self.game.fs.exists(c.OUT + '/.keys/final.key'))
        self.decoy(**{'staging/orders.txt': c.ORDERS})
        self.assertIn('2点', self.fail('check'))
        self.decoy(**{'staging/READY': 'yes'})
        self.assertIn('空', self.fail('check'))
        self.decoy(**{'staging/plan.txt': c.PLAN.replace(b'\n', b'\r\n')})
        self.send('check')
        self.assertTrue(self.game.state['decoy'])

    def test_cache_limits_apply_to_both_transmissions(self):
        self.to(9)
        self.decoy()
        self.assertIn('old', self.fail('check'))
        self.game.fs.remove(c.HOME + '/transfer-cache/old')
        self.assertIn('1 MiB', self.fail('check'))
        self.clean_cache()
        self.send('check')
        self.send('unlock', area='core', answer=c.KEY)
        self.submit_files()
        self.game.fs.write(c.HOME + '/transfer-cache/again.tmp', b'x' * MIB)
        self.assertIn('1 MiB', self.fail('submit'))

    def test_final_report_manifest_and_originals(self):
        self.to(10)
        self.send('unlock', area='core', answer=c.KEY)
        self.submit_files(**{'staging/report.txt': c.REPORT.replace(b',D-204', b'')})
        self.assertIn('乗員', self.fail('submit'))
        self.submit_files(**{'staging/orders.txt': 'forged'})
        self.assertIn('署名', self.fail('submit'))
        self.submit_files(**{'staging/manifest.txt': 'meeting.txt\n' * 5})
        self.assertIn('manifest', self.fail('submit'))
        self.game.fs.write(c.SOURCES['meeting.txt'], 'forged')
        self.submit_files()
        self.assertIn('原本', self.fail('submit'))
        self.send('reset', confirmed=True)
        names = list(c.EVIDENCE) + ['directive.txt']
        self.submit_files(**{'staging/manifest.txt': '\r\n'.join(reversed(names)) + '\r\n',
                             'staging/report.txt': c.REPORT.rstrip(b'\n')})
        self.send('submit')

    def test_early_recovery_and_late_records_keep_core_and_checkpoint(self):
        self.send('fetch', ref='BKP-0210')
        self.send('unlock', area='archive', answer=c.PASSWORD)
        self.send('fetch', ref='LIAISON-04')
        self.game.fs.write(c.HOME + '/recovery/recovery.conf',
                           'TARGET=liaison-04\nOUTPUT=/home/contractor/recovery/output\n')
        (self.root / c.HOME / 'recovery/recover.sh').chmod(0o744)
        self.send('recover')
        self.clean_cache()
        self.decoy()
        self.send('check')
        self.send('unlock', area='core', answer=c.KEY)
        self.submit_files()
        self.assertIn('環境エラー', self.fail('submit'))
        for ref in ('D-204', 'TERM-E5-03', 'MAIL-0216', 'NOAH-R7'):
            self.send('fetch', ref=ref)
            self.assertEqual(self.game.state['stage'], 10)
        self.restart()
        self.send('reset', confirmed=True)
        self.assertTrue(self.game.state['core'])
        self.submit_files()
        self.send('submit')

    def test_reset_repairs_old_record_corruption_saved_at_later_checkpoint(self):
        self.to(5)
        self.game.fs.write(c.SOURCES['meeting.txt'], 'accidental edit')
        self.send('fetch', ref='D-204')
        self.assertEqual(self.game.fs.read(c.SOURCES['meeting.txt']), b'accidental edit')
        self.restart()
        self.send('reset', confirmed=True)
        self.assertEqual(self.game.fs.read(c.SOURCES['meeting.txt']), c.EVIDENCE['meeting.txt'])
        self.assertIn('D-204', self.game.state['records'])

    def test_hint_printf_examples_produce_valid_plan_and_report(self):
        import shlex
        for number, expected in [(9, c.PLAN), (10, c.REPORT)]:
            line = next(line for line in c.STAGES[number]['hints'][2].splitlines()
                        if line.startswith('printf') and ('MEETING_POINT' in line or 'PASSENGERS' in line))
            args = shlex.split(line.split(' > ', 1)[0])
            result = subprocess.run(args, capture_output=True, check=True)
            self.assertEqual(result.stdout, expected)

    def test_recovery_reset_preserves_progress_and_can_be_retried(self):
        self.to(8)
        self.game.fs.write(c.HOME + '/recovery/recovery.conf', 'bad')
        self.send('reset', confirmed=True)
        self.assertIn(b'TARGET=liaison-00', self.game.fs.read(c.HOME + '/recovery/recovery.conf'))
        self.assertFalse(self.game.state['collected'])
        self.game.fs.write(c.HOME + '/recovery/recovery.conf', 'TARGET=liaison-04\nOUTPUT=/home/contractor/recovery/output\n')
        (self.root / c.HOME / 'recovery/recover.sh').chmod(0o744)
        self.send('recover')
        self.game.fs.remove(c.HOME + '/inbox/ren.txt')
        self.send('reset', confirmed=True)
        self.assertTrue(self.game.state['collected'])
        self.assertTrue(self.game.fs.exists(c.HOME + '/inbox/ren.txt'))
        self.assertFalse(self.game.fs.exists(c.OUT + '/.keys/final.key'))

    def test_reset_restores_core_and_accepted_decoy_after_restart(self):
        self.to(10)
        self.send('unlock', area='core', answer=c.KEY)
        self.game.fs.remove(c.BASE + '/core')
        self.game.fs.write(c.HOME + '/staging/plan.txt', 'bad')
        self.restart()
        self.send('reset', confirmed=True)
        self.assertEqual(self.game.fs.read(c.BASE + '/core/directive.txt'), c.DIRECTIVE.encode())
        self.assertEqual(self.game.fs.read(c.HOME + '/staging/plan.txt'), c.PLAN)
        self.assertTrue(self.game.state['core'])
        self.assertTrue(self.game.state['decoy'])

    def test_config_is_data_and_fake_files_do_not_advance(self):
        self.to(8)
        marker = Path(self.temp.name) / 'SHOULD-NOT-EXIST'
        self.game.fs.write(c.HOME + '/recovery/recovery.conf', f'TARGET=$(touch {marker})\nOUTPUT=/home/contractor/recovery/output\n')
        self.fail('recover')
        self.assertFalse(marker.exists())
        self.game.fs.write(c.HOME + '/recovery/recovery.conf', 'TARGET=liaison-04\nTARGET=liaison-04\nOUTPUT=/home/contractor/recovery/output\n')
        self.fail('recover')
        self.game.fs.write(c.OUT + '/orders.txt', c.ORDERS)
        self.send('check')
        self.assertEqual(self.game.state['stage'], 8)
        self.fail('submit')

    def test_record_interruption_retries_without_duplicate_progress(self):
        original = self.game.fs.write
        def broken(path, data, *args, **kwargs):
            if path.endswith('notes.txt'):
                raise OSError('simulated disk failure')
            return original(path, data, *args, **kwargs)
        with mock.patch.object(self.game.fs, 'write', side_effect=broken):
            self.fail('fetch', ref='NOAH-R7')
        self.restart()
        self.assertEqual(self.game.state['records'], ['NOAH-R7'])
        self.assertEqual(self.game.state['stage'], 2)
        self.assertTrue(self.game.fs.exists(c.BASE + '/records/research/notes.txt'))
        self.send('fetch', ref='NOAH-R7')
        self.assertEqual(self.game.state['stage'], 2)

    def test_decoy_and_completion_interruption_are_resumable(self):
        self.to(9)
        self.clean_cache()
        self.decoy()
        original = self.game.fs.write
        def broken(path, data, *args, **kwargs):
            if path.endswith('final.key'):
                raise OSError('simulated disk failure')
            return original(path, data, *args, **kwargs)
        with mock.patch.object(self.game.fs, 'write', side_effect=broken):
            self.fail('check')
        self.restart()
        self.assertTrue(self.game.state['decoy'])
        self.send('unlock', area='core', answer=c.KEY)
        self.submit_files()
        with mock.patch.object(self.game.fs, 'write', side_effect=OSError('simulated disk failure')):
            self.fail('submit')
        self.restart()
        self.assertTrue(self.game.state['submitted'])
        self.assertEqual(self.send('current'), c.COMPLETE)

    def test_reset_and_operator_rebuild_are_resumable(self):
        self.to(9)
        self.game.state['pending'] = {'kind': 'reset'}
        self.game.save()
        self.game.fs.remove(c.HOME + '/transfer-cache')
        self.restart()
        self.assertTrue(self.game.fs.exists(c.HOME + '/transfer-cache/old'))
        self.game.fs.remove(c.HOME)
        self.game.action('rebuild')
        self.assertEqual(self.game.fs.read(c.SOURCES['orders.txt']), c.ORDERS.encode())

    def test_hints_adapt_to_missing_records_and_stale_prompts_fail(self):
        self.send('fetch', ref='BKP-0210')
        for _ in range(4):
            self.send('hint')
        self.assertEqual(len(self.game.state['hints']['1']), 3)
        self.send('fetch', ref='NOAH-R7')
        self.send('hint')
        self.assertEqual(self.game.state['hints']['3'], [0])
        self.assertIn('ヒント 3', self.send('hints'))
        prompt = self.send('unlock', area='archive')
        self.send('unlock', area='archive', answer=c.PASSWORD)
        self.fail('unlock', area='archive', answer=c.PASSWORD, stage=prompt['stage'])
        self.fail('replay', number=10)
        before = json.dumps(self.game.state, sort_keys=True)
        self.send('replay', number=1)
        self.assertEqual(json.dumps(self.game.state, sort_keys=True), before)
        self.assertEqual(json.loads((self.private / 'replay-request.json').read_text()), {'stage': 1})

    def test_source_modes_and_symlink_isolation(self):
        old = os.umask(0o077)
        try:
            self.game.fs.write(c.HOME + '/recovery/recover.sh', c.RECOVER, 0o644)
            self.game.fs.mkdir(c.HOME + '/new-directory')
        finally:
            os.umask(old)
        self.assertEqual(self.game.fs.info(c.HOME + '/recovery/recover.sh').st_mode & 0o777, 0o644)
        self.assertEqual(self.game.fs.info(c.HOME + '/new-directory').st_mode & 0o777, 0o755)
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        marker = outside / 'secret'
        marker.write_text('untouched')
        self.game.fs.remove(c.HOME + '/inbox')
        (self.root / c.HOME / 'inbox').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.game.fs.write(c.HOME + '/inbox/secret', 'bad')
        with self.assertRaises(OSError):
            self.game.fs.read(c.HOME + '/inbox/secret')
        self.send('reset', confirmed=True)
        self.assertEqual(marker.read_text(), 'untouched')
        self.assertFalse((self.root / c.HOME / 'inbox').is_symlink())

    def test_all_practice_checkpoints_and_old_save_rejection(self):
        for n in range(1, 11):
            with self.subTest(n=n), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / 'root'
                root.mkdir()
                game = Engine(root, Path(folder) / 'private')
                practice(game, n)
                self.assertEqual(game.state['stage'], n)
                self.assertTrue(game.load_snapshot(n))
                game.close()
        self.game.state['scenario'] = 1
        self.game.save()
        dbpath = self.private / 'state.sqlite3'
        before = sqlite3.connect(dbpath).execute('SELECT data FROM state').fetchone()[0]
        with self.assertRaisesRegex(ValueError, '旧シナリオ'):
            Engine(self.root, self.private)
        after = sqlite3.connect(dbpath).execute('SELECT data FROM state').fetchone()[0]
        self.assertEqual(before, after)


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
