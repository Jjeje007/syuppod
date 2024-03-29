#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Dbus client for syuppod
# Part of syuppo package
# Copyright © 2019-2021 Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import time 
import sys
import gettext
import pathlib
import re
import logging


from syuppo.argsparser import ClientParserHandler
from syuppo.logger import addLoggingLevel
from syuppo.utils import _format_date
from syuppo.utils import _format_timestamp
from syuppo.utils import FormatTimestamp


try:
    from pydbus import SystemBus
except Exception as exc:
    print(f'Error: unexpected while loading dbus module: {exc}')
    print('Error: exiting with status \'1\'.')
    sys.exit(1)

try:
    from babel.dates import format_datetime
    from babel.dates import LOCALTZ
except Exception as exc:
    print(f'Error: unexpected while loading babel modules: {exc}')
    print('Error: exiting with status \'1\'.')
    sys.exit(1)

# Dbus server run as system
bus = SystemBus()

# Internationalization
# This doesn't need to be portable because it intend to be run only on gentoo
# For now :) (but portage can be can anywhere ...)

localedir = pathlib.Path(__file__).parent/'locale/'
if not pathlib.Path(localedir).is_dir():
    localedir = '/usr/share/locale/'

domain = gettext.textdomain('syuppoc')
gettext.install(domain)
gettext.bindtextdomain(domain, localedir)
_ = gettext.gettext

# WARNING This is for compatibilty between client and daemon
# TODO add debug option for client 
addLoggingLevel('DEBUG2', 9)

## TODO wait until daemon API is stabilized then update all this :p
## TODO better english (try it :p )

def state(myobject, opt, machine):
    """Display last tree repositories updater state or status"""
    reply = myobject.get_sync_attribute(opt)
    # For translation
    msg = {
        'success'       :   _('Success'),
        'failed'        :   _('Failed'),
        'never sync'    :   _('Program never sync'),
        'state'         :   _('Last state of the repositories syncronizer:')
        }
    if not machine:
        print('[*] {0}'.format(_(msg[opt])))
        print('    - {0}'.format(_(msg[reply])))
    else:
        print(_(msg[reply]))


def count(myobject, count, machine):
    """Display portage tree repositories updater successfully count depending on opt"""
    # This is for --all argument
    if not count:
        count = 'both'
    # Value is from module portagemanager (portagedbus)
    opt = {
        'session'   :   [ 'session' ],
        'overall'   :   [ 'count' ],
        'both'      :   [ 'count', 'session' ]
        }
    # For translation
    key_opt = { 
        'session'   :    _('Session'),
        'count'     :   _('Overall')
        }
    if not machine:
        print('[*]', _('The repositories syncronizer run successfully:'))
    for item in opt[count]:
        reply = myobject.get_sync_attribute(item)
        if machine:
            print('{0}'.format(reply))
        else:
            if int(reply) <= 1:
                msg = _('time')
            else:
                msg = _('times')
            print('    - {0}: {1} {2}'.format(_(key_opt[item]), reply, _(msg)))

     
def timestamp(myobject, formatting, machine):
    """Display last portage update as a formatted timestamp depending on formatting"""
    # This is for --all argument
    if not formatting:
        formatting = 'date'
    additionnal_msg = [ ]
    msg = ''
    # TEST return in progress if sync is running
    if myobject.get_sync_status() == 'True':
        msg = _('In progress')
        additionnal_msg.append(u"\u200B")
        additionnal_msg.append(u"\u200B")
    else:
        # Value is from dbus service (portagemanager and portagedbus)
        reply = int(myobject.get_sync_attribute('timestamp'))
        opt = re.match(r'^(unix|date.*|elapsed.*)$', formatting).group(1)
        
        # unix timestamp, easy man ! :)
        if opt == 'unix':
            msg = reply
            additionnal_msg.append(u"\u200B") # workaround for gettext ("") is reserved
            additionnal_msg.append(_('seconds since epoch (unix / posix time)'))
        elif 'date' in opt:
            msg = _format_date(reply, opt)
            additionnal_msg.append(_('The '))
            additionnal_msg.append(u"\u200B")    # workaround for gettext ("") is reserved
        elif 'elapsed' in opt:
            current_timestamp = time.time()
            elapsed = round(current_timestamp - int(reply))
            msg = _format_timestamp(elapsed, opt)
            additionnal_msg.append(_('There is '))
            additionnal_msg.append(_('ago'))
    # Now format 
    if not machine:
        print('[*]', _('Last repositories synchronization:'))
        print('    - {0}{1} {2}'.format(_(additionnal_msg[0]), _(msg), _(additionnal_msg[1])))
    else:
        print('{0}{1} {2}'.format(_(additionnal_msg[0]), _(msg), _(additionnal_msg[1])))


