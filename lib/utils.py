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
import logging

from distutils.version import StrictVersion
from distutils.util import strtobool
from ctypes import cdll

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
    
    def __init__(self, pathdir, stateopts):
        self.logger_name = f'::{__name__}::StateInfo::'
        logger = logging.getLogger(f'{self.logger_name}init::')        
        self.pathdir = pathdir
        # Load factory opts
        self.stateopts = stateopts
        # Re(s) for search over option
        # so normal_opt match everything except line starting with '#'
        self.normal_opt = re.compile(r'^(?!#)(.*):\s(.*)$')
        self.hashtag_opt = re.compile(r'^(#.*)$')
        # Detected newfile
        # True if newfile have been create so default opts have been 
        # written, then don't need to load with calling self.load() just load 
        # from stateopts directly
        self.newfile = False
        # Create / check statefile otps
        self.__check_config()
    
    
    def save(self, *args):
        """
        save specific(s) information(s) to already create statefile
        """
        
        logger = logging.getLogger(f'{self.logger_name}save::') 
        
        with self.__open('r+') as mystatefile:
            statefile = mystatefile.readlines()   # Pull the file contents to a list
            changed = False
            for item in args:
                option = str(item[0])
                value = str(item[1])
                found = False
                skip = False
                for index, line in enumerate(statefile):
                    if re.match(r'^' + option + r':.*$', line):
                        # make sure save request option != current line option
                        current_value = re.match(r'^' + option + r':\s*(.*)$', line).group(1)
                        if current_value == value:
                            logger.debug(f'Reject requested operation on save for option' 
                                              + f' \'{option}\', using value: \'{value}\':'
                                              + f' loaded value is equal ({current_value}).')
                            # Any way we found it, but we skip
                            found = True
                            skip = True
                            break
                        logger.debug(f'\'{option}: {value}\'.')
                        # Change line 
                        statefile[index] = f'{option}: {value}\n'
                        found = True
                        changed = True
                        break
                    # We have a problem !
                if not found and not skip:
                    logger.debug(f'Match failed for option: {option}: {value} !')
                    logger.error(f'Failed to write \'{option}: {value}\''
                                        + ' to statefile: {0}'.format(self.pathdir['statelog'])
                                        + ' (please report this !)')
            # So now erase / rewrite only if something change
            # but it should !!
            if changed:
                # Erase the file
                mystatefile.seek(0)
                mystatefile.truncate()
                    
                for line in statefile:
                    mystatefile.write(line)
            else:
                logger.debug('Hum... Nothing to write... Ciao...')
                

    def load(self, *args):
        """
        Read all opts line (line starting with '#' is ignored)
        and return as dict with key: option and value: value from line 'option: value'.
        Return all if no args or only specific from args.
        Args should be valid option(s) or it will be rejected.
        """
        
        logger = logging.getLogger(f'{self.logger_name}load::') 
        logger.debug('Extracting options from statefile: {0}'.format(self.pathdir['statelog']))
        
        with self.__open('r') as mystatefile:
            statefile = [ line.rstrip('\n') for line in mystatefile ]
        # Ok so we load all strip line from statefile at once
        # Any way, construct all the dict, then return all if no args, or only specified by args
        stateopts_load = { }
        for line in statefile:
            key = False
            value = False
            if self.normal_opt.match(line):
                key = self.normal_opt.match(line).group(1)
                # So try to convert value
                value = self.normal_opt.match(line).group(2)
                value = self.__convert(value)
                logger.debug(f'Add key: \'{key}\' and value: \'{value}\' to load list.')
                stateopts_load[key] = value
            else:
                logger.debug(f'Reject line: \'{line}\'.')
        # Ok so now we have construct dict then return all if full=True or key specified by to_load
        if not stateopts_load:
            logger.debug('Failed to parse options: nothing have been add to load list...')
            logger.error('Failed to parse options for statefile:' 
                              + ' {0}'.format(self.pathdir['statelog']))
            # So load default values from self.stateopts
            for key, value in self.stateopts.items():
                if not re.match(r'^#.*$', key):
                    # Don't need to convert because self.stateopts have already good type
                    logger.debug(f'Add default key: \'{key}\' and default' 
                                      + f' value: \'{value}\' to load list.')
                    stateopts_load[key] = value
            logger.error('Loaded default options for statefile (please report this).')
        
        if not args:
            logger.debug('Returning all load list.')
            return stateopts_load
        
        partial_stateopts_load = { }
        for item in args:
            try:
                partial_stateopts_load[item] = stateopts_load[item]
            except KeyError as error:
                logger.debug(f'Reject wrong load request: \'{item}\'')
                continue
            else:
                logger.debug(f'Returning requested \'{item}\':' 
                                  + f' \'{stateopts_load[item]}\'.')
        return partial_stateopts_load if partial_stateopts_load else False
        

    def __open(self, request_mode):
        """
        Open specific statefile, this intend to be used as context manager.
        """
        logger = logging.getLogger(f'{self.logger_name}__open::') 
        msg = 'writing' if request_mode == 'r+' else 'reading'
        try:
            if pathlib.Path(self.pathdir['statelog']).is_file():
                return pathlib.Path(self.pathdir['statelog']).open(mode=request_mode)
            else:
                msg = 'creating'
                return pathlib.Path(self.pathdir['statelog']).open(mode='w')
        except (OSError, IOError) as error:
            logger.critical(f'While {msg}'
                                + ' \'{0}\' state file:'.format(self.pathdir['statelog']))
            logger.critical(f'{error}.')
            logger.critical('Exiting with status \'1\'.')
            sys.exit(1)
    
    
    def __convert(self, opt):
        """
        Try to convert opt from str() to int() or bool()
        if failed return original opt (so str()), StrictVersion need str()
        """
        logger = logging.getLogger(f'{self.logger_name}__convert::') 
        from_type = type(opt)
        converters = {
            'int'   :   int,
            'bool'  :   [ bool, strtobool ]
            }
        for key, convert in converters.items():
            try:
                if key == 'bool':
                    opt = convert[0](convert[1](opt))
                else:
                    opt = convert(opt)
            except ValueError as error:
                logger.debug(f'Reject \'{opt}\' mismatch filter {key}(): {error}')
                continue
            else:
                logger.debug(f'Convert \'{opt}\' from {from_type}() to {key}().')
                break
        return opt
    
    
    def __compare(self, *opts, **kwargs):
        """
        compare vars using type int() or type StrictVersion() and return greatest if possible
        """
        logger = logging.getLogger(f'{self.logger_name}__compare::') 
        
        option = kwargs.get('option', '')
        # remove duplicate
        list(set(opts))
        logger.debug(f'List for option \'{option}\':'
                          + ' \'{0}\'.'.format(', '.join(str(x) for x in opts)))
        # Do we need to compare ?
        if len(opts) == 1:
            # we don't really know what we return: mean it could type != StrictVersion()/int()
            return opts[0]
        # Ok then compare
        ref_type = {
            'int'           :   int,
            'StrictVersion' :   StrictVersion
            }
        validate = [ ]
        greatest = False
        for key, comparator in ref_type.items():
            for value in opts:
                try:
                    # fixbug: AttributeError: 'StrictVersion' object has no attribute 'version'
                    # convert to str() because 'False' will match with filter StrictVersion (?!?) 
                    # then throw AttributeError at the second loop (validate)...
                    comparator(str(value))
                except ValueError as error:
                    logger.debug(f'Reject \'{value}\' mismatch filter {key}(): {error}')
                    continue
                else:
                    validate.append(value)
            if validate:
                greatest = validate[0]
                for value in validate:
                    # OK try to fix same bug ...
                    try:
                        if comparator(value) > comparator(greatest):
                            greatest = value
                    except AttributeError as error:
                        logger.debug(f'Reject \'{value}\' mismatch filter {key}(): {error}')
                        greatest = False
                        break
            if greatest:
                break
        return greatest
                
                
    def __check_config(self):
        """
        Check state file and its options, eventually create and add default options.
        So make statefile ready to load from and save to.
        """
        
        logger = logging.getLogger(f'{self.logger_name}__check_config::') 
        
        with self.__open('r+') as mystatefile:
            if mystatefile.mode == 'w':
                self.newfile = True
                logger.debug('Creating state file: {0}.'.format(self.pathdir['statelog']))
                for option, value in self.stateopts.items():
                        value = f': {value}' if not value == '' else ''
                        logger.debug(f'Adding default option: \'{option}{value}\'')
                        mystatefile.write(f'{option}{value}\n')
            else:
                logger.debug('Inspecting state file: {0}'.format(self.pathdir['statelog']))
                
                # Ok so we have to reconstruct statefile list 
                # and remove all bad, wrong option 
                # move to right place good one (first pass)
                # Second pass, add missing option (at the end)
                # Third pass : merge duplicate / select greatest if possible
                # extract key (option) / value form dict and make lists to access from index
                default_option = list(self.stateopts)
                default_value = list(self.stateopts.values())
                changed = False
                statefile = [ ]
                tomerge = { }
                nline = 1
                index = 0
                # First pass
                for line in mystatefile:
                    # Remove '\n'
                    line = line.rstrip('\n')
                    found = False
                    ref = False
                    option = False
                    value = False
                    ## For bad option
                    # And also extract option / value from current line
                    if self.hashtag_opt.match(line):
                        ref = 'hashtag_opt'
                        option = self.hashtag_opt.match(line).group(1)
                        value = ''
                    elif self.normal_opt.match(line):
                        ref = 'normal_opt'
                        option = self.normal_opt.match(line).group(1)
                        value = self.normal_opt.match(line).group(2)
                    else:
                        changed = True
                        if len(self.stateopts) < index+1:
                            logger.debug(f'Reject out of range line {nline}, mismatch any filters: \'{line}\'.')
                            nline += 1
                            continue
                        else:
                            logger.debug(f'Reject line {nline}, mismatch any filters: \'{line}\'.')
                            # Then add default option
                            statefile.append([ default_option[index], default_value[index] ])
                            msg = ''
                            if not default_value[index] == '':
                                msg = f': {default_value[index]}'
                            logger.debug(f'Adding default option to line {nline}:'
                                            + ' \'{0}{1}\'.'.format(default_option[index], msg))
                            nline += 1
                            index += 1
                            continue
                    # line match regular expressions
                    ## For wrong option
                    if not option in self.stateopts:
                        changed = True
                        if len(self.stateopts) < index+1:
                            logger.debug(f'Reject out of range line {nline},' 
                                              + f' wrong or obsolete option: \'{line}\'.')
                            nline += 1
                            continue
                        else:
                            logger.debug(f'Reject line {nline}, wrong or obsolete option: \'{line}\'.')
                            # Then add default option
                            statefile.append([ default_option[index], default_value[index] ])
                            msg = ''
                            if not default_value[index] == '':
                                msg = f': {default_value[index]}'
                            # index+1 over nline
                            logger.debug('Adding default option to line {0}:'.format(index+1)
                                            + ' \'{0}{1}\'.'.format(default_option[index], msg))
                            nline += 1
                            index += 1
                            continue
                    ## Now at this point: line is validate, it's a valid option
                    ## For right place option
                    # First: if index is out of range then add to tomerge list (only if not hashtag)
                    if len(self.stateopts) < index+1:
                        logger.debug(f'Found out of range option at line {nline}: \'{line}\'.')
                        changed = True
                        # append tomerge list only normal_opt
                        if ref == 'hashtag_opt':
                            logger.debug(f'Unselect line {nline}, hashtag option merging is useless: \'{line}\'.')
                            continue
                        # the key will be the option and list will be value
                        if not option in tomerge:
                            tomerge[option] = [ ]
                        tomerge[option].append(value)
                        continue
                        # Nothing to had because self.stateopts is IndexError (out of range)
                    # Second check if it's in good place
                    if not default_option[index] == option:
                        logger.debug(f'Found unexcepted option at line {nline}: \'{line}\'.')
                        changed = True
                        # append tomerge list only normal_opt
                        if ref == 'hashtag_opt':
                            logger.debug(f'Unselect line {nline}, hashtag option merging is useless: \'{line}\'.')
                            continue
                        # the key will be the option and list will be value
                        if not option in tomerge:
                            tomerge[option] = [ ]
                        tomerge[option].append(value)
                        # Then add default option
                        statefile.append([ default_option[index], default_value[index] ])
                        msg = ''
                        if not default_value[index] == '':
                            msg = f': {default_value[index]}'
                        logger.debug('Adding default option to line {0}:'.format(index+1)
                                        + ' \'{0}{1}\'.'.format(default_option[index], msg))
                        # We add something so increment vars
                        index += 1
                        nline += 1
                        # Then jump to the next item
                        continue
                    ## All are validate
                    # Write to statefile list of list the validate line
                    logger.debug(f'Option Validate on line {nline}: \'{line}\'')
                    statefile.append([option, value ])
                    # increment vars
                    index += 1
                    nline += 1
               
                # Second pass: check missing option (at the end)
                nline = index + 1
                if len(statefile) < len(self.stateopts):
                    changed = True
                    for index in range(index, len(self.stateopts)):
                        statefile.append([ default_option[index], default_value[index] ])
                        msg = ''
                        if not default_value[index] == '':
                            msg = f': {default_value[index]}'
                        logger.debug(f'Adding default option to line {nline}:'
                                          + ' \'{0}{1}\'.'.format(default_option[index], msg))
                        nline += 1
                
                # Third pass: duplicate value / default value to greater
                # So here there is only normal_opt which will be merged
                if tomerge:
                    for item in statefile:
                        # If duplicate exits
                        if item[0] in tomerge:
                            # Try to compare using int() then StrictVersion()
                            greatest = self.__compare(*tomerge[item[0]], item[1], option=item[0])
                            logger.name = f'{self.logger_name}config::'
                            if greatest:        
                                logger.debug(f'Merging value for option \'{item[0]}\':'
                                                    + f' current: \'{item[1]}\', newer: \'{greatest}\'.')
                                item[1] = greatest
                                continue
                            logger.debug('All filters failed, data cannot be' 
                                            + f' compared/merged for option \'{item[0]}\':'
                                            + ' \'{0}\'.'.format('|'.join(tomerge[item[0]])))
                            # First test if current value != default_value then keep it
                            # make self.stateopts str() because extracted value is/are str()
                            if not item[1] == str(self.stateopts[item[0]]):
                                logger.debug(f'Keeping value \'{item[1]}\'' 
                                                + f' (over: default_value=\'{self.stateopts[item[0]]}\' and' 
                                                + ' list=\'{0}\')'.format('|'.join(tomerge[item[0]]))
                                                + f' for option: \'{item[0]}\'.')
                            else:
                                # Pick the first value in the list 
                                # which is != default_value
                                found = False
                                for value in tomerge[item[0]]:
                                    # same here: make str() 
                                    if not value == str(self.stateopts[item[0]]):
                                        logger.debug(f'Selecting arbitrarily: \'{value}\'' 
                                                + f' (over: default_value=\'{self.stateopts[item[0]]}\' and' 
                                                + ' list=\'{0}\')'.format('|'.join(tomerge[item[0]]))
                                                + f' for option: \'{option}\'.')
                                        item[1] = value
                                        found = True
                                        break
                                if not found:
                                    # Ok so take default_value...
                                    logger.debug(f'Selecting default value: \'{self.stateopts[item[0]]}\'' 
                                                    + f' (over: current=\'{item[1]}\' and' 
                                                    + ' list=\'{0}\')'.format('|'.join(tomerge[item[0]]))
                                                    + f' for option: \'{item[0]}\'.')
                                    item[1] = self.stateopts[item[0]]
                # End piouff ;p
                if changed:
                    # Erase file
                    mystatefile.seek(0)
                    mystatefile.truncate()
                    for option in statefile:
                        # Work around for hashtag
                        value = f': {option[1]}' if not option[1] == '' else ''
                        line = f'{option[0]}{value}\n'
                        mystatefile.write(line)
                    logger.debug('Write changes to statefile: Success.')
                else:
                    logger.debug('All good, keeping previously state file untouched.')



class FormatTimestamp:
    """Convert seconds to time, optional rounded, depending of granularity's degrees.
        inspired by https://stackoverflow.com/a/24542445/11869956"""
        # TODO : (g)ranularity = auto this mean if minutes g = 1, if hours g=2 , if days g=2, if week g=3
        #        humm, i don't know, but when week and granularity = 2 than it display '1 week' until 1 week
        #   and 24 hour -> 1 week and 1 day ... we could display as well hours ?
        # Yes we could display in the list: current display - 2 
        # TODO logger !!
    def __init__(self):
        #self.logger_name = f'::{__name__}::FormatTimestamp::'
        #logger = logging.getLogger(f'{self.logger_name}init::')  
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
        #logger = logging.getLogger(f'{self.logger_name}convert::') 
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
            if translate:
                return _('any time now')
            return 'any time now'
        elif seconds < 60:
            if translate:
                return _('less than a minute')
            return 'less than a minute'
                
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


# TODO Should we need logger ???
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
