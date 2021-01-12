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
from syuppo.logger import ProcessLoggingHandler
from syuppo.logparser import LastSync
from syuppo.logparser import LastWorldUpdate 
from syuppo.utils import on_parent_exit

try:
    import numpy
    import pexpect
except Exception as exc:
    print(f'Got unexcept error while loading module: {exc}')
    sys.exit(1)

# TODO TODO TODO stablize API
# TODO get news ?

class PortageHandler:
    """
    Portage tracking class
    """
    def __init__(self, **kwargs):
        for key in 'interval', 'pathdir', 'dryrun', 'vdebug':
            if not key in kwargs:
                # Print to stderr :
                # when running in init mode stderr is redirect to a log file
                # logger is not yet initialized 
                print(f'Crit: missing argument: {key}, calling module: {__name__}.', file=sys.stderr)
                print('Crit: exiting with status \'1\'.', file=sys.stderr)
                sys.exit(1)
                
        self.pathdir = kwargs['pathdir']
        self.dryrun = kwargs['dryrun']
        self.vdebug = kwargs['vdebug']
        # Implent this for pretend_world() and dosync()
        # Because they are run in a dedicated thread (asyncio) 
        # And they won't exit until finished
        self.exit_now = { }
        self.exit_now['sync'] = False
        self.exit_now['pretend'] = False
        # Init timestamp converter/formatter 
        self.format_timestamp = FormatTimestamp(advanced_debug=self.vdebug['formattimestamp'])
        # Init logger
        self.logger_name = f'::{__name__}::PortageHandler::'
        logger = logging.getLogger(f'{self.logger_name}init::')
        
        # compatibility for python < 3.7 (dict is not ordered)
        if sys.version_info[:2] < (3, 7):
            from collections import OrderedDict 
            default_stateopts = OrderedDict(
            ('# Wrote by {0}'.format(self.pathdir['prog_name']) 
             + ' version: {0}'.format(self.pathdir['prog_version']), ''),
            ('# Please don\'t edit this file.',   ''),
            ('# Sync Opts'                    ,   ''),
            ('sync count'                     ,   0), 
            ('sync state'                     ,   'never sync'),
            ('sync network_error'             ,   0),
            ('sync retry'                     ,   0),
            ('sync timestamp'                 ,   0),
            ('# World Opts'                   ,   ''),
            ('world packages'                 ,   0),
            ('world last start'               ,   0),
            ('world last stop'                ,   0),
            ('world last state'               ,   'unknow'),
            ('world last total'               ,   0),
            ('world last failed'              ,   'none'),
            ('# Portage Opts'                 ,   ''),
            ('portage available'              ,   False),
            ('portage current'                ,   '0.0'),
            ('portage latest'                 ,   '0.0'),
            )
        else:
            # python >= 3.7 preserve dict order 
            default_stateopts = {
                '# Wrote by {0}'.format(self.pathdir['prog_name']) 
                + ' version: {0}'.format(self.pathdir['prog_version']): '',
                '# Please don\'t edit this file.':   '',
                '# Sync Opts'                    :   '',
                'sync count'                     :   0, 
                'sync state'                     :   'never sync',
                'sync network_error'             :   0,
                'sync retry'                     :   0,
                'sync timestamp'                 :   0,
                '# World Opts'                   :   '',
                'world packages'                 :   0,
                'world last start'               :   0,
                'world last stop'                :   0,
                'world last state'               :   'unknow',
                'world last total'               :   0,
                'world last failed'              :   'none',
                '# Portage Opts'                 :   '',
                'portage available'              :   False,
                'portage current'                :   '0.0',
                'portage latest'                 :   '0.0',
                }
        
        # Init save/load info file 
        self.stateinfo = StateInfo(pathdir=self.pathdir, stateopts=default_stateopts, dryrun=self.dryrun)
        # Retrieve status of saving from stateinfo
        # WARNING We have to be really carefull about this:
        # As of 2020/11/15 stateinfo can't be call twice in the same time.
        # But for the future better to leave comment and WARNING
        self.saving_status = self.stateinfo.saving
        loaded_stateopts = False
        if self.stateinfo.newfile or self.dryrun:
            # Don't need to load from StateInfo as it just create file 
            # or we don't want to write anything:
            # add default_stateopts from here
            loaded_stateopts = default_stateopts
        else:
            # Ok load from StateInfo in one time
            # We don't need to convert from str() to another type
            # it's done auto by class StateInfo
            loaded_stateopts = self.stateinfo.load()
        
        # locks for shared method/attr accross daemon threads
        self.locks = {
            'check_sync'        :   Lock(),
            'proceed'           :   Lock(),
            'cancel'            :   Lock(),
            'cancelled'         :   Lock(),
            'pretend_status'    :   Lock(),
            'sync_remain'       :   Lock(),
            'sync_elapsed'      :   Lock()
            }
        
        # Sync attributes TODO clean up ?
        self.sync = {
            'status'        :   'ready',    # values: ready | running
            'state'         :   loaded_stateopts.get('sync state'),
            'network_error' :   loaded_stateopts.get('sync network_error'),
            'retry'         :   loaded_stateopts.get('sync retry'),
            'global_count'  :   loaded_stateopts.get('sync count'),
            'timestamp'     :   loaded_stateopts.get('sync timestamp'),
            'interval'      :   kwargs['interval'],
            'elapsed'       :   0,
            'remain'        :   0,
            'session_count' :   0,   # Counting sync count since running (current session)
            'repos'         :   get_repo_info()  # Repo's dict to sync with key: 'names', 'formatted' 
                                                          # 'count' and 'msg'. 'names' is a list
            }
        
        # Print warning if interval 'too big'
        # If interval > 30 days (2592000 seconds)
        if self.sync['interval'] > 2592000:
            logger.warning('{0} sync interval looks too big (\'{1}\').'.format(self.sync['repos']['msg'].capitalize(),
                             self.format_timestamp.convert(self.sync['interval'], granularity=5)))
        
        # Last global update informations
        # For more details see module logparser
        self.world = {
            'state'     :   loaded_stateopts.get('world last state'), 
            'start'     :   loaded_stateopts.get('world last start'),
            'stop'      :   loaded_stateopts.get('world last stop'),
            'total'     :   loaded_stateopts.get('world last total'),
            'failed'    :   loaded_stateopts.get('world last failed')
            }
        # Manage pretend available packages updates 
        self.pretend = {
            'proceed'   :   False,      # True when pretend_world() should be run
            'status'    :   'ready',    # values: ready | running | completed
            'packages'  :   loaded_stateopts.get('world packages'), # Packages to update
            'interval'  :   600,        # Interval between two pretend_world() run TODO this could be tweaked !
            'remain'    :   600,        # TEST this the time between two pretend_world() lauch (avoid spamming)
            'forced'    :   False,      # (dbus) and for async call implantation.
            'cancel'    :   False,      # cancelling pretend_world pexpect when it detect world update in progress
            'cancelled' :   False       # same here so we know it has been cancelled if True
            }
        # Portage attributes
        self.portage = {
            'current'   :   loaded_stateopts.get('portage current'),
            'latest'    :   loaded_stateopts.get('portage latest'),
            'available' :   loaded_stateopts.get('portage available')
            }
       
    def check_sync(self, init=False, recompute=False):
        """ 
        Checking sync repo timestamp, recompute time remaining
         and, or elapsed if requested, allow or deny sync.
        :init:
            This is for print informations on init program. 
            Default False.
        :recompute:
            Requested to recalculate time remaining/elapsed. 
            Default False.
        :return:
            True if allow to sync, else False.        
        """
        
        logger = logging.getLogger(f'{self.logger_name}check_sync::')
        
        # Get the last emerge sync timestamp
        myparser = LastSync()
        sync_timestamp = myparser.get()
        
        if not sync_timestamp:
            # Don't need to logging anything it's 
            # already done in module logparser.
            return False
        
        current_timestamp = time.time()
        tosave = [ ]
        
        msg_repo = f"{self.sync['repos']['msg'].capitalize()}"
        
        if not sync_timestamp == self.sync['timestamp']:
            msg = (f"{msg_repo} have been sync outside the program")
            # For first run / resetted statefile
            if not self.sync['timestamp']:
                msg = ("Setting sync timestamp from factory (0) to:"
                       f" {sync_timestamp}")
                       
            logger.debug(f"{msg}, forcing pretend world...")
            # Any way, run pretend world
            with self.locks['proceed']:
                self.pretend['proceed'] = True
            self.sync['timestamp'] = sync_timestamp
            tosave.append(['sync timestamp', self.sync['timestamp']])
            recompute = True
        
        # Compute / recompute time remain
        # This shouldn't be done every time method check_sync()
        # is call because it will erase the arbitrary time remain
        # set by method dosync() when sync failed (network error)
        if recompute:
            logger.debug('Recompute is enable.')
            
            current = self.sync['elapsed']
            with self.locks['sync_remain']:
                self.sync['elapsed'] = round(current_timestamp - sync_timestamp)
            logger.debug(f"Sync elapsed timestamp: Current: {current}"
                         f", recalculate: {self.sync['elapsed']}")
            
            current = self.sync['remain']
            with self.locks['sync_remain']:
                self.sync['remain'] = self.sync['interval'] - self.sync['elapsed']
            logger.debug(f"Sync remain timestamp: Current: {current}"
                         f", recalculate: {self.sync['remain']}")
        
        if init:
            logger.info(f"Found {self.sync['repos']['count']}"
                        f" {self.sync['repos']['msg']} to sync:" 
                        f" {self.sync['repos']['formatted']}")        
        
        # For logging in debug / info
        for key in 'elapsed', 'remain', 'interval':
            # For logging in: INFO
            if init:
                # TEST keep default granularity for info
                timestamp = self.format_timestamp.convert(self.sync[key])
                logger.info(f"{msg_repo} sync {key} time: {timestamp}")
            # For logging in: DEBUG
            if recompute and key in ('elapsed', 'remain'):
                continue
            # For debug, full ouput (granularity=5)
            timestamp = self.format_timestamp.convert(self.sync[key],
                                                      granularity=5)
            logger.debug(f"{msg_repo} sync {key} time: {timestamp}")
    
        if tosave:
            self.stateinfo.save(*tosave)
            
        if self.sync['remain'] <= 0:
            return True # We can sync :)
        return False
    
    def dosync(self):
        """ Updating repo(s) """
        # Change name of the logger
        logger = logging.getLogger(f'{self.logger_name}dosync::')
        
        tosave = [ ]
        
        # This is for asyncio: don't run twice
        self.sync['status'] = 'running'
        
        # Refresh repositories infos
        self.sync['repos'] = get_repo_info()
        
        # This debug we display all the repositories
        logger.debug('Will sync {0} {1}: {2}.'.format(self.sync['repos']['count'], self.sync['repos']['msg'],
                                                                  ', '.join(self.sync['repos']['names'])))
        logger.info('Start syncing {0} {1}: {2}'.format(self.sync['repos']['count'], self.sync['repos']['msg'],
                                                                  self.sync['repos']['formatted']))
        
        if not self.dryrun:
            # Init logging
            logger.debug('Initializing logging handler:')
            logger.debug('Name: synclog')
            processlog = ProcessLoggingHandler(name='synclog')
            logger.debug('Writing to: {0}'.format(self.pathdir['synclog']))
            mylogfile = processlog.dolog(self.pathdir['synclog'])
            logger.debug('Log level: info')
            mylogfile.setLevel(processlog.logging.INFO)
        else:
            mylogfile = logging.getLogger(f'{self.logger_name}write_sync_log::')
        
        # Network failure related
        # main gentoo repo
        manifest_failure = re.compile(r'^!!!.Manifest.verification.impossible.due.to.keyring.problem:$')
        found_manifest_failure = False
        gpg_network_unreachable = re.compile(r'^gpg:.keyserver.refresh.failed:.Network.is.unreachable$')
        repo_gentoo_network_unreachable = False
        # Get return code for each repo
        failed_sync = re.compile(r'^Action:.sync.for.repo:\s(.*),.returned.code.=.1$')
        success_sync = re.compile(r'^Action:.sync.for.repo:\s(.*),.returned.code.=.0$')
        self.sync['repos']['failed'] = [ ]
        self.sync['repos']['success'] = [ ]
        # Set default values
        self.network_error = self.sync['network_error']
        self.retry = self.sync['retry']
        self.state = self.sync['state']
        
        # Running sync command using sudo (as root)
        myargs = ['/usr/bin/sudo', '/usr/bin/emerge', '--sync']
        myprocess = subprocess.Popen(myargs, preexec_fn=on_parent_exit(), 
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        mylogfile.info('##########################################\n')
        
        # TEST exit on demand
        # TODO move this to pexpect ??
        while not self.exit_now['sync']:
            for line in iter(myprocess.stdout.readline, ""):
                rstrip_line = line.rstrip()
                # write log             
                mylogfile.info(rstrip_line)
                # detected network failure for main gentoo repo 
                if found_manifest_failure:
                    # So make sure it's network related 
                    if gpg_network_unreachable.match(rstrip_line):
                        repo_gentoo_network_unreachable = True
                if manifest_failure.match(rstrip_line):
                    found_manifest_failure = True
                # get return code for each repo
                if failed_sync.match(rstrip_line):
                    self.sync['repos']['failed'].append(failed_sync.match(rstrip_line).group(1))
                if success_sync.match(rstrip_line):
                    self.sync['repos']['success'].append(success_sync.match(rstrip_line).group(1))
            # Ok so we have finished to read all line
            break
        # Close first
        myprocess.stdout.close()
        # Exit on demand
        if self.exit_now['sync']:
            logger.debug('Received exit order.')
            logger.debug('Shutting down subprocess.Popen running'
                         + ' command: \'{0}\''.format(' '.join(myargs[0:2]))
                         + ' and args: \'{0}\'.'.format(myargs[2]))
            logger.debug('Sending SIGTERM with timeout=3...')
            # First try to send SIGTERM...
            myprocess.terminate()
            # ... and wait 3s
            try:
                myprocess.wait(timeout=3)
            except TimeoutExpired:
                logger.debug('Got timeout while waiting for subprocess.Popen to terminate.')
                # Send SIGKILL
                logger.debug('Sending SIGKILL...')
                myprocess.kill()
                # wait forever... TEST
                myprocess.wait()
            finally:
                logger.debug('...exiting now, bye.')
                self.exit_now['sync'] = 'Done'
                return
        # Get return code
        return_code = myprocess.poll()
        
        if self.sync['repos']['success']:
            logger.debug('Repo sync completed: {0}'.format(', '.join(self.sync['repos']['success'])))
        if self.sync['repos']['failed']:
            logger.debug('Repo sync failed: {0}'.format(', '.join(self.sync['repos']['failed'])))
        
        if return_code:
            list_len = len(self.sync['repos']['failed'])
            msg = 'This repository'
            additionnal_msg = ''
            if list_len - 1 > 1:
                msg = 'These repositories'
            # Check out if we have an network failure for repo gentoo
            if repo_gentoo_network_unreachable:
                self.network_error = 1
                self.state = 'Failed'
                # sync will make ALOT of time to fail.
                # See : /etc/portage/repos.conf/gentoo.conf 
                # @2020-23-01 (~30min): 
                # sync-openpgp-key-refresh-retry-count = 40
                # sync-openpgp-key-refresh-retry-overall-timeout = 1200
                # first 5 times @ 600s (10min) - real is : 40min
                # after 5 times @ 3600s (1h) - real is : 1h30
                # then reset to interval (so mini is 24H)
                msg_on_retry = ''
                with self.locks['sync_remain']:
                    self.sync['remain'] = 600
                if self.retry == 1:
                    msg_on_retry = ' (1 time already)'
                elif 2 <= self.retry <= 5:
                    msg_on_retry = ' ({0} times already)'.format(self.retry)
                elif 6 <= self.retry <= 10:
                    msg_on_retry = ' ({0} times already)'.format(self.retry)
                    with self.locks['sync_remain']:
                        self.sync['remain'] = 3600
                elif self.retry > 10:
                    msg_on_retry = ' ({0} times already)'.format(self.retry)
                    with self.locks['sync_remain']:
                        self.sync['remain'] = self.sync['interval']
                
                if not self.sync['repos']['success']:
                    # All the repos failed
                    logger.error('{0} sync failed: network is unreachable.'.format(
                                                    self.sync['repos']['msg'].capitalize()))
                else:
                    logger.error('Main gentoo repository failed to sync: network is unreachable.')
                    additionnal_msg = ' also'
                    if list_len - 1 > 0:
                        logger.error('{0} {1} failed to sync: {2}.'.format(msg, additionnal_msg, 
                            ', '.join([name for name in self.sync['repos']['failed'] if not name == 'gentoo'])))
                # Increment retry
                old_sync_retry = self.retry
                self.retry += 1
                logger.debug('Incrementing sync retry from {0} to {1}.'.format(old_sync_retry,
                                                                                 self.retry))
                # If granularity=5 then rounded=False
                logger.error('Anyway will retry{0} sync in {1}.'.format(msg_on_retry,
                                                                      self.format_timestamp.convert(
                                                                          self.sync['remain'], granularity=5)))
            else:
                # Ok so this is not an network problem for main gentoo repo
                # DONT disable sync just keep syncing every 'interval'
                if 'gentoo' in self.sync['repos']['failed']:
                    logger.error('Main gentoo repository failed to sync with an unexcepted error !!')
                    # There is also other failed repo
                    if list_len - 1 > 0:
                        logger.error('{0} also failed to sync: {1}.'.format(msg, ', '.join(name for repos_failed \
                                                      in self.sync['repos']['failed'] if not name == 'gentoo')))
                    # State is Failed only if main gentoo repo failed
                    self.state = 'Failed'
                    # reset values
                    self.network_error = 0
                    self.retry = 0
                # Other repo
                else:
                    logger.error(f'{msg} failed to sync:' 
                                 + ' {0}.'.format(', '.join(self.sync['repos']['failed'])))
                # At the end 
                logger.error('You can retrieve log from: {0}.'.format(self.pathdir['synclog']))
                logger.error('Anyway will retry sync in {0}.'.format(self.format_timestamp.convert(
                                                                            self.sync['interval'], granularity=5
                                                                                                  )))
                
                logger.debug('Resetting remain interval to {0}.'.format(self.sync['interval']))
                # Any way reset remain to interval
                with self.locks['sync_remain']:
                    self.sync['remain'] = self.sync['interval']
        else:
            # Ok good :p
            self.state = 'Success'
            
            # Reset values
            self.retry = 0
            self.network_error = 0
            logger.info('Successfully syncing {0}.'.format(self.sync['repos']['msg']))
            # Count only success sync
            old_count_global = self.sync['global_count']
            old_count = self.sync['session_count']
            self.sync['global_count'] += 1
            logger.debug('Incrementing global sync count from \'{0}\' to \'{1}\''.format(old_count_global,
                                                                                           self.sync['global_count']))
            self.sync['session_count'] += 1
            logger.debug('Incrementing current sync count from \'{0}\' to \'{1}\''.format(old_count,
                                                                                    self.sync['session_count']))
            # group save to save in one shot
            tosave.append(['sync count', self.sync['global_count']])
            
            # Get sync timestamp from emerge.log
            logger.debug('Initializing emerge log parser:')
            myparser = LastSync(log=self.pathdir['emergelog'])
            logger.debug('Parsing file: {0}'.format(self.pathdir['emergelog']))
            logger.debug('Searching last sync timestamp.')
            sync_timestamp = myparser.get()
            
            if sync_timestamp:
                if sync_timestamp == self.sync['timestamp']:
                    logger.warning(f'Bug in class \'{self.__class__.__name__}\', method: dosync(): sync timestamp are equal...')
                else:
                    logger.debug('Updating sync timestamp from \'{0}\' to \'{1}\'.'.format(self.sync['timestamp'], sync_timestamp))
                    self.sync['timestamp'] = sync_timestamp
                    tosave.append(['sync timestamp', self.sync['timestamp']])
            # At the end of successfully sync, run pretend_world()
            with self.locks['proceed']:
                self.pretend['proceed'] = True
            logger.debug('Resetting remain interval to {0}'.format(self.sync['interval']))
            # Reset remain to interval
            with self.locks['sync_remain']:
                self.sync['remain'] = self.sync['interval']
            logger.info('Next syncing in {0}.'.format(self.format_timestamp.convert(self.sync['interval'], granularity=5)))
                    
        # Write / mod value only if change
        for value in 'state', 'retry', 'network_error':
            if not self.sync[value] == getattr(self, value):
                self.sync[value] = getattr(self, value)
                tosave.append([f'sync {value}', self.sync[value]])
        if not self.sync['status'] == 'running':
            logger.error('We are about to leave syncing process, but just found status already to False,'.format(
                                                                                        self.sync['repos']['msg']))
            logger.error('which mean syncing is/was NOT in progress, please check and report if True')
        # Then save every thing in one shot
        if tosave:
            self.stateinfo.save(*tosave)
        # At the end
        with self.locks['sync_remain']:
            self.sync['elapsed'] = 0
        self.sync['status'] = 'ready'
        return                 
           
    def get_last_world_update(self, detected=False):
        """
        Getting last world update timestamp
        """
        
        # Change name of the logger
        logger = logging.getLogger(f'{self.logger_name}get_last_world_update::')
        
        logger.debug(f"Running with detected={detected}")
        # keep default setting 
        # TODO : give the choice cf logparser module
        # TEST detected an failed and rejected world update.
        myparser = LastWorldUpdate(advanced_debug=self.vdebug['logparser'],
                                   log=self.pathdir['emergelog'],
                                   timestamp=detected)
        get_world_info, rejected = myparser.get()
        updated = False
        tosave = [ ]
        if get_world_info:
            to_print = True
            # Write only if change
            for key in 'start', 'stop', 'state', 'total', 'failed':
                if not self.world[key] == get_world_info[key]:
                    # Ok this mean world update has been run
                    # So run pretend_world()
                    with self.locks['proceed']:
                        self.pretend['proceed'] = True
                    updated = True
                    if to_print:
                        logger.info('Global update have been run.') # TODO: give more details
                        to_print = False
                            
                    self.world[key] = get_world_info[key]
                    tosave.append([f'world last {key}', self.world[key]])
            if not updated:
                logger.debug("Global update haven't been run," 
                             " keeping last know informations.")
                # TEST so if detected then global update 
                # have been aborded TEST WARNING this is not sure
                # at 100% because it could be incomplete and reject
                # because it didn't pass limit number 
                # set in module logparser
                if detected:
                    if rejected:
                        logger.info(f'Global update failed: {rejected}')
                    else:
                        logger.info('Global update have been aborded.')
        # Saving in one shot
        if tosave:
            self.stateinfo.save(*tosave)
        if updated:
            return True
        return False
       
    def pretend_world(self):
        """Check how many package to update"""
        # TODO more verbose for debug
        logger = logging.getLogger(f'{self.logger_name}pretend_world::')
        
        tosave = [ ]
        
        # Disable pretend authorization
        with self.locks['proceed']:
            self.pretend['proceed'] = False
        with self.locks['pretend_status']:
            self.pretend['status'] = 'running'
        
        logger.debug('Start searching available package(s) update.')
                
        update_packages = False
        retry = 0
        find_build_packages = re.compile(r'^Total:.(\d+).package.*$')        
        
        if not self.dryrun:
            # Init logger
            logger.debug('Initializing logging handler.')
            logger.debug('Name: pretendlog')
            processlog = ProcessLoggingHandler(name='pretendlog')
            logger.debug('Writing to: {0}'.format(self.pathdir['pretendlog']))
            mylogfile = processlog.dolog(self.pathdir['pretendlog'])
            logger.debug('Log level: info')
            mylogfile.setLevel(processlog.logging.INFO)
        else:
            mylogfile = logging.getLogger(f'{self.logger_name}write_pretend_world_log::')
            
        mycommand = '/usr/bin/emerge'
        myargs = [ '--verbose', '--pretend', '--deep', 
                  '--newuse', '--update', '@world', '--with-bdeps=y' ]
        
        while retry < 2:
            logger.debug('Running {0} {1}'.format(mycommand, ' '.join(myargs)))
            
            child = pexpect.spawn(mycommand, args=myargs, encoding='utf-8', preexec_fn=on_parent_exit(),
                                    timeout=None)
            # We capture log
            mycapture = io.StringIO()
            child.logfile = mycapture
            # Wait non blocking 
            # timeout is 30s because 10s sometimes raise pexpect.TIMEOUT 
            # but this will not block every TEST push to 60s ... 30s got two TIMEOUT back-to-back
            pexpect_timeout = 60
            while not child.closed and child.isalive():
                if self.pretend['cancel']:
                    # So we want to cancel
                    # Just break 
                    # child still alive
                    break
                # TEST exit on demand
                if self.exit_now['pretend']:
                    logger.debug('Received exit order.')
                    break
                try:
                    child.read_nonblocking(size=1, timeout=pexpect_timeout)
                    # We don't care about recording what ever since we recording from child.logfile 
                    # We wait until reach EOF
                except pexpect.EOF:
                    # Don't close here
                    break
                except pexpect.TIMEOUT:
                    # This shouldn't arrived
                    # TODO This should be retried ?
                    logger.error('Got unexcept timeout while running:' 
                                 + f' command: \'{mycommand}\''
                                 + ' and args: \'{0}\''.format(' '.join(myargs))
                                 + f' (timeout: {pexpect_timeout}) (please report this).')
                    break
                
                
            if self.exit_now['pretend']:
                logger.debug('Shutting down pexpect process running'
                             + f' command: \'{mycommand}\''
                             + ' and args: \'{0}\'.'.format(' '.join(myargs)))
                mycapture.close()
                child.terminate(force=True)
                child.close(force=True)
                logger.debug('...exiting now, ...bye.')
                self.exit_now['pretend'] = 'Done'
                return
            
            # Keep TEST-ing 
            if self.pretend['cancel']:                
                logger.warning('Stop searching available package(s) update as global update have been detected.')
                mycapture.close()
                child.terminate(force=True)
                # Don't really know but to make sure :)
                child.close(force=True)
                # Don't write log because it's have been cancelled (log is only partial)
                if self.pretend['cancelled']:
                    logger.warning('The previously task was already cancelled, check and report if False.')
                with self.locks['cancelled']:
                    self.pretend['cancelled'] = True
                with self.locks['cancel']:
                    self.pretend['cancel'] = False
                with self.locks['pretend_status']:
                    self.pretend['status'] = 'ready'
                # skip every thing else
                return
            
            # Ok it's not cancelled
            # First get log and close
            mylog = mycapture.getvalue()
            mycapture.close()
            child.close()
            # get return code
            return_code = child.wait()
            # Get package number and write log in the same time
            mylogfile.info('##### START ####')
            mylogfile.info('Command: {0} {1}'.format(mycommand, ' '.join(myargs)))
            for line in mylog.splitlines():
                mylogfile.info(line)
                if find_build_packages.match(line):
                    update_packages = int(find_build_packages.match(line).group(1))
                    # don't retry we got packages
                    retry = 2
            
            mylogfile.info(f'Terminate process: exit with status {return_code}')
            mylogfile.info('##### END ####')
            
            # We can have return_code > 0 and matching packages to update.
            # This can arrived when there is, for exemple, packages conflict (solved by skipping).
            # if this is the case, continue anyway.
            msg_on_return_code = 'Found'
            if return_code:
                msg_on_return_code = 'Anyway found'
                logger.error('Got error while searching for available package(s) update.')
                logger.error('Command: {0} {1}, return code: {2}'.format(mycommand,
                                                                           ' '.join(myargs), return_code))
                logger.error('You can retrieve log from: {0}.'.format(self.pathdir['pretendlog'])) 
                if retry < 1:
                    logger.error('Retrying without opts \'--with-bdeps\'...')
        
            # Ok so do we got update package ?
            if retry == 2:
                if update_packages > 1:
                    msg = f'{msg_on_return_code} {update_packages} packages to update.'
                elif update_packages == 1:
                    msg = f'{msg_on_return_code} only one package to update.'
                # no package found
                else:
                    if 'Anyway' in msg_on_return_code: 
                        msg = f'Anyway system is up to date.'
                    else:
                        msg = f'System is up to date.'
                logger.debug(f'Successfully search for packages update ({update_packages})')
                logger.info(msg)
            else:
                # Remove --with-bdeps and retry one more time.
                retry += 1
                if retry < 2:
                    myargs.pop()
                    logger.debug('Couldn\'t found how many package to update, retrying without opt \'--with bdeps\'.')

        # Make sure we have some update_packages
        if update_packages:
            if not self.pretend['packages'] == update_packages:
                self.pretend['packages'] = update_packages
                tosave.append(['world packages', self.pretend['packages']])
        else:
            if not self.pretend['packages'] == 0:
                self.pretend['packages'] = 0
                tosave.append(['world packages', self.pretend['packages']])
                
        # At the end
        if self.pretend['cancelled']:
            logger.debug('The previously task have been cancelled,' 
                             + ' resetting state to False (as this one is completed).')
        with self.locks['cancelled']:
            self.pretend['cancelled'] = False
        # Save
        if tosave:
            self.stateinfo.save(*tosave)
        with self.locks['pretend_status']:
            self.pretend['status'] = 'completed'

    def available_portage_update(self, detected=False, init=False):
        """
        Check if an update to portage is available.
        """
        
        # TODO: be more verbose for debug !
        logger = logging.getLogger(f'{self.logger_name}available_portage_update::')
        
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
        # pkg1 (list (example: ['test', '1.0', 'r1'])) - package to compare with
        # pkg2 (list (example: ['test', '1.0', 'r1'])) - package to compare againts
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
            #   @param pkg1: version to compare with (see ver_regexp in portage.versions.py)
            #   @type pkg1: string (example: "2.1.2-r3")
            #   @param pkg2: version to compare againts (see ver_regexp in portage.versions.py)
            #   @type pkg2: string (example: "2.1.2_rc5")
            #   @rtype: None or float
            #   @return:
            #   1. positive if ver1 is greater than ver2
            #   2. negative if ver1 is less than ver2
            #   3. 0 if ver1 equals ver2
            #   4. None if ver1 or ver2 are invalid (see ver_regexp in portage.versions.py)
            compare = vercmp(self.portage['current'], self.current)
            msg = False
            add_msg = ''
            if compare < 0:
                # If not available and it have been updated
                # than it have been updated to latest one
                if not self.available:
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
                    add_msg = 'latest '
                msg = (f"The portage package has been downgraded (from "
                       f"{add_msg}{self.portage['current']} to "
                       f"{self.current}).")
            elif compare == 0:
                # This have been aborded
                msg = ("The portage package process has been aborded.")
            
            # Just skipp if msg = False
            # so that mean compare == None
            if msg:
                logger.info(msg)
        
        tosave = [ ]
        # Update only if change
        for key in 'current', 'latest', 'available':
            if not self.portage[key] == getattr(self, key):
                # This print if there a new version of portage available
                # even if there is already an older version available
                # TEST: if checking only for key latest than it could
                # be == to current so check also result.
                if key == 'latest' and result:
                    logger.info("Found an update to portage (from "
                                f"{self.current} to {self.latest}).")
                
                self.portage[key] = getattr(self, key)
                tosave.append([f'portage {key}', self.portage[key]])
        
        if tosave:
            self.stateinfo.save(*tosave)    
            
    

def get_repo_info():
    """
    Get portage repos informations and return formatted
    """
    logger = logging.getLogger(f'::{__name__}::get_repo_info::')
    names = portdbapi().getRepositories()
    if names:
        names = sorted(names)
        repo_count = len(names)
        repo_msg = 'repositories'
        # get only first 6 elements if names > 6
        if repo_count > 6:
            repo_name = ', '.join(names[:6]) + ' (+' + str(repo_count - 6) + ')'
        elif repo_count == 1:
            repo_msg = 'repository'
            repo_name = ''.join(names)
        else:
            repo_name = ', '.join(names)
        logger.debug('Found {0} {1} to sync: {2}'.format(repo_count, repo_msg, ', '.join(names)))
        # return dict
        return { 'names' :   names, 'formatted' : repo_name, 'count' : repo_count, 'msg' : repo_msg }
    # This is debug message as it's not fatal for the program
    logger.debug('Could\'nt found sync repositories name(s) and count...')
    # We don't know so just return generic
    return { 'names' : [ ], 'formatted' : 'unknow', 'count' : '(?)', 'msg' : 'repo' }
