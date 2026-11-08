# -*- coding: utf-8 -*-
# -*- python -*-
# Part of syuppo package
# Copyright © 2019-2026 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
#
# Build duration history, kept in a small database so that estimating an
# update does not mean reparsing the log.
#
# The parsing itself is cheap -- 0.3 s for 42 MB -- but it would happen on
# every query, and the log only grows. Recording each build once and reading
# from an index instead keeps the cost proportional to what was added, not to
# what accumulated.

import logging
import os
import pathlib
import re
import sqlite3
import statistics
import time

from syuppo.logparser import EmergeLogParser


# Recorded alongside every measurement, and matched against when estimating.
#
# Two fields only, deliberately. Each one added narrows the set of usable
# measurements and lengthens the periods where there is no history to work
# from. MAKEOPTS changes build times directly and by a lot; the CPU model
# covers moving to another machine. Compiler version, CFLAGS, memory and
# disk all have some effect, but one that disappears into the normal
# variation between two builds of the same package.
CONFIG_FIELDS = ('makeopts', 'cpu')

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    id          INTEGER PRIMARY KEY,
    makeopts    TEXT NOT NULL,
    cpu         TEXT NOT NULL,
    first_seen  INTEGER NOT NULL,
    UNIQUE (makeopts, cpu)
);

CREATE TABLE IF NOT EXISTS duration (
    package     TEXT NOT NULL,
    started     INTEGER NOT NULL,
    seconds     INTEGER NOT NULL,
    config_id   INTEGER NOT NULL REFERENCES config(id),
    PRIMARY KEY (package, started)
);

-- No further index. The primary key already provides one on package, which
-- is the only filter that matters. Measured at 150k, 750k and 3M rows: an
-- index on (package, config_id, started) changes nothing, and would only
-- cost space and insert time.

