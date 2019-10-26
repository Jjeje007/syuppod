# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

# Version: 0.1

import os
import pathlib
import re
import errno
import sys
import tempfile
from logger import MainLoggingHandler



class StateInfo:
    """Write, edit or get info to and from state file"""
    def __init__(self, pathdir, runlevel, loglevel):
        self.pathdir = pathdir
                
        # Init logger
        self.logger_name = f'::{__name__}::StateInfo::'
        mainlog = MainLoggingHandler(self.logger_name, self.pathdir['debuglog'])
        self.log = getattr(mainlog, runlevel)()
        self.log.setLevel(loglevel)
        
        self.stateopts = (
            # '# Wrote by syuppod version: __version__' TODO : Writing version so we can know which version wrote the state file 
            # TODO : '# Pull Opts',
            'pull count: 0', 
            'pull error: 0',
            'pull state: never pull',
            # Setting default to '0.0' as StrictVersion compare will failed if only '0' or string
            # '0.0' -> factory | '0.0.0' -> empty list
            # TODO : '# Branch Opts',
            'branch all local: 0.0',
            'branch all remote: 0.0',
            'branch available all: 0.0',
            'branch available know: 0.0',
            'branch available new: 0.0', 
            # TODO : '# Kernel Opts',
            'kernel all: 0.0',
            'kernel installed all: 0.0',
            'kernel installed running: 0.0',
            'kernel available all: 0.0',
            'kernel available know: 0.0',
            'kernel available new: 0.0',
            # TODO : '# Sync Opts',
            'sync count: 0',
            'sync error: 0',
            'sync state: never sync',
            'sync update: unknow',
            'sync timestamp: 0',
            # TODO: '# World Opts
            'world update: unknow',
            'world packages: 0',
            'world last start: 0',
            'world last stop: 0',
            'world last state: unknow',
            'world last packages: 0',
            'world last failed at: 0',
            # TODO: '# Portage Opts',
            'portage available: False',
            'portage current: 0.0',
            'portage latest: 0.0'
            )
        
    
    def config(self):
        """Create, check state file and its options"""
        # If new file, factory info
        # TODO: add options to reset {pull,sync}_count to factory
        self.log.name = f'{self.logger_name}config::'
        
        try:
            if not pathlib.Path(self.pathdir['statelog']).is_file():
                self.log.debug('Create state file: \'{0}\'.'.format(self.pathdir['statelog']))
                with pathlib.Path(self.pathdir['statelog']).open(mode='w') as mystatefile:
                    for option in self.stateopts:
                        self.log.debug(f'Adding option \'{option}\'.')
                        mystatefile.write(option + '\n')
            else:
                with pathlib.Path(self.pathdir['statelog']).open(mode='r+') as mystatefile:
                    
                    regex = re.compile(r'^(.*):.*$')
                    
                    
                    # Get the content in the list
                    oldstatefile = mystatefile.readlines()
                    
                    # Erase file
                    mystatefile.seek(0)
                    mystatefile.truncate()
                                        
                    # Check if options from self.stateopts list is found in current state file.
                    for option in self.stateopts:
                        isfound = 'no'
                        for line in oldstatefile:
                            if regex.match(line).group(1) == regex.match(option).group(1):
                                self.log.debug('Found option \'{0}\' in state file.'.format(regex.match(option).group(1)))
                                isfound = 'yes'
                                break
                        if isfound == 'no':
                            oldstatefile.append(option + '\n')           
                            self.log.debug('Wrote new option \'{0}\' in state file'.format(regex.match(option).group(1)))
                    
                    # Check if wrong / old option is found in current state file and append in the list toremove
                    toremove = []
                    for line in oldstatefile:
                        isfound = 'no'
                        for option in self.stateopts:
                            try:
                                if regex.match(line).group(1) == regex.match(option).group(1):
                                        isfound = 'yes'
                                        break
                            except AttributeError as error:
                                # This is 'normal' if option is other then 'name and more: other' 
                                # exemple 'name_other' will not match group(1) and will raise 
                                # exception AttributeError. So this mean that the option is wrong anyway.
                                
                                # Break or this will print as many as self.stateopts list item.
                                break
                        if isfound == 'no':
                            toremove.append(line)
                    
                    # Remove old or wrong option found from oldstatefile list
                    for wrongopt in toremove:
                        oldstatefile.remove(wrongopt)
                        self.log.debug('Remove wrong or old option \'{0}\' from state file'.format(wrongopt.rstrip()))
                    
                    # (re)write file
                    for line in oldstatefile:
                        mystatefile.write(line)
        except (OSError, IOError) as error:
            self.log.critical('Error while checking / creating \'{0}\' state file.'.format(self.pathdir['statelog']))
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.log.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.log.critical(f'Got: \'{error}\'.')
            sys.exit(1)           
        
    def save(self, pattern, to_write):
        """Edit info to specific linne of state file"""
        
        self.log.name = f'{self.logger_name}save::'
        
        try:
            regex = re.compile(r"^" + pattern + r":.*$")
            with pathlib.Path(self.pathdir['statelog']).open(mode='r+') as mystatefile:
                oldstatefile = mystatefile.readlines()   # Pull the file contents to a list
                
                # Erase the file
                mystatefile.seek(0)
                mystatefile.truncate()
                
                # Rewrite 
                for line in oldstatefile:
                    if regex.match(line):
                        self.log.debug(f'\'{to_write}\'.')
                        mystatefile.write(to_write + '\n')
                    else:
                        mystatefile.write(line)
        except (OSError, IOError) as error:
            self.log.critical('Error while modifing \'{0}\' state file.'.format(self.pathdir['statelog']))
            self.log.debug(f'\tTried to write: \'{to_write}\' in section: \'{pattern}\'.')
            self.log.critical(f'\tGot: \'{error}\'.')
            sys.exit(1)

    def load(self, pattern):
        """Read info from specific state file"""
        
        self.log.name = f'{self.logger_name}load::'
        
        try:
            regex = re.compile(r"^" + pattern + r":.(.*)$")
            with pathlib.Path(self.pathdir['statelog']).open() as mystatefile: 
                for line in mystatefile:
                     if regex.match(line):
                        self.log.debug('\'{0}: {1}\''.format(pattern, regex.match(line).group(1)))
                        #self.log.debug('Hello world')
                        return regex.match(line).group(1)
        except (OSError, IOError) as error:
            self.log.critical('Error while reading \'{0}\' state file.'.format(self.pathdir['statelog']))
            self.log.debug(f'\tTried to read section: \'{pattern}\'.')
            self.log.critical(f'\tGot: \'{error}\'')
            sys.exit(1)  
 
