# -*- coding: utf-8 -*-
# -*- python -*- 
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
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
from portage.versions import pkgcmp, pkgsplit
from portage.dbapi.porttree import portdbapi
from portage.dbapi.vartree import vardbapi

from syuppo.utils import FormatTimestamp
from syuppo.utils import StateInfo
from syuppo.utils import on_parent_exit
from syuppo.logger import ProcessLoggingHandler

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
        # For more details see -> class EmergeLogParser -> last_world_update()
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
            'available' :   loaded_stateopts.get('portage available'),
            'remain'    :   30,     # check every 30s when 'available' is True
            'logflow'   :   True    # Control log info flow to avoid spamming syslog
            }
       
    def check_sync(self, init_run=False, recompute=False):
        """ Checking if we can sync repo depending on time interval.
        Minimum is 24H. """
        
        # Change name of the logger
        logger = logging.getLogger(f'{self.logger_name}check_sync::')
        # Get the last emerge sync timestamp
        myparser = EmergeLogParser(self.pathdir['emergelog'])
        sync_timestamp = myparser.last_sync()
        current_timestamp = time.time()
        tosave = [ ]
        
        if sync_timestamp:
            # first run ever 
            if self.sync['timestamp'] == 0:
                logger.debug('Found sync {0} timestamp set to factory: 0.'.format(self.sync['repos']['msg']))
                logger.debug(f'Setting to: {sync_timestamp}.')
                self.sync['timestamp'] = sync_timestamp
                tosave.append(['sync timestamp', self.sync['timestamp']])
                recompute = True
            # Detected out of program sync
            elif not self.sync['timestamp'] == sync_timestamp:
                logger.debug('{0} have been sync outside the program, forcing pretend world...'.format(
                                                                                self.sync['repos']['msg'].capitalize()))
                with self.locks['proceed']:
                    self.pretend['proceed'] = True # So run pretend world update
                self.sync['timestamp'] = sync_timestamp
                tosave.append(['sync timestamp', self.sync['timestamp']])
                recompute = True
            
            # Compute / recompute time remain
            # This shouldn't be done every time method check_sync() is call
            # because it will erase the arbitrary time remain set by method dosync()
            if recompute:
                logger.debug('Recompute is enable.')
                logger.debug('Current sync elapsed timestamp:' 
                                  + ' {0}'.format(self.sync['elapsed']))
                with self.locks['sync_remain']:
                    self.sync['elapsed'] = round(current_timestamp - sync_timestamp)
                logger.debug('Recalculate sync elapsed timestamp:' 
                                  + ' {0}'.format(self.sync['elapsed']))
                logger.debug('Current sync remain timestamp:' 
                                  + ' {0}.'.format(self.sync['remain']))
                with self.locks['sync_remain']:
                    self.sync['remain'] = self.sync['interval'] - self.sync['elapsed']
                logger.debug('Recalculate sync remain timestamp:' 
                                  + ' {0}'.format(self.sync['remain']))
            # For debug better to output with granularity=5
            logger.debug('{0} sync elapsed time:'.format(self.sync['repos']['msg'].capitalize()) 
                              + ' {0}.'.format(self.format_timestamp.convert(self.sync['elapsed']), granularity=5))
            logger.debug('{0} sync remain time:'.format(self.sync['repos']['msg'].capitalize())
                              + ' {0}.'.format(self.format_timestamp.convert(self.sync['remain'], granularity=5)))
            logger.debug('{0} sync interval:'.format(self.sync['repos']['msg'].capitalize())
                              + ' {0}.'.format(self.format_timestamp.convert(self.sync['interval'], granularity=5)))
            
            if init_run:
                logger.info('Found {0}'.format(self.sync['repos']['count']) 
                             + ' {0} to sync:'.format(self.sync['repos']['msg']) 
                             + ' {0}.'.format(self.sync['repos']['formatted']))
                logger.info('{0} sync elapsed time:'.format(self.sync['repos']['msg'].capitalize()) 
                             + ' {0}.'.format(self.format_timestamp.convert(self.sync['elapsed'])))
                logger.info('{0} sync remain time:'.format(self.sync['repos']['msg'].capitalize())
                             + ' {0}.'.format(self.format_timestamp.convert(self.sync['remain'])))
                logger.info('{0} sync interval:'.format(self.sync['repos']['msg'].capitalize())
                             + ' {0}.'.format(self.format_timestamp.convert(self.sync['interval'])))
            
            if tosave:
                self.stateinfo.save(*tosave)
                
            if self.sync['remain'] <= 0:
                return True # We can sync :)
            return False
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
            myparser = EmergeLogParser(self.pathdir['emergelog'])
            logger.debug('Parsing file: {0}'.format(self.pathdir['emergelog']))
            logger.debug('Searching last sync timestamp.')
            sync_timestamp = myparser.last_sync()
            
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
        self.sync['status'] = 'waiting'
        return                 
           
    def get_last_world_update(self, detected=False):
        """
        Getting last world update timestamp
        """
        
        # Change name of the logger
        logger = logging.getLogger(f'{self.logger_name}get_last_world_update::')
        logger.debug('Searching for last global update informations.')
        
        myparser = EmergeLogParser(self.pathdir['emergelog'])
        # keep default setting 
        # TODO : give the choice cf EmergeLogParser() --> last_world_update()
        ### WARNING to remove lastlines=1000 WARNING
        get_world_info = myparser.last_world_update(lastlines=1000,
                                    advanced_debug=self.vdebug['logparser'])
        
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
                # at 100% because it could be incompleted and reject
                # because it didn't pass limit number (nincompleted) 
                # set in EmergeLogParser.last_world_update()
                if detected:
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
                if retry < 2:
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


    def available_portage_update(self):
        """Check if an update to portage is available"""
        # TODO: be more verbose for debug !
        logger = logging.getLogger(f'{self.logger_name}available_portage_update::')
        # Reset remain here as we return depending of the situation
        self.portage['remain'] = 30
        
        self.available = False
        self.latest = False
        self.current = False
        latest_version = False
        current_version = False
        # This mean first run ever / or reset statefile 
        if self.portage['current'] == '0.0' and self.portage['latest'] == '0.0':
            # Return list any way, see --> https://dev.gentoo.org/~zmedico/portage/doc/api/portage.dbapi-pysrc.html 
            # Function 'match' ->  Returns: 
            #                           a list of packages that match origdep 
            portage_list = vardbapi().match('portage')
            self.latest = portdbapi().xmatch('bestmatch-visible', 'portage')
        else:
            self.latest = portdbapi().xmatch('bestmatch-visible', 'portage')
            if not self.latest:
                logger.error('Got not result when querying portage db for latest available portage package !')
                return False
            # It's up to date 
            if self.latest == self.portage['current']:
                mysplit = pkgsplit(self.latest)
                if not mysplit[2] == 'r0':
                    current_version = '-'.join(mysplit[-2:])
                else:
                    current_version = mysplit[1]
                logger.debug('No update to portage package is available' 
                                 + f' (current version: {current_version})')
                # Reset 'available' to False if not
                # Don't mess with False vs 'False' / bool vs str
                # TEST var is bool even loaded from statefile
                if self.portage['available']:
                    self.portage['available'] = False
                    self.stateinfo.save(['portage available', self.portage['available']])
                # Just make sure that self.portage['latest'] is also the same
                if self.latest == self.portage['latest']:
                    # Don't need to update any thing 
                    return True
                else:
                    self.stateinfo.save(['portage latest', self.portage['latest']])
                    return True
            # Get the list
            else:
                portage_list = vardbapi().match('portage')
        
        # Make sure current is not None
        if not portage_list:
            logger.error('Got no result when querying portage db for installed portage package...')
            return False
        if len(portage_list) > 1:
            logger.error('Got more than one result when querying portage db for installed portage package...')
            logger.error('The list contain: {0}'.format(' '.join(portage_list)))
            logger.error('This souldn\'t happend, anyway picking the first in the list.')
        
        # From https://dev.gentoo.org/~zmedico/portage/doc/api/portage.versions-pysrc.html
        # Parameters:
        # pkg1 (list (example: ['test', '1.0', 'r1'])) - package to compare with
        # pkg2 (list (example: ['test', '1.0', 'r1'])) - package to compare againts
        # Returns: None or integer
        # None if package names are not the same
        # 1 if pkg1 is greater than pkg2
        # -1 if pkg1 is less than pkg2
        # 0 if pkg1 equals pkg2
        self.current = portage_list[0]
        self.result = pkgcmp(pkgsplit(self.latest),pkgsplit(self.current))
        
        if self.result == None or self.result == -1:
            if not self.result:
                logger.error('Got no result when comparing latest' 
                                + ' available with installed portage package version.')
            else:
                logger.error('Got unexcept result when comparing latest' 
                                + ' available with installed portage package version.')
                logger.error('Result indicate that the latest available' 
                                + ' portage package version is lower than the installed one...')
            
            logger.error(f'Installed portage: \'{self.current}\', latest: \'{self.latest}\'.')
            if len(portage_list) > 1:
                logger.error('As we got more than one result when querying' 
                                + ' portage db for installed portage package.')
                logger.error('This could explain strange result.')
            self.portage['logflow'] = False
            return False
        else:
            # Split current version first
            mysplit = pkgsplit(self.current)
            if not mysplit[2] == 'r0':
                current_version = '-'.join(mysplit[-2:])
            else:
                current_version = mysplit[1]
            if self.result == 1:
                # Split latest version
                mysplit = pkgsplit(self.latest)
                if not mysplit[2] == 'r0':
                    latest_version = '-'.join(mysplit[-2:])
                else:
                    latest_version = mysplit[1]
                # Print one time only (when program start / when update found)
                # So this mean each time the program start and if update is available 
                # it will print only one time.
                if self.portage['logflow']:
                    logger.info(f'Found an update to portage (from {current_version} to {latest_version}).')
                    self.portage['logflow'] = False
                else:
                    logger.debug(f'Found an update to portage (from {current_version} to {latest_version}).')
                self.available = True
                # Don't return yet because we have to update portage['current'] and ['latest'] 
            elif self.result == 0:
                logger.debug('No update to portage package is available' 
                                  + f' (current version: {current_version})')
                self.available = False
            
            tosave = [ ]
            # Update only if change
            for key in 'current', 'latest', 'available':
                if not self.portage[key] == getattr(self, key):
                    self.portage[key] = getattr(self, key)
                    tosave.append([f'portage {key}', self.portage[key]])
                    # This print if there a new version of portage available
                    # even if there is already an older version available
                    # TEST
                    if key == 'latest' and self.portage['logflow'] and latest_version:
                        logger.info('Found an update to portage' 
                                      + f' (from {current_version} to {latest_version}).')
            if tosave:
                self.stateinfo.save(*tosave)    
    
    

