#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3


import time 
import sys
import locale
import gettext
import locale
import pathlib
import re

from argsparser import ClientParserHandler
from utils import FormatTimestamp

# TODO Force sync :)
# TODO git part
# TODO portage world part !!


try:
    from pydbus import SystemBus
except Exception as exc:
    print(f'Got unexcept error while loading dbus module: {exc}')
    sys.exit(1)

try:
    from babel.dates import format_datetime
    from babel.dates import LOCALTZ
except Exception as exc:
    print(f'Got unexcept error while loading babel modules: {exc}')
    sys.exit(1)

# Dbus server run as system
bus = SystemBus()

mylocale = locale.getdefaultlocale()
error_msg = [ ]
# see --> https://stackoverflow.com/a/10174657/11869956 thx
#localedir = os.path.join(os.path.dirname(__file__), 'locales')
# or python > 3.4:
try:
    localedir = pathlib.Path(__file__).parent/'locales'
    lang_translations = gettext.translation('client', localedir, languages=[mylocale[0]])
    lang_translations.install()
    _ = lang_translations.gettext
except Exception as exc:
    error_msg.append('Error: unexcept error while initializing translation:')
    error_msg.append(f'Error: {exc}')
    error_msg.append(f'Error: localedir={localedir}, languages={mylocale[0]}')
    error_msg.append('Error: translation has been disabled.')
    _ = gettext.gettext



def portage_state_status(myobject, opt, machine):
    """Display last tree repositories updater state or status"""
    reply = myobject.get_sync_attribute(opt)
    # For translation
    msg = {
        'Success'       :   _('Success'),
        'Failed'        :   _('Failed'),
        'In Progress'   :   _('In Progress'),
        # FIXME: this has been fix in the last git version 
        # and should be 'Finish'
        'Finished'      :   _('Finish'),
        'state'         :   _('Last state of the tree repositories updater:'),
        'update'        :   _('Last status of the tree repositories updater:')
        }
    if not machine:
        print('[*] {0}'.format(_(msg[opt])))
        print('    - {0}'.format(_(msg[reply])))
    else:
        print(_(msg[reply]))


def portage_error(myobject, machine):
    """Display last tree repositories updater error count"""
    reply = int(myobject.get_sync_attribute('error'))
    if not machine:
        print(_('[*] Current error count for the updater\'s tree repositories:'))
        msg = _('time')
        if reply > 1:
            msg = _('times')
        print('    - {0} {1}'.format(reply, _(msg)))
    else:
        print(reply)


def portage_count(myobject, count, machine):
    """Display portage tree repositories updater successfully count depending on opt"""
    # Value is from module portagemanager (portagedbus)
    opt = {
        'session'   :   [ 'current_count' ],
        'overall'   :   [ 'count' ],
        'both'      :   [ 'count', 'current_count' ]
        }
    # For translation
    key_opt = { 
        'current_count' :   _('Session'),
        'count'         :   _('Overall')
        }
    if not machine:
        print(_('[*] Tree repositories updater run successfully:'))
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


def _format_timestamp(seconds, opt):
    """Helper for formatting timestamp depending on opts"""
    # Default values
    rounded = True
    granularity = 2
    pattern = re.compile(r'^\w+(\:r|\:u)?(\:\d)?$')
    for match in pattern.finditer(opt):
        if match.group(1) == ':u':
            rounded = False
        if match.group(2):
            granularity = match.group(2)
            # remove ':'
            granularity = int(granularity[1:])
    #print(f'Rounded is {rounded} and Granularity is {granularity}')
    myformatter = FormatTimestamp()
    msg = myformatter.convert(seconds, granularity=granularity, rounded=rounded)
    return msg 


