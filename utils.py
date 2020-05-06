# -*- coding: utf-8 -*-
# -*- python -*- 
# Copyright © 2019,2020: Venturi Jérôme : jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

import os
import pathlib
import re
import errno
import sys
import time
import signal
import gettext
import locale

from ctypes import cdll
from logger import MainLoggingHandler


try:
    from babel.dates import format_datetime
    from babel.dates import LOCALTZ
except Exception as exc:
    print(f'Got unexcept error while loading babel modules: {exc}')
    sys.exit(1)



mylocale = locale.getdefaultlocale()
# see --> https://stackoverflow.com/a/10174657/11869956 thx
#localedir = os.path.join(os.path.dirname(__file__), 'locales')
# or python > 3.4:
#try:
localedir = pathlib.Path(__file__).parent/'locales'
lang_translations = gettext.translation('utils', localedir, languages=[mylocale[0]], fallback=True)
lang_translations.install()
_ = lang_translations.gettext

#print(f'lang_translations is {lang_translations}')

#except Exception as exc:
    #print('Error: unexcept error while initializing translation:', file=sys.stderr)
    #print(f'Error: {exc}', file=sys.stderr)
    #print(f'Error: localedir={localedir}, languages={mylocale[0]}', file=sys.stderr)
    #print('Error: translation has been disabled.', file=sys.stderr)
    #_ = gettext.gettext

