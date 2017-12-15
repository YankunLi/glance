#
#
"""update service information"""

import os
import sys
import time
import math
import random
import signal
import multiprocessing

from glance.service.utils.signals import signal_to_exception
from glance.service.utils.signals import SIGALRMException
from glance.service.utils.signals import SIGHUBException

try:
    from setproctitle import getproctitle, setproctitle
except ImportError:
    setproctitle = None

def service_process(service, config, log):
    proc = multiprocessing.current_process()
    if setprocetitle:
        setprocetitle("%s-%s" % (getproctitle(), proc.name))
    log.debug("Starting process %s for sync service information" % proc.name)

    #
    signal.signal(signal.SIGALRM, signal_to_exception)
    signal.signal(signal.SIGHUB, signal_to_exception)

    #update service information for interval time , interval if from configfile
    interval = 360
    if interval < 0 or interval is None:
        log.debug("Interval is invalid, so the interval of updating service\
                information  default value 360")

    next_window = math.floor(time.time()/interval) * interval

    stagger_offset = random.uniform(0, interval-1)

    max_time = int(max(interval - stagger_offset, 1))
    log.debug("Max sync service information time %s" % max_time)

    while True:
        try:
            time_to_sleep = (next_window + stagger_offset) - time.time()
            if time_to_sleep > 0:
                sleep(time_to_sleep)
            elif time_to_sleep < 0:
                next_window = time.time()

            next_window += interval

            signal.alarm(max_time)
            #collect service information and update service in db
   #         service.update()
            signal.alarm(0)
        except SIGALRMException:
            log.error("Took too long to run! Killed!")

            stagger_offset = stagger_offset * 0.9
            max_time = int(max(interval - stagger_offset, 1))
            log.debug("Max time of updating service information is: %s" % max_time)
        except SIGHUBException:
            pass
        except Exception:
            log.error("Updating service failed!")
            break
