# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 


from gitmanager import GitHandler

class GitDbus(GitHandler):
    """
        <node>
            <interface name='net.syuppod.Manager.Git'>
                <method name='set_enable'>
                    <arg type='s' name='response' direction='out'/>
                </method>
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
        
    def set_enable(self):
        """Enable git manager"""
        if self.enable:
            return 'already'
        else:
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
    
    ### Kernel attributes
    def get_kernel_attributes(self, key, subkey):
        """Retrieve specific kernel attribute and return trought dbus"""
        if not self.enable:
            return 'disable'
        if not subkey == 'running':
            return str(' '.join(self.kernel[key][subkey]))
        return str(self.kernel[key][subkey])
    
    ### Branch attributes
    def get_branch_attributes(self, key, subkey):
        """Retrieve specific branch attribute and return trought dbus"""
        if not self.enable:
            return 'disable'
        return str(' '.join(self.branch[key][subkey]))
    
