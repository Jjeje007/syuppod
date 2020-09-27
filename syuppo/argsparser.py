# -*- coding: utf-8 -*-
# -*- python -*-
# PYTHON_ARGCOMPLETE_OK
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import re
import argparse
import sys
import argcomplete

## TODO TODO TODO for client part, what about not just checking if option are ok
#                 we should parse it, and return for exemple dict? 
# TODO: add --dry-run opt to not write to statefile 
# TODO  argcomplete: make advance opts available
# TODO  make opt word not all required : like argparse default if --available you can write --a 
#       and it's match if there nothing eles which start by --a . Same here with for exemple:
#       --count : this can be both|session|overall -> for both you could write 'b' or 'bo' or 'bot' or ...

class CustomArgsCheck:
    """
    Advanced arguments checker which implant specific parsing
    """
    def __init__(self):
        # this is shared across method
        self.shared_timestamp = '(?:\:r|\:u)?(?:\:[1-5])?'
        self.shared_date = '(?:\:s|\:m|\:l|\:f)?'
    
    def _check_args_interval(self, interval):
        """
        Checking interval typo and converting to seconds
        """
        
        # By pass to implant ClientParserHandler args parse 
        if 'display' in interval:
            pattern = re.compile(r'^display(?:\:r|\:u|\:seconds)?(?:\:[1-5])?$')
            if not pattern.match(interval):
                self.parser.error(f'\'{interval}\' is not an valid interval !')
            return interval
        
        pattern = re.compile(r'^(?:\d+(?:d|w|h){1})+$')
        if not pattern.match(interval):
            self.parser.error(f'\'{interval}\' is not an valid interval !')
        pattern = re.compile(r'(\d+)(\w{1})')
        converted = 0
        for match in pattern.finditer(interval):
            if match.group(2) == 'h':
                converted += int(match.group(1)) * 3600
            elif match.group(2) == 'd':
                converted += int(match.group(1)) * 86400
            elif match.group(2) == 'w':
                converted += int(match.group(1)) * 604800
            else:
                # This should'nt happend :)
                self.parser.error(f'Got invalid interval while parsing: \'{match.string}\', ', 
                                  f'regex \'{match.re}\'.')
        # Ok so converted should be greater or equal to 86400 (mini sync/git interval)
        if converted < 86400:
            self.parser.error(f'Interval \'{interval}\' too small: minimum is 24 hours / 1 day !')
        return converted
    
    def _check_args_portage_count(self, count):
        """Checking portage count argument"""
        pattern = re.compile(r'^both$|^session$|^overall$')
        if not pattern.match(count):
            self.parser.error(f'invalid choice: \'{count}\' (choose from \'both\', \'session\' or \'overall\').')
        return count
    
    def _check_args_portage_timestamp(self, timestamp):
        """Checking portage timestamp argument"""
        pattern = re.compile(r'^date{0}$|^elapsed{1}$|^unix$'.format(self.shared_date, self.shared_timestamp))
        if not pattern.match(timestamp):
            self.parser.error(f'invalid choice: \'{timestamp}\' (choose from \'date\', \'elapsed\' or \'unix\').')
        return timestamp
    
    def _check_args_portage_elapse_remain(self, opt):
        """Checking portage elapsed or remain argument"""
        pattern = re.compile(r'^seconds$|^human{0}$'.format(self.shared_timestamp))
        if not pattern.match(opt):
            self.parser.error(f'invalid choice: \'{opt}\' (choose from \'seconds\' or \'human\').')
        return opt
    
    def _check_args_portage_available(self, available):
        """Checking portage available argument"""
        pattern = re.compile(r'^full$|^version$|^minimal$')
        if not pattern.match(available):
            self.parser.error(f'invalid choice: \'{available}\' (choose from \'full\', \'version\' or' 
                                                                 f' \'minimal\').')
        return available
    
    def _check_args_portage_last(self, last):
        """Checking portage last argument"""
        pattern = re.compile(r'^state$|^failed$|^total$|'
                             r'^start{0}$|^stop{0}$|'.format(self.shared_date)
                             + r'^elapsed{0}$|^duration{0}$'.format(self.shared_timestamp))
        if not pattern.match(last):
            self.parser.error(f'invalid choice: \'{last}\' (choose from \'state\', \'start\', \'stop\', \'total\' '
                                                          f'\'failed\', \'elapsed\' or \'duration\').')
        return last


