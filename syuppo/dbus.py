# -*- coding: utf-8 -*-
# -*- python -*- 
# Part of syuppo package
# Copyright © 2019-2021 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import logging 
from syuppo.manager import BaseHandler

# TODO TODO TODO This have to be rewrite after we move to dbus-next

class PortageDbus(BaseHandler):
    """
        <node>
            <interface name='net.syuppod.Manager.Portage'>
                <method name='get_sync_attribute'>
                    <arg type='s' name='sync_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_world_attribute'>
                    <arg type='s' name='world_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_pretend_attribute'>
                    <arg type='s' name='pretend_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_portage_attribute'>
                    <arg type='s' name='portage_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='forced_pretend'>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_sync_status'>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='get_world_update_status'>
                    <arg type='s' name='response' direction='out'/>
                </method>
                <method name='_get_debug_attributes'>
                    <arg type='s' name='debug_key' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
            </interface>
        </node>
    """
    def __init__(self, **kwargs):
        # Delegate arguments checking in portagemanager -> BaseHandler
        super().__init__(**kwargs)
        # add specific logger
        self.named_logger = f'::{__name__}::PortageDbus::'
        logger = logging.getLogger(f'{self.named_logger}init::')
        self.external_sync = False 
        self.world_state = False
    

    def get_sync_attribute(self, key):
        """
        Retrieve specific sync attribute and return through dbus.
        """
        logger = logging.getLogger(f'{self.named_logger}get_sync_attribute::')
        logger.debug(f'Requesting: {key}.')
        logger.debug('Returning: {0} (as string).'.format(self.sync[key]))
        return str(self.sync[key])   # Best to return string over other 


    def get_world_attribute(self, key):
        """
        Retrieve specific world attribute and return through dbus
        """
        logger = logging.getLogger(f'{self.named_logger}get_world_attribute::')
        logger.debug(f'Requesting: {key}')
        logger.debug('Returning: {0} (as string).'.format(self.world[key]))
        return str(self.world[key])
    
    
    def get_pretend_attribute(self, key):
        """
        Retrieve specific pretend attribute and return through dbus
        """
        logger = logging.getLogger(f'{self.named_logger}get_pretend_attribute::')
        logger.debug(f'Requesting: {key}')
        logger.debug('Returning: {0} (as string).'.format(self.pretend[key]))
        return str(self.pretend[key])


    def get_portage_attribute(self, key):
        """
        Retrieve specific portage attribute and return through dbus.
        """
        logger = logging.getLogger(f'{self.named_logger}get_portage_attribute::')
        logger.debug(f'Requesting: {key}.')
        logger.debug('Returning: {0} (as string).'.format(self.portage[key]))
        return str(self.portage[key])

        
    def forced_pretend(self):
        """
        Forcing recompute of available update package depending on conditions.
        """
        logger = logging.getLogger(f'{self.named_logger}forced_pretend::')
        logger.debug('Got request.')
        
        # Don't run if sync is in progress (as we will run pretend after)
        if self.sync['status'] == 'running':
            logger.debug('Failed: syncing {0}'.format(self.sync['repo']['msg']) 
                                      + ' is in progress (internal).')
            return 'sync'
        
        # same here but external sync
        if self.external_sync:
            logger.debug("Failed: external sync running on pid:"
                        f"{self.external_sync}")
            return 'sync'

        # Don't run if world update is in progress
        if self.world_state:
            logger.debug("Failed: global update running on pid:"
                        f" {self.world_state}")
            return 'world'
                    
        # Don't run if pretend is running
        if self.pretend['status'] == 'running':
            logger.debug('Failed: search for available package update already in progress.')
            return 'already'
        # Don't run if pretend have just been run 
        if self.pretend['status'] == 'completed':
            logger.debug('Failed: search for available package' 
                                 + ' update have just been completed' 
                                 + ' (interval: {0}s'.format(self.pretend['interval'])
                                 + ' | remain: {0}s).'.format(self.pretend['remain']))
            return 'too_early {0} {1}'.format(self.pretend['interval'], self.pretend['remain'])
        
        # Every thing is ok :p pioufff ! ;)
        with self.pretend['locks']['proceed']:
            self.pretend['proceed'] = True
        self.pretend['forced'] = True
        return 'running {0}'.format(self.pathdir['pretendlog'])
    
    def get_sync_status(self):
        """
        Retrieve sync status
        """
        logger = logging.getLogger(f'{self.named_logger}get_sync_status::')
        logger.debug('Got request.')
        
        if self.sync['status'] == 'running' or self.external_sync:
            return 'True'
        return 'False'
    
    def get_world_update_status(self):
        """
        Retrieve world update status
        """
        name = 'get_world_update_status'
        logger = logging.getLogger(f'{self.named_logger}{name}::')
        logger.debug('Got request.')
        
        if self.world_state:
            return 'True'
        return 'False'
        
    def _get_debug_attributes(self, key):
        """
        Retrieve specific attribute for debugging only
        """
        logger = logging.getLogger(f'{self.named_logger}_get_debug_attributes::')
        logger.debug(f'Requesting: {key}.')
        try:
            return str(getattr(self, key))
        except Exception as exc:
            logger.debug(f'Got exception: {exc}')
        else:
            logger.debug('Returning: {0} (as string).'.format(getattr(self, key)))
        
