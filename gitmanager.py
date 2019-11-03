# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

# OK all good normally this is version 0.1 final : 10/08/2019 
# 10/18/2019 : Added dedidace logger and stateinfo. 

import re
import os
import sys
import pathlib
import shutil
import errno
import platform
import time

from distutils.version import StrictVersion
from utils import StateInfo
from utils import FormatTimestamp
from utils import UpdateInProgress
from logger import MainLoggingHandler
from logger import ProcessLoggingHandler

try:
    import git 
    from git import InvalidGitRepositoryError as _InvalidGitRepositoryError
except Exception as exc:
    print(f'Got unexcept error while loading git module: {exc}')
    sys.exit(1)


# TODO : be more verbose for log.info !

class GitHandler:
    """Git tracking class."""
    def __init__(self, interval, repo, pathdir, runlevel, loglevel):
        self.pathdir = pathdir
        self.repo = repo
        
        # Init logger
        self.logger_name = f'::{__name__}::GitHandler::'
        gitmanagerlog = MainLoggingHandler(self.logger_name, self.pathdir['debuglog'],
                                           self.pathdir['fdlog'])
        self.log = getattr(gitmanagerlog, runlevel)()
        self.log.setLevel(loglevel)
        
        # Init load/save info to file
        self.stateinfo = StateInfo(self.pathdir, runlevel, self.log.level)
        
        # Check git config
        self._check_config()
        
        # Init FormatTimestamp
        self.format_timestamp = FormatTimestamp()
        
        self.update_inprogress = UpdateInProgress(self.log)
                       
        # Pull attributes
        self.pull = {
            'status'    :   False,
            'state'     :   self.stateinfo.load('pull state'),
            # TODO: expose log throught dbus
            # So we have to make an objet which will get last log from 
            # git.log file (and other log file)
            'log'       :   'TODO',             
            'error'     :   self.stateinfo.load('pull error'),
            'count'     :   str(self.stateinfo.load('pull count')),   # str() or get 'TypeError: must be str, not int' or vice versa
            'last'      :   int(self.stateinfo.load('pull last')),   # last pull timestamp
            'remain'    :   0,
            'elapsed'   :   0,
            'interval'  :   interval,
            'forced'    :   False
        }
        
        # Main remain for checking local branch checkout and local kernel installed
        self.remain = 35
        
        # Git branch attributes
        self.branch = {
            # all means from state file
            'all'   :   {
                # 'local' is branch locally checkout (git checkout)
                'local'     :   sorted(self.stateinfo.load('branch all local').split(), key=StrictVersion),
                # 'remote' is all available branch from remote repo (so including 'local' as well).
                'remote'    :   sorted(self.stateinfo.load('branch all remote').split(), key=StrictVersion)
            },
            # available means after pulling repo (so when running).
            'available'   :   {
                    # know means available since more than one pull (but didn't locally checkout)
                    'know'      :   sorted(self.stateinfo.load('branch available know').split(), key=StrictVersion),
                    # new means available since last pull and until next pull
                    'new'       :   sorted(self.stateinfo.load('branch available new').split(), key=StrictVersion),
                    # all means all available update branch.
                    'all'       :   sorted(self.stateinfo.load('branch available all').split(), key=StrictVersion)
            }
        }
        
        # Git kernel attributes
        self.kernel = {
            # 'all' means all kernel version from git tag command
            'all'           :   sorted(self.stateinfo.load('kernel all').split(), key=StrictVersion),
            # 'available' means update available
            'available'     :   {
                # 'know' means already know from state file (so from an old pull)
                'know'      :   sorted(self.stateinfo.load('kernel available know').split(), key=StrictVersion),
                # 'new' means available from the last pull and until next pull
                'new'       :   sorted(self.stateinfo.load('kernel available new').split(), key=StrictVersion),
                # 'all' means all available for update (so contain both 'know' and 'new')
                'all'       :   sorted(self.stateinfo.load('kernel available all').split(), key=StrictVersion)
            },
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
        
        self.log.name = f'{self.logger_name}get_running_kernel::'
        
        try:
            self.log.debug('Getting current running kernel:')
            running = re.search(r'([\d\.]+)', platform.release()).group(1)
            # Check if we get valid version
            StrictVersion(running)
        except ValueError as err:
            self.log.error(f'Got invalid version number while getting current running kernel:')
            self.log.error(f'\'{err}\'.')
            if self.kernel['installed']['running'] == '0.0':
                self.log.error(f'Previously know running kernel version is set to factory.')
                self.log.error(f'The list of available update kernel version should be false.')
            else:
                self.log.error(f'Keeping previously know running kernel version.')
            #return False
        except Exception as exc:
            self.log.error(f'Got unexcept error while getting current running kernel version:')
            self.log.error(f'\'{exc}\'')
            if self.kernel['installed']['running'] == '0.0':
                self.log.error(f'Previously know running kernel version is set to factory.')
                self.log.error(f'The list of available update kernel version should be false.')
            else:
                self.log.error(f'Keeping previously know running kernel version.')
            #return False
        else:
            # Valid version
            self.log.debug(f'Got base version: \'{running}\'.')
            
            # Don't write every time to state file 
            if not self.kernel['installed']['running'] == running:
                self.kernel['installed']['running'] = running
                # Update state file
                self.log.debug('Updating state info file.')
                self.stateinfo.save('kernel installed running', 'kernel installed running: ' + self.kernel['installed']['running'])
                #return True
    

    def get_installed_kernel(self):
        """Retrieve installed kernel(s) version on the system"""
        
        self.log.name = f'{self.logger_name}get_installed_kernel::'
        
        # Get the list of all installed kernel from /lib/modules
        self.log.debug('Getting list of all installed kernel from /lib/modules:')
        try:
            subfolders = [ ]
            for folder in os.scandir('/lib/modules/'):
                if folder.is_dir():
                    if re.search(r'([\d\.]+)', folder.name):
                        try:
                            version = re.search(r'([\d\.]+)', folder.name).group(1)
                            StrictVersion(version)
                        except ValueError as err:
                            self.log.error(f'While adding to the installed kernel list:')
                            self.log.error(f'Got: \'{err}\' ...skipping.')
                            continue
                        except Exception as exc:
                            self.log.error(f'While adding to the installed kernel list:')
                            self.log.error(f'Got unexcept error: \'{err}\' ...skipping.')
                            continue
                        else:
                            self.log.debug(f'Found version: \'{version}\'.')
                            subfolders.append(version)
        except OSError as error:
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.log.critical(f'Error while reading directory: \'{error.strerror}: {error.filename}\'.')
                self.log.critical(f'Daemon is intended to be run as sudo/root.')
                sys.exit(1)
            else:
                self.log.critical(f'Got unexcept error while reading directory: \'{error}\'.')
                # Don't exit 
            return
        except Exception as exc:
            self.log.error(f'Got unexcept error while getting installed kernel version list:')
            self.log.error(f'\'{exc}\'.')
            if self.kernel['installed']['all'] == '0.0' or self.kernel['installed']['all'] == '0.0.0':
                self.log.error('Previously list is empty.')
            else:
                self.log.error('Keeping previously list.')
            self.log.error('The list of available update kernel version should be false.')
            return
        
        # sort
        subfolders.sort(key=StrictVersion)
        
        if self._compare_multidirect(self.kernel['installed']['all'], subfolders):
            # Adding list to self.kernel
            self.log.debug('Adding to the list: \'{0}\'.'.format(' '.join(subfolders)))
            self.kernel['installed']['all'] = subfolders
            
            # Update state file
            self.log.debug('Updating state file info.')
            self.stateinfo.save('kernel installed all', 'kernel installed all: ' + ' '.join(self.kernel['installed']['all']))
        # Else keep previously list 
  
  
    def get_all_kernel(self):
        """Retrieve list of all git kernel version."""
        
        self.log.name = f'{self.logger_name}get_all_kernel::'
        
        # First get all tags from git (tags = versions)
        try:
            self.log.debug('Getting all git kernel version (not sorted):')
            stdout = git.Repo(self.repo).git.tag('-l').splitlines()
        except Exception as exc:
            err = exc.stderr
            # Try to strip off the formatting GitCommandError puts on stderr
            match = re.search(r"stderr: '(.*)'", err)
            if match:
                err = match.group(1)
            # TODO: same as pull : count the error
            self.log.error(f'Got unexcept error while getting available git kernel version:')
            self.log.error(f'{err}.')
            # Don't exit just keep previously list
            if self.kernel['available']['all'][0] == '0.0' or self.kernel['available']['all'][0] == '0.0.0':
                self.log.error('Previously list is empty, available git kernel update list should be wrong.')
            else:
                self.log.error('Keeping previously list.')
            return

        versionlist = [ ]
        for line in stdout:
            if re.match(r'^v([\d\.]+)-zen.*$', line):
                version = re.match(r'^v([\d\.]+)-zen.*$', line).group(1)
                try:
                    StrictVersion(version)
                except ValueError as err:
                    self.log.error('While searching for available git kernel version:')
                    self.log.error(f'Got: {err}. Skipping...')
                else:
                    self.log.debug(f'Found version : \'{version}\'')
                    versionlist.append(version)
        
        if not versionlist:
            if self.kernel['available']['all'][0] == '0.0' or self.kernel['available']['all'][0] == '0.0.0':
                self.log.error('Current and previously git kernel list version are empty.')
                self.log.error('Available git kernel update list should be wrong.')
            else:
                self.log.error('Keeping previously list.')
                self.log.error('Available git kernel update list could be wrong.')
            return
        
        # Ok so list is good, keep it
        
        # Remove duplicate
        self.log.debug('Removing duplicate entry from all kernel list.')
        versionlist = list(dict.fromkeys(versionlist))
        # Sorted
        versionlist.sort(key=StrictVersion)
        
        # Do we need to update kernel['all'] list or is the same ?
        if self._compare_multidirect(self.kernel['all'], versionlist):
            
            self.log.debug('Adding to \'all\' list: \'{0}\'.'.format(' '.join(self.kernel['all'])))
            self.kernel['all'] = versionlist
            
            # Update state file
            self.log.debug('Updating state file info.')
            self.stateinfo.save('kernel all', 'kernel all: ' + ' '.join(self.kernel['all']))
        # Else keep previously list and don't write anything
  
  
    def get_branch(self, key):
        """Retrieve git origin and local branch version list"""
        
        self.log.name = f'{self.logger_name}get_branch::'
        
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
                self.log.debug(f'Getting all available branch from {origin}:')
                stdout = git.Repo(self.repo).git.branch(opt).splitlines()
            except Exception as exc:
                err = exc.stderr
                # Try to strip off the formatting GitCommandError puts on stderr
                match = re.search(r"stderr: '(.*)'", err)
                if match:
                    err = match.group(1)
                self.log.error(f'Got unexcept error while getting {origin} branch info:')
                self.log.error(f'{err}.')
                # Don't exit just keep previously list 
                continue
        
            versionlist = []
            for line in stdout:
                # Get only 'master' branch's version list
                # For remote
                if re.match(r'^\s+\w+\/(\d+\.\d+)\/master', line):
                    version = re.match(r'^\s+\w+\/(\d+\.\d+)\/master', line).group(1)
                    try:
                        StrictVersion(version)
                    except ValueError as err:
                        self.log.error(f'While searching for available {origin} branch list:')
                        self.log.error(f'Got: \'{err}\' ...skipping.')
                        continue
                    else:
                        # Add to the list
                        self.log.debug(f'Found version: \'{version}\'.')
                        versionlist.append(version)
                # For local
                elif re.match(r'^..(\d+\.\d+)\/master', line):
                    version = re.match(r'^..(\d+\.\d+)\/master', line).group(1)
                    try:
                        StrictVersion(version)
                    except ValueError as err:
                        self.log.error(f'While searching for available {origin} branch list:')
                        self.log.error(f'Got: \'{err}\' ...skipping.')
                        continue
                    else:
                        # Add to the list
                        self.log.debug(f'Found version: \'{version}\'.')
                        versionlist.append(version)
                
            
            if not versionlist:
                self.log.error(f'Couldn\'t find any valid {origin} branch version.')
                # TODO : error or critical ? exit or no ?
                # For now we have to test...
                # Don't update the list - so keep the last know or maybe the factory '0.0'
                break 
            
            versionlist.sort(key=StrictVersion)
            
            if self._compare_multidirect(self.branch['all'][origin], versionlist):
                
                self.log.debug('Adding to the list: \'{0}\'.'.format(' '.join(self.branch['all'][origin])))
                self.branch['all'][origin] = versionlist
            
                # Write to state file
                self.log.debug('Updating state file.')
                self.stateinfo.save('branch all ' + origin, 'branch all ' + origin + ': ' + ' '.join(self.branch['all'][origin]))
            # Else keep data, save ressource, enjoy :)
            

    def get_available_update(self, target_attr):
        """Compare lists and return all available branch or kernel update."""
        
        self.log.name = f'{self.logger_name}get_available_update::'
        
        # First compare latest local branch with remote branch list to get current available branch version
        target = getattr(self, target_attr)
        if target_attr == 'branch':
            origin = self.branch['all']['local'][-1]
            versionlist = target['all']['remote']
        elif target_attr == 'kernel':
            origin = self.kernel['installed']['all'][-1]
            versionlist = target['all']
        
        self.log.debug(f'Checking available \'{target_attr}\' update :')
        current_available = [ ]
        for version in versionlist:
            try:
                # for branch -> branch['all']['local'][-1])
                if StrictVersion(version) > StrictVersion(origin):
                    current_available.append(version)
            except ValueError as err:
                # This shouldn't append
                # self.branch['all']['local'] (and ['remote']) is check in get_branch()
                # So print an error and continue with next item in the self.branch['all']['remote'] list
                self.log.error(f'Got unexcept error while checking available update {target_attr}:')
                self.log.error(f'{err} skipping...')
                continue
        
        if current_available:
            # Sorting 
            current_available.sort(key=StrictVersion)
            self.log.debug('Found version(s): \'{0}\'.'.format(' '.join(current_available)))
                      
            # First run and will call dopull() or just first run or calling dopull()
            if target['available']['new'][0] == '0.0' or self.pull['status']:
                if target['available']['new'][0] == '0.0' and self.pull['status']:
                    self.log.debug('First run and pull setup:')
                elif target['available']['new'][0] == '0.0':
                    self.log.debug('First run setup:')
                elif self.pull['status']:
                    self.log.debug('Pull run setup:')
                
                for switch in 'all', 'know', 'new':
                    self.log.debug(f'Clearing list \'{switch}\'.')
                    target['available'][switch].clear()
                    
                    if switch == 'new':
                        self.log.debug(f'Adding to \'{switch}\' list: \'0.0.0\' (means nothing available).')
                        target['available'][switch].append('0.0.0')
                    else:
                        self.log.debug('Adding to \'{1}\' list: {0}\'.'.format(' '.join(current_available), switch))
                        target['available'][switch] = current_available
                    
                    self.log.debug(f'Updating state file for list \'{switch}\'.')
                    self.stateinfo.save(target_attr + ' available ' + switch, 
                                      target_attr + ' available ' + switch + 
                                      ': ' + ' '.join(target['available'][switch]))
                    
            # When running - bewteen two pull 
            else:
                # No previously update list
                if target['available']['all'][0] == '0.0.0':
                    # So every thing should go to new list
                    self.log.debug('No previously update found.')
                    
                    for switch in 'all', 'know', 'new':
                        if switch == 'know':
                            if target['available'][switch][0] == '0.0.0':
                                self.log.debug(f'List \'{switch}\' already setup, skipping.')
                                continue
                            else:
                                self.log.debug(f'\Clearing list \'{switch}\'.')
                                target['available'][switch].clear()
                                self.log.debug(f'Adding to \'{switch}\' list: \'0.0.0\' (means nothing available).')
                                target['available'][switch].append('0.0.0')
                        else:
                            self.log.debug(f'\Clearing list \'{switch}\'.')
                            target['available'][switch].clear()
                            self.log.debug('Adding to \'{1}\' list: {0}\'.'.format(' '.join(current_available), switch))
                            target['available'][switch] = current_available
                        
                        self.log.debug(f'Updating state file for list \'{switch}\'.')
                        self.stateinfo.save(target_attr + ' available ' + switch, 
                                        target_attr + ' available ' + switch + 
                                        ': ' + ' '.join(target['available'][switch]))
                # We had already an update.
                else:
                    self.log.debug('Found previously update list.')
                    
                    ischange = 'no'
                                        
                    # compare 'previously all list' with 'current all list' and vice versa :
                    # self.branch['available']['all'] against current_available
                    tocompare = {
                        'firstpass'     :   [ current_available, target['available']['all'], 
                                         'previously and current update list.', 'previously' ],
                        'secondpass'    :   [ target['available']['all'], current_available,
                                         'current and previously update list.', 'current']
                        }
                    
                    
                    self.log.debug('Tracking change multidirectionally:')
                    
                    for value in tocompare.values():
                        self.log.debug('Between {0}'.format(value[2]))
                        
                        for upper_version in value[0]:
                            isfound = 'no'
                            for lower_version in value[1]:
                                if StrictVersion(upper_version) == StrictVersion(lower_version):
                                    isfound = 'yes'
                                    # We know that this version is in both list so keep it
                                    # And search over self.branch['available']['new'] and self.branch['available']['know']
                                    # To know if it is in one of them (and it should!!)
                                    for version in target['available']['know']:
                                        if StrictVersion(upper_version) == StrictVersion(version):
                                            self.log.debug(f'Keeping version \'{upper_version}\': already in list \'all\' and \'know\'.')
                                    for version in target['available']['new']:
                                        if StrictVersion(upper_version) == StrictVersion(version):
                                            self.log.debug(f'Keeping version \'{upper_version}\': already in list \'all\' and \'new\'.')
                                    break
                            if isfound == 'no':
                                # So something has change - 'hard' thing start here
                                ischange = 'yes'
                                self.log.debug(f'Version \'{upper_version}\' not found in {value[3]} list.')
                                # So now we have to know if this version is new or old (so to remove)
                                # So first compare with latest local branch
                                if StrictVersion(origin) >= StrictVersion(upper_version):
                                    # This mean the version is old (already checkout) so 
                                    # first remove from self.branch['available']['all']
                                    self.log.debug(f'Removing already checkout version \'{upper_version}\' from:')
                                    #self.log.debug('List \'all\'.')
                                    target['available']['all'].remove(upper_version)
                                    # Now search over self.branch['available']['new'] and self.branch['available']['know']
                                    # and remove 
                                    # Normaly if version is found in both than it's a bug !
                                    for version in target['available']['know']:
                                        if StrictVersion(upper_version) == StrictVersion(version):
                                            self.log.debug('List \'all\' and \'know\'.')
                                            target['available']['know'].remove(upper_version)
                                        # Normally there is only one version because we remove duplicate
                                        break
                                    for version in target['available']['new']:
                                        if StrictVersion(upper_version) == StrictVersion(version):
                                            self.log.debug('List \'all\' and \'new\'.')
                                            target['available']['new'].remove(upper_version)
                                        break
                                # So here it's a new version so it goes to ['available']['new']
                                # And also to ['available']['all'] 
                                elif StrictVersion(origin) < StrictVersion(upper_version):
                                    # Search over the list and remove '0.0.0' or '0.0' - got a 'bug' like that when testing 
                                    # it was '0.0.0' but add '0.0' in case ;)
                                    for switch in 'all', 'new':
                                        if '0.0' in target['available'][switch]:
                                            self.log.debug(f'Removing wrong option \'0.0\' from list \'{switch}\'.')
                                            target['available'][switch].remove('0.0')
                                        elif '0.0.0' in target['available'][switch]:
                                            self.log.debug(f'Removing wrong option \'0.0.0\' from list \'{switch}\'.')
                                            target['available'][switch].remove('0.0.0')
                                    # Add to both list 'all' and 'new' - i forgot to add to 'all' list ...
                                    self.log.debug(f'Adding new version \'{upper_version}\' to list \'new\' and \'all\'.')
                                    target['available']['new'].append(upper_version)
                                    target['available']['all'].append(upper_version)
                
                    # Nothing change - don't write to state file 
                    if ischange == 'no':
                        self.log.debug('Finally, didn\'t found any change, previously data has been keep.')
                    # Something change - write to the disk 
                    elif ischange == 'yes':
                        
                        for switch in 'all', 'know', 'new':
                            # Check if list is empty
                            if not target['available'][switch]:
                                self.log.debug(f'Adding to the empty list \'{switch}\': \'0.0.0\' (means nothing available).')
                                target['available'][switch] = [ ] # To make sure it's recognise as a list.
                                target['available'][switch].append('0.0.0')
                            else:
                                # Remove duplicate in case
                                self.log.debug(f'Removing duplicate entry (if any) from list \'{switch}\'.')
                                target['available'][switch] =  list(dict.fromkeys(target['available'][switch]))
                            # Then write to the state file 
                            self.log.debug(f'Updating state file for list \'{switch}\'.')
                            self.stateinfo.save(target_attr + ' available ' + switch, 
                                              target_attr + ' available ' + switch + 
                                              ': ' + ' '.join(target['available'][switch]))
            
        else:
            self.log.debug('No update found.')
            
            for switch in 'all', 'know', 'new':
                # No need to write to state file if already in good state...
                if target['available'][switch][0] == '0.0.0':
                    self.log.debug(f'List \'{switch}\' already setup, skipping.')
                else:
                    self.log.debug(f'Clearing list \'{switch}\'.')
                    target['available'][switch].clear()
                    self.log.debug(f'Adding to the list \'{switch}\': \'0.0.0\' (means nothing available).')
                    target['available'][switch].append('0.0.0')
                    self.log.debug(f'Updating state file for list \'{switch}\'.')
                    self.stateinfo.save(target_attr + ' available ' + switch, 
                                      target_attr + ' available ' + switch + 
                                      ': ' + ' '.join(target['available'][switch]))


    def get_last_pull(self, timestamp_only=False):
        """Get last git pull timestamp"""
        
         # BUG : even if git pull failed it's still modify .git/FETCH_HEAD  ...
        
        self.log.name = f'{self.logger_name}get_last_pull::'
        
        path = pathlib.Path(self.repo + '/.git/FETCH_HEAD')
        if path.is_file():
            lastpull =  round(path.stat().st_mtime)
            self.log.debug('Last git pull for repository \'{0}\': {1}.'.format(self.repo, 
                                                                               time.ctime(lastpull)))
            if timestamp_only:
                return lastpull
            
            saving = False
            
            if self.pull['last'] == 0:
                # First run 
                saving = True
                self.pull['last'] = lastpull
                
            elif not self.pull['last'] == lastpull:
                # This mean pull has been run outside the program
                self.log.debug('Git pull has been run outside the program.')
                self.log.debug('Current git pull timestamp: \'{0}\', last: \'{1}\'.'.format(self.pull['last'],
                                                                                            lastpull))
                self.log.debug('Forcing all update.')
                self.pull['forced'] = True
                
                # Saving timestamp
                self.pull['last'] = lastpull
                saving = True
                
            if saving:
                self.log.debug('Saving \'pull last: {0}\' to \'{1}\'.'.format(self.pull['last'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('pull last', 'pull last: ' + str(self.pull['last']))
                
            return True
        
        path = pathlib.Path(self.repo + '.git/refs/remotes/origin/HEAD')
        if path.is_file():
            self.log.debug(f'Repository \'{self.repo}\' has never been updated (pull).')
            self.pull['status'] = True
            
            return True
        
        # Got problem 
        return False
   

    def check_pull(self):
        """Check git pull status depending on specified interval"""
        
        self.log.name = f'{self.logger_name}check_pull::'
        
        # git pull already running ?
        if self.update_inprogress.check('Git', repogit=self.repo):
            # Update in progress 
            # retry in 3 minutes
            if self.pull['remain'] <= 180:
                self.pull['remain'] = 180
                return False
            else:
                # don't touch
                return False
        
        # Call get_last_pull()
        if self.get_last_pull():
            current_timestamp = time.time()
            self.pull['elasped'] = round(current_timestamp - self.pull['last'])
            self.pull['remain'] = self.pull['interval'] - self.pull['elasped']
            self.log.debug('Git pull elasped time: {0}'.format(self.format_timestamp.convert(self.pull['elasped']))) 
            self.log.debug('Git pull remain time: {0}'.format(self.format_timestamp.convert(self.pull['remain'])))
            self.log.debug('Git pull interval: {0}.'.format(self.format_timestamp.convert(self.pull['interval'])))
                        
            if self.pull['remain'] <= 0:
                self.pull['status'] = True
                return True
        return False
    

    def dopull(self):
        """Pulling git repository"""
        
        # TODO: thread
        # BUG : even if git pull failed it's still modify .git/FETCH_HEAD  ... 
        
        self.log.name = f'{self.logger_name}dopull::'
        
        try:
            gitlog = git.Repo(self.repo).git.pull()
        except Exception as exc:
            err = exc.stderr
            # Try to strip off the formatting GitCommandError puts on stderr
            match = re.search("stderr: '(.*)'$", err)
            if match:
                err = match.group(1)
            self.log.error('Error while pulling git repository:')
            self.log.error(f'{err}')
            
            # Just mark the first error and exit if second error 
            if self.pull['error'] == '1':
                # Look like it's not possible to get the error number
                # So it's not possible to know that is the same error...
                self.log.critical('This is the second error while pulling git repository.')
                self.log.critical('Cannot continue, please fix the error.')
                sys.exit(1)
            self.pull['state'] = 'Failed'
            self.pull['error'] = 1
            
            # Write error status to state file so if the program is stop and restart
            # it will know that it was already an error
            # Write 'state' to state file as well
            self.stateinfo.save('pull error', 'pull error: 1')
            self.stateinfo.save('pull state', 'pull state: Failed')
            
            # Reset remain to interval
            self.pull['remain'] = self.pull['interval']
            
            return False
        
        else:
            self.pull['state'] = 'Success'
            # Update 'state' status to state file
            self.stateinfo.save('pull state', 'pull state: Success')
            self.log.info('Successfully update git kernel repository.')
            
            # Erase status of git pull error in git.state file and reset self.pull error to 0
            self.pull['error'] = 0
            self.stateinfo.save('pull error', 'pull error: 0')
            
            # Append one more pull to git state file section 'pull'
            # Convert to integrer
            self.pull['count'] = int(self.pull['count'])
            self.pull['count'] += 1
            self.stateinfo.save('pull count', 'pull count: ' + str(self.pull['count'])) # Same here str() or 'TypeError: must be str, not int'
            
            # Append log to git.log file 
            processlog = ProcessLoggingHandler(name='gitlog')
            mylogfile = processlog.dolog(self.pathdir['gitlog'])
            mylogfile.setLevel(processlog.logging.INFO)
            mylogfile.info('##################################')
            for line in gitlog.splitlines():
                mylogfile.info(line)
            self.log.debug(f'Successfully wrote git pull log to \'{0}\'.'.format(self.pathdir['gitlog']))
            
            # Get last timestamp
            self.pull['last'] = self.get_last_pull(timestamp_only=True)
            
            # Save
            self.log.debug('Saving \'pull last: {0}\' to \'{1}\'.'.format(self.pull['last'], 
                                                                          self.pathdir['statelog']))
        
            # Reset remain to interval
            self.pull['remain'] = self.pull['interval']
            
            return True
                    

    def _check_config(self):
        """Check git config file options"""
        
        self.log.name = f'{self.logger_name}check_config::'
        
        # Check / add git config to get all tags from remote origin repository
                              # fetch = +refs/heads/*:refs/remotes/origin/*
        regex = re.compile(r'\s+fetch.=.\+refs/heads/\*:refs/remotes/origin/\*')
        to_write = '        fetch = +refs/tags/*:refs/tags/*'
        re_tag = re.compile(r'\s+fetch.=.\+refs/tags/\*:refs/tags/\*')
        
        try:
            with pathlib.Path(self.repo + '/.git/config').open() as myfile:
                for line in myfile:
                    if re_tag.match(line):
                        self.log.debug('Git config file already contain option to fetch all tags from remote repository.')
                        return
        except (OSError, IOError) as error:
            self.log.critical('Error while checking git config file option.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.log.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.log.critical(f'Got: \'{error}\'.')
            sys.exit(1)
        
        # Make backup
        try:
            # Check if backup file already exists 
            if not pathlib.Path(self.repo + '/.git/config.backup_' + name).is_file(): 
                shutil.copy2(self.repo + '/.git/config', self.repo + '/.git/config.backup_' + name)
        except (OSError, IOError) as error:
            self.log.critical('Error while making an backup to git config file.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.log.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.log.critical(f'Got: \'{error}\'.')
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
            self.log.critical('Error while adding option to git config file.')
            self.log.critical('Tried to add options to get all tags from remote repository.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.log.critical(f'Daemon is intended to be run as sudo/root.')
            else:
                self.log.critical(f'Got: \'{error}\'')
            sys.exit(1)
        else:
            self.log.debug('Added option to git config file: fetch all tags from remote repository.')
       
    
    def _compare_multidirect(self, old_list, new_list):
        """Compare lists multidirectionally"""
        
        self.log.name = f'{self.logger_name}_compare_multidirect::'
        
        self.log.debug('Tracking change multidirectionally:')
        ischange = False
        origin = old_list[-1]
        tocompare = {
            'first pass'    :   [ old_list, new_list, 'previously and current update list.', 'previously'],
            'second pass'   :   [ new_list, old_list, 'current and previously update list.', 'current' ]
            }
        
        for value in tocompare.values():
            self.log.debug('Between {0}'.format(value[2]))
            for upper_version in value[0]:
                isfound = False
                for lower_version in value[1]:
                    if StrictVersion(upper_version) == StrictVersion(lower_version):
                        self.log.debug(f'Keeping version \'{upper_version}\'.')
                        isfound = True
                        break
                if not isfound:
                    ischange = True
                    self.log.debug(f'Version \'{upper_version}\' not found in {value[3]} list.')
                    if StrictVersion(origin) >= StrictVersion(upper_version):
                        # we not adding anything but we just print this version is old one ...
                        self.log.debug(f'Removing old version \'{upper_version}\'.')
                    elif StrictVersion(origin) < StrictVersion(upper_version):
                        # ... and this version is new one.
                        # Any way we will replace all the list 
                        self.log.debug(f'Adding new version \'{upper_version}\'.')
        # Ok now if nothing change
        if not ischange:
            self.log.debug('Finally, didn\'t found any change, previously data has been kept.')
            return False
        else:
            return True
            


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