class StateInfo:
    """Write, edit or get info to and from state file"""
    def __init__(self, pathdir, runlevel, loglevel):
        self.pathdir = pathdir
                
        # Init logger
        self.logger_name = f'::{__name__}::StateInfo::'
        mainlogger = MainLoggingHandler(self.logger_name, self.pathdir['prog_name'], 
                                        self.pathdir['debuglog'], self.pathdir['fdlog'])
        self.logger = getattr(mainlogger, runlevel)()
        self.logger.setLevel(loglevel)
        
        self.stateopts = (
            # '# Wrote by syuppod version: __version__' TODO : Writing version so we can know which version wrote the state file 
            # TODO : '# Pull Opts',
            'pull count: 0', 
            'pull network_error: 0',
            'pull retry: 0',
            'pull state: never pull',
            'pull last: 0',
            # Setting default to '0.0' as StrictVersion compare will failed if only '0' or string
            # '0.0' -> factory | '0.0.0' -> empty list
            # TODO : '# Branch Opts',
            'branch all local: 0.0',
            'branch all remote: 0.0',
            'branch available: 0.0',
            #'branch available know: 0.0',
            #'branch available new: 0.0', 
            # TODO : '# Kernel Opts',
            'kernel all: 0.0',
            'kernel installed all: 0.0',
            'kernel installed running: 0.0',
            'kernel available: 0.0',
            #'kernel available know: 0.0',
            #'kernel available new: 0.0',
            # TODO : '# Sync Opts',
            'sync count: 0',
            #'sync error: 0',
            'sync state: never sync',
            'sync network_error: 0',
            'sync retry: 0',
            'sync update: unknow',
            'sync timestamp: 0',
            # TODO: '# World Opts
            'world packages: 0',
            'world last start: 0',
            'world last stop: 0',
            'world last state: unknow',
            'world last total: 0',
            'world last failed: 0',
            # TODO: '# Portage Opts',
            'portage available: False',
            'portage current: 0.0',
            'portage latest: 0.0'
            )
        
    
    def config(self):
        """Create, check state file and its options"""
        # If new file, factory info
        # TODO: add options to reset {pull,sync}_count to factory
        self.logger.name = f'{self.logger_name}config::'
        
        try:
            if not pathlib.Path(self.pathdir['statelog']).is_file():
                self.logger.debug('Create state file: \'{0}\'.'.format(self.pathdir['statelog']))
                with pathlib.Path(self.pathdir['statelog']).open(mode='w') as mystatefile:
                    for option in self.stateopts:
                        self.logger.debug(f'Adding option \'{option}\'.')
                        mystatefile.write(option + '\n')
            else:
                with pathlib.Path(self.pathdir['statelog']).open(mode='r+') as mystatefile:
                    
                    regex = re.compile(r'^(.*):.*$')
                    
                    
                    # Get the content in the list
                    oldstatefile = mystatefile.readlines()
                    
                    # Erase file
                    mystatefile.seek(0)
                    mystatefile.truncate()
                                        
                    # Check if options from self.stateopts list is found in current state file.
                    for option in self.stateopts:
                        isfound = 'no'
                        for line in oldstatefile:
                            if regex.match(line).group(1) == regex.match(option).group(1):
                                self.logger.debug('Found option \'{0}\' in state file.'.format(regex.match(option).group(1)))
                                isfound = 'yes'
                                break
                        if isfound == 'no':
                            oldstatefile.append(option + '\n')           
                            self.logger.debug('Wrote new option \'{0}\' in state file'.format(regex.match(option).group(1)))
                    
                    # Check if wrong / old option is found in current state file and append in the list toremove
                    toremove = []
                    for line in oldstatefile:
                        isfound = 'no'
                        for option in self.stateopts:
                            try:
                                if regex.match(line).group(1) == regex.match(option).group(1):
                                        isfound = 'yes'
                                        break
                            except AttributeError as error:
                                # This is 'normal' if option is other then 'name and more: other' 
                                # exemple 'name_other' will not match group(1) and will raise 
                                # exception AttributeError. So this mean that the option is wrong anyway.
                                
                                # Break or this will print as many as self.stateopts list item.
                                break
                        if isfound == 'no':
                            toremove.append(line)
                    
                    # Remove old or wrong option found from oldstatefile list
                    for wrongopt in toremove:
                        oldstatefile.remove(wrongopt)
                        self.logger.debug('Remove wrong or old option \'{0}\' from state file'.format(wrongopt.rstrip()))
                    
                    # (re)write file
                    for line in oldstatefile:
                        mystatefile.write(line)
        except (OSError, IOError) as error:
            self.logger.critical('Error while checking / creating \'{0}\' state file.'.format(self.pathdir['statelog']))
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.logger.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                self.logger.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.logger.critical(f'Got: \'{error}\'.')
            sys.exit(1)           
        
    def save(self, pattern, to_write):
        """Edit info to specific linne of state file"""
        
        self.logger.name = f'{self.logger_name}save::'
        
        try:
            regex = re.compile(r"^" + pattern + r":.*$")
            with pathlib.Path(self.pathdir['statelog']).open(mode='r+') as mystatefile:
                oldstatefile = mystatefile.readlines()   # Pull the file contents to a list
                
                # Erase the file
                mystatefile.seek(0)
                mystatefile.truncate()
                
                # Rewrite 
                for line in oldstatefile:
                    if regex.match(line):
                        self.logger.debug(f'\'{to_write}\'.')
                        mystatefile.write(to_write + '\n')
                    else:
                        mystatefile.write(line)
        except (OSError, IOError) as error:
            self.logger.critical('Error while modifing \'{0}\' state file.'.format(self.pathdir['statelog']))
            self.logger.debug(f'\tTried to write: \'{to_write}\' in section: \'{pattern}\'.')
            self.logger.critical(f'\tGot: \'{error}\'.')
            sys.exit(1)

    def load(self, pattern):
        """Read info from specific state file"""
        
        self.logger.name = f'{self.logger_name}load::'
        
        try:
            regex = re.compile(r"^" + pattern + r":.(.*)$")
            with pathlib.Path(self.pathdir['statelog']).open() as mystatefile: 
                for line in mystatefile:
                     if regex.match(line):
                        self.logger.debug('\'{0}: {1}\''.format(pattern, regex.match(line).group(1)))
                        #self.logger.debug('Hello world')
                        return regex.match(line).group(1)
        except (OSError, IOError) as error:
            self.logger.critical('Error while reading \'{0}\' state file.'.format(self.pathdir['statelog']))
            self.logger.debug(f'\tTried to read section: \'{pattern}\'.')
            self.logger.critical(f'\tGot: \'{error}\'')
            sys.exit(1)  
 
