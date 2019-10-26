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
import _emerge

from portage.versions import vercmp, ververify, cpv_getversion
from portage.emaint.modules.sync.sync import SyncRepos
from _emerge import actions
from utils import FormatTimestamp
from utils import CapturedFd
from logger import ProcessLoggingHandler

class PortageTracking:
    """Portage tracking class"""
    
    def __init__(self, interval, stateinfo, log, synclog, emergelog, pretendlog):
        self.stateinfo = stateinfo
        self.interval = interval
        self.log = log
        self.synclog = synclog
        self.emergelog = emergelog
        self.pretendlog = pretendlog
        self.format_timestamp = FormatTimestamp()
        self.human_interval = self.format_timestamp.convert(self.interval)
        self.elasped = 0
        self.human_elasped = 'None'
        self.remain = 0
        self.human_remain = 'None'
               
        # Sync attributes
        self.sync = {
            'status'    :   False, # By default it's disable ;)
            'state'     :   self.stateinfo.load('sync state'),
            'log'       :   'TODO', # TODO CF __init__ --> self.pull --> 'log'
            'error'     :   self.stateinfo.load('sync error'),
            'count'     :   str(self.stateinfo.load('sync count')),   # str() or get 'TypeError: must be str, not int' or vice versa
            'timestamp' :   int(self.stateinfo.load('sync timestamp')) 
            }
        # World attributes
        self.world = {
            'last'      :   self.stateinfo.load('world last'),
            'status'    :   False,   # This mean we don't have to run pretend world update
            'start'     :   int(self.stateinfo.load('world start')),
            'stop'      :   int(self.stateinfo.load('world stop')),
            'state'     :   self.stateinfo.load('world state'),
            'failed'    :   int(self.stateinfo.load('world failed')),            
            'update'    :   int(self.stateinfo.load('world update'))
            }
        self.portage = {
            'current'   :   self.stateinfo.load('portage current'),
            'latest'    :   self.stateinfo.load('portage latest'),
            'available' :   self.stateinfo.load('portage available')
            }
    
    
    def check_sync(self, init_run=False):
        """ Checking if we can sync repo depending on time interval.
        Minimum is 24H. """
        # Get the last emerge sync timestamp
        myparser = EmergeLogParser(self.log, self.emergelog)
        sync_timestamp = myparser.last_sync()
        
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
            elif init_run and self.sync['timestamp'] != sync_timestamp:
                self.log.debug('Portage repo has been update outside the program, forcing pretend world...')
                self.world['status'] = True # So run pretend world update
                self.sync['timestamp'] = sync_timestamp
                update_statefile = True
            elif self.sync['timestamp'] != sync_timestamp:
                self.log.warning('Bug in class \'PortageTracking\', method: check_sync(): timestamp are not the same...')
            
            self.elasped = round(current_timestamp - sync_timestamp)
            self.remain = self.interval - self.elasped
            self.log.debug('Update repo elasped time: \'{0}\'.'.format(self.format_timestamp.convert(self.elasped)))
            self.log.debug('Update repo remain time: \'{0}\'.'.format(self.format_timestamp.convert(self.remain)))
            self.log.debug('Update repo interval: \'{0}\'.'.format(self.format_timestamp.convert(self.interval)))
            
            if update_statefile:
                self.log.debug('Updating state file info.')
                self.stateinfo.save('sync timestamp', 'sync timestamp: ' + str(self.sync['timestamp']))
            
            if self.remain <= 0:
                self.sync['status'] = True
                return True
            
            return False
        
        else:
            return False        
    
    
    def dosync(self):
        """ Updating repo(s) """
        # Initalise
        sync = SyncRepos()
        
        # Get repo list
        repos = sync._get_repos()

        if repos[0]:
            # We have repo(s) to sync
            # Get the name of each
            names = re.findall('RepoConfig\(name=\'(.*?)\',.location', str(repos[1]), re.DOTALL)
            
            if names:
                repo_count = len(names)
                # Print only first three elements if list > 3
                if repo_count > 3:
                    repo_print = [ 'repositories',  ', '.join(names[:3]) + ' (+' + str(repo_count - 3) + ')' ]
                elif repo_count == 1:
                    repo_print = [ 'repository', ', '.join(names) ]
                else:
                    repo_print = [ 'repositories', ', '.join(names) ]
            else:
                # This shouldn't happend ...
                repo_print = [ 'repository',  '?...' ]
                repo_count = '?'
        
            #sttime = datetime.now().strftime('%Y-%m-%d %H:%M:%S  ')
            #sttime = time.strftime('%Y-%m-%d %H:%M:%S  ', time.localtime(time.time()))
            self.log.debug(f'Updating {repo_count} portage {repo_print[0]}.')
            
            # Init logging
            processlog = ProcessLoggingHandler(name='synclog')
            mylogfile = processlog.dolog(self.synclog)
            mylogfile.setLevel(processlog.logging.INFO)
                     
            with CapturedFd(fd=[1,2]) as tmpfile:
                ## TODO:
                # We have choice between all_repos and auto_sync 
                # So give the choice as well:
                # opts = --reposync, -y
                # Default is auto_sync()
                # state list is the return code from sync and as well msg from portage (if any)
                state = sync.auto_sync()
                
            try:
                with pathlib.Path(tmpfile.name).open() as mytmp:
                    mylogfile.info('##########################################\n')
                    for line in mytmp.readlines():
                        mylogfile.info(line)
            # Exception is from pathlib
            except (OSError, IOError) as error:
                self.log.warning('Error while writing sync log to log file.')
                if error.errno == errno.EPERM or error.errno == errno.EACCES:
                    self.log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                    self.log.critical(f'Daemon is intended to be run as sudo/root.')
                    sys.exit(1)
                else:
                    self.log.warning(f'Got: \'{error}\'.')
                    self.log.warning('You can retrieve complete log from dbus client.')
            else:
                self.log.debug(f'Sync log has been wrote to file: \'{self.synclog}\'.')
            
            # Examine state[0]: True / False
            if state[0]:
                # Sync is ok 
                
                # Don't update state file as it's already in state 'Success'
                if not self.sync['state'] == 'Success':
                                   
                    self.sync['state'] = 'Success'
                    # Update state file
                    self.stateinfo.save('sync state', 'sync state: Success')
                    self.log.info(f'Successfully update portage {repo_print[0]}: {repo_print[1]}.')
                
                # Same here if no error don't rewrite
                if not self.sync['error'] == '0':
                    # Erase error 
                    self.sync['error'] = 0
                    self.stateinfo.save('sync error', 'sync error: 0')
                
                
                # Count only success sync
                self.sync['count'] = int(self.sync['count'])
                self.sync['count'] += 1
                self.stateinfo.save('sync count', 'sync count: ' + str(self.sync['count']))
                
                # Reset self.remain to interval
                self.remain = self.interval
                
                # Get the sync timestamp from emerge.log 
                myparser = EmergeLogParser(self.log, self.emergelog)
                sync_timestamp = myparser.last_sync()
                
                if sync_timestamp:
                    if sync_timestamp == self.sync['timestamp']:
                        self.log.warning('Bug in class \'PortageTracking\', method: dosync(): timestamp are equal...')
                    else:
                        self.log.debug('Updating sync timestamp from \'{0}\' to \'{1}\'.'.format(self.sync['timestamp'], sync_timestamp))
                        self.sync['timestamp'] = sync_timestamp
                        self.stateinfo.save('sync timestamp', 'sync timestamp: ' + self.sync['timestamp'])
                
            else:
                # Problem
                # Here as well don't write if state is already in 'Failed'
                if not self.sync['state'] == 'Failed':
                    self.sync['state'] = 'Failed'
                    self.stateinfo.save('sync state', 'sync state: Failed')
                    self.log.error(f'Failed to update portage {repo_print[0]}: {repo_print[1]}.')
                
                # We mark the error and we exit after 3 retry
                # TODO : check this and pull['error'] as well and print an warning at startup 
                # or we can stop if error > max count and add an opts to reset the error (when fix)
                # then the option could be add to dbus client - thinking about this ;)
                self.sync['error'] = int(self.sync['error'])
                
                if int(self.sync['error']) > 3:
                    self.log.critical('This is the third error while syncing repo(s).')
                    self.log.critical('Cannot continue, please fix the error.')
                    sys.exit(1)
                
                # Increment error count
                self.sync['error'] += 1
                self.stateinfo.save('sync error', 'sync error: ' + str(self.sync['error']))
                
                # Retry in self.interval
                self.log.info('Will retry update in {0}'.format(self.format_timestamp.convert(self.interval)))
                self.remain = self.interval
            
            # This is for msg return from sync.auto_sync() but
            # i still don't really know which kind of message is...
            # TODO : investigate so we can know if this is needed or not.
            if state[1]:
                self.log.info(f'Got message while updating {repo_print[0]}: {state[1]}.')
        
        # No repo found ?!
        else:
            self.log.error('No repository found, abording update !')
            self.sync['state'] = 'No Repo'
            self.stateinfo.save('sync state', 'sync state: No Repo')
            
            # Increment error as well
            if int(self.sync['error']) > 3:
                self.log.critical('This is the third error while syncing repo(s).')
                self.log.critical('Cannot continue, please fix the error.')
                sys.exit(1)
            
            self.sync['error'] = int(self.sync['error'])
            self.sync['error'] += 1
            self.stateinfo.save('sync error', 'sync error: ' + str(self.sync['error']))
            
            # Ok keep syncing any way
            self.remain = self.interval
    
    def get_last_world_update(self):
        """Getting last world update timestamp"""
        # Check if we are running world update right now
        if world_update_inprogress(self.log):
            return 'inprogress'
            # For now keep last know timestamp
        else:
            myparser = EmergeLogParser(self.log, self.emergelog)
            # Ok for now keep default setting 
            # TODO : give the choice cf EmergeLogParser() --> last_world_update()
            world_timestamp = myparser.last_world_update()
            
            if world_timestamp:
                self.world['start'] = world_timestamp['start']
                self.world['stop'] = world_timestamp['stop']
                self.world['state'] = world_timestamp['state']
                try:
                    self.world['failed'] = world_timestamp['failed']
                except KeyError:
                    self.world['failed'] = 0
                return True
            else:
                return False
                       
            
    def pretend_world(self):
        """Check how many package to update"""
        ## TODO : This have to be run in a thread because it take long time to finish
        # and we didn't really need to wait.
        update_packages = False
        retry = 0
        find_build_packages = re.compile(r'Total:.(\d+).packages.*')
        myconfig = actions._emerge_config(action={ 'update' :  True }, args={ 'world' : True }, 
                                                      opts={ '--verbose' : True, '--pretend' : True, 
                                                             '--deep' : True, '--newuse' : True, 
                                                             '--update' : True, '--with-bdeps' : True  })
        # Init logging 
        processlog = ProcessLoggingHandler(name='pretendlog')
        mylogfile = processlog.dolog(self.pretendlog)
        mylogfile.setLevel(processlog.logging.INFO)
                
        while retry < 2:
            loadconfig = _emerge.actions.load_emerge_config(emerge_config=myconfig)
            try:
                # TODO : Should we capture stderr and stdout singly ?
                # TODO : expose this to dbus client and maybe propose to apply the proposal update ?
                #        Any way we HAVE to capture both (stdout and sterr) or sdtout will be print 
                #        to terminal or else where...
                self.log.debug('Getting how many packages have to be update.')
                self.log.debug('This could take some time, please wait...')
                               
                with CapturedFd(fd=[1, 2]) as tmpfile:
                    _emerge.actions.action_build(loadconfig)
                    
                # Make sure we have a total package
                with pathlib.Path(tmpfile.name).open() as mytmp:
                    #with pathlib.Path(self.pretendlog).open(mode='a') as mylogfile:
                    mylogfile.info('##################################################################\n')
                    for line in mytmp.readlines():
                        mylogfile.info(line.rstrip())
                        if find_build_packages.match(line):
                            # Ok so we got packages then don't retry
                            retry = 2
                            update_packages = int(find_build_packages.match(line).group(1))
                    
                # Ok so do we got update package ?
                if retry == 2:
                    if update_packages > 1:
                        to_print = 'packages'
                    else:
                        to_print = 'package'
                    
                    self.log.info(f'Found {update_packages} {to_print} to update.')
                else:
                    # Remove --with-bdeps and retry one more time.
                    myconfig = _emerge.actions._emerge_config(action={ 'update' :  True }, args={ 'world' : True }, 
                                                                opts={ '--verbose' : True, '--pretend' : True, 
                                                                       '--deep' : True, '--newuse' : True, 
                                                                       '--update' : True}) 
                    self.log.debug('Couldn\'t found how many package to update, retrying without opt \'--with-bdeps\'.')
                    retry = 1
            # TODO : get Exception from portage / _emerge !!
            except Exception as exc:
                self.log.error(f'Got unexcept error : {exc}')
            
        # Make sure we have some update_packages
        if update_packages:
            self.world['update'] = update_packages
            return True
        else:
            self.world['update'] = False
            return False

    def available_portage_update(self):
        """Check if an update to portage is available"""
        
        # This mean first run ever / or reset statefile 
        if self.portage['current'] == '0.0' and self.portage['latest'] == '0.0':
            # Return list any way, see --> https://dev.gentoo.org/~zmedico/portage/doc/api/portage.dbapi-pysrc.html 
            # Function 'match' ->  Returns: 
            #                           a list of packages that match origdep 
            current = portage.db[portage.root]['vartree'].dbapi.match('portage')
            latest = portage.db[portage.root]['porttree'].dbapi.xmatch('bestmatch-visible', 'portage')
        else:
            latest = portage.db[portage.root]['porttree'].dbapi.xmatch('bestmatch-visible', 'portage')
            if not latest:
                self.log.error('Got not result when querying portage db for latest available portage package')
                return False
            # It's up to date 
            if latest == self.portage['current']:
                # Just make sure that self.portage['latest'] is also the same
                # TODO : 'available' !!
                if latest == self.portage['latest']:
                    # Don't need to update any thing 
                    return True
                else:
                    self.portage['latest'] = latest
                    self.stateinfo.save('portage latest', 'portage latest: ' + str(latest))
                    return True
            else:
                current = portage.db[portage.root]['vartree'].dbapi.match('portage')
        
        # Make sure current is not None
        if not current:
            self.log.error('Got no result when querying portage db for installed portage package...')
            return False
        if len(current) > 1:
            self.log.error('Got more than one result when querying portage db for installed portage package...')
            self.log.error('The list contain: {0}'.format(' '.join(current)))
            self.log.error('This souldn\'t happend, picking the first in the list.')
        
        
        #if current == self.portage['current'] and latest == self.portage['latest']:
            #Still have an update but it's already know ?
            #TODO check 'available' !
            #return True
        
        # From https://dev.gentoo.org/~zmedico/portage/doc/api/portage.versions-pysrc.html
        # Parameters:
        # pkg1 (list (example: ['test', '1.0', 'r1'])) - package to compare with
        # pkg2 (list (example: ['test', '1.0', 'r1'])) - package to compare againts
        # Returns: None or integer
        # None if package names are not the same
        # 1 if pkg1 is greater than pkg2
        # -1 if pkg1 is less than pkg2
        # 0 if pkg1 equals pkg2
        result = pkgcmp(pkgsplit(latest),pkgsplit(current[0]))
        
        if not result:
            self.log.error('Got no result when comparing latest available with current portage package update.')
            self.log.error(f'Current portage: \'{current}\', latest: \'{latest}\'.')
            return False
        elif result == 1:
            self.log.info(f'Found an update to portage (from {current[0]} to {latest}).')
            # Don't return yet because we have to update portage['current'] and ['latest'] and 
        elif result == 0:
            print('Same version, no update available')
        elif result == -1:
            print('Oops !')