class DaemonParserHandler(CustomArgsCheck):
    """
    Handle daemon arguments parsing
    """
    def __init__(self, pathdir, version):
        prog = 'syuppod'
        self.pathdir = pathdir
        self.parser = argparse.ArgumentParser(prog=prog,
                                              description='Daemon which auto update portage tree' 
                                              ' and pretend world update for gentoo portage package manager.', 
                                              epilog='By default, %(prog)s will start in log level \'info\'.' 
                                              ' Interactive mode: log to terminal. Init mode: log to system' 
                                              ' log, debug to \'{0}\''.format(self.pathdir['debuglog']) 
                                              + ' and stderr to \'{0}\'.'.format(self.pathdir['fdlog']))
        # Optionnal arguments 
        # Changing title to reflect other title 
        # thx --> https://stackoverflow.com/a/16981688/11869956
        self.parser._optionals.title = '<optional arguments>'
        self.parser.add_argument('-v', 
                            '--version', 
                            action = 'version', 
                            version = '%(prog)s: version ' + version 
                            + ' - Copyright (C) 2019-2020 Jérôme Venturi,' 
                            ' <jerome dot venturi at gmail dot com> - License: GNU/GPL V3.')
        # Logging Options
        log_arg = self.parser.add_argument_group('<log options>')
        log_arg.add_argument('-d', 
                        '--debug', 
                        help = f'start daemon in log level \'debugg\'.', 
                        action = 'store_true')
        log_arg.add_argument('-q', 
                        '--quiet', 
                        help = 'start daemon in log level \'quiet\'.', 
                        action = 'store_true')
        # Portage Options
        portage_arg = self.parser.add_argument_group('<portage options>')
        portage_arg.add_argument('-s',
                            '--sync',
                            help = 'sync interval for portage update tree. Where \'int\' should be this form: 1w = 1 week, 1d = 1 day and 1h = 1 hour. Can be add together, for exemple: 1d12h, 1w12h, 1w2d1h... Minimum and default is 1d (1 day).', 
                            metavar = 'int',
                            type=self._check_args_interval,
                            default = 86400)
        advanced_debug = self.parser.add_argument_group('<advanced debug options>')
        #advanced_debug.add_argument('--fakeinit',
                                    #help = 'Start daemon like it\'s started by running'
                                            #+ ' /etc/init.d/syuppod/ start. So this is only usefull if started from terminal.',
                                    #action = 'store_true')
        advanced_debug.add_argument('--dryrun',
                                    help = """Run daemon without writing/creating anything to statefile or logs.
                                            This intend to be run from terminal.""",
                                    action = 'store_true')
    def parsing(self):
        self.args = self.parser.parse_args()
        return self.args

# TODO : Interactive shell  : https://code-maven.com/interactive-shell-with-cmd-in-python

