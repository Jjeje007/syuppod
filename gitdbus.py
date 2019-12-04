# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 


from gitmanager import GitHandler

class GitDbus(GitHandler):
    """
        <node>
            <interface name='net.syuppod.Manager.Git'>
                <method name='get_set_enable'>
                    <arg type='s' name='action' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
            </interface>
        </node>
    """
    def __init__(self, **kwargs):
        self.enable = kwargs.get('enable', False)
        # Needed to init gitmanager (GitHandler) at runtime
        # Saved and wait before calling super()
        self.kwargs = kwargs
        if self.enable:
            super().__init__(**self.kwargs)
        
    def get_set_enable(self, action):
        if self.enable:
            if action == 'get':
                return 'True'
            elif action == 'set':
                return 'already'
        else:
            if action == 'get':
                return 'False'
            elif action == 'set':
                # Init GitHandler (gitmanager module)
                super().__init__(**self.kwargs)
                # Ok so update all attributes same 
                # as main module and main() function
                # Get running kernel
                self.get_running_kernel()
                # Update all attributes
                self.check_pull(init_run=True) # We need this to print log.info only one time
                self.get_installed_kernel()
                self.get_all_kernel()
                self.get_available_update('kernel')
                self.get_branch('all')
                self.get_available_update('branch')
                # Ok init is done so we can set it 
                # so main module -> class MainLoopThread
                # can do the work :)
                self.enable = True
                return 'done'
