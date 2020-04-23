#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Starting : 2019-08-08

# This is a SYnc UPdate POrtage Daemon
# Copyright © Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import sys
import os
import argparse
import pathlib
import time
import re
import errno
import asyncio
import threading

from portagedbus import PortageDbus
from gitdbus import GitDbus
from gitmanager import check_git_dir
from gitmanager import GitWatcher
from portagemanager import EmergeLogWatcher
from logger import MainLoggingHandler
from logger import RedirectFdToLogger
from argsparser import DaemonParserHandler
from utils import StateInfo

# To remimber : http://stackoverflow.com/a/11887885
# TODO : enable or disable dbus bindings. So this should only be load if dbus is enable
# If dbus is disable (default is enable) then the user should be warn that it won't get any output
# it has to get info from state file
# TODO : exit gracefully 
# TODO : debug log level ! 
# TODO TODO : what if no internet connexion ? analyse return code for emerge --sync 
#             if no connexion then retry every N seconds (this could be decrease)

try:
    from gi.repository import GLib
    from pydbus import SystemBus # Changing to SystemBus (when run as root/sudo)
    # TODO: writing Exception like that in all program
except Exception as exc:
    print(f'Error: unexcept error while loading dbus bindings: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)

__version__ = "dev"
name = 'syuppod'  

pathdir = {
    'basedir'       :   '/var/lib/' + name,
    'logdir'        :   '/var/log/' + name,
    'emergelog'     :   '/var/log/emerge.log',
    'debuglog'      :   '/var/log/' + name + '/debug.log', # TEST changing
    'fdlog'         :   '/var/log/' + name + '/stderr.log', 
    'statelog'      :   '/var/lib/' + name + '/state.info', #'state.info',    #
    'gitlog'        :   '/var/log/' + name + '/git.log', #'git.log',  #      
    # TODO TODO TODO : add a check to see if user which run the program have enough right to perform all this operations
    'synclog'       :   '/var/log/' + name + '/sync.log', #'sync.log',       #
    'pretendlog'    :   '/var/log/' + name + '/pretend.log' #'pretend.log'     #
    
}

class MainDaemon(threading.Thread):
    def __init__(self, manager, watcher, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manager = manager
        self.watcher = watcher
        # Init asyncio loop
        self.scheduler = asyncio.new_event_loop()
    
    def run(self):
        logger.info('Start up completed.')
        while True:
            ### Portage stuff
            # Ok now just get sync timestamp or world pretend only 
            # if the emerge log has been close_write AND if there was an sync / update / both
            # in progress
            # TEST
            if self.watcher['portage'].refresh_sync:
                self.manager['portage'].check_sync()
                self.watcher['portage'].refresh_sync_done = True
            if self.manager['portage'].world['status'] == 'running' \
               and self.watcher['portage'].update_inprogress_world:
                # pretend running and world is running as well so call cancel
                self.manager['portage'].world['cancel'] = True
            if self.watcher['portage'].refresh_world \
               and not self.watcher['portage'].update_inprogress_world:
                # Call get_last_world so we can know if world has been update and it will call pretend
                self.manager['portage'].get_last_world_update()
                self.watcher['portage'].refresh_world_done = True
            if not self.watcher['portage'].update_inprogress_sync \
               and not self.watcher['portage'].update_inprogress_world \
               and self.manager['portage'].world['status'] == 'waiting' \
               and self.manager['portage'].world['cancelled']:
                # This is the case where we want to call pretend, there is not sync and world in progress
                # and pretend is waiting and it was cancelled so recall pretend :p
                logger.warning('Recalling the package(s) update\'s search as it was cancelled.')
                self.manager['portage'].world['pretend'] = True
                self.manager['portage'].world['cancelled'] = False
            if self.manager['portage'].world['status'] == 'finished':
                # Every thing is OK: pretend was wanted, has been called, finished well
                self.manager['portage'].world['status'] == 'waiting'
            # Also check portage package update depending on close_write
            # don't call if sync is in progress
            if self.watcher['portage'].refresh_package_search \
               and self.manager['portage'].portage['remain'] <= 0 \
               and not self.watcher['portage'].update_inprogress_sync:
                # This will be call every close_write but class EmergeLogWatcher has
                # 30s timer - this mean it won't call less than every 30s ;)
                self.manager['portage'].available_portage_update()
                self.watcher['portage'].refresh_package_search_done = True
            self.manager['portage'].portage['remain'] -= 1    
            # Regular sync
            if self.manager['portage'].sync['remain'] <= 0 and not self.manager['portage'].sync['status'] \
               and not self.watcher['portage'].update_inprogress_sync:
                # recompute time remain
                if self.manager['portage'].check_sync(recompute=True):
                    # sync not blocking using asyncio and thread 
                    # this is for python 3.5+ / None -> default ThreadPoolExecutor 
                    # where max_workers = n processors * 5
                    # TODO FIXME should we need all ?
                    logger.debug('Running dosync()')
                    self.scheduler.run_in_executor(None, self.manager['portage'].dosync, ) # -> ', )' = No args
            self.manager['portage'].sync['remain'] -= 1  # Should be 1 second or almost ;)
            self.manager['portage'].sync['elapsed'] += 1
            # Run pretend_world() if authorized 
            # Leave other check: is sync running ? is pretend already running ? is world update is running ?
            # to portagedbus module so it can reply to client
            # TEST Disable pretend_world() if sync is in progress other wise will run twice
            # Better to go with watcher over manager because it could be an external sync which will not be detected
            # by manager
            if self.manager['portage'].world['pretend'] and not self.watcher['portage'].update_inprogress_sync:
                if self.manager['portage'].world['forced']:
                    logger.warning('Forcing pretend world as requested by dbus client.')
                    self.manager['portage'].world['forced'] = False
                # Making async and non-blocking
                self.scheduler.run_in_executor(None, self.manager['portage'].pretend_world, ) # -> ', )' = same here
            
            ### Git stuff
            if self.manager['git'].enable:
                # TEST now watcher['git'] will handle update call depending on condition 
                # TEST Only update every 30s 
                if self.manager['git'].update:
                    # pull has been run, request refresh 
                    if self.watcher['git'].refresh_git_pull and not self.manager['git'].pull['status'] \
                    and not self.watcher['git'].pull_inprogress:
                        logger.debug('Got refresh request for git pull.')
                        # TEST Don't recompute here
                        self.manager['git'].pull['recompute'] = False
                        self.manager['git'].check_pull()
                        self.manager['git'].get_all_kernel()
                        self.manager['git'].get_branch('remote')
                        self.watcher['git'].refresh_git_pull_done = True
                        self.manager['git'].update = False
                    # Other git related request
                    if self.watcher['git'].refresh_git:
                        logger.debug('Got refresh request for git.')
                        self.manager['git'].get_branch('local')
                        self.manager['git'].get_available_update('branch')
                        # Other wise let's refresh_modules handle this
                        if not self.watcher['git'].refresh_modules:
                            self.manager['git'].get_available_update('kernel')
                        self.watcher['git'].refresh_git_done = True
                        self.manager['git'].update = False
                    # For '/lib/modules/' related request (installed kernel)
                    if self.watcher['git'].refresh_modules:
                        logger.debug('Got refresh request on modules.')
                        if self.watcher['git'].modules_create:
                            logger.debug('Found created: {0}'.format(' '.join(self.watcher['git'].modules_create)))
                        if self.watcher['git'].modules_delete:
                            logger.debug('Found deleted: {0}'.format(' '.join(self.watcher['git'].modules_delete)))
                        # Any way pass every thing to update_installed_kernel()
                        self.manager['git'].update_installed_kernel(deleted=self.watcher['git'].modules_delete,
                                                                    added=self.watcher['git'].modules_create)
                        self.watcher['git'].refresh_modules_done = True
                        self.manager['git'].update = False
                else:
                    if self.manager['git'].remain <= 0:
                        self.manager['git'].remain = 30
                        self.manager['git'].update = True
                    self.manager['git'].remain -= 1
                # pull
                if self.manager['git'].pull['remain'] <= 0 and not self.manager['git'].pull['status'] \
                   and not self.watcher['git'].pull_inprogress:
                    # TEST recompute here
                    self.manager['git'].pull['recompute'] = True
                    # Is an external git command in progress ? / recompute remain / bypass if network problem
                    if self.manager['git'].check_pull():
                        # Pull async and non blocking 
                        self.scheduler.run_in_executor(None, self.manager['git'].dopull, ) # -> ', )' = same here
                self.manager['git'].pull['remain'] -= 1
                self.manager['git'].pull['elapsed'] += 1
                
            time.sleep(1)




def main():
    """Main init"""
    
    # Check or create basedir and logdir directories
    for directory in 'basedir', 'logdir':
        if not pathlib.Path(pathdir[directory]).is_dir():
            try:
                pathlib.Path(pathdir[directory]).mkdir()
            except OSError as error:
                if error.errno == errno.EPERM or error.errno == errno.EACCES:
                    logger.critical(f'Got error while making directory: \'{error.strerror}: {error.filename}\'.')
                    logger.critical(f'Daemon is intended to be run as sudo/root.')
                    sys.exit(1)
                else:
                    logger.critical(f'Got unexcept error while making directory: \'{error}\'.')
                    sys.exit(1)
       
    # Init StateInfo
    mystateinfo = StateInfo(pathdir, runlevel, logger.level)
    
    # Check state file
    mystateinfo.config()
        
    # Init dbus service
    dbusloop = GLib.MainLoop()
    dbus_session = SystemBus()
    
    # Init manager
    manager = { }
    
    # Init watcher
    watcher = { }
    
    # Init portagemanager
    myportmanager = PortageDbus(args.sync, pathdir, runlevel, logger.level)
    # Init Emerge log watcher
    myportwatcher = EmergeLogWatcher(pathdir, runlevel, logger.level, myportmanager.sync['repos']['msg'], 
                             name='Emerge Log Watcher Daemon', daemon=True)
    
    # Check sync
    myportmanager.check_sync(init_run=True, recompute=True)
    # Get last portage package
    # Better first call here because this won't be call before EmergeLogWatcher detected close_write
    myportmanager.available_portage_update()
    # Same here: Check if global update has been run 
    myportmanager.get_last_world_update()
               
    if args.git:
        logger.debug('Git kernel tracking has been enable.')
        
        # Init gitmanager object through GitDbus class
        mygitmanager = GitDbus(enable=True, interval=args.pull, repo=args.repo, pathdir=pathdir, runlevel=runlevel,
                               loglevel=logger.level)
        # Init git watcher
        mygitwatcher = GitWatcher(pathdir, runlevel, logger.level, args.repo, name='Git Watcher Daemon',
                       daemon=True)
               
        # Get running kernel
        mygitmanager.get_running_kernel()
        
        # Update all attributes
        # Recompute enable
        mygitmanager.pull['recompute'] = True
        mygitmanager.check_pull(init_run=True) # We need this to print logger.info only one time
        mygitmanager.get_installed_kernel()
        mygitmanager.get_all_kernel()
        mygitmanager.get_available_update('kernel')
        mygitmanager.get_branch('all')
        mygitmanager.get_available_update('branch')       
    else:
        mygitmanager = GitDbus(enable=False, interval=args.pull, repo=args.repo, pathdir=pathdir, runlevel=runlevel,
                               loglevel=logger.level)
        mygitwatcher = False
    
    # Adding objects to manager
    manager['git'] = mygitmanager
    manager['portage'] = myportmanager
    
    # Adding objects to watcher
    watcher['portage'] = myportwatcher
    watcher['git'] = mygitwatcher
    
    # Adding dbus publishers
    dbus_session.publish('net.syuppod.Manager.Git', mygitmanager)
    dbus_session.publish('net.syuppod.Manager.Portage', myportmanager)
        
    # Init thread
    daemon_thread = MainDaemon(manager, watcher, name='Main Daemon Thread', daemon=True)
    
    # Start all threads and dbus
    watcher['portage'].start()
    if watcher['git']:
        watcher['git'].start()
    daemon_thread.start()
    dbusloop.run()
    
    daemon_thread.join()
    watcher['portage'].join()
    if watcher['git']:
        watcher['git'].join()
       
    
if __name__ == '__main__':

    # Parse arguments
    myargsparser = DaemonParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
        
    # Creating log
    mainlog = MainLoggingHandler('::main::', pathdir['debuglog'], pathdir['fdlog'])
    
    if sys.stdout.isatty():
        logger = mainlog.tty_run()      # create logger tty_run()
        logger.setLevel(mainlog.logging.INFO)
        runlevel = 'tty_run'
        display_init_tty = ''
        # This is not working with konsole (kde)
        print('\33]0; {0} - {1}  \a'.format(name, __version__), end='', flush=True)
    else:
        logger = mainlog.init_run()     # create logger init_run()
        logger.setLevel(mainlog.logging.INFO)
        runlevel = 'init_run'
        display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
        # Redirect stderr to log 
        # For the moment maybe stdout as well but nothing should be print to...
        # This is NOT good if there is error before log(ger) is initialized...
        fd2 = RedirectFdToLogger(logger)
        sys.stderr = fd2
       
    if args.debug and args.quiet or args.quiet and args.debug:
        logger.info('Both debug and quiet opts has been enable, falling back to log level info.')
        logger.setLevel(mainlog.logging.INFO)
    elif args.debug:
        logger.setLevel(mainlog.logging.DEBUG)
        logger.info(f'Debug has been enable. {display_init_tty}')
        logger.debug('Message are from this form \'::module::class::method:: msg\'.')
    elif args.quiet:
        logger.setLevel(mainlog.logging.ERROR)
    
    if sys.stdout.isatty():
        logger.info('Interactive mode detected, all logs go to terminal.')
    
    # run MAIN
    main()
    
    
    
    


