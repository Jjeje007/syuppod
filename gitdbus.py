# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

import sys
from gitmanager import GitHandler
from logger import MainLoggingHandler

# pydbus is loaded from main 

# TODO try to return list / dict over str ?? 

class GitDbus(GitHandler):
    """
        <node>
            <interface name='net.syuppod.Manager.Git'>
                <method name='get_kernel_attributes'>
                    <arg type='s' name='kernel_key' direction='in'/>
                    <arg type='s' name='kernel_subkey' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_branch_attributes'>
                    <arg type='s' name='branch_key' direction='in'/>
                    <arg type='s' name='branch_subkey' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='reset_pull_error'>
                    <arg type='s' name='response' direction='out'/>
                </method>
            </interface>
        </node>
    """
    def __init__(self, **kwargs):
        self.enable = kwargs.get('enable', False)
        if self.enable:
            # Delegate kwargs arguments checking in GitHandler (gitmanager module)
            super().__init__(**kwargs)
            # check if we have pull_state (from gitmanager -> GitWatcher object)
            self.pull_state = kwargs.get('pull_state', 'disabled')
            # Init logger (even if there is already a logger in GitHandler)
            # better to have a separate logger
            # Don't override self.logger_name from GitHandler
            self.named_logger = f'::{__name__}::GitDbus::'
            # pathdir is unpack from kwargs in GitHandler
            gitdbuslogger = MainLoggingHandler(self.named_logger, self.pathdir['prog_name'], 
                                            self.pathdir['debuglog'], self.pathdir['fdlog'])
            # Don't override self.logger from gitmanager -> GitHandler
            self.gdb_logger = getattr(gitdbuslogger, kwargs['runlevel'])()
            self.gdb_logger.setLevel(kwargs['loglevel'])
        # TEST If disabled do we need one logger ??
        else:
            self.named_logger = f'::{__name__}::GitDbus::'
            # pathdir is NOT unpack from kwargs in GitHandler (because git is disabled)
            # so check here
            for key in 'pathdir', 'runlevel', 'loglevel':
                if not key in kwargs:
                    # Print to stderr :
                    # when running in init mode stderr is redirect to a log file
                    # logger is not yet initialized 
                    print(f'Error: missing argument \'{key}\' when calling gitdbus module.', file=sys.stderr)
                    print('Error: needed for logging process even if git implentation is disabled.')
                    print('Error: exiting with status \'1\'.', file=sys.stderr)
                    sys.exit(1)
            gitdbuslogger = MainLoggingHandler(self.named_logger, kwargs['pathdir']['prog_name'], 
                                            kwargs['pathdir']['debuglog'], kwargs['pathdir']['fdlog'])
            # Don't override self.logger from gitmanager -> GitHandler
            self.gdb_logger = getattr(gitdbuslogger, kwargs['runlevel'])()
            self.gdb_logger.setLevel(kwargs['loglevel'])
    
    ### Kernel attributes
    def get_kernel_attributes(self, key, subkey):
        """Retrieve specific kernel attribute and return trought dbus"""
        self.gdb_logger.name = f'{self.named_logger}get_kernel_attributes::'
        self.gdb_logger.debug(f'Requesting: {key} | {subkey}')
        
        if not self.enable:
            self.gdb_logger.debug('Cannot succeed: git implentation is disabled.')
            self.gdb_logger.error('Failed dbus request, object: GitDbus(GitHandler),' 
                                  + ' method: get_kernel_attributes,'
                                  + ' git implentation is disabled.')
            return 'disable'
        
        if not subkey == 'running':
            if subkey == 'None':
                self.gdb_logger.debug('Returning: {0} (as string).'.format(' '.join(self.kernel[key])))
                return str(' '.join(self.kernel[key]))
            self.gdb_logger.debug('Returning: {0} (as string).'.format(' '.join(self.kernel[key][subkey])))
            return str(' '.join(self.kernel[key][subkey]))
        self.gdb_logger.debug('Returning: {0} (as string).'.format(self.kernel[key][subkey]))
        return str(self.kernel[key][subkey])
    
    ### Branch attributes
    def get_branch_attributes(self, key, subkey):
        """Retrieve specific branch attribute and return trought dbus"""
        self.gdb_logger.name = f'{self.named_logger}get_branch_attributes::'
        self.gdb_logger.debug(f'Requesting: {key} | {subkey}')
        
        if not self.enable:
            self.gdb_logger.debug('Cannot succeed: git implentation is disabled.')
            self.gdb_logger.error('Failed dbus request, object: GitDbus(GitHandler),' 
                                  + ' method: get_branch_attributes,'
                                  + ' git implentation is disabled.')
            return 'disable'
        
        if subkey == 'None':
            self.gdb_logger.debug('Returning: {0} (as string).'.format(' '.join(self.branch[key])))
            return str(' '.join(self.branch[key]))
        self.gdb_logger.debug('Returning: {0} (as string).'.format(' '.join(self.branch[key][subkey])))
        return str(' '.join(self.branch[key][subkey]))
    
    ### Other attributes
    def reset_pull_error(self):
        """Reset pull error and forced pull"""
        self.gdb_logger.name = f'{self.named_logger}reset_pull_error::'
        self.gdb_logger.debug('Got request.')
        
        if not self.enable:
            self.gdb_logger.debug('Cannot succeed: git implentation is disabled.')
            self.gdb_logger.error('Failed dbus request, object: GitDbus(GitHandler),' 
                                  + ' method: reset_pull_error,'
                                  + ' git implentation is disabled.')
            return 'disable'
        
        if self.pull['status']:
            self.gdb_logger.debug('Cannot succeed: already running (internal).')
            return 'running'
        
        if not self.pull_state == 'disabled':
            if self.pull_state:
                self.gdb_logger.debug('Cannot succeed: already running (external).')
                return 'running'
        else:
            self.gdb_logger.debug('External git pull running check is disabled.')
            # don't return 'running' as we don't know state so just pass to next
        
        if not self.pull['state'] == 'Failed':
            self.gdb_logger.debug('Cannot succeed: no error found.')
            return 'no_error'
        
        if self.pull['state'] == 'Failed' and self.pull['network_error']:
            self.gdb_logger.debug('Cannot succeed: network related error.')
            return 'network'
        
        # Ok everything should be good ;)
        self.gdb_logger.debug('Succeed: error reseted.')
        self.logger.warning('Resetting pull error as requested by dbus client.')
        self.pull['state'] = 'Success'
        self.stateinfo.save('pull state', 'pull state: Success')
        return 'done'
    
