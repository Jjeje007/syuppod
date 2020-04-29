# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

from portagemanager import PortageHandler
from logger import MainLoggingHandler

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
            </interface>
        </node>
    """
    def __init__(self, **kwargs):
        # Delegate arguments checking in portagemanager -> PortageHandler
        super().__init__(**kwargs)
        # add specific logger
        self.named_logger = f'::{__name__}::PortageDbus::'
        portagedbus_logger = MainLoggingHandler(self.named_logger, self.pathdir['prog_name'],
                                               self.pathdir['debuglog'], self.pathdir['fdlog'])
        self.pdb_logger = getattr(portagedbus_logger, kwargs['runlevel'])()
        self.pdb_logger.setLevel(kwargs['loglevel'])
        self.sync_state = kwargs.get('sync_state', 'disabled')
        self.world_state = kwargs.get('world_state', 'disabled')
    

    def get_sync_attribute(self, key):
        """
        Retrieve specific sync attribute and return through dbus.
        """
        self.pdb_logger.name = f'{self.named_logger}get_sync_attribute::'
        self.pdb_logger.debug(f'Requesting: {key}.')
        self.pdb_logger.debug('Returning: {0} (as string).'.format(self.sync[key]))
        return str(self.sync[key])   # Best to return string over other 


    def get_world_attribute(self, key, subkey):
        """
        Retrieve specific world attribute and return through dbus
        """
        self.pdb_logger.name = f'{self.named_logger}get_world_attribute::'
        self.pdb_logger.debug(f'Requesting: {key} | {subkey}.')
        # TODO ?? **kwargs or *args : list or dict 
        if not subkey == 'False':   # Workaround because subkey could be str or bool ...
            self.pdb_logger.debug('Returning: {0} (as string).'.format(self.world[key][subkey]))
            return str(self.world[key][subkey])
        self.pdb_logger.debug('Returning: {0} (as string).'.format(self.world[key]))
        return str(self.world[key])


    def get_portage_attribute(self, key):
        """
        Retrieve specific portage attribute and return through dbus.
        """
        self.pdb_logger.name = f'{self.named_logger}get_portage_attribute::'
        self.pdb_logger.debug(f'Requesting: {key}.')
        self.pdb_logger.debug('Returning: {0} (as string).'.format(self.portage[key]))
        return str(self.portage[key])
        
    def forced_pretend(self):
        """
        Forcing recompute of available update package depending on conditions.
        """
        self.pdb_logger.name = f'{self.named_logger}forced_pretend::'
        self.pdb_logger.debug('Got request.')
        
        # Don't run if sync is in progress (as we will run pretend after)
        if self.sync['status']:
            self.pdb_logger.debug('Failed: syncing {0}'.format(self.sync['repo']['msg']) 
                                      + ' is in progress (internal).')
            return 'sync'
        
        # same here but external sync
        if not self.sync_state == 'disabled':
            if self.sync_state:
                self.pdb_logger.debug('Failed: syncing {0}'.format(self.sync['repo']['msg']) 
                                      + ' is in progress (external).')
        else:
            self.pdb_logger.debug('External sync checker is disabled.')
            # don't return 'sync' as we don't know state so just pass to the next check
        
        # Don't run if world update is in progress
        if not self.world_state == 'disabled':
            if self.world_state:
                self.pdb_logger.debug('Failed: global update is in progress.')
                return 'world'
        else:
            self.pdb_logger.debug('External global update checker is disabled.')
            # same here we don't the state of global update ...
            
        # Don't run if pretend is running
        if self.world['status'] == 'running':
            self.pdb_logger.debug('Failed: search for available package update already in progress.')
            return 'already'
        # Don't run if pretend have just been run 
        if self.world['status'] == 'completed':
            self.pdb_logger.debug('Failed: search for available package' 
                                 + ' update have just been completed' 
                                 + ' (interval: {0}s'.format(self.world['interval'])
                                 + ' | remain: {0}s).'.format(self.world['remain']))
            return 'too_early {0} {1}'.format(self.world['interval'], self.world['remain'])
        
        # Every thing is ok :p pioufff ! ;)
        self.world['pretend'] = True
        self.world['forced'] = True
        return 'running {0}'.format(self.pathdir['pretendlog'])
