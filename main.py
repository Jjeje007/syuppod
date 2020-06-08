#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Starting : 2019-08-08

# SYnc UPdate POrtage Daemon - main
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

# TODO TODO TODO don't run as root, investigate: 
# TODO : exit gracefully 
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

# Default basic logging, this will handle earlier error when
# daemon is run using /etc/init.d/
# It will be re-config when all module will be loaded
import sys
import logging
# Custom level name share across all logger
logging.addLevelName(logging.CRITICAL, '[Crit ]')
logging.addLevelName(logging.ERROR,    '[Error]')
logging.addLevelName(logging.WARNING,  '[Warn ]')
logging.addLevelName(logging.INFO,     '[Info ]')
logging.addLevelName(logging.DEBUG,    '[Debug]')

if not sys.stdout.isatty() or '--fakeinit' in sys.argv:
    display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
    if '--fakeinit' in sys.argv:
        msg = ' with dryrun enable' if '--dryrun' in sys.argv else ''
        # This will only display if running from terminal
        print(f'Info: Running fake init{msg}.', file=sys.stderr)
        if '--dryrun' in sys.argv:
            print('Info: All logs goes to syslog.', file=sys.stderr)
            display_init_tty = ''
    # Get RootLogger
    root_logger = logging.getLogger()
    # So redirect stderr to syslog (for the moment)
    from lib.logger import RedirectFdToLogger
    from lib.logger import LogErrorFilter
    from lib.logger import LogLevelFilter
    fd_handler_syslog = logging.handlers.SysLogHandler(address='/dev/log',facility='daemon')
    fd_formatter_syslog = logging.Formatter('{0} %(levelname)s  %(message)s'.format(prog_name))
    fd_handler_syslog.setFormatter(fd_formatter_syslog)
    fd_handler_syslog.setLevel(40)
    root_logger.addHandler(fd_handler_syslog)
    fd2 = RedirectFdToLogger(root_logger)
    sys.stderr = fd2
    # Running --fakeinit from /etc/init.d is useless and not supported
    if '--fakeinit' in sys.argv and not sys.stdout.isatty():
        print('Running --fakeinit from /etc/init.d/ is NOT supported.', file=sys.stderr)
        print('Exiting with status \'1\'.', file=sys.stderr)
        sys.exit(1)
    # Check for --dryrun
    if '--dryrun' in sys.argv and not '--fakeinit' in sys.argv:
        print('Running --dryrun from /etc/init.d/ is NOT supported.', file=sys.stderr)
        print('Exiting with status \'1\'.', file=sys.stderr)
        sys.exit(1)
   
else:
    # import here what is necessary to handle logging when 
    # running in a terminal
    from lib.logger import LogLevelFormatter
    display_init_tty = ''

import argparse
import re
import pathlib
import time
import errno
import asyncio
import threading
from portagedbus import PortageDbus
from portagemanager import EmergeLogWatcher
from argsparser import DaemonParserHandler
try:
    from gi.repository import GLib
    from pydbus import SystemBus
except Exception as exc:
    print(f'Error: unexcept error while loading dbus bindings: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)



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
    
    def run(self):
        logger = logging.getLogger(f'{self.logger_name}run::')
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
        dbusloop.run()
    
    daemon_thread.join()
    myport['watcher'].join()
           
    
if __name__ == '__main__':    
    
    # Ok so first parse argvs
    myargsparser = DaemonParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
    
    if not args.dryrun:
        # Check or create basedir and logdir directories
        # Print to stderr as we have a redirect for init run 
        for directory in 'basedir', 'logdir':
            if not pathlib.Path(pathdir[directory]).is_dir():
                try:
                    pathlib.Path(pathdir[directory]).mkdir()
                except OSError as error:
                    if error.errno == errno.EPERM or error.errno == errno.EACCES:
                        print('Got error while making directory:' 
                            + f' \'{error.strerror}: {error.filename}\'.', file=sys.stderr)
                        print('Daemon is intended to be run as sudo/root.', file=sys.stderr)
                    else:
                        print('Got unexcept error while making directory:' 
                            + f' \'{error}\'.', file=sys.stderr)
                    print('Exiting with status \'1\'.', file=sys.stderr)
                    sys.exit(1)
    
    # Now re-configure logging
    if sys.stdout.isatty() and not args.fakeinit:
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
    elif not args.dryrun:
        # Reconfigure root logger only at the end 
        # this will keep logging error to syslog
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
        # Filter stderr output
        syslog_handler.addFilter(LogErrorFilter(stderr=False))
        syslog_handler.setLevel(20)
        handlers['syslog'] = syslog_handler
        
        # Catch file descriptor stderr
        # Same here 5MB, rotate 3x = 15MB
        fd_handler = logging.handlers.RotatingFileHandler(pathdir['fdlog'], maxBytes=5242880, backupCount=3)
        fd_formatter   = logging.Formatter('%(asctime)s  %(message)s')
        fd_handler.setFormatter(fd_formatter)
        fd_handler.addFilter(LogErrorFilter(stderr=True))
        # Level is error : See class LogErrorFilter
        fd_handler.setLevel(40)
        handlers['fd'] = fd_handler
        
        # reconfigure the root logger
        logger = logging.getLogger()
        # Rename root logger
        logger.root.name = f'{__name__}'
        # Add handlers
        for handler in handlers.values():
            logger.addHandler(handler)
        # Set log level
        logger.setLevel(logging.INFO)
        # redirect again but now not to syslog but to file ;)
        # First remove root_logger handler otherwise it will still send message to syslog
        root_logger.removeHandler(fd_handler_syslog)
        fd2 = RedirectFdToLogger(logger)
        sys.stderr = fd2
    else:
        # Keep default configuration
        logger = root_logger
        # Set loglevel to INFO
        logger.setLevel(logging.INFO)
        # We need to reset also fd_handler_syslog loglevel...
        fd_handler_syslog.setLevel(logging.DEBUG)
        
    # default level is INFO
    if args.debug and args.quiet:
        logger.info('Both debug and quiet opts has been enable,' 
                    + ' falling back to log level info.')
    elif args.debug:
        logger.setLevel(logging.DEBUG)
        logger.info(f'Debug has been enable. {display_init_tty}')
        logger.debug('Messages are from this form \'::module::class::method:: msg\'.')
    elif args.quiet:
        logger.setLevel(logging.ERROR)
    
    if sys.stdout.isatty() and not args.fakeinit:
        logger.info('Interactive mode detected, all logs go to terminal.')
    if args.dryrun:
        logger.info('Dryrun is enable, skipping all write process.')
    
    # run MAIN
    main()
    
    
    
    


