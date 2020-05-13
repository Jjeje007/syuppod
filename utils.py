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
from distutils.version import StrictVersion

try:
    from babel.dates import format_datetime
    from babel.dates import LOCALTZ
except Exception as exc:
    print(f'Error: got unexcept error while loading babel modules: {exc}', file=sys.stderr)
    print('Error: exiting with status \'1\'.', file=sys.stderr)
    sys.exit(1)



mylocale = locale.getdefaultlocale()
# see --> https://stackoverflow.com/a/10174657/11869956 thx
#localedir = os.path.join(os.path.dirname(__file__), 'locales')
# or python > 3.4:

localedir = pathlib.Path(__file__).parent/'locales'
lang_translations = gettext.translation('utils', localedir, languages=[mylocale[0]], fallback=True)
lang_translations.install()
_ = lang_translations.gettext

class StateInfo:
    """
    Write, edit or get info to and from state file
    """
    
    def __init__(self, pathdir, runlevel, loglevel, stateopts):
        self.pathdir = pathdir
        
        # Init logger
        self.logger_name = f'::{__name__}::StateInfo::'
        mainlogger = MainLoggingHandler(self.logger_name, self.pathdir['prog_name'], 
                                        self.pathdir['debuglog'], self.pathdir['fdlog'])
        self.logger = getattr(mainlogger, runlevel)()
        self.logger.setLevel(loglevel)
        # Load factory opts
        self.stateopts = stateopts
        # Re(s) for search over option
        # so normal_opt match everything except line starting with #
        self.normal_opt = re.compile(r'^(?!#)(.*:\s)(.*)$')
        self.hashtag_opt = re.compile(r'^(#.*)$')
    
    
    def config(self):
        """Create, check state file and its options"""
        self.logger.name = f'{self.logger_name}config::'
        
        try:
            if not pathlib.Path(self.pathdir['statelog']).is_file():
                # If new file, factory options
                self.logger.debug('Creating state file: \'{0}\'.'.format(self.pathdir['statelog']))
                with pathlib.Path(self.pathdir['statelog']).open(mode='w') as mystatefile:
                    for option in self.stateopts:
                        self.logger.debug(f'Adding default option: \'{option}\'.')
                        mystatefile.write(option + '\n')
                return
            else:
                self.logger.debug('Inspecting state file: {0}'.format(self.pathdir['statelog']))
                with pathlib.Path(self.pathdir['statelog']).open(mode='r') as mystatefile:
                    # Get the content in the list,  TEST rstrip trailing whitespace
                    statefile = [ line.rstrip() for line in mystatefile ]
                # Close
        except (OSError, IOError) as error:
            self.logger.critical('Error while checking / creating state file:' 
                                 + ' \'{0}\'.'.format(self.pathdir['statelog']))
            if error.errno == errno.EPERM or error.errno == errno.EACCES:
                self.logger.critical(f'Error: \'{error.strerror}: {error.filename}\'.')
                self.logger.critical('Daemon is intended to be run as sudo/root.')
            else:
                self.logger.critical(f'Error: \'{error}\'.')
            self.logger.critical('Exiting with status \'1\'.')
            sys.exit(1)  
        
        # this will definied if we need to rewrite statefile or not
        changed = False
        
        # First remove wrong opt
        index = 0
        for item in statefile[:]:
            found = False
            myre = False
            re_ref = False
            if self.hashtag_opt.match(item):
                re_ref = 'hashtag_opt'
            elif self.normal_opt.match(item):
                re_ref = 'normal_opt'
            else:
                # So item is wrong anyway ?
                self.logger.debug('Line {0}:'.format(index+1) 
                                  + f' \'{item}\' didn\'t' 
                                  + ' match any filters.')
                # 'jump' streight to remove
                re_ref = False
                
            if re_ref:
                myre = getattr(self, re_ref)
                for option in self.stateopts:
                    if myre.match(option):
                        if myre.match(item).group(1) == myre.match(option).group(1):
                            found = True
                            break
            if not found:
                self.logger.debug('Removing wrong option (line {0}):'.format(index+1)
                                      + f' \'{item}\'.')
                del statefile[index]
                # So remove 1 to index
                index -= 1
            # Add one to index
            index += 1
        
        
        # Check duplicate / merge options
        for option in self.stateopts:
            # Here we can use index() because there is no duplicate
            index = self.stateopts.index(option)
            found = False
            haschanged = False
            filtered_option = False
            filtered_statefile = False
            try:
                # Get current option filtered
                # Set re_ref using option filtered
                if self.hashtag_opt.match(option):
                    filtered_option = self.hashtag_opt.match(option).group(1)
                    re_ref = 'hashtag_opt'
                elif self.normal_opt.match(option):
                    filtered_option = self.normal_opt.match(option).group(1)
                    re_ref = 'normal_opt'
                # Get current statefile filtered
                if self.hashtag_opt.match(statefile[index]):
                    filtered_statefile = self.hashtag_opt.match(statefile[index]).group(1)
                elif self.normal_opt.match(statefile[index]):
                    filtered_statefile = self.normal_opt.match(statefile[index]).group(1)
            except AttributeError as error:
                # This should't arrived
                # TODO remove ?
                if len(statefile) < index+1:
                    self.logger.debug('Got unexcept AttributeError on statefile line' 
                                      + ' {0}: out of range.'.format(index+1)
                                      + f' (option searched: {option}).')
                else:
                    self.logger.debug('Got unexcept AttributeError on statefile line' 
                                      + ' {0}: \'{1}\''.format(index+1, statefile[index])
                                      + f' (option searched: \'{option}\').')
            except IndexError as error:
                # Ok so this mean end of line for statefile (no more option)
                # so let 'found' do the job
                self.logger.debug(f'Got IndexError, missing option: \'{option}\'.')
                # Reset filtered_statefile so go straight to not found
                filtered_statefile = False
            
            if filtered_option and filtered_statefile:
                if filtered_option == filtered_statefile:
                    self.logger.debug('Found option' 
                                      + ' (line {0}):'.format(index+1) 
                                      + ' \'{0}\'.'.format(statefile[index]))
                    found = True
                    # Even we found item and in the right place make sure threre is no duplicate
                    (duplicate, haschanged, statefile) = self._search_opt(option, statefile, index,
                                                                        re_ref, founded_opt=statefile[index])
                    self.logger.name = f'{self.logger_name}config::'
                    if duplicate:
                        self.logger.debug(f'Merging option \'{option}\''
                                          + ' (line {0}, overwritten \'{1}\')'.format(index+1, statefile[index])
                                          + f' with greater/newer value: \'{duplicate}\'.')
                        statefile[index] = duplicate
                else:
                    # Search over statefile list
                    (duplicate, haschanged, statefile) = self._search_opt(option, statefile, index, re_ref)
                    self.logger.name = f'{self.logger_name}config::'
                    if duplicate:
                        self.logger.debug('Moving option' 
                                           + f' \'{duplicate}\''
                                           + ' to line {0}.'.format(index+1))
                        found = True
                        statefile.insert(index, duplicate)
                # something changes during this loop
                if haschanged:
                    changed = True
                
            # Ok so option have not been found
            if not found:
                self.logger.debug('Will write new option'
                                   + ' (line {0}):'.format(index+1)
                                   + f' \'{option}\'.')
                statefile.insert(index, option)
                changed = True
                
        # Erase file and rewrite only if needed
        if changed:
            try:
                with pathlib.Path(self.pathdir['statelog']).open(mode='r+') as mystatefile:
                    mystatefile.seek(0)
                    mystatefile.truncate()
                    self.logger.debug('Writing changes to state file.')
                    for line in statefile:
                        mystatefile.write(line + '\n')
            except (OSError, IOError) as error:
                self.logger.critical('Error while checking / creating state file:' 
                                 + ' \'{0}\'.'.format(self.pathdir['statelog']))
                if error.errno == errno.EPERM or error.errno == errno.EACCES:
                    self.logger.critical(f'Error: \'{error.strerror}: {error.filename}\'.')
                    self.logger.critical('Daemon is intended to be run as sudo/root.')
                else:
                    self.logger.critical(f'Error: \'{error}\'.')
                self.logger.critical('Exiting with status \'1\'.')
                sys.exit(1)  
        else:
            self.logger.debug('All good, keeping previously state file untouched.')
                 
      
      
    def save(self, pattern, to_write):
        """Edit info to specific line of state file"""
        
        self.logger.name = f'{self.logger_name}save::'
        
        regex = re.compile(r'^' + pattern + r':.*$')
                
        try:
            with pathlib.Path(self.pathdir['statelog']).open(mode='r+') as mystatefile:
                statefile = mystatefile.readlines()   # Pull the file contents to a list
                
                # Erase the file
                mystatefile.seek(0)
                mystatefile.truncate()
                
                # Rewrite 
                for line in statefile:
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
        
        regex = re.compile(r'^' + pattern + r':\s(.*)$')
        
        try:
            with pathlib.Path(self.pathdir['statelog']).open() as mystatefile: 
                for line in mystatefile:
                     if regex.match(line):
                        self.logger.debug('\'{0}: {1}\''.format(pattern, regex.match(line).group(1)))
                        return regex.match(line).group(1)
        except (OSError, IOError) as error:
            self.logger.critical('Error while reading \'{0}\' state file.'.format(self.pathdir['statelog']))
            self.logger.debug(f'\tTried to read section: \'{pattern}\'.')
            self.logger.critical(f'\tGot: \'{error}\'')
            sys.exit(1)
   
   
    def _compare_version(self, opt1, opt2, option):
        """
        Private method to compare vars using type StrictVersion()
        """
        
        self.logger.name = f'{self.logger_name}_compare_version::'
        
        try:
            if StrictVersion(opt1) > StrictVersion(opt2):
                self.logger.debug(f'{option} opt1 ({opt1}) greater than opt2 ({opt2})')
                return opt1
            elif StrictVersion(opt1) < StrictVersion(opt2):
                self.logger.debug(f'{option} opt2 ({opt2}) greater than opt1 ({opt1})')
                return opt2
            # opt1 == opt2 so return opt1
            else:
                self.logger.debug(f'{option} opt1 ({opt1}) equal to opt2 ({opt2})')
                return opt1
        except ValueError as error:
            self.logger.debug(f'{option} comparing opt1 ({opt1}) and opt2 ({opt2}): {error}.')
            return False
    
    
    def _compare_int(self, opt1, opt2, option):
        """
        Private method to compare vars using type int()
        """
        
        self.logger.name = f'{self.logger_name}_compare_int::'
        
        try:
            if int(opt1) > int(opt2):
                self.logger.debug(f'{option} opt1 ({opt1}) greater than opt2 ({opt2})')
                return opt1
            elif int(opt1) < int(opt2):
                self.logger.debug(f'{option} opt2 ({opt2}) greater than opt1 ({opt1})')
                return opt2
            # opt1 == opt2 so return opt1
            else:
                self.logger.debug(f'{option} opt1 ({opt1}) equal to opt2 ({opt2})')
                return opt1
        except ValueError as error:
            self.logger.debug(f'{option} comparing opt1 ({opt1}) and opt2 ({opt2}): {error}.')
            return False
        
    def _search_opt(self, searched_opt, mylist, searched_index, re_ref, founded_opt=False):
        """
        Search over list missing and/or duplicate entry and compare/merge greater depending on var type.
        """
        self.logger.name = f'{self.logger_name}_search_opt::'
        
        # Default values
        default_value = False
        myre = getattr(self, re_ref)
        comparable = True
        greatest = False
        changed = False
        found = [ ]
        opt_only = myre.match(searched_opt).group(1)
        # 'hashtag_opt' don't need to be comparable
        # we just want to remove duplicate:
        if not re_ref == 'hashtag_opt':
            default_value = myre.match(searched_opt).group(2)
            if founded_opt:
                found.append(myre.match(founded_opt).group(2))
        
        index = 0
        for item in mylist[:]:
            filtered_item = False
            item_value = False
            try:
                # Get current item filtered
                if self.hashtag_opt.match(item):
                    filtered_item = self.hashtag_opt.match(item).group(1)
                elif self.normal_opt.match(item):
                    filtered_item = self.normal_opt.match(item).group(1)
                    item_value = self.normal_opt.match(item).group(2)
            except AttributeError as error:
                # This should't arrived
                # TODO remove ??
                self.logger.debug(f'Got unexcept AttributeError: {error}')
                self.logger.debug('Line {0}: \'{1}\','.format(current_index+1, item)
                                  + f' option searched: \'{searched_opt}\' and using filter: \'{re_ref}\'.')
                
            # make sure we compare the 'right' group (hashtag_opt vs normal_opt)
            if opt_only == filtered_item:
                # make sure we haven't founded the already founded (if founded_opt)
                # or excepted founded in the right index (searched_index)
                if not searched_index == index:
                    # So happen value only to founded_list and remove opt
                    # 'hashtag_opt' have no value - it have only one sub group()
                    if re_ref == 'hashtag_opt':
                        if not founded_opt:
                            self.logger.debug('Found option:'
                                       + f' \'{item}\''
                                       + ' (expected line {0},'.format(searched_index+1)
                                       + ' found line {0}).'.format(index+1))
                        else:
                            self.logger.debug('Removing duplicate option:'
                                       + f' \'{item}\''
                                       + ' (expected line {0},'.format(searched_index+1)
                                       + ' duplicate at line {0}).'.format(index+1))
                        found.append(item)
                    else:
                        self.logger.debug('Found option:'
                                       + f' \'{item}\''
                                       + ' (expected line {0},'.format(searched_index+1)
                                       + ' found line {0}).'.format(index+1))
                        found.append(item_value)
                    # Removing
                    del mylist[index]
                    # If removing then remove 1 to index also
                    index -= 1
                    changed = True
            index += 1
            
        # Ok so now, inspect founded_list and try to compare
        if found and len(found) > 1 and not re_ref == 'hashtag_opt':
            greatest = default_value
            for item in found:
                greater = self._compare_int(greatest, item, opt_only)
                self.logger.name = f'{self.logger_name}_search_opt::'
                if greater:
                    greatest = greater
                else:
                    greater = self._compare_version(greatest, item, opt_only)
                    self.logger.name = f'{self.logger_name}_search_opt::'
                    if greater:
                        greatest = greater
                    else:
                        self.logger.debug('All check failed, data cannot be compared/merged:' 
                                          + ' {0}'.format('|'.join(found)))
                        comparable = False
                        break
        # it's not comparable
        if found and len(found) > 1 and not comparable and not re_ref == 'hashtag_opt':
            # Try to avoid getting default_value
            greatest = default_value
            for item in found:
                if not item == greatest:
                    self.logger.debug(f'Selecting: {item}' 
                                      + f' (over: default_value={default_value} and' 
                                      + ' list={0}).'.format('|'.join(found)))
                    greatest = item
                    break
        elif found and len(found) == 1 and not founded_opt and not re_ref == 'hashtag_opt':
            # we don't care about merge because we have only one item in the list so...
            greatest = found[0]
        # hashtag_opt setup return only if not already found
        if found and re_ref == 'hashtag_opt' and not founded_opt:
            greatest = found[0]
        # else: Nothing found, keep greatest=False
        
        # return also changed because we could only founded wrong opt :p
        if greatest:
            # So greatest is only the value of the opt so repack 
            # but not for hashtag_opt setup
            # normal_opt will match ': ' so don't need to add here
            if not re_ref == 'hashtag_opt':
                greatest = '{0}{1}'.format(myre.match(searched_opt).group(1), greatest)
        return (greatest, changed, mylist)
            

 
class FormatTimestamp:
    """Convert seconds to time, optional rounded, depending of granularity's degrees.
        inspired by https://stackoverflow.com/a/24542445/11869956"""
        # TODO : (g)ranularity = auto this mean if minutes g = 1, if hours g=2 , if days g=2, if week g=3
        #        humm, i don't know, but when week and granularity = 2 than it display '1 week' until 1 week
        #   and 24 hour -> 1 week and 1 day ... we could display as well hours ?
        # Yes we could display in the list: current display - 2 
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
            # TEST print to stderr 
            print(f'Error: prctl failed with error code: \'{result}\'.', file=sys.stderr)
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
