# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 


from gitmanager import GitHandler

class GitDbus(GitHandler):
    """
        <node>
            <interface name='net.syuppod.Manager.Git'>
                <method name='check_enable'>
                    <arg type='b' name='response' direction='out'/>
                </method>
                <method name='mod'>
                    <arg type='s' name='a' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
            </interface>
        </node>
    """
    def __init__(self, enable=True, **kwargs):
        self.enable = enable
        if self.enable:
            super().__init__(**kwargs)
        
    def check_enable(self):
        if self.enable:
            return True
        return False
