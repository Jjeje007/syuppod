# -*- coding: utf-8 -*-
# -*- python -*- 
# Starting : 2019-08-08

# SYnc UPdate POrtage Daemon 
# Part of syuppo package
# Copyright © 2019-2021 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3


# TODO write GOOD english ;)
import sys
import logging
import argparse
import re
import pathlib
import time
import errno
import asyncio
import threading
import signal

from syuppo.dbus import PortageDbus
from syuppo.argsparser import DaemonParserHandler
from syuppo.logger import LogLevelFilter
from syuppo.logger import addLoggingLevel
from syuppo.utils import CatchExitSignal
from syuppo.utils import CheckProcRunning

try:
    from gi.repository import GLib
    from pydbus import SystemBus
except Exception as exc:
    print(f'Error: unexpected while loading module: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)

try:
    import inotify_simple
except Exception as exc:
    print(f'Got unexcept error while loading inotify_simple module: {exc}',
                                                            file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)

__version__ = 'dev'
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

# Custom level name share across all logger
logging.addLevelName(logging.CRITICAL, '[ Crit ]')
logging.addLevelName(logging.ERROR,    '[Error ]')
logging.addLevelName(logging.WARNING,  '[ Warn ]')
logging.addLevelName(logging.INFO,     '[ Info ]')
logging.addLevelName(logging.DEBUG,    '[Debug ]')
# Adding advanced debug loglevel
addLoggingLevel('DEBUG2', 9)
logging.addLevelName(logging.DEBUG2,   '[Vdebug]')

# Configure timing exit
timing_exit = time.process_time



class RegularDaemon(threading.Thread):
    """
    Regular daemon Thread which handle sync and
    pretend run 
    """
    def __init__(self, manager, dbus_daemon, dynamic_daemon, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.logger_name = f'::{__name__}::RegularDaemon::'
        logger = logging.getLogger(f'{self.logger_name}init::')
        
        self.manager = manager
        self.dbus_daemon = dbus_daemon
        self.dynamic_daemon = dynamic_daemon
        # Init asyncio loop
        self.scheduler = asyncio.new_event_loop()
        # Change log level of asyncio 
        # to be the same as RootLogger
        currentlevel = logger.getEffectiveLevel()
        logger.debug(f'Setting log level for asyncio to: {currentlevel}')
        logging.getLogger('asyncio').setLevel(currentlevel)
        # Catch signals
        self.mysignal = CatchExitSignal()
        
        self.logflow = 10
        self.delayed = {
            'count' :   0,
            'proc'  :   None
            }
    
    
    def allow(self, tocall):
        """
        Authorized the call to the specified method
        if no process is in progress.
        :param tocall:
            This is the method we want to call: choose between
            'sync' and 'pretend'
        :return:
            True if allowed else False
        """
        
        logger = logging.getLogger(f'{self.logger_name}allow::')
        
        allowed = False
        # Make sure no monitoring process is running
        if not self.dynamic_daemon.pstate:
            msg = ''
            if self.delayed['proc']:
                msg_count = "less than a second"
                if self.delayed['count']:
                    msg_count = f"{self.delayed['count']} second(s)"
                msg = (" (delayed by the execution of the"
                        f" '{self.delayed['proc']}' process for"
                        f" {msg_count}).")
            
            if tocall == 'sync':
                # For sync there is an another step
                with self.manager.sync['locks']['check']:
                    if self.manager.check_sync(recompute=True):
                        logger.debug(f"Allow running dosync(){msg}")
                        allowed = True
            elif tocall == 'pretend':
                logger.debug(f"Allow running pretend_world(){msg}")
                allowed = True
            
            self.logflow = 10
            self.delayed['count'] = 0
            self.delayed['proc'] = None
        # If a process is running then wait until it's finished
        # and record how long it been waiting for and which 
        # process
        else:
            # count how long it will be delayed and by witch process
            self.delayed['count'] += 1
            self.delayed['proc'] = self.dynamic_daemon.pstate['proc']
            # Avoid flood logger.debug, call every 10s
            if self.logflow <= 0:
                logger.debug(f"Delaying call for {tocall}: "
                            + f"process: {self.delayed['proc']} running"
                            + " (already delayed since:"
                            + f" {self.delayed['count']} second(s)")
                self.logflow = 10
            self.logflow -= 1
        return allowed    
    
    def run(self):
        """
        Proceed call to pretend_world() and
        to dosync() according to conditions
        """
        logger = logging.getLogger(f'{self.logger_name}run::')
        logger.debug('Regular Daemon Thread started.')
        
        # Make sure we sleep exactly 1s 
        # THX!: https://stackoverflow.com/a/49801719/11869956
        delay = 1
        next_time = time.time() + delay
        while not self.mysignal.exit_now:
            
            # Regular sync
            if (self.manager.sync['remain'] <= 0
               and self.manager.sync['status'] == 'ready'):
                if self.allow('sync'):
                    logger.debug("Running dosync()")
                    # sync not blocking using asyncio and thread 
                    self.scheduler.run_in_executor(None, 
                                            self.manager.dosync, )
            # TEST now it should be 1s 
            # WARNING it's not true every time
            # if all calls in this loop take more than 1s WARNING
            with self.manager.sync['locks']['remain']:
                self.manager.sync['remain'] -= 1
            with self.manager.sync['locks']['elapsed']:
                self.manager.sync['elapsed'] += 1
            
            # This is the case where we want to call pretend,
            # there is not process running
            # and pretend is waiting and 
            # it was cancelled so recall pretend :p
            if (self.manager.pretend['cancelled'] 
               and not self.dynamic_daemon.pstate):
                logger.warning("Recalling available packages updates"
                               " search as it was cancelled.")
                with self.manager.pretend['locks']['proceed']:
                    self.manager.pretend['proceed'] = True
                with self.manager.pretend['locks']['cancelled']:
                    self.manager.pretend['cancelled'] = False
            
            # Every thing is OK: pretend was wanted, 
            # has been called and is completed 
            if self.manager.pretend['status'] == 'completed':
                # Wait between two pretend_world() run 
                if self.manager.pretend['remain'] <= 0:
                    logger.debug("Changing state for pretend process" 
                                " from completed to waiting.")
                    logger.debug("pretend_world() can be call again.")
                    interval = self.manager.pretend['interval']
                    self.manager.pretend['remain'] = interval
                    with self.manager.pretend['locks']['status']:
                        self.manager.pretend['status'] = 'ready'
                self.manager.pretend['remain'] -= 1
            
            # Run pretend_world() if authorized 
            # Leave other check (sync running ? pretend already 
            # running ? world update running ?) to portagedbus 
            # module so it can reply to client.
            # Disable pretend_world() if sync is in progress 
            # otherwise will run twice.
            # Don't run pretend if world / sync in progress or 
            # if not status == 'ready'
            if (self.manager.pretend['proceed']
               and self.manager.pretend['status'] == 'ready'):
                if self.allow('pretend'):
                    if self.manager.pretend['forced']:
                        logger.warning('Recompute available packages updates'
                                        ' as requested by dbus client.')
                        self.manager.pretend['forced'] = False
                    logger.debug('Running pretend_world()')
                    # Making async and non-blocking
                    self.scheduler.run_in_executor(None,
                                                    # -> ', )' = same here
                                self.manager.pretend_world, ) 
                        
            # skip calls if we are behind schedule:
            next_time += (time.time() - next_time) // delay * delay + delay
            time.sleep(max(0, next_time - time.time()))
        # Loop exit
        logger.debug('Received exit order...')
        self.stop_dbus()
        self.stop_running_proc()
        self.wait_on_saving()
        logger.debug('...exiting now, bye.')
       
    def stop_dbus(self):
        """
        Stop dbus loop if running
        """
        logger = logging.getLogger(f'{self.logger_name}stop_dbus::')
        # This is a workaround: GLib.MainLoop have to been terminate
        # Here or it will never return to main()
        # But be sure it have been run()
        if self.dbus_daemon and self.dbus_daemon.is_running():
            start_time = timing_exit()
            logger.debug('Sending quit() to dbus loop (Glib.MainLoop()).')
            self.dbus_daemon.quit()
            end_time = timing_exit()
            logger.debug("Dbus loop have been shut down in"
                         f" {end_time - start_time} second(s).")
    
    def stop_running_proc(self):
        """
        Stop asyncio process dosync()
        and or pretend_world() if
        running
        """
        logger = logging.getLogger(f'{self.logger_name}stop_running_proc::')
        # Check and stop:
        # dosync() if running through self.scheduler (asyncio)
        # pretend_world() if running through self.scheduler (asyncio)
        for proc in 'sync', 'pretend':
            myattr = self.manager.sync
            msg = 'dosync()'
            if proc == 'pretend':
                myattr = self.manager.pretend
                msg = 'pretend_world()'
            
            if myattr['status'] == 'running':
                start_time = timing_exit()
                logger.debug(f"Sending exit request for running {msg}.")
                
                myattr['exit'] = True
                # Wait for reply
                while not myattr['exit'] == 'Done':
                    # So if we don't have reply but if
                    # status change to False then process have been done
                    # just break
                    if myattr['status'] in ('completed', 'ready'):
                        logger.debug(f"{msg} process have been completed.")
                        break
                end_time = timing_exit()
                logger.debug(f"{msg} have been shut down in "
                             f"{end_time - start_time} second(s).")    
    
    def wait_on_saving(self):
        """
        Wait if we are writing to statefile
        """
        logger = logging.getLogger(f'{self.logger_name}wait_on_saving::')
        # Wait if we are writing something to the statefile.
        process_wait = False
        start_time = timing_exit()
        while self.manager.saving_status:
            process_wait = True
        if process_wait:
            end_time = timing_exit()
            logger.debug("Remaining processes have been shut down in"
                         f" {end_time - start_time} second(s).")



class DynamicDaemon(threading.Thread):
    """
    Proceed changes depending on dynamics conditions
    """
    def __init__(self, pathdir, manager, 
                 advanced_debug=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Init logger
        self.logger_name = f'::{__name__}::DynamicDaemon::'
        logger = logging.getLogger(f'{self.logger_name}init::')
        # For exiting
        self.exit_now = False
        # Wait for this thread exiting
        self.exiting = threading.Event()
        self.manager = manager
        #logger.debug(f"MANAGER: {self.manager}")
        # Switch between watched target
        self.watch = {
            'inotify'  :   {
                'path'      :   pathdir['emergelog'],
                'flags'     :   8,
                'id'        :   'inotify',
                'call'      :   self.inotifywatch
                },
            'file'   :   {
                'path'      :   False,
                'id'        :   'file',
                'call'      :   self.filewatch
                }
            }
        # Default inotify setup
        self.caller = self.watch['inotify']
        self.timeout = 1
        self.inotify = False
        
        # for process querying
        self.prun = CheckProcRunning()
        self.pstate = False
        
        self.logflow = self.__load_def()        
    
    def __load_def(self):
        """
        Load default logflow attrs.
        """
        return {
            'debug' :   {
                'index'     :   0,
                'store'     :   0
                },
            'info'  :   {
                'index'     :   0,
                'store'     :   0
                }
            }
        
    def display_log(self, level):
        """
        Control the logflow.
        :level:
            The level of logging to apply.
        :return:
            True if authorized else False.
        """
        logger = logging.getLogger(f'{self.logger_name}display_log::')
        
        __config = {
            # For debug ouput every 60s
            'debug' :   ( 60, ),
            # For info output gradually
            # this is all in seconds because filewatch
            # loop sleep 1s
            # TODO this could also be tweak 
            'info'  :   ( 1800, 3600, 7200 )
            }
        
        current = time.time()
        if self.logflow[level]['store'] <= current:
            index = self.logflow[level]['index']
            length = len(__config[level])
            
            self.logflow[level]['store'] = (current + 
                                            __config[level][index])
            if self.logflow[level]['index'] < length - 1:
                self.logflow[level]['index'] += 1
            return True
        return False
    
    def filewatch(self):
        """
        Using pathlib to watch deleted file in /proc since 
        inotify won't work on /proc.
        """
        
        logger = logging.getLogger(f'{self.logger_name}filewatch::')
        
        msg = {
            'world'     :   'Global update',
            'sync'      :   'Synchronization',
            'system'    :   'System update',
            # We don't know if will be update or downgrade...
            'portage'   :   'The portage package process'
        }
               
        logger.debug(f"Started monitoring: '{self.caller['path']}'"
                    + f" using pathlib.Path().exists()")
        
        # For world update, make sure pretend is NOT running
        # TODO pretend could be left running when detecting
        # portage package process ?? TODO ?
        if (pathlib.Path(self.caller['path']).exists() 
                and self.manager.pretend['status'] == 'running'):
            logger.debug("Found pretend process running, shutting down.")
            with self.manager.pretend['locks']['cancel']:
                # Send proc id for specific msg 
                self.manager.pretend['cancel'] = self.pstate['proc']
            # Leave the recall to RegularDaemon
        
        # Make sure we sleep exactly 1s 
        # THX!: https://stackoverflow.com/a/49801719/11869956
        delay = 1
        next_time = time.time() + delay
        while (pathlib.Path(self.caller['path']).exists() 
                and not self.exit_now):
            if self.display_log('debug'):
                logger.debug(f"{msg[self.pstate['proc']]} is in progress"
                             f" on pid: {self.pstate['path'].stem}")
            if self.display_log('info'):
                logger.info(f"{msg[self.pstate['proc']]} is in progress.")
            # skip calls if we are behind schedule:
            next_time += (time.time() - next_time) // delay * delay + delay
            time.sleep(max(0, next_time - time.time()))
        
        # Loop terminate, we have to reset self.logflow
        self.logflow = self.__load_def()
        
        if self.exit_now:
            logger.debug("Stop waiting, receive exit order.")
            return
        logger.debug(f"{self.caller['path']} have been deleted.")
        # Don't use logger.info here because we don't know
        # if the process was successfully run or not.
        # This is check in manager --> get_last_world_update()
        # and check_sync() TODO: system is not implented for the 
        # moment.
            
    def inotifywatch(self):
        """
        Using inotify to watch specified path with specified flags.
        """
        logger = logging.getLogger(f'{self.logger_name}inotifywatch::')
        # if inotify not already setup
        if not self.inotify:
            self.inotify = self.__inotify()
        reader = False
        # For exit order also
        # But should be self.timeout != 0 / None
        # Otherwise it will be stuck until new data is available
        while not reader and not self.exit_now:
            reader = self.inotify.read(timeout=self.timeout)
    
        if self.exit_now:
            logger.debug("Stop waiting, receive exit order.")
            return 
        
        logger.debug(f"State changed with: {reader}.")
        # DONT close here: let self.checking() doing it
        # OR at the end of run()
    
    def __inotify(self):
        """
        Setup a watch and return its
        """
        logger = logging.getLogger(f'{self.logger_name}__inotify::')
        inotify = inotify_simple.INotify()
        # Ouput by flag over one numeric value
        get_flags = inotify_simple.flags.from_mask
        try:
            log_wd = inotify.add_watch(self.caller['path'], self.caller['flags'])
        except OSError as error:
            logger.error(f"Inotify watch crash: Using:"
                        + f" '{self.caller['path']}'.")
            logger.error(f"{error}: Exiting with status '1'.")
            sys.exit(1)
        else:
            logger.debug(f"Started monitoring: '{self.caller['path']}', flags:"
                        + f" '{get_flags(self.caller['flags'])}',"
                        + f" timeout={self.timeout}.")
            return inotify
          
    def checking(self):
        """
        Checking process using CheckProcRunning()
        and changed caller depending of
        its output
        """
        logger = logging.getLogger(f'{self.logger_name}checking::')
        # Get current processes state
        self.pstate = self.prun.check()
        # Found process
        if self.pstate:
            logger.debug("Found running process:"
                        + f" {self.pstate}")
            # For sync detect internal/external
            if self.pstate['proc'] == 'sync':
                # Just get the status from manager: True if internal else False
                if self.manager.sync['status'] == 'running':
                    self.pstate['internal'] = True
                    self.manager.external_sync = False
                else:
                    self.pstate['internal'] = False
                    # So advise dbus sync is external
                    # And set its pid. 'path' is a PosixPath object
                    self.manager.external_sync = self.pstate['path'].stem
                    logger.debug("Setting dbus external_sync to:"
                                f" {self.manager.external_sync}")
                logger.debug(f"Sync is internal: {self.pstate['internal']}")
            # For world advise also dbus and set its pid
            if self.pstate['proc'] == 'world':
                self.manager.world_state = self.pstate['path'].stem
                logger.debug("Setting dbus world_state to:"
                                f" {self.manager.world_state}")
            
            # Now switch the caller 
            self.watch['file']['path'] = self.pstate['path']
            # First close self.inotify() and
            # set it to False 
            if self.inotify:
                logger.debug(f"Closing inotify watcher: {self.inotify}")
                self.inotify.close()
                self.inotify = False
            # Then switch caller
            current_caller = self.caller
            self.caller = self.watch['file']
            logger.debug(f"Setting caller from '{current_caller}'"
                         + f" to '{self.caller}'.")
        # Not found
        else:
            # Reset dbus manager states
            logger.debug("Reset dbus manager states to False: current:"
                        f" external_sync: {self.manager.external_sync}"
                        f" world_state: {self.manager.world_state}")
            self.manager.external_sync = False
            self.manager.world_state = False
            # Make sure to get the default caller
            if not self.caller['id'] == 'inotify':
                current_caller = self.caller
                self.caller = self.watch['inotify']
                logger.debug(f"Resetting caller from '{current_caller}'"
                             f" to '{self.caller}' (default).")
            else:
                logger.debug(f"Keeping default caller: {self.caller}")
       
    def sync(self):
        """
        Update all attributes and methods
        related to a sync status changed
        """
        logger = logging.getLogger(f'{self.logger_name}sync::')
        
        # After a sync, portage package update have to be run
        logger.debug("Running .portage()")
        self.portage(detected=False)
        # pretend_world() should also be run
        # but only if it's an external sync 
        if self.pstate['internal']:
            logger.debug("Skip the rest of the processes: sync was internal.")
            return
        
        # This is for external sync only
        # Make sure to lock the method
        with self.manager.sync['locks']['check']:
            logger.debug("Running check_sync()")
            # Don't automatically recompute, let check_sync()
            # make the decision
            self.manager.check_sync()
            # If pretend_world() should be run 
            # then let RegularDaemon handle it
        
    def world(self):
        """
        Update all attributes and methods
        related to a world update changed
        """
        logger = logging.getLogger(f'{self.logger_name}world::')
        
        # call get_last_world_update() for update available
        # package update (could be to 0)
        logger.debug("Running get_last_world_update()")
        # TEST now get_last_world_update return True if
        # world update have run else False.
        if self.manager.get_last_world_update(detected=True):
            # let pretend_world() be run by RegularDaemon
            # And manage directly by get_last_world_update()
            # Also, call portage to update portage package update
            # status only if world have been updated
            logger.debug("Running '.portage()'")
            self.portage(detected=False)
    
    def system(self):
        """
        Update all attributes and methods
        related to a system update changed
        """
        logger = logging.getLogger(f'{self.logger_name}system::')
        # TODO TODO First we have to implant parser for system
        logger.debug("TODO !!")
        
    def portage(self, detected=True):
        """
        Update all attributes and methods
        related to a portage status changed
        :detected:
            If process running have been detected.
            Defaut: True (because it's a generic call
            in 'run' using getattr. So that mean,
            if it call directly than it have been
            detected)
        """
        logger = logging.getLogger(f'{self.logger_name}portage::')
        
        logger.debug("Running available_portage_update()")
        self.manager.available_portage_update(detected=detected)
        
    def run(self):
        """
        Wait on specifics status changes for specifics files and
        call specific methods depending situations.
        """
        logger = logging.getLogger(f'{self.logger_name}run::')
        logger.debug('Dynamic Daemon Thread started.')
        
        # Before entering the loop, select the appropriate caller
        self.checking()                
        while not self.exit_now:
            # wait on watching specified file/dir with specific caller
            self.caller['call']()
            
            if self.exit_now:
                break            
            # state has changed
            # there is two choices depending on caller
            if self.caller['id'] == 'inotify':
                logger.debug("Checking if specified process is running")
                self.checking()
                # self.checking() will automatically changed caller so
                # all we have to do here is to restart the loop :p
            elif self.caller['id'] == 'file':
                # this mean: we started to monitor inotify which result
                # in flags changed. Then, we check if specified process
                # is running which result to true. So, we wait to this 
                # specified process has finished, which is true now.
                # And here we are :p
                # All depend on self.pstate['proc']
                getattr(self, self.pstate['proc'])()
                # After this recall self.checking() 
                # so it can set the 'good' caller again
                self.checking()
                
        # Loop Stop
        logger.debug("Received exit order...")
        if self.inotify:
            self.inotify.close()
            logger.debug("Inotify() shut downed.")
        
        logger.debug("...exiting now, bye.")
        # Send reply to main
        self.exit_now = 'Done'
        # Test: set event
        self.exiting.set()



def main():
    """
    Main
    """
    
    # Ok so first parse argvs
    myargsparser = DaemonParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
       
    # Then configure logging
    if sys.stdout.isatty():
        from syuppo.logger import LogLevelFormatter
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
        # TODO For a better approch ? see [1]
        # [1]: https://gitweb.gentoo.org/proj/portage.git/tree/lib/portage/output.py?id=03d4c33f48eb5e98c9fdc8bf49ee239489229b8e
        print(f'\33]0;{prog_name} - version: {__version__}\a', end='', 
             flush=True)
    else:
        # configure the root logger
        logger = logging.getLogger()
        # Rename root logger
        logger.root.name = f'{__name__}'
        # Add debug handler only if debug is enable
        handlers = { }
        if args.debug and not args.quiet:
            # Ok so it's 5MB each, rotate 3 times = 15MB TEST
            debug_handler = logging.handlers.RotatingFileHandler(
                                                        pathdir['debuglog'],
                                                        maxBytes=5242880,
                                                        backupCount=3)
            debug_formatter = logging.Formatter('%(asctime)s  %(name)s'
                                                '  %(message)s')
            debug_handler.setFormatter(debug_formatter)
            # For a better understanding get 
            # all level message for debug log
            debug_handler.addFilter(LogLevelFilter(50))
            debug_handler.setLevel(10)
            handlers['debug'] = debug_handler
        # Other level goes to Syslog
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log',
                                                        facility='daemon')
        syslog_formatter = logging.Formatter(f'{prog_name} %(levelname)s'
                                             '  %(message)s')
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
        display_init_tty = f"Log are located to {pathdir['debuglog']}"
        # Check for --dryrun
        if args.dryrun:
            logger.error("Running --dryrun from /etc/init.d/"
                         " is NOT supported.")
            logger.error("Exiting with status 1.")
            sys.exit(1)
    elif sys.stdout.isatty():
        from getpass import getuser
        display_init_tty = ''
        logger.info('Interactive mode detected, all logs go to terminal.')
        # Just check if user == 'syuppod'
        running_user = getuser()
        if not running_user == 'syuppod':
            logger.error("Running program from terminal require to run as"
                         f" syuppod user (current: {running_user}).")
            logger.error("Exiting with status '1'.")
            sys.exit(1)
        # Check if directories exists
        if not args.dryrun:
            # Check basedir and logdir directories
            for directory in 'basedir', 'logdir':
                if not pathlib.Path(pathdir[directory]).is_dir():
                    # Ok so exit because we cannot manage this:
                    # Program have to been run as syuppod
                    # BUT creating directories have to be run as root...
                    logger.error(f"Missing directory: '{pathdir[directory]}'.")
                    logger.error("Exiting with status '1'.")
                    sys.exit(1)
        else:
            logger.warning("Dryrun is enabled, skipping all write process.")
          
    # Setup level logging (default = INFO)
    if args.debug and args.quiet:
        logger.info("Both debug and quiet opts have been enabled," 
                    " falling back to log level info.")
    elif args.debug:
        logger.setLevel(logging.DEBUG)
        logger.info(f"Debug is enabled. {display_init_tty}")
        logger.debug("Messages are from this form "
                     "'::module::class::method:: msg'.")
    elif args.quiet:
        logger.setLevel(logging.ERROR)
    
    if args.nodbus:
        logger.warning("Dbus binding is DISABLED.")
    else:
        # Init dbus service
        dbusloop = GLib.MainLoop()
        dbus_session = SystemBus()
    
    # Init manager
    manager = PortageDbus(interval=args.sync, pathdir=pathdir, 
                          dryrun=args.dryrun, vdebug=args.vdebug)
    
    # Init Dynamic Daemon
    dynamic_daemon = DynamicDaemon(pathdir, manager, 
                                  name='Dynamic Daemon Thread', daemon=True)
    
    # Check sync
    # Don't need to lock here 
    manager.check_sync(init=True, recompute=True)
    # Get last portage package
    # Better first call here because this won't be call 
    # before DynamicDaemon detected close_write
    manager.available_portage_update(init=True)
    # Same here: Check if global update have been run 
    manager.get_last_world_update()
    
    dbus_daemon = False
    if not args.nodbus:
        dbus_daemon = dbusloop        
    
    failed_access = re.compile(r'^.*AccessDenied.*is.not.allowed.to' 
                               r'.own.the.service.*due.to.security'
                               r'.policies.in.the.configuration.file.*$')
    
    busconfig = False
    if not args.nodbus:
        busconfig = True
        # Adding dbus publisher
        try:
            dbus_session.publish('net.syuppod.Manager.Portage', manager)
        except GLib.GError as error:
            error = str(error)
            if failed_access.match(error):
                logger.error(f"{error}")
                logger.error(f"Try to copy configuration file: '{dbus_conf}'"
                             " to '/usr/share/dbus-1/system.d/'"
                             " and restart the daemon.")
            else:
                logger.error(f"Unexcept error: {error}")
            logger.error("Dbus bindings have been DISABLED !")
            busconfig = False
      
    # Init daemon thread
    regular_daemon = RegularDaemon(manager, dbus_daemon, dynamic_daemon, 
                                   name='Regular Daemon Thread', daemon=True)
    
    logger.info('Start up completed.')
    # Start all threads and dbus thread
    dynamic_daemon.start()
    regular_daemon.start()
    if busconfig:
        logger.debug('Running dbus loop using Glib.MainLoop().')
        dbusloop.run()
    
    # Exiting gracefully
    # Glib.MainLoop is shut down in MainDaemonThread
    regular_daemon.join()
    
    logger.debug('Sending exit request to Dynamic Daemon thread.')
    start_time = timing_exit()
    dynamic_daemon.exit_now = True
    # Wait for the event
    dynamic_daemon.exiting.wait()
    end_time = timing_exit()
    logger.debug("Dynamic Daemon thread have been shut down in"
                f" {end_time - start_time} second(s).")
    dynamic_daemon.join()
    
    # Every thing done
    logger.info('...exiting, ...bye-bye.')
    sys.exit(0)
    
    
    


