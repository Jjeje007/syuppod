# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 


import re
import argparse
from gitmanager import check_git_dir


class ArgsParserHandler:
    """Handle arguments parsing"""
    def __init__(self, pathdir, myversion):
        prog = 'syuppod'
        self.pathdir = pathdir
        self.parser = argparse.ArgumentParser(description='Daemon which automate git kernel update.' 
                                     + ' Auto update portage tree and pretend world update for gentoo portage package manager.', 
                                     epilog='By default, %(prog)s will start in log level \'info\'. Interactive mode: log to terminal. Init mode: log to system log and debug to \'{0}\''.format(self.pathdir['debuglog']))
        self.parser.add_argument('-v', 
                            '--version', 
                            action = 'version', 
                            version = '%(prog)s: ' + myversion + 
                            ' - Copyright (C) 2019 Jérôme Venturi, <jerome dot venturi at gmail dot com> - License: GNU/GPL V3.')
        # Logging Options
        log_arg = self.parser.add_argument_group('<Log options>')
        log_arg.add_argument('-d', 
                        '--debug', 
                        help = f'start daemon in log level \'debugg\'.', 
                        action = 'store_true')
        log_arg.add_argument('-q', 
                        '--quiet', 
                        help = 'start daemon in log level \'quiet\'.', 
                        action = 'store_true')
        # Git Options
        git_arg = self.parser.add_argument_group('<Git options>')
        git_arg.add_argument('-g', 
                        '--git', 
                        help = 'enable git kernel tracking.', 
                        action = 'store_true')
        git_arg.add_argument('-r', 
                        '--repo', 
                        help = 'specify git kernel \'dir\' (default=\'/usr/src/linux\').',
                        default = '/usr/src/linux', 
                        metavar = 'dir')
        git_arg.add_argument('-p', 
                        '--pull', 
                        help = 'pull interval. Where \'int\' should be this form: 1w = 1 week, 1d = 1 day and 1h = 1 hour. Can be add together, for exemple: 2w1d12h, 2d1h... Minimum is 1d (1 day) and default is 1w (1 week).',
                        default = 604800,
                        type=self._check_args_interval,
                        metavar = 'int')
        # Portage Options
        portage_arg = self.parser.add_argument_group('<Portage options>')
        portage_arg.add_argument('-s',
                            '--sync',
                            help = 'sync interval for portage update tree. Where \'int\' should be this form: 1w = 1 week, 1d = 1 day and 1h = 1 hour. Can be add together, for exemple: 1d12h, 1w12h, 1w2d1h... Minimum and default is 1d (1 day).', 
                            metavar = 'int',
                            type=self._check_args_interval,
                            default = 86400)
    
    
    def parsing(self):
        self.args = self.parser.parse_args()
        
        if self.args.git:
            mygitdir = check_git_dir(self.args.repo)
            if not mygitdir[0]:
                if mygitdir[1] == 'dir':
                    self.parser.error(f'\'{self.args.repo}\' is not a valid path !')
                elif mygitdir[1] == 'read':
                    self.parser.error(f'\'{self.args.repo}\' is not a readable dir !')
                elif mygitdir[1] == 'git':
                    self.parser.error(f'\'{self.args.repo}\' is not a valid git repo !')
        
        return self.args


    def _check_args_interval(self, interval):
        """Checking interval typo and converting to seconds"""
        
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
                self.parser.error(f'Got invalid interval while parsing: \'{match.string}\', regex \'{match.re}\'.')
        
        # Ok so converted should be greater or equal to 86400 (mini sync interval)
        #if not converted >= 86400:
            #self.parser.error(f'Interval \'{interval}\' too small: minimum is 24 hours / 1 day !')
        #else:
        return converted

