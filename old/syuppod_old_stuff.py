
### OLD STUFF ###


class ThreadMainLoop(threading.Thread):
    """Thread for the main loop"""
    def __init__(self, shared, *args, **kwargs):
        super(ThreadMainLoop,self).__init__(*args, **kwargs)
        slef.shared = shared
        
    def run(self):
        # I'm not here...
        pass






    
    #if sys.stdout.isatty():
        #display_init_tty = ''
    #else:
        #display_init_tty = 'Log are located to {0}'.format(pathdir['debuglog'])
    
    ### Parsing arguments ###
    # TODO : add opt sleep loop interval (mini is 30s)
    # TODO : write an autocompletion for bash !
    # TODO : make a class and move to ex: parsing
    #parser = argparse.ArgumentParser(description='Daemon which automate git kernel update.' 
                                     #+ ' Auto update portage tree and pretend world update for gentoo portage package manager.', 
                                     #epilog='By default, %(prog)s will start in log level \'info\'. Interactive mode: log to terminal. Init mode: log to system log and debug to \'{0}\''.format(pathdir['debuglog']))
    #parser.add_argument('-v', 
                        #'--version', 
                        #action = 'version', 
                        #version = '%(prog)s: ' + __version__ + 
                        #' - Copyright (C) 2019 Jérôme Venturi, <jerome dot venturi at gmail dot com> - License: GNU/GPL V3.')
    #Logging Options
    #log_arg = parser.add_argument_group('<Log options>')
    #log_arg.add_argument('-d', 
                     #'--debug', 
                     #help = f'start daemon in log level \'debugg\'.' 
                     #action = 'store_true')
    #log_arg.add_argument('-q', 
                     #'--quiet', 
                     #help = 'start daemon in log level \'quiet\'.', 
                     #action = 'store_true')
    #Git Options
    #git_arg = parser.add_argument_group('<Git options>')
    #git_arg.add_argument('-g', 
                     #'--git', 
                     #help = 'enable git kernel tracking.', 
                     #action = 'store_true')
    #git_arg.add_argument('-r', 
                     #'--repo', 
                     #help = 'specify git kernel \'dir\' (default=\'/usr/src/linux\').',
                     #default = '/usr/src/linux', 
                     #metavar = 'dir')
    #git_arg.add_argument('-p', 
                     #'--pull', 
                     #help = 'pull interval. Where \'int\' should be this form: 1w = 1 week, 1d = 1 day. Minimum is 1d (1 day) and default is 1w (1 week).',
                     #default = 604800,
                     #type=check_args_interval,
                     #metavar = 'int')
    #Portage Options
    #portage_arg = parser.add_argument_group('<Portage options>')
    #portage_arg.add_argument('-s',
                        #'--sync',
                        #help = 'sync interval for portage update tree. Where \'int\' should be this form: 1w = 1 week, 1d = 1 day. Minimum and default is 1d (1 day).', 
                        #metavar = 'int',
                        #type=check_args_interval,
                        #default = 86400)
         
    #args = parser.parse_args()



def check_args_interval(interval, pattern=re.compile(r"^\d+d{1}$|^\d+w{1}$")):
    """Checking interval typo and converting to seconds"""
    if not pattern.match(interval):
        parser.error(f'\'{interval}\' is not an valid interval !')
    
    pattern = re.match(r"^(\d+)(\w+)$", interval)
    
    if int(pattern.group(1)) <= 0:
            parser.error(f'\'{interval}\' is not an valid interval !')    
    # Convert to seconds
    if pattern.group(2) == 'd':
        interval = int(pattern.group(1)) * 86400
        return interval
    if pattern.group(2) == 'w':
        interval = int(pattern.group(1)) * 604800
        return interval



#TODO : make a class and move this to an other module called logging ? logger ?         
#def create_logger_init():
    #"""Setup the logging environment in init mode."""
    #logging.addLevelName(logging.CRITICAL, '[Crit ]')
    #logging.addLevelName(logging.ERROR,    '[Error]')
    #logging.addLevelName(logging.WARNING,  '[Warn ]')
    #logging.addLevelName(logging.INFO,     '[Info ]')
    #logging.addLevelName(logging.DEBUG,    '[Debug]')
    
    #logger           = logging.getLogger(name)
    
    #File debug only part
    #file_handler     = logging.handlers.WatchedFileHandler(debug_log)
    #TODO: change asctime format to the same as Syslog (Month Day Hour:Minutes:Seconds)
    #file_formatter   = logging.Formatter('%(asctime)s  %(name)s  %(levelname)s  %(message)s')
    #file_handler.setFormatter(file_formatter)
    #file_handler.addFilter(LogLevelFilter(logging.DEBUG))
    #file_handler.setLevel(logging.DEBUG)
    #logger.addHandler(file_handler)
    
    #Syslog part
    #syslog_handler   = logging.handlers.SysLogHandler(address='/dev/log',facility='daemon')
    #syslog_handler.setLevel(logging.INFO)
    #syslog_formatter = logging.Formatter('%(name)s %(levelname)s %(message)s')
    #syslog_handler.setFormatter(syslog_formatter)
    #logger.addHandler(syslog_handler)
    
    #return logger


#def create_logger_tty():
    #"""Setup the logging environment in interactive mode (tty)."""
    #logging.addLevelName(logging.CRITICAL, '[Crit ]')
    #logging.addLevelName(logging.ERROR,    '[Error]')
    #logging.addLevelName(logging.WARNING,  '[Warn ]')
    #logging.addLevelName(logging.INFO,     '[Info ]')
    #logging.addLevelName(logging.DEBUG,    '[Debug]')
    
    #logger           = logging.getLogger(name)
    
    #Output all to console
    #console_handler = logging.StreamHandler()
    #console_formatter   = logging.Formatter('%(levelname)s  %(message)s')
    #console_handler.setFormatter(console_formatter)
    #logger.addHandler(console_handler)
    
    #return logger



#class LogLevelFilter(logging.Filter):
    #"""https://stackoverflow.com/a/7447596/190597 (robert)."""
    #def __init__(self, level):
        #self.level = level

    #def filter(self, record):
        #Just revert >= to <= then get only current level or lower.
        #return record.levelno <= self.level
    
    