class EmergeLogParser:
    """
    Parse emerge.log file and extract informations.
    """
    def __init__(self, emergelog):
        self.logger_name =  f'::{__name__}::EmergeLogParser::' 
        # Get a logger
        logger = logging.getLogger(f'{self.logger_name}init::')
        self.aborded = 5
        self.emergelog = emergelog
        
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
                         + f" setting arbitrary to: {self.log_lines['count']}"
                         + "lines.")
        else:
            self.log_lines = {
                'count'     :   nlines, 
                'real'      :   True
                }
            logger.debug(f"Setting '{self.emergelog}' maximum lines count to:"
                         + f" {self.log_lines['count']} lines.")
        # Init numpy range lists
        self._range = { }
    
    
    def last_sync(self, lastlines=500, nrange=10):
        """
        Return last sync timestamp
        @returns: timestamp
        @error: return False
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
        
        logger = logging.getLogger(f'{self.logger_name}last_sync::')
        
        completed_re = re.compile(r'^(\d+):\s{1}===.Sync.completed.for.gentoo$')
        self.lastlines = lastlines
        # construct exponantial list
        self._range['sync'] = numpy.geomspace(self.lastlines, self.log_lines['count'], 
                                              num=nrange, endpoint=True, dtype=int)
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
                # __keep_collecting manage self.lastlines increment
                if self.__keep_collecting(count, ['last sync timestamp for main repo \'gentoo\'', 
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
     
    
    def last_world_update(self, lastlines=3000, incompleted=True, 
                          nincompleted=[30/100, 'percentage'], nrange=8,
                          advanced_debug=False):
        """
        Get last world update timestamp
        @param lastlines  read last n lines from emerge log file (as we don't have to read all the file to get last world update)
                          you can tweak it but any way if you lower it and if the function don't get anything in the first pass
                          it will increment it depending on function __keep_collecting()
        @type integer
        @param incompleted enable or disable the search for start but failed update world
        @type boolean
        @param nincompleted a list which filter start from how much packages the function capture or not failed update world.                        
        @type list where first element should integer or percentage in this form (n/100)
                   where second element require either 'number' (if first element is number) or 'percentage' (if first element is percentage)
        @returns: dictionary
        @keys:  'start'     -> start timestamp.
                'stop'      -> stop timestamp.
                'total'     -> total packages which has been update.
                'state'     -> 'completed' / 'partial' / 'incompleted'
                'failed'    -> if 'completed': 'none', if 'partial' / 'incompleted': package number which failed. 
        @error: return False
        
        Exemple from emerge.log:
            1569446718:  *** emerge --newuse --update --ask --deep --keep-going --quiet-build=y --verbose world
            1569447047:  >>> emerge (1 of 44) sys-kernel/linux-firmware-20190923 to /
            1569447213:  === (1 of 44) Cleaning (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            1569447214:  === (1 of 44) Compiling/Merging (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            1569447219:  === (1 of 44) Merging (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            1569447222:  >>> AUTOCLEAN: sys-kernel/linux-firmware:0
            1569447222:  === Unmerging... (sys-kernel/linux-firmware-20190904)
            1569447224:  >>> unmerge success: sys-kernel/linux-firmware-20190904
            1569447225:  === (1 of 44) Post-Build Cleaning (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            1569447225:  ::: completed emerge (1 of 44) sys-kernel/linux-firmware-20190923 to / 
        """
        
        # TODO clean-up it's start to be huge !
        # Logging setup
        logger = logging.getLogger(f'{self.logger_name}last_world_update::')
        if not hasattr(logging, 'DEBUG2'):
            raise AttributeError("logging.DEBUG2 NOT setup.")
        if advanced_debug:
            logger.setLevel(logging.DEBUG2)

        self.collect = {
            'completed'     :   [ ],
            'incompleted'   :   [ ],
            'partial'       :   [ ]
            }
        self.packages_count = 1
        self.lastlines = lastlines
        self.nincompleted = nincompleted
        self.group = { }
        # construct exponantial list
        self._range['world'] = numpy.geomspace(self.lastlines, self.log_lines['count'], num=nrange, endpoint=True, dtype=int)
        
        incompleted_msg = ''
        if incompleted:
            incompleted_msg = ', incompleted'

        compiling = False
        package_name = None
        keep_running =  True
        current_package = False
        count = 1
        keepgoing = False
        linecompiling = 0
        record = [ ]
        forced = False       
       
        #   Added @world
        #   Added \s* after (?:world|@world) to make sure we match only @world or world 
        #   Should we match with '.' or '\s' ??
        start_opt = re.compile(r'^(\d+):\s{2}\*\*\*.emerge.*\s(?:world|@world)\s*.*$')
        start_parallel = re.compile(r'^\d+:\s{1}Started.emerge.on:.*$')
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
        #       an auto restart, only true if current_package == True 
        keepgoing_opt = re.compile(r'^.*\s--keep-going\s.*$')
        #   So make sure we start to compile the world update and this should be the first package 
        start_compiling = re.compile(r'^\d+:\s{2}>>>.emerge.\(1.of.(\d+)\)\s(.*)\sto.*$')
        #   Make sure it failed with status == 1
        failed = re.compile(r'(\d+):\s{2}\*\*\*.exiting.unsuccessfully.with.status.\'1\'\.$')
        succeeded = re.compile(r'(\d+):\s{2}\*\*\*.exiting.successfully\.$')
        
        # TODO  Give a choice to enable or disable incompleted collect
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
        
        def _saved_incompleted():
            """
            Saving world update 'incompleted' state
            """
            if self.nincompleted[1] == 'percentage':
                if self.packages_count <= round(self.group['total'] * self.nincompleted[0]):
                    logger.debug('NOT recording incompleted, ' 
                                 + 'start: {0}, '.format(self.group['start']) 
                                 + 'stop: {0}, '.format(self.group['stop']) 
                                 + 'total packages: {0}, '.format(self.group['total'])
                                 + 'failed: {0}'.format(self.group['failed']))
                    msg = f'* {self.nincompleted[1]}'
                    if self.nincompleted[1] == 'number':
                        msg = f'- {self.nincompleted[1]}'
                    logger.debug(f'Rejecting because packages count ({self.packages_count})'
                                 + ' <= packages total ({0})'.format(self.group['total'])
                                 + f' {msg} limit ({self.nincompleted[0]})')
                    logger.debug('Rounded result is :' 
                                 + ' {0}'.format(round(self.group['total'] * self.nincompleted[0])))
                    self.packages_count = 1
                    return
            elif self.nincompleted[1] == 'number':
                if self.packages_count <= self.nincompleted[0]:
                    logger.debug('NOT recording incompleted, ' 
                                 + 'start: {0}, '.format(self.group['start']) 
                                 + 'stop: {0}, '.format(self.group['stop']) 
                                 + 'total packages: {0}, '.format(self.group['total'])
                                 + 'failed: {0}'.format(self.group['failed']))
                    logger.debug(f'Rejecting because packages count ({self.packages_count})'
                                 + f' <= number limit ({self.nincompleted[0]}).')
                    self.packages_count = 1
                    return
            # Record how many package compile successfully
            # if it passed self.nincompleted
            # TEST try to fix bug: during world update, emerge crash:
            # FileNotFoundError: [Errno 2] No such file or directory: 
            #   b'/var/db/repos/gentoo/net-misc/openssh/openssh-8.3_p1-r1.ebuild'
            # This have to be fix in main also: sync shouldn't be run if world update is in progress ??
            if self.group['stop'] <= self.group['start']:
                logger.debug('NOT recording incompleted, ' 
                              + 'start: {0}, '.format(self.group['start']) 
                              + 'stop: {0}, '.format(self.group['stop']) 
                              + 'total packages: {0}, '.format(self.group['total'])
                              + 'failed: {0}'.format(self.group['failed']))
                logger.debug('BUG, rejecting because stop timestamp =< start timestamp')
                return
            self.group['state'] = 'incompleted'
            self.collect['incompleted'].append(self.group)
            logger.debug('Recording incompleted, ' 
                            + 'start: {0}, '.format(self.group['start']) 
                            + 'stop: {0}, '.format(self.group['stop']) 
                            + 'total packages: {0}, '.format(self.group['total'])
                            + 'failed: {0}'.format(self.group['failed']))
            
        def _saved_partial():
            """
            Saving world update 'partial' state
            """ 
            # Ok so we have to validate the collect
            # This mean that total number of package should be 
            # equal to : total of saved count - total of failed packages
            # This is NOT true every time, so go a head and validate any way
            # TODO: keep testing :)
            # Try to detect skipped packages due to dependency
            # TEST here like upstair
            if self.group['stop'] <= self.group['start']:
                logger.debug('NOT recording partial, ' 
                              + 'start: {0}, '.format(self.group['start']) 
                              + 'stop: {0}, '.format(self.group['stop']) 
                              + 'total packages: {0}, '.format(self.group['total'])
                              + 'failed: {0}'.format(self.group['failed']))
                logger.debug('BUG, rejecting because stop timestamp =< start timestamp')
                return
            self.group['dropped'] = ''
            dropped =   self.group['saved']['total'] - \
                        self.group['saved']['count'] - \
                        self.packages_count
            if dropped > 0:
                self.group['dropped'] = f' (+{dropped} dropped)'
                                                                                    
            self.group['state'] = 'partial'
            self.group['total'] = self.group['saved']['total']
            # Easier to return str over list - because it's only for display
            self.group['failed'] = ' '.join(self.group['failed']) \
                                        + '{0}'.format(self.group['dropped'])
            self.collect['partial'].append(self.group)
            logger.debug('Recording partial, ' 
                            + 'start: {0}, '.format(self.group['start']) 
                            + 'stop: {0}, '.format(self.group['stop']) 
                            + 'total packages: {0}, '.format(self.group['total'])
                            + 'failed: {0}'.format(self.group['failed']))
            
        def _saved_completed():
            """
            Saving world update 'completed' state.
            """
            # The BUG have been fixed but keep this in case
            for key in 'start', 'stop', 'total':
                try:
                    self.group[key]
                except KeyError:
                    logger.error('While saving completed world update informations,')
                    logger.error(f'got KeyError for key {key}, skip saving but please report this.')
                    # Ok so return and don't save
                    return
            # Same here TEST
            if self.group['stop'] <= self.group['start']:
                logger.debug('NOT recording completed, ' 
                              + 'start: {0}, '.format(self.group['start']) 
                              + 'stop: {0}, '.format(self.group['stop']) 
                              + 'total packages: {0}, '.format(self.group['total'])
                              + 'failed: {0}'.format(self.group['failed']))
                logger.debug('BUG, rejecting because stop timestamp =< start timestamp')
                return
            self.group['state'] = 'completed'
            # For comptability if not 'failed' then 'failed' = 'none'
            self.group['failed'] = 'none'
            self.collect['completed'].append(self.group)
            self.packages_count = 1
            logger.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                           .format(self.group['start'], self.group['stop'], self.group['total']))
        
                    
        while keep_running:
            logger.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, self.emergelog))
            logger.debug(f'Extracting list of completed{incompleted_msg} and partial global update'
                           + ' group informations.')
            for line in self.getlog(self.lastlines):
                linecompiling += 1
                if compiling:
                    # If keepgoing is detected, last package could be in completed state
                    # so current_package is False but compiling end to a failed match.
                    if current_package or (keepgoing and \
                        # mean compile as finished (it's the last package)
                        self.packages_count == self.group['total'] and \
                        # make sure emerge was auto restarted
                        # other wise this end to a completed update
                        'total' in self.group['saved'] ):
                        # Save lines
                        if current_package:
                            # This will just record line from current package (~10lines max)
                            record.append(line)
                            logger.debug2(f"Recording line: '{line}'.")
                        if failed.match(line):
                            logger.debug2(f"Got failed match at line: {line}.")
                            # We don't care about record here so reset it
                            record = [ ]
                            if not 'failed' in self.group:
                                self.group['failed'] = f'at {self.packages_count} ({package_name})'
                            # set stop
                            self.group['stop'] = int(failed.match(line).group(1))
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                            # first test if it's been restarted (keepgoing) or it's just incompleted.
                            if keepgoing and 'total' in self.group['saved']:
                                logger.debug2("Calling _saved_partial().")
                                _saved_partial()
                            elif incompleted:
                                logger.debug2("Calling _saved_incompleted().")
                                _saved_incompleted()
                            else:
                                logger.debug('NOT recording partial/incompleted, ' 
                                            + 'start: {0}, '.format(self.group['start']) 
                                            + 'stop: {0}, '.format(self.group['stop']) 
                                            + 'total packages: {0}, '.format(self.group['total'])
                                            + 'failed: {0}'.format(self.group['failed']))
                                logger.debug(f'Additionnal informations: keepgoing ({keepgoing}), '
                                                f'incompleted ({incompleted}), '
                                                f'nincompleted ({self.nincompleted[0]} / {self.nincompleted[1]}).')
                            # At then end reset
                            self.packages_count = 1
                            current_package = False
                            compiling = False
                            package_name = None
                            keepgoing = False
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                        elif keepgoing and start_compiling.match(line):
                            logger.debug2("Keepgoing enable, got start"
                                        + " compiling line at" 
                                        + f" line: '{line}'.")
                            # Try to fix BUG describe upstair
                            unexpect_start = False
                            logger.debug2("Start analizing record lines.")
                            for saved_line in record:
                                logger.debug2(f"Record: {saved_line}.")
                                # This is also handled :
                                # 1581349345:  === (2 of 178) Compiling/Merging (kde-apps/pimcommon-19.12.2::/usr/portage/kde-apps/pimcommon/pimcommon-19.12.2.ebuild)
                                # 1581349360:  *** terminating.
                                # 1581349366: Started emerge on: févr. 10, 2020 16:42:46
                                # 1581349366:  *** emerge --newuse --update --ask --deep --keep-going --with-bdeps=y --quiet-build=y --verbose world
                                if start_opt.match(saved_line):
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
                                self.group['stop'] = int(re.match(r'^(\d+):\s+.*$', record[0]).group(1))
                                if not 'failed' in self.group:
                                    self.group['failed'] = f'at {self.packages_count} ({package_name})'
                                logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                            + f" {keepgoing}, linecompiling: "
                                            + f" {linecompiling}, package_name:"
                                            + f" {package_name}, packages_count:"
                                            + f" {self.packages_count}, compiling:"
                                            + f" {compiling}, current_package:"
                                            + f" {current_package}.")
                                # First try if it was an keepgoing restart
                                if keepgoing and 'total' in self.group['saved']:
                                    logger.debug('Forcing save of current world update group'
                                                + ' using partial (start: {0}).'.format(self.group['start']))
                                    _saved_partial()
                                # incompleted is enable ?
                                elif incompleted:
                                    logger.debug('Forcing save of current world update group'
                                                + ' using incompleted (start: {0}).'.format(self.group['start']))
                                    _saved_incompleted()
                                else:
                                    logger.debug('Skipping save of current world update group'
                                                   + ' (unmet conditions).')
                                # Ok now we have to restart everything
                                self.group = { }
                                # Get the timestamp
                                self.group['start'] = int(start_opt.match(unexpect_start).group(1))
                                #--keep-going setup
                                if keepgoing_opt.match(unexpect_start):
                                    logger.debug2("Got unexcept keepgoing match"
                                                + f" at line: {unexpect_start}.")
                                    keepgoing = True
                                self.group['total'] = int(start_compiling.match(line).group(1))
                                # Get the package name
                                package_name = start_compiling.match(line).group(2)
                                compiling = True
                                self.packages_count = 1
                                self.group['saved'] = {
                                    'count' :    0
                                }
                                # we are already 'compiling' the first package
                                current_package = True
                                logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
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
                            self.group['failed'].append(package_name)
                            # Set name of the package to current one
                            package_name = start_compiling.match(line).group(2)
                            # get the total number of package from this new emerge 
                            self.group['total'] = int(start_compiling.match(line).group(1))
                            self.packages_count = 1
                            current_package = True # As we restart to compile
                            compiling = True
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                        elif re.match(r'\d+:\s{2}:::.completed.emerge.\(' 
                                            + str(self.packages_count) 
                                            + r'.*of.*' 
                                            + str(self.group['total']) 
                                            + r'\).*$', line):
                            logger.debug2("Got completed match at line:"
                                        + f" '{line}'.")
                            current_package = False # Compile finished for the current package
                            record = [ ] # same here it's finished so reset record
                            compiling = True
                            package_name = None
                            if not self.packages_count >= self.group['total']:
                                self.packages_count += 1
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                    elif re.match(r'^\d+:\s{2}>>>.emerge.\('
                                            + str(self.packages_count) 
                                            + r'.*of.*' 
                                            + str(self.group['total']) 
                                            + r'\).*$', line):
                        logger.debug2("Got start compiling match at line:"
                                    + f" '{line}'.")
                        current_package = True
                        # reset record as it will restart
                        logger.debug2("Reset recorded lines.")
                        record = [ ]
                        logger.debug2("Restart recording lines at line:"
                                    + f" '{line}'.")
                        record.append(line) # Needed to set stop if unexpect_start is detected
                        # This is a lot of reapeat for python 3.8 we'll get this :
                        # https://www.python.org/dev/peps/pep-0572/#capturing-condition-values
                        # TODO : implant this ?
                        package_name = re.match(r'^\d+:\s{2}>>>.emerge.\('
                                                + str(self.packages_count) 
                                                + r'.*of.*' 
                                                + str(self.group['total']) 
                                                + r'\)\s(.*)\sto.*$', line).group(1)
                        compiling = True
                        logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                    elif succeeded.match(line):
                        logger.debug2(f"Got succeeded match at line: '{line}'.")
                        # Reset record here as well
                        logger.debug2("Reset recorded lines.")
                        record = [ ]
                        # set stop
                        self.group['stop'] = int(succeeded.match(line).group(1))
                        # Make sure it's succeeded the right compile
                        # In case we run parallel emerge
                        if self.packages_count == self.group['total']:
                            current_package = False
                            compiling = False
                            package_name = None
                            keepgoing = False
                            logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                            logger.debug2("Calling _saved_completed().")
                            _saved_completed()
                        else:
                            logger.debug('NOT recording completed,' 
                                         + ' start: {0},'.format(self.group['start'])
                                         + ' stop: {0},'.format(self.group['stop']) 
                                         + ' packages: {0}'.format(self.group['total']))
                            logger.debug(f'Rejecting because packages count ({self.packages_count})' 
                                         + ' != recorded total packages' 
                                         + ' ({0}).'.format(self.group['total']))
                elif start_opt.match(line):
                    logger.debug2(f"Got start opt match at line: '{line}'.")
                    self.group = { }
                    # Get the timestamp
                    self.group['start'] = int(start_opt.match(line).group(1))
                    # --keep-going setup
                    if keepgoing_opt.match(line):
                        logger.debug2("Keepgoing enable.")
                        keepgoing = True
                    linecompiling = 0
                    logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                 + f" {keepgoing}, linecompiling: "
                                 + f" {linecompiling}.")
                # So this is the nextline after start_opt match
                # But make sure we got start_opt match !
                elif linecompiling == 1 and 'start' in self.group:
                    # Make sure it's start to compile
                    if start_compiling.match(line):
                        logger.debug2("Got start compiling match at line:"
                                    + f" '{line}'.")
                        # Ok we start already to compile the first package
                        # Get how many package to update 
                        self.group['total'] = int(start_compiling.match(line).group(1))
                        # Get the package name
                        package_name = start_compiling.match(line).group(2)
                        compiling = True
                        self.packages_count = 1
                        self.group['saved'] = {
                            'count' :    0
                            }
                        # we are already 'compiling' the first package
                        current_package = True
                        logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                    else:
                        # This has been aborded OR it's not the right
                        # start opt match ....
                        logger.debug2("Look like it has been aborded at line:"
                                     + f" '{line}'.")
                        self.group = { }
                        compiling = False
                        self.packages_count = 1
                        current_package = False
                        package_name = None
                        keepgoing = False
                        logger.debug2(f"Stats: group: {self.group}, keepgoing:"
                                     + f" {keepgoing}, linecompiling: "
                                     + f" {linecompiling}, package_name:"
                                     + f" {package_name}, packages_count:"
                                     + f" {self.packages_count}, compiling:"
                                     + f" {compiling}, current_package:"
                                     + f" {current_package}.")
                        # don't touch linecompiling
                  
            # Do we got something ?
            if incompleted:
                if self.collect['completed'] or self.collect['incompleted'] or self.collect['partial']:
                    logger.debug2("Stop running, collect has been successfull.")
                    keep_running = False
                else:
                    # That mean we have nothing ;)
                    if self.__keep_collecting(count, ['last global update informations', 
                                'has never been update using \'world\' update schema...'], 'world'):
                        keep_running = True
                        count += 1
                    else:
                        logger.debug("FAILED to collect last world update informations.")
                        return False
            else:
                if self.collect['completed'] or self.collect['partial']:
                    logger.debug2("Stop running, collect has been successfull.")
                    keep_running = False
                else:
                    if self.__keep_collecting(count, ['last global update informations', 
                                 'has never been update using \'world\' update schema...'], 'world'):
                        keep_running = True
                        count += 1
                    else:
                        logger.debug("FAILED to collect last world update informations.")
                        return False
                   
        # So now compare and get the highest 'start' timestamp from each list
        logger.debug2("Extracting lastest world update from 'completed'"
                    + f"'{incompleted_msg}' and 'partial' collected lists.")
        tocompare = [ ]
        for target in 'completed', 'incompleted', 'partial':
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
            if latest_sublist['state'] == 'completed':
                logger.debug('Selecting completed,' 
                             + ' start: {0},'.format(latest_sublist['start']) 
                             + ' stop: {0},'.format(latest_sublist['stop'])
                             + ' total packages: {0}'.format(latest_sublist['total']))
            elif latest_sublist['state'] == 'incompleted':
                logger.debug('Selecting incompleted,' 
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
   
   
    def getlines(self):
        """
        Get total number of lines from log file
        """
        logger = logging.getLogger(f'{self.logger_name}getlines::')
        
        myargs = ['/bin/wc', '--lines', self.emergelog]
        mywc = subprocess.Popen(myargs, preexec_fn=on_parent_exit(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
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
        
        logger = logging.getLogger(f'{self.logger_name}getlog::')
                
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
            
             
    def __keep_collecting(self, curr_loop, msg, key):
        """
        Restart collecting if nothing has been found and
        managing lastlines increment to load.
        """
               
        logger = logging.getLogger(f'{self.logger_name}keep_collecting::')
        
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
