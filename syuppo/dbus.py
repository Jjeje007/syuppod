# -*- coding: utf-8 -*-
# -*- python -*- 
# Part of syuppo package
# Copyright © 2019-2021 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import logging 
from dbus_fast.service import ServiceInterface, method
from syuppo.manager import BaseHandler

# The interface used to be declared as an XML docstring, which is how pydbus
# reads it. dbus-fast builds it from the @method decorators and the type
# annotations instead, so the description now lives with each method rather
# than in a block that had to be kept in sync by hand.
INTERFACE = 'net.syuppod.Manager.Portage'


# ServiceInterface comes FIRST on purpose. BaseHandler sits at the end of a
# cooperative super().__init__() chain running through manager.py; with
# ServiceInterface last in the MRO, that chain reaches it instead of object
# and calls its __init__ with no interface name, which it refuses. Putting it
# first keeps the chain ending on object, and the explicit call below stays
# the only one initialising the interface.
class PortageDbus(ServiceInterface, BaseHandler):
    """
    Exposes the daemon state on the system bus.

    Every method returns a string: callers get to parse what they need, and
    the interface stays stable whatever the internal types become.
    """
    def __init__(self, **kwargs):
        # Delegate arguments checking in portagemanager -> BaseHandler
        BaseHandler.__init__(self, **kwargs)
        ServiceInterface.__init__(self, INTERFACE)
        # add specific logger
        self.named_logger = f'::{__name__}::PortageDbus::'
        logger = logging.getLogger(f'{self.named_logger}init::')
        self.external_sync = False 
        self.world_state = False

    @method()
    def get_sync_attribute(self, key: 's') -> 's':
        """
        Retrieve specific sync attribute and return through dbus.
        """
        logger = logging.getLogger(f'{self.named_logger}get_sync_attribute::')
        logger.debug(f'Requesting: {key}.')
        logger.debug('Returning: {0} (as string).'.format(self.sync[key]))
        return str(self.sync[key])   # Best to return string over other 


    @method()
    def get_world_attribute(self, key: 's') -> 's':
        """
        Retrieve specific world attribute and return through dbus
        """
        logger = logging.getLogger(f'{self.named_logger}get_world_attribute::')
        logger.debug(f'Requesting: {key}')
        logger.debug('Returning: {0} (as string).'.format(self.world[key]))
        return str(self.world[key])
    
    
    @method()
    def get_pretend_attribute(self, key: 's') -> 's':
        """
        Retrieve specific pretend attribute and return through dbus
        """
        logger = logging.getLogger(f'{self.named_logger}get_pretend_attribute::')
        logger.debug(f'Requesting: {key}')
        logger.debug('Returning: {0} (as string).'.format(self.pretend[key]))
        return str(self.pretend[key])


    @method()
    def get_estimate(self, key: 's') -> 's':
        """
        Estimated build time of the pending update, one field at a time:
        'seconds', 'known', 'unknown' or 'degraded'. Returns 'None' until a
        pretend has produced an estimate, or when there is nothing to update.
        An unknown key returns 'None' too, with an error logged, rather than
        a KeyError sent back over the bus.
        """
        logger = logging.getLogger(f'{self.named_logger}get_estimate::')
        logger.debug(f'Requesting: {key}.')
        # Read the reference once: pretend_world() replaces the dict as a
        # whole, so this one is consistent even if a new one lands meanwhile.
        estimate = self.pretend['estimate']
        if estimate is None:
            value = None
        elif key in estimate:
            value = estimate[key]
        else:
            logger.error(f"Unknown estimate key: '{key}'.")
            value = None
        logger.debug(f'Returning: {value} (as string).')
        return str(value)


    @method()
    def get_portage_attribute(self, key: 's') -> 's':
        """
        Retrieve specific portage attribute and return through dbus.
        """
        logger = logging.getLogger(f'{self.named_logger}get_portage_attribute::')
        logger.debug(f'Requesting: {key}.')
        logger.debug('Returning: {0} (as string).'.format(self.portage[key]))
        return str(self.portage[key])

        
    @method()
    def forced_pretend(self) -> 's':
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
    
    @method()
    def get_sync_status(self) -> 's':
        """
        Retrieve sync status
        """
        logger = logging.getLogger(f'{self.named_logger}get_sync_status::')
        logger.debug('Got request.')
        
        if self.sync['status'] == 'running' or self.external_sync:
            return 'True'
        return 'False'
    
    @method()
    def get_world_update_status(self) -> 's':
        """
        Retrieve world update status
        """
        name = 'get_world_update_status'
        logger = logging.getLogger(f'{self.named_logger}{name}::')
        logger.debug('Got request.')
        
        if self.world_state:
            return 'True'
        return 'False'
