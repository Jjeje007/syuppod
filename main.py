#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Starting : 2019-08-08

# SYnc UPdate POrtage Daemon - main
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

# TEST in progress: exit gracefully 
# TODO write GOOD english :p
# TODO : debug log level !
# TODO threading cannot share object attribute 
#       or it will not be update ?!?

__version__ = "dev"
prog_name = 'syuppod'
dbus_conf = 'syuppod-dbus.conf'
pathdir = {
    'prog_name'     :   prog_name,
    'prog_version'  :   __version__,
    'basedir'       :   '/var/lib/' + prog_name,
    'logdir'        :   '/var/log/' + prog_name,
    'emergelog'     :   '/var/log/emerge.log',
    'debuglog'      :   '/var/log/' + prog_name + '/debug.log',
    'fdlog'         :   '/var/log/' + prog_name + '/stderr.log', 
    'statelog'      :   '/var/lib/' + prog_name + '/state.info',
    'synclog'       :   '/var/log/' + prog_name + '/sync.log',
    'pretendlog'    :   '/var/log/' + prog_name + '/pretend.log'    
    }

import sys
import logging
# Custom level name share across all logger
logging.addLevelName(logging.CRITICAL, '[Crit ]')
logging.addLevelName(logging.ERROR,    '[Error]')
logging.addLevelName(logging.WARNING,  '[Warn ]')
logging.addLevelName(logging.INFO,     '[Info ]')
logging.addLevelName(logging.DEBUG,    '[Debug]')

import argparse
import re
import pathlib
import time
import errno
import asyncio
import threading
import signal
from getpass import getuser
from portagedbus import PortageDbus
from portagemanager import EmergeLogWatcher
from argsparser import DaemonParserHandler
from lib.logger import LogErrorFilter
from lib.logger import LogLevelFilter
from lib.logger import LogLevelFormatter
try:
    from gi.repository import GLib
    from pydbus import SystemBus
