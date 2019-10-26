# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

from portagemanager import PortageHandler

class PortageDbus(PortageHandler):
    # TODO : write it !
    """
        <node>
            <interface name='net.lew21.pydbus.ClientServerExample'>
                <method name='publish_branch_old_local'>
                    <arg type='a{ss}' name='response' direction='out'/>
                </method>
                <method name='mod'>
                    <arg type='s' name='a' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='Quit'/>
            </interface>
        </node>
    """