#class GitTracking:
    #"""Git tracking class."""
    #def __init__(self, interval, repo, stateinfo):
        #Changing None to 'None' for dbus compatibility
        #self.stateinfo = stateinfo
        #self.interval = interval
        #self.human_interval = format_timestamp(self.interval)
        #self.repo = repo
        #self.elasped = 0
        #self.human_elasped = 'None'
        #self.mtime = 0
        #self.human_mtime = 'None'
        #self.remain = 0
        #self.human_remain = 'None'
        
        #Pull attributes
        #self.pull = {
            #'status'    :   'disable',
            #'state'     :   self.stateinfo.load('pull state'),
            #TODO: expose log throught dbus
            #So we have to make an objet which will get last log from 
            #git.log file (and other log file)
            #'log'       :   'TODO',             
            #'error'     :   self.stateinfo.load('pull error'),
            #'count'     :   str(self.stateinfo.load('pull count'))   # str() or get 'TypeError: must be str, not int' or vice versa
        #}
        #Git branch attributes
        #self.branch = {
            #all means from state file
            #'all'   :   {
                #'local' is branch locally checkout (git checkout)
                #'local'     :   sorted(self.stateinfo.load('branch all local').split(), key=StrictVersion), #['5.1', '5.2', '5.3', '5.4'],
                #'remote' is all available branch from remote repo (so including 'local' as well).
                #'remote'    :   sorted(self.stateinfo.load('branch all remote').split(), key=StrictVersion) #['4.20', '5.1', '5.2', '5.3', '5.4', '5.5']
            #},
            #available means after pulling repo (so when running).
            #'available'   :   {
                    #know means available since more than one pull (but didn't locally checkout)
                    #'know'      :   sorted(self.stateinfo.load('branch available know').split(), key=StrictVersion),
                    #new means available since last pull and until next pull
                    #'new'       :   sorted(self.stateinfo.load('branch available new').split(), key=StrictVersion),
                    #all means all available update branch.
                    #'all'       :   sorted(self.stateinfo.load('branch available all').split(), key=StrictVersion)
            #}
        #}
        #Git kernel attributes
        
        #self.kernel = {
            #'all' means all kernel version from git tag command
            #'all'           :   sorted(self.stateinfo.load('kernel all').split(), key=StrictVersion),
            #'available' means update available
            #'available'     :   {
                #'know' means already know from state file (so from an old pull)
                #'know'      :   sorted(self.stateinfo.load('kernel available know').split(), key=StrictVersion),
                #'new' means available from the last pull and until next pull
                #'new'       :   sorted(self.stateinfo.load('kernel available new').split(), key=StrictVersion),
                #'all' means all available for update (so contain both 'know' and 'new'
                #'all'       :   sorted(self.stateinfo.load('kernel available all').split(), key=StrictVersion)
            #},
            #'installed' means compiled and installed into the system
            #'installed'     :   {
                #'running' is from `uname -r' command
                #'running'   :   self.stateinfo.load('kernel installed running'),
                #'all' is all the installed kernel retrieve from /lib/modules which means that
                #/lib/modules should be clean up when removing old kernel...
                #TODO: get mtime for each folder in /lib/modules and print an warning if folder is older than ???
                #with mtime we can know when 
                #'all'       :   sorted(self.stateinfo.load('kernel installed all').split(), key=StrictVersion)
            #}
            #TODO : add 'compiled' key : to get last compiled kernel (time)
        #}
    
    #def get_running_kernel(self):
        #"""Retrieve running kernel version"""
        #try:
            #log.debug('Getting current running kernel:')
            #running = re.search(r'([\d\.]+)', platform.release()).group(1)
            #Check if we get valid version
            #StrictVersion(running)
        #except ValueError as err:
            #log.error(f'{debugtab}Got invalid version number while getting current running kernel:')
            #log.error(f'{debugtab}\t\'{err}\'.')
            #if self.kernel['installed']['running'] == '0.0':
                #log.error(f'{debugtab}Previously know running kernel version is set to factory.')
                #log.error(f'{debugtab}The list of available update kernel version should be false.')
            #else:
                #log.error(f'{debugtab}Keeping previously know running kernel version.')
            #return False
        #except Exception as exc:
            #log.error(f'{debugtab}Got unexcept error while getting current running kernel version:')
            #log.error(f'\t\'{exc}\'')
            #if self.kernel['installed']['running'] == '0.0':
                #log.error(f'{debugtab}Previously know running kernel version is set to factory.')
                #log.error(f'{debugtab}The list of available update kernel version should be false.')
            #else:
                #log.error(f'{debugtab}Keeping previously know running kernel version.')
            #return False
        #else:
            #Valid version
            #log.debug(f'\tGot base version: \'{running}\'.')
            #TODO : compare with old before updating. And if this is the same
            #just pass : so we don't have to write to state file every time
            #self.kernel['installed']['running'] = running
            #Update state file
            #log.debug('\tUpdating state info file.')
            #self.stateinfo.save('kernel installed running', 'kernel installed running: ' + self.kernel['installed']['running'])
            #return True
    

    #def get_installed_kernel(self):
        #"""Retrieve installed and running kernel(s) version on the system"""
        #Get the list of all installed kernel from /lib/modules
        #log.debug('Getting list of all installed kernel from /lib/modules:')
        #try:
            #subfolders = [ ]
            #for folder in os.scandir('/lib/modules/'):
                #if folder.is_dir():
                    #if re.search(r'([\d\.]+)', folder.name):
                        #try:
                            #version = re.search(r'([\d\.]+)', folder.name).group(1)
                            #StrictVersion(version)
                        #except ValueError as err:
                            #log.error(f'{debugtab}While adding to the installed kernel list:')
                            #log.error(f'{debugtab}\tGot: \'{err}\' ...skipping.')
                            #continue
                        #except Exception as exc:
                            #log.error(f'{debugtab}While adding to the installed kernel list:')
                            #log.error(f'{debugtab}\tGot unexcept error: \'{err}\' ...skipping.')
                            #continue
                        #else:
                            #log.debug(f'Found version: \'{version}\'.')
                            #subfolders.append(version)
        #except OSError as error:
            #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                #log.critical(f'Error while reading directory: \'{error.strerror}: {error.filename}\'.')
                #log.critical(f'Daemon is intended to be run as sudo/root.')
                #sys.exit(1)
            #else:
                #log.critical(f'Got unexcept error while reading directory: \'{error}\'.')
                #Don't exit 
            #return
        #except Exception as exc:
            #log.error(f'{debugtab}Got unexcept error while getting installed kernel version list:')
            #log.error(f'\t\'{exc}\'.')
            #if self.kernel['installed']['all'] == '0.0' or self.kernel['installed']['all'] == '0.0.0':
                #log.error('Previously list is empty.')
            #else:
                #log.error('Keeping previously list.')
            #log.error('The list of available update kernel version should be false.')
            #return
        
        #sort
        #subfolders.sort(key=StrictVersion)
        
        #TODO : compare with old before updating.
        #So we can 'print' which one is remove or new 
        
        #Adding list to self.kernel
        #log.debug('Adding to the list: \'{0}\'.'.format(' '.join(subfolders)))
        #self.kernel['installed']['all'] = subfolders
        
        #Update state file
        #log.debug('\tUpdating state file info.')
        #self.stateinfo.save('kernel installed all', 'kernel installed all: ' + ' '.join(self.kernel['installed']['all']))
        
        
    #def get_all_kernel(self):
        #"""Retrieve list of all git kernel version."""
        #First get all tags from git (tags = versions)
        #try:
            #log.debug('Getting all git kernel version (not sorted):')
            #stdout = git.Repo(self.repo).git.tag('-l').splitlines()
        #except Exception as exc:
            #err = exc.stderr
            #Try to strip off the formatting GitCommandError puts on stderr
            #match = re.search(r"stderr: '(.*)'", err)
            #if match:
                #err = match.group(1)
            #TODO: same as pull : count the error
            #log.error(f'{debugtab}Got unexcept error while getting available git kernel version:')
            #log.error(f'{debugtab}\t{err}.')
            #Don't exit just keep previously list
            #if self.kernel['available']['all'][0] == '0.0' or self.kernel['available']['all'][0] == '0.0.0':
                #log.error('{debugtab}Previously list is empty, available git kernel update list should be wrong.')
            #else:
                #log.error('{debugtab}Keeping previously list.')
            #return

        #versionlist = [ ]
        #for line in stdout:
            #if re.match(r'^v([\d\.]+)-zen.*$', line):
                #version = re.match(r'^v([\d\.]+)-zen.*$', line).group(1)
                #try:
                    #StrictVersion(version)
                #except ValueError as err:
                    #log.error('While searching for available git kernel version:')
                    #log.error(f'\tGot: {err}. Skipping...')
                #else:
                    #log.debug(f'Found version : \'{version}\'')
                    #versionlist.append(version)
        
        #if not versionlist:
            #if self.kernel['available']['all'][0] == '0.0' or self.kernel['available']['all'][0] == '0.0.0':
                #log.error('{debugtab}Current and previously git kernel list version are empty.')
                #log.error('{debugtab}Available git kernel update list should be wrong.')
            #else:
                #log.error('{debugtab}Keeping previously list.')
                #log.error('{debugtab}Available git kernel update list could be wrong.')
            #return
        
        #Ok so list is good, keep it
        
        #Remove duplicate
        #log.debug('Removing duplicate entry from all kernel list.')
        #versionlist = list(dict.fromkeys(versionlist))
        
        #self.kernel['all'] = sorted(versionlist, key=StrictVersion)
        #log.debug('\tAdding to \'all\' list: \'{0}\'.'.format(' '.join(self.kernel['all'])))
        
         #Update state file
        #log.debug('\tUpdating state file info.')
        #self.stateinfo.save('kernel all', 'kernel all: ' + ' '.join(self.kernel['all']))
    
    
    #def get_all_branch(self, switcher):
        #"""Retrieve git origin and local branch version list"""
        #switch = { 
            #Main loop - check only local (faster) 
            #'local'     :   {
                    #'local'     :   '-l'
                    #},
            #After dopull()
            #'remote'    :   {   
                    #'remote'    :   '-r'
                    #},
            #Init program
            #'both'      :   {
                    #'local'     :   '-l',
                    #'remote'    :   '-r'
                    #}
            #}
        #for origin, opt in switch[switcher].items():
            #try:
                #log.debug(f'Getting all available branch from {origin}:')
                #stdout = git.Repo(self.repo).git.branch(opt).splitlines()
            #except Exception as exc:
                #err = exc.stderr
                #Try to strip off the formatting GitCommandError puts on stderr
                #match = re.search(r"stderr: '(.*)'", err)
                #if match:
                    #err = match.group(1)
                #log.error(f'{debugtab}Got unexcept error while getting {origin} branch info:')
                #log.error(f'{debugtab}\t{err}.')
                #Don't exit just keep previously list 
                #continue
        
            #versionlist = []
            #for line in stdout:
                #Get only 'master' branch's version list
                #For remote
                #if re.match(r'^\s+\w+\/(\d+\.\d+)\/master', line):
                    #version = re.match(r'^\s+\w+\/(\d+\.\d+)\/master', line).group(1)
                    #try:
                        #StrictVersion(version)
                    #except ValueError as err:
                        #log.error(f'{debugtab}While searching for available {origin} branch list:')
                        #log.error(f'{debugtab}\tGot: \'{err}\' ...skipping.')
                        #continue
                    #else:
                        #Add to the list
                        #log.debug(f'Found version: \'{version}\'.')
                        #versionlist.append(version)
                #For local
                #elif re.match(r'^..(\d+\.\d+)\/master', line):
                    #version = re.match(r'^..(\d+\.\d+)\/master', line).group(1)
                    #try:
                        #StrictVersion(version)
                    #except ValueError as err:
                        #log.error(f'{debugtab}While searching for available {origin} branch list:')
                        #log.error(f'{debugtab}\tGot: \'{err}\' ...skipping.')
                        #continue
                    #else:
                        #Add to the list
                        #log.debug(f'Found version: \'{version}\'.')
                        #versionlist.append(version)
                
            
            #if not versionlist:
                #log.error(f'{debugtab}Couldn\'t find any valid {origin} branch version.')
                #TODO : error or critical ? exit or no ?
                #For now we have to test...
                #Don't update the list - so keep the last know or maybe the factory '0.0'
                #break 
            
            #TODO : compare with old before updating. And if this is the same
            #just pass : so we don't have to write to state file every time
            #Update 
            #self.branch['all'][origin] = sorted(versionlist, key=StrictVersion)
            #log.debug('\tAdding to the list: \'{0}\'.'.format(' '.join(self.branch['all'][origin])))
        
            #Write to state file
            #log.debug('\tUpdating state file.')
            #self.stateinfo.save('branch all ' + origin, 'branch all ' + origin + ': ' + ' '.join(self.branch['all'][origin]))


    #def get_available_update(self, target_attr):
        #"""Compare lists and return all available branch or kernel update."""
        #First compare latest local branch with remote branch list to get current available branch version
        #target = getattr(self, target_attr)
        #if target_attr == 'branch':
            #origin = self.branch['all']['local'][-1]
            #versionlist = target['all']['remote']
        #elif target_attr == 'kernel':
            #origin = self.kernel['installed']['all'][-1]
            #versionlist = target['all']
        
        #log.debug(f'Checking available \'{target_attr}\' update :')
        #current_available = [ ]
        #for version in versionlist:
            #try:
                #for branch -> branch['all']['local'][-1])
                #if StrictVersion(version) > StrictVersion(origin):
                    #current_available.append(version)
            #except ValueError as err:
                #This shouldn't append
                #self.branch['all']['local'] (and ['remote']) is check in get_all_branch()
                #So print an error and continue with next item in the self.branch['all']['remote'] list
                #log.error(f'{debugtab}Got unexcept error while checking available update {target_attr}:')
                #log.error(f'{debugtab}\t{err} skipping...')
                #continue
        
        #if current_available:
            #Sorting 
            #current_available.sort(key=StrictVersion)
            #log.debug('\tFound version(s): \'{0}\'.'.format(' '.join(current_available)))
                      
            #First run and will call dopull() or just first run or calling dopull()
            #if target['available']['new'][0] == '0.0' or self.pull['status'] == 'enable':
                #if target['available']['new'][0] == '0.0' and self.pull['status'] == 'enable':
                    #log.debug('\tFirst run and pull setup:')
                #elif target['available']['new'][0] == '0.0':
                    #log.debug('\tFirst run setup:')
                #elif self.pull['status'] == 'enable':
                    #log.debug('\tPull run setup:')
                
                #for switch in 'all', 'know', 'new':
                    #log.debug(f'\t\tClearing list \'{switch}\'.')
                    #target['available'][switch].clear()
                    
                    #if switch == 'new':
                        #log.debug(f'Adding to \'{switch}\' list: \'0.0.0\' (means nothing available).')
                        #target['available'][switch].append('0.0.0')
                    #else:
                        #log.debug('\t\tAdding to \'{1}\' list: {0}\'.'.format(' '.join(current_available), switch))
                        #target['available'][switch] = current_available
                    
                    #log.debug(f'\t\tUpdating state file for list \'{switch}\'.')
                    #self.stateinfo.save(target_attr + ' available ' + switch, 
                                      #target_attr + ' available ' + switch + 
                                      #': ' + ' '.join(target['available'][switch]))
                    
            #When running - bewteen two pull 
            #else:
                #No previously update list
                #if target['available']['all'][0] == '0.0.0':
                    #So every thing should go to new list
                    #log.debug('No previously update found.')
                    
                    #for switch in 'all', 'know', 'new':
                        #if switch == 'know':
                            #if target['available'][switch][0] == '0.0.0':
                                #log.debug(f'List \'{switch}\' already setup, skipping.')
                                #continue
                            #else:
                                #log.debug(f'\t\t\Clearing list \'{switch}\'.')
                                #target['available'][switch].clear()
                                #log.debug(f'Adding to \'{switch}\' list: \'0.0.0\' (means nothing available).')
                                #target['available'][switch].append('0.0.0')
                        #else:
                            #log.debug(f'\t\t\Clearing list \'{switch}\'.')
                            #target['available'][switch].clear()
                            #log.debug('\t\tAdding to \'{1}\' list: {0}\'.'.format(' '.join(current_available), switch))
                            #target['available'][switch] = current_available
                        
                        #log.debug(f'\t\tUpdating state file for list \'{switch}\'.')
                        #self.stateinfo.save(target_attr + ' available ' + switch, 
                                        #target_attr + ' available ' + switch + 
                                        #': ' + ' '.join(target['available'][switch]))
                #We had already an update.
                #else:
                    #log.debug('Found previously update list.')
                    
                    #ischange = 'no'
                                        
                    #compare 'previously all list' with 'current all list' and vice versa :
                    #self.branch['available']['all'] against current_available
                    #tocompare = {
                        #'firstpass'     :   [ current_available, target['available']['all'], 
                                         #'previously and current update list.', 'previously' ],
                        #'secondpass'    :   [ target['available']['all'], current_available,
                                         #'current and previously update list.', 'current']
                        #}
                    
                    
                    #log.debug('Tracking change multidirectionally:')
                    
                    #for value in tocompare.values():
                        #log.debug('Between {0}'.format(value[2]))
                        
                        #for upper_version in value[0]:
                            #isfound = 'no'
                            #for lower_version in value[1]:
                                #if StrictVersion(upper_version) == StrictVersion(lower_version):
                                    #isfound = 'yes'
                                    #We know that this version is in both list so keep it
                                    #And search over self.branch['available']['new'] and self.branch['available']['know']
                                    #To know if it is in one of them (and it should!!)
                                    #for version in target['available']['know']:
                                        #if StrictVersion(upper_version) == StrictVersion(version):
                                            #log.debug(f'Keeping version \'{upper_version}\': already in list \'all\' and \'know\'.')
                                    #for version in target['available']['new']:
                                        #if StrictVersion(upper_version) == StrictVersion(version):
                                            #log.debug(f'Keeping version \'{upper_version}\': already in list \'all\' and \'new\'.')
                                    #break
                            #if isfound == 'no':
                                #So something has change - 'hard' thing start here
                                #ischange = 'yes'
                                #log.debug(f'Version \'{upper_version}\' not found in {value[3]} list.')
                                #So now we have to know if this version is new or old (so to remove)
                                #So first compare with latest local branch
                                #if StrictVersion(origin) >= StrictVersion(upper_version):
                                    #This mean the version is old (already checkout) so 
                                    #first remove from self.branch['available']['all']
                                    #log.debug(f'Removing already checkout version \'{upper_version}\' from:')
                                    #log.debug('\tList \'all\'.')
                                    #target['available']['all'].remove(upper_version)
                                    #Now search over self.branch['available']['new'] and self.branch['available']['know']
                                    #and remove 
                                    #Normaly if version is found in both than it's a bug !
                                    #for version in target['available']['know']:
                                        #if StrictVersion(upper_version) == StrictVersion(version):
                                            #log.debug('\tList \'all\' and \'know\'.')
                                            #target['available']['know'].remove(upper_version)
                                        #Normally there is only one version because we remove duplicate
                                        #break
                                    #for version in target['available']['new']:
                                        #if StrictVersion(upper_version) == StrictVersion(version):
                                            #log.debug('\tList \'all\' and \'new\'.')
                                            #target['available']['new'].remove(upper_version)
                                        #break
                                #So here it's a new version so it goes to ['available']['new']
                                #And also to ['available']['all'] 
                                #elif StrictVersion(origin) < StrictVersion(upper_version):
                                    #Search over the list and remove '0.0.0' or '0.0' - got a 'bug' like that when testing 
                                    #it was '0.0.0' but add '0.0' in case ;)
                                    #for switch in 'all', 'new':
                                        #if '0.0' in target['available'][switch]:
                                            #log.debug(f'Removing wrong option \'0.0\' from list \'{switch}\'.')
                                            #target['available'][switch].remove('0.0')
                                        #elif '0.0.0' in target['available'][switch]:
                                            #log.debug(f'Removing wrong option \'0.0.0\' from list \'{switch}\'.')
                                            #target['available'][switch].remove('0.0.0')
                                    #Add to both list 'all' and 'new' - i forgot to add to 'all' list ...
                                    #log.debug(f'Adding new version \'{upper_version}\' to list \'new\' and \'all\'.')
                                    #target['available']['new'].append(upper_version)
                                    #target['available']['all'].append(upper_version)
                
                    #Nothing change - don't write to state file 
                    #if ischange == 'no':
                        #log.debug('Finally, didn\'t found any change, previously data has been keep.')
                    #Something change - write to the disk 
                    #elif ischange == 'yes':
                        
                        #for switch in 'all', 'know', 'new':
                            #Check if list is empty
                            #if not target['available'][switch]:
                                #log.debug(f'Adding to the empty list \'{switch}\': \'0.0.0\' (means nothing available).')
                                #target['available'][switch] = [ ] # To make sure it's recognise as a list.
                                #target['available'][switch].append('0.0.0')
                            #else:
                                #Remove duplicate in case
                                #log.debug(f'Removing duplicate entry (if any) from list \'{switch}\'.')
                                #target['available'][switch] =  list(dict.fromkeys(target['available'][switch]))
                            #Then write to the state file 
                            #log.debug(f'Updating state file for list \'{switch}\'.')
                            #self.stateinfo.save(target_attr + ' available ' + switch, 
                                              #target_attr + ' available ' + switch + 
                                              #': ' + ' '.join(target['available'][switch]))
            
        #else:
            #log.debug('\tNo update found.')
            
            #for switch in 'all', 'know', 'new':
                #No need to write to state file if already in good state...
                #if target['available'][switch][0] == '0.0.0':
                    #log.debug(f'List \'{switch}\' already setup, skipping.')
                #else:
                    #log.debug(f'\tClearing list \'{switch}\'.')
                    #target['available'][switch].clear()
                    #log.debug(f'Adding to the list \'{switch}\': \'0.0.0\' (means nothing available).')
                    #target['available'][switch].append('0.0.0')
                    #log.debug(f'Updating state file for list \'{switch}\'.')
                    #self.stateinfo.save(target_attr + ' available ' + switch, 
                                      #target_attr + ' available ' + switch + 
                                      #': ' + ' '.join(target['available'][switch]))


    #def get_last_pull(self):
        #"""Get last git pull timestamp"""
        #path = pathlib.Path(self.repo + '/.git/FETCH_HEAD')
        #if path.is_file():
            #self.mtime = round(path.stat().st_mtime)
            #self.human_mtime = datetime.fromtimestamp(self.mtime).strftime("%A, %B %d, %Y %H:%M:%S")
            #log.debug(f'Last git pull for repository \'{self.repo}\': {self.human_mtime}.')
            #return
        #path = pathlib.Path(self.repo + '.git/refs/remotes/origin/HEAD')
        #if path.is_file():
            #log.debug('Repository \'{self.repo}\' has never been updated (pull).')
            #self.pull['status'] = 'enable'
            #return
   

    #def check_pull(self):
        #"""Check git pull status depending on specified interval"""
        #if self.pull['status'] == 'disable':
            #current_timestamp = time.time()
            #self.elasped = round(current_timestamp - self.mtime)
            #self.human_elasped = format_timestamp(self.elasped)
            #self.remain = self.interval - self.elasped
            #self.human_remain = format_timestamp(self.remain)
            #log.debug(f'Git pull elasped time: {self.human_elasped}') 
            #log.debug(f'Git pull remain time: {self.human_remain}')
            #log.debug(f'Git pull interval: {self.human_interval}.')
            #if self.remain <= 0:
                #self.pull['status'] = 'enable'
    

    #def dopull(self):
        #"""Pulling git repository"""
        #try:
            #gitlog = git.Repo(self.repo).git.pull()
        #except Exception as exc:
            #err = exc.stderr
            #Try to strip off the formatting GitCommandError puts on stderr
            #match = re.search("stderr: '(.*)'$", err)
            #if match:
                #err = match.group(1)
            #log.error('Error while pulling git repository:')
            #log.error(f'\t{err}')
            
            #Just mark the first error and exit if second error 
            #if self.pull['error'] == '1':
                #Look like it's not possible to get the error number
                #So it's not possible to know that is the same error...
                #log.critical('This is the second error while pulling git repository.')
                #log.critical('Cannot continue, please fix the error.')
                #sys.exit(1)
            #self.pull['state'] = 'Failed'
            #self.pull['error'] = 1
            
            #Write error status to state file so if the program is stop and restart
            #it will know that it was already an error
            #Write 'state' to state file as well
            #self.stateinfo.save('pull error', 'pull error: 1')
            #self.stateinfo.save('pull state', 'pull state: Failed')
        
        #else:
            #self.pull['state'] = 'Success'
            #Update 'state' status to state file
            #self.stateinfo.save('pull state', 'pull state: Success')
            #log.info('Successfully update git kernel repository.')
            
            #Erase status of git pull error in git.state file and reset self.pull error to 0
            #self.pull['error'] = 0
            #self.stateinfo.save('pull error', 'pull error: 0')
            
            #Append one more pull to git state file section 'pull'
            #Convert to integrer
            #self.pull['count'] = int(self.pull['count'])
            #self.pull['count'] += 1
            #self.stateinfo.save('pull count', 'pull count: ' + str(self.pull['count'])) # Same here str() or 'TypeError: must be str, not int'
            
            #Append log to git.log file 
            #sttime = datetime.now().strftime('%Y-%m-%d %H:%M:%S  ')
            #try:
                #with pathlib.Path(pathdir['gitlog']).open(mode='a') as mylogfile:
                    #mylogfile.write('##################################\n')
                    #for line in gitlog.splitlines():
                        #mylogfile.write(sttime + line + '\n')
            #Catching all exception because it's not fatal to the program
            #It will output the pull log through logging module 
            #except Exception as exc:
                #log.error('Error while writing git pull log to \'{0}\':'.format(pathdir['gitlog']))
                #log.error(f'\t{exc}')
                #log.error('Content of git pull log:')
                #for line in gitlog.splitlines():
                    #log.error('\t' + line)
            #else:
                #log.debug('Successfully wrote git pull log to \'{0}\'.'.format(pathdir['gitlog']))
     
  
    #def check_config(self):
        #"""Check git config file options"""    
        #Check / add git config for get all tags from remote origin repository
                              #fetch = +refs/heads/*:refs/remotes/origin/*
        #regex = re.compile(r'\s+fetch.=.\+refs/heads/\*:refs/remotes/origin/\*')
        #to_write = '        fetch = +refs/tags/*:refs/tags/*'
        #re_tag = re.compile(r'\s+fetch.=.\+refs/tags/\*:refs/tags/\*')
        
        #try:
            #with pathlib.Path(self.repo + '/.git/config').open() as myfile:
                #for line in myfile:
                    #if re_tag.match(line):
                        #log.debug('Git config file already contain option to fetch all tags from remote repository.')
                        #return
        #except (OSError, IOError) as error:
            #log.critical('Error while checking git config file option.')
            #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                #log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                #log.critical('Daemon is intended to be run as sudo/root.')
            #else:
                #log.critical(f'Got: \'{error}\'.')
            #sys.exit(1)
        
        #Make an backup
        #try:
            #Check if backup file already exists 
            #if not pathlib.Path(self.repo + '/.git/config.backup_' + name).is_file(): 
                #shutil.copy2(self.repo + '/.git/config', self.repo + '/.git/config.backup_' + name)
        #except (OSError, IOError) as error:
            #log.critical('Error while making an backup to git config file.')
            #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                #log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                #log.critical('Daemon is intended to be run as sudo/root.')
            #else:
                #log.critical(f'Got: \'{error}\'.')
            #sys.exit(1)
        #Modify
        #try:
            #with pathlib.Path(self.repo + '/.git/config').open(mode='r+') as myfile:
                #old_file = myfile.readlines()   # Pull the file contents to a list
                #myfile.seek(0)                  # Jump to start, so we overwrite instead of appending
                #myfile.truncate                 # Erase file 
                #for line in old_file:
                    #if regex.match(line):
                        #myfile.write(line)
                        #myfile.write(to_write + '\n')
                    #else:
                        #myfile.write(line)
        #except (OSError, IOError) as error:
            #log.critical('Error while adding option to git config file.')
            #log.critical('Tried to add options to get all tags from remote repository.')
            #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                #log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                #log.critical(f'Daemon is intended to be run as sudo/root.')
            #else:
                #log.critical(f'Got: \'{error}\'')
            #sys.exit(1)
        #else:
            #log.debug('Added option to git config file: fetch all tags from remote repository.')