class FormatTimestamp:
    def __init__(self):
        self.intervals = (
            ('years', 31556952),  # https://www.calculateme.com/time/years/to-seconds/
            ('months', 2629746),  # https://www.calculateme.com/time/months/to-seconds/
            ('weeks', 604800),  # 60 * 60 * 24 * 7
            ('days', 86400),    # 60 * 60 * 24
            ('hours', 3600),    # 60 * 60
            ('minutes', 60),
            #('seconds', 1),
            )
        
    def convert(self, seconds, granularity=3):
        """Convert seconds to varying degrees of granularity.
        https://stackoverflow.com/a/24542445/11869956"""
        # TODO : round for exemple:  full display: 4 days, 2 hours, 42 minutes and 50 seconds
        # TODO TODO TODO !!!
        # if granularity is 2 this should be 4 days 3 hours NOT 2 hours (because 42 minutes)
        if seconds < 0:
            return 'any time now.'
        elif seconds < 60:
            return 'less than a minute.'
        
        result = []

        for name, count in self.intervals:
            value = seconds // count
            if value:
                seconds -= value * count
                if value == 1:
                    name = name.rstrip('s')
                result.append("{} {}".format(value, name))
        
        return ', '.join(result[:granularity])
    

class CapturedFd:
    """Pipe the specified fd to an temporary file
    https://stackoverflow.com/a/41301870/11869956
    Modified to capture both stdout and stderr.
    Need a list as argument ex: fd=[1,2]"""
    # TODO : not sure about that still thinking :p
    def __init__(self, fd):
        self.fd = fd
        self.prevfd = [ ]

    def __enter__(self):
        mytmp = tempfile.NamedTemporaryFile()
        for fid in self.fd:
            self.prevfd.append(os.dup(fid))
            os.dup2(mytmp.fileno(), fid)
        return mytmp

    def __exit__(self, exc_type, exc_value, traceback):
        i = 0
        for fid in self.fd:
            os.dup2(self.prevfd[i], fid)
            i = i + 1



