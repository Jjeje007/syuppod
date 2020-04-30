# -*- coding: utf-8 -*-
# -*- python -*- 
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3


import re
import os
import sys
import pathlib
import shutil
import errno
import platform
import time
import threading
import uuid

from distutils.version import StrictVersion
from utils import StateInfo
from utils import FormatTimestamp
from utils import UpdateInProgress
from logger import MainLoggingHandler
from logger import ProcessLoggingHandler

try:
    import inotify_simple
    import git 
    from git import InvalidGitRepositoryError as _InvalidGitRepositoryError
except Exception as exc:
    # Print to stderr
    print(f'Error: unexcept error while loading module: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)


# TODO : be more verbose for logger.info !
# TODO 

class GitHandler:
    """Git tracking class."""
    def __init__(self, **kwargs):
        # Check we got all required kwargs
        for key in 'interval', 'repo', 'pathdir', 'runlevel', 'loglevel':
            if not key in kwargs:
                # Print to stderr :
                # when running in init mode stderr is redirect to a log file
                # logger is not yet initialized 
                print(f'Crit: missing argument: {key}, calling module: {__name__}.', file=sys.stderr)
                print('Crit: exiting with status \'1\'.', file=sys.stderr)
                sys.exit(1)
                
        self.pathdir = kwargs.get('pathdir')
        self.repo = kwargs.get('repo')
        
        # Init logger
        self.logger_name = f'::{__name__}::GitHandler::'
        gitmanager_logger = MainLoggingHandler(self.logger_name, self.pathdir['prog_name'], 
                                           self.pathdir['debuglog'], self.pathdir['fdlog'])
        self.logger = getattr(gitmanager_logger, kwargs['runlevel'])()
        self.logger.setLevel(kwargs['loglevel'])
        
        # Init load/save info to file
        self.stateinfo = StateInfo(self.pathdir, kwargs['runlevel'], self.logger.level)
        
        # Check git config
        self._check_config()
        
        # Init FormatTimestamp
        self.format_timestamp = FormatTimestamp()
        
        # Pull attributes
        self.pull = {
            'status'        :   False, # False when not running / True otherwise
            'state'         :   self.stateinfo.load('pull state'),
            'network_error' :   int(self.stateinfo.load('pull network_error')),
            'retry'         :   int(self.stateinfo.load('pull retry')),
            'count'         :   str(self.stateinfo.load('pull count')),   # str() or get 'TypeError: must be str
                                                                          #  not int' or  vice versa
            'current_count' :   0,   
            'last'          :   int(self.stateinfo.load('pull last')),   # last pull timestamp
            'remain'        :   0,
            'elapsed'       :   0,
            'interval'      :   kwargs.get('interval'),
            #'update_all'    :   False,   # True after pull or if detected pull's outside run
            'recompute'     :   False   # True if remain as to be recompute
            }
        
        # 'Main remain' 
        self.remain = 30
        # Authorized update or not 
        self.update = True
        
        # Git branch attributes
        self.branch = {
            'logflow'   :   True, # Flow control over logger.info 
            # all means from state file
            'all'   :   {
                # 'local' is branch locally checkout (git checkout)
                'local'     :   sorted(self.stateinfo.load('branch all local').split(), key=StrictVersion),
                # 'remote' is all available branch from remote repo (so including 'local' as well).
                'remote'    :   sorted(self.stateinfo.load('branch all remote').split(), key=StrictVersion)
                },
            'available'   :  sorted(self.stateinfo.load('branch available').split(), key=StrictVersion) # {
            }
        
        # Git kernel attributes
        self.kernel = {
            'logflow'       :   True, # Flow control over logger.info
            # 'all' means all kernel version from git tag command
            'all'           :   sorted(self.stateinfo.load('kernel all').split(), key=StrictVersion),
            # 'available' means update available
            'available'     :   sorted(self.stateinfo.load('kernel available').split(), key=StrictVersion),
            # 'installed' means compiled and installed into the system
            'installed'     :   {
                # 'running' is from `uname -r' command
                'running'   :   self.stateinfo.load('kernel installed running'),
                # 'all' is all the installed kernel retrieve from /lib/modules which means that
                # /lib/modules should be clean up when removing old kernel...
                # TODO: get mtime for each folder in /lib/modules and print an warning if folder is older than ???
                # with mtime we can know when 
                'all'       :   sorted(self.stateinfo.load('kernel installed all').split(), key=StrictVersion)
                }
            # TODO : add 'compiled' key : to get last compiled kernel (time)
            }
    
    
    def get_running_kernel(self):
        """Retrieve running kernel version"""
        
        self.logger.name = f'{self.logger_name}get_running_kernel::'
        
        try:
            running = re.search(r'([\d\.]+)', platform.release()).group(1)
            # Check if we get valid version
            StrictVersion(running)
        except ValueError as err:
            self.logger.error(f'Got invalid version number while getting current running kernel:')
            self.logger.error(f'\'{err}\'.')
            if StrictVersion(self.kernel['installed']['running']) == StrictVersion('0.0'):
                self.logger.error(f'Previously know running kernel version is set to factory.')
                self.logger.error(f'The list of available update kernel version should be false.')
            else:
                self.logger.error(f'Keeping previously know running kernel version.')
        except Exception as exc:
            self.logger.error(f'Got unexcept error while getting current running kernel version:')
            self.logger.error(f'\'{exc}\'')
            if StrictVersion(self.kernel['installed']['running']) == StrictVersion('0.0'):
                self.logger.error(f'Previously know running kernel version is set to factory.')
                self.logger.error(f'The list of available update kernel version should be false.')
            else:
                self.logger.error(f'Keeping previously know running kernel version.')
        else:
            # Valid version
            self.logger.debug(f'Got base version: \'{running}\'.')
            
            # Don't write every time to state file 
            if not StrictVersion(self.kernel['installed']['running']) == StrictVersion(running):
                # Be a little more verbose for logger.info
                self.logger.info('Running kernel have changed (from {0} '.format(self.kernel['installed']['running'])
                              + f'to {running}).')
                self.kernel['installed']['running'] = running
                # Update state file
                self.stateinfo.save('kernel installed running', 'kernel installed running: ' 
                                    + self.kernel['installed']['running'])
    

    def get_installed_kernel(self):
        """Retrieve installed kernel(s) version on the system"""
        
        self.logger.name = f'{self.logger_name}get_installed_kernel::'
        
        # Get the list of all installed kernel from /lib/modules
        self.logger.debug('Extracting from /lib/modules/.')
        try:
            subfolders = [ ]
            # WARNING be carfull this was added in 3.6 !!
            with os.scandir('/lib/modules/') as listdir:
                for folder in listdir:
                    if folder.is_dir():
                        if re.search(r'([\d\.]+)', folder.name):
                            try:
                                version = re.search(r'([\d\.]+)', folder.name).group(1)
                                StrictVersion(version)
                            except Exception as err:
                                self.logger.error(f'While inspecting {folder.path} (version: {version})'
                                            + f', got: {err} ...skipping.')
                                continue
                            #except Exception as exc:
                                #self.logger.error(f'While inspecting {folder} (version: {version})'
                                            #+ f', got: {err} ...skipping.')
                                #continue
                            else:
                                self.logger.debug(f'Found version: {version}.')
                                subfolders.append(version)
        except OSError as error:
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.logger.critical(f'Error while reading directory: {error.strerror}: {error.filename}.')
                self.logger.critical('Daemon is intended to be run as sudo/root.')
                self.logger.critical('Exiting with status 1.')
                sys.exit(1)
            else:
                self.logger.error(f'Got unexcept error while reading directory: {error}.')
            return
        except Exception as exc:
            self.logger.error('Got unexcept error while getting installed kernel version list.')
            self.logger.error(f'{exc}.')
            if StrictVersion(self.kernel['installed']['all'][0]) == StrictVersion('0.0') \
                or StrictVersion(self.kernel['installed']['all'][0]) == StrictVersion('0.0.0'):
                self.logger.error('Previously list is empty.')
            else:
                self.logger.error('Keeping previously list.')
            self.logger.error('The list of available update kernel version should be false.')
            return
            
        
        # sort
        subfolders.sort(key=StrictVersion)
        
        if self._compare_multidirect(self.kernel['installed']['all'], subfolders, 'installed kernel'):
            self.logger.name = f'{self.logger_name}get_installed_kernel::'
            # Adding list to self.kernel
            self.logger.debug('Adding to the list: {0}.'.format(' '.join(subfolders)))
            self.kernel['installed']['all'] = subfolders
            
            # Update state file
            self.stateinfo.save('kernel installed all', 'kernel installed all: ' 
                                + ' '.join(self.kernel['installed']['all']))
        else:
            self.logger.name = f'{self.logger_name}get_installed_kernel::'
            # Else keep previously list 
  
  
    def update_installed_kernel(self, deleted=[], added=[]):
        """Remove or add new installed kernel while running"""
        
        self.logger.name = f'{self.logger_name}update_installed_kernel::'
        
        kernel_list = self.kernel['installed']['all'].copy()
        
        if not deleted and not added:
            self.logger.debug('There is nothing to do...')
            return
        if deleted:
            for folder in deleted:
                try:
                    version = re.search(r'([\d\.]+)', folder).group(1)
                    StrictVersion(version)
                except ValueError as err:
                    self.logger.error(f'While inspecting {folder} (version: {version}), got: {err} ...skipping.')
                    continue
                except Exception as exc:
                    self.logger.error(f'While inspecting {folder} (version: {version})' 
                                   + f', got unexcept: {err} ...skipping.')
                    continue
                else:
                    self.logger.debug(f'Removing version: {version} (folder: {folder}).')
                    try:
                        kernel_list.remove(version)
                    except ValueError as err:
                        self.logger.error(f'Got ValueError when removing version {version}' +
                                       'from kernel installed list.')
                        continue
                    else:
                        self.logger.debug('Version: {0} removed (list: {1})'.format(version, 
                                                                 ', '.join(kernel_list)))
        if added:
            for folder in added:
                try:
                    version = re.search(r'([\d\.]+)', folder).group(1)
                    StrictVersion(version)
                except ValueError as err:
                    self.logger.error(f'While inspecting {folder} (version: {version}), got: {err} ...skipping.')
                    continue
                except Exception as exc:
                    self.logger.error(f'While inspecting {folder} (version: {version})' 
                                   + f', got unexcept: {err} ...skipping.')
                    continue
                else:
                    self.logger.debug(f'Adding version: {version} (folder: {folder}).')
                    kernel_list.append(version)
                    self.logger.debug('Version: {0} added (list: {1})'.format(version, 
                                                           ', '.join(kernel_list)))
        # Make sure we have something 
        if kernel_list:
            # Remove duplicate
            kernel_list = list(dict.fromkeys(kernel_list))
            kernel_list.sort(key=StrictVersion)
            
            if self._compare_multidirect(self.kernel['installed']['all'], kernel_list, 'installed kernel'):
                self.logger.name = f'{self.logger_name}update_installed_kernel::'
                self.logger.debug('Kernel installed list have been updated.')
                self.kernel['installed']['all'] = kernel_list
                self.stateinfo.save('kernel installed all', 'kernel installed all: ' 
                                    + ' '.join(self.kernel['installed']['all']))
            else:
                # This is not fatal but this shouldn't arrived
                self.logger.name = f'{self.logger_name}update_installed_kernel::'
                self.logger.debug('Both list are equal !!' 
                            + ' (Old: {0} '.format(', '.join(self.kernel['installed']['all']))
                            + '| new: {0}).'.format(', '.join(kernel_list)))
        else:
            self.logger.debug('Nothing more to do...')
                    
               
    def get_all_kernel(self):
        """Retrieve list of all git kernel version."""
        
        self.logger.name = f'{self.logger_name}get_all_kernel::'
        
        # First get all tags from git (tags = versions)
        try:
            myprocess = git.Repo(self.repo).git.tag('-l').splitlines()
        except Exception as exc:
            err = exc.stderr
            # Try to strip off the formatting GitCommandError puts on stderr
            match = re.search(r"stderr: '(.*)'", err)
            if match:
                err = match.group(1)
            self.logger.error(f'Got unexcept error while getting available git kernel version.')
            self.logger.error(f'{err}.')
            # Don't exit just keep previously list
            if StrictVersion(self.kernel['available']['all'][0]) == StrictVersion('0.0') \
                or StrictVersion(self.kernel['available']['all'][0]) == StrictVersion('0.0.0'):
                self.logger.error('Previously list is empty, available git kernel update list should be wrong.')
            else:
                self.logger.error('Keeping previously list.')
            return

        versionlist = [ ]
        for line in myprocess:
            # TODO make 'zen' independent ??
            if re.match(r'^v([\d\.]+)-zen.*$', line):
                version = re.match(r'^v([\d\.]+)-zen.*$', line).group(1)
                try:
                    StrictVersion(version)
                except ValueError as err:
                    self.logger.error('While searching for available git kernel version.')
                    self.logger.error(f'Got: {err}. Skipping...')
                else:
                    # List is really too looong ...
                    self.logger.debug(f'Found version : {version}')
                    versionlist.append(version)
        
        if not versionlist:
            if StrictVersion(self.kernel['available']['all'][0]) == StrictVersion('0.0') \
                or StrictVersion(self.kernel['available']['all'][0]) == StrictVersion('0.0.0'):
                self.logger.error('Current and previously git kernel list version are empty.')
                self.logger.error('Available git kernel update list should be wrong.')
            else:
                self.logger.error('Keeping previously list.')
                self.logger.error('Available git kernel update list could be wrong.')
            return
        
        # Ok so list is good, keep it
        
        # Remove duplicate
        self.logger.debug('Removing duplicate entry from all kernel list.')
        versionlist = list(dict.fromkeys(versionlist))
        # Sorted
        versionlist.sort(key=StrictVersion)
        
        # Do we need to update kernel['all'] list or is the same ?
        if self._compare_multidirect(self.kernel['all'], versionlist, 'kernel'):
            self.logger.name = f'{self.logger_name}get_all_kernel::'
            self.logger.debug('Adding to list all: {0}.'.format(' '.join(self.kernel['all'])))
            self.kernel['all'] = versionlist
            
            # Update state file
            self.stateinfo.save('kernel all', 'kernel all: ' + ' '.join(self.kernel['all']))
        else:
            self.logger.name = f'{self.logger_name}get_all_kernel::'
            # Else keep previously list and don't write anything
  
  
    def get_branch(self, key):
        """Retrieve git origin and local branch version list"""
        
        self.logger.name = f'{self.logger_name}get_branch::'
        
        switch = { 
            # Main loop - check only local (faster) 
            'local'     :   {
                    'local'     :   '-l'
                    },
            # After dopull()
            'remote'    :   {   
                    'remote'    :   '-r'
                    },
            # Init program
            'all'      :   {
                    'local'     :   '-l',
                    'remote'    :   '-r'
                    }
            }
        for origin, opt in switch[key].items():
            try:
                self.logger.debug(f'Extracting from {origin} branch.')
                myprocess = git.Repo(self.repo).git.branch(opt).splitlines()
            except Exception as exc:
                err = exc.stderr
                # Try to strip off the formatting GitCommandError puts on stderr
                match = re.search(r"stderr: '(.*)'", err)
                if match:
                    err = match.group(1)
                self.logger.error(f'Got unexcept error while getting {origin} branch info.')
                self.logger.error(f'{err} ...skipping.')
                # Don't exit just keep previously list 
                continue
        
            versionlist = []
            for line in myprocess:
                # Get only 'master' branch's version list
                # For remote
                if re.match(r'^\s+\w+\/(\d+\.\d+)\/master', line):
                    version = re.match(r'^\s+\w+\/(\d+\.\d+)\/master', line).group(1)
                    try:
                        StrictVersion(version)
                    except ValueError as err:
                        self.logger.error(f'While searching for available {origin} branch list.')
                        self.logger.error(f'Got: {err} ...skipping.')
                        continue
                    else:
                        # Add to the list
                        self.logger.debug(f'Found version: {version}')
                        versionlist.append(version)
                # For local
                elif re.match(r'^..(\d+\.\d+)\/master', line):
                    version = re.match(r'^..(\d+\.\d+)\/master', line).group(1)
                    try:
                        StrictVersion(version)
                    except ValueError as err:
                        self.logger.error(f'While searching for available {origin} branch list.')
                        self.logger.error(f'Got: {err} ...skipping.')
                        continue
                    else:
                        # Add to the list
                        self.logger.debug(f'Found version: {version}')
                        versionlist.append(version)
                
            
            if not versionlist:
                self.logger.error(f'Couldn\'t find any valid {origin} branch version.')
                # TEST : error or critical ? exit or no ?
                # For now we have to test...
                # Don't update the list - so keep the last know or maybe the factory '0.0'
                break 
            
            versionlist.sort(key=StrictVersion)
                                                                    # origin: local or remote
            if self._compare_multidirect(self.branch['all'][origin], versionlist, f'{origin} branch'):
                self.logger.name = f'{self.logger_name}get_branch::'
                self.logger.debug('Adding to the list: {0}.'.format(' '.join(self.branch['all'][origin])))
                self.branch['all'][origin] = versionlist
            
                # Write to state file
                self.stateinfo.save('branch all ' + origin, 'branch all ' + origin + ': ' 
                                    + ' '.join(self.branch['all'][origin]))
            else:
                # reset logger_name
                self.logger.name = f'{self.logger_name}get_branch::'
                # Else keep data, save ressource, enjoy :)
            

    def get_available_update(self, target_attr):
        """Compare lists and return all available branch or kernel update."""
        self.logger.name = f'{self.logger_name}get_available_update::'
        
        target = getattr(self, target_attr)
        if target_attr == 'branch':
            origin = self.branch['all']['local'][-1]
            versionlist = target['all']['remote']
        elif target_attr == 'kernel':
            origin = self.kernel['installed']['all'][-1]
            versionlist = target['all']
        
        self.logger.debug(f'Checking available {target_attr} update.')
        current_available = [ ]
        for version in versionlist:
            try:
                # for branch -> branch['all']['local'][-1])
                if StrictVersion(version) > StrictVersion(origin):
                    current_available.append(version)
            except ValueError as err:
                # This shouldn't append
                # lists are checked in get_branch() and get_installed_kernel()
                # So print an error and continue with next item
                self.logger.error(f'Got unexcept error while checking available {target_attr} update.')
                self.logger.error(f'Got: {err} skipping...')
                continue
        if current_available:
            # Sorting 
            current_available.sort(key=StrictVersion)
            self.logger.debug('Found version(s): {0}.'.format(' '.join(current_available)))
            
            # Any way we will replace the whole list
            # Now compare new available list with old available list 
            if self._compare_multidirect(target['available'], current_available, target_attr):
                self.logger.name = f'{self.logger_name}get_available_update::'
                # So this mean rewrite it 
                self.logger.debug('Adding to the list: {0}.'.format(' '.join(current_available)))
                target['available'] = current_available
                # Write to state file
                self.stateinfo.save(target_attr + ' available', target_attr + ' available: '
                                    + ' '.join(target['available']))
            else:
                self.logger.name = f'{self.logger_name}get_available_update::'
                # else keep previously list
        # Nothing available so reset to '0.0.0' if necessary
        else:
            self.logger.debug(f'No available {target_attr} update.')
            if not StrictVersion(target['available'][0]) == StrictVersion('0.0.0') \
               or not StrictVersion(target['available'][0]) == StrictVersion('0.0'):
                self.logger.debug(f'Clearing list.')
                target['available'].clear()
                target['available'].append('0.0.0')
                self.stateinfo.save(target_attr + ' available', target_attr + ' available: ' 
                                    + ' '.join(target['available']))
        

    def get_last_pull(self, timestamp_only=False):
        """Get last git pull timestamp"""
                
        self.logger.name = f'{self.logger_name}get_last_pull::'
        
        path = pathlib.Path(self.repo + '/.git/FETCH_HEAD')
        if path.is_file():
            lastpull =  round(path.stat().st_mtime)
            self.logger.debug('Last git pull for repository \'{0}\': {1}.'.format(self.repo, 
                                                                               time.ctime(lastpull)))
            if timestamp_only:
                return lastpull
            
            saving = False
            
            if self.pull['last'] == 0:
                # First run 
                saving = True
                self.pull['last'] = lastpull
                
            elif not self.pull['last'] == lastpull:
                # This mean pull have been run outside the program
                self.logger.debug('Git pull have been run outside the program.')
                self.logger.debug('Current git pull timestamp: {0}, '.format(self.pull['last'])
                               + f'last: {lastpull}.')
                # TEST normaly this shouldn't needed any more 
                #self.logger.debug('Forcing all update.')
                #self.pull['update_all'] = True
                self.logger.debug('Enable recompute.')
                self.pull['recompute'] = True
                
                # TEST This have to be TEST !
                if self.pull['state'] == 'Failed' and not self.pull['network_error']:
                    # Ok so assume this have been fix (because pull have been run outside the program)
                    self.logger.warning('Git pull have been run outside the program.')
                    self.logger.warning('Found current pull state to Failed.')
                    self.logger.warning('Assuming that this have been fixed, please report if not.')
                    self.pull['state'] = 'Success'
                    self.stateinfo.save('pull state', 'pull state: Success')
                # Saving timestamp
                self.pull['last'] = lastpull
                saving = True
                
            if saving:
                self.stateinfo.save('pull last', 'pull last: ' + str(self.pull['last']))
            return True
        
        path = pathlib.Path(self.repo + '.git/refs/remotes/origin/HEAD')
        if path.is_file():
            self.logger.debug(f'Repository: {self.repo}, have never been updated (pull).')
            return True
        
        # Got problem 
        return False
   

    def check_pull(self, init_run=False):
        """Check git pull status depending on specified interval"""
        
        self.logger.name = f'{self.logger_name}check_pull::'
        
        # Call get_last_pull()
        if self.get_last_pull():
            if self.pull['recompute']:
                self.logger.debug('Recompute is enable.')
                self.pull['recompute'] = False
                current_timestamp = time.time()
                self.logger.debug('Current pull elapsed timestamp: {0}'.format(self.pull['elapsed']))
                self.pull['elapsed'] = round(current_timestamp - self.pull['last'])
                self.logger.debug('Recalculate pull elapsed timestamp: {0}'.format(self.pull['elapsed']))
                self.logger.debug('Current pull remain timestamp: {0}'.format(self.pull['remain']))
                self.pull['remain'] = self.pull['interval'] - self.pull['elapsed']
                self.logger.debug('Recalculate pull remain timestamp: {0}'.format(self.pull['remain']))
            
            self.logger.debug('Git pull elapsed time: ' 
                + '{0}'.format(self.format_timestamp.convert(self.pull['elapsed']))) 
            self.logger.debug('Git pull remain time: ' 
                + '{0}'.format(self.format_timestamp.convert(self.pull['remain'])))
            self.logger.debug('Git pull interval: ' 
                + '{0}.'.format(self.format_timestamp.convert(self.pull['interval'])))
            
            if init_run:
                self.logger.info('Git pull elapsed time: ' 
                    + '{0}'.format(self.format_timestamp.convert(self.pull['elapsed']))) 
                self.logger.info('Git pull remain time: '
                    + '{0}'.format(self.format_timestamp.convert(self.pull['remain'])))
                self.logger.info('Git pull interval: ' 
                    + '{0}.'.format(self.format_timestamp.convert(self.pull['interval'])))
            
            
            if self.pull['remain'] <= 0:
                return True
            # TEST Bypass remain as it's a network_error
            # This should be good but keep more testing
            if self.pull['network_error']:
                self.logger.debug('Bypassing remain timestamp ({0}) '.format(self.pull['remain'])
                               + 'as network error found.')
                return True
        return False
    

    def dopull(self):
        """Pulling git repository"""
        self.logger.name = f'{self.logger_name}dopull::'
        
        if self.pull['status']:
            self.logger.error('We are about to update git repository and found status to True,')
            self.logger.error('which mean it is already in progress, please check and report if False.')
            return
        # Skip pull if state is Failed and it's not an network error
        if self.pull['state'] == 'Failed' and not self.pull['network_error']:
            self.logger.error('Skipping git repository update due to previously error.')
            self.logger.error('Fix the error and reset using syuppod\'s dbus client.')
            return
        
        self.pull['status'] = True 
        # ALERT Be really carfull with this kind of thing because python will NOT trow Exception
        # in the else block (so make sure it's well written (not like me ;) )
        try:
            myprocess = git.Repo(self.repo).git.pull()
        except Exception as exc:
            err = exc.stderr
            # Try to strip off the formatting GitCommandError puts on stderr
            match = re.search("stderr: '(.*)'$", err)
            if match:
                err = match.group(1)
            network_error = re.search('.*Couldn.t.resolve.host.*', err)
            
            if network_error:
                # TEST TEST
                # 10 times @ 600s (10min)
                # after 10 times @ 3600s (1h)
                # then reset to interval (so mini is 24H)
                msg_on_retry = ''
                self.pull['remain'] = 600
                if self.pull['retry'] == 1:
                    msg_on_retry = ' (1 time already)'
                elif 2 <= self.pull['retry'] <= 10:
                    msg_on_retry = ' ({0} times already)'.format(self.pull['retry'])
                elif 11 <= self.pull['retry'] <= 20:
                    msg_on_retry = ' ({0} times already)'.format(self.pull['retry'])
                    self.pull['remain'] = 3600
                elif self.pull['retry'] > 20:
                    msg_on_retry = ' ({0} times already)'.format(self.pull['retry'])
                    self.pull['remain'] = self.pull['interval']
                self.logger.error('Got network error while pulling git repository.')
                self.logger.error(err)
                # This is normal 'retry{0}' see --> _set_remain_on_network_error()
                self.logger.error('Will retry{0} pulling in {1}.'.format(msg_on_retry,
                                                                     self.format_timestamp.convert(self.pull['remain'])))
                
                old_count = self.pull['retry']
                self.pull['retry'] += 1
                self.logger.debug('Incrementing pull retry from {0} to {1}.'.format(old_count, self.pull['retry']))
                # Save
                self.stateinfo.save('pull retry', 'pull retry: ' + str(self.pull['retry']))
                                
                if not self.pull['network_error']:
                    # Set network_error
                    self.pull['network_error'] = '1'
                    self.stateinfo.save('pull network_error', 'pull network_error: 1')
            else:
                self.logger.error('Got unexcept error while pulling git repository.')
                self.logger.error(err)
                # Reset retry and network_error
                if not self.pull['retry']:
                    self.pull['retry'] = 0
                    self.stateinfo.save('pull retry', 'pull retry: 0')
                if not self.pull['network_error']:
                    self.pull['network_error'] = 0
                    self.stateinfo.save('pull network_error', 'pull network_error: 0')
                                
                # Reset remain to interval 
                # But if no action then pull will be skipped
                self.pull['remain'] = self.pull['interval']
                
            if not self.pull['state'] == 'Failed':
                self.pull['state'] = 'Failed'
                self.stateinfo.save('pull state', 'pull state: Failed')
            
        else:
            self.logger.info('Successfully update git kernel repository.')
            # Update 'state' status to state file
            if not self.pull['state'] == 'Success':
                self.pull['state'] = 'Success'
                self.stateinfo.save('pull state', 'pull state: Success')
            
            # Reset retry and network_error
            if self.pull['retry']:
                self.pull['retry'] = 0
                self.stateinfo.save('pull retry', 'pull retry: 0')
            if self.pull['network_error']:
                self.pull['network_error'] = 0
                self.stateinfo.save('pull network_error', 'pull network_error: 0')

            # Append one more pull to git state file section 'pull'
            # Convert to integrer
            old_count_global = self.pull['count']
            old_count = self.pull['current_count']
            self.pull['count'] = int(self.pull['count'])
            self.pull['count'] += 1
            self.logger.debug('Incrementing global pull count from \'{0}\' to \'{1}\''.format(old_count_global,
                                                                                           self.pull['count']))
            self.pull['current_count'] += 1
            self.logger.debug('Incrementing current pull count from \'{0}\' to \'{1}\''.format(old_count,
                                                                                    self.pull['current_count']))
            
            self.stateinfo.save('pull count', 'pull count: ' + str(self.pull['count'])) # Same here str() or 'TypeError: 
                                                                                        # must be str, not int'
            
            # Append log to git.log file 
            processlog = ProcessLoggingHandler(name='gitlog')
            mylogfile = processlog.dolog(self.pathdir['gitlog'])
            mylogfile.setLevel(processlog.logging.INFO)
            mylogfile.info('##################################')
            for line in myprocess.splitlines():
                mylogfile.info(line)
            self.logger.debug('Successfully wrote git pull log to {0}.'.format(self.pathdir['gitlog']))
                        
            self.pull['remain'] = self.pull['interval']
            # Force update all 
            #self.pull['update_all'] = True
            #self.logger.debug('Setting update_all to True')
        finally:
            # Get last timestamp 
            # Any way even if git pull failed it will write to .git/FETCH_HEAD 
            # So get the timestamp any way
            self.pull['last'] = self.get_last_pull(timestamp_only=True)
            # Save
            self.logger.name = f'{self.logger_name}dopull::'
            self.logger.debug('Saving \'pull last: {0}\' to \'{1}\'.'.format(self.pull['last'], 
                                                                                 self.pathdir['statelog']))
            self.stateinfo.save('pull last', 'pull last: ' + str(self.pull['last']))
            # Reset status
            self.pull['status'] = False
        
                    
    def _check_config(self):
        """Check git config file options"""
        
        self.logger.name = f'{self.logger_name}check_config::'
        
        # Check / add git config to get all tags from remote origin repository
                              # fetch = +refs/heads/*:refs/remotes/origin/*
        regex = re.compile(r'\s+fetch.=.\+refs/heads/\*:refs/remotes/origin/\*')
        to_write = '        fetch = +refs/tags/*:refs/tags/*'
        re_tag = re.compile(r'\s+fetch.=.\+refs/tags/\*:refs/tags/\*')
        
        try:
            with pathlib.Path(self.repo + '/.git/config').open() as myfile:
                for line in myfile:
                    if re_tag.match(line):
                        self.logger.debug('Git config file already contain option to fetch all tags from remote repository.')
                        return
        except (OSError, IOError) as error:
            self.logger.critical('Error while checking git config file option.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.logger.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.logger.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.logger.critical(f'Got: \'{error}\'.')
            sys.exit(1)
        
        # Make backup
        try:
            # Check if backup file already exists 
            if not pathlib.Path(self.repo + '/.git/config.backup_' + name).is_file(): 
                shutil.copy2(self.repo + '/.git/config', self.repo + '/.git/config.backup_' + name)
        except (OSError, IOError) as error:
            self.logger.critical('Error while making an backup to git config file.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.logger.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.logger.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.logger.critical(f'Got: \'{error}\'.')
            sys.exit(1)
        # Modify
        try:
            with pathlib.Path(self.repo + '/.git/config').open(mode='r+') as myfile:
                old_file = myfile.readlines()   # Pull the file contents to a list
                myfile.seek(0)                  # Jump to start, so we overwrite instead of appending
                myfile.truncate                 # Erase file 
                for line in old_file:
                    if regex.match(line):
                        myfile.write(line)
                        myfile.write(to_write + '\n')
                    else:
                        myfile.write(line)
        except (OSError, IOError) as error:
            self.logger.critical('Error while adding option to git config file.')
            self.logger.critical('Tried to add options to get all tags from remote repository.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.logger.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.logger.critical(f'Daemon is intended to be run as sudo/root.')
            else:
                self.logger.critical(f'Got: \'{error}\'')
            sys.exit(1)
        else:
            self.logger.debug('Added option to git config file: fetch all tags from remote repository.')
       
    
    def _compare_multidirect(self, old_list, new_list, msg):
        """Compare lists multidirectionally"""
        
        self.logger.name = f'{self.logger_name}_compare_multidirect::'
        
        self.logger.debug('Tracking change multidirectionally:')
        ischange = False
        origin = old_list[-1]
        tocompare = {
            'first pass'    :   [ old_list, new_list, 'previously and current update list', 'previously'],
            'second pass'   :   [ new_list, old_list, 'current and previously update list', 'current' ]
            }
        current_version = '0.0.0'
        
        for value in tocompare.values():
            self.logger.debug('Between {0}.'.format(value[2]))
            #self.logger.debug(f'Current version: {current_version}.')
            for upper_version in value[0]:
                isfound = False
                #self.logger.debug(f'Current version: {current_version}.')
                for lower_version in value[1]:
                    #self.logger.debug(f'Current version: {current_version}.')
                    if StrictVersion(upper_version) == StrictVersion(lower_version):
                        self.logger.debug(f'Keeping version: {upper_version}')
                        isfound = True
                        break
                if not isfound:
                    ischange = True
                    self.logger.debug(f'Version: {upper_version}, not found in {value[3]} list.')
                    # First pass then this version is obsolete 
                    if value[3] == 'previously':
                        # we not adding anything but we just print this version is old one ...
                        self.logger.debug(f'Removing obsolete version: {upper_version}.')
                        # Don't log if version == '0.0.0' or '0.0'
                        if not StrictVersion(upper_version) == StrictVersion('0.0.0') \
                           or not StrictVersion(upper_version) == StrictVersion('0.0'):
                            self.logger.info('{0} version \'{1}\' have been removed.'.format(msg.capitalize(),
                                                                                   upper_version))
                    # Second pass then this version is 'new' (but not neccessary greater)
                    elif value[3] == 'current':
                        # ... and this version is new one.
                        # Any way we will replace all the list if lists are different
                        self.logger.debug(f'Adding new version: {upper_version}')
                        # Try to be more verbose for logger.info
                        # same here 
                        if not StrictVersion(upper_version) == StrictVersion('0.0.0') \
                           or not StrictVersion(upper_version) == StrictVersion('0.0'):
                            self.logger.info(f'Found new {msg} version: {upper_version}')
                        current_version = upper_version
        # Ok now if nothing change
        if not ischange:
            self.logger.debug('Finally, didn\'t found any change, previously data have been kept.')
            return False
        else:
            return True
        


class GitWatcher(threading.Thread):
    """Monitor specific git folder and file using inotify"""
    def __init__(self, pathdir, runlevel, loglevel, repo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pathdir = pathdir
        self.repo = repo
        self.repo_git = self.repo.rstrip('/') + '/.git/'
        # Init logger
        self.logger_name = f'::{__name__}::GitWatcher::'
        gitwatcher_logger = MainLoggingHandler(self.logger_name, self.pathdir['prog_name'], 
                                               self.pathdir['debuglog'], self.pathdir['fdlog'])
        self.logger = getattr(gitwatcher_logger, runlevel)()
        self.logger.setLevel(loglevel)
        self.tasks = { 
            'repo'  : {
                    'requests'   : {
                        'pending'       :   [ ],
                        'completed'      :   False
                        }
                    },
            'pull'  : {
                    'inprogress'    :   False,
                    'requests'   : {
                        'pending'       :   [ ],
                        'completed'      :   False
                        }
                    },
            'mod'   : {
                    'created'   :   [ ],
                    'deleted'   :   [ ],
                    'requests'   : {
                        'pending'       :   [ ],
                        'completed'      :   False
                        }                    
                    }
                }
        # Init Inotify
        self.inotify_repo = inotify_simple.INotify()
        self.inotify_mod = inotify_simple.INotify()
        self.watch_flags = inotify_simple.flags.CLOSE_WRITE | inotify_simple.flags.CREATE | \
                           inotify_simple.flags.DELETE
        try:
            #self.repo_wd = 
            self.inotify_repo.add_watch(self.repo_git, self.watch_flags)
            #self.mod_wd = 
            self.inotify_mod.add_watch('/lib/modules/', self.watch_flags)
        except OSError as error:
            self.logger.error('Git watcher daemon crash:')
            self.logger.error('Using {0} and /lib/modules/'.format(self.repo_git))
            self.logger.error(f'{error}')
            self.logger.error('Exiting with status 1.')
            sys.exit(1)
        
    def run(self):
        self.logger.debug('Git watcher daemon started ' 
                        + '(monitoring {0} and /lib/modules/).'.format(self.repo_git))
        found_fetch_head = False
        found_orig_head_lock = False
        while True:
            self.repo_read = self.inotify_repo.read(timeout=0)
            self.mod_read = self.inotify_mod.read(timeout=0)
            # First git repo
            if self.repo_read:
                # Reset each time
                found_fetch_head = False
                found_orig_head_lock = False
                self.logger.debug('State changed for: {0} ({1}).'.format(self.repo_git, self.repo_read))
                # TEST Try to catch git pull command
                # pull will first touch the FETCH_HEAD file 
                # At the end : ORIG_HEAD.lock
                for event in self.repo_read:
                    if event.name == 'FETCH_HEAD':
                        found_fetch_head = True
                    if event.name == 'ORIG_HEAD.lock':
                        found_orig_head_lock = True
                # Starting pull when only FETCH_HEAD is found
                if found_fetch_head and not found_orig_head_lock:
                    self.tasks['pull']['inprogress'] = True
                    # TODO logger.info :p
                    self.logger.debug('Git pull is in progress.')
                # Finished pull: more TEST-ing needed
                elif found_fetch_head and found_orig_head_lock:
                    self.tasks['pull']['inprogress'] = False
                    # Each request have it's own id (8 characters)
                    pull_id = uuid.uuid4().hex[:8]
                    self.tasks['pull']['requests']['pending'].append(pull_id)
                    # TODO logger.info :p
                    self.logger.debug('Git pull have been run.')
                    # Every thing have to be refreshed
                    repo_id = uuid.uuid4().hex[:8]
                    self.tasks['repo']['requests']['pending'].append(repo_id)
                    self.logger.debug(f'Sending request for git repo (id={repo_id}) '
                                      + f'and git pull (id={pull_id}) informations refresh.')
                else:
                    repo_id = uuid.uuid4().hex[:8]
                    self.tasks['repo']['requests']['pending'].append(repo_id)
                    self.logger.debug(f'Sending request (id={repo_id}) for git repo informations refresh.')
            # Then for /lib/modules/
            if self.mod_read:
                self.logger.debug('State changed for: {0} ({1}).'.format('/lib/modules/', self.mod_read))
                for event in self.mod_read:
                    # Create
                    if event.mask == 1073742080:
                        self.tasks['mod']['created'].append(event.name)
                        # Ad unique id
                        mod_id = uuid.uuid4().hex[:8]
                        self.tasks['mod']['requests']['pending'].append(mod_id)
                        self.logger.debug(f'Found created: {event.name} (id={mod_id}).')
                    # Delete
                    if event.mask == 1073742336:
                        self.tasks['mod']['deleted'].append(event.name)
                        # Ad unique id
                        mod_id = uuid.uuid4().hex[:8]
                        self.tasks['mod']['requests']['pending'].append(mod_id)
                        self.logger.debug(f'Found deleted: {event.name} (id={mod_id}).')
                if self.tasks['mod']['requests']['pending']:
                    msg = ''
                    if len(self.tasks['mod']['requests']['pending']) > 1:
                        msg = 's'
                    self.logger.debug(f'Sending request{msg}' 
                            + ' (id{0}={1})'.format(msg, '|'.join(self.tasks['mod']['requests']['pending']))
                            + ' for modules informations refresh.')
            
            # wait for request reply
            for switch in 'repo', 'pull', 'mod':
                if self.tasks[switch]['requests']['completed']:
                    if switch == 'mod':
                        reader = 'mod_read'
                        msg = 'modules'
                        # Reset list here
                        self.tasks[switch]['created'] = [ ]
                        self.tasks[switch]['deleted'] = [ ]
                    else:
                        reader = 'repo_read'
                        msg = f'git {switch}'
                    self.logger.debug(f'Got reply id for {msg} requests: '
                                      + '{0}'.format(self.tasks[switch]['requests']['completed']))
                    self.logger.debug('{0}'.format(msg.capitalize()) 
                                      + ' pending id list:' 
                                      + ' {0}'.format(', '.join(self.tasks[switch]['requests']['pending'])))                        
                    # Finished is the id of the last request proceed by main
                    # So we need to erase range from this id index to the first element in the list
                    id_index = self.tasks[switch]['requests']['pending'].index(
                        self.tasks[switch]['requests']['completed'])
                    plurial_msg = ''
                    if id_index > 0:
                        plurial_msg = 's'
                    # Make sure to remove also pointed index (so index+1)
                    to_remove = self.tasks[switch]['requests']['pending'][0:id_index+1]
                    del self.tasks[switch]['requests']['pending'][0:id_index+1]
                    self.logger.debug('{0} request{1}'.format(msg.capitalize(), plurial_msg)
                                + ' (id{0}={1})'.format(plurial_msg, '|'.join(to_remove))
                                + ' have been refreshed.')
                    self.tasks[switch]['requests']['completed'] = False
                    # Nothing left to read, nothing pending, waiting :p
                    if not getattr(self, reader) and not self.tasks[switch]['requests']['pending']:
                        self.logger.debug(f'All {msg} requests have been refreshed, sleeping...')
            time.sleep(1)
               
        

def check_git_dir(directory):
    """Cheking if dir exits, is writable and is a git repository"""
    if not os.path.isdir(directory):
        return (False, 'dir')
    if not os.access(directory, os.R_OK):
        return (False, 'read')
    try:
        git.Repo(directory)
    except _InvalidGitRepositoryError:
        return (False, 'git')
    return (True, '')