#class PortageTracking:
    #"""Portage tracking class"""
    
    #def __init__(self, interval, stateinfo):
        #self.stateinfo = stateinfo
        #self.interval = interval
        #self.human_interval = format_timestamp(self.interval)
        #self.elasped = 0
        #self.human_elasped = 'None'
        #self.remain = 0
        #self.human_remain = 'None'
               
        #Sync attributes
        #self.sync = {
            #'status'    :   False, # By default it's disable ;)
            #'state'     :   self.stateinfo.load('sync state'),
            #'log'       :   'TODO', # TODO CF __init__ --> self.pull --> 'log'
            #'error'     :   self.stateinfo.load('sync error'),
            #'count'     :   str(self.stateinfo.load('sync count')),   # str() or get 'TypeError: must be str, not int' or vice versa
            #'timestamp' :   int(self.stateinfo.load('sync timestamp')) 
            #}
        #World attributes
        #self.world = {
            #'last'      :   self.stateinfo.load('world last'),
            #'status'    :   False,   # This mean we don't have to run pretend world update
            #'start'     :   int(self.stateinfo.load('world start')),
            #'stop'      :   int(self.stateinfo.load('world stop')),
            #'state'     :   self.stateinfo.load('world state'),
            #'failed'    :   int(self.stateinfo.load('world failed')),            
            #'update'    :   int(self.stateinfo.load('world update'))
        #}
    
    
    #def check_sync(self, init_run=False):
        #""" Checking if we can sync repo depending on time interval.
        #Minimum is 24H. """
        #Get the last emerge sync timestamp
        #myparser = EmergeLogParser()
        #sync_timestamp = myparser.last_sync()
        
        #current_timestamp = time.time()
        
        #if sync_timestamp:
            #Ok it's first run ever 
            #if self.sync['timestamp'] == 0:
                #log.debug('Found portage update repo timestamp set to factory: \'0\'.')
                #log.debug(f'Setting to: \'{sync_timestamp}\'.')
                #self.sync['timestamp'] = sync_timestamp
            #This mean that sync has been run outside the program 
            #elif init_run and self.sync['timestamp'] != sync_timestamp:
                #log.debug('Portage repo has been update outside the program, forcing pretend world...')
                #self.world['status'] = True # So run pretend world update
                #self.sync['timestamp'] = sync_timestamp
            #elif self.sync['timestamp'] != sync_timestamp:
                #log.warning('Bug in class \'PortageTracking\', method: check_sync(): timestamp are not the same...')
            
            #self.elasped = round(current_timestamp - sync_timestamp)
            #self.remain = self.interval - self.elasped
            #log.debug('Update repo elasped time: \'{0}\'.'.format(format_timestamp(self.elasped)))
            #log.debug('Update repo remain time: \'{0}\'.'.format(format_timestamp(self.remain)))
            #log.debug('Update repo interval: \'{0}\'.'.format(format_timestamp(self.interval)))
            
            #if self.remain <= 0:
                #self.sync['status'] = True
                #return True
            
            #return False
        
        #else:
            #return False        
    
    
    #def dosync(self):
        #""" Syncing the repo(s) """
        #Initalise
        #sync = SyncRepos()
        
        #Get repo list
        #repos = sync._get_repos()

        #if repos[0]:
            #We have repo(s) to sync
            #Get the name of each
            #names = re.findall('RepoConfig\(name=\'(.*?)\',.location', str(repos[1]), re.DOTALL)
            
            #if names:
                #repo_count = len(names)
                #Print only first three elements if list > 3
                #if repo_count > 3:
                    #repo_print = [ 'repositories',  ', '.join(names[:3]) + ' (+' + str(repo_count - 3) + ')' ]
                #elif repo_count == 1:
                    #repo_print = [ 'repository', ', '.join(names) ]
                #else:
                    #repo_print = [ 'repositories', ', '.join(names) ]
            #else:
                #This shouldn't happend ...
                #repo_print = [ 'repository',  '?...' ]
                #repo_count = '?'
        
            #sttime = datetime.now().strftime('%Y-%m-%d %H:%M:%S  ')
            #log.debug(f'Updating {repo_count} portage {repo_print[0]}.')
            #with CapturedFd(fd=[1,2]) as tmpfile:
                #TODO:
                #We have choice between all_repos and auto_sync 
                #So give the choice as well:
                #opts = --reposync, -y
                #Default is auto_sync()
                #state list is the return code from sync and as well msg from portage (if any)
                #state = sync.auto_sync()
                
            #try:
                #TODO : logrotate ! and give the choice as well : opts = --logrotate -l
                #with pathlib.Path(tmpfile.name).open() as mytmp:
                    #with pathlib.Path(pathdir['synclog']).open(mode='a') as mylogfile:
                        #mylogfile.write('##########################################\n')
                        #for line in mytmp.readlines():
                            #mylogfile.write(sttime + line)
            #Exception is from pathlib
            #except (OSError, IOError) as error:
                #log.warning('Error while writing sync log to log file.')
                #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                    #log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                    #log.critical(f'Daemon is intended to be run as sudo/root.')
                    #sys.exit(1)
                #else:
                    #log.warning(f'Got: \'{error}\'.')
                    #log.warning('You can retrieve complete log from dbus client.')
            #else:
                #log.debug('Sync log has been wrote to file: \'{0}\'.'.format(pathlib.Path(pathdir['synclog'])))
            
            #Examine state[0] True / False
            #if state[0]:
                #Sync is ok 
                #self.sync['state'] = 'Success'
                #Update state file
                #self.stateinfo.save('sync state', 'sync state: Success')
                #log.info(f'Successfully update portage {repo_print[0]}: {repo_print[1]}.')
                
                #Erase error 
                #self.sync['error'] = 0
                #self.stateinfo.save('sync error', 'sync error: 0')
                
                #Count only success sync
                #self.sync['count'] = int(self.sync['count'])
                #self.sync['count'] += 1
                #self.stateinfo.save('sync count', 'sync count: ' + str(self.sync['count']))
                
                #Reset self.remain to interval
                #self.remain = self.interval
                
                #Get the sync timestamp from emerge.log 
                #myparser = EmergeLogParser()
                #sync_timestamp = myparser.last_sync()
                
                #if sync_timestamp:
                    #if sync_timestamp == self.sync['timestamp']:
                        #log.warning('Bug in class \'PortageTracking\', method: dosync(): timestamp are equal...')
                    #else:
                        #log.debug('Updating sync timestamp from \'{0}\' to \'{1}\'.'.format(self.sync['timestamp'], sync_timestamp))
                        #self.sync['timestamp'] = sync_timestamp
                        #self.stateinfo.save('sync timestamp', 'sync timestamp: ' + self.sync['timestamp'])
                
            #else:
                #Problem
                #self.sync['state'] = 'Failed'
                #self.stateinfo.save('sync state', 'sync state: Failed')
                #log.error(f'Failed to update portage {repo_print[0]}: {repo_print[1]}.')
                
                #We mark the error and we exit after 3 retry
                #TODO : check this and pull['error'] as well and print an warning at startup 
                #or we can stop if error > max count and add an opts to reset the error (when fix)
                #then the option could be add to dbus client - thinking about this ;)
                #self.sync['error'] = int(self.sync['error'])
                
                #if int(self.sync['error']) > 3:
                    #log.critical('This is the third error while syncing repo(s).')
                    #log.critical('Cannot continue, please fix the error.')
                    #sys.exit(1)
                #Increment error count
                #self.sync['error'] += 1
                #self.stateinfo.save('sync error', 'sync error: ' + str(self.sync['error']))
                
                #Retry in self.interval
                #log.info('Will retry update in {0}'.format(format_timestamp(self.interval)))
                #self.remain = self.interval
            
            #This is for msg return from sync.auto_sync() but
            #i still don't really know which kind of message is...
            #TODO : investigate so we can know if this is needed or not.
            #if state[1]:
                #log.info(f'Got message while updating {repo_print[0]}: {state[1]}.')
        
        #No repo found ?!
        #else:
            #log.error('No repository found, abording update !')
            #self.sync['state'] = 'No Repo'
            #self.stateinfo.save('sync state', 'sync state: No Repo')
            
            #Increment error as well
            #if int(self.sync['error']) > 3:
                #log.critical('This is the third error while syncing repo(s).')
                #log.critical('Cannot continue, please fix the error.')
                #sys.exit(1)
            
            #self.sync['error'] = int(self.sync['error'])
            #self.sync['error'] += 1
            #self.stateinfo.save('sync error', 'sync error: ' + str(self.sync['error']))
            
            #Ok keep syncing any way
            #self.remain = self.interval
    
    #def get_last_world_update(self):
        #"""Getting last world update timestamp"""
        #Check if we are running world update right now
        #if world_update_inprogress():
            #return 'inprogress'
            #For now keep last know timestamp
        #else:
            #myparser = EmergeLogParser()
            #Ok for now keep default setting 
            #TODO : give the choice cf EmergeLogParser() --> last_world_update()
            #world_timestamp = myparser.last_world_update()
            
            #if world_timestamp:
                #self.world['start'] = world_timestamp['start']
                #self.world['stop'] = world_timestamp['stop']
                #self.world['state'] = world_timestamp['state']
                #try:
                    #self.world['failed'] = world_timestamp['failed']
                #except KeyError:
                    #self.world['failed'] = 0
                #return True
            #else:
                #return False
                       
            
    #def pretend_world(self):
        #"""Check how many package to update"""
        #update_packages = False
        #retry = 0
        #find_build_packages = re.compile(r'Total:.(\d+).packages.*')
        #myconfig = _emerge.actions._emerge_config(action={ 'update' :  True }, args={ 'world' : True }, 
                                                      #opts={ '--verbose' : True, '--pretend' : True, 
                                                             #'--deep' : True, '--newuse' : True, 
                                                             #'--update' : True, '--with-bdeps' : True  })
            
        #while retry < 2:
            #loadconfig = _emerge.actions.load_emerge_config(emerge_config=myconfig)
            #try:
                #sttime = datetime.now().strftime('%Y-%m-%d %H:%M:%S  ')
                #TODO : Should we capture stderr and stdout singly ?
                #TODO : expose this to dbus client and maybe propose to apply the proposal update ?
                       #Any way we HAVE to capture both (stdout and sterr) or sdtout will be print 
                       #to terminal or else where...
                #log.debug('Getting how many packages have to be update.')
                #log.debug('This could take some time, please wait...')
                #with CapturedFd(fd=[1, 2]) as tmpfile:
                    #_emerge.actions.action_build(loadconfig)
                    
                #Make sure we have a total package
                #with pathlib.Path(tmpfile.name).open() as mytmp:
                    #with pathlib.Path(pathdir['pretendlog']).open(mode='a') as mylogfile:
                        #mylogfile.write('##################################################################\n')
                        #for line in mytmp.readlines():
                            #mylogfile.write(sttime + line)
                            #if find_build_packages.match(line):
                                #Ok so we got packages then don't retry
                                #retry = 2
                                #update_packages = int(find_build_packages.match(line).group(1))
                    
                #Ok so do we got update package ?
                #if retry == 2:
                    #if update_packages > 1:
                        #to_print = 'packages'
                    #else:
                        #to_print = 'package'
                    
                    #log.info(f'Found {update_packages} {to_print} to update.')
                #else:
                    #Remove --with-bdeps and retry one more time.
                    #myconfig = _emerge.actions._emerge_config(action={ 'update' :  True }, args={ 'world' : True }, 
                                                                #opts={ '--verbose' : True, '--pretend' : True, 
                                                                       #'--deep' : True, '--newuse' : True, 
                                                                       #'--update' : True}) 
                    #log.debug('Couldn\'t found how many package to update, retrying without opt \'--with-bdeps\'.')
                    #retry = 1
            #TODO : get Exception from portage / _emerge !!
            #except Exception as exc:
                #log.error(f'Got unexcept error : {exc}')
            
        #Make sure we have some update_packages
        #if update_packages:
            #self.world['update'] = int(update_packages)
            #return True
        #else:
            #self.world['update'] = False
            #return False
            
            