class EmergeLogParser:
    """Parse emerge.log file and extract informations"""
    def __init__(self, log, emergelog):
        self.log = log 
        self.aborded = 5
        self.emergelog = emergelog
    
    def last_sync(self, lastlines=100):
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
      
        # RE
        start_re = re.compile(r'^(\d+):\s{2}===.sync$')
        completed_re = re.compile(r'^\d+:\s{1}===.Sync.completed.for.gentoo$')
        stop_re = re.compile(r'^\d+:\s{2}\*\*\*.terminating.$')
        
        self.lastlines = lastlines
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
                if self._keep_collecting(count, ['last update for main repo \'gentoo\'', 
                                            'never sync...']):
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
            self.log.debug(f'Found: \'{latest}\'.')
            return latest
        
        self.log.error('Failed to found latest update timestamp for main repo \'gentoo\'.')
        return False
     
    
    def last_world_update(self, lastlines=1000, incompleted=True, nincompleted=[30/100, 'percentage']):
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
                'packages'  -> total packages which has been / could been update.
                'state'     -> could be 'completed' if success or 'incompleted' if failed.
                'failed'    -> definied only if failed, package number which failed. 
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
        
        collect = {
            'completed' :   [ ],
            'incompleted'   :   [ ]
            }
        
        incompleted_msg = ''
        if incompleted:
            incompleted_msg = 'and incompleted'
        
        compiling = False
        packages_count = 1
        keep_running =  True
        current_package = False
        count = 1
        self.lastlines = lastlines
        
        # RE
        start = re.compile(r'^(\d+):\s{2}\*\*\*.emerge.*world.*$')
        # So make sure we start to compile the world update and this should be the first package 
        not_aborded = re.compile(r'^\d+:\s{2}>>>.emerge.\(1.of.(\d+)\).*$')
        failed = re.compile(r'(\d+):\s{2}\*\*\*.exiting.unsuccessfully.with.status.*$')
        succeeded = re.compile(r'(\d+):\s{2}\*\*\*.exiting.successfully\.$')
        
        # TODO : Give a choice to enable or disable incompleted collect
        #        Also: i think we should remove incompleted update which just failed after n package 
        #        Where n could be : a pourcentage or a number (if think 30% could be a good start)
        #        Maybe give the choice to tweak this as well  - YES !
        # TODO : Also we can update 'system' first (i'm not doing that way but)
        #        Add this option as well :)
        
        while keep_running:
            self.log.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, self.emergelog))
            mylog = self.getlog(self.lastlines)
            self.log.debug(f'Extracting list of completed {incompleted_msg} world update informations.')
            for line in mylog:
                if compiling:
                    if current_package:
                        if failed.match(line):
                            current_package = False
                            compiling = False
                            # If incompleted is enable (by default)
                            if incompleted:
                                if nincompleted[1] == 'percentage':
                                    if packages_count <= group['packages'] * nincompleted[0]:
                                        packages_count = 1
                                        continue
                                elif nincompleted[1] == 'number':
                                    if packages_count <= nincompleted[0]:
                                        packages_count = 1
                                        continue
                                group['stop'] = int(failed.match(line).group(1))
                                # Record how many package compile successfully
                                # So if incompleted is enable and nincompleted
                                group['failed'] = packages_count
                                group['state'] = 'incompleted'
                                collect['incompleted'].append(group)
                                self.log.debug('Recording incompleted, start: {0}, stop: {1}, packages: {2}, failed at: {3}'
                                          .format(group['start'], group['stop'], group['packages'], group['failed']))
                            packages_count = 1
                        elif re.match('\d+:\s{2}:::.completed.emerge.\(' 
                                            + str(packages_count) + r'.*of.*' 
                                            + str(group['packages']) + r'\).*$', line):
                            current_package = False # Compile finished
                            compiling = True
                            packages_count = packages_count + 1
                    elif re.match(r'^\d+:\s{2}>>>.emerge.\('
                                            + str(packages_count) + r'.*of.*' 
                                            + str(group['packages']) + r'\).*$', line):
                        current_package = True
                    elif succeeded.match(line):
                        # Make sure it's succeeded the right compile
                        # In case we run parallel emerge
                        if packages_count >= group['packages']:
                            current_package = False
                            compiling = False
                            group['stop'] = int(succeeded.match(line).group(1))
                            group['state'] = 'completed'
                            collect['completed'].append(group)
                            packages_count = 1
                            self.log.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                                          .format(group['start'], group['stop'], group['packages']))
                        # Just leave the rest because we don't in which state we are...
                elif start.match(line):
                    group = { }
                    # Make sure it's start to compile
                    nextline = next(mylog)
                    if not_aborded.match(nextline):
                        # Ok we start already to compile the first package
                        # So get the timestamp when we start  
                        group['start'] = int(start.match(line).group(1))
                        # Get how many package to update 
                        group['packages'] = int(not_aborded.match(nextline).group(1))
                        
                        compiling = True
                        packages_count = 1
                        
                        # As we jump to the next line we are already 'compiling' the first package
                        current_package = True
                    else:
                        # This has been aborded
                        compiling = False
                        packages_count = 1
                        current_package = False
                    
            # Do we got something ?
            #if collect['completed']:
            #    keep_running = True
            if incompleted:
                if collect['completed'] and collect['incompleted']:
                    keep_running = False
                elif collect['completed'] or collect['incompleted']:
                    # We enable incompleted but we have a completed update 
                    # so it's better :)
                    keep_running = False
                else:
                    # That mean we have nothing ;)
                    if self._keep_collecting(count, ['last world update', 
                                'have never been update using \'world\' update schema...']):
                        keep_running = True
                        count = count + 1
                    else:
                        return False
            else:
                if collect['completed']:
                    keep_running = False
                else:
                    if self._keep_collecting(count, ['last world update', 
                                 'have never been update using \'world\' update schema...']):
                        keep_running = True
                        count = count + 1
                    else:
                        return False
                    
        #### TO REMOVE - testing only
        #if collect['completed']:
            #print('Found completed update world')
            #for listing in collect['completed']:
                #start = time.ctime(int(listing['start']))
                #stop = time.ctime(int(listing['stop']))
                #npackages = listing['packages']
                #print(f'Found: {start}, {stop}, packages : {npackages}')
        #if collect['incompleted']:
            #print('Found incompleted update world')
            #for listing in collect['incompleted']:
                #start = time.ctime(int(listing['start']))
                #stop = time.ctime(int(listing['stop']))
                #npackages = listing['packages']
                #failed = listing['failed']
                #print(f'Found: {start}, {stop}, packages : {npackages}, failed : {failed}')
                
        # So now compare and get the highest timestamp from each list
        tocompare = [ ]
        for target in 'completed', 'incompleted':
            if collect[target]:
                # This this the start timestamp
                latest_timestamp = collect[target][0]['start']
                latest_sublist = collect[target][0]
                for sublist in collect[target]:
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
                self.log.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                        .format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['packages']))
            elif latest_sublist['state'] == 'incompleted':
                self.log.debug('Recording incompleted, start: {0}, stop: {1}, packages: {2}, failed at: {3}'
                        .format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['packages'], latest_sublist['failed']))
            return latest_sublist
        else:
            self.log.error('Failed to found latest world update informations.')
            return False           
        
        
    def getlog(self, lastlines, bsize=2048):
        """Get last n lines from emerge.log file
        https://stackoverflow.com/a/12295054/11869956"""
        # get newlines type, open in universal mode to find it
        try:
            with pathlib.Path(self.emergelog).open('rU') as mylog:
                if not mylog.readline():
                    return  # empty, no point
                sep = mylog.newlines  # After reading a line, python gives us this
            assert isinstance(sep, str), 'multiple newline types found, aborting'

            # find a suitable seek position in binary mode
            with pathlib.Path(self.emergelog).open('rb') as mylog:
                mylog.seek(0, os.SEEK_END)
                linecount = 0
                pos = 0

                while linecount <= lastlines + 1:
                    # read at least n lines + 1 more; we need to skip a partial line later on
                    try:
                        mylog.seek(-bsize, os.SEEK_CUR)           # go backwards
                        linecount += mylog.read(bsize).count(sep.encode()) # count newlines
                        mylog.seek(-bsize, os.SEEK_CUR)           # go back again
                    except (IOError, OSError) as error:
                        if error.errno == errno.EINVAL:
                            # Attempted to seek past the start, can't go further
                            bsize = mylog.tell()
                            mylog.seek(0, os.SEEK_SET)
                            pos = 0
                            linecount += mylog.read(bsize).count(sep.encode())
                            break
                        raise # Some other I/O exception, re-raise
                    pos = mylog.tell()

            # Re-open in text mode
            with pathlib.Path(self.emergelog).open('r') as mylog:
                mylog.seek(pos, os.SEEK_SET)  # our file position from above

                for line in mylog:
                    # We've located n lines *or more*, so skip if needed
                    if linecount > lastlines:
                        linecount -= 1
                        continue
                    # The rest we yield
                    yield line.rstrip()
        except (OSError, IOError) as error:
            self.log.critical('Error while getting informations from emerge.log file.')
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.log.critical(f'Daemon is intended to be run as sudo/root.')
            else:
                self.log.critical(f'Got: \'{error}\'.')
            self.log.critical('Exiting with error \'1\'.')
            sys.exit(1)
    
    def _keep_collecting(self, count, message):
        """Restart collecting if nothing has been found."""
        ### TODO : Total line !
        if  count < 5:
            self.log.debug(f'After {count} run: couldn\'t found {message[0]} timestamp.')
            self.lastlines = self.lastlines + 1000
            self.log.debug('Restarting with an bigger increment (+1000 lines each pass)...')
        elif count >= 5 and count < 10:
            self.log.debug(f'After {count} run, {message[0]} timestamp still not found...')
            self.log.debug('Restarting with an bigger increment (+3000 lines each pass)...')
            self.lastlines = self.lastlines + 3000
        elif count >= 10 and count < 15:
            self.log.debug(f'After {count} run, {message[0]} timestamp not found !')
            self.log.debug('Restarting with an bigger increment (+6000 lines each pass)...')
            self.log.debug(f'{self.aborded} pass left before abording...')
            self.aborded = self.aborded - 1
            self.lastlines = self.lastlines + 6000
        elif count > 15:
            self.log.error(f'After 15 pass and more than 40 000 lines read, couldn\'t find {message[0]} timestamp.')
            self.log.error(f'Look like the system {message[1]}')
            return False
        return True




