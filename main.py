#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Starting : 2019-08-08

# This is a SYnc UPdate POrtage Daemon
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
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

# TODO TODO TODO don't run as root ! investigate !
# TODO : exit gracefully 
# TODO : debug log level ! 

try:
    from gi.repository import GLib
    from pydbus import SystemBus
except Exception as exc:
    print(f'Error: unexcept error while loading dbus bindings: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)

__version__ = "dev"
prog_name = 'syuppod'  

pathdir = {
    'prog_name'     :   prog_name,
    'basedir'       :   '/var/lib/' + prog_name,
    'logdir'        :   '/var/log/' + prog_name,
    'emergelog'     :   '/var/log/emerge.log',
    'debuglog'      :   '/var/log/' + prog_name + '/debug.log',
    'fdlog'         :   '/var/log/' + prog_name + '/stderr.log', 
    'statelog'      :   '/var/lib/' + prog_name + '/state.info',
    'gitlog'        :   '/var/log/' + prog_name + '/git.log', 
    # TODO TODO TODO : add a check to see if user which run the program 
    # have enough right to perform all this operations
    'synclog'       :   '/var/log/' + prog_name + '/sync.log',
    'pretendlog'    :   '/var/log/' + prog_name + '/pretend.log'    
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
            # get sync timestamp or world pretend only if emergelog have been close_write 
            # AND if there was an sync / update / both in progress.
            # Check pending requests for 'sync'
            if self.watcher['portage'].tasks['sync']['requests']['pending'] \
               and not self.watcher['portage'].tasks['sync']['inprogress']:
                # Take a copy so you can immediatly send back what you take and 
                # still process it here
                sync_requests = self.watcher['portage'].tasks['sync']['requests']['pending'].copy()
                msg = ''
                if len(sync_requests) > 1:
                    msg = 's'
                logger.debug(f'Got refresh request{msg}'
                             + ' (id{0}={1})'.format(msg, '|'.join(sync_requests)) 
                             + ' for sync informations.')
                # Send reply
                self.watcher['portage'].tasks['sync']['requests']['completed'] = sync_requests[-1]
                self.manager['portage'].check_sync()
            # pretend running and world is running as well so call cancel
            if self.manager['portage'].world['status'] == 'running' \
               and self.watcher['portage'].tasks['world']['inprogress']:
                self.manager['portage'].world['cancel'] = True
            # Check pending requests for 'world' <=> global update
            if self.watcher['portage'].tasks['world']['requests']['pending'] \
               and not self.watcher['portage'].tasks['world']['inprogress']:
                world_requests = self.watcher['portage'].tasks['world']['requests']['pending'].copy()
                msg = ''
                if len(world_requests) > 1:
                    msg = 's'
                logger.debug(f'Got refresh request{msg}'
                             + ' (id{0}={1})'.format(msg, '|'.join(world_requests)) 
                             + ' for global update informations.')
                # Send reply
                self.watcher['portage'].tasks['world']['requests']['completed'] = world_requests[-1]
                # Call get_last_world so we can know if world has been update and it will call pretend
                self.manager['portage'].get_last_world_update()
            # This is the case where we want to call pretend, there is not sync and world in progress
            # and pretend is waiting and it was cancelled so recall pretend :p
            if not self.watcher['portage'].tasks['sync']['inprogress'] \
               and not self.watcher['portage'].tasks['world']['inprogress'] \
               and self.manager['portage'].world['status'] == 'waiting' \
               and self.manager['portage'].world['cancelled']:
                logger.warning('Recalling package(s) update\'s search as it was cancelled.')
                self.manager['portage'].world['pretend'] = True
                self.manager['portage'].world['cancelled'] = False
            # Every thing is OK: pretend was wanted, has been called and is completed 
            if self.manager['portage'].world['status'] == 'completed':
                # TEST Wait between two pretend_world() run 
                if self.manager['portage'].world['remain'] <= 0:
                    logger.debug('Changing state for world from \'completed\' to \'waiting\'.')
                    logger.debug('pretend_world() can be call again.')
                    self.manager['portage'].world['remain'] = self.manager['portage'].world['interval']
                    self.manager['portage'].world['status'] == 'waiting'
                self.manager['portage'].world['remain'] -= 1
            # Check pending requests for portage package update
            # don't call if sync/world/both is in progress
            if self.watcher['portage'].tasks['package']['requests']['pending'] \
               and self.manager['portage'].portage['remain'] <= 0: # \
               #and not self.watcher['portage'].tasks['sync']['inprogress'] \
               #and not self.watcher['portage'].tasks['world']['inprogress']:
                package_requests = self.watcher['portage'].tasks['package']['requests']['pending'].copy()
                msg = ''
                if len(package_requests) > 1:
                    msg = 's'
                logger.debug(f'Got refresh request{msg}'
                             + ' (id{0}={1})'.format(msg, '|'.join(package_requests)) 
                             + ' for portage\'s package update informations.')
                # Send reply
                self.watcher['portage'].tasks['package']['requests']['completed'] = package_requests[-1] 
                # Set timer to 30s between two (group) of request  
                self.manager['portage'].available_portage_update()
                self.watcher['portage'].refresh_package_search_done = True
            self.manager['portage'].portage['remain'] -= 1    
            # Regular sync
            if self.manager['portage'].sync['remain'] <= 0 and not self.manager['portage'].sync['status'] \
               and not self.watcher['portage'].tasks['sync']['inprogress']:
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
            # Leave other check (sync running ? pretend already running ? world update running ?)
            # to portagedbus module so it can reply to client.
            # TEST Disable pretend_world() if sync is in progress other wise will run twice.
            # Better to go with watcher over manager because it could be an external sync which will not be detected
            # by manager
            # Don't run pretend if world / sync in progress or if not status == 'waiting'
            if self.manager['portage'].world['pretend'] \
               and self.manager['portage'].world['status'] == 'waiting' \
               and not self.watcher['portage'].tasks['sync']['inprogress'] \
               and not self.watcher['portage'].tasks['world']['inprogress']:
                if self.manager['portage'].world['forced']:
                    logger.warning('Forcing pretend world as requested by dbus client.')
                    self.manager['portage'].world['forced'] = False
                logger.debug('Running pretend_world()')
                # Making async and non-blocking
                self.scheduler.run_in_executor(None, self.manager['portage'].pretend_world, ) # -> ', )' = same here
            
            ### Git stuff
            if self.manager['git'].enable:
                # TEST now watcher['git'] will handle update call depending on condition 
                # TEST Only update every 30s 
                if self.manager['git'].update:
                    # pull have been run, request refresh 
                    if self.watcher['git'].tasks['pull']['requests']['pending'] \
                       and not self.manager['git'].pull['status'] \
                       and not self.watcher['git'].tasks['pull']['inprogress'] \
                       and not self.watcher['git'].repo_read:
                        # Wait until there is nothing more to read (so pack all the request together)
                        # TODO we could wait 10s before processing ? (so make sure every thing is packed)
                        # Any way this have to be more TEST-ed
                        # Ok enumerate request(s) on pull and save latest
                        # This will 'block' to the latest know request (know in main)
                        pull_requests = self.watcher['git'].tasks['pull']['requests']['pending'].copy()
                        msg = ''
                        if len(pull_requests) > 1:
                            msg = 's'
                        logger.debug(f'Got refresh request{msg}'
                                     + ' (id{0}={1})'.format(msg, '|'.join(pull_requests)) 
                                     + ' for git pull informations.')
                        # Immediatly send back latest request proceed so watcher can remove all the already proceed
                        # requests
                        self.watcher['git'].tasks['pull']['requests']['completed'] = pull_requests[-1]
                        # TEST Don't recompute here
                        self.manager['git'].pull['recompute'] = False
                        self.manager['git'].check_pull()
                        self.manager['git'].get_all_kernel()
                        self.manager['git'].get_branch('remote')
                        self.manager['git'].update = False
                    # Other git repo related request(s)
                    if self.watcher['git'].tasks['repo']['requests']['pending'] \
                       and not self.watcher['git'].repo_read:
                        # Same here as well
                        repo_requests = self.watcher['git'].tasks['repo']['requests']['pending'].copy()
                        msg = ''
                        if len(repo_requests) > 1:
                            msg = 's'
                        logger.debug(f'Got refresh request{msg}'
                                     + ' (id{0}={1})'.format(msg, '|'.join(repo_requests)) 
                                     + ' for git repo informations.')
                        # Same here send back latest request id (know here)
                        self.watcher['git'].tasks['repo']['requests']['completed'] = repo_requests[-1]
                        self.manager['git'].get_branch('local')
                        self.manager['git'].get_available_update('branch')
                        # Other wise let's modules related handle this
                        # by using update_installed_kernel()
                        if not self.watcher['git'].tasks['mod']['requests']['pending']:
                            self.manager['git'].get_available_update('kernel')
                        self.manager['git'].update = False
                    # For '/lib/modules/' related request (installed kernel)
                    if self.watcher['git'].tasks['mod']['requests']['pending'] \
                       and not self.watcher['git'].mod_read:
                        # Also here
                        mod_requests = self.watcher['git'].tasks['mod']['requests']['pending'].copy()
                        msg = ''
                        if len(mod_requests) > 1:
                            msg = 's'
                        logger.debug(f'Got refresh request{msg}'
                                     + ' (id{0}={1})'.format(msg, '|'.join(mod_requests)) 
                                     + ' for modules informations.')
                        if self.watcher['git'].tasks['mod']['created']:
                            logger.debug('Found created: {0}'.format(' '.join(
                                                             self.watcher['git'].tasks['mod']['created'])))
                        if self.watcher['git'].tasks['mod']['deleted']:
                            logger.debug('Found deleted: {0}'.format(' '.join(
                                                             self.watcher['git'].tasks['mod']['deleted'])))
                        # Any way pass every thing to update_installed_kernel()
                        self.manager['git'].update_installed_kernel(
                                                    deleted=self.watcher['git'].tasks['mod']['deleted'],
                                                    added=self.watcher['git'].tasks['mod']['created'])
                        # Wait until update_installed_kernel() otherwise watcher will erase 'deleted' and
                        # 'created'...
                        self.watcher['git'].tasks['mod']['requests']['completed'] = mod_requests[-1]
                        self.manager['git'].get_available_update('kernel')
                        self.manager['git'].update = False
                else:
                    if self.manager['git'].remain <= 0:
                        # TODO : lower  this to have more sensibility ?
                        self.manager['git'].remain = 30
                        self.manager['git'].update = True
                    self.manager['git'].remain -= 1
                # pull
                if self.manager['git'].pull['remain'] <= 0 and not self.manager['git'].pull['status'] \
                   and not self.watcher['git'].tasks['pull']['inprogress']:
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
    
    # Init Emerge log watcher first because we need status of sync and world process 
    # this is a workaround because EmergeLogWatcher need sync['repos']['msg']
    # so init as :
    myportwatcher = EmergeLogWatcher(pathdir, runlevel, logger.level, 'repo', 
                             name='Emerge Log Watcher Daemon', daemon=True)
    
    # Init portagemanager
    myportmanager = PortageDbus(sync_state=myportwatcher.tasks['sync']['inprogress'],
                                world_state=myportwatcher.tasks['sync']['inprogress'], interval=args.sync,
                                pathdir=pathdir, runlevel=runlevel, loglevel=logger.level)
    # TEST workaround 
    myportwatcher.sync_msg = myportmanager.sync['repos']['msg']
        
    # Check sync
    myportmanager.check_sync(init_run=True, recompute=True)
    # Get last portage package
    # Better first call here because this won't be call before EmergeLogWatcher detected close_write
    myportmanager.available_portage_update()
    # Same here: Check if global update has been run 
    myportmanager.get_last_world_update()
               
    if args.git:
        logger.debug('Git kernel tracking has been enable.')
        
        # Init git watcher first so we can get pull (external) running status
        mygitwatcher = GitWatcher(pathdir, runlevel, logger.level, args.repo, name='Git Watcher Daemon',
                       daemon=True)
        
        # Init gitmanager object through GitDbus class
        mygitmanager = GitDbus(enable=True, pull_state=mygitwatcher.tasks['pull']['inprogress'],
                               interval=args.pull, repo=args.repo, pathdir=pathdir, runlevel=runlevel,
                               loglevel=logger.level)
               
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
        # Init only logger TEST needed for logging process 
        mygitmanager = GitDbus(enable=False, pathdir=pathdir, runlevel=runlevel, loglevel=logger.level)
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
    mainlog = MainLoggingHandler('::main::', pathdir['prog_name'], pathdir['debuglog'], pathdir['fdlog'])
    
    if sys.stdout.isatty():
        logger = mainlog.tty_run()      # create logger tty_run()
        logger.setLevel(mainlog.logging.INFO)
        runlevel = 'tty_run'
        display_init_tty = ''
        # This is not working with konsole (kde)
        # TODO
        print('\33]0; {0} - {1}  \a'.format(prog_name, __version__), end='', flush=True)
    else:
        logger = mainlog.init_run()     # create logger init_run()
        logger.setLevel(mainlog.logging.INFO)
        runlevel = 'init_run'
        display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
        # TODO rewrite / change 
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
    
    
    
    