#class StateInfo:
    #"""Write, edit or get info to and from state file"""
    #def config(self):
        #"""Create, check state file and its options"""
        #If new file, factory info
        #TODO: add options to reset {pull,sync}_count to factory
        #try:
            #if not pathlib.Path(pathdir['state']).is_file():
                #log.debug('Create state file: \'{0}\'.'.format(pathdir['state']))
                #with pathlib.Path(pathdir['state']).open(mode='w') as statefile:
                    #for option in stateopts:
                        #log.debug(f'Adding option \'{option}\'.')
                        #statefile.write(option + '\n')
            #else:
                #with pathlib.Path(pathdir['state']).open(mode='r+') as statefile:
                    
                    #regex = re.compile(r'^(.*):.*$')
                    
                    
                    #Get the content in the list
                    #oldstatefile = statefile.readlines()
                    
                    #Erase file
                    #statefile.seek(0)
                    #statefile.truncate()
                                        
                    #Check if options from stateopts list is found in current state file.
                    #for option in stateopts:
                        #isfound = 'no'
                        #for line in oldstatefile:
                            #if regex.match(line).group(1) == regex.match(option).group(1):
                                #log.debug('Found option \'{0}\' in state file.'.format(regex.match(option).group(1)))
                                #isfound = 'yes'
                                #break
                        #if isfound == 'no':
                            #oldstatefile.append(option + '\n')           
                            #log.debug('Wrote new option \'{0}\' in state file'.format(regex.match(option).group(1)))
                    
                    #Check if wrong / old option is found in current state file and append in the list toremove
                    #toremove = []
                    #for line in oldstatefile:
                        #isfound = 'no'
                        #for option in stateopts:
                            #try:
                                #if regex.match(line).group(1) == regex.match(option).group(1):
                                        #isfound = 'yes'
                                        #break
                            #except AttributeError as error:
                                #This is 'normal' if option is other then 'name and more: other' 
                                #exemple 'name_other' will not match group(1) and will raise 
                                #exception AttributeError. So this mean that the option is wrong anyway.
                                
                                #Break or this will print as many as stateopts list item.
                                #break
                        #if isfound == 'no':
                            #toremove.append(line)
                    
                    #Remove old or wrong option found from oldstatefile list
                    #for wrongopt in toremove:
                        #oldstatefile.remove(wrongopt)
                        #log.debug('Remove wrong or old option \'{0}\' from state file'.format(wrongopt.rstrip()))
                    
                    #(re)write file
                    #for line in oldstatefile:
                        #statefile.write(line)
        #except (OSError, IOError) as error:
            #log.critical('Error while checking / creating \'{0}\' state file.'.format(pathdir['state']))
            #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                #log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                #log.critical('Daemon is intended to be run as sudo/root.')
            #else:
                #log.critical(f'Got: \'{error}\'.')
            #sys.exit(1)           
        
    #def write(self, pattern, to_write):
        #"""Edit info to specific linne of state file"""
        #try:
            #regex = re.compile(r"^" + pattern + r":.*$")
            #with pathlib.Path(pathdir['state']).open(mode='r+') as statefile:
                #oldstatefile = statefile.readlines()   # Pull the file contents to a list
                
                #Erase the file
                #statefile.seek(0)
                #statefile.truncate()
                
                #Rewrite 
                #for line in oldstatefile:
                    #if regex.match(line):
                        #statefile.write(to_write + '\n')
                    #else:
                        #statefile.write(line)
        #except (OSError, IOError) as error:
            #log.critical('Error while modifing \'{0}\' state file.'.format(pathdir['state']))
            #log.debug(f'\tTried to write: \'{to_write}\' in section: \'{pattern}\'.')
            #log.critical(f'\tGot: \'{error}\'.')
            #sys.exit(1)

    #def read(self, pattern):
        #"""Read info from specific state file"""
        #try:
            #regex = re.compile(r"^" + pattern + r":.(.*)$")
            #with pathlib.Path(pathdir['state']).open() as statefile: 
                #for line in statefile:
                     #if regex.match(line):
                        #return regex.match(line).group(1)
        #except (OSError, IOError) as error:
            #log.critical('Error while reading \'{0}\' state file.'.format(pathdir['state']))
            #log.debug(f'\tTried to read section: \'{pattern}\'.')
            #log.critical(f'\tGot: \'{error}\'')
            #sys.exit(1)        
            
            
            
