# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3
# -*- coding: utf-8 -*-
# -*- python -*- 

import logging
import logging.handlers

# TODO : maybe give the choice to custom logrotate ?

class MainLoggingHandler:
    """Main logging handler"""
    def __init__(self, name, debuglog, fdlog):
        self.name = name
        self.debuglog = debuglog
        self.fdlog = fdlog
        self.logging = logging
        logging.addLevelName(logging.CRITICAL, '[Crit ]')
        logging.addLevelName(logging.ERROR,    '[Error]')
        logging.addLevelName(logging.WARNING,  '[Warn ]')
        logging.addLevelName(logging.INFO,     '[Info ]')
        logging.addLevelName(logging.DEBUG,    '[Debug]')
        
        
    def init_run(self):
        """Logging handler for init run"""
        
        self.logger = logging.getLogger(self.name)
        
        # TODO: debug.log rotate is a REAL mess, don't know why
        # this could be because we have one logger by module ?
        # Debug only go to file
        # Rotate the log 
        # 2.86MB, rotate 3x times
        debug_handler = logging.handlers.RotatingFileHandler(self.debuglog, maxBytes=3000000, backupCount=3)
        datefmt = '%Y-%m-%d %H:%M:%S'
        debug_formatter   = logging.Formatter('%(asctime)s  %(name)s  %(message)s', datefmt)
        debug_handler.setFormatter(debug_formatter)
        debug_handler.addFilter(LogLevelFilter(10))
        debug_handler.setLevel(10)
        if not self.logger.handlers:
            self.logger.addHandler(debug_handler)
        
        # Other level goes to Syslog
        syslog_handler   = logging.handlers.SysLogHandler(address='/dev/log',facility='daemon')
        syslog_formatter = logging.Formatter('syuppod %(levelname)s  %(message)s')
        syslog_handler.setFormatter(syslog_formatter)
        # Filter stderr output
        syslog_handler.addFilter(LogErrorFilter(stderr=False))
        syslog_handler.setLevel(20)
        self.logger.addHandler(syslog_handler)
        
        # Catch file descriptor stderr
        # Rotate the log 
        # 2.86MB, rotate 3x times
        fd_handler = logging.handlers.RotatingFileHandler(self.fdlog, maxBytes=3000000, backupCount=3)
        fd_formatter   = logging.Formatter('%(asctime)s  %(message)s', datefmt)
        fd_handler.setFormatter(fd_formatter)
        fd_handler.addFilter(LogErrorFilter(stderr=True))
        # Level is error : See class LogErrorFilter
        fd_handler.setLevel(40)
        self.logger.addHandler(fd_handler)
       
        return self.logger
    
    
    def tty_run(self):
        """Logging handler for interactive terminal"""
        # Output all to console
        
        self.logger = logging.getLogger(self.name)
        
        console_handler = self.logging.StreamHandler()
        console_handler.setFormatter(LogLevelFormatter())
        # Otherwise will print twice ...
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)
               
        return self.logger



class ProcessLoggingHandler:
    """Specific logging which handle process logging"""
    def __init__(self, name):
        self.name = name
        self.logging = logging
        self.logger = logging.getLogger(name)
        
    def dolog(self, log):
        """Write Specific log"""
        # Same here : 2.86MB, rotate 3x times 
        file_handler     = logging.handlers.RotatingFileHandler(log, maxBytes=3000000, backupCount=3)
        datefmt = '%Y-%m-%d %H:%M:%S'
        file_formatter   = logging.Formatter('%(asctime)s  %(message)s', datefmt)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(self.logging.INFO)
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
        
        return self.logger



class LogLevelFilter(logging.Filter):
    """https://stackoverflow.com/a/7447596/190597 (robert)."""
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        # Just revert >= to <= then get only current level or lower.
        return record.levelno <= self.level



class LogErrorFilter(logging.Filter):
    """Filter logging.error and separate msg from stderr"""
    def __init__(self, stderr):
        self.stderr = stderr
        
    def filter(self, record):
        if self.stderr:
            try:
                if record.__dict__['STDERR']:
                    return record
                else:
                    return False
            except KeyError:
                return False
        else:
            try:
                if record.__dict__['STDERR']:
                    return False
                else:
                    return record
            except KeyError:
                return record
 
 
   
class LogLevelFormatter(logging.Formatter):
    """Formatter which separate debug and other log level for tty_run()
    https://stackoverflow.com/a/54739720/11869956"""
    formats = {
            logging.DEBUG   :   '%(levelname)s  %(name)s  %(message)s',
            'default'       :   '%(levelname)s  %(message)s'
            }
    
    def format(self, record):
        log_fmt = self.formats.get(record.levelno, self.formats['default'])
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)



class RedirectFdToLogger:
    """Retrieve from https://stackoverflow.com/a/51612402/11869956
    And modified to filter stderr to a separate file"""
    def __init__(self, logger):
        self.logger = logger
        self.msg = ''

    def write(self, message):
        self.msg = self.msg + message
        while '\n' in self.msg:
            pos = self.msg.find('\n')
            self.logger.error(self.msg[:pos], extra={ 'STDERR' : True })
            self.msg = self.msg[pos+1:]

    def flush(self):
        if self.msg != '':
            self.logger.error(self.msg, extra={ 'STDERR' : True })
            self.msg = ''
