"""setup logging"""

import sys
import os
import logging
import logging.config

def setup_logging(configfile, stdout=None):
    log = logging.getLogger('server')

    try:
        if sys.version_info >= (2, 6):
            logging.config.fileConfig(configfile,
                                      disable_existing_loggers=False)
        else:
            logging.config.fileConfig(configfile)
            for logger in logging.root.manager.loggerDict.values():
                logger.disabled = 0

        if stdout:
            rootLogLevel = logging.getLogger().getEffectiveLevel()
            log.setLevel(rootLogLevel)
            streamHandler = logging.StreamHandler(sys.stdout)
            streamHandler.setFormatter(DebugFormatter())
            streamHandler.setLevel(rootLogLevel)
            log.addHandler(streamHandler)
    except Exception, e:
        sys.stderr.write("Error occurs when initialize logging:")
        sys.stderr.write(str(e))
        sys.stderr.write(os.linesep)

    return log