#class CapturedFd:
    #"""Pipe the specified fd to an temporary file
    #https://stackoverflow.com/a/41301870/11869956
    #Modified to capture both stdout and stderr.
    #Need a list as argument ex: fd=[1,2]"""
    #TODO : not sure about that still thinking :p
    #def __init__(self, fd):
        #self.fd = fd
        #self.prevfd = [ ]

    #def __enter__(self):
        #mytmp = tempfile.NamedTemporaryFile()
        #for fid in self.fd:
            #self.prevfd.append(os.dup(fid))
            #os.dup2(mytmp.fileno(), fid)
        #return mytmp

    #def __exit__(self, exc_type, exc_value, traceback):
        #i = 0
        #for fid in self.fd:
            #os.dup2(self.prevfd[i], fid)
            #i = i + 1

#class EmergeLogParser:
    #"""Parse emerge.log file and extract informations"""
    #def __init__(self):
        #self.aborded = 5      
    
    #def last_sync(self, lastlines=100):
        #"""Return last sync timestamp
        #@returns: timestamp
        #@error: return False
        #Exemple of emerge.log :
            #1569592862: Started emerge on: sept. 27, 2019 16:01:02
            #1569592862:  *** emerge --keep-going --quiet-build=y --sync
            #1569592862:  === sync
            #1569592862: >>> Syncing repository 'gentoo' into '/usr/portage'...
            #1569592868: >>> Starting rsync with rsync://92.60.51.128/gentoo-portage
            #1569592932: === Sync completed for gentoo
            #1569592932: >>> Syncing repository 'steam-overlay' into '/var/lib/layman/steam-overlay'...
            #1569592932: >>> Starting layman sync for steam-overlay...
            #1569592933: >>> layman sync succeeded: steam-overlay
            #1569592933: >>> laymansync sez... "Hasta la sync ya, baby!"
            #1569592933: === Sync completed for steam-overlay
            #1569592933: >>> Syncing repository 'reagentoo' into '/var/lib/layman/reagentoo'...
            #1569592933: >>> Starting layman sync for reagentoo...
            #1569592933: >>> layman sync succeeded: reagentoo
            #1569592933: >>> laymansync sez... "Hasta la sync ya, baby!"
            #1569592933: === Sync completed for reagentoo
            #1569592933: >>> Syncing repository 'rage' into '/var/lib/layman/rage'...
            #1569592934: >>> Starting layman sync for rage...
            #1569592934: >>> layman sync succeeded: rage
            #1569592934: >>> laymansync sez... "Hasta la sync ya, baby!"
            #1569592934: === Sync completed for rage
            #1569592934: >>> Syncing repository 'pinkpieea' into '/var/lib/layman/pinkpieea'...
            #1569592934: >>> Starting layman sync for pinkpieea...
            #1569592935: >>> layman sync succeeded: pinkpieea    
            #1569592935: >>> laymansync sez... "Hasta la sync ya, baby!"
            #1569592935: === Sync completed for pinkpieea
            #1569592937:  *** terminating. 
            #adapt from https://stackoverflow.com/a/54023859/11869956"""
      
        #RE
        #start_re = re.compile(r'^(\d+):\s{2}===.sync$')
        #completed_re = re.compile(r'^\d+:\s{1}===.Sync.completed.for.gentoo$')
        #stop_re = re.compile(r'^\d+:\s{2}\*\*\*.terminating.$')
        
        #self.lastlines = lastlines
        #with_delimiting_lines = True
        #collect = [ ]
        #keep_running = True
        #count = 1
        
        #while keep_running:
            #log.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, pathdir['emergelog']))
            #inside_group = False
            #log.debug('Extracting list of successfully update for main repo \'gentoo\'.')
            #for line in self.getlog(self.lastlines):
                #if inside_group:
                    #if stop_re.match(line):
                        #inside_group = False
                        #if with_delimiting_lines:
                            #group.append(line)
                        #Ok so with have all the line
                        #search over group list to check if sync for repo gentoo is in 'completed' state
                        #and add timestamp line '=== sync ' to collect list
                        #TODO: should we warn about an overlay which failed to sync ?
                        #for value in group:
                            #if completed_re.match(value):
                                #collect.append(current_timestamp)
                                #log.debug(f'Recording: \'{current_timestamp}\'.')
                    #else:
                        #group.append(line)
                #elif start_re.match(line):
                    #inside_group = True
                    #group = [ ]
                    #current_timestamp = int(start_re.match(line).group(1))
                    #if with_delimiting_lines:
                        #group.append(line)
            #Collect is finished.
            #If we got nothing then extend by 100 last lines to self.getlog()
            #if collect:
                #keep_running = False
            #else:
                #if self._keep_collecting(count, ['last update for main repo \'gentoo\'', 
                                            #'never sync...']):
                    #count = count + 1
                    #keep_running = True
                #else:
                    #return False
        
        #Proceed to get the latest timestamp
        #log.debug('Extracting latest update from: {0}'.format(', '.join(str(timestamp) for timestamp in collect)))
        #latest = collect[0]
        #for timestamp in collect:
            #if timestamp > latest:
                #latest = timestamp
        #if latest:
            #log.debug(f'Found: \'{latest}\'.')
            #return latest
        
        #log.error('Failed to found latest update timestamp for main repo \'gentoo\'.')
        #return False
     
    
    #def last_world_update(self, lastlines=1000, incompleted=True, nincompleted=[30/100, 'percentage']):
        #"""Get last world update timestamp
        #@param lastlines  read last n lines from emerge log file (as we don't have to read all the file to get last world update)
                          #you can tweak it but any way if you lower it and if the function don't get anything in the first pass
                          #it will increment it depending on function _keep_collecting()
        #@type integer
        #@param incompleted enable or disable the search for start but failed update world
        #@type boolean
        #@param nincompleted a list which filter start from how much packages the function capture or not failed update world.                        
        #@type list where first element should integer or percentage in this form (n/100)
                   #where second element require either 'number' (if first element is number) or 'percentage' (if first element is percentage)
        #@returns: dictionary
        #@keys:  'start'     -> start timestamp.
                #'stop'      -> stop timestamp.
                #'packages'  -> total packages which has been / could been update.
                #'state'     -> could be 'completed' if success or 'incompleted' if failed.
                #'failed'    -> definied only if failed, package number which failed. 
        #@error: return False
        
        #Exemple from emerge.log:
            #1569446718:  *** emerge --newuse --update --ask --deep --keep-going --quiet-build=y --verbose world
            #1569447047:  >>> emerge (1 of 44) sys-kernel/linux-firmware-20190923 to /
            #1569447213:  === (1 of 44) Cleaning (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            #1569447214:  === (1 of 44) Compiling/Merging (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            #1569447219:  === (1 of 44) Merging (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            #1569447222:  >>> AUTOCLEAN: sys-kernel/linux-firmware:0
            #1569447222:  === Unmerging... (sys-kernel/linux-firmware-20190904)
            #1569447224:  >>> unmerge success: sys-kernel/linux-firmware-20190904
            #1569447225:  === (1 of 44) Post-Build Cleaning (sys-kernel/linux-firmware-20190923::/usr/portage/sys-kernel/linux-firmware/linux-firmware-20190923.ebuild)
            #1569447225:  ::: completed emerge (1 of 44) sys-kernel/linux-firmware-20190923 to / """
        
        #collect = {
            #'completed' :   [ ],
            #'incompleted'   :   [ ]
            #}
        
        #incompleted_msg = ''
        #if incompleted:
            #incompleted_msg = 'and incompleted'
        
        #compiling = False
        #packages_count = 1
        #keep_running =  True
        #current_package = False
        #count = 1
        #self.lastlines = lastlines
        
        #RE
        #start = re.compile(r'^(\d+):\s{2}\*\*\*.emerge.*world.*$')
        #So make sure we start to compile the world update and this should be the first package 
        #not_aborded = re.compile(r'^\d+:\s{2}>>>.emerge.\(1.of.(\d+)\).*$')
        #failed = re.compile(r'(\d+):\s{2}\*\*\*.exiting.unsuccessfully.with.status.*$')
        #succeeded = re.compile(r'(\d+):\s{2}\*\*\*.exiting.successfully\.$')
        
        #TODO : Give a choice to enable or disable incompleted collect
               #Also: i think we should remove incompleted update which just failed after n package 
               #Where n could be : a pourcentage or a number (if think 30% could be a good start)
               #Maybe give the choice to tweak this as well  - YES !
        #TODO : Also we can update 'system' first (i'm not doing that way but)
               #Add this option as well :)
        
        #while keep_running:
            #log.debug('Loading last \'{0}\' lines from \'{1}\'.'.format(self.lastlines, pathdir['emergelog']))
            #mylog = self.getlog(self.lastlines)
            #log.debug(f'Extracting list of completed {incompleted_msg} world update informations.')
            #for line in mylog:
                #if compiling:
                    #if current_package:
                        #if failed.match(line):
                            #current_package = False
                            #compiling = False
                            #If incompleted is enable (by default)
                            #if incompleted:
                                #if nincompleted[1] == 'percentage':
                                    #if packages_count <= group['packages'] * nincompleted[0]:
                                        #packages_count = 1
                                        #continue
                                #elif nincompleted[1] == 'number':
                                    #if packages_count <= nincompleted[0]:
                                        #packages_count = 1
                                        #continue
                                #group['stop'] = int(failed.match(line).group(1))
                                #Record how many package compile successfully
                                #So if incompleted is enable and nincompleted
                                #group['failed'] = packages_count
                                #group['state'] = 'incompleted'
                                #collect['incompleted'].append(group)
                                #log.debug('Recording incompleted, start: {0}, stop: {1}, packages: {2}, failed at: {3}'
                                          #.format(group['start'], group['stop'], group['packages'], group['failed']))
                            #packages_count = 1
                        #elif re.match('\d+:\s{2}:::.completed.emerge.\(' 
                                            #+ str(packages_count) + r'.*of.*' 
                                            #+ str(group['packages']) + r'\).*$', line):
                            #current_package = False # Compile finished
                            #compiling = True
                            #packages_count = packages_count + 1
                    #elif re.match(r'^\d+:\s{2}>>>.emerge.\('
                                            #+ str(packages_count) + r'.*of.*' 
                                            #+ str(group['packages']) + r'\).*$', line):
                        #current_package = True
                    #elif succeeded.match(line):
                        #Make sure it's succeeded the right compile
                        #In case we run parallel emerge
                        #if packages_count >= group['packages']:
                            #current_package = False
                            #compiling = False
                            #group['stop'] = int(succeeded.match(line).group(1))
                            #group['state'] = 'completed'
                            #collect['completed'].append(group)
                            #packages_count = 1
                            #log.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                                          #.format(group['start'], group['stop'], group['packages']))
                        #Just leave the rest because we don't in which state we are...
                #elif start.match(line):
                    #group = { }
                    #Make sure it's start to compile
                    #nextline = next(mylog)
                    #if not_aborded.match(nextline):
                        #Ok we start already to compile the first package
                        #So get the timestamp when we start  
                        #group['start'] = int(start.match(line).group(1))
                        #Get how many package to update 
                        #group['packages'] = int(not_aborded.match(nextline).group(1))
                        
                        #compiling = True
                        #packages_count = 1
                        
                        #As we jump to the next line we are already 'compiling' the first package
                        #current_package = True
                    #else:
                        #This has been aborded
                        #compiling = False
                        #packages_count = 1
                        #current_package = False
                    
            #Do we got something ?
            #if collect['completed']:
               #keep_running = True
            #if incompleted:
                #if collect['completed'] and collect['incompleted']:
                    #keep_running = False
                #elif collect['completed'] or collect['incompleted']:
                    #We enable incompleted but we have a completed update 
                    #so it's better :)
                    #keep_running = False
                #else:
                    #That mean we have nothing ;)
                    #if self._keep_collecting(count, ['last world update', 
                                #'have never been update using \'world\' update schema...']):
                        #keep_running = True
                        #count = count + 1
                    #else:
                        #return False
            #else:
                #if collect['completed']:
                    #keep_running = False
                #else:
                    #if self._keep_collecting(count, ['last world update', 
                                 #'have never been update using \'world\' update schema...']):
                        #keep_running = True
                        #count = count + 1
                    #else:
                        #return False
                    
        #TO REMOVE - testing only
        #if collect['completed']:
            #print('Found completed update world')
            #for listing in collect['completed']:
                #start = time.ctime(int(listing['start']))
                #stop = time.ctime(int(listing['stop']))
                #npackages = listing['packages']
                #print(f'Found: {start}, {stop}, packages : {npackages}')
        #if collect['incompleted']:
            #print('Found incompleted update world')
            #for listing in collect['incompleted']:
                #start = time.ctime(int(listing['start']))
                #stop = time.ctime(int(listing['stop']))
                #npackages = listing['packages']
                #failed = listing['failed']
                #print(f'Found: {start}, {stop}, packages : {npackages}, failed : {failed}')
                
        #So now compare and get the highest timestamp from each list
        #tocompare = [ ]
        #for target in 'completed', 'incompleted':
            #if collect[target]:
                #This this the start timestamp
                #latest_timestamp = collect[target][0]['start']
                #latest_sublist = collect[target][0]
                #for sublist in collect[target]:
                    #if sublist['start'] > latest_timestamp:
                        #latest_timestamp = sublist['start']
                        #latest_sublist = sublist
                #Add latest to tocompare list
                #tocompare.append(latest_sublist)
        #Then compare latest from each list 
        #To find latest of latest
        #log.debug('Extracting latest world update informations.')
        #if tocompare:
            #latest_timestamp = tocompare[0]['start']
            #latest_sublist = tocompare[0]
            #for sublist in tocompare:
                #if sublist['start'] > latest_timestamp:
                    #latest_timestamp = sublist['start']
                    #Ok we got latest of all latest
                    #latest_sublist = sublist
        #else:
            #log.error('Failed to found latest world update informations.')
            #We got error
            #return False
        
        #if latest_sublist:
            #if latest_sublist['state'] == 'completed':
                #log.debug('Recording completed, start: {0}, stop: {1}, packages: {2}'
                        #.format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['packages']))
            #elif latest_sublist['state'] == 'incompleted':
                #log.debug('Recording incompleted, start: {0}, stop: {1}, packages: {2}, failed at: {3}'
                        #.format(latest_sublist['start'], latest_sublist['stop'], latest_sublist['packages'], latest_sublist['failed']))
            #return latest_sublist
        #else:
            #log.error('Failed to found latest world update informations.')
            #return False           
        
        
    #def getlog(self, lastlines, bsize=2048):
        #"""Get last n lines from emerge.log file
        #https://stackoverflow.com/a/12295054/11869956"""
        #get newlines type, open in universal mode to find it
        #try:
            #with pathlib.Path(pathdir['emergelog']).open('rU') as mylog:
                #if not mylog.readline():
                    #return  # empty, no point
                #sep = mylog.newlines  # After reading a line, python gives us this
            #assert isinstance(sep, str), 'multiple newline types found, aborting'

            #find a suitable seek position in binary mode
            #with pathlib.Path(pathdir['emergelog']).open('rb') as mylog:
                #mylog.seek(0, os.SEEK_END)
                #linecount = 0
                #pos = 0

                #while linecount <= lastlines + 1:
                    #read at least n lines + 1 more; we need to skip a partial line later on
                    #try:
                        #mylog.seek(-bsize, os.SEEK_CUR)           # go backwards
                        #linecount += mylog.read(bsize).count(sep.encode()) # count newlines
                        #mylog.seek(-bsize, os.SEEK_CUR)           # go back again
                    #except (IOError, OSError) as error:
                        #if error.errno == errno.EINVAL:
                            #Attempted to seek past the start, can't go further
                            #bsize = mylog.tell()
                            #mylog.seek(0, os.SEEK_SET)
                            #pos = 0
                            #linecount += mylog.read(bsize).count(sep.encode())
                            #break
                        #raise # Some other I/O exception, re-raise
                    #pos = mylog.tell()

            #Re-open in text mode
            #with pathlib.Path(pathdir['emergelog']).open('r') as mylog:
                #mylog.seek(pos, os.SEEK_SET)  # our file position from above

                #for line in mylog:
                    #We've located n lines *or more*, so skip if needed
                    #if linecount > lastlines:
                        #linecount -= 1
                        #continue
                    #The rest we yield
                    #yield line.rstrip()
        #except (OSError, IOError) as error:
            #log.critical('Error while getting informations from emerge.log file.')
            #if error.errno == errno.EPERM or error.errno == errno.EACCES:
                #log.critical(f'Got: \'{error.strerror}: {error.filename}\'.')
                #log.critical(f'Daemon is intended to be run as sudo/root.')
            #else:
                #log.critical(f'Got: \'{error}\'.')
            #log.critical('Exiting with error \'1\'.')
            #sys.exit(1)
    
    #def _keep_collecting(self, count, message):
        #"""Restart collecting if nothing has been found."""
        #TODO : Total line !
        #if  count < 5:
            #log.debug(f'After {count} run: couldn\'t found {message[0]} timestamp.')
            #self.lastlines = self.lastlines + 1000
            #log.debug('Restarting with an bigger increment (+1000 lines each pass)...')
        #elif count >= 5 and count < 10:
            #log.debug(f'After {count} run, {message[0]} timestamp still not found...')
            #log.debug('Restarting with an bigger increment (+3000 lines each pass)...')
            #self.lastlines = self.lastlines + 3000
        #elif count >= 10 and count < 15:
            #log.debug(f'After {count} run, {message[0]} timestamp not found !')
            #log.debug('Restarting with an bigger increment (+6000 lines each pass)...')
            #log.debug(f'{self.aborded} pass left before abording...')
            #self.aborded = self.aborded - 1
            #self.lastlines = self.lastlines + 6000
        #elif count > 15:
            #log.error(f'After 15 pass and more than 40 000 lines read, couldn\'t find {message[0]} timestamp.')
            #log.error(f'Look like the system {message[1]}')
            #return False
        #return True




