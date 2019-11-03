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
import utils

from portagedbus import PortageDbus
from gitdbus import GitDbus
from gitmanager import check_git_dir
from logger import MainLoggingHandler
from logger import RedirectFdToLogger
from argsparser import ArgsParserHandler
from utils import UpdateInProgress

# To remimber : http://stackoverflow.com/a/11887885
# TODO : enable or disable dbus bindings. So this should only be load if dbus is enable
# If dbus is disable (default is enable) then the user should be warn that it won't get any output
# it has to get info from state file
# TODO : exit gracefully 

# TODO : debug log level ! 
try:
    from gi.repository import GLib
    from pydbus import SessionBus # Changing to SystemBus (when run as root/sudo)
    # TODO: writing Exception like that in all program
except Exception as exc:
    print(f'Got unexcept error while loading dbus bindings: {exc}')
    sys.exit(1)

__version__ = "0.1-beta1"
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
    mystateinfo = utils.StateInfo(pathdir, runlevel, log.level)
    
    # Check state file
    mystateinfo.config()
        
    # Init dbus service
    #dbusloop = GLib.MainLoop()
    #dbus_session = SessionBus()
    #objtracking = []
    
    # Init portagemanager
    myportmanager = PortageDbus(args.sync, pathdir, runlevel, log.level)
    
    # Check sync
    myportmanager.check_sync(init_run=True)
    
    if args.git:
        log.debug('Git kernel tracking has been enable.')
        
        # Init gitmanager object through GitDbus class
        mygitmanager = GitDbus(args.pull, args.repo, pathdir, runlevel, log.level)
        
        # Get running kernel
        mygitmanager.get_running_kernel()
        
        # Update all attributes
        # mygitmanager.get_last_pull() # We don't need this i think
        mygitmanager.get_installed_kernel()
        mygitmanager.get_all_kernel()
        mygitmanager.get_available_update('kernel')
        mygitmanager.get_branch('all')
        mygitmanager.get_available_update('branch')       
   
    log.info('...running.')
   
    ## Loop forever :)
    while True:
        # First: check if we have to sync
        if myportmanager.sync['status'] or myportmanager.sync['remain'] <= 0:
            # Make sure sync is not in progress
            if myportmanager.check_sync():
                # sync
                if myportmanager.dosync():
                    myupdate = UpdateInProgress('World')
                    if not myupdate.check(quiet=True):
                        # pretend world update as sync is ok :)
                        myportmanager.pretend_world()
                        # check portage update
                        myportmanager.available_portage_update()
        myportmanager.sync['remain'] -= 1 # For the moment this will not exactly be one second
                                          # Because all this stuff take more time - specially pretend_world()
        
        # Then: check available portage update
        if myportmanager.portage['remain'] <= 0:
            if myportmanager.portage['available']:
                # Make sure it's still available
                myportmanager.available_portage_update()
                # reset remain 
                myportmanager.portage['remain'] = 30
        myportmanager.portage['remain'] -= 1
        
        # Last (for portage): check if we are running world update
        if myportmanager.world['remain'] <= 0:
            myportmanager.get_last_world_update()
            if myportmanager.world['status']:
                # So pretend has to be run 
                myportmanager.pretend_world()
        myportmanager.world['remain'] -= 1
        
        
        # Git stuff
        if args.git:
            # First: pull
            if mygitmanager.pull['status'] or mygitmanager.pull['remain'] <= 0:
                # Is git in progress ?
                if mygitmanager.check_pull():
                    # This is necessary to move all kernel / branch 
                    # from new list to know list
                    mygitmanager.get_available_update('kernel')
                    mygitmanager.get_available_update('branch')
                    # Pull 
                    if mygitmanager.dopull():
                        # Pull is ok
                        # Then update all kernel / remote branch
                        mygitmanager.get_all_kernel()
                        mygitmanager.get_available_update('kernel')
                        mygitmanager.get_branch('remote')
                        mygitmanager.get_available_update('branch')
            mygitmanager.pull['remain'] -= 1
            # Then : update all local info
            if mygitmanager.remain <= 0:
                # This is a regular info update
                mygitmanager.get_installed_kernel()
                mygitmanager.get_available_update('kernel')
                mygitmanager.get_branch('local')
                mygitmanager.get_available_update('branch')
                mygitmanager.remain = 35
            mygitmanager.remain -= 1
            # Last: forced all kernel / remote branch update 
            # as git pull was run outside the program
            if mygitmanager.pull['forced']:
                mygitmanager.get_all_kernel()
                mygitmanager.get_available_update('kernel')
                mygitmanager.get_branch('remote')
                mygitmanager.get_available_update('branch')
                mygitmanager.pull['forced'] = False
                        
        time.sleep(1)


    log.info('Nothing left to do, exiting')
    #sys.exit(0)
    #dbus_session.publish('net.' + name + '.Test', trackgit)    
    #dbusloop.run()
    



if __name__ == '__main__':

    ### Parse arguments ###
    myargsparser = ArgsParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
        
    ### Creating log ###
    mainlog = MainLoggingHandler('::main::', pathdir['debuglog'], pathdir['fdlog'])
    
    if sys.stdout.isatty():
        log = mainlog.tty_run()      # create logger tty_run()
        log.setLevel(mainlog.logging.INFO)
        runlevel = 'tty_run'
        display_init_tty = ''
    else:
        log = mainlog.init_run()     # create logger init_run()
        log.setLevel(mainlog.logging.INFO)
        runlevel = 'init_run'
        display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
        # Redirect stderr to log 
        # For the moment maybe stdout as well but nothing should be print to...
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
    
    
    
    


