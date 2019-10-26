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
import threading
import utils
#import pdb 

#from utils import StateInfo
from portagedbus import PortageDbus
from gitdbus import GitDbus
from gitmanager import check_git_dir
from logger import MainLoggingHandler
from argsparser import ArgsParserHandler
import portagemanager


# To remimber : http://stackoverflow.com/a/11887885
# TODO : enable or disable dbus bindings. So this should only be load if dbus is enable
# If dbus is disable (default is enable) then the user should be warn that it won't get any output
# it has to get info from state file

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
    'debuglog'      :   'debug.log', # TEST changing
    'statelog'         :   'state.info',    #'/var/lib/' + name + 'state.info'
    'gitlog'        :   'git.log',  # '/var/log/' + name + 'git.log',     
    # TODO TODO TODO : add a check to see if user which run the program have enough right to perform all this operations
    'synclog'       :   'sync.log',       #'/var/log/' + name + 'sync.log'
    'pretendlog'    :   'pretend.log'     #'/var/log' + name + 'pretend.log'
    
}




class ThreadMainLoop(threading.Thread):
    """Thread for the main loop"""
    def __init__(self, shared, *args, **kwargs):
        super(ThreadMainLoop,self).__init__(*args, **kwargs)
        slef.shared = shared
        
    def run(self):
        # I'm not here...
        pass


    def main():
    """Main daemon."""
    
    # Check or create basedir and logdir directories
    for directory in 'basedir', 'logdir':
        if not pathlib.Path(pathdir[directory]).is_dir():
            try:
                pathlib.Path(pathdir[directory]).mkdir()
            except OSError as error:
                if error.errno == errno.EPERM or error.errno == errno.EACCES:
                    log.critical(f'Error while making directory: \'{error.strerror}: {error.filename}\'.')
                    log.critical(f'Daemon is intended to be run as sudo/root.')
                    sys.exit(1)
                else:
                    log.critical(f'Something went wrong while making directory: \'{error}\'.')
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
        
        # Init trackgit object through GitDbus class
        mygitmanager = GitDbus(args.pull, args.repo, pathdir, runlevel, log.level)
   
    ## Loop forever :)
    while True:
        # First: check if we have to sync
        if myportmanager.sync['status'] or myportmanager.sync['remain'] <= 0:
            # Make sure sync is not in progress
            if myportmanager.check_sync():
                # sync
                if myportmanager.dosync():
                    # pretend world update as sync is ok :)
                    myportmanager.pretend_world()
                    # check portage update
                    myportmanager.available_portage_update()
        myportmanager.sync['remain'] -= 1
        
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
                
        #time.sleep(1)
        await asyncio.sleep(10)
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        #print('Branch all remote is {0}'.format(' '.join(trackgit.branch['all']['remote'])))
        #print('Branch all remote is {0}'.format(' '.join(trackgit.branch['all']['remote'])))
        #trackgit.check_config()
        #Ok for the init just do 'both'
        #And in the loop just do 'local'
        #trackgit.get_all_branch('both')
        #trackgit.pull['status'] = 'enable'
        #trackgit.get_running_kernel()
        #trackgit.get_installed_kernel()
        #trackgit.get_all_kernel()
        #trackgit.get_available_update('branch')
        #trackgit.get_available_update('kernel')
        #trackgit.get_last_pull()
        #trackgit.check_pull()
        #if trackgit.pull['status'] == 'enable':
        #trackgit.dopull()
    
    
    #if trackportage.check_sync(init_run=True):
        #log.debug('Portage sync has been authorised')
    #else:
        #log.debug('Portage sync has been delayed')
        
    #mysyncer = trackportage.dosync()
    #log.name = 'Main'
    
    #mypretend_world = trackportage.pretend_world()
    
    #trackportage.check_sync(init_run=True)
    
    mylast_world_update = trackportage.get_last_world_update()
    
    #availableportage = trackportage.available_portage_update()
    
    #myparser = portagemanager.EmergeLogParser(log, pathdir['emergelog'], '::test::')
    
    last_sync = trackportage.check_sync(timestamp_only=True)
    
    #log.debug(f'Last sync is {last_sync}')
    #i = 1
    #for line in myparser.getlog():
        #log.debug(f'Got line n°{i}: {line}')
        #i += 1
    
    
    
    #if mylast_world_update:
        #if mylast_world_update == 'inprogress':
            #log.debug('Ok understood...')
        #else:
            #log.debug('Ok, last world update start at {0} and terminate at {1}.'.format(time.ctime(trackportage.world['start']),
                                                                                #time.ctime(trackportage.world['stop'])))
        
    
    #print('Here is the log from dosync(): {0}.'.format(trackportage.sync['log']))
        
        
        #for value in trackgit.branch['all']['local']:
        #print('Local branch is {0}'.format(' '.join(trackgit.branch['all']['local'])))
        #print('Remote branch is {0}'.format(' '.join(trackgit.branch['all']['remote'])))   
    
    log.info('Nothing left to do, exiting')
    #sys.exit(0)
    #dbus_session.publish('net.' + name + '.Test', trackgit)    
    #dbusloop.run()
    



if __name__ == '__main__':

    ### Parse arguments ###
    myargsparser = ArgsParserHandler(pathdir, __version__)
    args = myargsparser.parsing()
        
    ### Creating log ###
    mainlog = MainLoggingHandler('::main::', pathdir['debuglog'])
    
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
    
    if args.debug and args.quiet or args.quiet and args.debug:
        log.info('Both debug and quiet opts has been enable, falling back to log level info.')
        log.setLevel(mainlog.logging.INFO)
    elif args.debug:
        log.setLevel(mainlog.logging.DEBUG)
        log.info(f'Debug has been enable. {display_init_tty}')
        log.debug('Message are from this form \'::module::class::method:: msg\'.')
    elif args.quiet:
        log.setLevel(mainlog.logging.ERROR)
    
    if sys.stdout.isatty():
        log.info('Running in interactive mode, all logs go to terminal.')
    
    ### MAIN ###
    main()
    
    
    
    