#def world_update_inprogress():
    #"""Check if world update is in progress
    #@return: True or False
    #Adapt from https://stackoverflow.com/a/31997847/11869956"""
    
    #TODO: system as well 
    #psutil module is slower then this.
    
    #pids_only = re.compile(r'^\d+$')
    #world = re.compile(r'^.*emerge.*\sworld\s.*$')
    #pretend = re.compile(r'.*emerge.*\s-\w*p\w*\s.*|.*emerge.*\s--pretend\s.*')
    #inprogress = False

    #pids = [ ]
    #for dirname in os.listdir('/proc'):
        #if pids_only.match(dirname):
            #try:
                #with pathlib.Path('/proc/{0}/cmdline'.format(dirname)).open('rb') as myfd:
                    #content = myfd.read().decode().split('\x00')
            #IOError exception when pid as finish between getting the dir list and open it each
            #except IOError:
                #continue
            #except Exception as exc:
                #log.error(f'Got unexcept error: {exc}')
                #TODO: Exit or not ?
                #continue
            #if world.match(' '.join(content)):
                 #Don't match any -p or --pretend opts
                #if not pretend.match(' '.join(content)):
                    #inprogress = True

    #if inprogress:
        #TODO
        #log.debug('World update in progress')
        #return True
    #else:
        #TODO
        #log.debug('World update is not in progress')
        #return False

#TODO : rename to get_latest_version
#def find_number_maximum(*arguments):
    #"""Compare version numbers and return the highest."""
    #number_max = arguments[0]
    #for arg in arguments:
        #if StrictVersion(arg) > StrictVersion(number_max):
            #number_max = arg
    #return number_max

#def format_timestamp(seconds, granularity=3):
    #"""Convert seconds to varying degrees of granularity.
       #https://stackoverflow.com/a/24542445/11869956"""
    #TODO : round for exemple:  full display: 4 days, 2 hours, 42 minutes and 50 seconds 
    #if granularity is 2 this should be 4 days 3 hours NOT 2 hours (because 42 minutes)
    #if seconds < 60:
        #return 'less than a minute'
    
    #result = []

    #for name, count in intervals:
        #value = seconds // count
        #if value:
            #seconds -= value * count
            #if value == 1:
                #name = name.rstrip('s')
            #result.append("{} {}".format(value, name))
    
    #return ', '.join(result[:granularity])
