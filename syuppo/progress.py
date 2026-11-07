# -*- coding: utf-8 -*-
# -*- python -*-
# Part of syuppo package
# Copyright © 2019-2026 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
#
# Progress of the emerge running right now: which package, which phase, how
# far along, and how long until it is done.
#
# Any emerge, not only @world. The daemon keeps following @world on its own
# (it has to know when the whole system is up to date); this is only about
# showing what is being built.
#
# Nothing runs in the background. The state is worked out when someone asks
# (dbus), then kept for a couple of seconds: the cost follows the use, and is
# nil while nothing is being built.

import json
import logging
import os
import re
import time

# Same split as the durations database: 'cat/pkg' up to the first '-<digit>'.
# The names have to match on both sides, so the rule has to be the same.
SPLIT_CPV = re.compile(r'^(\S+?)-\d')

# emerge.log, one session:
#   1793921009: Started emerge on: nov. 06, 2026 00:23:29
#   1793921009:  *** emerge --newuse --update ... @world
#   1793921161:  >>> emerge (1 of 140) dev-lang/rust-1.99.0 to /
#   1793921168:  === (1 of 140) Compiling/Merging (dev-lang/rust-1.99.0::...)
#   1793922379:  ::: completed emerge (1 of 140) dev-lang/rust-1.99.0 to /
#   1793951167:  *** terminating.
# Anchored on the two-space indent portage writes, like the durations parser.
STARTED_RE = re.compile(r'^(\d+):\sStarted\semerge\son:')
BUILD_RE = re.compile(r'^(\d+):\s{2}>>>\semerge\s\((\d+)\sof\s(\d+)\)\s(\S+)\sto\s')
STEP_RE = re.compile(r'^(\d+):\s{2}===\s\((\d+)\sof\s(\d+)\)\s(.+?)\s\(')
DONE_RE = re.compile(r'^(\d+):\s{2}:::\scompleted\semerge\s\((\d+)\sof\s(\d+)\)\s')
END_RE = re.compile(r'^(\d+):\s{2}\*\*\*\sterminating\.')

# The steps emerge writes in the log, reduced to a short key the client
# translates. Coarse: 'Compiling/Merging' covers everything from unpack to
# install, which is why the sandbox phase below is preferred when present.
LOG_STEPS = {
    'Cleaning': 'cleaning',
    'Compiling/Merging': 'building',
    'Merging': 'merging',
    'Post-Build Cleaning': 'cleaning',
}

# portage renames the sandbox process after the package it builds:
#   [dev-python/pyqt6-6.11.0-r1] sandbox /usr/lib/portage/python3.14/ebuild.sh compile
# The phase is information no other source gives.
SANDBOX_RE = re.compile(r'\[([a-z0-9-]+/[^\]]+)\]\s+sandbox\b')
PHASE_RE = re.compile(r'ebuild\.sh\s+(\w+)')

# An emerge that builds or may build. Not a pretend, a sync, a search or an
# info: those compile nothing. The daemon's own pretend falls in the first.
NOT_BUILDING_RE = re.compile(
    r'\s(?:-\w*p\w*|--pretend|--sync|-\w*s\w*|--search|--searchdesc'
    r'|--info|--version|--help|--list-sets|--depclean|-\w*c\w*'
    r'|--unmerge|-\w*C\w*)(?:\s|$)')


def is_emerge(cmd):
    """
    Whether 'cmd' is emerge itself, as opposed to a wrapper that launched it
    ('sudo emerge ...', 'nice emerge ...') or a process merely naming it.
    emerge is a Python script: its own command line is either 'emerge ...'
    or '<python> .../emerge ...'.
    """
    tokens = cmd.split()
    if not tokens:
        return False
    if os.path.basename(tokens[0]) == 'emerge':
        return True
    return (len(tokens) > 1 and os.path.basename(tokens[0]).startswith('python')
            and os.path.basename(tokens[1]) == 'emerge')


def cat_pkg(cpv):
    """'dev-lang/rust-1.99.0' -> 'dev-lang/rust' (None if it does not split)."""
    m = SPLIT_CPV.match(cpv)
    return m.group(1) if m else None


def read_processes(proc='/proc'):
    """
    Every readable process: [(pid, ppid, cmdline, start_epoch)].

    start_epoch is when the process started, in seconds since the epoch:
    field 22 of /proc/<pid>/stat counts clock ticks since boot, and
    /proc/stat gives the boot time.
    """
    try:
        with open(f'{proc}/stat') as f:
            btime = next(int(l.split()[1]) for l in f if l.startswith('btime'))
    except (OSError, StopIteration, ValueError):
        btime = 0
    hz = os.sysconf('SC_CLK_TCK')
    out = []
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        try:
            with open(f'{proc}/{name}/cmdline', 'rb') as f:
                cmd = ' '.join(x for x in f.read().decode(
                    errors='replace').split('\0') if x)
            with open(f'{proc}/{name}/stat', 'rb') as f:
                raw = f.read().decode(errors='replace')
        except OSError:
            continue
        if not cmd:
            continue
        try:
            # The command name sits between parentheses and may hold spaces
            # or parentheses: cut after the LAST closing one. What follows
            # starts at field 3 (state), so field 22 is index 19.
            fields = raw[raw.rindex(')') + 2:].split()
            ppid = int(fields[1])
            start = btime + int(fields[19]) / hz
        except (ValueError, IndexError):
            ppid, start = 0, 0
        out.append((int(name), ppid, cmd, start))
    return out


