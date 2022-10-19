# -*- coding: utf-8 -*-
# -*- python -*-
# Part of syuppo package
# Copyright © 2019-2021 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import os
import sys 
import re
import pathlib
import time
import errno
import subprocess
import io
import uuid
import logging

from threading import Lock
from portage.versions import pkgcmp
from portage.versions import pkgsplit
from portage.versions import vercmp
from portage.dbapi.porttree import portdbapi
from portage.dbapi.vartree import vardbapi

from syuppo.utils import FormatTimestamp
from syuppo.utils import StateInfo
from syuppo.utils import on_parent_exit
from syuppo.logger import ProcessLoggingHandler
from syuppo.logparser import LastSync
from syuppo.logparser import LastWorldUpdate 


try:
    import numpy
    import pexpect
except Exception as exc:
    print(f'Error: unexpected while loading module: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)

# TODO get news ?

class GenericHandler:
    """
    Generic handler
    """
    
    def stateopts(self):
        pass

        
        
class SyncHandler:
    """
    Manage informations related to 'sync'.
    """
    
    def __init__(self, **kwargs):
        super().__init__()
        self.__logger_name = f'::{__name__}::SyncHandler::'
        logger = logging.getLogger(f'{self.__logger_name}init::')
        
        self.sync = {
            # Values: ready | running | completed
            'status'        :   'ready',
            # Values: never sync | success | failed
            'state'         :   self.loaded_stateopts.get('sync state'),
            # Values: See sync_failed() layout keys
            'error'         :   self.loaded_stateopts.get('sync error'),
            # Values: >= 0
            'retry'         :   self.loaded_stateopts.get('sync retry'),
            # Values: >= 0
            'count'         :   self.loaded_stateopts.get('sync count'),
            # Values: int
            'timestamp'     :   self.loaded_stateopts.get('sync timestamp'),
            # Values: >= 86400
            'interval'      :   kwargs['interval'],
            # Values: int 
            'elapsed'       :   0,
            # Values: int 
            'remain'        :   0,
            # Values: >= 0
            'session'       :   0,   
            # Repos informations: 
            #   'names'     :   list of repos names
            #   'formatted' :   (str) list of repos names formatted
            #   'count'     :   (int) number of repos
            #   'msg'       :   repository / repositories
            #   'failed'    :   list that fail last sync
            #   'success'   :   list that successed last sync
            'repos'         :   self.get_repo_info(),
            # Values: True | False
            'cancel'        :   False,
            # Values: True | False
            'exit'          :   False,
            # locks for shared method/attr accross daemon threads
            'locks'         :   {
                # For running check_sync()
                'check'     :   Lock(),
                # Others are attrs
                'cancel'    :   Lock(),
                'remain'    :   Lock(),
                'elapsed'   :   Lock(),
                'status'    :   Lock()
                }                                                 
            }
        
        # Print warning if interval 'too big'
        # If interval > 30 days (2592000 seconds)
        if self.sync['interval'] > 2592000:
            interval = self.sync['interval']
            logger.warning("The selected synchronization interval is large: "
                          f"{self.format_timestamp(interval, granularity=5)}.")
    
    
    def stateopts(self):
        """
        Specific stateopts dict
        """
        super().stateopts()
        self.default_stateopts.update({
            '# Sync Opts'                    :   '',
            'sync count'                     :   0, 
            'sync state'                     :   'never sync',
            'sync error'                     :   0,
            'sync retry'                     :   0,
            'sync timestamp'                 :   0
            })
            
    def get_repo_info(self):
        """
        Get portage repos informations and return formatted
        """
        logger = logging.getLogger(f'::{self.__logger_name}::get_repo_info::')
        
        # Generic infos
        infos = { 
            'names'     :   [ ], 
            'formatted' :   'unknow',
            'count'     :   '(?)',
            'msg'       :   'repo',
            'failed'    :   [ ],
            'success'   :   [ ]
            }
        
        names = portdbapi().getRepositories()
        
        if names:
            names = sorted(names)
            count = len(names)
            msg = 'repositories'
            # get only first 6 elements if names > 6
            if count > 6:
                formatted = ', '.join(names[:6]) + ' (+' + str(count - 6) + ')'
            elif count == 1:
                msg = 'repository'
                formatted = ''.join(names)
            else:
                formatted = ', '.join(names)
            logger.debug(f"Informations extracted for {count} {msg}: "
                         f"{','.join(names)}")
            
            infos['names'] = names
            infos['formatted'] = formatted
            infos['count'] = count
            infos['msg'] = msg
            return infos
        
        logger.error("Failed to extract repositories informations"
                     " from portdbapi().getRepositories()")
        return infos
    
    def check_sync(self, init=False, recompute=False, external=False):
        """ 
        Checking sync repo timestamp, recompute time remaining
         and, or elapsed if requested, allow or deny sync.
        :param init:
            Display informations on program init. 
            Default False.
        :param recompute:
            Recalculate time remaining and elapsed. 
            Default False.
        :param external:
            Display external sync process status:
            failed/aborted or success.
            Default False.
        :return:
            True if sync allowed, else False.        
        """
        
        logger = logging.getLogger(f'{self.__logger_name}check_sync::')
        
        # Get the last emerge sync timestamp
        myparser = LastSync()
        sync_timestamp = myparser()
        
        if not sync_timestamp:
            # Don't need to logging anything it's 
            # already done in module logparser.
            return False
        
        current_timestamp = time.time()
        tosave = [ ]
        
        msg_repo = f"{self.sync['repos']['msg']}"
        
        if not sync_timestamp == self.sync['timestamp']:
            msg = (f"{msg_repo.capitalize()} have been sync"
                   " outside the program")
            # For first run / resetted statefile
            if not self.sync['timestamp']:
                msg = ("Setting sync timestamp from factory (0) to:"
                       f" {sync_timestamp}")
            # For external sync
            elif external:
                logger.info(f"Manual {msg_repo} synchronization"
                            " is successful.")
            
            logger.debug(f"{msg}, forcing pretend world...")
            # Any way, run pretend world
            with self.pretend['locks']['proceed']:
                self.pretend['proceed'] = True
            self.sync['timestamp'] = sync_timestamp
            tosave.append(['sync timestamp', self.sync['timestamp']])
            recompute = True
        elif external:
            logger.info(f"Manual {msg_repo} synchronization failed"
                        " or aborted.")
        
        # Compute / recompute time remain
        # This shouldn't be done every time method check_sync()
        # is call because it will erase the arbitrary time remain
        # set by method dosync() when sync failed (network error)
        if recompute:
            logger.debug('Recompute is enable.')
            
            current = self.sync['elapsed']
            with self.sync['locks']['remain']:
                self.sync['elapsed'] = round(current_timestamp - sync_timestamp)
            logger.debug(f"Sync elapsed timestamp: Current: {current}"
                         f", recalculate: {self.sync['elapsed']}")
            
            current = self.sync['remain']
            with self.sync['locks']['remain']:
                self.sync['remain'] = self.sync['interval'] - self.sync['elapsed']
            logger.debug(f"Sync remain timestamp: Current: {current}"
                         f", recalculate: {self.sync['remain']}")
        
        if init:
            logger.info(f"Found {self.sync['repos']['count']}"
                        f" {self.sync['repos']['msg']} to sync:" 
                        f" {self.sync['repos']['formatted']}")        
        
        # For logging in debug / info
        for key in 'interval', 'elapsed', 'remain':
            # For logging in: INFO
            if init:
                # TEST keep default granularity for info
                timestamp = self.format_timestamp(self.sync[key])
                logger.info(f"{msg_repo.capitalize()} sync {key}"
                            f" time: {timestamp}")
            # For logging in: DEBUG
            if recompute and key in ('elapsed', 'remain'):
                continue
            # For debug, full ouput (granularity=5)
            timestamp = self.format_timestamp(self.sync[key],
                                                      granularity=5)
            logger.debug(f"{msg_repo.capitalize()} sync {key}"
                         f" time: {timestamp}")
    
        if tosave:
            self.stateinfo.save(*tosave)
            
        if self.sync['remain'] <= 0:
            return True # We can sync :)
        return False
    
    def dosync(self):
        """ 
        Updating repo(s) 
        """
        
        logger = logging.getLogger(f'{self.__logger_name}dosync::')
               
        # This is for asyncio: don't run twice
        with self.sync['locks']['status']:
            self.sync['status'] = 'running'
        
        # Refresh repositories infos
        self.sync['repos'] = self.get_repo_info()
        
        # For debug: display all the repositories
        logger.debug(f"Start syncing {self.sync['repos']['count']}" 
                     f" {self.sync['repos']['msg']}:" 
                     f" {', '.join(self.sync['repos']['names'])}")
        logger.info(f"Start syncing {self.sync['repos']['count']}" 
                     f" {self.sync['repos']['msg']}:" 
                     f" {self.sync['repos']['formatted']}")
               
        if not self.dryrun:
            # Init logging
            logger.debug('Initializing logging handler:')
            logger.debug('Name: synclog')
            processlog = ProcessLoggingHandler(name='synclog')
            logger.debug('Writing to: {0}'.format(self.pathdir['synclog']))
            log_writer = processlog.dolog(self.pathdir['synclog'])
            logger.debug('Log level: info')
            log_writer.setLevel(processlog.logging.INFO)
        else:
            log_writer = logging.getLogger(f'{self.__logger_name}write_sync_log::')
        
        # Errors related
        # See failed_sync()
        error = 'unexcepted'
        # Network failure # TODO
        manifest_failure = re.compile(r'^!!!.Manifest.verification.impossible'
                                      '.due.to.keyring.problem:$')
        found_manifest_failure = False
        gpg_network_unreachable = re.compile(r'^gpg:.keyserver.refresh.failed:'
                                             '.Network.is.unreachable$')
               
        # Get return code for each repo
        repo_failed = re.compile(r'^Action:.sync.for.repo:\s(.*),'
                                 '.returned.code.=.1$')
        repo_success = re.compile(r'^Action:.sync.for.repo:\s(.*),'
                                  '.returned.code.=.0$')
        self.sync['repos']['failed'] = [ ]
        self.sync['repos']['success'] = [ ]
        
        # Running sync command using sudo (as root)
        cmd = '/usr/bin/sudo'
        args = [ '/usr/bin/emerge', '--sync' ]
        msg = f"Stop {self.sync['repos']['msg']} synchronization"
        
        # Running using pexpect
        return_code, logfile = self._pexpect('sync', cmd, args, msg)
        
        if return_code == 'exit':
            return
        
        # Write and in the same time analysis logfile
        log_writer.info('##########################################\n')
        for line in logfile:
            # Write
            log_writer.info(line)
             # detected network failure for main gentoo repo 
            if found_manifest_failure:
                # So make sure it's network related 
                if gpg_network_unreachable.match(line):
                    error = 'network'
            if manifest_failure.match(line):
                found_manifest_failure = True
            # get return code for each repo
            if repo_failed.match(line):
                name = repo_failed.match(line).group(1)
                self.sync['repos']['failed'].append(name)
            if repo_success.match(line):
                name = repo_success.match(line).group(1)
                self.sync['repos']['success'].append(name)
        
        if self.sync['repos']['success']:
            logger.debug("Repo sync completed: "
                         f"{', '.join(self.sync['repos']['success'])}")
        if self.sync['repos']['failed']:
            logger.debug("Repo sync failed: "
                         f"{', '.join(self.sync['repos']['failed'])}")
        # WARNING TODO THIS has to be rewritten in this way: If repo "gentoo"
        # (main) is sync successfully, then we have to get his timestamp. 
        # This have to be tread has a success sync. If other repos failed, then 
        # its will be skip (and information about which one, how many times and
        # the error have to be given). If repo sync for gentoo failed, than it will be
        # retry without other repo which sync successfully (to test).
        # WARNING TODO
        
        if return_code:
            attributes = self.failed_sync(self.sync['retry'], error)
        else:
            attributes = self.success_sync()
            
        tosave = [ ]
        for key, value in attributes.items():
            # Make sure key exists
            if key in self.sync:
                if not self.sync[key] == value:
                    logger.debug(f"Changing value for sync['{key}'] from"
                                 f" {self.sync[key]} to {value}")
                    # Make sure to use locks if exists
                    if key in self.sync['locks']:
                        logger.debug("Using locks() for changing "
                                     f"sync['{key}']")
                        with self.sync['locks'][key]:
                            self.sync[key] = value
                    else:
                        logger.debug("Not using locks() for changing "
                                     f"sync['{key}']")
                        self.sync[key] = value
                    # Save key only if exists from loaded_stateopts
                    if f"sync {key}" in self.loaded_stateopts:
                        logger.debug(f"Append for saving: 'sync {key} : "
                                     f"{value}'")
                        tosave.append([f"sync {key}", self.sync[key]])
                    else:
                        logger.debug(f"Not append for saving: 'sync {key} : "
                                     f"{value}'")
                else:
                    logger.debug(f"Keeping same value of sync['{key}']:"
                                 f" {value}")
            else:
                logger.error(f"Missing key '{key}' in sync dictionnary"
                               " (please report this)")
            
        # Then save every thing in one shot
        if tosave:
            self.stateinfo.save(*tosave)
    
    def failed_sync(self, retry, error):
        """
        Proceed when sync process failed.
        :param error:
            Error type, to choose between 'network' and
            'unexcepted'.
        :param retry:
            How many retry have been already run.
        """
        logger = logging.getLogger(f'{self.__logger_name}failed_sync::')
        
        layout = {
            # TODO: this could be tweaked ?
            # sync will make ALOT of time to fail.
            # See : /etc/portage/repos.conf/gentoo.conf 
            # @2020-23-01 (~30min): 
            # sync-openpgp-key-refresh-retry-count = 40
            # sync-openpgp-key-refresh-retry-overall-timeout = 1200
            # first 5 times @ 600s (10min) - real is : 40min
            # after 5 times @ 3600s (1h) - real is : 1h30
            # then reset to interval (so mini is 24H)
            # For Network error: 
            #   retry 5 times @ 600s
            #   retry 5 times @ 3600s
            #   then retry forever @ selected interval
            'network'    : ((0, 600), (4, 3600), (9, self.sync['interval'])),
            # For Other errors:
            #   retry 1 time @ 600s
            #   retry 1 time @ 3600s
            #   then retry forever @ selected interval
            'unexcepted' : ((0, 600), (1, 3600), (2, self.sync['interval']))
            }
        
        repos = f"{', '.join(self.sync['repos']['failed'])}"
        msg_count = 'this repository'
        if len(self.sync['repos']['failed']) > 1:
            msg_count = 'these repositories'
        msg_error = 'an'
        # Check out if we have an network failure for repo gentoo
        if error == 'network':
            msg_error = 'a'
        
        # Select the remain interval
        # depending on error type
        for item in layout[error]:
            if item[0] <= retry:
                remain = item[1]
        
        msg_on_retry = ''
        if retry == 1:
            msg_on_retry = ' (1 time already)'
        elif retry > 1:
            msg_on_retry = f" ({retry} times already)"
                
        delay =  self.format_timestamp(remain, granularity=5)
        logger.error(f"Synchronization of {msg_count} failed due to "
                     f"{msg_error} {error} error: {repos}, will "
                     f"retry in {delay}{msg_on_retry}.")
            
        logger.debug(f"Incrementing sync retry from {retry} to {retry+1}")
                       
        return { 
            'error'     :   error, 
            'state'     :   'failed', 
            'retry'     :   retry+1, 
            'remain'    :   remain, 
            'status'    :   'ready' 
            }
                
    def success_sync(self):
        """
        Proceed when sync process is successful.
        """
        
        logger = logging.getLogger(f'{self.__logger_name}success_sync::')
        
        msg_repo = f"{self.sync['repos']['msg']}"
        logger.info(f"{msg_repo.capitalize()} synchronization is successful.")
        
        for count in 'count', 'session':
            logger.debug(f"Incrementing {count} count from "
                         f"{self.sync[count]} to "
                         f"{self.sync[count]+1}")
        
        # Get sync timestamp from emerge.log
        logger.debug('Initializing emerge log parser:')
        myparser = LastSync(log=self.pathdir['emergelog'])
        logger.debug(f"Parsing file: {self.pathdir['emergelog']}")
        logger.debug('Searching last sync timestamp.')
        sync_timestamp = myparser()
        
        if sync_timestamp:
            if sync_timestamp == self.sync['timestamp']:
                logger.warning(f"Bug in class {self.__class__.__name__}, "
                               "method: success_sync(): sync timestamp are "
                               "equal...")
            else:
                logger.debug("Updating sync timestamp from "
                             f"{self.sync['timestamp']} to "
                             f"{sync_timestamp}")
                
        logger.debug(f"Resetting remain interval to {self.sync['interval']}")
        
        delay = self.format_timestamp(self.sync['interval'], granularity=5)
        logger.info(f"Next synchronization in {delay}.")
        
        # At the end of successfully sync, run pretend_world()
        with self.pretend['locks']['proceed']:
            self.pretend['proceed'] = True
        
        return { 
            'error'         :   0, 
            'state'         :   'success', 
            'retry'         :   0, 
            'remain'        :   self.sync['interval'],
            'elapsed'       :   0,
            'status'        :   'completed',
            'session'       :   self.sync['session']+1, 
            'count'         :   self.sync['count']+1,
            'timestamp'     :   sync_timestamp 
            }



class PretendHandler:
    """
    Manage informations related to 'pretend'.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__logger_name = f'::{__name__}::PretendHandler::'
        logger = logging.getLogger(f'{self.__logger_name}init::')
        
        # Manage pretend available packages updates 
        self.pretend = {
            # True when pretend_world() should be run
            'proceed'   :   False,
            # values: ready | running | completed
            'status'    :   'ready',
            # Packages to update
            'packages'  :   self.loaded_stateopts.get('pretend packages'),
            # Interval between two pretend_world() 
            # TODO could be tweaked
            'interval'  :   600,
            # Time between two pretend_world() lauch (avoid spamming)
            'remain'    :   600,
            # (dbus) and for async call implantation.
            'forced'    :   False,
            # cancelling pretend_world pexpect when it 
            # detect world update in progress
            'cancel'    :   False,
            # For exiting 
            'exit'      :   False,
            # same here so we know it has been cancelled if True
            'cancelled' :   False,
            # locks for shared method/attr accross daemon threads
            'locks'     :   {
                # For calling pretend_world()
                'proceed'   :   Lock(),
                # Others are attrs
                'cancel'    :   Lock(),
                'cancelled' :   Lock(),
                'status'    :   Lock()
                }
            }
    
    def stateopts(self):
        """
        Specific stateopts dict
        """
        super().stateopts()
        self.default_stateopts.update({
            '# Pretend Opts'                 :   '',
            # Default to -1010 so we know it's first run
            'pretend packages'               :   -1010
            })
        
    def pretend_world(self):
        """
        Get how many package to update
        """
        # TODO more verbose for debug
        logger = logging.getLogger(f'{self.__logger_name}pretend_world::')
        
        tosave = [ ]
        
        # Disable pretend authorization
        with self.pretend['locks']['proceed']:
            self.pretend['proceed'] = False
        with self.pretend['locks']['status']:
            self.pretend['status'] = 'running'
        
        logger.debug('Start searching available package(s) update.')
                
        packages = False
        retry = 0
        extract_packages = re.compile(r'^Total:.(\d+).package.*$')        
        
        if not self.dryrun:
            # Init logger
            logger.debug('Initializing logging handler.')
            logger.debug('Name: pretendlog')
            processlog = ProcessLoggingHandler(name='pretendlog')
            logger.debug('Writing to: {0}'.format(self.pathdir['pretendlog']))
            log_writer = processlog.dolog(self.pathdir['pretendlog'])
            logger.debug('Log level: info')
            log_writer.setLevel(processlog.logging.INFO)
        else:
            name = f'{self.__logger_name}write_pretend_world_log::'
            log_writer = logging.getLogger(name)
            
        cmd = '/usr/bin/emerge'
        args = [ '--verbose', '--pretend', '--deep', 
                  '--newuse', '--update', '@world', '--with-bdeps=y' ]
        cmd_line = f"{cmd} {' '.join(args)}"
        msg = 'Stop checking for available updates'
        
        while retry < 2:
            logger.debug(f"Running {cmd_line}")
            return_code, logfile = self._pexpect('pretend', cmd, 
                                                 args, msg)
            if return_code == 'exit':
                return
            
            # Get package number and write log in the same time
            log_writer.info("##### START ####")
            log_writer.info(f"Command: {cmd_line}")
            for line in logfile:
                log_writer.info(line)
                if extract_packages.match(line):
                    packages = int(extract_packages.match(line).group(1))
                    # don't retry we got packages
                    retry = 2
            log_writer.info("Terminate process: exit with status "
                            f"'{return_code}'")
            log_writer.info("##### END ####")
            
            # We can have return_code > 0 and 
            # matching packages to update.
            # This can arrived when there is, for exemple,
            # packages conflict (solved by skipping).
            # if this is the case, continue anyway.
            msg_on_return_code = 'Found'
            if return_code:
                msg_on_return_code = 'Anyway found'
                logger.error("Got error while searching for available "
                             "package(s) update.")
                logger.error(f"Command: {cmd_line}, return code: "
                             f"{return_code}")
                logger.error("You can retrieve log from: "
                             f"{self.pathdir['pretendlog']}")
                if retry < 1:
                    logger.error('Retrying without opts \'--with-bdeps\'...')
        
            # Ok so do we got update package ?
            if retry == 2:
                if packages > 1:
                    msg = (f'{msg_on_return_code} {packages} '
                           'packages to update.')
                elif packages == 1:
                    msg = f'{msg_on_return_code} only one package to update.'
                # no package found
                else:
                    if 'Anyway' in msg_on_return_code: 
                        msg = f'Anyway system is up to date.'
                    else:
                        msg = f'System is up to date.'
                logger.debug("Successfully search for packages update:"
                             f" {packages}")
                logger.info(msg)
            else:
                # Remove --with-bdeps and retry one more time.
                retry += 1
                if retry < 2:
                    args.pop()
                    logger.debug("Couldn't found how many package to update,"
                                 " retrying without opt '--with bdeps'.")

        # Make sure we have some packages
        if packages:
            self.change_packages_value(tochange=packages)
        else:
            self.change_packages_value(tochange=0)
                
        with self.pretend['locks']['cancelled']:
            self.pretend['cancelled'] = False
        with self.pretend['locks']['status']:
            self.pretend['status'] = 'completed'
            
    def change_packages_value(self, toadd="def", tosubtract="def", 
                              tochange="def"):
        """
        Add, subtract or change available package update value
        param toadd:
            Value to add. Default: def.
        param tosubtract:
            Value to subtract. Default: def.
        param tochange:
            Change value. Default: def.
        """
        name = 'change_packages_value'
        logger = logging.getLogger(f'{self.__logger_name}{name}::')
        
        logger.debug(f"Running with toadd={toadd}, tosubtract={tosubtract}"
                     f" and tochange={tochange}")
        
        packages = self.pretend['packages']
        
        if toadd == "def" and tosubtract == "def" and tochange == "def":
            logger.error("change_packages_value called without value...")
            return
        
        if not toadd == "def":
            logger.debug(f"Adding +{toadd} to packages updates: {packages}")
            packages += toadd
        elif not tosubtract == "def":
            logger.debug(f"Subtracting -{toadd} to packages updates: "
                         f"{packages}")
            packages -= tosubtract
            if packages < 0:
                logger.error("Found packages updates < 0 when subtracting"
                             f" {tosubtract}, previously: "
                             f"{self.pretend['packages']} "
                             "(please report this)")
                packages = 0
        elif not tochange == "def":
            logger.debug(f"Changing packages updates from {packages} to"
                         f" {tochange}")
            packages = tochange
        
        if not packages == self.pretend['packages']:
            self.pretend['packages'] = packages
            self.stateinfo.save(['pretend packages', self.pretend['packages']])
                
    
    
class PortageHandler:
    """
    Manage informations related to 'portage'.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__logger_name = f'::{__name__}::PortageHandler::'
        logger = logging.getLogger(f'{self.__logger_name}init::')
        
        # Portage attributes
        self.portage = {
            'current'   :   self.loaded_stateopts.get('portage current'),
            'latest'    :   self.loaded_stateopts.get('portage latest'),
            'available' :   self.loaded_stateopts.get('portage available')
            }
    
    def stateopts(self):
        """
        Specific stateopts dict
        """
        super().stateopts()
        self.default_stateopts.update({
            '# Portage Opts'                 :   '',
            'portage available'              :   False,
            'portage current'                :   '0.0',
            'portage latest'                 :   '0.0',
            })
    
    def available_portage_update(self, detected=False, init=False):
        """
        Check if an update to portage is available.
        """
        
        # TODO: be more verbose for debug !
        name = 'available_portage_update'
        logger = logging.getLogger(f'{self.__logger_name}{name}::')
        
        logger.debug(f"Running with detected={detected}, init={init}")
                
        self.available = False
        self.latest = False
        self.current = False
        
        # First, any way get installed and latest
        current = vardbapi().match('portage')[0]
        latest = portdbapi().xmatch('bestmatch-visible', 'portage')
        
        # Then just compare
        # From site-packages/portage/versions.py
        #   @param mypkg: either a pv or cpv
        #   @return:
        #   1. None if input is invalid.
        #   2. (pn, ver, rev) if input is pv
        #   3. (cp, ver, rev) if input is a cpv
        result = pkgcmp(pkgsplit(latest),pkgsplit(current))
        # From site-packages/portage/versions.py
        # Parameters:
        # pkg1 (list (example: ['test', '1.0', 'r1'])) - 
        #                           package to compare with
        # pkg2 (list (example: ['test', '1.0', 'r1'])) - 
        #                           package to compare againts
        # Returns: None or integer
        # None if package names are not the same
        # 1 if pkg1 is greater than pkg2
        # -1 if pkg1 is less than pkg2
        # 0 if pkg1 equals pkg2
        if result == None or result == -1:
            msg = 'no result (package names are not the same ?!)'
            if result == -1:
                msg = ('the latest version available is lower than the'
                       ' one installed...')
            logger.error("FAILED to compare versions when obtaining update "
                         "informations for the portage package.")
            logger.error(f"Result is: {msg}")
            logger.error(f"Current portage version: {current}, latest:"
                         f" {latest}.")
            # Return is ignored for the moment...
            # TODO ??
            return
        
        # Split current version
        # as we don't know yet if latest > current
        split = pkgsplit(current)
        self.current = split[1]
        if not split[2] == 'r0':
            self.current = '-'.join(split[-2:])
        
        # Check if an update to portage is available
        if result:
            # Now, split latest because > current
            split = pkgsplit(latest)
            self.latest = split[1]
            if not split[2] == 'r0':
                self.latest = '-'.join(split[-2:])
            logger.debug(f"Found an update to portage (from {self.current}"
                         f" to {self.latest}).")
            # Print only one time when program start
            if init:
               logger.info("Found an update to portage (from "
                           f"{self.current} to {self.latest}).")
            self.available = True
        else:
            logger.debug("No update to portage package is available" 
                        f" (current version: {self.current})")
            self.available = False
        
        # For detected we have to compare current extracted
        # version and last current know version (so from
        # self.portage['current']. Both versions are already
        # split 
        if detected:
            # From site-packages/portage/versions.py
            #   Compare two versions
            #   Example usage:
            #       >>> from portage.versions import vercmp
            #       >>> vercmp('1.0-r1','1.2-r3')
            #       negative number    
            #       >>> vercmp('1.3','1.2-r3')
            #       positive number
            #       >>> vercmp('1.0_p3','1.0_p3')
            #       0
            #   @param pkg1: version to compare with 
            #       (see ver_regexp in portage.versions.py)
            #   @type pkg1: string (example: "2.1.2-r3")
            #   @param pkg2: version to compare againts 
            #       (see ver_regexp in portage.versions.py)
            #   @type pkg2: string (example: "2.1.2_rc5")
            #   @rtype: None or float
            #   @return:
            #   1. positive if ver1 is greater than ver2
            #   2. negative if ver1 is less than ver2
            #   3. 0 if ver1 equals ver2
            #   4. None if ver1 or ver2 are invalid 
            #       (see ver_regexp in portage.versions.py)
            compare = vercmp(self.portage['current'], self.current)
            msg = False
            add_msg = ''
            if compare < 0:
                # If not available and it have been updated
                # than it have been updated to latest one
                if not self.available:
                    # TEST If no more update available
                    # then remove '1' from self.pretend['packages']
                    logger.debug("Removing 1 to available updates")
                    self.change_packages_value(tosubtract=1)
                    add_msg = 'latest '
                msg = (f"The portage package has been updated (from "
                       f"{self.portage['current']} to "
                       f"{add_msg}{self.current}).")
            elif compare > 0:
                # Same here but reversed: if it was not 
                # available (self.portage['available'])
                # and now it is (self.available) than
                # it have been downgraded from latest.
                if not self.portage['available'] and self.available:
                    # TEST same here but reversed as well:
                    # add 1 to available updates
                    logger.debug("Adding 1 to available updates")
                    self.change_packages_value(toadd=1)
                    add_msg = 'latest '
                msg = (f"The portage package has been downgraded (from "
                       f"{add_msg}{self.portage['current']} to "
                       f"{self.current}).")
            elif compare == 0:
                # This have been aborted
                msg = ("The portage package process has been aborted.")
            
            # Just skipp if msg = False
            # so that mean compare == None
            if msg:
                logger.info(msg)
        
        tosave = [ ]
        to_print = True
        # Update only if change
        for key in 'current', 'latest', 'available':
            if not self.portage[key] == getattr(self, key):
                # This print if there a new version of portage available
                # even if there is already an older version available
                # TEST: if checking only for key latest than it could
                # be == to current so check also result.
                if key == 'latest' and result and to_print:
                    logger.info("Found an update to portage (from "
                                f"{self.current} to {self.latest}).")
                    to_print = False
                
                self.portage[key] = getattr(self, key)
                tosave.append([f'portage {key}', self.portage[key]])
        
        if tosave:
            self.stateinfo.save(*tosave)
        
    
    
class WorldHandler:
    """
    Manage informations related to 'world'
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__logger_name = f'::{__name__}::WorldHandler::'
        logger = logging.getLogger(f'{self.__logger_name}init::')
        
        # Last global update informations
        # For more details see module logparser
        self.world = {
            'state'     :   self.loaded_stateopts.get('world last state'), 
            'start'     :   self.loaded_stateopts.get('world last start'),
            'stop'      :   self.loaded_stateopts.get('world last stop'),
            'total'     :   self.loaded_stateopts.get('world last total'),
            'failed'    :   self.loaded_stateopts.get('world last failed'),
            'nfailed'   :   self.loaded_stateopts.get('world last nfailed')
            }
    
    def stateopts(self):
        """
        Specific stateopts dict
        """
        super().stateopts()
        self.default_stateopts.update({
            '# World Opts'                  :   '',
            'world last start'              :   0,
            'world last stop'               :   0,
            'world last state'              :   'unknow',
            'world last total'              :   0,
            'world last failed'             :   'none',
            'world last nfailed'            :   0
            })
    
    def get_last_world_update(self, detected=False):
        """
        Getting last world update informations
        """
        
        name = 'get_last_world_update'
        logger = logging.getLogger(f'{self.__logger_name}{name}::')
        logger.debug(f'Running with detected={detected}')
        
        myparser = LastWorldUpdate(advanced_debug=self.vdebug['logparser'],
                                   log=self.pathdir['emergelog'])
        get_world_info = myparser()
        
        updated = False
        tosave = [ ]
        if get_world_info:
            to_print = True
            # Write only if change
            for key in self.world.keys():
                if not self.world[key] == get_world_info[key]:
                    # Ok this mean world update has been run
                    # TEST DONT run pretend_world()
                    #with self.pretend['locks']['proceed']:
                        #self.pretend['proceed'] = True
                    updated = True
                    if to_print:
                        logger.info('Global update have been run.')
                        to_print = False
                            
                    self.world[key] = get_world_info[key]
                    tosave.append([f'world last {key}', self.world[key]])
            ## For now, if incomplete and fragment opts 
            # from LastWorldUpdate are left to default
            # then, the only rejected group should be the first
            # package that failed. And this will not change
            # how many package to update (so don't need to run
            # pretend...) TEST pretend is no more run ...
            if not updated and detected:
                logger.info("Global update have been aborted or"
                            " failed to emerge first package.")
            elif not updated:
                logger.debug("Global update haven't been run," 
                             " keeping last know informations.")
            elif updated:
                # TEST DONT run pretend_world() 
                # Recalculate how many package left
                # (if any) using key 'nfailed' and 'total'
                # And so pretend_world() will be run only
                # after a successfully sync ;)
                if not self.world['state'] == 'completed':
                    self.recompute_packages_left()
                else:
                    logger.debug("State is 'completed' setting pretend"
                                 " packages to 0.")
                    self.change_packages_value(tochange=0)
                    #self.pretend['packages'] = 0
                    #tosave.append(['pretend packages', self.pretend['packages']])
        # Saving in one shot
        if tosave:
            self.stateinfo.save(*tosave)
        if updated:
            return True
        return False
    
    def recompute_packages_left(self):
        """
        Recompute package left only for 
        state != 'completed'
        """
        name = 'recompute_packages_left'
        logger = logging.getLogger(f'{self.__logger_name}{name}::')
        
        packages = self.pretend['packages']        
        if not self.world['total'] == self.pretend['packages']:
            # Make sure it's not first run ever
            if self.pretend['packages'] == -1010:
                logger.debug("First run detected, skipping...")
                # DONT save anything because pretend_world() will be
                # run (first run ever)
                return
            
            logger.warning("Updated packages extracted from"
                           f" '{self.pathdir['emergelog']}' and from"
                           " pretend emerge process are NOT equal...")
            # So calculate using total from logparser module
            packages = self.world['total']
        else:
            logger.debug("Will use default packages number from pretend emerge"
                         f" process: {packages}")
                
        left = packages - (self.world['total'] - self.world['nfailed'])
        logger.debug(f"Packages left to update: {left}")
        if left < 1:
            logger.warning("The last world update state extracted from"
                           f" '{self.pathdir['emergelog']}' is NOT 'completed'"
                           f" BUT found update left < 1: {left}.")
            logger.warning("Resetting update to '0' but please report this")
            left = 0
        
        self.change_packages_value(tochange=left)
        #self.pretend['packages'] = left
        #self.stateinfo.save(['pretend packages', self.pretend['packages']])



class BaseHandler(PortageHandler, WorldHandler, PretendHandler,
                  SyncHandler, GenericHandler):
    """
    Base class for all Handler
    """
    def __init__(self, **kwargs):
        for key in 'interval', 'pathdir', 'dryrun', 'vdebug':
            if not key in kwargs:
                # Print to stderr :
                # when running in init mode stderr is redirect to a log file
                # logger is not yet initialized 
                print(f"Crit: missing argument: {key}," 
                      f"calling module: {__name__}.", file=sys.stderr)
                print('Crit: exiting with status \'1\'.', file=sys.stderr)
                sys.exit(1)
                
        self.pathdir = kwargs['pathdir']
        self.dryrun = kwargs['dryrun']
        self.vdebug = kwargs['vdebug']
        
        # Init timestamp converter/formatter 
        self.format_timestamp = FormatTimestamp(advanced_debug=self.vdebug['formattimestamp'])
        
        # Init logger
        self.__logger_name = f'::{__name__}::BaseHandler::'
        logger = logging.getLogger(f'{self.__logger_name}init::')
        
        # python >= 3.7 preserve dict order 
        # Now each inheritance class provide
        # is own stateopts
        self.default_stateopts = {
            f"# Wrote by {self.pathdir['prog_name']}" 
            + f" version: {self.pathdir['prog_version']}"   :   '',
            '# Please don\'t edit this file.'               :   '',
            }
        # Load stateopts from all other class
        super().stateopts()
        
        # Init save/load info file 
        self.stateinfo = StateInfo(pathdir=self.pathdir, 
                                   stateopts=self.default_stateopts, 
                                   dryrun=self.dryrun)
        # Retrieve status of saving from stateinfo
        # WARNING We have to be really carefull about this:
        # As of 2020/11/15 stateinfo can't be call twice in the same time.
        # But for the future better to leave comment and WARNING
        self.saving_status = self.stateinfo.saving
        self.loaded_stateopts = False
        if self.stateinfo.newfile or self.dryrun:
            # Don't need to load from StateInfo as it just create file 
            # or we don't want to write anything:
            # add default_stateopts from here
            self.loaded_stateopts = self.default_stateopts
        else:
            # Ok load from StateInfo in one time
            # We don't need to convert from str() to another type
            # it's done auto by class StateInfo
            self.loaded_stateopts = self.stateinfo.load()
        
        # Init all other class
        super().__init__(**kwargs)
        
    def _pexpect(self, proc, cmd, args, msg):
        """
        Run specific process using pexpect
        
        :param proc:
            This should be call with 'sync' or 'pretend'.
        :param cmd:
            The command to run.
        :param args:
            The arguments as a list.
        :param msg:
            A specific msg when calling exit or cancel.
        :return:
            An iterable with, first element is the return
            code of the command or 'exit' if aborted/cancelled. 
            The second element is the logfile if success, else False.
        """
        logger = logging.getLogger(f'{self.__logger_name}_pexpect::')
        
        myattr = getattr(self, proc)
        # This keys match keys from module 'utils'
        # class 'CheckProcRunning', method 'check':
        # 'world', 'system', 'sync', 'portage'
        # Added: distinction between internal and external sync
        generic_msg = 'has been detected.'
        __msg = {
            'sync internal' :   'an automatic synchronization',
            'sync external' :   'a manual synchronization',
            'world'         :   'a global update',
            'system'        :   'a system update'
            }
        
        child = pexpect.spawn(cmd, args=args, encoding='utf-8', 
                              preexec_fn=on_parent_exit(),
                              timeout=None)
        # We capture log
        mycapture = io.StringIO()
        child.logfile = mycapture
        # Wait non blocking
        # WARNING DONT set this to 0 or it will
        # eat a LOT of cpu: specially when there is
        # no data to read (ex: sync and network problem)
        # WARNING
        pexpect_timeout = 1
        while not child.closed and child.isalive():
            if myattr['cancel']:
                # So we want to cancel
                # Just break 
                # child still alive
                logger.debug(f"Received cancel order: {myattr['cancel']}")
                break
            if myattr['exit']:
                # Same here: child still alive
                logger.debug('Received exit order.')
                break
            try:
                child.read_nonblocking(size=1, timeout=pexpect_timeout)
                # We don't care about recording what ever since we 
                # recording from child.logfile, 
                # just wait until reach EOF.
            except pexpect.EOF:
                # Process have finish
                # Don't close here
                break
            except pexpect.TIMEOUT:
                # Just continue until EOF
                # Setting a timeout > 1, will
                # just made more lantency when 
                # calling cancel/exit ...
                # BUT timeout = 0 will eat A LOT
                # of cpu doing nothing...
                continue
        
        if myattr['exit'] or myattr['cancel']:
            logger.debug("Shutting down pexpect process running"
                         f" command: '{cmd}' and args: "
                         f"'{' '.join(args)}'")
            mycapture.close()
            child.terminate(force=True)
            child.close(force=True)
            
            if myattr['exit']:
                logger.debug('...exiting now, ...bye.')
                myattr['exit'] = 'Done'
                return 'exit', False
            
            # Log specific message
            logger.warning(f"{msg}: {__msg[myattr['cancel']]} {generic_msg}")
            # Don't return process log because 
            # it's have been cancelled (process log is only partial)
            if proc == 'pretend':
                with myattr['locks']['cancelled']:
                    myattr['cancelled'] = True
            with myattr['locks']['cancel']:
                myattr['cancel'] = False
            with myattr['locks']['status']:
                myattr['status'] = 'ready'
            # skip everything else
            return 'exit', False
                
        # Process finished
        mylog = mycapture.getvalue()
        mycapture.close()
        child.close()
        status = child.wait()
        return status, mylog.splitlines()
  


