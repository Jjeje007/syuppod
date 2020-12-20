# -*- coding: utf-8 -*-
# -*- python -*- 
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import logging
import subprocess
import re

from syuppo.utils import on_parent_exit

try:
    import numpy
except Exception as exc:
    print(f'Got unexcept error while loading module: {exc}')
    sys.exit(1)


class EmergeLogParser:
    """
    Parse log file and extract informations.
    """
    def __init__(self, **kwargs):
        self.__nlogger =  f'::{__name__}::EmergeLogParser::' 
        logger = logging.getLogger(f'{self.__nlogger}init::')
        
        self.aborded = 5
        self.emergelog = kwargs.get('log',
                                    '/var/log/emerge.log')
        
        nlines = self.getlines()
        self.log_lines = { }
        if not nlines:
            # So we don't know how many lines have emerge.log 
            # go a head and give an arbitrary count
            self.log_lines = {
                'count'    :   60000, 
                'real'     :   False
                }
            logger.error(f"Couldn't get '{self.emergelog}' lines count,"
                         " setting arbitrary to: "
                         f"{self.log_lines['count']} lines.")
        else:
            self.log_lines = {
                'count'     :   nlines, 
                'real'      :   True
                }
            logger.debug(f"Setting '{self.emergelog}' maximum lines count to:"
                         + f" {self.log_lines['count']} lines.")
        # Init numpy range lists
        self._range = { }

    def getlines(self):
        """
        Get total number of lines from log file
        """
        logger = logging.getLogger(f'{self.__nlogger}getlines::')
        
        myargs = ['/bin/wc', '--lines', self.emergelog]
        mywc = subprocess.Popen(myargs, preexec_fn=on_parent_exit(),
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE, 
                                universal_newlines=True)
        
        nlines = re.compile(r'^(\d+)\s.*$')
        
        for line in mywc.stdout:
            if nlines.match(line):
                return int(nlines.match(line).group(1))
        mywc.stdout.close()
        
        return_code = mywc.poll()
        if return_code:
            logger.error(f'Got error while getting lines number for \'{self.emergelog}\' file.')
            logger.error('Command: {0}, return code: {1}'.format(' '.join(myargs), return_code))
            for line in mywc.stderr:
                line = line.rstrip()
                if line:
                    logger.error(f'Stderr: {line}')
            mywc.stderr.close()
        # Got nothing
        return False
   
   
    def getlog(self, lastlines=500):
        """
        Get last n lines from log file
        https://stackoverflow.com/a/136280/11869956
        """
        
        logger = logging.getLogger(f'{self.__nlogger}getlog::')
                
        myargs = ['/bin/tail', '-n', str(lastlines), self.emergelog]
        mytail = subprocess.Popen(myargs, preexec_fn=on_parent_exit(),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        # From https://stackoverflow.com/a/4417735/11869956
        for line in iter(mytail.stdout.readline, ""):
            yield line.rstrip()
        mytail.stdout.close()
        
        return_code = mytail.poll()
        if return_code:
            logger.error(f'Error reading \'{self.emergelog}\','
                         + f" command: \'{' '.join(myargs)}\'," 
                         + f' return code: \'{return_code}\'.')
            for line in mytail.stderr:
                line = line.rstrip()
                if line:
                    logger.error(f'Stderr: {line}')
            mytail.stderr.close()
            
             
    def keep_collecting(self, curr_loop, msg, key):
        """
        Restart collecting if nothing has been found and
        managing lastlines increment to load.
        """
               
        logger = logging.getLogger(f'{self.__nlogger}keep_collecting::')
        
        if not self.log_lines['real']:
            additionnal_msg='(unknow maximum lines)'
        else:
            additionnal_msg='(it is the maximum)'
        # Get loop count
        loop_count = len(self._range[key])
        
        if curr_loop < loop_count:
            logger.debug(f'Retry {curr_loop}/{loop_count - 1}: {msg[0]}' 
                         + ' not found, reloading an bigger increment...')
            self.lastlines = self._range[key][curr_loop]
            return True
        elif curr_loop >= loop_count:
            logger.error(f'After {loop_count - 1} retries and {self.lastlines} lines read' 
                         + f' {additionnal_msg}, {msg[0]} not found.')
            logger.error(f'Look like the system {msg[1]}')
            return False
 
 
 
class LastSync(EmergeLogParser):
    """
    Get the last sync timestamp
    """
    def __init__(self, lastlines=500, nrange=10, **kwargs):
        super().__init__(**kwargs)     
        
        self.lastlines = lastlines
        # construct exponantial list
        self._range['sync'] = numpy.geomspace(self.lastlines, self.log_lines['count'], 
                                              num=nrange, endpoint=True, dtype=int)
        self.__nlogger = f'::{__name__}::LastSync::' 
        
    def get(self):
        """
        Return last sync timestamp
        :return: 
            timestamp else False
        
        Exemple of emerge.log :
            1569592862: Started emerge on: sept. 27, 2019 16:01:02
            1569592862:  *** emerge --keep-going --quiet-build=y --sync
            1569592862:  === sync
            1569592862: >>> Syncing repository 'gentoo' into '/usr/portage'...
            1569592868: >>> Starting rsync with rsync://92.60.51.128/gentoo-portage
            1569592932: === Sync completed for gentoo
            1569592932: >>> Syncing repository 'steam-overlay' into '/var/lib/layman/steam-overlay'...
            1569592932: >>> Starting layman sync for steam-overlay...
            1569592933: >>> layman sync succeeded: steam-overlay
            1569592933: >>> laymansync sez... "Hasta la sync ya, baby!"
            1569592933: === Sync completed for steam-overlay
            1569592933: >>> Syncing repository 'reagentoo' into '/var/lib/layman/reagentoo'...
            1569592933: >>> Starting layman sync for reagentoo...
            1569592933: >>> layman sync succeeded: reagentoo
            1569592933: >>> laymansync sez... "Hasta la sync ya, baby!"
            1569592933: === Sync completed for reagentoo
            1569592933: >>> Syncing repository 'rage' into '/var/lib/layman/rage'...
            1569592934: >>> Starting layman sync for rage...
            1569592934: >>> layman sync succeeded: rage
            1569592934: >>> laymansync sez... "Hasta la sync ya, baby!"
            1569592934: === Sync completed for rage
            1569592934: >>> Syncing repository 'pinkpieea' into '/var/lib/layman/pinkpieea'...
            1569592934: >>> Starting layman sync for pinkpieea...
            1569592935: >>> layman sync succeeded: pinkpieea    
            1569592935: >>> laymansync sez... "Hasta la sync ya, baby!"
            1569592935: === Sync completed for pinkpieea
            1569592937:  *** terminating. 
            adapt from https://stackoverflow.com/a/54023859/11869956
        """
        
        logger = logging.getLogger(f'{self.__nlogger}get::')
        
        completed_re = re.compile(r'^(\d+):\s{1}===.Sync.completed.for.gentoo$')
        collect = [ ]
        keep_running = True
        count = 1
        
        while keep_running:
            logger.debug('Loading last {0} lines from {1}.'.format(self.lastlines, self.emergelog))
            logger.debug('Extracting list of successfully sync for main repo gentoo.')
            for line in self.getlog(self.lastlines):
                if completed_re.match(line):
                    current_timestamp = int(completed_re.match(line).group(1))
                    collect.append(current_timestamp)
                    logger.debug(f'Recording: {current_timestamp}.')
            # Collect is finished.
            # If we got nothing then extend last lines for self.getlog()
            if collect:
                keep_running = False
            else:
                # keep_collecting manage self.lastlines increment
                if self.keep_collecting(count, ['last sync timestamp for main repo \'gentoo\'', 
                                            'never sync...'], 'sync'):
                    count = count + 1
                    keep_running = True
                else:
                    return False
        
        latest = collect[0]
        # Don't need to proceed if list item == 1
        if len(collect) == 1:
            logger.debug(f'Selecting latest: \'{latest}\'.')
            return latest
        # otherwise get the latest timestamp
        logger.debug('Extracting latest sync from:' 
                     + ' {0}'.format(', '.join(str(timestamp) for timestamp in collect)))
        for timestamp in collect:
            if timestamp > latest:
                latest = timestamp
        if latest:
            logger.debug(f'Selecting latest: \'{latest}\'.')
            return latest
        
        logger.error('Failed to found latest update timestamp for main repo gentoo.')
        return False
      
      
      
class LastWorldUpdate(EmergeLogParser):
    """
    Get the last world update informations
    """
    def __init__(self,  lastlines=3000, incomplete=30/100, 
                 nrange=8, advanced_debug=False, **kwargs):
        """
        :param lastlines:  
            Read last n lines from emerge log file (as we don't have
            to read all the file to get last world update)
            Can be tweak but any way if you lower it and if the function
            don't get anything in the first pass it will increment it 
            depending on function keep_collecting(). Default 3000. 
        :param incomplete:
            Enable or disable the search for start but failed update world.
            True for enable without limiter. False for disable. 
            Integer or float to enable limiter. 
            When limiter is enabled, integer setup will filter by arbitary
            number the limit where it will save failed update world or not.
            So, for exemple, if emerge have to update 150 packages but failed
            at 50 and incomplete=45 then this will be recorded. Float setup,
            will filter by percentage. Default 30/100.
        :nrange: 
            List length for numpy to build an exponantial list. Default 8. 
        :advanced_debug:
            Enable or disable advanced debugging. This will make A LOT of log.
            True for enable else False. Default False.
        :return: 
            If detected, a dictionary:
            'start'     :   start timestamp.
            'stop'      :   stop timestamp.
            'total'     :   total packages which have been update.
            'state'     :   'complete' or 'partial' or 'incomplete'
            'failed'    :   if 'complete': 'none', if 'partial' or 'incomplete':
                            package number which failed. 
            Else False.
        """
        
        if not hasattr(logging, 'DEBUG2'):
            raise AttributeError("logging.DEBUG2 NOT setup.")
                
        super().__init__(**kwargs)
               
        self.__nlogger = f'::{__name__}::LastWorldUpdate::'
        self.lastlines = lastlines
        self.incomplete = incomplete
        self.advanced_debug = advanced_debug
        
        # construct exponantial list
        self._range['world'] = numpy.geomspace(self.lastlines, self.log_lines['count'], num=nrange, endpoint=True, dtype=int)
        
        self.group = { }
        
        self.collect = {
            'complete'     :   [ ],
            'incomplete'   :   [ ],
            'partial'       :   [ ]
            }
        
        self.packages_count = 1
        self.compiling = False
        self.package_name = None
        self.current_package = False
        self.keepgoing = False
        self.linecompiling = 0
        self.record = [ ]
        ## RE setup ##
        #   Added @world
        #   Added \s* after (?:world|@world) to make sure we match only @world or world 
        #   Should we match with '.' or '\s' ??
        self.start_opt = re.compile(r'^(\d+):\s{2}\*\*\*.emerge.*\s(?:world|@world)\s*.*$')
        # TODO ?
        # start_parallel = re.compile(r'^\d+:\s{1}Started.emerge.on:.*$')
        #   Detect package dropped due to unmet dependency
        #   for exemple (display in terminal only):
        #       * emerge --keep-going: kde-apps/dolphin-19.08.3 dropped because it requires
        #       * >=kde-apps/kio-extras-19.08.3:5
        #   BUT we get nothing in a emerge.log about that.
        #   We CAN'T have the name of the package.
        #   Just get the number and display some more informations, like:
        #   (+n package(s) dropped) - this has to be TEST more and more
        
        #   --keep-going opts: restart immediatly after failed package ex:
        #       1572887531:  >>> emerge (1078 of 1150) kde-apps/kio-extras-19.08.2 to /
        #       1572887531:  === (1078 of 1150) Cleaning (kde-apps/kio-extras-19.08.2::/usr/portage/kde-apps/kio-extras/kio-extras-19.08.2.ebuild)
        #       1572887531:  === (1078 of 1150) Compiling/Merging (kde-apps/kio-extras-19.08.2::/usr/portage/kde-apps/kio-extras/kio-extras-19.08.2.ebuild)
        #       1572887560:  >>> emerge (1 of 72) x11-libs/gtk+-3.24.11 to /
        #   And the package number should be:
        #       total package number - package failed number
        #   And it should restart to 1
        #   This is NOT true each time, some time emerge jump over more than just
        #   the package which failed (depending of the list of dependency)
        #       For the moment: if opts --keep-going found,
        #      if new emerge is found (mean restart to '1 of n') then this will be treat as
        #       an auto restart, only true if self.current_package == True 
        self.keepgoing_opt = re.compile(r'^.*\s--keep-going\s.*$')
        #   So make sure we start to compile the world update and this should be the first package 
        self.start_compiling = re.compile(r'^\d+:\s{2}>>>.emerge.\(1.of.(\d+)\)\s(.*)\sto.*$')
        #   Make sure it failed with status == 1
        self.failed_line = re.compile(r'(\d+):\s{2}\*\*\*.exiting.unsuccessfully.with.status.\'1\'\.$')
        self.succeeded_line = re.compile(r'(\d+):\s{2}\*\*\*.exiting.successfully\.$')
        # TODO  Give a choice to enable or disable incomplete collect
        # TODO  Improve performance, for now :
        #       Elapsed Time: 2.97 seconds.  Collected 217 stack frames (88 unique)
        #       For 51808 lines read (the whole file) - but it's not intend to be 
        #       run like that
        #       With default settings:
        #       Elapsed Time: 0.40 seconds.  Collected 118 stack frames (82 unique)
        #       For last 3000 lines.
        # BUGFIX This is detected :
        #           1563019245:  >>> emerge (158 of 165) kde-plasma/powerdevil-5.16.3 to /
        #           1563025365: Started emerge on: juil. 13, 2019 15:42:45
        #           1563025365:  *** emerge --newuse --update --ask --deep --keep-going --with-bdeps=y --quiet-build=y --verbose world
        #       this is NOT a parallel emerge and the merge which 'crashed' was a world update...
        #       After some more investigation: this is the only time in my emerge.log (~52000 lines)
        #       After more and more investigation: this is an emerge crashed.
        #       So don't know but i think this could be a power cut or something like that.
        #       And the program raise:
        #           Traceback (most recent call last):
        #           File "./test.py", line 40, in <module>
        #           get_world_info = myparser.last_world_update(lastlines=60000)
        #           File "/data/01/devel/python/syuppod/portagemanager.py", line 876, in last_world_update
        #           group['failed'] = ' '.join(group['failed']) \
        #           TypeError: sequence item 1: expected str instance, NoneType found
        # TODO  After some more test with an old emerge.log, we really have to implant detection 
        #       of parallel merge
                    
    def _compiling(self):
        """
        Manage calls related to compiling lines.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_compiling::')
        
        
        
    
    def _save(self, target):
        """
        Common saving process.
        :target:
            Targeted group from complete, partial or incomplete.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save::')
        
        # The BUG have been fixed but keep this as a safeguard
        # Keep WARNING for each theses safeguard
        for key in 'start', 'stop', 'total':
            try:
                self.group[key]
            except KeyError:
                logger.error(f"When saving '{target} world update' "
                             f"informations, got KeyError for key: '{key}'.")
                logger.error("Skip current process but please report it.")
                # Ok so return and don't save
                return
        
        
        # Make sure start timestamp > stop timestamp
        # Same here keep this as a safeguard, better 
        # to catch error then let all the parser crashed
        # Keep WARNING for each theses safeguard
        if self.group['stop'] <= self.group['start']:
            logger.debug(f"NOT recording {target},"
                         f" start: {self.group['start']},"
                         f" stop: {self.group['stop']},"
                         f" total packages: {self.group['total']},"
                         f" failed: {self.group['failed']}.")
            logger.debug('BUG, rejecting because stop timestamp <= start timestamp')
            return
        
        # Ok so we can validate the collect
        self.collect[target].append(self.group)
        logger.debug(f"Recording {target},"
                    f" start: {self.group['start']},"
                    f" stop: {self.group['stop']},"
                    f" total packages: {self.group['total']},"
                    f" failed: {self.group['failed']}.")
        self.packages_count = 1
     
    def _save_incomplete(self):
        """
        Specific saving process for the incomplete group.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save_incomplete::')
        
        # If self.incomplete == True then save anyway
        # and at this point it should only be True
        if not isinstance(self.incomplete, bool):
            
            # For float
            if not isinstance(self.incomplete, int):
                limit = round(self.group['total'] * self.incomplete)
                _type = 'float'
                logger.debug("Limiter is activated using a percentage"
                            f" template: {self.incomplete}")
            # For int
            else:
                limit = self.incomplete
                _type = 'int'
                logger.debug("Limiter is activated using a fixed"
                            f" template: {self.incomplete}")
            
            if self.packages_count < limit:
                logger.debug("NOT recording incomplete,"
                            f" start: {self.group['start']},"
                            f" stop: {self.group['stop']},"
                            f" total packages: {self.group['total']},"
                            f" failed: {self.group['failed']}.")
            
                msg = f"fixed limit number ({limit})"
                if _type == 'float':
                    msg = (f"packages total ({self.group['total']})"
                           f" * limit ({self.incomplete})"
                           f" (rounded result: {limit})")
                    
                logger.debug("Rejecting because packages count"
                            f" ({self.packages_count}) < {msg}.")
                self.packages_count = 1
                return
        else:
            logger.debug("Limiter is deactived.")
        # Ok everything is validate
        self.group['state'] = 'incomplete'
        self._save('incomplete')
        
    def _save_partial(self):
        """
        Specific saving process for the partial group.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save_partial::')
        
        # Ok so we have to validate the collect
        # This mean that total number of package should be 
        # equal to : total of saved count - total of failed packages
        # This is NOT true every time, so go a head and validate any way
        # TEST Try to detect skipped packages due to dependency
        # First make sure 'failed' key doesn't contain item
        # as NoneType: this mean that parser isn't working proprely
        # Keep WARNING for each theses safeguard
        try:
            for item in self.group['failed']:
                if not item:
                    raise TypeError("'failed' list contain"
                                    " unexpected 'NoneType' item")
        except TypeError as error:
            logger.error("When saving 'partial world update'"
                        f" informations: {error}.")
            logger.error("Skip current process but please report it.")
            self.packages_count = 1
            return
        
        dropped = (self.group['saved']['total'] - 
                   self.group['saved']['count'] -
                   self.packages_count)
        if dropped > 0:
            logger.debug(f"Some package(s) have been dropped: {dropped}")
            self.group['failed'] = (f"{' '.join(self.group['failed'])}"
                                   f" (+{dropped} dropped)")
                                                                                
        self.group['total'] = self.group['saved']['total']
        self.group['state'] = 'partial'
        self._save('partial')
    
    def _save_complete(self):
        """
        Specific saving process for the complete group.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save_complete::')
        
        # Make sure there is no key 'failed' and 'saved'
        # otherwise this method shouln't have been called...
        # Keep WARNING for each theses safeguard
        for key in 'failed', 'saved':
            if key in self.group:
                logger.error("When saving 'complete world update'"
                            " informations: 'group' dictionary contain"
                            f" unexpected key '{key}'.")
                logger.error("Skip current process but please report it.")
                return                    
        
        # For comptability if not 'failed' then 'failed' = 'none'
        self.group['failed'] = 'none'
        self.group['state'] = 'complete'
        self._save('complete')
    
                    
    def get(self):
        """
        Collect and return the informations.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}get::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        incomplete_msg = ''
        if self.incomplete:
            incomplete_msg = ', incomplete'
        
        keep_running =  True
        count = 1                    

        while keep_running:
            logger.debug(f"Loading last {self.lastlines} lines"
                         f" from {self.emergelog}.")
            logger.debug(f"Extracting list of complete{incomplete_msg} and"
                         " partial global update group informations.")
            for line in self.getlog(self.lastlines):
                self.linecompiling += 1
                if self.compiling:
                    # If self.keepgoing is detected, last package could be in complete state
                    # so self.current_package is False but compiling end to a failed match.
                    if self.current_package or (self.keepgoing and \
                        # mean compile as finished (it's the last package)
                        self.packages_count == self.group['total'] and \
                        # make sure emerge was auto restarted
                        # other wise this end to a complete update
                        'total' in self.group['saved'] ):
                        # Save lines
                        if self.current_package:
                            # This will just record line from current package (~10lines max)
                            self.record.append(line)
                            logger.debug2(f"Recording line: '{line}'.")
                        if self.failed_line.match(line):
                            logger.debug2(f"Got failed match at line: {line}.")
                            # We don't care about record here so reset it
                            self.record = [ ]
                            if not 'failed' in self.group:
                                self.group['failed'] = f'at {self.packages_count} ({self.package_name})'
                            # set stop
                            self.group['stop'] = int(self.failed_line.match(line).group(1))
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                            # first test if it's been restarted (self.keepgoing) or it's just incomplete.
                            if self.keepgoing and 'total' in self.group['saved']:
                                logger.debug2("Calling _save_partial().")
                                self._save_partial()
                            elif self.incomplete:
                                logger.debug2("Calling _save_incomplete().")
                                self._save_incomplete()
                            else:
                                logger.debug('NOT recording partial/incomplete, ' 
                                            + 'start: {0}, '.format(self.group['start']) 
                                            + 'stop: {0}, '.format(self.group['stop']) 
                                            + 'total packages: {0}, '.format(self.group['total'])
                                            + 'failed: {0}'.format(self.group['failed']))
                                logger.debug(f'Additionnal informations: keepgoing ({self.keepgoing}), '
                                                f'incomplete ({self.incomplete})')
                            # At then end reset
                            self.packages_count = 1
                            self.current_package = False
                            self.compiling = False
                            self.package_name = None
                            self.keepgoing = False
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                        elif self.keepgoing and self.start_compiling.match(line):
                            logger.debug2("Keepgoing enable, got start"
                                        + " compiling line at" 
                                        + f" line: '{line}'.")
                            # Try to fix BUG describe upstair
                            unexpect_start = False
                            logger.debug2("Start analizing record lines.")
                            for saved_line in self.record:
                                logger.debug2(f"Record: {saved_line}.")
                                # This is also handled :
                                # 1581349345:  === (2 of 178) Compiling/Merging (kde-apps/pimcommon-19.12.2::/usr/portage/kde-apps/pimcommon/pimcommon-19.12.2.ebuild)
                                # 1581349360:  *** terminating.
                                # 1581349366: Started emerge on: févr. 10, 2020 16:42:46
                                # 1581349366:  *** emerge --newuse --update --ask --deep --keep-going --with-bdeps=y --quiet-build=y --verbose world
                                if self.start_opt.match(saved_line):
                                    logger.debug2("Got start opt at recorded"
                                                + f" line: '{saved_line}',"
                                                + " stop analizing.")
                                    unexpect_start = saved_line
                                    break
                            if unexpect_start:
                                # TEST recall this to warning because program now parse emerge.log 
                                # only if it detect inotify changed 
                                logger.warning(f'Parsing {self.emergelog}, raise unexpect'
                                               + ' world update start opt:'
                                               + f' \'{unexpect_start}\'' 
                                               ' (please report this).')
                                # Expect first element in a list is a stop match
                                self.group['stop'] = int(re.match(r'^(\d+):\s+.*$', self.record[0]).group(1))
                                if not 'failed' in self.group:
                                    self.group['failed'] = f'at {self.packages_count} ({self.package_name})'
                                logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                            + f" {self.keepgoing}, linecompiling: "
                                            + f" {self.linecompiling}, package_name:"
                                            + f" {self.package_name}, packages_count:"
                                            + f" {self.packages_count}, compiling:"
                                            + f" {self.compiling}, current_package:"
                                            + f" {self.current_package}.")
                                # First try if it was an keepgoing restart
                                if self.keepgoing and 'total' in self.group['saved']:
                                    logger.debug('Forcing save of current world update group'
                                                + ' using partial (start: {0}).'.format(self.group['start']))
                                    self._save_partial()
                                # incomplete is enable ?
                                elif self.incomplete:
                                    logger.debug('Forcing save of current world update group'
                                                + ' using incomplete (start: {0}).'.format(self.group['start']))
                                    self._save_incomplete()
                                else:
                                    logger.debug('Skipping save of current world update group'
                                                   + ' (unmet conditions).')
                                # Ok now we have to restart everything
                                self.group = { }
                                # Get the timestamp
                                self.group['start'] = int(self.start_opt.match(unexpect_start).group(1))
                                #--keep-going setup
                                if self.keepgoing_opt.match(unexpect_start):
                                    logger.debug2("Got unexcept keepgoing match"
                                                + f" at line: {unexpect_start}.")
                                    self.keepgoing = True
                                self.group['total'] = int(self.start_compiling.match(line).group(1))
                                # Get the package name
                                self.package_name = self.start_compiling.match(line).group(2)
                                self.compiling = True
                                self.packages_count = 1
                                self.group['saved'] = {
                                    'count' :    0
                                }
                                # we are already 'compiling' the first package
                                self.current_package = True
                                logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                                logger.debug2("Skipping everything else...")
                                # skip everything else
                                continue
                            # save the total number of package from the first emerge failed
                            if not 'total' in self.group['saved']:
                                # 'real' total package number
                                self.group['saved']['total'] = self.group['total']
                            self.group['saved']['count'] += self.packages_count
                            # Keep the name of each package which failed
                            if not 'failed' in self.group:
                                self.group['failed'] =  [ ]
                            self.group['failed'].append(self.package_name)
                            # Set name of the package to current one
                            self.package_name = self.start_compiling.match(line).group(2)
                            # get the total number of package from this new emerge 
                            self.group['total'] = int(self.start_compiling.match(line).group(1))
                            self.packages_count = 1
                            self.current_package = True # As we restart to compile
                            self.compiling = True
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                        elif re.match(r'\d+:\s{2}:::.completed.emerge.\(' 
                                            + str(self.packages_count) 
                                            + r'.*of.*' 
                                            + str(self.group['total']) 
                                            + r'\).*$', line):
                            logger.debug2("Got complete match at line:"
                                        + f" '{line}'.")
                            self.current_package = False # Compile finished for the current package
                            self.record = [ ] # same here it's finished so reset record
                            self.compiling = True
                            self.package_name = None
                            if not self.packages_count >= self.group['total']:
                                self.packages_count += 1
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                    elif re.match(r'^\d+:\s{2}>>>.emerge.\('
                                            + str(self.packages_count) 
                                            + r'.*of.*' 
                                            + str(self.group['total']) 
                                            + r'\).*$', line):
                        logger.debug2("Got start compiling match at line:"
                                    + f" '{line}'.")
                        self.current_package = True
                        # reset record as it will restart
                        logger.debug2("Reset recorded lines.")
                        self.record = [ ]
                        logger.debug2("Restart recording lines at line:"
                                    + f" '{line}'.")
                        self.record.append(line) # Needed to set stop if unexpect_start is detected
                        # This is a lot of reapeat for python 3.8 we'll get this :
                        # https://www.python.org/dev/peps/pep-0572/#capturing-condition-values
                        # TODO : implant this ?
                        self.package_name = re.match(r'^\d+:\s{2}>>>.emerge.\('
                                                + str(self.packages_count) 
                                                + r'.*of.*' 
                                                + str(self.group['total']) 
                                                + r'\)\s(.*)\sto.*$', line).group(1)
                        self.compiling = True
                        logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                    elif self.succeeded_line.match(line):
                        logger.debug2(f"Got succeeded match at line: '{line}'.")
                        # Reset record here as well
                        logger.debug2("Reset recorded lines.")
                        self.record = [ ]
                        # set stop
                        self.group['stop'] = int(self.succeeded_line.match(line).group(1))
                        # Make sure it's succeeded the right compile
                        # In case we run parallel emerge
                        if self.packages_count == self.group['total']:
                            self.current_package = False
                            self.compiling = False
                            self.package_name = None
                            self.keepgoing = False
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                            logger.debug2("Calling _save_complete().")
                            self._save_complete()
                        else:
                            logger.debug('NOT recording complete,' 
                                         + ' start: {0},'.format(self.group['start'])
                                         + ' stop: {0},'.format(self.group['stop']) 
                                         + ' packages: {0}'.format(self.group['total']))
                            logger.debug(f'Rejecting because packages count ({self.packages_count})' 
                                         + ' != recorded total packages' 
                                         + ' ({0}).'.format(self.group['total']))
                elif self.start_opt.match(line):
                    logger.debug2(f"Got start opt match at line: '{line}'.")
                    self.group = { }
                    # Get the timestamp
                    self.group['start'] = int(self.start_opt.match(line).group(1))
                    # --keep-going setup
                    if self.keepgoing_opt.match(line):
                        logger.debug2("Keepgoing enable.")
                        self.keepgoing = True
                    self.linecompiling = 0
                    logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                 + f" {self.keepgoing}, linecompiling: "
                                 + f" {self.linecompiling}.")
                # So this is the nextline after self.start_opt match
                # But make sure we got self.start_opt match !
                elif self.linecompiling == 1 and 'start' in self.group:
                    # Make sure it's start to compile
                    if self.start_compiling.match(line):
                        logger.debug2("Got start compiling match at line:"
                                    + f" '{line}'.")
                        # Ok we start already to compile the first package
                        # Get how many package to update 
                        self.group['total'] = int(self.start_compiling.match(line).group(1))
                        # Get the package name
                        self.package_name = self.start_compiling.match(line).group(2)
                        self.compiling = True
                        self.packages_count = 1
                        self.group['saved'] = {
                            'count' :    0
                            }
                        # we are already 'compiling' the first package
                        self.current_package = True
                        logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                    else:
                        # This has been aborded OR it's not the right
                        # start opt match ....
                        logger.debug2("Look like it has been aborded at line:"
                                     + f" '{line}'.")
                        self.group = { }
                        self.compiling = False
                        self.packages_count = 1
                        self.current_package = False
                        self.package_name = None
                        self.keepgoing = False
                        logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {self.keepgoing}, linecompiling: "
                                     + f" {self.linecompiling}, package_name:"
                                     + f" {self.package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {self.compiling}, current_package:"
                                     + f" {self.current_package}.")
                        # don't touch self.linecompiling
                  
            # Do we got something ?
            if self.incomplete:
                if self.collect['complete'] or self.collect['incomplete'] or self.collect['partial']:
                    logger.debug2("Stop running, collect has been successfull.")
                    keep_running = False
                else:
                    # That mean we have nothing ;)
                    if self.keep_collecting(count, ['last global update informations', 
                                'has never been update using \'world\' update schema...'], 'world'):
                        keep_running = True
                        count += 1
                    else:
                        logger.debug("FAILED to collect last world update informations.")
                        return False
            else:
                if self.collect['complete'] or self.collect['partial']:
                    logger.debug2("Stop running, collect has been successfull.")
                    keep_running = False
                else:
                    if self.keep_collecting(count, ['last global update informations', 
                                 'has never been update using \'world\' update schema...'], 'world'):
                        keep_running = True
                        count += 1
                    else:
                        logger.debug("FAILED to collect last world update informations.")
                        return False
                   
        # So now compare and get the highest 'start' timestamp from each list
        logger.debug2("Extracting lastest world update from 'complete'"
                    + f"'{incomplete_msg}' and 'partial' collected lists.")
        tocompare = [ ]
        for target in 'complete', 'incomplete', 'partial':
            if self.collect[target]:
                logger.debug2(f"Extracting latest world update from '{target}'.")
                # This is the 'start' timestamp
                latest_timestamp = self.collect[target][0]['start']
                latest_sublist = self.collect[target][0]
                for sublist in self.collect[target]:
                    logger.debug2(f"Inspecting: {sublist}.")
                    if sublist['start'] > latest_timestamp:
                        latest_timestamp = sublist['start']
                        latest_sublist = sublist
                # Add latest to tocompare list
                logger.debug2(f"Selecting: {latest_sublist}")
                tocompare.append(latest_sublist)
        # Then compare latest from each list 
        # To find latest of latest
        logger.debug('Extracting latest of the latest world update informations.')
        if tocompare:
            latest_timestamp = tocompare[0]['start']
            latest_sublist = tocompare[0]
            for sublist in tocompare:
                logger.debug2(f"Inspecting: {sublist}.")
                if sublist['start'] > latest_timestamp:
                    latest_timestamp = sublist['start']
                    # Ok we got latest of all latest
                    latest_sublist = sublist
        else:
            logger.error('Failed to found latest global update informations.')
            # We got error
            return False
        
        if latest_sublist:
            if latest_sublist['state'] == 'complete':
                logger.debug('Selecting complete,' 
                             + ' start: {0},'.format(latest_sublist['start']) 
                             + ' stop: {0},'.format(latest_sublist['stop'])
                             + ' total packages: {0}'.format(latest_sublist['total']))
            elif latest_sublist['state'] == 'incomplete':
                logger.debug('Selecting incomplete,' 
                             + ' start: {0},'.format(latest_sublist['start']) 
                             + ' stop: {0},'.format(latest_sublist['stop'])
                             + ' total packages: {0}'.format(latest_sublist['total'])
                             + ' failed: {0}'.format(latest_sublist['failed']))
            elif latest_sublist['state'] == 'partial':
                logger.debug('Selecting partial,' 
                             + ' start: {0},'.format(latest_sublist['start']) 
                             + ' stop: {0},'.format(latest_sublist['stop'])
                             + ' total packages: {0}'.format(latest_sublist['saved']['total'])
                             + ' failed: {0}'.format(latest_sublist['failed']))
            return latest_sublist
        else:
            logger.error('Failed to found latest global update informations.')
            return False
        