def interval(myobject, interval, machine):
    """Display or modify tree updater interval"""
    # This is for --all argument
    if not interval:
        interval = 'display'
    pattern = re.compile(r'^display(.*)?$')
    additionnal_msg = u"\u200B" # woraround for gettext
    # first check if we get only digit
    if isinstance(interval, int):
        # TODO !
        print('Not yet implanted')
    elif pattern.match(interval):
        reply = int(myobject.get_sync_attribute('interval'))
        if 'seconds' in interval:
            msg = reply
            additionnal_msg = (_('seconds'))
        else:
            msg = _format_timestamp(reply, interval)
        if not machine:
            print('[*]', _('Current repositories synchronization interval:'))
            print('    - {0} {1}'.format(_(msg), _(additionnal_msg)))
        else:
            print(msg)


def elapsed_remain(myobject, switch, opt, machine):
    """Display tree updater remain time formatted depending on opts"""
    # Default for --all argument
    if not opt:
        opt = 'human:3'
    translate = {
        'elapsed'   :   _('Current repositories synchronization elapsed time:'),
        'remain'    :   _('Current repositories synchronization remain time:')
        }
    reply = int(myobject.get_sync_attribute(switch))
    if 'seconds' in opt:
        msg = reply
        additionnal_msg = _('seconds')
    else:
        msg = _format_timestamp(reply, opt)
        additionnal_msg = u"\u200B" # woraround gettext
    if not machine:
        print('[*] {0}'.format(_(translate[switch])))
        print('    - {0} {1}'.format(_(msg), _(additionnal_msg)))
    else:
        print(msg)
 
 
def available(myobject, available, machine):
    """Display portage package status"""
    # Default for --all argument
    if not available:
        available = 'minimal'
    # Any way we have to check if available
    reply = myobject.get_portage_attribute('available')
    msg = u"\u200B"  # woraround gettext
    additionnal_msg = _('Portage package update status:')
    formatting = '-'
    if available == 'minimal':
        if reply == 'True':
            msg = _('Available')
        else:
            msg = _('Not available')
    elif available == 'version':
        if reply == 'True':
            msg = myobject.get_portage_attribute('latest')
            additionnal_msg = _('Available portage package update, version:')
        else:
            formatting = ''
    else:
        current = myobject.get_portage_attribute('current')
        if reply == 'True':
            latest = myobject.get_portage_attribute('latest')
            msg = _('Available (from {0} to {1})').format(current, latest)
        else:
            msg = _('Not available ({0})').format(current)
    # Now format 
    if not machine:
        print('[*] {0}'.format(_(additionnal_msg)))
        print('    {0} {1}'.format(formatting, _(msg)))
    else:
        print('{0}'.format(_(msg)))
      
      
def packages(myobject, machine):
    """Display world packages to update"""
    reply = myobject.get_pretend_attribute('packages')
    msg = _('None')
    if reply and not reply == '0':
        msg = reply
    if not machine:
        print('[*]', _('Available packages to update:'))
        print(f'    - {msg}')
    else:
        print(msg)
     
     
def last(myobject, last, machine):
    """Display informations about last world update"""
    # Default for --all argument
    if not last:
        last = 'elapsed:r:2'
        
    # Parse
    if 'state' in last:
        msg = myobject.get_world_attribute('state')
        additionnal_msg = _('Last world update state:')
    elif 'total' in last:
        msg = myobject.get_world_attribute('total')
        additionnal_msg = _('Last world update packages:')
    elif 'failed' in last:
        reply = myobject.get_world_attribute('failed')
        if reply == 'none':
            msg = _('None')
            additionnal_msg = _('Last world update failed package:')
        else:
            msg = reply
            additionnal_msg = _('Last world update failed packages:')
    elif 'start' in last:
        reply = int(myobject.get_world_attribute('start'))
        msg = _('The {0}').format(_format_date(reply, last))
        additionnal_msg = _('Last world update started:')
    elif 'stop' in last:
        reply = int(myobject.get_world_attribute('stop'))
        msg = _('The {0}').format(_format_date(reply, last))
        additionnal_msg = _('Last world update stoped:')
    elif 'elapsed' in last:
        reply = int(myobject.get_world_attribute('stop'))
        current_timestamp = time.time()
        elapsed = round(current_timestamp - reply)
        msg = _('There is {0} ago').format(_format_timestamp(elapsed, last))
        additionnal_msg = _('Last world update finished:')
    elif 'duration' in last:
        start = int(myobject.get_world_attribute('start'))
        stop = int(myobject.get_world_attribute('stop'))
        duration = round(stop - start)
        msg = _format_timestamp(duration, last)
        additionnal_msg = _('Last world update lasted:')
    # TEST return 'In progress' if running
    if myobject.get_world_update_status() == 'True':
        msg = _('In progress')
    
    # Display
    if not machine:
        print('[*] {0}'.format(_(additionnal_msg)))
        print('    - {0}'.format(msg))
    else:
        print(msg)
      