CREATE TABLE IF NOT EXISTS cursor (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    offset      INTEGER NOT NULL,
    inode       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    last_ts     INTEGER NOT NULL
);
"""

# Anchored on the two-space indent portage writes, so that a package name
# containing '>>> emerge (' could not be mistaken for a real entry.
START_RE = re.compile(
    r'^(\d+):\s{2}>>> emerge \((\d+) of (\d+)\) (\S+?)-\d[^\s]* to ')
END_RE = re.compile(
    r'^(\d+):\s{2}::: completed emerge \((\d+) of (\d+)\) (\S+?)-\d[^\s]* to ')


def _human(seconds):
    """'42 s', '53 min 12 s', '2 h 48 min': for debug lines only."""
    if seconds < 60:
        return f'{seconds} s'
    if seconds < 3600:
        return f'{seconds // 60} min {seconds % 60:02d} s'
    return f'{seconds // 3600} h {seconds % 3600 // 60:02d} min'


class PackagesDurations(EmergeLogParser):
    """
    How long each package took to build, historically.

    Sits beside LastSync and LastWorldUpdate rather than replacing them:
    those follow one session and report how it went, this one sweeps the
    whole log and answers a different question -- how long does this package
    usually take.
    """

    def __init__(self, dbpath, makeconf='/etc/portage/make.conf',
                 advanced_debug=False, **kwargs):
        """
        dbpath is the database FILE, not the directory holding it. Its parent
        is created if missing. Any other keyword goes through to
        EmergeLogParser, which is where 'log' is picked up -- it defaults to
        /var/log/emerge.log, so there is usually nothing to pass.

        advanced_debug (syuppod --vdebug durations) logs every build
        recorded, one line each, at level DEBUG2.
        """
        super().__init__(**kwargs)
        self.__nlogger = f'::{__name__}::PackagesDurations::'
        self.advanced_debug = advanced_debug
        self.dbpath = pathlib.Path(dbpath)
        self.makeconf = makeconf
        self._db = None
        self._config_id = None
        # Builds seen starting but not yet finished. Keyed on the position in
        # the session plus the package, which is what tells two concurrent
        # emerge sessions apart: parsing runs in file order, so a start pairs
        # with the first matching completion after it.
        self._pending = {}

    # ── Database ────────────────────────────────────────────────────────

    def connect(self):
        if self._db is not None:
            return self._db
        # sqlite3 reports 'unable to open database file' for anything it
        # cannot use, a directory included. Saying so plainly saves the
        # guessing.
        if self.dbpath.is_dir():
            raise ValueError(f'{self.dbpath} is a directory: dbpath is the '
                             'database file itself, e.g. '
                             '/var/lib/syuppod/durations.db')
        self.dbpath.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the daemon runs pretend_world() through an
        # executor, so the thread that opened the connection is not always
        # the one that uses it next. The caller serialises access with a lock;
        # sqlite itself is built thread-safe.
        db = sqlite3.connect(str(self.dbpath), check_same_thread=False)
        # WAL writes sequentially to a side file instead of scattering writes
        # through the database, and lets a reader work while writing.
        # synchronous=NORMAL stops forcing the disk on every commit, only at
        # checkpoints: measured at 260 ms for 400 inserts by default, 8.7 ms
        # this way. A power cut could then lose the last transactions -- one
        # build duration, recoverable from the log -- but a crash or SIGKILL
        # cannot: the WAL covers those.
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=NORMAL')
        db.executescript(SCHEMA)
        db.commit()
        self._db = db
        return db

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    # ── Current configuration ───────────────────────────────────────────

    def read_makeopts(self):
        """
        MAKEOPTS from make.conf.

        Read from the file rather than through portage.settings: five lines
        instead of tying the daemon to the portage API, and per-package
        overrides are out of scope here -- a measurement taken under one is
        simply attributed to the global setting.
        """
        try:
            with open(self.makeconf, 'r') as f:
                value = ''
                for line in f:
                    line = line.strip()
                    if line.startswith('MAKEOPTS='):
                        value = line.split('=', 1)[1].strip().strip('"\'')
                return value or 'unset'
        except OSError:
            return 'unknown'

    def read_cpu(self):
        """Model name from /proc/cpuinfo: covers moving to another machine."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('model name'):
                        return line.split(':', 1)[1].strip()
        except OSError:
            pass
        return 'unknown'

    def config_id(self, timestamp=0):
        """Row id for the current configuration, creating it if needed."""
        if self._config_id is not None:
            return self._config_id
        db = self.connect()
        values = (self.read_makeopts(), self.read_cpu())
        row = db.execute('SELECT id FROM config WHERE makeopts = ? AND cpu = ?',
                         values).fetchone()
        if row is None:
            cur = db.execute(
                'INSERT INTO config (makeopts, cpu, first_seen) VALUES (?, ?, ?)',
                values + (timestamp,))
            db.commit()
            self._config_id = cur.lastrowid
        else:
            self._config_id = row[0]
        return self._config_id

    # ── Reading the log ─────────────────────────────────────────────────

    def _cursor(self):
        row = self.connect().execute(
            'SELECT offset, inode, size, last_ts FROM cursor WHERE id = 1'
        ).fetchone()
        return row or (0, 0, 0, 0)

    def _rotated(self, offset, inode, size):
        """
        Whether the log was rotated since the last read.

        Two signs, either of which is enough: a different inode means the
        name now points at a new file, and a size below our offset means the
        file was truncated. Missing this leaves the parser reading from an
        offset into a file that no longer holds what it held -- and, worse,
        leaves inotify watching a rotated-away file that nothing writes to.
        """
        try:
            st = os.stat(self.emergelog)
        except OSError:
            return True, 0, 0
        return (st.st_ino != inode or st.st_size < offset), st.st_ino, st.st_size

    def update(self):
        """
        Read what was appended since last time and record any build that
        finished. Returns the number of durations added.
        """
        logger = logging.getLogger(f'{self.__nlogger}update::')
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        db = self.connect()
        offset, inode, size, last_ts = self._cursor()
        rotated, new_inode, new_size = self._rotated(offset, inode, size)

        if rotated:
            logger.debug('Log rotated or first run, reading from the start.')
            offset = 0
            self._pending.clear()

        added = 0
        config = self.config_id()
        try:
            with open(self.emergelog, 'r') as f:
                f.seek(offset)
                for line in f:
                    ts = self._feed(line, db, config, logger)
                    if ts:
                        added += 1
                        last_ts = max(last_ts, ts)
                new_offset = f.tell()
        except OSError as exc:
            logger.error(f'Could not read {self.emergelog}: {exc}')
            return 0

        db.execute(
            'INSERT INTO cursor (id, offset, inode, size, last_ts) VALUES (1,?,?,?,?)'
            ' ON CONFLICT(id) DO UPDATE SET offset=?, inode=?, size=?, last_ts=?',
            (new_offset, new_inode, new_size, last_ts) * 2)
        db.commit()
        if added:
            logger.debug(f'Recorded {added} build duration(s).')
        return added

    def _feed(self, line, db, config, logger=None):
        """
        Feed one line. Returns the timestamp when a build was recorded.
        With advanced_debug, each build is logged through 'logger'.
        """
        # Substring test before the regex: 2.6x cheaper over a whole log, and
        # the vast majority of lines match neither.
        if '>>> emerge (' in line:
            m = START_RE.match(line)
            if m:
                self._pending[(m.group(2), m.group(3), m.group(4))] = int(m.group(1))
        elif '::: completed emerge (' in line:
            m = END_RE.match(line)
            if m:
                key = (m.group(2), m.group(3), m.group(4))
                started = self._pending.pop(key, None)
                if started is not None:
                    ended = int(m.group(1))
                    # OR IGNORE rather than a lookup: re-reading a stretch of
                    # log after a rotation would otherwise fail on the primary
                    # key. The measurement is identical either way.
                    cur = db.execute(
                        'INSERT OR IGNORE INTO duration VALUES (?,?,?,?)',
                        (m.group(4), started, ended - started, config))
                    if self.advanced_debug and logger:
                        # rowcount 0: already in the database (log re-read
                        # after a rotation)
                        what = 'Recorded' if cur.rowcount else 'Already known'
                        logger.debug2(
                            f'{what}: {m.group(4)} ({_human(ended - started)},'
                            ' started '
                            + time.strftime('%Y-%m-%d %H:%M',
                                            time.localtime(started))
                            + f', config {config}).')
                    return ended
        return None

    # ── Estimating ──────────────────────────────────────────────────────

    def estimate(self, packages, samples=5):
        """
        Estimated build time for each package, in seconds.

        Returns {package: (seconds, source)}, where source says where the
        figure comes from: 'current' for measurements taken under the
        configuration in use, 'other' when it had to fall back on a different
        one. Packages never built are absent.

        The fallback matters more than it looks. Without it, changing
        MAKEOPTS would leave the daemon with nothing to say for weeks, until
        enough builds accumulated. With it, it still answers -- and says the
        figure comes from elsewhere, which is the honest thing to do.
        """
        if not packages:
            return {}
        db = self.connect()
        config = self.config_id()
        out = {}

        # Median of the last N builds rather than the mean: one interrupted
        # or unusually slow build would drag a mean along with it.
        for source, clause, args in (
                ('current', 'AND config_id = ?', (config,)),
                ('other', '', ())):
            missing = [p for p in packages if p not in out]
            if not missing:
                break
            for pkg in missing:
                rows = db.execute(
                    f'SELECT seconds FROM duration WHERE package = ? {clause}'
                    ' ORDER BY started DESC LIMIT ?', (pkg,) + args + (samples,)
                ).fetchall()
                if rows:
                    out[pkg] = (int(statistics.median(r[0] for r in rows)), source)
        return out

    def estimate_total(self, packages, samples=5):
        """
        Total for a set of packages, and what it is based on.

        Returns (seconds, known, unknown, degraded) -- the last three being
        counts, so a caller can say how much of the figure is solid. Summing
        is exact here rather than approximate: emerge builds one package at a
        time unless --jobs is used, so measured durations do not overlap.
        """
        # Count per entry of 'packages', not per distinct package: the same
        # 'cat/pkg' can come twice (two slots, e.g. dev-lang/python 3.14 and
        # 3.15), and each is a build of its own. Counting the dict instead
        # summed such a package once and reported the second entry as
        # "without history".
        found = self.estimate(list(dict.fromkeys(packages)), samples)
        total = known = degraded = 0
        for pkg in packages:
            if pkg in found:
                seconds, source = found[pkg]
                total += seconds
                known += 1
                if source != 'current':
                    degraded += 1
        return total, known, len(packages) - known, degraded
