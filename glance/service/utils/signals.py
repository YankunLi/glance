"""process signals"""

import signal

def signal_to_exception(signum, frame):
    """convert signal to exception"""
    if signum == signal.SIGALRM:
        raise SIGALRMException()
    if signum == signal.SIGHUP:
        raise SIGHUPException()
    raise SIGNALException(signum)

class SIGNALException(Exception):
    pass

class SIGALRMException(SIGNALException):
    pass

class SIGHUPException(SIGNALException):
    pass