def _format_date(timestamp, opt):
    """Helper for formatting date"""
    # Default value
    display='long'
    trans = { 
            ':s' :   'short',
            ':m' :   'medium',
            ':l' :   'long',
            ':f' :   'full'
            }
    # Parse opt to found if display has to be modified
    pattern = re.compile(r'^\w+(\:\w)?')
    for match in pattern.finditer(opt):
        if match.group(1):
            display = match.group(1)
            display = trans[display]
    
    mydate = format_datetime(int(timestamp), tzinfo=LOCALTZ, format=display, locale=mylocale[0])
    if display == 'long':
        # HACK This is a tweak, user should be aware
        # This removed :  +0100 at the end of 'long' output
        mydate = mydate[:-6]
    return mydate
     

def portage_timestamp(myobject, formatting, machine):
    """Display last portage update as a formatted timestamp depending on formatting"""
    # Value is from dbus service (portagemanager and portagedbus)
    reply = int(myobject.get_sync_attribute('timestamp'))
    opt = re.match(r'^(unix|date.*|elapse.*)$', formatting).group(1)
    additionnal_msg = [ ]
    # unix timestamp, easy man ! :)
    if opt == 'unix':
        msg = reply
        additionnal_msg.append('')
        additionnal_msg.append(_('seconds since epoch (unix / posix time)'))
    elif 'date' in opt:
        msg = _format_date(reply, opt)
        additionnal_msg.append(_('The '))
        additionnal_msg.append('')
    elif 'elapse' in opt:
        current_timestamp = time.time()
        elapsed = round(current_timestamp - int(reply))
        msg = _format_timestamp(elapsed, opt)
        additionnal_msg.append(_('There is '))
        additionnal_msg.append(_('ago'))
    # Now format 
    if not machine:
        print(_('[*] Last tree repositories update:'))
        print('    - {0}{1} {2}'.format(_(additionnal_msg[0]), _(msg), _(additionnal_msg[1])))
    else:
        print(msg)


def portage_interval(myobject, interval, machine):
    """Display or modify tree updater interval"""
    pattern = re.compile(r'^display(.*)?$')
    additionnal_msg = ''
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
            print(_('[*] Current tree repositories update interval:'))
            print('    - {0} {1}'.format(_(msg), _(additionnal_msg)))
        else:
            print(msg)

def portage_elapse_remain(myobject, switch, msg, opt, machine):
    """Display tree updater remain time formatted depending on opts"""
    additionnal_msg = [ ]
    additionnal_msg.append(msg)
    reply = int(myobject.get_sync_attribute(switch))
    if 'seconds' in opt:
        msg = reply
        additionnal_msg.append(_('seconds'))
    else:
        msg = _format_timestamp(reply, opt)
        additionnal_msg.append('')
    if not machine:
        print(_('[*] Current tree repositories updater {0} time:').format(_(additionnal_msg[0])))
        print('    - {0} {1}'.format(_(msg), _(additionnal_msg[1])))
    else:
        print(msg)
        
def portage_available(myobject, available, machine):
    """Display portage package status"""
    # Any way we have to check if available
    reply = myobject.get_portage_attribute('available')
    msg = ''
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
        print(_('[*] {0}').format(_(additionnal_msg)))
        print('    {0} {1}'.format(formatting, _(msg)))
    else:
        print('{0}'.format(_(msg)))
        
def portage_packages(myobject, machine):
    """Display world packages to update"""
    reply = myobject.get_world_attribute('packages', 'False')
    msg = _('None')
    if reply:
        msg = reply
    if not machine:
        print(_('[*] Available packages to update:'))
        print(f'    - {msg}')
    else:
        print(msg)
        
