# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

import os
import sys 
import re
import pathlib
import time
import errno
import subprocess
import io

from portage.versions import pkgcmp, pkgsplit
from portage.dbapi.porttree import portdbapi
from portage.dbapi.vartree import vardbapi
from utils import FormatTimestamp
from utils import StateInfo
from utils import UpdateInProgress
from utils import on_parent_exit
from logger import MainLoggingHandler
from logger import ProcessLoggingHandler

try:
    import numpy
except Exception as exc:
    print(f'Got unexcept error while loading numpy module: {exc}')
    sys.exit(1)


class PortageHandler:
    """Portage tracking class"""
    
    def __init__(self, interval, pathdir, runlevel, loglevel):
        self.pathdir = pathdir
        # Init convert/format timestamp
        self.format_timestamp = FormatTimestamp()
        # Init logger
        self.logger_name = f'::{__name__}::PortageHandler::'
        portagemanagerlog = MainLoggingHandler(self.logger_name, self.pathdir['debuglog'], 
                                               self.pathdir['fdlog'])
        self.log = getattr(portagemanagerlog, runlevel)()
        self.log.setLevel(loglevel)
        # Init save/load info file
        self.stateinfo = StateInfo(self.pathdir, runlevel, self.log.level)
        # Init Class UpdateInProgress
        self.update_inprogress = UpdateInProgress(self.log)
        # Remain for check_sync()
        # This avoid at maximum parsing emerge.log twice at the same time
        self.remain = 31
        # Sync attributes
        self.sync = {
            'status'        :   False, # True when running / False when not
            'state'         :   self.stateinfo.load('sync state'), # 'Success' / 'Failed'
            'recompute_done':   False, # True when recompute already done / False when not
                                       # reset in method dosync()
            'network_error' :   int(self.stateinfo.load('sync network_error')),
            'retry'         :   int(self.stateinfo.load('sync retry')),
            'log'           :   'TODO', # TODO CF gitmanager.py -> __init__ -> self.pull['log']
            #'error'         :   self.stateinfo.load('sync error'),
            'count'         :   str(self.stateinfo.load('sync count')),   # str() or get 'TypeError: must be str, not 
                                                                          # int' or vice versa
            'timestamp'     :   int(self.stateinfo.load('sync timestamp')),
            'interval'      :   interval,
            'elapse'        :   0,
            'remain'        :   0,
            'current_count' :   0,   # Counting sync count since running (current session)
            'repos'         :   self._get_repositories()  # Repo's dict to sync with key 'names', 'formatted' 
                                                          # 'count' and 'msg'. 'names' is a list
            }
        # Print warning if interval 'too big'
        # If interval > 30 days (2592000 seconds)
        if self.sync['interval'] > 2592000:
            self.log.warning('{0} sync interval looks too big (\'{1}\').'.format(self.sync['repos']['msg'].capitalize(),
                             self.format_timestamp.convert(self.sync['interval'], granularity=6)))
        
        # World attributes
        self.world = {
            'status'    :   False,   # True when running / False when not
            'pretend'   :   False,   # True when pretend_world() should be run / False when shouldn't
            'update'    :   False,   # True when global update is in progress / False if not
            'updated'   :   False,   # True if system has been updated / False otherwise
            'packages'  :   int(self.stateinfo.load('world packages')), # Packages to update
            'remain'    :   5, # TEST Check every 5s  TODO: this could be tweaked (dbus client or args ?)
            'forced'    :   False, # to forced pretend for dbus client We could use 'status' key but 
                                    # this is for async call implantation.
            'cancel'    :   False,  # this is for cancelling pretend_world subprocess when it detect an world update
            'cancelled' :   False,  # same here so we know it has been cancelled if True
            # attributes for last world update informations extract from emerge.log file
            'last'      :   {
                    'state'     :   self.stateinfo.load('world last state'), 
                    'start'     :   int(self.stateinfo.load('world last start')),
                    'stop'      :   int(self.stateinfo.load('world last stop')),
                    'total'     :   int(self.stateinfo.load('world last total')),
                    'failed'    :   self.stateinfo.load('world last failed')
                }
            }
        
        # Portage attributes
        self.portage = {
            'current'   :   self.stateinfo.load('portage current'),
            'latest'    :   self.stateinfo.load('portage latest'),
            'available' :   self.stateinfo.load('portage available'),
            'remain'    :   30,     # check every 30s when 'available' is True
            'logflow'   :   True    # Control log info flow to avoid spamming syslog
            }

       
    def check_sync(self, init_run=False, recompute=False):
        """ Checking if we can sync repo depending on time interval.
        Minimum is 24H. """
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}check_sync::'
        
        # Check if sync is running
        if self.update_inprogress.check('Sync', additionnal_msg=self.sync['repos']['msg']):
            # Syncing is in progress keep last timestamp
            # Retry in ten minutes (so we got newly timestamp)
            self.sync['remain'] = 600
            # Make sure self.sync['status'] == True
            # This could mean sync is running outside the program
            if not self.sync['status']:
                self.log.error('Syncing is in progress but found status to False')
                self.log.error('If sync is not running outside the program, please report this')
                self.log.error('Resetting status to True')
                self.sync['status'] = True
            return False
        else:
            # Same here make sure self.sync['status'] == False
            if self.sync['status']:
                self.log.error('Syncing is NOT in progress but found status to True, please report this')
                self.log.error('Resetting status to False')
                self.sync['status'] = False
        
        # Get the last emerge sync timestamp
        myparser = EmergeLogParser(self.log, self.pathdir['emergelog'], self.logger_name)
        sync_timestamp = myparser.last_sync()
        self.log.name = f'{self.logger_name}check_sync::'
        
        current_timestamp = time.time()
        update_statefile = False
        
        # Refresh repositories infos
        self.sync['repos'] = self._get_repositories()
        self.log.name = f'{self.logger_name}check_sync::'
        
        if sync_timestamp:
            # Ok it's first run ever 
            if self.sync['timestamp'] == 0:
                self.log.debug('Found sync {0} timestamp set to factory: \'0\'.'.format(self.sync['repos']['msg']))
                self.log.debug(f'Setting to: \'{sync_timestamp}\'.')
                self.sync['timestamp'] = sync_timestamp
                update_statefile = True
                recompute = True
            # Detected out of program sync
            elif not self.sync['timestamp'] == sync_timestamp:
                self.log.debug('{0} has been sync outside the program, forcing pretend world...'.format(
                                                                                self.sync['repos']['msg'].capitalize()))
                self.world['pretend'] = True # So run pretend world update
                self.sync['timestamp'] = sync_timestamp
                update_statefile = True
                recompute = True
            
            # Compute / recompute time remain
            # This shouldn't be done every time method check_sync() is call
            # because it will erase the arbitrary time remain set by method dosync()
            if recompute:
                self.sync['elapse'] = round(current_timestamp - sync_timestamp)
                self.sync['remain'] = self.sync['interval'] - self.sync['elapse']
            
            self.log.debug('{0} sync elapsed time: \'{1}\'.'.format(self.sync['repos']['msg'].capitalize(),
                                                                    self.format_timestamp.convert(self.sync['elapse'])))
            self.log.debug('{0} sync remain time: \'{1}\'.'.format(self.sync['repos']['msg'].capitalize(),
                                                                   self.format_timestamp.convert(self.sync['remain'])))
            self.log.debug('{0} sync interval: \'{1}\'.'.format(self.sync['repos']['msg'].capitalize(),
                                                                self.format_timestamp.convert(self.sync['interval'])))
            
            if init_run:
                self.log.info('Found {0} {1} to sync: {2}'.format(self.sync['repos']['count'], 
                                                                  self.sync['repos']['msg'],
                                                                  self.sync['repos']['formatted']))
                self.log.info('{0} sync elapsed time: \'{1}\'.'.format(self.sync['repos']['msg'].capitalize(),
                                                                    self.format_timestamp.convert(self.sync['elapse'])))
                self.log.info('{0} sync remain time: \'{1}\'.'.format(self.sync['repos']['msg'].capitalize(),
                                                                    self.format_timestamp.convert(self.sync['remain'])))
                self.log.info('{0} sync interval: \'{1}\'.'.format(self.sync['repos']['msg'].capitalize(),
                                                                  self.format_timestamp.convert(self.sync['interval'])))
            
            if update_statefile:
                self.log.debug('Saving \'sync timestamp: {0}\' to \'{1}\'.'.format(self.sync['timestamp'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('sync timestamp', 'sync timestamp: ' + str(self.sync['timestamp']))
            else:
                self.log.debug('Skip saving \'sync timestamp: {0}\' to \'{1}\': already in good state.'.format(self.sync['timestamp'], 
                                                                                 self.pathdir['statelog']))
            
            if self.sync['remain'] <= 0:
                return True # We can sync :)
            return False
        return False        
    
    
    def dosync(self):
        """ Updating repo(s) """
        # Change name of the logger
        self.log.name = f'{self.logger_name}dosync::'
        
        # Check if sync is disable
        if self.sync['state'] == 'Failed' and not self.sync['network_error']:
            self.log.error('Skipping sync update due to previously error.')
            self.log.error('Fix the error and reset using syuppod\'s dbus client.')
            # Make sure to not recompute
            self.sync['recompute_done'] = True
            # Reset remain to interval otherwise it will call every seconds
            self.sync['remain'] = self.sync['interval']
            return
        
        # Check if already running
        # BUT this shouldn't happend
        if self.sync['status']:
            self.log.error('We are about to sync {0}, but just found status to True,'.format(self.sync['repos']['msg']))
            self.log.error('which mean syncing is in progress, please check and report if False')
            # Don't touch status
            # recheck in 10 minutes
            self.sync['remain'] = 600
            # Make sure to not recompute
            self.sync['recompute_done'] = True
            return # Return will not be check as we implant asyncio and thread
            # keep last know timestamp
        
        # Ok for now status is True
        self.sync['status'] = True
        
        # Refresh repositories infos
        self.sync['repos'] = self._get_repositories()
        self.log.name = f'{self.logger_name}dosync::'
                
        self.log.debug('Will sync {0} {1}: {2}.'.format(self.sync['repos']['count'], self.sync['repos']['msg'],
                                                                  ', '.join(self.sync['repos']['names'])))
        self.log.info('Start syncing {0} {1}: {2}'.format(self.sync['repos']['count'], self.sync['repos']['msg'],
                                                                  self.sync['repos']['formatted']))
            
        # Init logging
        self.log.debug('Initializing logging handler:')
        self.log.debug('Name: \'synclog\'')
        processlog = ProcessLoggingHandler(name='synclog')
        self.log.debug('Writing to: {0}'.format(self.pathdir['synclog']))
        mylogfile = processlog.dolog(self.pathdir['synclog'])
        self.log.debug('Log level: info')
        mylogfile.setLevel(processlog.logging.INFO)
        
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
        
        myargs = ['/usr/bin/emerge', '--sync']
        myprocess = subprocess.Popen(myargs, preexec_fn=on_parent_exit(), 
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        mylogfile.info('##########################################\n')
        
        for line in iter(myprocess.stdout.readline, ""):
            #TODO : get info messages as well
            #exemple : 
            #* An update to portage is available. It is _highly_ recommended
            #* that you update portage now, before any other packages are updated.
            
            #* To update portage, run 'emerge --oneshot portage' now.
            rstrip_line = line.rstrip()
            # write log             
            mylogfile.info(rstrip_line)
            # TEST detected network failure for main gentoo repo 
            if found_manifest_failure:
                # So make sure it's network related 
                if gpg_network_unreachable.match(rstrip_line):
                    repo_gentoo_network_unreachable = True
            if manifest_failure.match(rstrip_line):
                found_manifest_failure = True
            # TEST  get return code for each repo
            if failed_sync.match(rstrip_line):
                self.sync['repos']['failed'].append(failed_sync.match(rstrip_line).group(1))
            if success_sync.match(rstrip_line):
                self.sync['repos']['success'].append(success_sync.match(rstrip_line).group(1))                   
        myprocess.stdout.close()
        return_code = myprocess.poll()
        
        self.log.debug('Repo sync completed: {0}'.format(', '.join(self.sync['repos']['success'])))
        self.log.debug('Repo sync failed: {0}'.format(', '.join(self.sync['repos']['failed'])))
        
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
                # TEST TEST Cannot be same as module gitmanager because:
                # sync will make ALOT more time to fail.
                # See : /etc/portage/repos.conf/gentoo.conf 
                # @2020-23-01 (~30min): 
                # sync-openpgp-key-refresh-retry-count = 40
                # sync-openpgp-key-refresh-retry-overall-timeout = 1200
                # first 5 times @ 600s (10min) - real is : 40min
                # after 5 times @ 3600s (1h) - real is : 1h30
                # then reset to interval (so mini is 24H)
                msg_on_retry = ''
                self.sync['remain'] = 600
                if self.retry == 1:
                    msg_on_retry = ' (1 time already)'
                elif 2 <= self.retry <= 5:
                    msg_on_retry = ' ({0} times already)'.format(self.retry)
                elif 6 <= self.retry <= 10:
                    msg_on_retry = ' ({0} times already)'.format(self.retry)
                    self.sync['remain'] = 3600
                elif self.retry > 10:
                    msg_on_retry = ' ({0} times already)'.format(self.retry)
                    self.sync['remain'] = self.sync['interval']
                
                if not self.sync['repos']['success']:
                    # All the repos failed
                    self.log.error('{0} sync failed: network is unreachable.'.format(
                                                    self.sync['repos']['msg'].capitalize()))
                else:
                    self.log.error('Main gentoo repository failed to sync: network is unreachable.')
                    additionnal_msg = 'also'
                    if list_len - 1 > 0:
                        self.log.error('{0} {1} failed to sync: {2}.'.format(msg, additionnal_msg, 
                            ', '.join([name for name in self.sync['repos']['failed'] if not name == 'gentoo'])))
                # Increment retry
                old_sync_retry = self.retry
                self.retry += 1
                self.log.debug('Incrementing sync retry from {0} to {1}.'.format(old_sync_retry,
                                                                                 self.retry))
                self.log.error('Will retry{0} syncing in {1}.'.format(msg_on_retry,
                                                                      self.format_timestamp.convert(
                                                                          self.sync['remain'])))
                # Make sure to not recompute
                self.sync['recompute_done'] = True
            else:
                # Ok so this is not an network problem for main gentoo repo
                # Disable sync only if main gentoo repo have problem
                # Ok but this should be retry one time because of this :
                #   * Verifying /usr/portage/.tmp-unverified-download-quarantine ...!!! Manifest verification failed:
                # TODO TODO this should be retry with a different server ?! 
                # Keep TEST before  
                if 'gentoo' in self.sync['repos']['failed']:
                    self.log.error('Main gentoo repository failed to sync with a unexcept error !!.')
                    self.log.error('Auto sync has been disable. To reenable it, use syuppod\'s dbus client.')
                    additionnal_msg = 'also'
                    # State is Failed only if main gentoo repo failed
                    self.state = 'Failed'
                    # reset values
                    self.network_error = 0
                    self.retry = 0
                # Other repo
                if list_len - 1 > 0:
                    self.log.error('{0} {1}failed to sync: {2}.'.format(msg, additionnal_msg, 
                        ', '.join(name for name in self.sync['repos']['failed'] if not name == 'gentoo')))
                
                self.log.error('You can retrieve log from: \'{0}\'.'.format(self.pathdir['synclog']))
                
                if not additionnal_msg == 'also':
                    self.log.info('Will retry sync in {0}'.format(self.format_timestamp.convert(
                                                                                    self.sync['interval'])))
                    # Reset remain to interval
                    self.log.debug('Only {0} failed to sync: {1}.'.format(msg.lower(),
                                                                        ', '.join(self.sync['repos']['failed'])))
                self.log.debug('Resetting remain interval to {0}'.format(self.sync['interval']))
                # Any way reset remain to interval
                self.sync['remain'] = self.sync['interval']
                # Make sure to not recompute
                self.sync['recompute_done'] = True
        else:
            # Ok good :p
            self.state = 'Success'
            # Reset values
            self.retry = 0
            self.network_error = 0
            # Ok here we can recompute
            self.sync['recompute_done'] = False
            self.log.info('Successfully syncing {0}.'.format(self.sync['repos']['msg']))
            # BUG : found this in the log :
            #2020-01-10 09:10:39  ::portagemanager::PortageHandler::get_last_world_update::  Global update not in progress.
            #2020-01-10 09:10:39  ::portagemanager::EmergeLogParser::last_world_update::  Loading last '3000' lines from '/var/log/emerge.log'.
            #2020-01-10 09:10:39  ::portagemanager::EmergeLogParser::last_world_update::  Extracting list of completed, incompleted and partial global update group informations.
            #2020-01-10 09:10:39  ::portagemanager::EmergeLogParser::last_world_update::  Recording partial, start: 1578411408, stop: 1578425705, total packages: 203, failed: app-misc/piper-9999
            #2020-01-10 09:10:39  ::portagemanager::EmergeLogParser::last_world_update::  Extracting latest global update informations.
            #2020-01-10 09:10:39  ::portagemanager::EmergeLogParser::last_world_update::  Keeping partial, start: 1578411408, stop: 1578425705, total packages: 203, failed: app-misc/piper-9999
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Skip saving 'sync state: Success' to '/var/lib/syuppod/state.info': already in good state.
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Skip saving 'sync error: 0' to '/var/lib/syuppod/state.info': already in good state.
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Incrementing global sync count from '51' to '52'
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Incrementing current sync count from '0' to '1'
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Saving 'sync count: 52' to '/var/lib/syuppod/state.info'.
            #2020-01-10 09:10:40  ::utils::StateInfo::save::  'sync count: 52'.
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Initializing emerge log parser:
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Parsing file: /var/log/emerge.log
            #2020-01-10 09:10:40  ::portagemanager::PortageHandler::get_last_world_update::  Searching last sync timestamp.
            # this shouldn't be ::get_last_world_update:: but ::dosync:: BUG
            # Count only success sync
            old_count_global = self.sync['count']
            old_count = self.sync['current_count']
            
            self.sync['count'] = int(self.sync['count'])
            self.sync['count'] += 1
            self.log.debug('Incrementing global sync count from \'{0}\' to \'{1}\''.format(old_count_global,
                                                                                           self.sync['count']))
            self.sync['current_count'] += 1
            self.log.debug('Incrementing current sync count from \'{0}\' to \'{1}\''.format(old_count,
                                                                                    self.sync['current_count']))
            self.log.debug('Saving \'sync count: {0}\' to \'{1}\'.'.format(self.sync['count'], 
                                                                                 self.pathdir['statelog']))
            self.stateinfo.save('sync count', 'sync count: ' + str(self.sync['count']))
                
            # Get the sync timestamp from emerge.log
            self.log.debug('Initializing emerge log parser:')
            myparser = EmergeLogParser(self.log, self.pathdir['emergelog'], self.logger_name)
            self.log.debug('Parsing file: {0}'.format(self.pathdir['emergelog']))
            self.log.debug('Searching last sync timestamp.')
            sync_timestamp = myparser.last_sync()
                                
            if sync_timestamp:
                if sync_timestamp == self.sync['timestamp']:
                    self.log.warning(f'Bug in class \'{self.__class__.__name__}\', method: dosync(): sync timestamp are equal...')
                else:
                    self.log.debug('Updating sync timestamp from \'{0}\' to \'{1}\'.'.format(self.sync['timestamp'], sync_timestamp))
                    self.sync['timestamp'] = sync_timestamp
                    self.log.debug('Saving \'sync timestamp: {0}\' to \'{1}\'.'.format(self.sync['timestamp'], 
                                                                                 self.pathdir['statelog']))
                    self.stateinfo.save('sync timestamp', 'sync timestamp: ' + str(self.sync['timestamp']))
            # At the end of successfully sync, run pretend_world()
            self.world['pretend'] = True
            self.log.debug('Resetting remain interval to {0}'.format(self.sync['interval']))
            # Reset remain to interval
            self.sync['remain'] = self.sync['interval']
            self.log.info('Next syncing in {0}'.format(self.format_timestamp.convert(self.sync['interval'])))
                    
        # At the end
        self.sync['elapse'] = 0
        # Write / mod value only if change
        for value in 'state', 'retry', 'network_error':
            if not self.sync[value] == getattr(self, value):
                self.sync[value] = getattr(self, value)
                self.stateinfo.save(f'sync {value}', f'sync {value}: ' + str(getattr(self, value)))
        if not self.sync['status']:
            self.log.error('We are about to leave syncing process, but just found status already to False,'.format(
                                                                                        self.sync['repos']['msg']))
            self.log.error('which mean syncing is/was NOT in progress, please check and report if True')
        self.sync['status'] = False
        return                 
            
            
    def get_last_world_update(self):
        """Getting last world update timestamp"""
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}get_last_world_update::'
        
        # Check if we are running world update right now
        if self.update_inprogress.check('World'):
            self.world['update'] = True
            # Check every 2s
            self.world['remain'] = 2
            return
            # keep last know timestamp
        else:
            # World is not 'In Progress':
            self.world['update'] = False
            # Reset state of updated
            self.world['updated'] = False
            
            myparser = EmergeLogParser(self.log, self.pathdir['emergelog'], self.logger_name)
            # keep default setting 
            # TODO : give the choice cf EmergeLogParser() --> last_world_update()
            get_world_info = myparser.last_world_update()
            self.log.name = f'{self.logger_name}get_last_world_update::'
            
            if get_world_info:
                to_print = True                
                # Write only if change
                for key in 'start', 'stop', 'state', 'total', 'failed':
                    if not self.world['last'][key] == get_world_info[key]:
                        # Ok this mean world update has been run
                        # So run pretend_world()
                        self.world['pretend'] = True
                        self.world['updated'] = True
                        if to_print:
                            self.log.info('Global update has been run') # TODO: give more details
                            to_print = False
                            
                        self.world['last'][key] = get_world_info[key]
                        self.log.debug(f'Saving \'world last {key}: '
                                       + '\'{0}\' '.format(self.world['last'][key]) 
                                       + 'to \'{0}\'.'.format(self.pathdir['statelog']))
                        self.stateinfo.save('world last ' + key, 
                                            'world last ' + key 
                                            + ': ' + str(self.world['last'][key]))
            # Reset remain :)
            self.world['remain'] = 5
            return
    
    
    def pretend_world(self):
        """Check how many package to update"""
        # TODO more verbose for debug
        # TODO BUG crashed @ 2020 01 10 :: 09:10:40 without any reason AND no log ...
        # Change name of the logger
        self.log.name = f'{self.logger_name}pretend_world::'
        
        # Auto cancel if world update is in progress
        if self.world['update']:
            self.log.warning('The available package(s) update\'s search has been call.')
            self.log.warning('But a global update is in progress, skipping...')
            self.world['cancel'] = False
            self.world['cancelled'] = True
            self.world['status'] = False
            # stop running pretend !
            self.world['pretend'] = False
            return
        
        if not self.world['pretend']:
            self.log.error('We are about to search available package(s) update and found pretend to False,')
            self.log.error('which mean this was NOT authorized, please report it.')
        # Disable pretend authorization
        self.world['pretend'] = False
        # Make sure it's not already running        
        if self.world['status']:
            self.log.error('We are about to search available package(s) update and found status to True,')
            self.log.error('which mean it is already in progress, please check and report if False.')
            return
        self.world['status'] = True
        
        # Don't need to run if cancel just received
        if self.world['cancel']:
            self.log.warning('Stop searching available package(s) update as global update has been detected.')
            # Do we have already cancelled ?
            if self.world['cancelled']:
                self.log.warning('The previously task was already cancelled, check and report if False.')
            self.world['cancelled'] = True
            self.world['cancel'] = False
            self.world['status'] = False
            return
        
        self.log.debug('Start searching available package(s) update.')
                
        update_packages = False
        retry = 0
        # Removed .packages.* 
        find_build_packages = re.compile(r'^Total:.(\d+).*$', re.MULTILINE) # As we read by chunk not by line
        skip_line_with_dot_only = re.compile(r'^\.$', re.MULTILINE)
        
        # Init logging
        self.log.debug('Initializing logging handler.')
        self.log.debug('Name: pretendlog')
        processlog = ProcessLoggingHandler(name='pretendlog')
        self.log.debug('Writing to: {0}'.format(self.pathdir['pretendlog']))
        mylogfile = processlog.dolog(self.pathdir['pretendlog'])
        self.log.debug('Log level: info')
        mylogfile.setLevel(processlog.logging.INFO)
        
        myargs = [ '/usr/bin/emerge', '--verbose', '--pretend', '--deep', 
                  '--newuse', '--update', '@world', '--with-bdeps=y' ]
               
        while retry < 2:
            process = subprocess.Popen(myargs, preexec_fn=on_parent_exit(), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, universal_newlines=True) #bufsize=1
            self.log.debug('Running {0}'.format(' '.join(myargs)))
            mylogfile.info('Running {0}\n'.format(' '.join(myargs)))
            # Disable timestamp for logging
            processlog.set_formatter('short')
            # TODO for now i haven't found a simple and better way
            # thx to https://stackoverflow.com/a/28019908/11869956
            # The only problem is it's not line by line so we cannot write logfile with timestamp
            # so logfile is little bit a mess
            # BUG TODO Found this in a log :
            #   Total: 163 pa
            #   ckages (149 upgrades, 2 new, 6 in new slots, 6 reinstalls, 1 uninstall), Size of downloads: 1 304 240 KiB
            # So this is NOT the right way to read and write !!!
            # TODO have a look --> https://pypi.org/project/sarge/
            #       see also pexpect 

            sout = io.open(process.stdout.fileno(), 'rb', buffering=1, closefd=False)
            while not self.world['cancel']:
                buf = sout.read1(1024).decode('utf-8')
                if len(buf) == 0: 
                    break
                if not skip_line_with_dot_only.search(buf):
                    mylogfile.info(buf)
                if find_build_packages.search(buf):
                    #Ok so we got packages then don't retry
                    retry = 2
                    update_packages = int(find_build_packages.search(buf).group(1))
            # FIXME workaround to cancel this process when running in thread with asyncio
            # calling asyncio.Task.cancel() won't work 
            if self.world['cancel']:                
                self.log.warning('Stop searching available package(s) update as global update has been detected.')
                process.terminate()
                # Enable logging timestamp
                processlog.set_formatter('normal')
                mylogfile.info('Terminate process: global update has been detected.')
                mylogfile.info('##### END ####')
                if self.world['cancelled']:
                    self.log.warning('The previously task was already cancelled, check and report if False.')
                if not self.world['status']:
                    self.log.error('We are about to leave pretend process, but just found status already to False,')
                    self.log.error('which mean process is/was NOT in progress, please check and report if True')
                
                self.world['cancelled'] = True
                self.world['cancel'] = False
                self.world['status'] = False
                # skip every thing else
                return
            process.stdout.close()
            
            # get return code (see --> https://docs.python.org/3/library/subprocess.html#subprocess.Popen.poll)
            # better to use poll() over wait()
            return_code = process.poll()
            
            # Enable logging timestamp
            processlog.set_formatter('normal')
            mylogfile.info(f'Terminate process: exit with status {return_code}')
            mylogfile.info('##### END ####')
            
            # We can have return_code > 0 and matching packages to update.
            # This can arrived when there is, for exemple, packages conflict (solved by skipping).
            # if this is the case, continue anyway.
            if return_code:
                self.log.error('Got error while searching for available package(s) update.')
                self.log.error('Command: {0}, return code: {1}'.format(' '.join(myargs), return_code))
                self.log.error('You can retrieve log from: \'{0}\'.'.format(self.pathdir['pretendlog'])) 
                if retry < 2:
                    self.log.error('Retrying without opts \'--with-bdeps\'...')
        
            # Ok so do we got update package ?
            if retry == 2:
                if update_packages > 1:
                    msg = f'Found {update_packages} packages to update.'
                elif update_packages == 1:
                    msg = f'Found only one package to update.'
                # no package found
                else:
                    msg = f'System is up to date.'
                self.log.debug(f'Successfully search for packages update ({update_packages})')
                self.log.info(msg)
            else:
                # Remove --with-bdeps and retry one more time.
                retry += 1
                if retry < 2:
                    myargs.pop()
                    self.log.debug('Couldn\'t found how many package to update, retrying without opt \'--with bdeps\'.')

        # Make sure we have some update_packages
        if update_packages:
            if not self.world['packages'] == update_packages:
                self.world['packages'] = update_packages
                self.log.debug('Saving \'world packages: {0}\' to \'{1}\'.'.format(self.world['packages'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('world packages', 'world packages: ' + str(self.world['packages']))
        else:
            if not self.world['packages'] == 0:
                self.world['packages'] = 0
                self.log.debug('Saving \'world packages: {0}\' to \'{1}\'.'.format(self.world['packages'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('world packages', 'world packages: ' + str(self.world['packages']))
        
        # At the end
        if self.world['cancelled']:
            self.log.debug('The previously task has been cancelled, resetting state to False (as this one is ' +
                           'completed.')
        self.world['cancelled'] = False
        if not self.world['status']:
            self.log.error('We are about to leave pretend process, but just found status already to False,')
            self.log.error('which mean process is/was NOT in progress, please check and report if True')
        self.world['status'] = False


    def available_portage_update(self):
        """Check if an update to portage is available"""
        # TODO: be more verbose for debug !
        # TODO save only version 
        # Change name of the logger
        self.log.name = f'{self.logger_name}available_portage_update::'
        # Reset remain here as we return depending of the situation
        self.portage['remain'] = 30
        
        self.available = False
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
                self.log.error('Got not result when querying portage db for latest available portage package')
                return False
            # It's up to date 
            if self.latest == self.portage['current']:
                mysplit = pkgsplit(self.latest)
                if not mysplit[2] == 'r0':
                    myversion = '-'.join(mysplit[-2:])
                else:
                    myversion = mysplit[1]
                self.log.debug(f'No update to portage package is available (current version: {myversion}')
                # Reset 'available' to False if not
                # Don't mess with False vs 'False' / bool vs str
                if self.portage['available'] == 'True':
                        self.portage['available'] = False
                        self.stateinfo.save('portage available', 'portage available: ' + str(self.portage['available']))
                # Just make sure that self.portage['latest'] is also the same
                if self.latest == self.portage['latest']:
                    # Don't need to update any thing 
                    return True
                else:
                    self.stateinfo.save('portage latest', 'portage latest: ' + str(self.portage['latest']))
                    return True
            else:
                portage_list = vardbapi().match('portage')
        
        # Make sure current is not None
        if not portage_list:
            self.log.error('Got no result when querying portage db for installed portage package...')
            return False
        if len(portage_list) > 1:
            self.log.error('Got more than one result when querying portage db for installed portage package...')
            self.log.error('The list contain: {0}'.format(' '.join(portage_list)))
            self.log.error('This souldn\'t happend, anyway picking the first in the list.')
        
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
                self.log.error('Got no result when comparing latest available with installed portage package version.')
            else:
                self.log.error('Got unexcept result when comparing latest available with installed portage package version.')
                self.log.error('Result indicate that the latest available portage package version is lower than the installed one...') 
            
            self.log.error(f'Installed portage: \'{self.current}\', latest: \'{self.latest}\'.')
            if len(portage_list) > 1:
                self.log.error('As we got more than one result when querying portage db for installed portage package,')
                self.log.error('this could explain strange result.')
            # TODO: Should we reset all attributes ?
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
                    self.log.info(f'Found an update to portage (from {current_version} to {latest_version}).')
                    self.portage['logflow'] = False
                else:
                    self.log.debug(f'Found an update to portage (from {current_version} to {latest_version}).')
                self.available = True
                # Don't return yet because we have to update portage['current'] and ['latest'] 
            elif self.result == 0:
                self.log.debug(f'No update to portage package is available (current version: {current_version}')
                self.available = False
            
            # Update only if change
            for key in 'current', 'latest', 'available':
                if not self.portage[key] == getattr(self, key):
                    self.portage[key] = getattr(self, key)
                    self.log.debug('Saving \'portage {0}: {1}\' to \'{2}\'.'.format(key, self.portage[key], 
                                                                                 self.pathdir['statelog']))
                    self.stateinfo.save('portage ' + key, 'portage ' + key + ': ' + str(self.portage[key]))
                    # This print if there a new version of portage available
                    # even if there is already an older version available
                    if key == 'latest' and self.portage['logflow']:
                        self.log.info(f'Found an update to portage (from {current_version} to {latest_version}).')
    
    
    def _get_repositories(self):
        """Get repos informations and return formatted"""
        self.log.name = f'{self.logger_name}_get_repositories::'
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
            self.log.debug('Found {0} {1} to sync: {2}'.format(repo_count, repo_msg, ', '.join(names)))
            # return dict
            return { 'names' :   names, 'formatted' : repo_name, 'count' : repo_count, 'msg' : repo_msg }
        # This is debug message as it's not fatal for the program
        self.log.debug('Could\'nt found sync repositories name(s) and count...')
        # We don't know so just return generic
        return { 'names' : '', 'formatted' : 'unknow', 'count' : '(?)', 'msg' : 'repo' }
    
    

class EmergeLogParser:
    """Parse emerge.log file and extract informations"""
    def __init__(self, log, emergelog, logger_name):
        self.log = log
        self.logger_name =  f'::{__name__}::EmergeLogParser::'    #logger_name
        self.aborded = 5
        self.emergelog = emergelog
        
        self.lines = self.getlines()
        if not self.lines:
            # So we don't know how many lines have emerge.log 
            # go a head and give an arbitrary number
            self.lines = [60000, False]
        else:
            self.lines = [self.lines, True]
        self._range = { }
    
    
    def last_sync(self, lastlines=500):
        """Return last sync timestamp
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
            adapt from https://stackoverflow.com/a/54023859/11869956"""
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}last_sync::'
        
        # RE
        start_re = re.compile(r'^(\d+):\s{2}\*\*\*.emerge.*--sync.*$')
        completed_re = re.compile(r'^\d+:\s{1}===.Sync.completed.for.gentoo$')
        stop_re = re.compile(r'^\d+:\s{2}\*\*\*.terminating.$')
        
        self.lastlines = lastlines
        # construct exponantial list
        self._range['sync'] = numpy.geomspace(self.lastlines, self.lines[0], num=15, endpoint=True, dtype=int)
        with_delimiting_lines = True
        collect = [ ]
        keep_running = True
        count = 1
        
        while keep_running:
            self.log.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, self.emergelog))
            inside_group = False
            self.log.debug('Extracting list of successfully sync for main repo \'gentoo\'.')
            for line in self.getlog(self.lastlines):
                if inside_group:
                    if stop_re.match(line):
                        inside_group = False
                        if with_delimiting_lines:
                            group.append(line)
                        # Ok so with have all the line
                        # search over group list to check if sync for repo gentoo is in 'completed' state
                        # and add timestamp line '=== sync ' to collect list
                        for value in group:
                            if completed_re.match(value):
                                collect.append(current_timestamp)
                                self.log.debug(f'Recording: \'{current_timestamp}\'.')
                    else:
                        group.append(line)
                elif start_re.match(line):
                    inside_group = True
                    group = [ ]
                    current_timestamp = int(start_re.match(line).group(1))
                    if with_delimiting_lines:
                        group.append(line)
            # Collect is finished.
            # If we got nothing then extend  last lines to self.getlog()
            if collect:
                keep_running = False
            else:
                if self._keep_collecting(count, ['last sync timestamp for main repo \'gentoo\'', 
                                            'never sync...'], 'sync'):
                    self.log.name = f'{self.logger_name}last_sync::'
                    count = count + 1
                    keep_running = True
                else:
                    return False
        
        # Proceed to get the latest timestamp
        self.log.debug('Extracting latest sync from: {0}'.format(', '.join(str(timestamp) for timestamp in collect)))
        latest = collect[0]
        for timestamp in collect:
            if timestamp > latest:
                latest = timestamp
        if latest:
            self.log.debug(f'Select: \'{latest}\'.')
            return latest
        
        self.log.error('Failed to found latest update timestamp for main repo \'gentoo\'.')
        return False
     
    
    def last_world_update(self, lastlines=3000, incompleted=True, nincompleted=[30/100, 'percentage']):
        """Get last world update timestamp
        @param lastlines  read last n lines from emerge log file (as we don't have to read all the file to get last world update)
                          you can tweak it but any way if you lower it and if the function don't get anything in the first pass
                          it will increment it depending on function _keep_collecting()
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
                'failed'    -> if 'completed': 0, if 'partial' / 'incompleted': package number which failed. 
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
            1569447225:  ::: completed emerge (1 of 44) sys-kernel/linux-firmware-20190923 to / """
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}last_world_update::'
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
        self._range['world'] = numpy.geomspace(self.lastlines, self.lines[0], num=15, endpoint=True, dtype=int)
        
        incompleted_msg = ''
        if incompleted:
            incompleted_msg = ', incompleted'
        compiling = False
        package_name = None
        keep_running =  True
        current_package = False
        count = 1
        keepgoing = False
        #parallel_merge = False
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
        # TODO  need more testing. But for the moment: if opts --keep-going found,
        #       if new emerge is found (mean restart to '1 of n') then this will be treat as
        #       an auto restart, only true if current_package == True 
        # TODO  testing doing in a same time an world update and an other install
        keepgoing_opt = re.compile(r'^.*\s--keep-going\s.*$')
        #   So make sure we start to compile the world update and this should be the first package 
        start_compiling = re.compile(r'^\d+:\s{2}>>>.emerge.\(1.of.(\d+)\)\s(.*)\sto.*$')
        #   Make sure it's failed with status == 1
        failed = re.compile(r'(\d+):\s{2}\*\*\*.exiting.unsuccessfully.with.status.\'1\'\.$')
        succeeded = re.compile(r'(\d+):\s{2}\*\*\*.exiting.successfully\.$')
        
        # TODO  Give a choice to enable or disable incompleted collect
        #       Also: i think we should remove incompleted update which just failed after n package 
        #       Where n could be : a pourcentage or a number (if think 30% could be a good start)
        #       Maybe give the choice to tweak this as well  - YES !
        # TODO  Also we can update 'system' first (i'm not doing that way but)
        #       Add this option as well :)
        # TODO  Improve performance, for now :
        #       Elapsed Time: 2.97 seconds.  Collected 217 stack frames (88 unique)
        #       For 51808 lines read (the whole file) - but it's not intend to be 
        #       run like that
        #       With default settings:
        #       Elapsed Time: 0.40 seconds.  Collected 118 stack frames (82 unique)
        #       For last 3000 lines.
        
        # BUG FIX?? This is detected :
        #           1563019245:  >>> emerge (158 of 165) kde-plasma/powerdevil-5.16.3 to /
        #           1563025365: Started emerge on: juil. 13, 2019 15:42:45
        #           1563025365:  *** emerge --newuse --update --ask --deep --keep-going --with-bdeps=y --quiet-build=y --verbose world
        #       this is NOT a parallel emerge and the merge which 'crashed' (???) was a world update...
        #       After some more investigation: this is the only time in my emerge.log (~52000 lines)
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
            """Saving world update incompleted state"""
            if self.nincompleted[1] == 'percentage':
                if self.packages_count <= round(self.group['total'] * self.nincompleted[0]):
                    self.log.debug('NOT recording incompleted, ' 
                                    + 'start: {0}, '.format(self.group['start']) 
                                    + 'stop: {0}, '.format(self.group['stop']) 
                                    + 'total packages: {0}, '.format(self.group['total'])
                                    + 'failed: {0}'.format(self.group['failed']))
                    self.log.debug('Additionnal informations: not selected because:')
                    self.log.debug(f'Incompleted is True, packages count ({self.packages_count})'
                                    + ' <= packages total ({0})'.format(self.group['total'])
                                    + f' * percentage limit ({self.nincompleted[0]})')
                    self.log.debug('Round result is : {0} <= {1} (False)'.format(self.packages_count,
                                                    round(self.group['total'] * self.nincompleted[0])))
                    self.packages_count = 1
                    return
            elif self.nincompleted[1] == 'number':
                if self.packages_count <= self.nincompleted[0]:
                    self.log.debug('NOT recording incompleted, ' 
                                    + 'start: {0}, '.format(self.group['start']) 
                                    + 'stop: {0}, '.format(self.group['stop']) 
                                    + 'total packages: {0}, '.format(self.group['total'])
                                    + 'failed: {0}'.format(self.group['failed']))
                    self.log.debug('Additionnal informations: not selected because:')
                    self.log.debug(f'Incompleted is True, packages count ({self.packages_count})'
                                    + f' <= number limit ({self.nincompleted[0]}): False.')
                    self.packages_count = 1
                    return
            # Record how many package compile successfully
            # if it passed self.nincompleted
            self.group['state'] = 'incompleted'
            self.collect['incompleted'].append(self.group)
            self.log.debug('Recording incompleted, ' 
                            + 'start: {0}, '.format(self.group['start']) 
                            + 'stop: {0}, '.format(self.group['stop']) 
                            + 'total packages: {0}, '.format(self.group['total'])
                            + 'failed: {0}'.format(self.group['failed']))
            
        def _saved_partial():
            """Saving world update partial state""" 
            # Ok so we have to validate the collect
            # This mean that total number of package should be 
            # equal to : total of saved count - total of failed packages
            # This is NOT true every time, so go a head and validate any way
            # TODO: keep testing :)
            # Try to detect skipped packages due to dependency
            self.group['dropped'] = ''
            dropped =   self.group['saved']['total'] - \
                        self.group['saved']['count'] - \
                        self.packages_count
            if dropped > 0:
                self.group['dropped'] = f' (+{dropped} dropped)'
                                                                                    
            self.group['state'] = 'partial'
            self.group['total'] = self.group['saved']['total']
            #print('self.group[failed] is {0}'.format(self.group['failed']))
            # Easier to return str over list - because it's only for display
            self.group['failed'] = ' '.join(self.group['failed']) \
                                        + '{0}'.format(self.group['dropped'])
            self.collect['partial'].append(self.group)
            self.log.debug('Recording partial, ' 
                            + 'start: {0}, '.format(self.group['start']) 
                            + 'stop: {0}, '.format(self.group['stop']) 
                            + 'total packages: {0}, '.format(self.group['total'])
                            + 'failed: {0}'.format(self.group['failed']))
            
        def _saved_completed():
            """Saving world update completed state"""
            # workaround BUG describe just below
            for key in 'start', 'stop', 'total':
                try:
                    self.group.get(key)
                except KeyError:
                    self.log.error('While saving completed world update informations,')
                    self.log.error(f'got KeyError for key {key}, skip saving but please report it.')
                    # Ok so return and don't save
                    return
            self.group['state'] = 'completed'
            # For comptability 
            # Make str() because:
            # If value is not '0', then  value is str() any way.
            # stateinfo load as str()
            # if not str() then when comparing value in class PortageHandler
            #   method get_last_world_update(), it will keep rewriting value 
            #   because int(0) != str(0) and - by the way - this will be treat 
            #   as an world update run.
            self.group['failed'] = '0'
            self.collect['completed'].append(self.group)
            self.packages_count = 1
            # FIXME BUG : got this in stderr.log : 
            # 2019-12-19 12:09:49    File "/data/01/src/syuppod/main.py", line 131, in run
            # 2019-12-19 12:09:49      self.manager['portage'].get_last_world_update()
            # 2019-12-19 12:09:49    File "/data/01/src/syuppod/portagemanager.py", line 397, in get_last_world_update
            # 2019-12-19 12:09:49      get_world_info = myparser.last_world_update()
            # 2019-12-19 12:09:49    File "/data/01/src/syuppod/portagemanager.py", line 1207, in last_world_update
            # 2019-12-19 12:09:49      _saved_completed()
            # 2019-12-19 12:09:49    File "/data/01/src/syuppod/portagemanager.py", line 1056, in _saved_completed
            # 2019-12-19 12:09:49      .format(self.group['start'], self.group['stop'], self.group['total']))
            # 2019-12-19 12:09:49  KeyError: 'start'
            # This is strange and shouldn't arrived 
            # TODO This has been called succeeded.match BUT there were no succeeded world update (it failed immediatly
            # 5 times without any package compiled) ...
            # The most important thing it's this screew up the whole program ...
            # First workaround should be try / except : don't record this and print a warning !
            self.log.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                           .format(self.group['start'], self.group['stop'], self.group['total']))
        
                    
        while keep_running:
            self.log.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, self.emergelog))
            mylog = self.getlog(self.lastlines)
            self.log.debug(f'Extracting list of completed{incompleted_msg} and partial global update'
                           + ' group informations.')
            for line in mylog:
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
                            record.append(line)
                        if failed.match(line):
                            # We don't care about record here so reset it
                            record = [ ]
                            if not 'failed' in self.group:
                                self.group['failed'] = f'at {self.packages_count} ({package_name})'
                            # set stop
                            self.group['stop'] = int(failed.match(line).group(1))
                            # first make sure it's restart or it's just incompleted.
                            if keepgoing and 'total' in self.group['saved']:
                                _saved_partial()
                            elif incompleted:
                                _saved_incompleted()
                            else:
                                self.log.debug('NOT recording partial/incompleted, ' 
                                            + 'start: {0}, '.format(self.group['start']) 
                                            + 'stop: {0}, '.format(self.group['stop']) 
                                            + 'total packages: {0}, '.format(self.group['total'])
                                            + 'failed: {0}'.format(self.group['failed']))
                                self.log.debug(f'Additionnal informations: keepgoing ({keepgoing}), '
                                                f'incompleted ({incompleted}), '
                                                f'nincompleted ({self.nincompleted[0]} / {self.nincompleted[1]}).')
                            # At then end reset
                            self.packages_count = 1
                            current_package = False
                            compiling = False
                            package_name = None
                            keepgoing = False
                        elif keepgoing and start_compiling.match(line):
                            # Try to fix BUG describe upstair
                            unexcept_start = False
                            for saved_line in record:
                                # This is also a handled :
                                # 1581349345:  === (2 of 178) Compiling/Merging (kde-apps/pimcommon-19.12.2::/usr/portage/kde-apps/pimcommon/pimcommon-19.12.2.ebuild)
                                # 1581349360:  *** terminating.
                                # 1581349366: Started emerge on: févr. 10, 2020 16:42:46
                                # 1581349366:  *** emerge --newuse --update --ask --deep --keep-going --with-bdeps=y --quiet-build=y --verbose world
                                if start_opt.match(saved_line):
                                    unexcept_start = saved_line
                                    break
                            if unexcept_start:
                                # FIXME for now avoid logging this as error because 
                                # it's spam a LOT /var/log/messages (every self.world['remain'] seconds - 5s (2020-02-12))
                                # TODO maybe we -could- log only once this error...
                                self.log.debug(f'While parsing {self.emergelog}, got unexcept'
                                                f' world update start opt:')
                                self.log.debug(f'{unexcept_start}')
                                # Except first element in a list is a stop match
                                self.group['stop'] = int(re.match(r'^(\d+):\s+.*$', record[0]).group(1))
                                if not 'failed' in self.group:
                                    self.group['failed'] = f'at {self.packages_count} ({package_name})'
                                # First try if it was an keepgoing restart
                                if keepgoing and 'total' in self.group['saved']:
                                    self.log.debug('Forcing save of current world update group'
                                                + ' using partial (start: {0}).'.format(self.group['start']))
                                    _saved_partial()
                                # incompleted is enable ?
                                elif incompleted:
                                    self.log.debug('Forcing save of current world update group'
                                                + ' using incompleted (start: {0}).'.format(self.group['start']))
                                    _saved_incompleted()
                                else:
                                    self.log.debug('Skipping save of current world update group'
                                                   + ' (unmet conditions).')
                                # Ok now we have to restart everything
                                self.group = { }
                                # Get the timestamp
                                self.group['start'] = int(start_opt.match(unexcept_start).group(1))
                                #--keep-going setup
                                if keepgoing_opt.match(unexcept_start):
                                    keepgoing = True
                                self.group['total'] = int(start_compiling.match(line).group(1))
                                #Get the package name
                                package_name = start_compiling.match(line).group(2)
                                compiling = True
                                self.packages_count = 1
                                self.group['saved'] = {
                                    'count' :    0
                                }
                                # we are already 'compiling' the first package
                                current_package = True
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
                        elif re.match('\d+:\s{2}:::.completed.emerge.\(' 
                                            + str(self.packages_count) 
                                            + r'.*of.*' 
                                            + str(self.group['total']) 
                                            + r'\).*$', line):
                            current_package = False # Compile finished for the current package
                            record = [ ] # same here it's finished so reset record
                            compiling = True
                            package_name = None
                            if not self.packages_count >= self.group['total']:
                                self.packages_count += 1
                    elif re.match(r'^\d+:\s{2}>>>.emerge.\('
                                            + str(self.packages_count) 
                                            + r'.*of.*' 
                                            + str(self.group['total']) 
                                            + r'\).*$', line):
                        current_package = True
                        # reset record as it will restart 
                        record = [ ]
                        record.append(line) # Needed to set stop if unexcept_start is detected
                        # This is a lot of reapeat for python 3.8 we'll get this :
                        # https://www.python.org/dev/peps/pep-0572/#capturing-condition-values
                        # TODO : implant this ?
                        package_name = re.match(r'^\d+:\s{2}>>>.emerge.\('
                                                + str(self.packages_count) 
                                                + r'.*of.*' 
                                                + str(self.group['total']) 
                                                + r'\)\s(.*)\sto.*$', line).group(1)
                        compiling = True
                    elif succeeded.match(line):
                        # Reset record here as well
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
                            _saved_completed()
                        else:
                            self.log.debug('NOT recording completed, start: {0}, stop: {1}, packages: {2}'
                                          .format(self.group['start'], self.group['stop'], self.group['total']))
                            self.log.debug(f'Additionnal informations: packages count is {packages_count}')
                elif start_opt.match(line):
                    self.group = { }
                    # Get the timestamp
                    self.group['start'] = int(start_opt.match(line).group(1))
                    #--keep-going setup
                    if keepgoing_opt.match(line):
                        keepgoing = True
                    linecompiling = 0
                # So this is the nextline after start_opt match
                elif linecompiling == 1:
                    # Make sure it's start to compile
                    # Got StopIteration exception while running world update with @world
                    # There were no nextline.
                    # Class: UpdateInProgress (self.update_inprogress.check()) didn't detect world update
                    # This has been fixed but keep this in case.
                    #try:
                        #nextline = next(mylog)
                    #This mean we start to run world update 
                    #except StopIteration:
                        #compiling = False
                        #self.packages_count = 1
                        #current_package = False
                        #package_name = None
                        #keepgoing = False
                    #else:
                    if start_compiling.match(line):
                        #Ok we start already to compile the first package
                        #Get how many package to update 
                        self.group['total'] = int(start_compiling.match(line).group(1))
                        #Get the package name
                        package_name = start_compiling.match(line).group(2)
                        compiling = True
                        self.packages_count = 1
                        self.group['saved'] = {
                            'count' :    0
                            }
                        # we are already 'compiling' the first package
                        current_package = True
                    else:
                        #This has been aborded
                        self.group = { }
                        compiling = False
                        self.packages_count = 1
                        current_package = False
                        package_name = None
                        keepgoing = False
                        # don't touch linecompiling
                  
            # Do we got something ?
            if incompleted:
                if self.collect['completed'] or self.collect['incompleted'] or self.collect['partial']:
                    keep_running = False
                else:
                    # That mean we have nothing ;)
                    if self._keep_collecting(count, ['last global update timestamp', 
                                'have never been update using \'world\' update schema...'], 'world'):
                        self.log.name = f'{self.logger_name}last_world_update::'
                        keep_running = True
                        count = count + 1
                    else:
                        return False
            else:
                if self.collect['completed'] or self.collect['partial']:
                    keep_running = False
                else:
                    if self._keep_collecting(count, ['last global update timestamp', 
                                 'have never been update using \'world\' update schema...'], 'world'):
                        self.log.name = f'{self.logger_name}last_world_update::'
                        keep_running = True
                        count = count + 1
                    else:
                        return False
                   
        # So now compare and get the highest timestamp from each list
        tocompare = [ ]
        for target in 'completed', 'incompleted', 'partial':
            if self.collect[target]:
                # This this the start timestamp
                latest_timestamp = self.collect[target][0]['start']
                latest_sublist = self.collect[target][0]
                for sublist in self.collect[target]:
                    if sublist['start'] > latest_timestamp:
                        latest_timestamp = sublist['start']
                        latest_sublist = sublist
                # Add latest to tocompare list
                tocompare.append(latest_sublist)
        # Then compare latest from each list 
        # To find latest of latest
        self.log.debug('Extracting latest global update informations.')
        if tocompare:
            latest_timestamp = tocompare[0]['start']
            latest_sublist = tocompare[0]
            for sublist in tocompare:
                if sublist['start'] > latest_timestamp:
                    latest_timestamp = sublist['start']
                    # Ok we got latest of all latest
                    latest_sublist = sublist
        else:
            self.log.error('Failed to found latest global update informations.')
            # We got error
            return False
        
        if latest_sublist:
            if latest_sublist['state'] == 'completed':
                self.log.debug('Keeping completed, start: {0}, stop: {1}, total packages: {2}'
                        .format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['total']))
            elif latest_sublist['state'] == 'incompleted':
                self.log.debug('Keeping incompleted, start: {0}, stop: {1}, total packages: {2}, failed: {3}'
                        .format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['total'], latest_sublist['failed']))
            elif latest_sublist['state'] == 'partial':
                self.log.debug('Keeping partial, start: {0}, stop: {1}, total packages: {2}, failed: {3}'
                        .format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['saved']['total'], latest_sublist['failed']))
            return latest_sublist
        else:
            self.log.error('Failed to found latest world update informations.')
            return False           
   
   
    def getlines(self):
        """Get the total number of lines from emerge.log file"""
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
            self.log.error(f'Got error while getting lines number for \'{self.emergelog}\' file.')
            self.log.error('Command: {0}, return code: {1}'.format(' '.join(myargs), return_code))
            for line in mywc.stderr:
                line = line.rstrip()
                if line:
                    self.log.error(f'Stderr: {line}')
            mywc.stderr.close()
        # Got nothing
        return False
   
   
    def getlog(self, lastlines=100, offset=0):
        """Get last n lines from emerge.log file
        https://stackoverflow.com/a/136280/11869956"""
                
        myargs = ['/bin/tail', '-n', str(lastlines + offset), self.emergelog]
        mytail = subprocess.Popen(myargs, preexec_fn=on_parent_exit(),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        # From https://stackoverflow.com/a/4417735/11869956
        for line in iter(mytail.stdout.readline, ""):
            yield line.rstrip()
        mytail.stdout.close()
        
        return_code = mytail.poll()
        if return_code:
            self.log.error(f'Got error while reading {self.emergelog} file.')
            self.log.error('Command: {0}, return code: {1}'.format(' '.join(myargs), return_code))
            for line in mytail.stderr:
                line = line.rstrip()
                if line:
                    self.log.error(f'Stderr: {line}')
            mytail.stderr.close()
            
             
    def _keep_collecting(self, count, message, function):
        """Restart collecting if nothing has been found."""
               
        # Change name of the logger
        self.log.name = f'{self.logger_name}_keep_collecting::'
        
        if not self.lines[1]:
            to_print='(unknow maximum lines)'
        else:
            to_print='(it is the maximum)'
        
        # Count start at 1 because it follow self._range list
        if  count < 5:
            self.log.debug(f'After {count} run: couldn\'t found {message[0]}.')
            self.lastlines = self._range[function][count]
            self.log.debug('Restarting with an bigger increment...')
        elif count >= 5 and count < 10:
            self.log.debug(f'After {count} run, {message[0]} still not found...')
            self.log.debug('Restarting with an bigger increment...')
            self.lastlines = self._range[function][count]
        elif count >= 10 and count < 15:
            self.log.debug(f'After {count} run, {message[0]} not found !')
            self.log.debug('Restarting with an bigger increment...')
            self.log.debug(f'{self.aborded} pass left before abording...')
            self.aborded = self.aborded - 1
            self.lastlines = self._range[function][count]
        elif count == 15:
            self.log.error(f'After 15 pass and {self.lastlines} lines read {to_print}, couldn\'t find {message[0]}.')
            self.log.error(f'Look like the system {message[1]}')
            return False
        return True
