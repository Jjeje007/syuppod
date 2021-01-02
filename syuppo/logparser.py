# -*- coding: utf-8 -*-
# -*- python -*- 
# Part of syuppo package
# Copyright © 2019-2021 Venturi Jérôme : jerome dot Venturi at gmail dot com
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
    Base class that implant shared methods for parsing emerge.log
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
    Extract the last sync timestamp
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
    Extract the last world update informations.
    """
    def __init__(self,  lastlines=3000, incomplete=30/100,
                 fragment=30/100, nrange=8, advanced_debug=False,
                 debug_show_all_lines=False, **kwargs):
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
        :param fragment:
            Enable or disable the search for start, autorestart and end to 
            failed update world.
            True for enable without limiter. False for disable. 
            Integer or float to enable limiter. 
            When limiter is enabled, integer setup will filter by arbitary
            number the limit where it will save failed update world or not.
            So, for exemple, if emerge have to update 150 packages but failed
            at 30, restart and definetly failed at 20 and fragment=45 then 
            this will be recorded. Float setup, will filter by percentage. 
            Default 30/100.
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
            'state'     :   'complete', 'partial', 'incomplete' or 'fragment'
            'failed'    :   if 'complete': 'none', if 'partial', 'incomplete'
                            or 'fragment':
                                package number which failed. 
            Else False.
        """
        
        if not hasattr(logging, 'DEBUG2'):
            raise AttributeError("logging.DEBUG2 NOT setup.")
                
        super().__init__(**kwargs)
               
        self.__nlogger = f'::{__name__}::LastWorldUpdate::'
        self.lastlines = lastlines
        self.incomplete = incomplete
        self.fragment = fragment
        self.advanced_debug = advanced_debug
        self.debug_show_all_lines = debug_show_all_lines
        
        # construct exponantial list
        self._range['world'] = numpy.geomspace(self.lastlines, 
                                               self.log_lines['count'], 
                                               num=nrange, endpoint=True,
                                               dtype=int)
        
        self.collect = [ ]
        # Reading line from self.getlog() generator 
        # (EmergeLogParser)
        self.line = False
        
        # Parser to store all extracted informations
        # and all configurations. Can be reset in one
        # time and don't need to change the code every
        # time something new is added / something
        # depreceated is removed.
        self.parser = { }
        
        # Load default parser keys/values
        self._load_default_cfg(init=True)
        
        ## RE setup ##
        self.start_emerge = re.compile(r'^(\d+):\s{1}Started.emerge.on:.*$')
        # Added @world
        # Added \s* after (?:world|@world) to make 
        # sure we match only @world or world 
        # Should we match with '.' or '\s' ??
        self.start_opt = re.compile(r'^(\d+):\s{2}\*\*\*.emerge.*\s'
                                     '(?:world|@world)\s*.*$')
        # So match emerge but NOT follow by --depclean 
        # or --sync or --resume
        self.start_parallel = re.compile(r'^\d+:\s{2}\*\*\*.emerge.'
                                          '(?!.*(--depclean|--sync|--resume)'
                                          '.*$)')
        # match emerge --resume
        self.resume_opt = re.compile(r'^\d+:\s{2}\*\*\*.emerge.*'
                                        '\s--resume\s.*$')
        # Detect package dropped due to unmet dependency
        # for exemple (display in terminal only):
        #   * emerge --keep-going: kde-apps/dolphin-19.08.3 dropped
        #                                       because it requires
        #   * >=kde-apps/kio-extras-19.08.3:5
        # BUT we get nothing in a emerge.log about that.
        # We CAN'T have the name of the package.
        # Just get the number and display some more informations, like:
        # (+n package(s) dropped) - this has to be TEST more and more
        self.keepgoing_opt = re.compile(r'^.*\s--keep-going\s.*$')
        # For --resume make sure its restart
        self.start_resume = re.compile(r'^\d+:\s{2}\*\*\*'
                                        '.Resuming.merge\.\.\.$')
        # So make sure we start to compile the world update 
        # and this should be the first package 
        self.start_compiling = re.compile(r'^\d+:\s{2}>>>.emerge.'
                                           '\(1.of.(\d+)\)'
                                           '\s(.*)\sto.*$')
        # For finished line:
        #   1569179409:  *** Finished. Cleaning up...
        self.finished_line = re.compile(r'(\d+):\s{2}\*\*\*.Finished'
                                         '\..Cleaning up\.\.\.$')
        # For terminating line:
        #   1563026610:  *** terminating.
        self.terminating_line = re.compile(r'(\d+):\s{2}\*\*\*.terminating\.$')
        # For exiting line:
        self.exiting_line = re.compile(r'\d+:\s{2}\*\*\*.exiting\s{1}'
                                        '(?:successfully|unsuccessfully).*$')
        # Make sure it failed with status == 1
        self.failed_line = re.compile(r'(\d+):\s{2}\*\*\*.exiting.'
                                       'unsuccessfully.with.status.\'1\'\.$')
        self.succeeded_line = re.compile(r'(\d+):\s{2}\*\*\*.exiting.'
                                          'successfully\.$')
        # TODO Give a choice to enable or disable 
        # incomplete/fragment collect
        
        # TODO improve performance:
        # For 51808 lines read (the whole file) - but it's not 
        #   Elapsed Time: 2.97 seconds.  Collected 217 stack 
        #                                  frames (88 unique)
        # 
        # For 129761 lines read:
        #   23296316 function calls (22688021 primitive calls)
        #                                    in 10.764 seconds
        
        # With default settings 3000lines:
        #   OLD version: Elapsed Time: 0.40 seconds. Collected 118 
        #                                  stack frames (82 unique)
        #   NEW version: 508617 function calls (495529 primitive calls)
        #                                              in 0.316 seconds
    
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
        
        fragment_msg = ' and partial'
        if self.fragment:
            fragment_msg = ', partial and fragmented'
            
        keep_running =  True
        count = 1                    

        while keep_running:
            logger.debug(f"Loading last {self.lastlines} lines"
                         f" from {self.emergelog}.")
            logger.debug(f"Extracting list of complete{incomplete_msg}"
                         f"{fragment_msg} group for global"
                         "update informations.")
            for self.line in self.getlog(self.lastlines):
                # Show all logparser line for extra debugging
                if self.debug_show_all_lines:
                    logger.debug2(f"Loading current line: {self.line}")
                
                self.parser['line'] += 1
                if self.parser['running']:
                    # everything start with self._running()
                    self._running()
                elif self.start_opt.match(self.line):
                    logger.debug2(f"start_opt match at line: {self.line}")
                    self._config_detected()
                # So check if nextline match start_opt.
                # self.parser['line'] is set to '0' in 
                # self._config_detected()
                elif (self.parser['line'] == 1 
                      and 'start' in self.parser['group']):
                    # Have to be validate
                    self._validate_start()
           
            
            # Parsing finished 
            if self.collect:
                logger.debug2("Stop running, collect have been successfull.")
                keep_running = False
            elif self.keep_collecting(count, 
                                      ['last global update informations', 
                                       "have never been update using 'world'"
                                       " update schema..."], 'world'):
                keep_running = True
                count += 1
            else:
                logger.debug("FAILED to collect last world update informations.")
                return False
          
        # So now compare and get the highest 'start' timestamp from each list
        logger.debug2("Extracting lastest world update informations from "
                      f"complete{incomplete_msg}{fragment_msg}"
                      " collected lists.")
        
        latest_timestamp = self.collect[0]['start']
        latest_sublist = self.collect[0]
        for sublist in self.collect:
            logger.debug2(f"Inspecting: {sublist}.")
            if sublist['start'] > latest_timestamp:
                latest_timestamp = sublist['start']
                # Ok we got latest
                latest_sublist = sublist
        
        if latest_sublist:
            failed = f" failed: {latest_sublist['failed']}"
            if latest_sublist['state'] == 'complete':
                failed = ''
                
            logger.debug(f"Selecting {latest_sublist['state']},"
                         f" start: {latest_sublist['start']}" 
                         f" stop: {latest_sublist['stop']}"
                         f" total packages: {latest_sublist['total']}"
                         f"{failed}")
            return latest_sublist
        else:
            logger.error('FAILED to found latest global update informations.')
            return False
        
    def _load_default_cfg(self, include=(), exclude=(),
                          init=False, verbose=False):
        """
        Load or reload default attrs.
        
        :include:
            For partial reload, set keys(s) that should
            be reload. Default '()'.
        :exclude:
            For partial reload, set keys(s) that should
            not be reload. Default '()'.
        :init:
            Initial load. Default False.
        :verbose:
            Toggle verbose for logging, only with 
            advanced_debug=True. Default False.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_load_default_cfg::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # Default keys/values:
        __defaults = {
            # For saving current world update 'group' informations.
            'group'         :   { },
            # Current packages count while analizing world
            # update 'group' informations
            # EX: emerge (n of total): count is 'n'
            'count'         :   1,
            # Current package name:
            # EX: emerge (158 of 165) kde-plasma/powerdevil-5.16.3
            # name: 'kde-plasma/powerdevil-5.16.3'
            'name'          :   None,
            # The current world update 'group' informations
            # is running.
            'running'      :   False,
            # Analyzing the current package status
            # Trying to match status end: complete/failed
            'current'       :   False,
            # If keepgoing_opt match then keepgoing = True,
            # else False. keepgoing True activated partial 
            # fragment group status (for fragment if enable).
            'keepgoing'     :   False,
            # The internal line number from within a new match found.
            # This is almost dedicated to match something at a 
            # specific line number without using next().
            # Set it to 2 to avoid calling _config_detected after
            # first line read at the first load (even if nothing 
            # was detected...)
            'line'          :  2,
            # The specifics lines recorded. Use to do a reverse scan.
            'record'        :   [ ],
            # This is set when finished_line is match and use to
            # validate the match.
            'finished'      :   False,
            # Same as above but for complete match
            'completed'     :   False,
            # Same as above but for unexcepted start_opt match.
            'started'       :   False,
            # This is to indicate that finished have been
            # process and unvalidated so skip also next terminating
            # match.
            'saved'         :   False,
            # TEST detect parallel start
            'parallel'      :   {
                'start'     :   False,
                'total'     :   None
                },
            # For detecting --resume opt
            'resume'        :   False
            }
        
        # Using both include and exclude is useless
        if include:
            msg = (f"Partial reload of default attributes for: "
                   f"{', '.join(include)}.")
        elif exclude:
            msg = (f"Partial reload of default attributes excluding: "
                   f"{', '.join(exclude)}.")
        elif init:
            msg = "Loading of all default attributes."
        else:
            msg = "Reloading of all default attributes."
                
        logger.debug2(msg)
        
        for key, value in __defaults.items():
            if include and not key in include:
                parser_value = self.parser[key]
                if verbose:
                    logger.debug2("Skip reload for not included key:"
                                 f" {key}, current value: {parser_value}")
                continue
            if exclude and key in exclude:
                parser_value = self.parser[key]
                if verbose:
                    logger.debug2("Skip reload for excluded key:"
                                 f" {key}, current value: {parser_value}")
                continue
            if verbose:
                logger.debug2(f"Reloading key: {key}, value: current:"
                              f" {parser_value}, default: {__defaults[key]}")
            self.parser[key] = __defaults[key]
            
    def _config_detected(self):
        """
        World update start setup
        """
        logger = logging.getLogger(f'{self.__nlogger}_config_detected::')
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        #self.parser['group'] = { }
        self._load_default_cfg(include=('group',))
        # Get the timestamp
        self.parser['group']['start'] = int(self.start_opt.match(self.line).group(1))
        # --keep-going setup
        if self.keepgoing_opt.match(self.line):
            logger.debug2(f"keepgoing_opt match at line: {self.line}")
            self.parser['keepgoing'] = True
        self.parser['line'] = 0
        
    def _validate_start(self):
        """
        World update start validation
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_validate_start::')
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # Make sure it's start to compile
        if self.start_compiling.match(self.line):
            logger.debug2("start_compiling match at line:"
                        + f" '{self.line}'.")
            # Ok we start already to compile the first package
            # Get how many package to update
            total = int(self.start_compiling.match(self.line).group(1))
            self.parser['group']['total'] = total
            # Get the package name
            name = self.start_compiling.match(self.line).group(2)
            self.parser['name'] = name
            self.parser['running'] = True
            self.parser['count'] = 1
            # we are already 'compiling' the first package
            self.parser['current'] = True
        else:
            # This has been aborded OR it's not the right
            # start opt match ....
            logger.debug2("Look like it has been aborded or something"
                          f" is wrong at line: '{self.line}'.")
            # reload default but not key line
            self._load_default_cfg(exclude=('line',))            
    
    def _running(self):
        """
        Processing of matches and calls during 'compiling' state.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_running::')
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
    
        if self.parser['current']:
            self._current_package()
        
        # Start compiling next package
        # Need >= python3.8 for capturing condition values
        # https://www.python.org/dev/peps/pep-0572/#capturing-condition-values
        elif match := re.match(r'^\d+:\s{2}>>>.emerge.\('
                      + str(self.parser['count']) 
                      + r'.*of.*' 
                      + str(self.parser['group']['total']) 
                      + r'\)\s(.*)\sto.*$', self.line):
            logger.debug2("start_current (package) match at line:"
                          f" {self.line}")
            self.parser['current'] = True
            # reset record as it will restart
            self.parser['record'] = [ ]
            # Needed to set stop if unexpect_start is detected
            self.parser['record'].append(self.line) 
           
            self.parser['name'] = match.group(1)
            self.parser['running'] = True
        
        # For finished we should catch unsuccessfully exit
        # AND ONLY on next line: linecompiling == 1
        # linecompiling is reset to 0 in _current_package()
        elif self.parser['finished'] and self.parser['line'] == 1:
            if self.failed_line.match(self.line):
                logger.debug2("failed_line (finished_line) match at line:"
                             f" {self.line}")
                # Call self._analyze_finished_match()
                # Because it's could be ambiguous
                # TODO TODO !
                if self.parser['parallel']['total']:
                    logger.debug2("parallel merge (failed_line)"
                                 " may also be running...")
                    self._analyze_finished_match()
                # Set only stop, everything else is done in
                # self._save_switcher()
                timestamp = self.failed_line.match(self.line).group(1)
                self.parser['group']['stop'] = int(timestamp)
                self._save_switcher()
            else:
                # TEST so if failed_line not detected this could be
                # a false positive
                self.parser['finished'] = False
                self.parser['current'] = True
                self.parser['saved'] =  True
                logger.debug2(f"finished_line aborded at line: {self.line}")
                if self.parser['parallel']['total']:
                    # For the moment go ahead and if this was not
                    # the current world update that failed then
                    # it's the parallel that succeeded :)
                    # WARNING If there is more than one paralle merge
                    # then it's going to be really really a mess ....
                    logger.debug2("start_parallel (finished_line):" 
                                 " 'total' reset, look like it's"
                                 f" succeeded at line: {self.line}")
                    self.parser['parallel']['total'] = None
        
        # Here it's a complete process BUT this doesn't 
        # mean we'll have only a successfully match:
        # If self.parser['keepgoing'] is detected, last package could be in
        # complete state but compiling end to a failed match. 
        elif self.parser['completed']:
            if self.succeeded_line.match(self.line):
                logger.debug2("succeeded_line (completed) match"
                             f" at line: {self.line}")
                # Set stop 
                timestamp = self.succeeded_line.match(self.line).group(1)
                self.parser['group']['stop'] = int(timestamp)
                self._save_complete()
                # reset to default
                self._load_default_cfg()
            elif self.failed_line.match(self.line):
                logger.debug2("failed_line (completed) match at line:"
                             f" {self.line}")
                # Set stop timestamp
                timestamp = self.failed_line.match(self.line).group(1)
                self.parser['group']['stop'] = int(timestamp)
                # The only choice is partial
                self._save_partial_fragment('partial')
                # reset also
                self._load_default_cfg()
        
        # For started we should catch an start_opt
        # match at linecompiling = 1
        # same here linecompiling is reset in _current_package()
        elif self.parser['started'] and self.parser['line'] == 1:
            # This is validate
            if self.start_opt.match(self.line):
                logger.debug2(f"start_opt (started) match at line: {self.line}")
                
                # Make sure we get stop timestamp or
                # just skip current group 
                # parser attrs is reset in _set_stop_timestamp()
                # only if failed to extracted.
                if self._set_stop_timestamp():
                    # Then after: save the current group (it's failed)
                    # It will set all attr to default
                    self._save_switcher()
                    # Then call _config_detected()
                    self._config_detected()
                self.parser['started'] = False
                # After let self.get() do the job
            
            # TEST get parallel start-up. So that mean 
            # if it's not a world update start than it could be
            # a parallel start: this will not match --depclean
            # --sync AND --resume
            elif self.start_parallel.match(self.line):
                logger.debug2("start_parallel (started) match at"
                             f" line: {self.line}")
                # Ok so keep running and just set key parallel to True
                # So we can get new emerge info (total package) in _current_package()
                self.parser['parallel']['start'] = True
                self.parser['started'] = False
                # Restart
                self.parser['current'] = True
                # Reset 'line' to 0 so _current_package can detect
                # start_compiling
            
            # TEST this could be an --resume restart
            elif self.resume_opt.match(self.line):
                logger.debug2("resume_opt (started) match at line:"
                             f" {self.line}")
                self.parser['line'] = 0
                # Restart
                self.parser['current'] = True
                self.parser['resume'] = True
            
            # Ok so if not validate we should restart to current_package
            else:
                # reset self.parser['started']
                self.parser['started'] = False
                # Then just restart
                self.parser['current'] = True
            
    def _current_package(self):
        """
        Processing of matches and calls during 'current' state is True.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_current_package::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # Record each line between start_compiling match
        # and completed emerge match, this is almost
        # 10 lines (if there is no start_parallel
        # match...)
        self.parser['record'].append(self.line)
       
        # We can match:
        # completed emerge (so current_package 
        # successfully merge)
        # EXEMPLE:
        #   1572890844:  >>> emerge (67 of 69) kde-apps/eventviews-19.08.2 to /
        #   1572890844:  === (67 of 69) Cleaning {...CUT...}
        #   1572890844:  === (67 of 69) Compiling/Merging {...CUT...}
        #   1572890859:  === (67 of 69) Merging {...CUT...}
        #   1572890861:  >>> AUTOCLEAN: kde-apps/eventviews:5
        #   1572890861:  === Unmerging... (kde-apps/eventviews-19.08.2)
        #   1572890862:  >>> unmerge success: kde-apps/eventviews-19.08.2
        #   1572890863:  === (67 of 69) Post-Build Cleaning {...CUT...}
        #   1572890863:  ::: completed emerge (67 of 69) kde-apps/eventviews-19.08.2 to /
        if re.match(r'\d+:\s{2}:::.completed.emerge.\(' 
                    + str(self.parser['count']) 
                    + r'.*of.*' 
                    + str(self.parser['group']['total']) 
                    + r'\).*$', self.line):
            logger.debug2("stop_current (package) match at line:"
                          f" {self.line}")
            self._pkg_complete()
                    
        # We can match:
        # started line if emerge crash also or CTRL-C or bug ??
        # EXEMPLE:
        # 1605181577:  === (104 of 157) Cleaning {...CUT...}
        # 1605181578:  === (104 of 157) Compiling/Merging {...CUT...}
        # 1605183558: Started emerge on: nov. 12, 2020 13:19:17
        # 1605183558:  *** emerge --newuse --update --ask --deep --keep-going
        # {...SPLIT...}    --with-bdeps=y --quiet-build=y --regex-search-auto=y 
        # {...SPLIT...}    --verbose @world
        # 1605183716:  >>> emerge (1 of 54) x11-apps/xkbcomp-1.4.4 to /
        # 1605183716:  === (1 of 54) Cleaning {...CUT...}
        elif self.start_emerge.match(self.line):
            logger.debug2(f"start_emerge match at line: {self.line}")
            # Same here this have to be validate
            # Because its should have an start_opt match
            # at the nextline.
            self.parser['started'] = True
            self.parser['line'] = 0
            self.parser['current'] = False
        
        ### TEST get total package if key 'start' is True
        # Here could be the line after start_emerge match: 
        # it was invalidate but it match a parallel merge
        # WARNING This could take advantage over keepgoing
        # restart !! WARNING
        elif self.parser['parallel']['start']:
            # After 10 lines don't bother try to match
            # this have been aborded and this could generate
            # some false positive if searching again and
            # again... (ie: keepgoing restart). TEST
            if (self.parser['line'] < 11 and
                    self.start_compiling.match(self.line)):
                # Ok so just save total package (this could reduce 
                # false positive)
                total = int(self.start_compiling.match(self.line).group(1))
                self.parser['parallel']['total'] = total
                logger.debug2("start_compiling (start_parallel), total saved:"
                             f" {total}, at line: {self.line}, ")
                # reset start
                self.parser['parallel']['start'] = False
            elif self.parser['line'] > 10:
                logger.debug2("start_parallel: NO match after 10 lines,"
                             " abording search...")
                self._load_default_cfg(include=('parallel',))
        
        ### TEST detect --resume and treat as keepgoing restart
        elif self.parser['resume']:
            if self.parser['line'] == 1:
                if self.start_resume.match(self.line):
                    logger.debug2("start_resume (resume) match"
                                 f" at line: {self.line}")
                    # Just restart so we can check next line
                else:
                    logger.debug2(f"start_resume aborded at line: {self.line}")
                    self.parser['resume'] = False
                    # This have to be TEST to know what to do in this
                    # situation...
            elif self.parser['line'] == 2:
                # Ok make sure we got an start_compiling match
                # before calling _pkg_keepgoing()
                if self.start_compiling.match(self.line):
                    logger.debug2("start_compiling (start_resume) match"
                                 f" at line: {self.line}")
                    logger.debug2("start_compiling (start_resume) processing"
                                 "like keepgoing restart.")
                    self._pkg_keepgoing()
                else:
                    logger.debug2("start_compiling (start_resume) aborded"
                                 f" at line: {self.line}")
                    self.parser['resume'] = False
                    # TEST same as above
            else:
                logger.debug2(f"resume_opt aborded at line: {self.line}")
                self.parser['resume'] = False
                
        # WARNING ALL the rest could generate false positive WARNING
        # We can match an autorestart only if:
        #   keepgoing was enable    AND
        #   current package count + current total package <= matched total package
        # EXEMPLE:
        # 1576005571:  >>> emerge (176 of 183) kde-plasma/powerdevil-5.17.4 to /
        # 1576005571:  === (176 of 183) Cleaning {...CUT...}
        # 1576005571:  === (176 of 183) Compiling/Merging {...CUT...}
        # 1576005596:  >>> emerge (1 of 6) kde-plasma/systemsettings-5.17.4 to /
        # So its restart right after failing... (and in this exemple
        # it skip 1 package). This could generate A LOT of false positive...
        elif (self.start_compiling.match(self.line) and 
                self.parser['keepgoing']):
            total = int(self.start_compiling.match(self.line).group(1))
            msg = ("current total: "
                   f"{self.parser['group']['total']}, count: "
                   f"{self.parser['count']}, matched total: {total}")
            logger.debug2("start_compiling (keepgoing_opt) match"
                        f" at line: {self.line}")
            if self.parser['count'] + total <= self.parser['group']['total']:
                logger.debug2(f"keepgoing restart match: {self.line}")
                logger.debug2(f"keepgoing enable: {msg}")
                self._pkg_keepgoing()
            else:
                logger.debug2("start_compiling (keepgoing) aborded"
                             f" at line: {msg}")
            
        # Fourth False: we can match an finished line if
        # world update failed (even with keepgoing opt enable)
        # EXEMPLE (with keepgoing opt enable)
        # 1569179009:  >>> emerge (122 of 172) dev-qt/qtwebengine-5.12.5 to /
        # 1569179009:  === (122 of 172) Cleaning {...CUT...}
        # 1569179010:  === (122 of 172) Compiling/Merging {...CUT...}
        # 1569179409:  *** Finished. Cleaning up...
        # 1569179410:  *** exiting unsuccessfully with status '1'.
        # 1569179411:  *** terminating.
        # There is always the finished line right after.
        # AND this should exit unsuccessfully !
        # Same here: it could gnerate false positive...
        elif self.finished_line.match(self.line):
            logger.debug2(f"finished_line match at line: {self.line}")
            # But we still have to validate 
            # Because if exit successfully or anything else
            # to the nextline then this should be ignored
            # so just set:
            self.parser['line'] = 0
            self.parser['finished'] = True
            self.parser['current'] = False
       
    def _set_stop_timestamp(self):
        """
        Analyze record list and get stop
        timestamp
        """
        name = f'{self.__nlogger}_set_stop_timestamp::'
        logger = logging.getLogger(name)
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        if not self.parser['record']:
            logger.error("When extracting world update informations,"
                         " found 'record' list empty.")
            logger.error("Skip current process but please report it.")
            # Reset everything
            self._load_default_cfg()
            return False
        
        stop = re.compile(r'^(\d+):\s{2}===\s\('
                          + str(self.parser['count'])
                          + r'\s*of\s*'
                          + str(self.parser['group']['total'])
                          + r'\).*$')
        
        logger.debug2("Extracting stop timestamp from record list")
        timestamp = False
        for line in reversed(self.parser['record']):
            logger.debug2(f"Analyzing: {line}")
            if stop.match(line):
                timestamp = stop.match(line).group(1)
                logger.debug2(f"Timestamp extracted: {timestamp}"
                             f" from: {line}")
                break
        
        if not timestamp:
            logger.error("When extracting world update informations,"
                         " failed to set stop timestamp.")
            logger.error("Skip current process but please report it.")
            # same here reset everything
            self._load_default_cfg()
            return False
        
        self.parser['group']['stop'] = int(timestamp)
        return True        
    
    def _analyze_finished_match(self):
        """
        Analyze ambiguous finished line
        """
        name = f'{self.__nlogger}_analyze_finished_match::'
        logger = logging.getLogger(name)
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # parallel merge have been detected 
        # so we have to analyze the record list
        # to be sure which one that ended and make 
        # a decision if we stop or not.
        # TODO TODO
        logger.warning("_analyze_finished_match have been called!")
        # For now, just print the record list
        for item in self.parser['record']:
            # print to debug because we need this 
            # informations to see what to do / write
            logger.debug(f"record list: {item}")
                    
    def _pkg_complete(self):
        """
        'complete' configuration.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_pkg_complete::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # Compile finished for the current package
        self.parser['current'] = False 
        self.parser['record'] = [ ]
        # But it's not here to make the decision
        # that this current compiling group 
        # is finished
        self.parser['running'] = True
        self.parser['name'] = None
        if self.parser['count'] < self.parser['group']['total']:
            self.parser['count'] += 1
        # IF count == total then compiling group finished 
        elif self.parser['count'] == self.parser['group']['total']:
            logger.debug2("stop_compiling reached: current count: "
                         f"{self.parser['count']}, current total count: "
                         f"{self.parser['group']['total']}")
            self.parser['completed'] = True
        elif self.parser['count'] > self.parser['group']['total']:
            logger.error("When searching for last world update informations:"
                           " found current packages count > total packages")
            logger.error(f"Start timestamp: {self.parser['group']['start']}, current"
                         f" packages count: {self.parser['count']}, total:"
                         f" {self.parser['group']['total']}")
            logger.error("Skip current process but please report it.")
            self._load_default_cfg()
    
    def _pkg_keepgoing(self):
        """
        'keepgoing' configuration.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_pkg_keepgoing::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
            
        # If this is the first time we setup keepgoing
        # there is no key saved...
        if not 'saved' in self.parser['group']:
            self.parser['group']['saved'] = { }
            # Record the total number of package 
            # from the first process (original one)
            self.parser['group']['saved']['total'] = self.parser['group']['total']
            # Add also key 'count'
            self.parser['group']['saved']['count'] = 0
        # ...and also no list for key failed
        if not 'failed' in self.parser['group']:
            self.parser['group']['failed'] =  [ ]
       
        # Save current packages count
        self.parser['group']['saved']['count'] += self.parser['count']
        # Keep the name of each package which failed
        self.parser['group']['failed'].append(self.parser['name'])
        
        # Set name of the package to current one
        self.parser['name'] = self.start_compiling.match(self.line).group(2)
        # get the total number of package from this new emerge 
        self.parser['group']['total'] = int(self.start_compiling.match(self.line).group(1))
        # We already compiling the first package
        self.parser['count'] = 1
        self.parser['current'] = True 
        self.parser['running'] = True
        
        logger.debug2(f"Stats: group: {self.parser['group']}, keepgoing:"
                    + f" {self.parser['keepgoing']}, linecompiling: "
                    + f" {self.parser['line']}, package_name:"
                    + f" {self.parser['name']}, packages_count:"
                    + f" {self.parser['count']}, compiling:"
                    + f" {self.parser['running']}, current_package:"
                    + f" {self.parser['current']}.")
          
    def _save(self, target):
        """
        Common saving process.
        :target:
            Targeted group from complete, partial, incomplete
            or fragment.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # The BUG have been fixed but keep this as a safeguard
        # Keep WARNING for each of theses safeguard
        for key in 'start', 'stop', 'total':
            try:
                self.parser['group'][key]
            except KeyError:
                logger.error(f"When saving '{target} world update' "
                             f"informations, got KeyError for key: '{key}'.")
                logger.error("Skip current process but please report it.")
                # Ok so return and don't save
                return
        
        
        # Make sure start timestamp > stop timestamp
        # Same here keep this as a safeguard, better 
        # to catch error then let all the parser crashed
        # Keep WARNING for each of theses safeguard
        if self.parser['group']['stop'] <= self.parser['group']['start']:
            logger.debug(f"NOT recording {target},"
                         f" start: {self.parser['group']['start']},"
                         f" stop: {self.parser['group']['stop']},"
                         f" total packages: {self.parser['group']['total']},"
                         f" failed: {self.parser['group']['failed']}.")
            logger.debug('BUG, rejecting because stop timestamp <= start timestamp')
            return
        
        # Ok so we can validate the collect
        self.collect.append(self.parser['group'])
        logger.debug(f"Recording {target},"
                    f" start: {self.parser['group']['start']},"
                    f" stop: {self.parser['group']['stop']},"
                    f" total packages: {self.parser['group']['total']},"
                    f" failed: {self.parser['group']['failed']}.")
        self.parser['count'] = 1
     
    def _save_incomplete_fragment(self, arg):
        """
        Specific saving process for the incomplete and fragment group.
        This is handle not complete process without keepgoing set or
        fragment process which is a 'mix' between incomplete and
        partial.
        :arg:
            Targeted saving process: incomplete or fragment.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}'
                                   '_save_incomplete_fragment::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
            
        logger.debug(f"Running with arg: {arg}")
        
        target = getattr(self, arg)
        # If target == True then save anyway
        # and at this point it should only be True
        if not isinstance(target, bool):
            
            # For float
            if not isinstance(target, int):
                limit = round(self.parser['group']['total'] * target)
                _type = 'float'
                logger.debug("Limiter is activated using a percentage"
                            f" template: {target * 100}%")
            # For int
            else:
                limit = target
                _type = 'int'
                logger.debug("Limiter is activated using a fixed"
                            f" template: {target}")
            
            if self.parser['count'] < limit:
                logger.debug(f"NOT recording {arg},"
                            f" start: {self.parser['group']['start']},"
                            f" stop: {self.parser['group']['stop']},"
                            f" total packages: {self.parser['group']['total']},"
                            f" failed: {self.parser['group']['failed']}.")
            
                msg = f"fixed limit number ({limit})"
                if _type == 'float':
                    msg = (f"packages total ({self.parser['group']['total']})"
                           f" * limit ({target})"
                           f" (rounded result: {limit})")
                    
                logger.debug("Rejecting because packages count"
                            f" ({self.parser['count']}) < {msg}.")
                self.parser['count'] = 1
                return
        else:
            logger.debug("Limiter is deactived.")
        # everything is validate
        self.parser['group']['state'] = arg
        self._save(arg)
        
    def _save_partial_fragment(self, arg):
        """
        Specific saving process for the partial and fragment group.
        This is handle process keepgoing which end to a complete 
        (partial) and incomplete (fragment) state.
        :arg:
            Targeted saving process: incomplete or fragment.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save_partial_fragment::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        logger.debug(f"Running with arg: {arg}")
        
        # Ok so we have to validate the collect
        # This mean that total number of package should be 
        # equal to : total of saved count - total of failed packages
        # This is NOT true every time, so go a head and validate any way
        # TEST Try to detect skipped packages due to dependency
        # First make sure 'failed' key doesn't contain item
        # as NoneType: this mean that parser isn't working proprely
        # Keep WARNING for each theses safeguard
        try:
            for item in self.parser['group']['failed']:
                if not item:
                    raise TypeError("'failed' list contain"
                                    " unexpected 'NoneType' item")
        except TypeError as error:
            logger.error(f"When saving '{arg} world update'"
                        f" informations: {error}.")
            logger.error("Skip current process but please report it.")
            self.parser['count'] = 1
            return
        
        # Get the recorded number of package
        self.parser['group']['total'] = self.parser['group']['saved']['total']
        
        # Calculate dropped package (if any)
        dropped = (self.parser['group']['saved']['total'] - 
                   self.parser['group']['saved']['count'] -
                   self.parser['count'])
        
        msg = ''
        if dropped > 0:
            logger.debug(f"Package(s) which have been dropped: {dropped}")
            msg = f" (+{dropped} dropped)"
        
        if arg == 'partial':
            self.parser['group']['failed'] = (f"{' '.join(self.parser['group']['failed'])}"
                                             f"{msg}.")
            self.parser['group']['state'] = 'partial'
            self._save('partial')
            
        elif arg == 'fragment':
            additionnal_msg = ''
            failed = f"at {self.parser['group']['failed'].pop()}"
            # As we get the last element (and remove)
            # Make sure we have element left
            if len(self.parser['group']['failed']) > 0:
                additionnal_msg = (" and also: "
                                   f"{' '.join(self.parser['group']['failed'])}")
            
            self.parser['group']['failed'] = f"{failed}{additionnal_msg}{msg}"
            # Add total package count for saving with
            # self._save_incomplete_fragment()
            self.parser['count'] = (self.parser['count'] + 
                                   self.parser['group']['saved']['count'])
            # Don't need to set state here it will be set in:
            self._save_incomplete_fragment('fragment')
          
    def _save_complete(self):
        """
        Specific saving process for the complete group.
        This is handle complete process.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_save_complete::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
        
        # Make sure there is no key 'failed' and 'saved'
        # otherwise this method shouln't have been called...
        # Keep WARNING for each of theses safeguard
        for key in 'failed', 'saved':
            if key in self.parser['group']:
                logger.error("When saving 'complete world update'"
                            " informations: 'group' dictionary contain"
                            f" unexpected key '{key}'.")
                logger.error("Skip current process but please report it.")
                return                    
        
        # For comptability if not 'failed' then 'failed' = 'none'
        self.parser['group']['failed'] = 'none'
        self.parser['group']['state'] = 'complete'
        self._save('complete')    
        
    def _save_switcher(self):
        """
        Call _save_* depending on condition.
        This is only for specific failed match: 'finished'
        because it could be 'incomplete' or 'fragment'.
        """
        
        logger = logging.getLogger(f'{self.__nlogger}_pkg_terminate::')
        
        if self.advanced_debug:
            logger.setLevel(logging.DEBUG2)
            
        # Search over self.parser['group'] to know which
        # _save_*() to call
        # But there is only two choices: incomplete
        # or fragment. So if there is key 'saved' in
        # self.parser['group'] and key 'total' in self.parser['group']['saved']
        # then it's fragment else it's incomplete
        if ('saved' in self.parser['group'] 
           and 'total' in self.parser['group']['saved']):
            # Ok so we have to add last failed to the list
            self.parser['group']['failed'].append(self.parser['name'])
            logger.debug2("Calling _save_partial_fragment('fragment')")
            self._save_partial_fragment('fragment')
        else:
            # same here add failed package_name
            self.parser['group']['failed'] = (f"at {self.parser['count']}"
                                              f" ({self.parser['name']})")
            logger.debug2("Calling _save_incomplete_fragment('incomplete')")
            self._save_incomplete_fragment('incomplete')
        # Then reset everything
        self._load_default_cfg()
