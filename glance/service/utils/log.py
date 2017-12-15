"""setup logging"""
import sys
import os
import logging
import logging.config

def setup_logging(configfile):
    log = logging.getlogger('server')

    try:
        if sys.version_info >= (2, 6):
            logging.config.fileConfig(configfile,
                                      disable_existing_loggers=False)
        else:
            logging.config.fileConfig(configfile)
            for logger in logging.root.manager.loggerDict.values():
                logger.disabled = 0
    except Exception, e:
        sys.stderr.write("Error occurs when initialize logging:")
        sys.stderr.write(str(e))
        sys.stderr.write(os.linesep)