except Exception as exc:
    print(f'Error: unexcept error while loading dbus bindings: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)



class CatchExitSignal:
    """
    Catch SIGINT or SIGTERM signal and advise signal receive
    """
    def __init__(self):
        self.logger_name = f'::{__name__}::CatchExitSignal::'
        logger = logging.getLogger(f'{self.logger_name}init::')
        self.exit_now = False
        logger.debug('Watching signal SIGINT.')
        signal.signal(signal.SIGINT, self.exit_gracefully)
        logger.debug('Watching signal SIGTERM.')
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        logger = logging.getLogger(f'{self.logger_name}exit_gracefully::')
        logger.debug(f'Got signal: \'{signum}\' on stack frame: \'{frame}\'.')
        logger.info(f'Received signal \'{signum}\'...')
        self.exit_now = True



class MainDaemon(threading.Thread):
    """
    Main Daemon
    """
    def __init__(self, myport, *args, **kwargs):
        self.logger_name = f'::{__name__}::MainDaemonThread::'
        logger = logging.getLogger(f'{self.logger_name}init::')
        super().__init__(*args, **kwargs)
        self.myport = myport
        # Init asyncio loop
        self.scheduler = asyncio.new_event_loop()
        # Change log level of asyncio 
        # to be the same as RootLogger
        currentlevel = logger.getEffectiveLevel()
        logger.debug(f'Setting log level for asyncio to: {currentlevel}')
        logging.getLogger('asyncio').setLevel(currentlevel)
        # Catch signals
        self.mysignal = CatchExitSignal()
    
    def run(self):
        logger = logging.getLogger(f'{self.logger_name}run::')
        logger.info('Start up completed.')
        logger.debug('Main Daemon Thread started.')
        logflow = 10
        # LOOP start
        while not self.mysignal.exit_now:
            
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
                # Dont automatically recompute, let check_sync() make the decision
                self.myport['manager'].check_sync()
            
            # pretend running and world is running as well so call cancel
            if self.myport['manager'].pretend['status'] == 'running' \
               and self.myport['watcher'].tasks['world']['inprogress']:
                self.myport['manager'].pretend['cancel'] = True
            
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
               and self.myport['manager'].pretend['status'] == 'ready' \
               and self.myport['manager'].pretend['cancelled']:
                logger.warning('Recalling available packages updates search as it was cancelled.')
                self.myport['manager'].pretend['proceed'] = True
                self.myport['manager'].pretend['cancelled'] = False
            
            # Every thing is OK: pretend was wanted, has been called and is completed 
            if self.myport['manager'].pretend['status'] == 'completed':
                # Wait between two pretend_world() run 
                if self.myport['manager'].pretend['remain'] <= 0:
                    logger.debug('Changing state for pretend process from \'completed\' to \'waiting\'.')
                    logger.debug('pretend_world() can be call again.')
                    self.myport['manager'].pretend['remain'] = self.myport['manager'].pretend['interval']
                    self.myport['manager'].pretend['status'] = 'ready'
                else:
                    self.myport['manager'].pretend['remain'] -= 1
            
            # Check pending requests for portage package update
            # don't call if sync/world/both is in progress
            # remain is set in portagemanager, this will avoid call to often
            if self.myport['watcher'].tasks['package']['requests']['pending'] \
               and self.myport['manager'].portage['remain'] <= 0:
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
                # This is done in available_portage_update()
                self.myport['manager'].available_portage_update()
            self.myport['manager'].portage['remain'] -= 1    
            
            # Regular sync
            if self.myport['manager'].sync['remain'] <= 0 \
               and not self.myport['manager'].sync['status'] \
               and not self.myport['watcher'].tasks['sync']['inprogress']:
                # TEST avoid syncing when updating world or it could crash emerge:
                #  FileNotFoundError: [Errno 2] No such file or directory: 
                #   b'/var/db/repos/gentoo/net-misc/openssh/openssh-8.3_p1-r1.ebuild'
                if not self.myport['watcher'].tasks['world']['inprogress']:
                    logflow = 10
                    # recompute time remain
                    if self.myport['manager'].check_sync(recompute=True):
                        # sync not blocking using asyncio and thread 
                        # this is for python 3.5+ / None -> default ThreadPoolExecutor 
                        # where max_workers = n processors * 5
                        # TODO FIXME should we need all ?
                        logger.debug('Running dosync()')
                        self.scheduler.run_in_executor(None, self.myport['manager'].dosync, ) # -> ', )' = No args
                else:
                    # Avoid spamming every 1s debug log
                    if logflow <= 0:
                        logger.debug('Delaying call for check_sync() because world update is in progress.')
                        logflow = 10
                    logflow -= 1
            self.myport['manager'].sync['remain'] -= 1  # Should be 1 second or almost ;)
            self.myport['manager'].sync['elapsed'] += 1
            
            # Run pretend_world() if authorized 
            # Leave other check (sync running ? pretend already running ? world update running ?)
            # to portagedbus module so it can reply to client.
            # Disable pretend_world() if sync is in progress other wise will run twice.
            # Better to go with watcher over manager because it could be an external sync which will not be detected
            # by manager
            # Don't run pretend if world / sync in progress or if not status == 'ready'
            if self.myport['manager'].pretend['proceed'] \
               and self.myport['manager'].pretend['status'] == 'ready' \
               and not self.myport['watcher'].tasks['sync']['inprogress'] \
               and not self.myport['watcher'].tasks['world']['inprogress']:
                if self.myport['manager'].pretend['forced']:
                    logger.warning('Recompute available packages updates as requested by dbus client.')
                    self.myport['manager'].pretend['forced'] = False
                logger.debug('Running pretend_world()')
                # Making async and non-blocking
                self.scheduler.run_in_executor(None, self.myport['manager'].pretend_world, ) # -> ', )' = same here
            
            time.sleep(1)
        
        # LOOP Terminate
        # This is a workaround: GLib.MainLoop have to been terminate 
        # Here or it will never return to main()
        # But be sure it have been run()
        logger.debug('Received exit order...')
        if self.myport['dbus'].is_running():
            start_time = timing_exit['processor']()
            logger.debug('Sending quit() to dbus loop (Glib.MainLoop()).')
            self.myport['dbus'].quit()
            end_time = timing_exit['processor']()
            logger.debug('Dbus loop have been shut down in'
                         + ' {0}'.format(end_time - start_time)
                         + f" {timing_exit['msg']}.")
        
        #  Wait before exiting if:
        # dosync() is running through self.scheduler (asyncio)
        if self.myport['manager'].sync['status']:
            start_time = timing_exit['processor']()
            logger.debug('Sending exit request for running dosync().')
            self.myport['manager'].exit_now['sync'] = True
            # Wait for reply
            while not self.myport['manager'].exit_now['sync'] == 'Done':
                # So if we don't have reply but if
                # status change to False then process have been done
                # just break
                if not self.myport['manager'].sync['status']:
                    logger.debug('dosync() process have been completed.')
                    break
            end_time = timing_exit['processor']()
            logger.debug('dosync() have been shut down in'
                         + ' {0}'.format(end_time - start_time)
                         + f" {timing_exit['msg']}.")
        
        # pretend_world() is running through self.scheduler (asyncio)
        if self.myport['manager'].pretend['status'] == 'running':
            start_time = timing_exit['processor']()
            logger.debug('Sending exit request for running pretend_world().')
            self.myport['manager'].exit_now['pretend'] = True
            # Wait for reply
            while not self.myport['manager'].exit_now['pretend'] == 'Done':
                # same as dosync() shut down
                if self.myport['manager'].pretend['status'] == 'completed':
                    logger.debug('pretend_world() process have been completed.')
                    break
            end_time = timing_exit['processor']()
            logger.debug('pretend_world() have been shut down in'
                         + ' {0}'.format(end_time - start_time)
                         + f" {timing_exit['msg']}.")
        
        # IF we are writing something to the statefile.
        process_wait = False
        start_time = timing_exit['processor']()
        while self.myport['manager'].saving_status:
            process_wait = True
        if process_wait:
            end_time = timing_exit['processor']()
            logger.debug('...exiting now, bye' 
                        + ' (remaining processes have been shut down in'
                        + ' {0}'.format(end_time - start_time)
                        + f" {timing_exit['msg']}).")
        else:
            logger.debug('...exiting now, bye.')
        


def main():
    """
    Init main daemon
    """
    
    # Init dbus service
    dbusloop = GLib.MainLoop()
    dbus_session = SystemBus()
    
    # Init Emerge log watcher
    # For now status of emerge --sync and @world is get directly from portagemanager module
    myportwatcher = EmergeLogWatcher(pathdir, name='Emerge Log Watcher Daemon', daemon=True)
    
    # Init portagemanager
    myportmanager = PortageDbus(interval=args.sync, pathdir=pathdir, dryrun=args.dryrun)
    
    # Check sync
    myportmanager.check_sync(init_run=True, recompute=True)
    # Get last portage package
    # Better first call here because this won't be call before EmergeLogWatcher detected close_write
    myportmanager.available_portage_update()
    # Same here: Check if global update has been run 
    myportmanager.get_last_world_update()
    
    # Adding objet to myport
    myport = { }
    myport['manager'] = myportmanager
    myport['watcher'] = myportwatcher
    myport['dbus'] = dbusloop
    
    failed_access = re.compile(r'^.*AccessDenied.*is.not.allowed.to' 
                               + r'.own.the.service.*due.to.security'
                               + r'.policies.in.the.configuration.file.*$')
    busconfig = True
    # Adding dbus publisher
    try:
        dbus_session.publish('net.syuppod.Manager.Portage', myportmanager)
    except GLib.GError as error:
        error = str(error)
        if failed_access.match(error):
            logger.error(f'Got error: {error}')
            logger.error(f'Try to copy configuration file: \'{dbus_conf}\''
                         + ' to \'/usr/share/dbus-1/system.d/\' and restart daemon')
        else:
            logger.error(f'Got unexcept error: {error}')
        logger.error('Dbus bindings have been DISABLED !!')
        busconfig = False
    
    # Init daemon thread
    daemon_thread = MainDaemon(myport, name='Main Daemon Thread', daemon=True)
    
    # Start all threads and dbus thread
    myport['watcher'].start()
    daemon_thread.start()
    if busconfig:
        logger.debug('Running dbus loop using Glib.MainLoop().')
        dbusloop.run()
    
    # Exiting gracefully - Try to :p
    # Glib.MainLoop is shut down in MainDaemonThread
    daemon_thread.join()
    
    # For watcher thread
    # This could, sometime, last almost 10s before exiting
    # TODO Maybe we could investigate more about this
    logger.debug('Sending exit request to watcher thread.')
    start_time = timing_exit['processor']()
    myport['watcher'].exit_now = True
    # Only wait for thread to send 'Done'
    # TODO : maybe better using wait()?
    # see: https://docs.python.org/3/library/threading.html#threading.Condition.wait
    while not myport['watcher'].exit_now == 'Done':
        pass
    end_time = timing_exit['processor']()
    logger.debug('Watcher thread have been shut down in'
                + ' {0}'.format(end_time - start_time)
                + f" {timing_exit['msg']}.")
    myport['watcher'].join()
    
    # Every thing done
    logger.info('...exiting, ...bye-bye.')
    sys.exit(0)
           
    
if __name__ == '__main__':    
    
    # Ok so first parse argvs
    myargsparser = DaemonParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
    
    # Then configure logging
    if sys.stdout.isatty():
        # configure the root logger
        logger = logging.getLogger()
        # Rename root logger
        logger.root.name = f'{__name__}'
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(LogLevelFormatter())
        logger.addHandler(console_handler)
        # Default to info
        logger.setLevel(logging.INFO)
        # Working with xfce4-terminal and konsole if set to '%w'
        print(f'\33]0;{prog_name} - version: {__version__}\a', end='', flush=True)
    else:
        # configure the root logger
        logger = logging.getLogger()
        # Rename root logger
        logger.root.name = f'{__name__}'
        # Add debug handler only if debug is enable
        handlers = { }
        if args.debug and not args.quiet:
            # Ok so it's 5MB each, rotate 3 times = 15MB TEST
            debug_handler = logging.handlers.RotatingFileHandler(pathdir['debuglog'], maxBytes=5242880, backupCount=3)
            debug_formatter   = logging.Formatter('%(asctime)s  %(name)s  %(message)s')
            debug_handler.setFormatter(debug_formatter)
            # For a better debugging get all level message to debug
            debug_handler.addFilter(LogLevelFilter(50))
            debug_handler.setLevel(10)
            handlers['debug'] = debug_handler
        # Other level goes to Syslog
        syslog_handler   = logging.handlers.SysLogHandler(address='/dev/log',facility='daemon')
        syslog_formatter = logging.Formatter(f'{prog_name} %(levelname)s  %(message)s')
        syslog_handler.setFormatter(syslog_formatter)
        syslog_handler.setLevel(20)
        handlers['syslog'] = syslog_handler
        # Add handlers
        for handler in handlers.values():
            logger.addHandler(handler)
        # Set log level
        logger.setLevel(logging.INFO)
    
    # Then, pre-check
    if not sys.stdout.isatty():
        display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
        # Check for --dryrun
        if args.dryrun:
            logger.error('Running --dryrun from /etc/init.d/ is NOT supported.')
            logger.error('Exiting with status \'1\'.')
            sys.exit(1)
    elif sys.stdout.isatty():
        display_init_tty = ''
        logger.info('Interactive mode detected, all logs go to terminal.')
        # TODO FIXME this have to be removed when we will change how syuppod is setup
        logger.info('Make sure to run init file as root to setup syuppod.')
        # Just check if user == 'syuppod'
        if not getuser() == 'syuppod':
            logger.error(getuser())
            logger.error('Running program from terminal require to run as \'syuppod\' user.')
            logger.error('Exiting with status \'1\'.')
            sys.exit(1)
        # Check if directories exists
        if not args.dryrun:
            # Check basedir and logdir directories
            for directory in 'basedir', 'logdir':
                if not pathlib.Path(pathdir[directory]).is_dir():
                    # Ok so exit because we cannot manage this:
                    # Program has to been run as syuppod
                    # BUT creating directories has to be run as root...
                    logger.error(f"Missing directory: '{pathdir[directory]}'.")
                    logger.error('Exiting with status \'1\'.')
                    sys.exit(1)
        else:
            logger.info('Dryrun is enabled, skipping all write process.')
          
    # Setup level logging (default = INFO)
    if args.debug and args.quiet:
        logger.info('Both debug and quiet opts have been enabled,' 
                    + ' falling back to log level info.')
    elif args.debug:
        logger.setLevel(logging.DEBUG)
        logger.info(f'Debug has been enabled. {display_init_tty}')
        logger.debug('Messages are from this form \'::module::class::method:: msg\'.')
    elif args.quiet:
        logger.setLevel(logging.ERROR)
    
    # Configure timing exit
    timing_exit = { }
    # keep compatibility for v3.5/v3.6
    timing_exit['processor'] = time.process_time
    timing_exit['msg'] = 'seconds'
    # time.process_time_ns() have been added to v3.7
    #if sys.version_info[:2] > (3, 6):
        #timing_exit['processor'] = time.process_time_ns
        #timing_exit['msg'] = 'nanoseconds'
    
    # run MAIN
    main()
    
    
    
    


