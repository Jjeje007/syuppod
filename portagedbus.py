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
            </interface>
        </node>
    """
    ### sync attributes
    def get_sync_attribute(self, key):
        return str(self.sync[key])   # Best to return string over other 
       
    ### world attributes
    def get_world_attribute(self, key, subkey):
        if not subkey == 'False':   # Workaround because subkey could be str or bool ...
            return str(self.world[key][subkey])
        return str(self.world[key])
    
    ### portage attributtes
    def get_portage_attribute(self, key):
        return str(self.portage[key])
    
