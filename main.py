#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Starting : 08 aout 2019

import sys
import os
import argparse
import pathlib
import time
import re
import errno
#import utils
import threading

from portagedbus import PortageDbus
from gitdbus import GitDbus
from gitmanager import check_git_dir
from logger import MainLoggingHandler
from logger import RedirectFdToLogger
from argsparser import DaemonParserHandler
from utils import UpdateInProgress
from utils import StateInfo

# To remimber : http://stackoverflow.com/a/11887885
# TODO : enable or disable dbus bindings. So this should only be load if dbus is enable
# If dbus is disable (default is enable) then the user should be warn that it won't get any output
# it has to get info from state file
# TODO : exit gracefully 

# TODO : debug log level ! 
try:
    from gi.repository import GLib
    from pydbus import SystemBus # Changing to SystemBus (when run as root/sudo)
    # TODO: writing Exception like that in all program
except Exception as exc:
    print(f'Error: unexcept error while loading dbus bindings: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)

__version__ = "dev"
# DONT change this or dbus service won't work (client part)
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


class MainLoopThread(threading.Thread):
    def __init__(self, manager, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manager = manager
    
    def run(self):
        while True:
            # First: check if we have to sync
            if self.manager['portage'].sync['remain'] <= 0:
                # Make sure sync is not in progress
                if self.manager['portage'].check_sync():
                    # sync
                    if self.manager['portage'].dosync():
                        # Check if we are running world update and
                        # abord pretend world and check portage update
                        # if this is the case.
                        myupdate = UpdateInProgress(log)
                        if not myupdate.check(tocheck='World', quiet=True):
                            # pretend world update as sync is ok :)
                            self.manager['portage'].pretend_world()
                            # check portage update
                            self.manager['portage'].available_portage_update()
            self.manager['portage'].sync['remain'] -= 1  # For the moment this will not exactly be one second
            self.manager['portage'].sync['elapse'] += 1 # Because all this stuff take more time - specially
                                                         # pretend_world()
            
            # Then: check available portage update
            if self.manager['portage'].portage['remain'] <= 0:
                #if self.manager['portage'].portage['available']:
                # We have to check every time
                # Because you can make the update and then go back 
                self.manager['portage'].available_portage_update()
                # reset remain 
                self.manager['portage'].portage['remain'] = 30
            self.manager['portage'].portage['remain'] -= 1
            
            # Then: check if we are running world update
            if self.manager['portage'].world['remain'] <= 0:
                self.manager['portage'].get_last_world_update()
                if self.manager['portage'].world['status']:
                    # So pretend has to be run 
                    self.manager['portage'].pretend_world()
            self.manager['portage'].world['remain'] -= 1
            
            # For portage, last: implant forced pretend to be called
            # over dbus to no blocking call. 
            # Leave other check: is sync running ? is pretend already running ? is world update is running ?
            # to portagedbus module so it can reply to client 
            if self.manager['portage'].world['forced']:
                log.warning('Forcing pretend world as requested by dbus client.')
                self.manager['portage'].pretend_world()
                # Reset to False
                self.manager['portage'].world['forced'] = False
                        
            # Git stuff
            if self.manager['git'].enable:
                # First: pull
                if self.manager['git'].pull['status'] or self.manager['git'].pull['remain'] <= 0:
                    # Is git in progress ?
                    if self.manager['git'].check_pull():
                        # This is necessary to move all kernel / branch 
                        # from new list to know list
                        self.manager['git'].get_available_update('kernel')
                        self.manager['git'].get_available_update('branch')
                        # Pull 
                        if self.manager['git'].dopull():
                            # Pull is ok
                            # Then update all kernel / remote branch
                            self.manager['git'].get_all_kernel()
                            self.manager['git'].get_available_update('kernel')
                            self.manager['git'].get_branch('remote')
                            self.manager['git'].get_available_update('branch')
                self.manager['git'].pull['remain'] -= 1
                # Then : update all local info
                if self.manager['git'].remain <= 0:
                    # This is a regular info update
                    self.manager['git'].get_installed_kernel()
                    self.manager['git'].get_available_update('kernel')
                    self.manager['git'].get_branch('local')
                    self.manager['git'].get_available_update('branch')
                    self.manager['git'].remain = 35
                self.manager['git'].remain -= 1
                # Last: forced all kernel / remote branch update 
                # as git pull was run outside the program
                if self.manager['git'].pull['forced']:
                    self.manager['git'].get_all_kernel()
                    self.manager['git'].get_available_update('kernel')
                    self.manager['git'].get_branch('remote')
                    self.manager['git'].get_available_update('branch')
                    self.manager['git'].pull['forced'] = False
                        
            time.sleep(1)




def main():
    """Main daemon."""
    
    # Check or create basedir and logdir directories
    for directory in 'basedir', 'logdir':
        if not pathlib.Path(pathdir[directory]).is_dir():
            try:
                pathlib.Path(pathdir[directory]).mkdir()
            except OSError as error:
                if error.errno == errno.EPERM or error.errno == errno.EACCES:
                    log.critical(f'Got error while making directory: \'{error.strerror}: {error.filename}\'.')
                    log.critical(f'Daemon is intended to be run as sudo/root.')
                    sys.exit(1)
                else:
                    log.critical(f'Got unexcept error while making directory: \'{error}\'.')
                    sys.exit(1)
       
    # Init StateInfo
    mystateinfo = StateInfo(pathdir, runlevel, log.level)
    
    # Check state file
    mystateinfo.config()
        
    # Init dbus service
    dbusloop = GLib.MainLoop()
    dbus_session = SystemBus()
    manager = { }
    
    # Init portagemanager
    myportmanager = PortageDbus(args.sync, pathdir, runlevel, log.level)
        
    # Check sync
    myportmanager.check_sync(init_run=True)
               
    if args.git:
        log.debug('Git kernel tracking has been enable.')
        
        # Init gitmanager object through GitDbus class
        mygitmanager = GitDbus(enable=True, interval=args.pull, repo=args.repo, pathdir=pathdir, runlevel=runlevel,
                               loglevel=log.level)
               
        # Get running kernel
        mygitmanager.get_running_kernel()
        
        # Update all attributes
        mygitmanager.check_pull(init_run=True) # We need this to print log.info only one time
        mygitmanager.get_installed_kernel()
        mygitmanager.get_all_kernel()
        mygitmanager.get_available_update('kernel')
        mygitmanager.get_branch('all')
        mygitmanager.get_available_update('branch')       
    else:
        mygitmanager = GitDbus(enable=False, interval=args.pull, repo=args.repo, pathdir=pathdir, runlevel=runlevel,
                               loglevel=log.level)
        
   
    log.info('... now running.')
    manager['git'] = mygitmanager
    dbus_session.publish('net.syuppod.Manager.Git', mygitmanager)
    manager['portage'] = myportmanager
    dbus_session.publish('net.syuppod.Manager.Portage', myportmanager)
    thread = MainLoopThread(manager, name='Main Loop Thread', daemon=True) # TEST
    thread.start()
    dbusloop.run()
    thread.join()
   
    log.info('Nothing left to do, exiting')
    
    
    
if __name__ == '__main__':

    ### Parse arguments ###
    myargsparser = DaemonParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
        
    ### Creating log ###
    mainlog = MainLoggingHandler('::main::', pathdir['debuglog'], pathdir['fdlog'])
    
    if sys.stdout.isatty():
        log = mainlog.tty_run()      # create logger tty_run()
        log.setLevel(mainlog.logging.INFO)
        runlevel = 'tty_run'
        display_init_tty = ''
        # This is not working with konsole (kde)
        print('\33]0; {0} - {1}  \a'.format(name, __version__), end='', flush=True)
    else:
        log = mainlog.init_run()     # create logger init_run()
        log.setLevel(mainlog.logging.INFO)
        runlevel = 'init_run'
        display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
        # Redirect stderr to log 
        # For the moment maybe stdout as well but nothing should be print to...
        # This is NOT good if there is error before log(ger) is initialized...
        fd2 = RedirectFdToLogger(log)
        sys.stderr = fd2
       
    if args.debug and args.quiet or args.quiet and args.debug:
        log.info('Both debug and quiet opts has been enable, falling back to log level info.')
        log.setLevel(mainlog.logging.INFO)
    elif args.debug:
        log.setLevel(mainlog.logging.DEBUG)
        log.info(f'Debug has been enable. {display_init_tty}')
        log.debug('Message are from this form \'::module::class::method:: msg\'.')
    elif args.quiet:
        log.setLevel(mainlog.logging.ERROR)
    
    log.info('Starting up...')
    
    if sys.stdout.isatty():
        log.info('Interactive mode detected, all logs go to terminal.')
    
    ### MAIN ###
    main()
    
    
    
    


