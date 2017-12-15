"""process signals"""

import signal

def signal_to_exception(signum, frame):
    """convert signal to exception"""
    if signum == signal.SIGALRM:
        raise SIGALRMException()
    if signum == signal.SIGHUB:
        raise SIGHUBException()
    raise SIGNALException(signum)

class SIGNALException(Exception):
    pass

class SIGALRMException(SIGNALException):
    pass

class SIGHUBException(SIGNALException):
    pass