class ClientParserHandler(CustomArgsCheck):
    """Handle client arguments parsing"""
    def __init__(self, version):
        # Init super class
        super().__init__()
        prog = 'syuppoc'
        self.parser = argparse.ArgumentParser(prog=prog,
                                              description='Dbus client for syuppod daemon. Control and '
                                              ' retrieve informations from an already running daemon.')
        ## Global options
        self.parser.add_argument('-v', 
                                '--version', 
                                action = 'version', 
                                version = '%(prog)s: version ' + version + 
                                ' - Copyright (C) 2019-2020 Jérôme Venturi,' 
                                ' <jerome dot venturi at gmail dot com> - License: GNU/GPL V3.')
        self.parser.add_argument('-m',
                                 '--machine',
                                 action = 'store_true',
                                 help = 'display output to machine language.')
        self.parser._optionals.title = '<optional arguments>'
        portage_args   = self.parser.add_argument_group('<portage options>')
        portage_args.add_argument('--state',
                                  action = 'store_true',
                                  help = 'Display state of the last update tree.')
        portage_args.add_argument('--status',
                                  action = 'store_true',
                                  help = 'Display current status from the updater tree.')
        portage_args.add_argument('--error',
                                  action = 'store_true',
                                  help = 'Display current error count.')
        portage_args.add_argument('--count',
                                  metavar = 'cnt',
                                  nargs = '?',
                                  const = 'both',
                                  choices = [ 'session', 'overall', 'both' ],
                                  #type = self._check_args_portage_count,
                                  help = 'Display successfully update count. Where \'cnt\' should be one of: ' 
                                  '\'session\', \'overall\' or \'both\'. \'session\' is count from current '
                                  'session and \'overall\' from the first run ever. Default is \'both\' with in '
                                  'order: \'overall\', \'session\').')                                  
        portage_args.add_argument('--available',
                                  metavar = 'avl',
                                  nargs = '?',
                                  const = 'minimal',
                                  type = self._check_args_portage_available,
                                  help = 'Display available portage\'s package update. Where \'avl\' could be '
                                  'one of: \'full\', \'version\' or \'minimal\'. \'full\' will display '
                                  'available or not available follow by installed package version and  ' 
                                  'available package version (if any). \'version\' will display package '
                                  'version if available (otherwise: nothing). \'minimal\' will display just'
                                  ' available or not available.')
        portage_args.add_argument('--timestamp',
                                  metavar = 'tsp',
                                  nargs = '?',
                                  const = 'date:m',
                                  type = self._check_args_portage_timestamp,
                                  help = 'Display last update timestamp. Where \'tsp\' should be one of: '
                                  '\'date[:date_format]\', \'elapsed[:elapsed_format]\' or \'unix\'. '
                                  '\'date\' output an formatted localized date, optionnal tweak using '
                                  '\'[:date_format]\': [:s]hort, [:m]edium, [:l]ong or [:f]ull (default: [:l]'
                                  'ong). \'elapsed\' an localized elapsed time, optional rounded and tweak using '
                                  '\'[:elapsed_format]\' (with: [:r]ounded, [:u]nrounded and [:1]-5 to choose '
                                  'granularity level - this can be collapse, ex: [:r:5]). \'unix\' an unix '
                                  'timestamp. Default: \'date\' with date_format = medium. ')
        portage_args.add_argument('--interval',
                                  metavar = 'int',
                                  nargs = '?',
                                  const = 'display',
                                  type = self._check_args_interval,
                                  help = 'Display or modify current tree\'s updater interval. Where \'int\' '
                                  'should be this form: 1w = 1 week, 1d = 1 day and 1h = 1 hour. Can be add ' 
                                  'together, for exemple: 1d12h, 1w12h, 1w2d1h... Minimum is 1d (1 day). If '
                                  '\'int\' is missing than display current interval. Optionnal seconds or ' 
                                  'rounded and tweak can be execute using \'display[:format]\' argument with:'
                                  ' [:seconds], [:r]ounded, [:u]nrounded and [:1]-5 to choose granularity level'
                                  ' - this can be collapse, ex: [:r:5]). Default is [:r]ounded and granularity '
                                  'is [:2]. ' 'Exemple: \'display:u:3\'.' )
        portage_args.add_argument('--elapsed',
                                  metavar = 'ela',
                                  nargs = '?',
                                  const = 'human:3',
                                  type = self._check_args_portage_elapse_remain,
                                  help = 'Display elapsed time since last update tree. Where \'ela\' should '
                                  'be one of: \'human\' or \'seconds\'. \'human\' output an formatted elapsed '
                                  'rounded time. Optionnal unrounded or tweak can be execute using: [:r]ounded'
                                  ', [:u]nrounded and [:1]-5 to choose granularity level - this can be collapse,'
                                  ' ex: [:r:5]. Default is human, [:r]ounded and granularity is [:3].')
        portage_args.add_argument('--remain',
                                  metavar = 'rmn',
                                  nargs = '?',
                                  const = 'human:3',
                                  type = self._check_args_portage_elapse_remain,
                                  help = 'Display remain time since last update tree. Where \'ela\' should '
                                  'be one of: \'human\' or \'seconds\'. \'human\' output an formatted rounded '
                                  ' remain time. Optionnal unrounded or tweak can be execute using: [:r]ounded'
                                  ', [:u]nrounded and [:1]-5 to choose granularity level - this can be collapse,'
                                  ' ex: [:r:5]. Default is human, [:r]ounded and granularity is [:3].')
        portage_args.add_argument('--packages',
                                  action = 'store_true',
                                  help = 'Display packages\'s update related informations from `emerge --pretend`.'
                                  ' This will NOT run an `emerge --pretend` in a background.')
        portage_args.add_argument('--last',
                                  metavar = 'lst',
                                  nargs = '?',
                                  const = 'elapsed:r:2',
                                  type = self._check_args_portage_last,
                                  help = 'Display last world update informations. Where \'lst\' could be: '
                                  '\'state\', \'start[:date]\', \'stop[:date]\', \'total\', \'failed\', '
                                  '\'elapsed[:format]\' and \'duration[:format]\'. \'state\' could be in completed if'
                                  ' last world update didn\'t failed, incompleted '
                                  'if it failed and partial if it failed but the switch --keep-going was enable (so it'
                                  ' restart). \'total\' is the total package which was update. \'failed\' is  count ('
                                  'name of the package(s) which failed). '
                                  '\'[:date_format]\': [:s]hort, [:m]edium, [:l]ong or [:f]ull (default: [:l]ong). '
                                  '\'[format]\' could be: [:r]ounded, [:u]nrounded and '
                                  '[:1]-5 to choose granularity level - this can be collapse, ex: [:u:3]. Default: '
                                  '\'elapsed:r:2\'')
        portage_args.add_argument('--forced',
                                  action = 'store_true',
                                  help = 'Force recalculation of the packages informations. This will send forced command' 
                                  ' to daemon. Normally, this is done automatically when syuppod sync or when world update' 
                                  ' have been run.')
        portage_args.add_argument('--all',
                                  action = 'store_true',
                                  help='Display all the informations in one time with defaults options.')
        
    def parsing(self):
        argcomplete.autocomplete(self.parser)
        args = self.parser.parse_args()
        # Print usage if no arg has been given
        noarg = True
        for arg in vars(args):
            if getattr(args, arg):
                noarg = False
                break
        if noarg:
            self.parser.print_usage(file=sys.stderr)
            self.parser.exit(status=1)
        # everything is ok ;)
        return args

