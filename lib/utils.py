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
    
    def __init__(self, **kwargs):
        self.logger_name = f'::{__name__}::StateInfo::'
        logger = logging.getLogger(f'{self.logger_name}init::')        
        self.pathdir = kwargs['pathdir']
        # Load factory opts
        self.stateopts = kwargs['stateopts']
        # For dry run
        self.dryrun = kwargs.get('dryrun', False)
        # Re(s) for search over option
        # so normal_opt match everything except line starting with '#'
        self.normal_opt = re.compile(r'^(?!#)(.*):\s(.*)$')
        self.hashtag_opt = re.compile(r'^(#.*)$')
        # TEST try to wait before exiting if SIGTERM is receive 
        # and if we are processing something to 'save' (ie write to statefile)
        # This is not as bad as we think if program exit when we are writing something:
        # We will only lost theses write but any way this class can rewrite / extract good
        # opts and remove wrong ones (but we don't know if it could recover from a corrupt file ...)
        self.saving = False
        # Detected newfile
        # True if newfile have been create so default opts have been 
        # written, then don't need to load with calling self.load() just load 
        # from stateopts directly
        self.newfile = False
        # Create / check statefile opts
        if self.dryrun:
            logger.debug('Dryrun is enable, skip checking/creating statefile.')
            return
        self.__check_config()
    
    
    def save(self, *args):
        """
        save specific(s) information(s) to already create statefile
        """
        
        logger = logging.getLogger(f'{self.logger_name}save::') 
        
        if self.dryrun:
            call = 'None ?!'
            if args:
                call = args
            logger.debug('Dryrun is enable, skipping save for:'
                         + f' {call}')
            return
        
        # This will protect all the process even we could write nothing
        self.saving = True
        logger.debug('Setting saving flag to True.')
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
                #So we are writing to statefile
                #self.saving = True
                # Erase the file
                mystatefile.seek(0)
                mystatefile.truncate()
                    
                for line in statefile:
                    mystatefile.write(line)
                # End write
                #self.saving = False
            else:
                logger.debug('Hum... Nothing to write... Ciao...')
        self.saving = False
        logger.debug('Resetting saving flag to False.') 
                

    def load(self, *args):
        """
        Read all opts line (line starting with '#' is ignored)
        and return as dict with key: option and value: value from line 'option: value'.
        Return all if no args or only specific from args.
        Args should be valid option(s) or it will be rejected.
        """
        
        logger = logging.getLogger(f'{self.logger_name}load::')
        
        if self.dryrun:
            call = '(None) = loading all'
            if args:
                call = args
            logger.warning(f'Module: {__name__}, Class: StateInfo, Method: load(),' 
                           + ' dryrun is enable but received call for: {call}' 
                           + ' (please report this).')
            return
        
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
        #msg = 'reading'
        #if request_mode == 'r+':
            #msg = 'writing'
            #self.saving = True
            #logger.debug('Setting saving flag to True')
        try:
            if pathlib.Path(self.pathdir['statelog']).is_file():
                logger.debug(f"Opening \'{self.pathdir['statelog']}\' for {msg}.")
                return pathlib.Path(self.pathdir['statelog']).open(mode=request_mode)
            else:
                msg = 'creating'
                #self.saving = True
                #logger.debug('Setting saving flag to True')
                logger.debug(f"Creating state file: {self.pathdir['statelog']}")
                return pathlib.Path(self.pathdir['statelog']).open(mode='w')
        except (OSError, IOError) as error:
            logger.critical(f"While {msg} \'{self.pathdir['statelog']}\'" 
                            + f' state file: {error}.')
            logger.critical('Exiting with status \'1\'.')
            sys.exit(1)
        #finally:
            #Reset saving to False
            #self.saving = False
            #logger.debug('Resetting saving flag to False')
    
    
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
        
        self.saving = True
        logger.debug('Setting saving flag to True.')
        with self.__open('r+') as mystatefile:
            if mystatefile.mode == 'w':
                self.newfile = True
                # Same here we are writig to statefile
                #self.saving = True
                for option, value in self.stateopts.items():
                    value = f': {value}' if not value == '' else ''
                    logger.debug(f'Adding default option: \'{option}{value}\'')
                    mystatefile.write(f'{option}{value}\n')
                # End writing
                #self.saving = False
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
                    # Same here set saving to True wa are writing
                    #self.saving = True
                    # Erase file
                    mystatefile.seek(0)
                    mystatefile.truncate()
                    for option in statefile:
                        # Work around for hashtag
                        value = f': {option[1]}' if not option[1] == '' else ''
                        line = f'{option[0]}{value}\n'
                        mystatefile.write(line)
                    # End writing
                    #self.saving = False
                    logger.debug('Write changes to statefile: Success.')
                else:
                    logger.debug('All good, keeping previously state file untouched.')
        self.saving = False
        logger.debug('Resetting saving flag to False.')