class FormatTimestamp:
    """Convert seconds to time, optional rounded, depending of granularity's degrees.
        inspired by https://stackoverflow.com/a/24542445/11869956"""
        # TODO : (g)ranularity = auto this mean if minutes g = 1, if hours g=2 , if days g=2, if week g=3
        #        humm, i don't know, but when week and granularity = 2 than it display '1 week' until 1 week
        #   and 24 hour -> 1 week and 1 day ... we could display as well hours ?
    def __init__(self):
        # For now i haven't found a way to do it better
        # TODO: optimize ?!? ;)
        self.intervals = {
            # 'years'     :   31556952,  # https://www.calculateme.com/time/years/to-seconds/
            # https://www.calculateme.com/time/months/to-seconds/ -> 2629746 seconds
            # But it's outputing some strange result :
            # So 3 seconds less (2629743) : 4 weeks, 2 days, 10 hours, 29 minutes and 3 seconds
            # than after 3 more seconds : 1 month ?!?
            # Google give me 2628000 seconds
            # So 3 seconds less (2627997): 4 weeks, 2 days, 9 hours, 59 minutes and 57 seconds
            # Strange as well 
            # So for the moment latest is week ...
            #'months'    :   2419200, # 60 * 60 * 24 * 7 * 4 
            'weeks'     :   604800,  # 60 * 60 * 24 * 7
            'days'      :   86400,    # 60 * 60 * 24
            'hours'     :   3600,    # 60 * 60
            'minutes'   :   60,
            'seconds'  :   1
            }
        self.nextkey = {
            'seconds'   :   'minutes',
            'minutes'   :   'hours',
            'hours'     :   'days',
            'days'      :   'weeks',
            'weeks'     :   'weeks',
            #'months'    :   'months',
            #'years'     :   'years' # stop here
            }
        self.translate = {
            'weeks'     :   _('weeks'),
            'days'      :   _('days'),
            'hours'     :   _('hours'),
            'minutes'   :   _('minutes'),
            'seconds'   :   _('seconds'),
            ## Single
            'week'      :   _('week'),
            'day'       :   _('day'),
            'hour'      :   _('hour'),
            'minute'    :   _('minute'),
            'second'    :   _('second'),
            ' and'      :   _(' and'),
            ','         :   _(','),     # This is for compatibility
            ''          :   '\0'        # same here BUT we CANNOT pass empty string to gettext 
                                        # or we get : warning: Empty msgid.  It is reserved by GNU gettext:
                                        # gettext("") returns the header entry with
                                        # meta information, not the empty string.
                                        # Thx to --> https://stackoverflow.com/a/30852705/11869956 - saved my day
            }
        
    def convert(self, seconds, granularity=2, rounded=True, translate=False):
        """Proceed the conversion"""
        
        def _format(result):
            """Return the formatted result
            TODO : numpy / google docstrings"""
            start = 1 
            length = len(result)
            none = 0
            next_item = False
            for item in reversed(result[:]):
                if item['value']:
                    # if we have more than one item
                    if length - none > 1:
                        # This is the first 'real' item 
                        if start == 1:
                            item['punctuation'] = ''
                            next_item = True
                        elif next_item:
                            # This is the second 'real' item
                            # Happend 'and' to key punctuation
                            item['punctuation'] = ' and'
                            next_item = False
                        # If there is more than two 'real' item
                        # than happend ','
                        elif 2 < start:
                            item['punctuation'] = ','
                        else:
                            item['punctuation'] = ''
                    else:
                        item['punctuation'] = ''
                    start += 1
                else:
                    none += 1
            return [ { 'value'        :   mydict['value'], 
                       'name'         :   mydict['name_strip'],
                       'punctuation'  :   mydict['punctuation'] } for mydict in result \
                                                                  if mydict['value'] is not None ]
                    
        
        def _rstrip(value, name):
            """Rstrip 's' name depending of value"""
            if value == 1:
                name = name.rstrip('s')
            return name
            
            
        # Make sure granularity is an integer
        if not isinstance(granularity, int):
            raise ValueError(f'Granularity should be an integer: {granularity}')
        
        # For seconds only don't need to compute
        if seconds < 0:
            return _('any time now')
        elif seconds < 60:
            return _('less than a minute')
                
        result = []
        for name, count in self.intervals.items():
            value = seconds // count
            if value:
                seconds -= value * count
                name_strip = _rstrip(value, name)
                # save as dict: value, name_strip (eventually strip), name (for reference), value in seconds
                # and count (for reference)
                result.append({ 
                        'value'        :   value,
                        'name_strip'   :   name_strip,
                        'name'         :   name, 
                        'seconds'      :   value * count,
                        'count'        :   count
                                 })
            else:
                if len(result) > 0:
                    # We strip the name as second == 0
                    name_strip = name.rstrip('s')
                    # adding None to key 'value' but keep other value
                    # in case when need to add seconds when we will 
                    # recompute every thing
                    result.append({ 
                        'value'        :   None,
                        'name_strip'   :   name_strip,
                        'name'         :   name, 
                        'seconds'      :   0,
                        'count'        :   count
                                 })
        
        # Get the length of the list
        length = len(result)
        # Don't need to compute everything / everytime
        # added result[:granularity] for rounded
        if length < granularity or not rounded:
            if translate:
                return ' '.join('{0} {1}{2}'.format(item['value'], _(self.translate[item['name']]), 
                                                _(self.translate[item['punctuation']])) \
                                                for item in _format(result[:granularity]))
            else:
                return ' '.join('{0} {1}{2}'.format(item['value'], item['name'], item['punctuation']) \
                                                for item in _format(result[:granularity]))
            
        start = length - 1
        # Reverse list so the firsts elements 
        # could be not selected depending on granularity.
        # And we can delete item after we had his seconds to next
        # item in the current list (result)
        for item in reversed(result[:]):
            if granularity <= start <= length - 1:
                # So we have to round
                current_index = result.index(item)
                next_index = current_index - 1
                # skip item value == None
                # if the seconds of current item is superior
                # to the half seconds of the next item: round
                if item['value'] and item['seconds'] > result[next_index]['count'] // 2:
                    # +1 to the next item (in seconds: depending on item count)
                    result[next_index]['seconds'] += result[next_index]['count']
                # Remove item which is not selected
                del result[current_index]
            start -= 1
        # Ok now recalcul every thing
        # Reverse as well 
        for item in reversed(result[:]):
            # Check if seconds is superior or equal to the next item 
            # but not from 'result' list but from 'self.intervals' dict
            # Make sure it's not None
            if item['value']:
                next_item_name = self.nextkey[item['name']]
                # This mean we are at weeks
                if item['name'] == next_item_name:
                    # Just recalcul
                    item['value'] = item['seconds'] // item['count']
                    item['name_strip'] = _rstrip(item['value'], item['name'])
                # Stop to weeks to stay 'right' 
                elif item['seconds'] >= self.intervals[next_item_name]:
                    # First make sure we have the 'next item'
                    # found via --> https://stackoverflow.com/q/26447309/11869956
                    # maybe there is a faster way to do it ? - TODO
                    if any(search_item['name'] == next_item_name for search_item in result):
                        next_item_index = result.index(item) - 1
                        # Append to
                        result[next_item_index]['seconds'] += item['seconds']
                        # recalcul value
                        result[next_item_index]['value'] = result[next_item_index]['seconds'] // \
                                                           result[next_item_index]['count']
                        # strip or not
                        result[next_item_index]['name_strip'] = _rstrip(result[next_item_index]['value'],
                                                                       result[next_item_index]['name'])
                    else:
                        # Creating 
                        next_item_index = result.index(item) - 1
                        # get count
                        next_item_count = self.intervals[next_item_name]
                        # convert seconds
                        next_item_value = item['seconds'] // next_item_count
                        # strip 's' or not
                        next_item_name_strip = _rstrip(next_item_value, next_item_name)
                        # added to dict
                        next_item = {
                                       'value'      :   next_item_value,
                                       'name_strip' :   next_item_name_strip,
                                       'name'       :   next_item_name,
                                       'seconds'    :   item['seconds'],
                                       'count'      :   next_item_count
                                       }
                        # insert to the list
                        result.insert(next_item_index, next_item)
                    # Remove current item
                    del result[result.index(item)]
                else:
                    # for current item recalculate
                    # keys 'value' and 'name_strip'
                    item['value'] = item['seconds'] // item['count']
                    item['name_strip'] = _rstrip(item['value'], item['name'])
        if translate:
            return ' '.join('{0} {1}{2}'.format(item['value'], 
                                                _(self.translate[item['name']]), 
                                                _(self.translate[item['punctuation']])) \
                                                for item in _format(result))
        else:
            return ' '.join('{0} {1}{2}'.format(item['value'], item['name'], item['punctuation']) \
                                                for item in _format(result))


