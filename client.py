#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 
# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# TODO git part
# Good Translation 
import time 
import sys
import locale
import gettext
import locale
import pathlib
import re

from argsparser import ClientParserHandler
from utils import _format_date
from utils import _format_timestamp
from portageclient import portage_state_status
from portageclient import portage_error
from portageclient import portage_count
from portageclient import portage_timestamp
from portageclient import portage_interval
from portageclient import portage_elapse_remain
from portageclient import portage_available
from portageclient import portage_packages
from portageclient import portage_last
from portageclient import portage_forced
from gitclient import _check_enable

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
    translate = True
    _ = lang_translations.gettext
except Exception as exc:
    error_msg.append('Error: unexcept error while initializing translation:')
    error_msg.append(f'Error: {exc}')
    error_msg.append(f'Error: localedir={localedir}, languages={mylocale[0]}')
    error_msg.append('Error: translation has been disabled.')
    translate = False
    _ = gettext.gettext

      
def portage_parser(args):
    """Parser for portage implentation"""
    myobject  = bus.get("net.syuppod.Manager.Portage")
    mycall = {
        'state'     :   { 'func' : portage_state_status, 'args' : [myobject, 'state', args.machine] },
                                                                # Attribute is 'update' not 'status'
        'status'    :   { 'func' : portage_state_status, 'args' : [myobject, 'update', args.machine] },
        'error'     :   { 'func' : portage_error, 'args' : [myobject, args.machine] },
        'count'     :   { 'func' : portage_count, 'args' : [myobject, args.count, args.machine] },
        'timestamp' :   { 'func' : portage_timestamp, 'args' : [myobject, args.timestamp, args.machine, translate] },
        'interval'  :   { 'func' : portage_interval, 'args' : [myobject, args.interval, args.machine, translate] },
        'elapse'    :   { 'func' : portage_elapse_remain, 'args' : [myobject, 'elapse', args.elapse, args.machine,
                                                                     translate] },
        'remain'    :   { 'func' : portage_elapse_remain, 'args' : [myobject, 'remain', args.remain, args.machine, 
                                                                     translate] },
        'available' :   { 'func' : portage_available, 'args' : [myobject, args.available, args.machine] },
        'packages'  :   { 'func' : portage_packages, 'args' : [myobject, args.machine] },
        'last'      :   { 'func' : portage_last, 'args' : [myobject, args.last, args.machine, translate] },
        'forced'    :   { 'func' : portage_forced, 'args' : [myobject, args.machine] }
        }
    
    for key in mycall:
        if args.all:
            mycall[key]['func'](*mycall[key]['args'])
        elif getattr(args, key):
            mycall[key]['func'](*mycall[key]['args'])


def git_parser(args):
    """Parser for git implentation"""
    myobject  = bus.get("net.syuppod.Manager.Git")
    mycall = {
        ''  :   { 'func' : '', 'args' : [myobject]}
        }
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

