# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

from portagemanager import PortageHandler

class PortageDbus(PortageHandler):
    """
        <node>
            <interface name='net.syuppod.Manager.Portage'>
                <method name='get_sync_attribute'>
                    <arg type='s' name='sync_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_world_attribute'>
                    <arg type='s' name='world_key' direction='in'/>
                    <arg type='s' name='world_subkey' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_portage_attribute'>
                    <arg type='s' name='portage_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='forced_pretend'>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='forced_sync'>
                    <arg type='s' name='response' direction='out'/>
                </method>
            </interface>
        </node>
    """
    ### sync attributes
    def get_sync_attribute(self, key):
        return str(self.sync[key])   # Best to return string over other 
       
    ### world attributes
    def get_world_attribute(self, key, subkey):
        # Ok this has to be done this way:
        # like **kwargs or *args : list or dict 
        if not subkey == 'False':   # Workaround because subkey could be str or bool ...
            return str(self.world[key][subkey])
        return str(self.world[key])
    
    ### portage attributtes
    def get_portage_attribute(self, key):
        return str(self.portage[key])
    
    ### forced method
    def forced_sync(self):
        # TODO: some idea to make this 'good'
        # We could force sync one time every 24H 
        # But only 2 times a week . we think it fair enough.
        self.log.info('This is a test from portagedbus')
        return 'ok'
    
    def forced_pretend(self):
        # Every time if not in progress and sync also 
        # TODO: this should be async also 
        # Look like pydbus is not...
        # https://github.com/ldo/dbussy
        if not self.world['pretend']: # and not self.sync[:
            #return 'Order has been sent, see log in {0}'.format(self.pathdir['pretendlog'])
            self.pretend_world()
            return 'completed'
        return 'already in progress'
    
    # TODO: some ideas : we could propose applied pretend update
    #       this mean lauching terminal through dbus and asking root passw / sudo ?
    