class EmergeProgress:
    """
    What the running emerge is doing, worked out on demand.

    snapshot() returns a dict:
        state     'idle', 'running' or 'multiple'
        count     number of emerge processes found
        package   'cat/pkg-version' being built, '' if none yet
        phase     short key: 'dependencies', a sandbox phase ('compile',
                  'install', ...) or a log step ('building', 'merging', ...)
        done      packages completed in this session
        total     packages in this session (0 until the first is started)
        seconds   estimated time left, or None when it cannot be told
                  honestly (see _remaining)
        unknown   packages left that have no build history
    """

    def __init__(self, durations, lock, log='/var/log/emerge.log',
                 mtimedb='/var/cache/edb/mtimedb', processes=read_processes,
                 clock=time.time, cache=2):
        self.__nlogger = f'::{__name__}::EmergeProgress::'
        self.durations = durations
        self.lock = lock
        self.log = log
        self.mtimedb = mtimedb
        self.processes = processes
        self.clock = clock
        self.cache = cache
        self._snapshot = None
        self._taken = 0
        # The session followed: emerge pid, and where we are in the log.
        self._pid = None
        self._session = None

    # ── Public ──────────────────────────────────────────────────────────

    def snapshot(self):
        now = self.clock()
        if self._snapshot is not None and now - self._taken < self.cache:
            return self._snapshot
        logger = logging.getLogger(f'{self.__nlogger}snapshot::')
        try:
            snap = self._compute(now)
        except Exception as exc:
            # Progress is a display: it must never take the daemon down.
            logger.error(f'Could not work out the emerge progress: {exc}')
            snap = self._idle()
        self._snapshot = snap
        self._taken = now
        return snap

    # ── Working it out ──────────────────────────────────────────────────

    @staticmethod
    def _idle(count=0, state='idle'):
        return {'state': state, 'count': count, 'package': '', 'phase': '',
                'done': 0, 'total': 0, 'seconds': None, 'unknown': 0}

    def _compute(self, now):
        procs = self.processes()
        candidates = [(pid, ppid, cmd, start) for pid, ppid, cmd, start in procs
                      if is_emerge(cmd)
                      and not NOT_BUILDING_RE.search(' ' + cmd)]
        # portage forks: a child keeps its parent's command line. Count only
        # the emerge whose parent is not an emerge itself.
        pids = {c[0] for c in candidates}
        emerges = [(pid, cmd, start) for pid, ppid, cmd, start in candidates
                   if ppid not in pids]
        if not emerges:
            self._pid = self._session = None
            return self._idle()
        if len(emerges) > 1:
            # Decided in August: one session followed, never several. Their
            # lists cannot be told apart reliably (mtimedb holds only one).
            self._pid = self._session = None
            return self._idle(len(emerges), 'multiple')

        pid, cmd, start = emerges[0]
        if pid != self._pid or self._session is None:
            # Also retried while not found: the 'Started' line is written a
            # moment after the process starts.
            self._pid = pid
            self._session = self._find_session(start)
        session = self._session
        if session is None:
            snap = self._idle(1, 'running')
            snap['phase'] = 'dependencies'
            return snap
        self._read_forward(session)

        snap = self._idle(1, 'running')
        snap['total'] = session['total']
        snap['done'] = session['done']
        if not session['package']:
            # Started, nothing built yet: still resolving dependencies.
            snap['phase'] = 'dependencies'
            return snap
        snap['package'] = session['package']
        snap['phase'] = self._sandbox_phase(procs, session['package']) \
            or session['step']
        snap['seconds'], snap['unknown'] = self._remaining(session, now)
        return snap

    def _find_session(self, start):
        """
        Locate in the log the session of the emerge started at 'start'.

        Reads the end of the file backwards, block by block, until the
        timestamps fall before the process started: the session is in that
        tail. Its 'Started emerge on' line is written a moment after the
        process starts (Python has to load portage first), so it is the
        first such line at or after 'start' -- with a small margin.
        """
        try:
            size = os.path.getsize(self.log)
            with open(self.log, 'rb') as f:
                block = 65536
                pos = size
                data = b''
                while pos > 0:
                    step = min(block, pos)
                    pos -= step
                    f.seek(pos)
                    data = f.read(step) + data
                    first = data.split(b'\n', 2)
                    # first complete line of what we hold (skip a partial one)
                    line = first[1] if pos > 0 and len(first) > 1 else first[0]
                    m = re.match(rb'^(\d+):', line)
                    if m and int(m.group(1)) < start - 5:
                        break
        except OSError:
            return None
        # Walk what we read forwards, remembering byte offsets.
        offset = pos
        found = None
        lines = data.split(b'\n')
        if pos > 0:
            # The first piece is the tail of a line cut by the block: its
            # timestamp would be truncated. Step over it.
            offset += len(lines[0]) + 1
            lines = lines[1:]
        for raw in lines:
            line = raw.decode(errors='replace')
            m = STARTED_RE.match(line)
            if m and found is None and int(m.group(1)) >= start - 2:
                found = offset
            offset += len(raw) + 1
        if found is None:
            return None
        return {'offset': found, 'inode': os.stat(self.log).st_ino,
                'total': 0, 'done': 0, 'package': '',
                'started': 0, 'step': '', 'building': False, 'over': False}

    def _read_forward(self, session):
        """Read what was appended since last time (seek, then forward)."""
        if session['over']:
            return
        try:
            st = os.stat(self.log)
        except OSError:
            return
        if st.st_ino != session['inode'] or st.st_size < session['offset']:
            # Rotated (or truncated) under us: the offset means nothing in
            # the new file. Keep what is known, and go on from the start of
            # the new one -- logrotate leaves it empty, emerge writes on.
            session['inode'] = st.st_ino
            session['offset'] = 0
        try:
            # Binary, so that the offset counts bytes exactly whatever the
            # encoding of the line.
            with open(self.log, 'rb') as f:
                f.seek(session['offset'])
                for raw in f:
                    if not raw.endswith(b'\n'):
                        break          # half-written line: next time
                    session['offset'] += len(raw)
                    self._feed(session, raw.decode(errors='replace'))
        except OSError:
            pass

    @staticmethod
    def _feed(session, line):
        # Substring tests first: most lines match none of these.
        if '>>> emerge (' in line:
            m = BUILD_RE.match(line)
            if m:
                session['package'] = m.group(4)
                session['started'] = int(m.group(1))
                session['done'] = int(m.group(2)) - 1
                session['total'] = int(m.group(3))
                session['step'] = ''
                session['building'] = True
        elif '=== (' in line:
            m = STEP_RE.match(line)
            if m and m.group(4) in LOG_STEPS:
                session['step'] = LOG_STEPS[m.group(4)]
        elif '::: completed emerge (' in line:
            m = DONE_RE.match(line)
            if m:
                session['done'] = int(m.group(2))
                session['building'] = False
        elif '*** terminating.' in line and END_RE.match(line):
            session['over'] = True

    @staticmethod
    def _sandbox_phase(procs, package):
        """Phase of the sandbox building 'package', '' if none is running."""
        for _pid, _ppid, cmd, _start in procs:
            m = SANDBOX_RE.search(cmd)
            if m and m.group(1) == package:
                p = PHASE_RE.search(cmd)
                if p:
                    return p.group(1)
        return ''

    def _remaining(self, session, now):
        """
        (seconds, unknown) left in this session.

        The packages still to build come from mtimedb -- the list --resume
        uses. It is trusted only when it agrees with the log: as many
        entries as the log says are left, the first one being the package
        in progress. Otherwise there is no figure rather than a wrong one,
        except when the package in progress is the last of the session.
        """
        n = session['total']
        current = session['package']
        building = session['building']
        # Left to do, the package in progress included while it builds
        expected = n - session['done']

        left = None
        try:
            with open(self.mtimedb) as f:
                mergelist = json.load(f).get('resume', {}).get('mergelist', [])
            # Binary packages are numbered in the log like the others, so
            # they have to be counted here too.
            cpvs = [e[2] for e in mergelist
                    if len(e) >= 4 and e[0] in ('ebuild', 'binary')
                    and e[3] == 'merge']
            if len(cpvs) == expected and (not building or cpvs[0] == current):
                left = cpvs
        except (OSError, ValueError, AttributeError, IndexError, TypeError):
            pass
        if left is None and expected == 1 and building:
            left = [current]             # last package: no list needed
        if left is None:
            return None, 0

        names = [cat_pkg(c) for c in left]
        with self.lock:
            found = self.durations.estimate(
                list(dict.fromkeys(n for n in names if n)))
        seconds = 0
        unknown = 0
        for i, name in enumerate(names):
            if name not in found:
                unknown += 1
                continue
            median = found[name][0]
            if i == 0 and building:
                # Time already spent on the package in progress
                median = max(0, median - (now - session['started']))
            seconds += median
        return int(seconds), unknown
