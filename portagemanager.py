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
import portage
import subprocess

from portage.versions import pkgcmp, pkgsplit
from utils import FormatTimestamp
from utils import CapturedFd
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
        # Sync attributes
        self.sync = {
            'state'         :   self.stateinfo.load('sync state'), # 'Success' / 'Failed'
            'update'        :   self.stateinfo.load('sync update'), # 'In Progress' / 'Finish'
            'log'           :   'TODO', # TODO CF gitmanager.py -> __init__ -> self.pull['log']
            'error'         :   self.stateinfo.load('sync error'),
            'count'         :   str(self.stateinfo.load('sync count')),   # str() or get 'TypeError: must be str, not int' or vice versa
            'timestamp'     :   int(self.stateinfo.load('sync timestamp')),
            'interval'      :   interval,
            'elapse'       :   0,
            'remain'        :   0,
            'current_count' :   0   # Counting sync count since running (current session)
            }
        
        # Print warning about interval it's 'too big'
        # If interval > 30 days (2592000 seconds)
        if self.sync['interval'] > 2592000:
            self.log.warning('Sync interval for portage update tree is too big (\'{0}\').'
                             .format(self.format_timestamp.convert(self.sync['interval'], granularity=6)))
        
        # World attributes
        self.world = {
            'status'    :   False,   # This mean we don't have to run pretend world update
            'pretend'   :   False,   # False / True when running pretend (avoid running twice)
            'update'    :   self.stateinfo.load('world update'), # 'In Progress' / 'Finish'
            'packages'  :   int(self.stateinfo.load('world packages')), # Packages to update
            'remain'    :   30, # Check every 30s  TODO: this could be tweaked (dbus client or args ?)
            'forced'    :   False, # to forced pretend for dbus client We could use 'status' key but 
                                   # this is for the future when async call will be implant.
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
    
    
    def check_sync(self, init_run=False, timestamp_only=False):
        """ Checking if we can sync repo depending on time interval.
        Minimum is 24H. """
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}check_sync::'
        
        # Check if sync is running
        if self.update_inprogress.check('Sync'):
            # Syncing is in progress keep last timestamp
            if not self.sync['update'] == 'In Progress':
                self.sync['update'] = 'In Progress'
                self.log.debug('Saving \'sync update: {0}\' to \'{1}\'.'.format(self.sync['update'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('sync update', 'sync update: ' + self.sync['update'])
            # Retry in ten minutes (so we got newly timestamp)
            self.sync['remain'] = 600
            return False
        else:
            # Reset update to 'Finished'
            if not self.sync['update'] == 'Finish':
                self.sync['update'] = 'Finish'
                self.log.debug('Saving \'sync update: {0}\' to \'{1}\'.'.format(self.sync['update'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('sync update', 'sync update: ' + self.sync['update'])
        
        # Get the last emerge sync timestamp
        myparser = EmergeLogParser(self.log, self.pathdir['emergelog'], self.logger_name)
        sync_timestamp = myparser.last_sync()
        
        self.log.name = f'{self.logger_name}check_sync::'
        
        if timestamp_only:
            return sync_timestamp
        
        current_timestamp = time.time()
        update_statefile = False
                
        if sync_timestamp:
            # Ok it's first run ever 
            if self.sync['timestamp'] == 0:
                self.log.debug('Found portage update repo timestamp set to factory: \'0\'.')
                self.log.debug(f'Setting to: \'{sync_timestamp}\'.')
                self.sync['timestamp'] = sync_timestamp
                update_statefile = True
            # This mean that sync has been run outside the program 
            elif init_run and not self.sync['timestamp'] == sync_timestamp:
                self.log.debug('Portage repo has been update outside the program, forcing pretend world...')
                self.world['status'] = True # So run pretend world update
                self.sync['timestamp'] = sync_timestamp
                update_statefile = True
            # Same here 
            elif self.sync['timestamp'] != sync_timestamp:
                self.log.debug('Portage repo has been update outside the program, forcing pretend world...')
                self.world['status'] = True # So run pretend world update
                self.sync['timestamp'] = sync_timestamp
                update_statefile = True
            
            self.sync['elapse'] = round(current_timestamp - sync_timestamp)
            self.sync['remain'] = self.sync['interval'] - self.sync['elapse']
            
            self.log.debug('Update repo elapsed time: \'{0}\'.'.format(self.format_timestamp.convert(self.sync['elapse'])))
            self.log.debug('Update repo remain time: \'{0}\'.'.format(self.format_timestamp.convert(self.sync['remain'])))
            self.log.debug('Update repo interval: \'{0}\'.'.format(self.format_timestamp.convert(self.sync['interval'])))
            
            if init_run:
                self.log.info('Update repo elapsed time: \'{0}\'.'.format(self.format_timestamp.convert(self.sync['elapse'])))
                self.log.info('Update repo remain time: \'{0}\'.'.format(self.format_timestamp.convert(self.sync['remain'])))
                self.log.info('Update repo interval: \'{0}\'.'.format(self.format_timestamp.convert(self.sync['interval'])))
            
            if update_statefile:
                self.log.debug('Saving \'sync timestamp: {0}\' to \'{1}\'.'.format(self.sync['timestamp'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('sync timestamp', 'sync timestamp: ' + str(self.sync['timestamp']))
            else:
                self.log.debug('Skip saving \'sync timestamp: {0}\' to \'{1}\': already in good state.'.format(self.sync['timestamp'], 
                                                                                 self.pathdir['statelog']))
            
            if self.sync['remain'] <= 0:
                return True
            return False
        return False        
    
    
    def dosync(self):
        """ Updating repo(s) """
        
        # TODO: asyncio :)
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}dosync::'
        
        # We going to sync :)
        if not self.sync['update'] == 'In Progress':
            self.sync['update'] = 'In Progress'
            self.log.debug('Saving \'sync update: {0}\' to \'{1}\'.'.format(self.sync['update'], 
                                                                            self.pathdir['statelog']))
            self.stateinfo.save('sync update', 'sync update: ' + self.sync['update'])
                
        # Check if already running
        if self.update_inprogress.check('Sync'):
            # recheck in 10 minutes
            self.sync['remain'] = 600
            return False # 'inprogress'
            # keep last know timestamp # Keep 'In Progress' 
                
        self.log.debug('Will update portage repository.')
            
        # Init logging
        self.log.debug('Initializing logging handler:')
        self.log.debug('Name: \'synclog\'')
        processlog = ProcessLoggingHandler(name='synclog')
        self.log.debug('Writing to: {0}'.format(self.pathdir['synclog']))
        mylogfile = processlog.dolog(self.pathdir['synclog'])
        self.log.debug('Log level: info')
        mylogfile.setLevel(processlog.logging.INFO)
        
        myargs = ['/usr/bin/emerge', '--sync']
        mysync = subprocess.Popen(myargs, preexec_fn=on_parent_exit(), 
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        #mysync = await asyncio.create_subprocess_exec(myargs, stdout=asyncio.subprocess.PIPE, 
                                                        # stderr=asyncio.subprocess.STDOUT, universal_newlines=True)
            
        mylogfile.info('##########################################\n')
        
        for line in iter(mysync.stdout.readline, ""):
            #TODO : get info messages as well
            #exemple : 
            #* An update to portage is available. It is _highly_ recommended
            #* that you update portage now, before any other packages are updated.
            
            #* To update portage, run 'emerge --oneshot portage' now.
            
            #TODO: as the log print successfully / failed sync by repo like :
            #Action: sync for repo: gentoo, returned code = 0
            #Action: sync for repo: steam-overlay, returned code = 0
            #Action: sync for repo: reagentoo, returned code = 0
            #Action: sync for repo: rage, returned code = 0
            #Action: sync for repo: pinkpieea, returned code = 0
            mylogfile.info(line.rstrip())
        mysync.stdout.close()
            
        # It's finished 
        if not self.sync['update'] == 'Finish':
            self.sync['update'] = 'Finish'
            self.log.debug('Saving \'sync update: {0}\' to \'{1}\'.'.format(self.sync['update'], 
                                                                            self.pathdir['statelog']))
            self.stateinfo.save('sync update', 'sync update: ' + self.sync['update'])
            
        return_code = mysync.wait()
        
        if return_code:
            self.log.error('Got error while updating portage repository.')
            self.log.error('Command: {0}, return code: {1}'.format(' '.join(myargs), return_code))
            self.log.error('You can retrieve log from: \'{0}\'.'.format(self.pathdir['synclog']))
                
            # don't write if state is already in 'Failed'
            if not self.sync['state'] == 'Failed':
                self.sync['state'] = 'Failed'
                self.log.debug('Saving \'sync state: {0}\' to \'{1}\'.'.format(self.sync['state'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('sync state', 'sync state: Failed')
            else:
                self.log.debug('Skip saving \'sync state: {0}\' to \'{1}\': already in good state.'.format(self.sync['state'], 
                                                                                 self.pathdir['statelog']))
                    
            # We mark the error and we exit after 3 retry
            #TODO : check this and pull['error'] as well and print an warning at startup 
            # or we can stop if error > max count and add an opts to reset the error (when fix)
            # then the option could be add to dbus client - thinking about this ;)
            old_count = self.sync['error']
            
            self.sync['error'] = int(self.sync['error'])
                              
            if int(self.sync['error']) > 3:
                self.log.critical('This is the third error while  updating portage repository.')
                self.log.critical('Cannot continue, please fix the error.')
                sys.exit(1)
            
            # Increment error count
            self.sync['error'] += 1
            self.log.debug('Incrementing sync error from \'{0}\' to \'{1}\''.format(old_count, 
                                                                                    self.sync['error']))
            self.log.debug('Saving \'sync error: {0}\' to \'{1}\'.'.format(self.sync['error'], 
                                                                                 self.pathdir['statelog']))
            self.stateinfo.save('sync error', 'sync error: ' + str(self.sync['error']))
                
            # Retry in self.sync['interval']
            self.log.info('Will retry update in {0}'.format(self.format_timestamp.convert(self.sync['interval'])))
            self.log.debug('Resetting remain interval to {0}'.format(self.sync['interval']))
            self.sync['remain'] = self.sync['interval']
                
            return False
                
        else:
            # Ok good :p
            # Don't update state file if it's already in state 'Success'
            if not self.sync['state'] == 'Success':
                self.sync['state'] = 'Success'
                # Update state file
                self.log.debug('Saving \'sync state: {0}\' to \'{1}\'.'.format(self.sync['state'], 
                                                                                self.pathdir['statelog']))
                self.stateinfo.save('sync state', 'sync state: Success')
            else:
                self.log.debug('Skip saving \'sync state: {0}\' to \'{1}\': already in good state.'.format(self.sync['state'], 
                                                                                 self.pathdir['statelog']))
                
            self.log.info(f'Successfully update portage repository.')
            
            # Same here if no error don't rewrite
            if not self.sync['error'] == '0':
                # Erase error 
                self.log.debug('Resetting sync error to \'0\'')
                self.sync['error'] = 0
                self.log.debug('Saving \'sync error: {0}\' to \'{1}\'.'.format(self.sync['error'], 
                                                                                self.pathdir['statelog']))
                self.stateinfo.save('sync error', 'sync error: 0')
            else:
                self.log.debug('Skip saving \'sync error: {0}\' to \'{1}\': already in good state.'.format(self.sync['error'], 
                                                                                 self.pathdir['statelog'])) 
                
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
                
            # Reset self.sync['remain'] to interval
            self.log.debug('Resetting remain interval to {0}'.format(self.sync['interval']))
            self.sync['remain'] = self.sync['interval']
            
            self.log.info('Will retry update in {0}'.format(self.format_timestamp.convert(self.sync['interval'])))
            
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
            return True
                
                
    def get_last_world_update(self):
        """Getting last world update timestamp"""
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}get_last_world_update::'
        
        # Check if we are running world update right now
        if self.update_inprogress.check('World'):
            if not self.world['update'] == 'In Progress':
                self.world['update'] = 'In Progress'
                self.log.debug('Saving \'world update: {0}\' to \'{1}\'.'.format(self.world['update'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('world update', 'world update: ' + self.world['update'])
            # Check every 10s
            self.world['remain'] = 10
            self.world['status'] = False # don't run pretend_world()
            return 'inprogress'
            # keep last know timestamp
        else:
            # World is not 'In Progress':
            if not self.world['update'] == 'Finish':
                self.world['update'] = 'Finish'
                self.log.debug('Saving \'world update: {0}\' to \'{1}\'.'.format(self.world['update'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('world update', 'world update: ' + self.world['update'])
            # else: TODO: debug log level :)
            
            self.world['remain'] = 25
            
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
                        #if key == 'start':
                        self.world['status'] = True
                        if to_print:
                            self.log.info('World update has been run') # TODO: give more details
                            to_print = False
                            
                        self.world['last'][key] = get_world_info[key]
                        self.log.debug(f'Saving \'world last {key}: '
                                       + '\'{0}\' '.format(self.world['last'][key]) 
                                       + 'to \'{0}\'.'.format(self.pathdir['statelog']))
                        self.stateinfo.save('world last ' + key, 
                                            'world last ' + key 
                                            + ': ' + str(self.world['last'][key]))
                return True # All good ;)
            else:
                # TODO : should we modified last world update attributes ?
                return False
                       
            
    def pretend_world(self):
        """Check how many package to update"""
         ## TODO : This have to be run in a thread because it take long time to finish
        # and we didn't really need to wait as will be in a forever loop ...
        # Ok TODO: asyncio give a try :)
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}pretend_world::'
        
        # Make sure it's not already running        
        if self.world['pretend']:
            self.log.warning('Pretend world already in progress, skipping...') # Normaly this should spam 
            return 'inprogress' # anyway at the moment we don't check return code 
        
        self.world['pretend'] = True
        update_packages = False
        retry = 0
        find_build_packages = re.compile(r'Total:.(\d+).packages.*')
         # Make sure 
        
        # Init logging 
        processlog = ProcessLoggingHandler(name='pretendlog')
        mylogfile = processlog.dolog(self.pathdir['pretendlog'])
        mylogfile.setLevel(processlog.logging.INFO)
        
        myargs = [ '/usr/bin/emerge', '--verbose', '--pretend', '--deep', 
                  '--newuse', '--update', 'world', '--with-bdeps=y' ]
               
        while retry < 2:
            mypretend = subprocess.Popen(myargs, preexec_fn=on_parent_exit(), 
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            mylogfile.info('##########################################\n')
            for line in iter(mypretend.stdout.readline, ""):
                    # Write the log
                    mylogfile.info(line.rstrip())
                    if find_build_packages.match(line):
                        # Ok so we got packages then don't retry
                        retry = 2
                        update_packages = int(find_build_packages.match(line).group(1))
            mypretend.stdout.close()
            
            # Check if return code is ok
            return_code = mypretend.wait()
            
            # We can have return_code > 0 and matching packages to update.
            # This can arrived when there is, for exemple, packages conflict (solved by skipping).
            # if this is the case, continue anyway.
            if return_code:
                self.log.error('Got error while pretending world update.')
                self.log.error('Command: {0}, return code: {1}'.format(' '.join(myargs), return_code))
                self.log.error('You can retrieve log from: \'{0}\'.'.format(self.pathdir['pretendlog'])) 
                if retry < 2:
                    self.log.error('Retrying without opts \'--with-bdeps\'...')
        
            # Ok so do we got update package ?
            if retry == 2:
                if update_packages > 1:
                    to_print = 'packages'
                else:
                    to_print = 'package'
                    
                self.log.info(f'Found {update_packages} {to_print} to update.')
            else:
                # Remove --with-bdeps and retry one more time.
                retry += 1
                if retry < 2:
                    myargs.pop()
                    self.log.debug('Couldn\'t found how many package to update, retrying without opt \'--with bdeps\'.')
                
        
        # pretend has been run then:
        self.world['status'] = False
        self.world['pretend'] = False
        
        # Make sure we have some update_packages
        if update_packages:
            if not self.world['packages'] == update_packages:
                self.world['packages'] = update_packages
                self.log.debug('Saving \'world packages: {0}\' to \'{1}\'.'.format(self.world['packages'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('world packages', 'world packages: ' + str(self.world['packages']))
            # else: debug log level
            return True
        else:
            if not self.world['packages'] == 0:
                self.world['packages'] = 0
                self.log.debug('Saving \'world packages: {0}\' to \'{1}\'.'.format(self.world['packages'], 
                                                                                 self.pathdir['statelog']))
                self.stateinfo.save('world packages', 'world packages: ' + str(self.world['packages']))
            return False


    def available_portage_update(self):
        """Check if an update to portage is available"""
        # TODO: be more verbose for debug !
        
        # Change name of the logger
        self.log.name = f'{self.logger_name}available_portage_update::'
        
        self.available = False
        # This mean first run ever / or reset statefile 
        if self.portage['current'] == '0.0' and self.portage['latest'] == '0.0':
            # Return list any way, see --> https://dev.gentoo.org/~zmedico/portage/doc/api/portage.dbapi-pysrc.html 
            # Function 'match' ->  Returns: 
            #                           a list of packages that match origdep 
            portage_list = portage.db[portage.root]['vartree'].dbapi.match('portage')
            self.latest = portage.db[portage.root]['porttree'].dbapi.xmatch('bestmatch-visible', 'portage')
        else:
            self.latest = portage.db[portage.root]['porttree'].dbapi.xmatch('bestmatch-visible', 'portage')
            if not self.latest:
                self.log.error('Got not result when querying portage db for latest available portage package')
                return False
            # It's up to date 
            if self.latest == self.portage['current']:
                self.log.debug(f'No update to portage package is available (current version: {self.latest}')
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
                portage_list = portage.db[portage.root]['vartree'].dbapi.match('portage')
        
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
            if self.result == 1:
                # Print one time only (when program start / when update found)
                # So this mean each time the program start and if update is available 
                # it will print.
                if self.portage['logflow']:
                    self.log.info(f'Found an update to portage (from {self.current} to {self.latest}).')
                    self.portage['logflow'] = False
                else:
                    self.log.debug(f'Found an update to portage (from {self.current} to {self.latest}).')
                self.available = True
                # Don't return yet because we have to update portage['current'] and ['latest'] 
            elif self.result == 0:
                self.log.debug(f'No update to portage package is available (current version: {self.current}')
                self.available = False
            
            # Update only if change
            for key in 'current', 'latest', 'available':
                if not self.portage[key] == getattr(self, key):
                    self.portage[key] = getattr(self, key)
                    self.log.debug('Saving \'portage {0}: {1}\' to \'{2}\'.'.format(key, self.portage[key], 
                                                                                 self.pathdir['statelog']))
                    self.stateinfo.save('portage ' + key, 'portage ' + key + ': ' + str(self.portage[key]))
                    # TODO: We need to test that
                    # But this should print if there a new version of portage available
                    # even if there is already an older version available
                    if key == 'latest' and self.portage['logflow']:
                        self.log.info(f'Found an update to portage (from {self.current} to {self.latest}).')
            


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
            self.log.debug('Extracting list of successfully update for main repo \'gentoo\'.')
            for line in self.getlog(self.lastlines):
                if inside_group:
                    if stop_re.match(line):
                        inside_group = False
                        if with_delimiting_lines:
                            group.append(line)
                        # Ok so with have all the line
                        # search over group list to check if sync for repo gentoo is in 'completed' state
                        # and add timestamp line '=== sync ' to collect list
                        # TODO: should we warn about an overlay which failed to sync ?
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
            # If we got nothing then extend by 100 last lines to self.getlog()
            if collect:
                keep_running = False
            else:
                if self._keep_collecting(count, ['last update timestamp for main repo \'gentoo\'', 
                                            'never sync...'], 'sync'):
                    self.log.name = f'{self.logger_name}last_sync::'
                    count = count + 1
                    keep_running = True
                else:
                    return False
        
        # Proceed to get the latest timestamp
        self.log.debug('Extracting latest update from: {0}'.format(', '.join(str(timestamp) for timestamp in collect)))
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
        #   (+n package(s) dropped) - this has to be tested more and more
        
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
        
        # BUGFIX   This is detected :
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
            self.log.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                           .format(self.group['start'], self.group['stop'], self.group['total']))
        
                    
        while keep_running:
            self.log.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, self.emergelog))
            mylog = self.getlog(self.lastlines)
            self.log.debug(f'Extracting list of completed{incompleted_msg} and partial world update'
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
                                if start_opt.match(saved_line):
                                    unexcept_start = saved_line
                                    break
                            if unexcept_start:
                                self.log.error(f'While parsing {self.emergelog}, got unexcept'
                                                f' world update start opt:')
                                self.log.error(f'{unexcept_start}')
                                # Except first element in a list is a stop match
                                self.group['stop'] = int(re.match(r'^(\d+):\s+.*$', record[0]).group(1))
                                if not 'failed' in self.group:
                                    self.group['failed'] = f'at {self.packages_count} ({package_name})'
                                # First try if it was an keepgoing restart
                                if keepgoing and 'total' in self.group['saved']:
                                    self.log.error('Forcing save of current world update group.')
                                    _saved_partial()
                                # if incompleted is enable
                                elif incompleted:
                                    self.log.error('Forcing save of current world update group.')
                                    _saved_incompleted()
                                else:
                                    self.log.error('Skipping save of current world update group '
                                                   + '(unmet conditions).')
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
                    if self._keep_collecting(count, ['last world update timestamp', 
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
                    if self._keep_collecting(count, ['last world update timestamp', 
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
        self.log.debug('Extracting latest world update informations.')
        if tocompare:
            latest_timestamp = tocompare[0]['start']
            latest_sublist = tocompare[0]
            for sublist in tocompare:
                if sublist['start'] > latest_timestamp:
                    latest_timestamp = sublist['start']
                    # Ok we got latest of all latest
                    latest_sublist = sublist
        else:
            self.log.error('Failed to found latest world update informations.')
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
        
        return_code = mywc.wait()
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
        
        return_code = mytail.wait()
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
