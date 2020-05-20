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
from portagemanager import EmergeLogWatcher
from lib.logger import MainLoggingHandler
from lib.logger import RedirectFdToLogger
from argsparser import DaemonParserHandler

# TODO TODO TODO don't run as root ! investigate !
# TODO : exit gracefully 
# TODO : debug log level !
# TODO threading we cannot share object attribute 
#       or it will no be update ?!?

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
    'prog_version'  :   __version__,
    'basedir'       :   '/var/lib/' + prog_name,
    'logdir'        :   '/var/log/' + prog_name,
    'emergelog'     :   '/var/log/emerge.log',
    'debuglog'      :   '/var/log/' + prog_name + '/debug.log',
    'fdlog'         :   '/var/log/' + prog_name + '/stderr.log', 
    'statelog'      :   '/var/lib/' + prog_name + '/state.info',
    # TODO TODO TODO : add a check to see if user which run the program 
    # have enough right to perform all this operations
    'synclog'       :   '/var/log/' + prog_name + '/sync.log',
    'pretendlog'    :   '/var/log/' + prog_name + '/pretend.log'    
}

class MainDaemon(threading.Thread):
    def __init__(self, myport, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.myport = myport
        # Init asyncio loop
        self.scheduler = asyncio.new_event_loop()
    
    def run(self):
        logger.info('Start up completed.')
        while True:
            ### Portage stuff
            # Check pending requests for 'sync'
            # TEST workaround - but it have more latency 
            if self.myport['watcher'].tasks['world']['inprogress']:
                self.myport['manager'].world_state = True
            else:
                self.myport['manager'].world_state = False
            if self.myport['watcher'].tasks['sync']['inprogress']:
                self.myport['manager'].sync_state = True
            else:
                self.myport['manager'].sync_state = False
            ### End workaround
            # get sync timestamp or world pretend only if emergelog have been close_write 
            # AND if there was an sync / update / both in progress.
            if self.myport['watcher'].tasks['sync']['requests']['pending'] \
               and not self.myport['watcher'].tasks['sync']['inprogress']:
                # Take a copy so you can immediatly send back what you take and 
                # still process it here
                sync_requests = self.myport['watcher'].tasks['sync']['requests']['pending'].copy()
                msg = ''
                if len(sync_requests) > 1:
                    msg = 's'
                logger.debug(f'Got refresh request{msg}'
                             + ' (id{0}={1})'.format(msg, '|'.join(sync_requests)) 
                             + ' for sync informations.')
                # Send reply
                self.myport['watcher'].tasks['sync']['requests']['completed'] = sync_requests[-1]
                self.myport['manager'].check_sync()
            # pretend running and world is running as well so call cancel
            if self.myport['manager'].world['status'] == 'running' \
               and self.myport['watcher'].tasks['world']['inprogress']:
                self.myport['manager'].world['cancel'] = True
            # Check pending requests for 'world' <=> global update
            if self.myport['watcher'].tasks['world']['requests']['pending'] \
               and not self.myport['watcher'].tasks['world']['inprogress']:
                world_requests = self.myport['watcher'].tasks['world']['requests']['pending'].copy()
                msg = ''
                if len(world_requests) > 1:
                    msg = 's'
                logger.debug(f'Got refresh request{msg}'
                             + ' (id{0}={1})'.format(msg, '|'.join(world_requests)) 
                             + ' for global update informations.')
                # Send reply
                self.myport['watcher'].tasks['world']['requests']['completed'] = world_requests[-1]
                # Call get_last_world so we can know if world has been update and it will call pretend
                self.myport['manager'].get_last_world_update()
            # This is the case where we want to call pretend, there is not sync and world in progress
            # and pretend is waiting and it was cancelled so recall pretend :p
            if not self.myport['watcher'].tasks['sync']['inprogress'] \
               and not self.myport['watcher'].tasks['world']['inprogress'] \
               and self.myport['manager'].world['status'] == 'waiting' \
               and self.myport['manager'].world['cancelled']:
                logger.warning('Recalling package(s) update\'s search as it was cancelled.')
                self.myport['manager'].world['pretend'] = True
                self.myport['manager'].world['cancelled'] = False
            # Every thing is OK: pretend was wanted, has been called and is completed 
            if self.myport['manager'].world['status'] == 'completed':
                # TEST Wait between two pretend_world() run 
                if self.myport['manager'].world['remain'] <= 0:
                    logger.debug('Changing state for world from \'completed\' to \'waiting\'.')
                    logger.debug('pretend_world() can be call again.')
                    self.myport['manager'].world['remain'] = self.myport['manager'].world['interval']
                    self.myport['manager'].world['status'] = 'waiting'
                else:
                    self.myport['manager'].world['remain'] -= 1
            # Check pending requests for portage package update
            # don't call if sync/world/both is in progress
            if self.myport['watcher'].tasks['package']['requests']['pending'] \
               and self.myport['manager'].portage['remain'] <= 0: # \
               #and not self.myport['watcher'].tasks['sync']['inprogress'] \
               #and not self.myport['watcher'].tasks['world']['inprogress']:
                package_requests = self.myport['watcher'].tasks['package']['requests']['pending'].copy()
                msg = ''
                if len(package_requests) > 1:
                    msg = 's'
                logger.debug(f'Got refresh request{msg}'
                             + ' (id{0}={1})'.format(msg, '|'.join(package_requests)) 
                             + ' for portage\'s package update informations.')
                # Send reply
                self.myport['watcher'].tasks['package']['requests']['completed'] = package_requests[-1] 
                # Set timer to 30s between two (group) of request  
                self.myport['manager'].available_portage_update()
                self.myport['watcher'].refresh_package_search_done = True
            self.myport['manager'].portage['remain'] -= 1    
            # Regular sync
            if self.myport['manager'].sync['remain'] <= 0 and not self.myport['manager'].sync['status'] \
               and not self.myport['watcher'].tasks['sync']['inprogress']:
                # recompute time remain
                if self.myport['manager'].check_sync(recompute=True):
                    # sync not blocking using asyncio and thread 
                    # this is for python 3.5+ / None -> default ThreadPoolExecutor 
                    # where max_workers = n processors * 5
                    # TODO FIXME should we need all ?
                    logger.debug('Running dosync()')
                    self.scheduler.run_in_executor(None, self.myport['manager'].dosync, ) # -> ', )' = No args
            self.myport['manager'].sync['remain'] -= 1  # Should be 1 second or almost ;)
            self.myport['manager'].sync['elapsed'] += 1
            # Run pretend_world() if authorized 
            # Leave other check (sync running ? pretend already running ? world update running ?)
            # to portagedbus module so it can reply to client.
            # TEST Disable pretend_world() if sync is in progress other wise will run twice.
            # Better to go with watcher over manager because it could be an external sync which will not be detected
            # by manager
            # Don't run pretend if world / sync in progress or if not status == 'waiting'
            if self.myport['manager'].world['pretend'] \
               and self.myport['manager'].world['status'] == 'waiting' \
               and not self.myport['watcher'].tasks['sync']['inprogress'] \
               and not self.myport['watcher'].tasks['world']['inprogress']:
                if self.myport['manager'].world['forced']:
                    logger.warning('Forcing pretend world as requested by dbus client.')
                    self.myport['manager'].world['forced'] = False
                logger.debug('Running pretend_world()')
                # Making async and non-blocking
                self.scheduler.run_in_executor(None, self.myport['manager'].pretend_world, ) # -> ', )' = same here
            
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
                    logger.critical('Daemon is intended to be run as sudo/root.')
                    sys.exit(1)
                else:
                    logger.critical(f'Got unexcept error while making directory: \'{error}\'.')
                    sys.exit(1)
                    
    # Init dbus service
    dbusloop = GLib.MainLoop()
    dbus_session = SystemBus()
    
    # Init Emerge log watcher first because we need status of sync and world process 
    # this is a workaround because EmergeLogWatcher need sync['repos']['msg']
    # so init as NOT WORKING :
    myportwatcher = EmergeLogWatcher(pathdir, runlevel, logger.level, 'repo', 
                             name='Emerge Log Watcher Daemon', daemon=True)
    
    # Init portagemanager
    # BUG sharing object's attribute over multiple thread is NOT working ?
    myportmanager = PortageDbus(interval=args.sync, pathdir=pathdir, runlevel=runlevel, loglevel=logger.level)
    # TEST workaround 
    # Ok So this is NOT working (sharing object attribute over multiple thread is NOT working)
    myportwatcher.sync_msg = myportmanager.sync['repos']['msg']
    
    # Check sync
    myportmanager.check_sync(init_run=True, recompute=True)
    # Get last portage package
    # Better first call here because this won't be call before EmergeLogWatcher detected close_write
    myportmanager.available_portage_update()
    # Same here: Check if global update has been run 
    myportmanager.get_last_world_update()
    
    # Adding objet to manager
    myport = { }
    myport['manager'] = myportmanager
    
    # Adding object to watcher
    myport['watcher'] = myportwatcher
    
    # Adding dbus publishers
    dbus_session.publish('net.syuppod.Manager.Portage', myportmanager)
        
    # Init thread
    daemon_thread = MainDaemon(myport, name='Main Daemon Thread', daemon=True)
    
    # Start all threads and dbus thread
    myport['watcher'].start()
    daemon_thread.start()
    dbusloop.run()
    
    daemon_thread.join()
    myport['watcher'].join()
           
    
if __name__ == '__main__':
    
    # Parse arguments
    myargsparser = DaemonParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
        
    # Creating log
    mainlog = MainLoggingHandler('::main::', pathdir['prog_name'], pathdir['debuglog'], pathdir['fdlog'])
    
    if sys.stdout.isatty() and not args.fakeinit:
        logger = mainlog.tty_run()      # create logger tty_run()
        logger.setLevel(mainlog.logging.INFO)
        runlevel = 'tty_run'
        display_init_tty = ''
        # This is not working with konsole (kde)
        # TODO
        print('\33]0; {0} - {1}  \a'.format(prog_name, __version__), end='', flush=True)
    else:
        if args.fakeinit:
            print('Running fake init.', file=sys.stderr)
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
        
        #print('This is a test', file=sys.stderr)
       
    if args.debug and args.quiet or args.quiet and args.debug:
        logger.info('Both debug and quiet opts has been enable, falling back to log level info.')
        logger.setLevel(mainlog.logging.INFO)
    elif args.debug:
        logger.setLevel(mainlog.logging.DEBUG)
        logger.info(f'Debug has been enable. {display_init_tty}')
        logger.debug('Message are from this form \'::module::class::method:: msg\'.')
    elif args.quiet:
        logger.setLevel(mainlog.logging.ERROR)
    
    if sys.stdout.isatty() and not args.fakeinit:
        logger.info('Interactive mode detected, all logs go to terminal.')
    
    # run MAIN
    main()
    
    
    
    


