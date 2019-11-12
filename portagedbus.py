# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

from portagemanager import PortageHandler

class PortageDbus(PortageHandler):
    # TODO : write it !
    """
        <node>
            <interface name='net.syuppod.Manager.Portage'>
                <method name='get_sync_remain'>
                    <arg type='i' name='response' direction='out'/>
                </method>
                 <method name='get_world_packages'>
                    <arg type='i' name='response' direction='out'/>
                </method>
                <method name='mod'>
                    <arg type='s' name='a' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='Quit'/>
            </interface>
        </node>
    """
    def get_sync_remain(self):
        return self.sync['remain']
    def get_world_packages(self):
        return self.world['packages']
    
    