class FormatTimestamp:
    """
    Convert seconds to time, optional rounded, depending of granularity's degrees.
    inspired by https://stackoverflow.com/a/24542445/11869956
    """
    # TODO logger !!
    
    def __init__(self):
        #self.logger_name = f'::{__name__}::FormatTimestamp::'
        #logger = logging.getLogger(f'{self.logger_name}init::')  
        # Dict ordered only with python >= 3.7
        if sys.version_info[:2] < (3, 7):
            from collections import OrderedDict 
            self.intervals = OrderedDict(
                ('weeks',  604800),     # 60 * 60 * 24 * 7
                ('days',  86400),      # 60 * 60 * 24
                ('hours',  3600),       # 60 * 60
                ('minutes', 60),
                ('seconds', 1)
                )
        else:
            self.intervals = {
                # Stop to week, month is too ambiguous to calculate 
                # Try plenty of website almost no one give same value ...
                'weeks'     :   604800,     # 60 * 60 * 24 * 7
                'days'      :   86400,      # 60 * 60 * 24
                'hours'     :   3600,       # 60 * 60
                'minutes'   :   60,
                'seconds'   :   1
                }
        self.nextkey = {
            'seconds'   :   'minutes',
            'minutes'   :   'hours',
            'hours'     :   'days',
            'days'      :   'weeks',
            'weeks'     :   'weeks',
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
        # Acces intervals by names 
        self.byname = {
            'weeks'     :   4,     
            'days'      :   3,    
            'hours'     :   2,
            'minutes'   :   1,
            'seconds'   :   0
            }
        # By id
        self.byid =  {
            4   :   'weeks',     
            3   :   'days',    
            2   :   'hours',
            1   :   'minutes',
            0   :   'seconds' 
            }
        
        
    def convert(self, seconds, granularity=2, rounded=True, translate=False):
        """
        Proceed the conversion
        """
        #logger = logging.getLogger(f'{self.logger_name}convert::') 
        def __format(result):
            """
            Return the formatted result
            """
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
                       'name'         :   mydict['name_rstrip'],
                       'punctuation'  :   mydict['punctuation'] } for mydict in result ]
            # TEST value == None is removed: in last 'result' list iteration
            # And clean up if not rounded or granularity > len(result)
                      
        def __rstrip(value, name):
            """
            Rstrip 's' name depending of value
            """
            if value == 1:
                name = name.rstrip('s')
            return name
            
            
        # Make sure granularity is an integer
        if not isinstance(granularity, int):
            raise ValueError(f'Granularity should be an integer: {granularity}')
        # Make sure granularity is between 1-5
        assert 0 < granularity < 6, f'Granularity argument out of range [1-5]: {granularity}'
        
        # For seconds only don't need to compute
        if seconds < 0:
            if translate:
                return _('any time now')
            return 'any time now'
        elif seconds < 60:
            if translate:
                return _('less than a minute')
            return 'less than a minute'
         
        # TEST save seconds for latter 
        seconds_arg = seconds 
        
        result = []
        for name, count in self.intervals.items():
            value = seconds // count
            if value:
                seconds -= value * count
                name_rstrip = __rstrip(value, name)
                # save as dict: value, name_rstrip (eventually strip), name (for reference), value in seconds
                # and count (for reference)
                result.append({ 
                        'value'        :   value,
                        'name_rstrip'   :   name_rstrip,
                        'name'         :   name, 
                        'seconds'      :   value * count,
                        'count'        :   count
                                 })
            else:
                if len(result) > 0:
                    # We strip the name as second == 0
                    name_rstrip = name.rstrip('s')
                    # adding None to key 'value' but keep other value
                    # in case when need to add seconds when we will 
                    # recompute every thing
                    result.append({ 
                        'value'        :   None,
                        'name_rstrip'   :   name_rstrip,
                        'name'         :   name, 
                        'seconds'      :   0,
                        'count'        :   count
                                 })
        
        # Get the length of the list
        length = len(result)
        # Don't need to compute everything / everytime
        # added result[:granularity] for rounded
        if length < granularity or not rounded:
             # Clean-up / remove all value == None
            for item in result[:]:
                if item['value'] == None:
                    result.remove(item)
            # Translation 
            if translate:
                return ' '.join('{0} {1}{2}'.format(item['value'], _(self.translate[item['name']]), 
                                                _(self.translate[item['punctuation']])) \
                                                for item in __format(result[:granularity]))
            else:
                return ' '.join('{0} {1}{2}'.format(item['value'], item['name'], item['punctuation']) \
                                                for item in __format(result[:granularity]))
            
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
                    #print(f"Item value: {item['value']}, seconds: {item['seconds']},"
                          #f" count: {item['count']}, name: {item['name']}")
                    item['value'] = item['seconds'] // item['count']
                    item['name_rstrip'] = __rstrip(item['value'], item['name'])
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
                        result[next_item_index]['name_rstrip'] = __rstrip(result[next_item_index]['value'],
                                                                       result[next_item_index]['name'])
                    else:
                        # Creating 
                        next_item_index = result.index(item) - 1
                        # get count
                        next_item_count = self.intervals[next_item_name]
                        # convert seconds
                        next_item_value = item['seconds'] // next_item_count
                        # strip 's' or not
                        next_item_name_strip = __rstrip(next_item_value, next_item_name)
                        # added to dict
                        next_item = {
                                       'value'      :   next_item_value,
                                       'name_rstrip' :   next_item_name_strip,
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
                    # keys 'value' and 'name_rstrip'
                    item['value'] = item['seconds'] // item['count']
                    item['name_rstrip'] = __rstrip(item['value'], item['name'])
            # If value == None then delete
            else:
                result.remove(item)
        
        # TEST if list result < granularity then
        # try to add result from  interval's latest result list (mean '[-1]') + 2
        if len(result) < granularity:
            seconds_sum = 0
            for item in result:
                if not item['value'] == None:
                    seconds_sum += item['seconds']
            # If seconds left (if any) > latest item from 'result' list - 2:
            # This mean, for exemple if granularity = 2, len = 1, latest item = 'weeks'
            # then, since we rounded, it could have seconds left but these seconds are < 'days'
            # but could be calculate using 'hours', and we still output two item (like requested
            # by granularity = 2). This is for fine tunning rounded process otherwise, to use the exmple,
            # We output 'weeks' until 'days' is reached: during 23h59m59s... It's a long long time (even if rounded).
            
            # So first make sure we are not out of range and will not get us to 'seconds'
            last_result_id = self.byname[result[-1]['name']]
            if last_result_id - 2 > 0:
                # First get name using id 
                name_by_id = self.byid[last_result_id - 2]
                # Then make sure we have seconds left and its >= to intervals[last_result_id - 2]
                if seconds_arg - seconds_sum >= self.intervals[name_by_id]:
                    # So reconstruct and add a new dict to list 'result'
                    seconds = seconds_arg - seconds_sum
                    count = self.intervals[name_by_id]
                    value = seconds // count
                    name_rstrip = __rstrip(value, name_by_id)
                    # name = name_by_id
                    result.append({ 
                        'value'         :   value,
                        'name_rstrip'   :   name_rstrip,
                        'name'          :   name_by_id,
                        'seconds'       :   seconds,
                        'count'         :   count
                        })
        
        # Return result using translation or not 
        if translate:
            return ' '.join('{0} {1}{2}'.format(item['value'], 
                                                _(self.translate[item['name']]), 
                                                _(self.translate[item['punctuation']])) \
                                                for item in __format(result))
        else:
            return ' '.join('{0} {1}{2}'.format(item['value'], item['name'], item['punctuation']) \
                                                for item in __format(result))



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
    """
    Client helper for formatting timestamp depending on opts
    """
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
    """
    Client helper for formatting date
    """
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
    #if display == 'long':
        # We don't need this, using 'medium' and it will automatically remove '+0100' ;)
        #HACK This is a tweak, user should be aware
        #This removed :  +0100 at the end of 'long' output
        #mydate = mydate[:-6]
    return mydate