def world_update_inprogress(log):
    """Check if world update is in progress
    @return: True or False
    Adapt from https://stackoverflow.com/a/31997847/11869956"""
    
    # TODO: system as well 
    # psutil module is slower then this.
    
    pids_only = re.compile(r'^\d+$')
    world = re.compile(r'^.*emerge.*\sworld\s.*$')
    pretend = re.compile(r'.*emerge.*\s-\w*p\w*\s.*|.*emerge.*\s--pretend\s.*')
    inprogress = False

    pids = [ ]
    for dirname in os.listdir('/proc'):
        if pids_only.match(dirname):
            try:
                with pathlib.Path('/proc/{0}/cmdline'.format(dirname)).open('rb') as myfd:
                    content = myfd.read().decode().split('\x00')
            # IOError exception when pid as finish between getting the dir list and open it each
            except IOError:
                continue
            except Exception as exc:
                log.error(f'Got unexcept error: {exc}')
                # TODO: Exit or not ?
                continue
            if world.match(' '.join(content)):
                #  Don't match any -p or --pretend opts
                if not pretend.match(' '.join(content)):
                    inprogress = True

    if inprogress:
        # TODO
        log.debug('World update in progress')
        return True
    else:
        # TODO
        log.debug('World update is not in progress')
        return False