def forced(myobject, machine):
    """Forcing pretend world over dbus"""
    # This just send the message it won't wait until recompute is done:
    # ~6min on my system with ~900 packages installed
    formatter = FormatTimestamp()
    additionnal_msg = [ ]
    additionnal_msg.append('')
    additionnal_msg.append('')
    tab = '    '
    reply = myobject.forced_pretend()
    
    if 'too_early' in reply:
        split_reply = reply.split(' ')
        # Ok so interval is second item in the list
        # and remain is third
        # Ok so we have to calculate
        elapsed = int(split_reply[1]) - int(split_reply[2])
        additionnal_msg[0] = formatter(elapsed, granularity=5, rounded=False, translate=True)
        additionnal_msg[1] = formatter(int(split_reply[2]), granularity=5, rounded=False, translate=True)
        reply = 'too_early'
        if machine:
            tab = ''
    elif 'running' in reply:
        split_reply = reply.split(' ')
        # second item is where pretend.log is localized
        additionnal_msg[0] = split_reply[1]
        reply = 'running'  
    
    msg = {
        'sync'      :   _('Sync is in progress, abording...'),
        'world'     :   _('Global update is in progress, abording...'),
        'already'   :   _('Recompute already in progress, abording...'),
        'too_early' :   _('Recompute have just been completed {0} ago.\n').format(additionnal_msg[0]) +
                        _('{0}You have to wait ').format(tab) +
                        _('{0} before you can run it again.').format(additionnal_msg[1]),
        'running'   :   _('Order have been sent, see {0} for more details.').format(additionnal_msg[0])
        }
    
    if not machine:
        print('[*]', _('Force recompute available update packages:'))
        print('    - {0}'.format(_(msg[reply])))
    else:
        print(_(msg[reply]))

      
def parser(args):
    """Parser for portage implentation"""
    myobject  = bus.get("net.syuppod.Manager.Portage")
    portcaller = {
        'state'     :   { 'func': state, 'args' : [myobject, 'state', args.machine] },
        'count'     :   { 'func': count, 'args' : [myobject, args.count, args.machine] },
        'timestamp' :   { 'func': timestamp, 'args' : [myobject, args.timestamp, args.machine] },
        'interval'  :   { 'func': interval, 'args' : [myobject, args.interval, args.machine] },
        'elapsed'   :   { 'func': elapsed_remain, 'args' : [myobject, 'elapsed', args.elapsed, args.machine] },
        'remain'    :   { 'func': elapsed_remain, 'args' : [myobject, 'remain', args.remain, args.machine] },
        'available' :   { 'func': available, 'args' : [myobject, args.available, args.machine] },
        'packages'  :   { 'func': packages, 'args' : [myobject, args.machine] },
        'last'      :   { 'func': last, 'args' : [myobject, args.last, args.machine] },
        'forced'    :   { 'func': forced, 'args' : [myobject, args.machine] }
        }
    
    for key in portcaller:
        if args.all:
            # Skip forced for all args
            if key == 'forced':
                continue
            portcaller[key]['func'](*portcaller[key]['args'])
        elif getattr(args, key):
            portcaller[key]['func'](*portcaller[key]['args'])

def main():
    myargsparser = ClientParserHandler(version='dev')
    # OK for now disable argcomplete because it will NOT work in this setup
    # so we'll have to make an external file ...
    #argcomplete.autocomplete(myargsparser.parser)
    args = myargsparser.parsing()

    # Call parser
    parser(args)

