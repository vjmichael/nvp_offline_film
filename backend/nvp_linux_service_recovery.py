"""Installed systemd generation custody. Root-owned evidence, not creator consent.

An installed administrator-controlled stop hook records an empty former service
subtree (apart from the hook itself). The trusted host binds admissions to the
start record before launch. Untrusted workers cannot write these records or the
host ledger. A hostile administrator/host is not in this trust boundary.
No evidence is inferred from PID names, timeouts, or an environment variable.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/var/lib/nvp-service-recovery')
CGROUP = Path('/sys/fs/cgroup')
FORMAT = 'nvp.systemd.generation.v1'  # historical same-boot records
PERSISTENT_FORMAT = 'nvp.systemd.generation.v2'
MAX_GENERATIONS = 4096  # record segment size; historical root segment retained
MAX_SEGMENTS = 16
_SEGMENT = re.compile(r"segment-[0-9]{4}\Z")
_PENDING = re.compile(r"\.pending-[0-9a-f]{24}\Z")
_RECORD = re.compile(r"[0-9a-f]{32}\.(?:start|stop)\.json\Z")
_UNIT = re.compile(r'nvp-[a-z0-9-]+@[a-z_][a-z0-9_-]{0,31}\.service\Z')
_HEX = re.compile(r'[0-9a-f]{32}\Z')
_RESULTS = frozenset(('success', 'signal', 'exit-code', 'core-dump', 'timeout', 'watchdog', 'oom-kill', 'resources'))
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _unit(value):
    if not isinstance(value, str) or not _UNIT.fullmatch(value):
        raise ValueError('Invalid fixed NVP service name')
    return value


def _inv(value):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError('Invalid systemd invocation identity')
    return value


def _boot():
    return _inv(Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', ''))


def _scope(unit):
    relative = Path('/proc/self/cgroup').read_text().strip().split('::', 1)[1]
    path = CGROUP / relative.lstrip('/')
    matches = [p for p in (path, *path.parents) if p.name == unit and p.is_relative_to(CGROUP)]
    if len(matches) != 1 or not matches[0].is_dir() or path.resolve() != path:
        raise PermissionError('Not executing in the exact installed service cgroup')
    return matches[0], path


def _trusted_directory(path):
    """Verify every ancestor by dirfd, not a followable path check."""
    if not path.is_absolute() or '..' in path.parts:
        raise PermissionError('Unsafe authority directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            old = fd
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=old)
            os.close(old)
            s = os.fstat(fd)
            if s.st_uid != 0 or s.st_mode & 0o022:
                raise PermissionError('Authority directory not root-controlled')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _record_directories(unit):
    root = ROOT / _unit(unit)
    fd = _trusted_directory(root)
    try:
        names = sorted(n for n in os.listdir(fd) if _SEGMENT.fullmatch(n))
    finally:
        os.close(fd)
    if len(names) >= MAX_SEGMENTS or any(not 1 <= int(n[-4:]) < MAX_SEGMENTS for n in names):
        raise PermissionError('Unreviewed authority segment')
    return [root, *(root / n for n in names)]


def _read(unit, invocation, kind):
    if kind not in ('start','stop'): raise ValueError('Invalid generation record kind')
    name = _inv(invocation) + '.' + kind + '.json'
    found = []
    for folder in _record_directories(unit):
        fd = _trusted_directory(folder)
        try:
            try: os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError: continue
            found.append(folder)
        finally: os.close(fd)
    if not found: raise FileNotFoundError(name)
    if len(found) != 1: raise PermissionError('Duplicate generation record across segments')
    return _read_at(unit, invocation, kind, found[0])


def _read_at(unit, invocation, kind, folder):
    unit, invocation = _unit(unit), _inv(invocation)
    if kind not in ('start', 'stop'):
        raise ValueError('Invalid generation record kind')
    fd = _trusted_directory(folder)
    try:
        name = invocation + '.' + kind + '.json'
        with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd), 'rb') as stream:
            s = os.fstat(stream.fileno())
            if s.st_uid != 0 or s.st_mode & 0o022 or not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_size > 8192:
                raise PermissionError('Authority record not root-controlled regular file')
            raw = stream.read(8193)
        doc = json.loads(raw)
        if (raw != canonical(doc) or doc.get('format') not in (FORMAT, PERSISTENT_FORMAT) or doc.get('unit') != unit or
            doc.get('invocation') != invocation or doc.get('kind') != kind):
            raise PermissionError('Mismatched authority identity')
        required={'format','kind','unit','invocation','boot','scope','time_ns'}
        if kind=='stop': required|={'start_sha256','service_result','prior_subtree_empty'}
        persistent = doc['format'] == PERSISTENT_FORMAT
        cold = persistent and kind == 'stop' and doc.get('service_result') == 'cold-reboot'
        if persistent:
            required |= {'machine','sequence','previous_start_sha256'}
        if cold:
            required |= {'witness_invocation','witness_start_sha256','witness_boot'}
        if (set(doc)!=required or not isinstance(doc['boot'],str) or not _HEX.fullmatch(doc['boot']) or
            not isinstance(doc['scope'],str) or not Path(doc['scope']).is_relative_to(CGROUP) or
            Path(doc['scope']).name!=unit or '..' in Path(doc['scope']).parts or
            type(doc['time_ns']) is not int or doc['time_ns']<=0 or
            (kind=='stop' and (not isinstance(doc['start_sha256'],str) or not _SHA.fullmatch(doc['start_sha256']) or
                (doc['service_result'] not in _RESULTS and not cold) or doc['prior_subtree_empty'] is not True))):
            raise PermissionError('Malformed generation record')
        if persistent and (not isinstance(doc['machine'],str) or not _HEX.fullmatch(doc['machine']) or
            type(doc['sequence']) is not int or not 1 <= doc['sequence'] <= MAX_GENERATIONS * MAX_SEGMENTS or
            not isinstance(doc['previous_start_sha256'],str) or not _SHA.fullmatch(doc['previous_start_sha256'])):
            raise PermissionError('Malformed persistent generation identity')
        if cold and (not isinstance(doc['witness_invocation'],str) or not _HEX.fullmatch(doc['witness_invocation']) or
            not isinstance(doc['witness_boot'],str) or not _HEX.fullmatch(doc['witness_boot']) or
            not isinstance(doc['witness_start_sha256'],str) or not _SHA.fullmatch(doc['witness_start_sha256'])):
            raise PermissionError('Malformed reboot witness')
        expected = _record_folder(unit, doc)
        if folder != expected:
            raise PermissionError('Generation stored in wrong segment')
        return doc
    finally:
        os.close(fd)


def _record_folder(unit, doc):
    base = ROOT / unit
    segment = ((doc['sequence'] - 1) // MAX_GENERATIONS if doc['format'] == PERSISTENT_FORMAT else 0)
    if not 0 <= segment < MAX_SEGMENTS:
        raise RuntimeError('Authority retention limit; reviewed migration required')
    return base if segment == 0 else base / f'segment-{segment:04d}'


def _ensure_unit(unit):
    parent = _trusted_directory(ROOT)
    try:
        try:
            os.mkdir(_unit(unit), 0o755, dir_fd=parent)
            os.chmod(unit,0o755,dir_fd=parent,follow_symlinks=False)
        except FileExistsError: pass
        os.fsync(parent)
    finally: os.close(parent)


def _repair_pending(unit):
    """Root hook only. Unpublished temp files have no authority; a published
    two-link inode must match exactly one canonical record in its own folder.
    Never repair a foreign link or infer a stop record from a pending file."""
    if os.geteuid() != 0: raise PermissionError('Root publication repair required')
    for folder in _record_directories(unit):
        fd = _trusted_directory(folder)
        try:
            names = os.listdir(fd)
            pending = [n for n in names if n.startswith('.pending-')]
            if len(pending) > 64: raise PermissionError('Excess interrupted publications')
            for name in pending:
                a = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if (not _PENDING.fullmatch(name) or not stat.S_ISREG(a.st_mode) or a.st_uid != 0 or a.st_mode & 0o022 or a.st_nlink not in (1,2) or a.st_size > 8192):
                    raise PermissionError('Untrusted interrupted publication')
                if a.st_nlink == 2:
                    matches = []
                    for final in names:
                        if not _RECORD.fullmatch(final): continue
                        b = os.stat(final, dir_fd=fd, follow_symlinks=False)
                        if (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino): matches.append(final)
                    if len(matches)!=1: raise PermissionError('Unmatched interrupted record link')
                    # Confirm document identity before removing the extra link.
                    with os.fdopen(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd),'rb') as f: raw=f.read(8193)
                    doc=json.loads(raw); inv,kind,_=matches[0].split('.')
                    if raw!=canonical(doc) or doc.get('unit')!=unit or doc.get('invocation')!=inv or doc.get('kind')!=kind:
                        raise PermissionError('Interrupted record identity mismatch')
                    os.unlink(name,dir_fd=fd); os.fsync(fd)
                    _read_at(unit,inv,kind,folder)  # full structural validation
                else:
                    os.unlink(name,dir_fd=fd); os.fsync(fd)
        finally: os.close(fd)


def _write(unit, kind, doc):
    if os.geteuid() != 0:
        raise PermissionError('Only installed root hook may issue evidence')
    # The package creates ROOT with root ownership; create per-unit directory
    # via trusted dirfd. Atomic, no overwrite (including on replay).
    _ensure_unit(unit)
    folder = _record_folder(unit, doc)
    base = ROOT / unit
    if folder != base:
        parent = _trusted_directory(base)
        try:
            try:
                os.mkdir(folder.name,0o755,dir_fd=parent)
                os.chmod(folder.name,0o755,dir_fd=parent,follow_symlinks=False)
            except FileExistsError: pass
            os.fsync(parent)
        finally: os.close(parent)
    try: prior = _read(unit, doc['invocation'], kind)
    except FileNotFoundError: pass
    else:
        if prior != doc: raise PermissionError('Authority record already published with different contents')
        return
    fd = _trusted_directory(folder)
    name = _inv(doc['invocation']) + '.' + kind + '.json'
    import secrets
    temp = '.pending-' + secrets.token_hex(12)
    try:
        with os.fdopen(os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644, dir_fd=fd), 'wb') as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(canonical(doc)); stream.flush(); os.fsync(stream.fileno())
        # Rename without overwriting using hard-link publication; unlink temp
        # before directory fsync. A crash with two links fails closed on read.
        os.link(temp, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.fsync(fd)  # persist final link before removing the recoverable staging link
        os.unlink(temp, dir_fd=fd); os.fsync(fd)
    finally:
        try: os.unlink(temp, dir_fd=fd)
        except FileNotFoundError: pass
        os.close(fd)


def _exclusive_hook(scope, current):
    # The systemd hook itself is the only permitted process in the subtree.
    # Enumerate every descendant cgroup, not just the parent cgroup.procs.
    if current not in (scope, scope / '.control'):
        raise PermissionError('Not a privileged service control hook')
    seen = set(); count = 0
    def fail_walk(exc): raise exc
    for directory, dirs, _ in os.walk(scope, followlinks=False, onerror=fail_walk):
        count += 1
        if count > 4096 or any((Path(directory) / name).is_symlink() for name in dirs):
            raise PermissionError('Unreviewed service subtree')
        seen.update(int(x) for x in (Path(directory) / 'cgroup.procs').read_text().split())
    if seen != {os.getpid()}:
        raise RuntimeError('Service subtree still contains other processes')


def _machine():
    # The authority store is local to this installed machine, not transferable.
    # A malicious root or restored/cloned disk snapshot is outside this boundary.
    fd = _trusted_directory(Path('/etc'))
    try:
        with os.fdopen(os.open('machine-id', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd), 'rb') as f:
            info = os.fstat(f.fileno())
            if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode) or info.st_size > 64:
                raise PermissionError('Untrusted machine identity')
            return _inv(f.read(65).decode('ascii').strip())
    finally:
        os.close(fd)


def _persistent_chain(unit, machine):
    # Every v2 start links its predecessor. No wall-clock inference: RTC/NTP
    # may move backwards. Missing interior records or forked sequence fail closed.
    try: folders = _record_directories(unit)
    except FileNotFoundError: return []
    starts = []; seen=set()
    for folder in folders:
        fd = _trusted_directory(folder)
        try: names = [n for n in os.listdir(fd) if n.endswith('.start.json')]
        finally: os.close(fd)
        if len(names)>MAX_GENERATIONS: raise PermissionError('Authority segment exceeds reviewed bound')
        for name in names:
            if name in seen: raise PermissionError('Duplicate start record across segments')
            seen.add(name)
            starts.append(_read_at(unit,name.removesuffix('.start.json'),'start',folder))
    chain = sorted((d for d in starts if d['format'] == PERSISTENT_FORMAT), key=lambda d:d['sequence'])
    prev = '0'*64
    for seq, doc in enumerate(chain, 1):
        if doc['machine'] != machine or doc['sequence'] != seq or doc['previous_start_sha256'] != prev:
            raise PermissionError('Persistent generation chain mismatch')
        prev = digest(doc)
    return chain


def _cold_stops(chain, witness):
    # Only the installed root hook reaches this function, after its real cgroup
    # exclusivity check. A previous kernel cannot retain its tasks across reboot.
    # No same-boot missing stop is inferred; legacy boot records stay quarantined.
    for old in chain:
        if old['boot'] == witness['boot']:
            continue
        try:
            _read(old['unit'], old['invocation'], 'stop')
        except FileNotFoundError:
            stop = dict(old, kind='stop', time_ns=time.time_ns(), start_sha256=digest(old),
                        service_result='cold-reboot', prior_subtree_empty=True,
                        witness_invocation=witness['invocation'], witness_start_sha256=digest(witness),
                        witness_boot=witness['boot'])
            _write(old['unit'], 'stop', stop)


def systemd_hook(kind, unit):
    """Called only as installed root-owned ExecStartPre/ExecStopPost."""
    if os.geteuid() != 0 or kind not in ('start', 'stop'):
        raise PermissionError('Invalid privileged generation hook')
    unit = _unit(unit); invocation = _inv(os.environ.get('INVOCATION_ID'))
    scope, current = _scope(unit)
    _exclusive_hook(scope, current)
    boot, machine = _boot(), _machine()
    _ensure_unit(unit)
    fd = _trusted_directory(ROOT / unit)
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _repair_pending(unit)
        _publish_hook(kind,unit,invocation,scope,boot,machine)
    finally:
        os.close(fd)


def _publish_hook(kind,unit,invocation,scope,boot,machine):
    if kind == 'start':
        chain = _persistent_chain(unit, machine)
        if any(old['scope'] != str(scope) for old in chain):
            raise PermissionError('Installed scope changed')
        matches=[old for old in chain if old['invocation']==invocation]
        if matches:
            doc=matches[0]
            if len(matches)!=1 or doc!=chain[-1] or doc['boot']!=boot:
                raise PermissionError('Stale start replay')
            try: _read(unit,invocation,'stop')
            except FileNotFoundError: pass
            else: raise PermissionError('Stopped invocation cannot restart')
            # Retry incomplete cold-stop publication without changing witness identity.
            _cold_stops(chain[:-1],doc)
            return
        if len(chain) >= MAX_GENERATIONS * MAX_SEGMENTS:
            raise RuntimeError('Authority retention limit; reviewed migration required')
        doc = {'format': PERSISTENT_FORMAT, 'kind': kind, 'unit': unit, 'invocation': invocation,
               'boot': boot, 'scope': str(scope), 'time_ns': time.time_ns(), 'machine': machine,
               'sequence': len(chain)+1, 'previous_start_sha256': digest(chain[-1]) if chain else '0'*64}
        _write(unit, kind, doc)
        _cold_stops(chain, doc)
    else:
        start = _read(unit, invocation, 'start')
        if start['boot'] != boot or start['scope'] != str(scope) or (start['format']==PERSISTENT_FORMAT and start['machine']!=machine):
            raise PermissionError('Stop does not match original start')
        service_result = os.environ.get('SERVICE_RESULT')
        if service_result not in _RESULTS:
            raise PermissionError('No systemd stop result')
        doc = dict(start, kind='stop', time_ns=time.time_ns(), start_sha256=digest(start),
                   service_result=service_result, prior_subtree_empty=True)
        try: prior=_read(unit,invocation,'stop')
        except FileNotFoundError: pass
        else:
            if prior != dict(doc,time_ns=prior['time_ns']):
                raise PermissionError('Conflicting stop replay')
            return
        if start['format']==FORMAT and start['time_ns']>doc['time_ns']:
            raise PermissionError('Legacy stop time reversed')
        _write(unit, kind, doc)


class SystemdRecoveryAuthority:
    """Trusted host uses same installed fixed unit for admission and recovery."""
    def __init__(self, unit):
        self.unit = _unit(unit)

    def current(self):
        invocation = _inv(os.environ.get('INVOCATION_ID'))
        scope, current = _scope(self.unit)
        if current != scope / 'nvp.host':
            raise PermissionError('Host is not in installed delegated subgroup')
        doc = _read(self.unit, invocation, 'start')
        if doc.get('boot') != _boot() or doc.get('scope') != str(scope):
            raise PermissionError('Stale generation start')
        if doc['format'] == PERSISTENT_FORMAT:
            chain = _persistent_chain(self.unit, _machine())
            if not chain or chain[-1] != doc:
                raise PermissionError('Current invocation is not the persistent chain head')
        # A stopped generation must never start more work.
        try: _read(self.unit, invocation, 'stop')
        except FileNotFoundError: pass
        else: raise PermissionError('Generation is already stopped')
        return doc

    def stopped(self, invocation, start_sha256):
        current = self.current()
        if invocation == current['invocation'] or not _SHA.fullmatch(start_sha256):
            raise PermissionError('Cannot recover current or unbound generation')
        start = _read(self.unit, invocation, 'start')
        stop = _read(self.unit, invocation, 'stop')
        if (digest(start) != start_sha256 or stop.get('start_sha256') != start_sha256 or
            stop.get('prior_subtree_empty') is not True or
            any(stop.get(k) != start.get(k) for k in ('format','unit','invocation','boot','scope')) or
            start.get('scope') != current.get('scope')):
            raise PermissionError('Unmatched or stale stop witness')
        if start['format'] == FORMAT:
            if (start['boot'] != current['boot'] or
                not start['time_ns'] <= stop['time_ns'] <= current['time_ns']):
                raise PermissionError('Legacy stop not in current boot')
            return stop
        if current['format'] != PERSISTENT_FORMAT or any(stop.get(k)!=start.get(k) for k in ('machine','sequence','previous_start_sha256')):
            raise PermissionError('Persistent stop binding mismatch')
        chain = _persistent_chain(self.unit, _machine())
        if not chain or chain[-1] != current or start not in chain[:-1]:
            raise PermissionError('Source generation is not an authenticated predecessor')
        if stop['service_result'] == 'cold-reboot':
            matches = [d for d in chain if d['invocation']==stop['witness_invocation']]
            if (len(matches)!=1 or matches[0]['sequence']<=start['sequence'] or
                digest(matches[0])!=stop['witness_start_sha256'] or matches[0]['boot']!=stop['witness_boot'] or
                matches[0]['boot']==start['boot'] or matches[0]['scope']!=start['scope']):
                raise PermissionError('Invalid cross-boot stop witness')
        return stop