class UpdateInProgress:
    """Check if update is in progress..."""

    def __init__(self, logger):
        """Arguments:
            (callable) @log : an logger from logging module"""
        self.logger = logger
        # Avoid spamming with log.info
        self.logflow =  {
            'Sync'      :   0,   
            'World'     :   0,
            'Git'       :   0
            }
        self.timestamp = {
            'Sync'      :   0, 
            'World'     :   0,
            'Git'       :   0
            }
        self.msg = {
            'Sync'  :   'Syncing ',
            'World' :   'Global update',
            'Git'   :   'Git pull'
            }
        
        
    def check(self, tocheck, additionnal_msg='', repogit=False, quiet=False):
        """...depending on tocheck var
        Arguments:
            (str) @tocheck : call with 'World' or 'Sync' or 'Git'
            (str) @repogit : full path to git repo (use only with @tocheck == 'Git'
            (str) @quiet : enable or disable quiet output
        @return: True or False
        Adapt from https://stackoverflow.com/a/31997847/11869956"""
        
        # TODO: system as well 
        pids_only = re.compile(r'^\d+$')
        # For world
        # Added @world TODO: keep testing don't know if \s after (?:world|@world) is really needed...
        world = re.compile(r'^.*emerge.*\s(?:world|@world)\s*.*$')
        pretend = re.compile(r'.*emerge.*\s-\w*p\w*\s.*|.*emerge.*\s--pretend\s.*')
        # For sync
        sync = re.compile(r'.*emerge\s--sync\s*$')
        webrsync = re.compile(r'.*emerge-webrsync\s*.*$')
        # For git 
        git_pull = re.compile(r'.*git\s{1}(?:pull|fetch).*')
        
        if repogit:
            self.repogit = os.path.realpath(repogit)
            
        inprogress = False
        
        # TODO maybe we could collect for sync and world in one pass 
        # performance is 2x faster (almost) (means from ~0.025s to ~0.015s)
        
        pids = [ ]
        for dirname in os.listdir('/proc'):
            if pids_only.match(dirname):
                try:
                    with pathlib.Path('/proc/{0}/cmdline'.format(dirname)).open('rb') as myfd:
                        content = myfd.read().decode().split('\x00')
                # IOError exception when pid as finish between getting the dir list and open it each
                except IOError:
                    continue
                except Exception as exc:
                    self.logger.error(f'Got unexcept error: {exc}')
                    # TODO: Exit or not ?
                    continue
                # Check world update
                if tocheck == 'World':
                    if world.match(' '.join(content)):
                        #  Don't match any -p or --pretend opts
                        if not pretend.match(' '.join(content)):
                            inprogress = True
                            break
                # Check sync update
                elif tocheck == 'Sync':
                    if sync.match(' '.join(content)):
                        inprogress = True
                        break
                    elif webrsync.match(' '.join(content)):
                        inprogress = True
                        break
                # Check git pull / fetch
                elif tocheck == 'Git':
                    if git_pull.match(' '.join(content)):
                        try:
                            # We need to get the path to besure that it is 
                            # the right git pull / fetch process
                            path = os.readlink('/proc/{0}/cwd'.format(dirname))
                            if not repogit:
                                self.logger.error('Missing repogit args !')
                                return False # TODO : hum don't know :)
                            # Then compare path
                            elif os.path.samefile(path, self.repogit):
                                inprogress = True
                                break
                        # Same as upper 
                        except IOError:
                            continue
                        except Exception as exc:
                            self.logger.error(f'Got unexcept error: {exc}')
                            # TODO: Exit or not ?
                            continue
                else:
                    self.logger.critical(f'Bug module: \'{__name__}\', Class: \'{self.__class__.__name__}\',' +
                                      f' method: check(), tocheck: \'{tocheck}\'.')
                    self.logger.critical('Exiting with status \'1\'...')
                    sys.exit(1)
            
        displaylog = False
        current_timestamp = time.time()
        
        if inprogress:
            self.logger.debug('{0}{1} in progress.'.format(self.msg[tocheck], additionnal_msg))
            # We just detect 'inprogress'
            if self.timestamp[tocheck] == 0:
                displaylog = True
                # add 30 minutes (1800s)
                self.timestamp[tocheck] = current_timestamp + 1800
                self.logflow[tocheck] = 1                
            else:
                # It's running
                if self.timestamp[tocheck] <= current_timestamp:
                    displaylog = True
                    if self.logflow[tocheck] == 1:
                        # Add 1 hour (3600s)
                        self.timestamp[tocheck] = current_timestamp + 3600
                        self.logflow[tocheck] = 2
                    elif self.logflow[tocheck] >= 2:
                        # Add 2 hours (7200s) forever
                        self.timestamp[tocheck] = current_timestamp + 7200 
                        self.logflow[tocheck] = 3
                    else:
                        self.logger.warning(f'Bug module: \'{__name__}\', Class: \'{self.__class__.__name__}\',' +
                                          f' method: check(), logflow : \'{self.logflow[tocheck]}\'.')
                        self.logger.warning('Resetting all attributes')
                        self.timestamp[tocheck] = 0
                        self.logflow[tocheck] = 0
            if displaylog and not quiet:
                self.logger.info('{0}{1} in progress.'.format(self.msg[tocheck], additionnal_msg))
            return True
        else:
            self.logger.debug('{0}{1} not in progress.'.format(self.msg[tocheck], additionnal_msg))
            # Reset attributes
            self.timestamp[tocheck] = 0
            self.logflow[tocheck] = 0
            return False


# Taken from https://gist.github.com/evansd/2346614
def on_parent_exit(signame='SIGTERM'):
    """
    Return a function to be run in a child process which will trigger SIGNAME
    to be sent when the parent process dies
    """
    PR_SET_PDEATHSIG = 1
    signum = getattr(signal, signame)
    def set_parent_exit_signal():
        # http://linux.die.net/man/2/prctl
        result = cdll['libc.so.6'].prctl(PR_SET_PDEATHSIG, signum)
        if result != 0:
            # BUG Look like this is not working 
            # mean : it raise but didn't got this error msg ...
            raise #PrCtlError('prctl failed with error code %s' % result)
    return set_parent_exit_signal


def _format_timestamp(seconds, opt, translate):
    """Client helper for formatting timestamp depending on opts"""
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
    myformatter = FormatTimestamp()
    msg = myformatter.convert(seconds, granularity=granularity, rounded=rounded, translate=translate)
    return msg 


def _format_date(timestamp, opt):
    """Client helper for formatting date"""
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


