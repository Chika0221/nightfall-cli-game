"""Descriptor-relative filesystem access: never traverse player-controlled links."""
import contextlib
import os
from pathlib import PurePosixPath
import stat
import uuid


class UnsafePath(ValueError):
    pass


class Files:
    def __init__(self, root, uid=None, gid=None):
        self.root = str(root)
        self.uid = os.getuid() if uid is None else uid
        self.gid = os.getgid() if gid is None else gid

    @staticmethod
    def parts(path):
        p = PurePosixPath(path)
        if p.is_absolute() or not p.parts or '..' in p.parts:
            raise UnsafePath('安全でないパスです。')
        return p.parts

    def own(self, fd):
        if os.geteuid() == 0:
            os.fchown(fd, self.uid, self.gid)

    @contextlib.contextmanager
    def directory(self, parts=(), create=False):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in parts:
                if create:
                    try:
                        os.mkdir(name, 0o755, dir_fd=fd)
                        made = True
                    except FileExistsError:
                        made = False
                else:
                    made = False
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
                if made:
                    os.fchmod(fd, 0o755)
                    self.own(fd)
            yield fd
        finally:
            os.close(fd)

    def mkdir(self, path):
        with self.directory(self.parts(path), create=True):
            pass

    def write(self, path, data, mode=0o644):
        if isinstance(data, str):
            data = data.encode('utf-8')
        parts = self.parts(path)
        with self.directory(parts[:-1], create=True) as parent:
            tmp = '.nightfall-' + uuid.uuid4().hex
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    self.own(stream.fileno())
                    os.fchmod(stream.fileno(), mode)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
            finally:
                try:
                    os.unlink(tmp, dir_fd=parent)
                except FileNotFoundError:
                    pass

    def read(self, path, limit=8 * 1024 * 1024):
        parts = self.parts(path)
        with self.directory(parts[:-1]) as parent:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise UnsafePath(f'{path} はリンクでない通常ファイルにしてください。')
                if info.st_size > limit:
                    raise UnsafePath(f'{path} がサイズ上限を超えています。')
                data = stream.read(limit + 1)
                if len(data) > limit:
                    raise UnsafePath(f'{path} がサイズ上限を超えています。')
                return data

    def info(self, path):
        parts = self.parts(path)
        with self.directory(parts[:-1]) as parent:
            return os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)

    def exists(self, path):
        try:
            self.info(path)
            return True
        except FileNotFoundError:
            return False

    def remove(self, path):
        parts = self.parts(path)
        try:
            with self.directory(parts[:-1]) as parent:
                self._remove(parent, parts[-1])
        except FileNotFoundError:
            pass

    def _remove(self, parent, name):
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                for entry in os.listdir(child):
                    self._remove(child, entry)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=parent)
        else:
            os.unlink(name, dir_fd=parent)

    def tree(self, path):
        """Bounded snapshot, including empty directories; links are never followed."""
        entries = []
        total = 0
        def visit(fd, prefix):
            nonlocal total
            for name in sorted(os.listdir(fd)):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                rel = prefix + '/' + name
                if len(entries) >= 5000:
                    raise UnsafePath('復旧対象のファイルが多すぎます。')
                if stat.S_ISDIR(info.st_mode):
                    entries.append((rel, None, info.st_mode & 0o777))
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        visit(child, rel)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    data = self.read(rel)
                    total += len(data)
                    if total > 32 * 1024 * 1024:
                        raise UnsafePath('復旧対象は32 MiB以下にしてください。')
                    entries.append((rel, data, info.st_mode & 0o777))
                else:
                    raise UnsafePath(f'{rel} にリンクまたは特殊ファイルがあります。')
        info = self.info(path)
        if stat.S_ISDIR(info.st_mode):
            entries.append((path, None, info.st_mode & 0o777))
            with self.directory(self.parts(path)) as fd:
                visit(fd, path)
        else:
            entries.append((path, self.read(path), info.st_mode & 0o777))
        return entries