def portage_last(myobject, last, machine):
    """Display informations about last world update"""
    if 'state' in last:
        msg = myobject.get_world_attribute('last', 'state')
        additionnal_msg = _('Last world update state:')
    elif 'total' in last:
        msg = myobject.get_world_attribute('last', 'total')
        additionnal_msg = _('Last world update packages:')
    elif 'failed' in last:
        reply = myobject.get_world_attribute('last', 'failed')
        if reply == '0':
            msg = _('None')
            additionnal_msg = _('Last world update failed package:')
        else:
            msg = reply
            additionnal_msg = _('Last world update failed packages:')
    elif 'start' in last:
        reply = int(myobject.get_world_attribute('last', 'start'))
        msg = _('The {0}').format(_format_date(reply, last))
        additionnal_msg = _('Last world update started:')
    elif 'stop' in last:
        reply = int(myobject.get_world_attribute('last', 'stop'))
        msg = _('The {0}').format(_format_date(reply, last))
        additionnal_msg = _('Last world update stoped:')
    elif 'elapse' in last:
        reply = int(myobject.get_world_attribute('last', 'stop'))
        current_timestamp = time.time()
        elapsed = round(current_timestamp - reply)
        msg = _('There is {0} ago').format(_format_timestamp(elapsed, last))
        additionnal_msg = _('Last world update finished:')
    elif 'duration' in last:
        start = int(myobject.get_world_attribute('last', 'start'))
        stop = int(myobject.get_world_attribute('last', 'stop'))
        duration = round(stop - start)
        msg = _format_timestamp(duration, last)
        additionnal_msg = _('Last world update lasted:')
    
    # Now display
    if not machine:
        print(_('[*] {0}').format(_(additionnal_msg)))
        print('    - {0}'.format(msg))
    else:
        print(msg)
        
def portage_parser(args):
    """Parser for portage implentation"""
    myobject  = bus.get("net.syuppod.Manager.Portage")
    if args.state:
        portage_state_status(myobject, 'state', args.machine)
    if args.status:
        # Attribute is 'update' not 'status'
        portage_state_status(myobject, 'update', args.machine)
    if args.error:
        portage_error(myobject, args.machine)
    if args.count:
        portage_count(myobject, args.count, args.machine)
    if args.timestamp:
        portage_timestamp(myobject, args.timestamp, args.machine)
    if args.interval:
        portage_interval(myobject, args.interval, args.machine)
    if args.elapse:
        # FIXME : should be 'elapse', fix in latest git version
        portage_elapse_remain(myobject, 'elasped', _('elapse'), args.elapse, args.machine)
    if args.remain:
        portage_elapse_remain(myobject, 'remain', _('remain'), args.remain, args.machine)
    if args.available:
        portage_available(myobject, args.available, args.machine)
    if args.packages:
        portage_packages(myobject, args.machine)
    if args.last:
        portage_last(myobject, args.last, args.machine)
    if args.all:
        portage_state_status(myobject, 'state', args.machine)
        # Attribute is 'update' not 'status'
        portage_state_status(myobject, 'update', args.machine)
        portage_error(myobject, args.machine)
        # Defaults are from module argsparser class ClientParserHandler
        portage_count(myobject, 'both', args.machine)
        portage_timestamp(myobject, 'date', args.machine)
        portage_interval(myobject, 'display', args.machine)
        portage_elapse_remain(myobject, 'elasped', _('elapse'), 'human:3', args.machine)
        portage_elapse_remain(myobject, 'remain', _('remain'), 'human:3', args.machine)
        portage_available(myobject, 'minimal', args.machine)
        

def _check_enable(myobject):
    """Check if git implantation is enable"""
    # This has to be call every time we need to access
    # method from Git bus object - to make sure it's enable
    reply = myobject.get_set_enable('get')
    if reply == 'True':
        return True
    else:
        return False
    

def git_parser(args):
    """Parser for git implentation"""
    
    
    myobject  = bus.get("net.syuppod.Manager.Git")
    reply = myobject.get_set_enable('set')
    print(f'Reply is {reply}')


### MAIN ###

myargsparser = ClientParserHandler(version='dev')
args = myargsparser.parsing()

# Caller for subcomand
mycall = { 'portage'    :   portage_parser,
           'git'        :   git_parser
           }

# Print errors if not -q
if not args.quiet:
    for error in error_msg:
        print(error, file=sys.stderr)

# Call the selected subcommand
mycall[args.subparser_name](args)

