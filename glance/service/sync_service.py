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

sys.path.insert(0, '/root/workplace/openstack/glance/')

from glance.service.utils.signals import signal_to_exception
from glance.service.utils.signals import SIGALRMException
from glance.service.utils.signals import SIGHUPException

try:
    from setproctitle import getproctitle, setproctitle
except ImportError:
    setproctitle = None

DISKS_DIR = '/dev/disk/by-uuid/'

def service_process(service, config, log):
    proc = multiprocessing.current_process()
    if setproctitle:
        setproctitle("%s-%s" % (getproctitle(), proc.name))
    log.debug("Starting process %s for sync service information" % proc.name)

    #
    signal.signal(signal.SIGALRM, signal_to_exception)
    signal.signal(signal.SIGHUP, signal_to_exception)

    #update service information for interval time , interval if from configfile
    interval = 4
    if interval < 0 or interval is None:
        log.debug("Interval is invalid, so the interval of updating service\
                information  default value 360")

    next_window = math.floor(time.time()/interval) * interval

    stagger_offset = random.uniform(0, interval-1)

    max_time = int(max(interval - stagger_offset, 1))
    log.debug("Max sync service information time %s" % max_time)

    import pdb
    pdb.set_trace()
    while True:
        try:
            time_to_sleep = (next_window + stagger_offset) - time.time()
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)
            elif time_to_sleep < 0:
                next_window = time.time()

            next_window += interval

            signal.alarm(max_time)
            #collect service information and update service in db
   #         service.update()
            fetch_disks_info()
            sys.stdout.flush()
            log.info("fetch disks information")
            signal.alarm(0)
        except SIGALRMException:
            log.error("Took too long to run! Killed!")

            stagger_offset = stagger_offset * 0.9
            max_time = int(max(interval - stagger_offset, 1))
            log.debug("Max time of updating service information is: %s" % max_time)
        except SIGHUPException:
            pass
        except Exception:
            log.error("Updating service failed!")
            break

def fetch_disks_info():
    """GET all filesystem uuid, then fetch it's information"""
    global DISKS_DIR
    disks_dir = DISKS_DIR
    #{uuid: uuid path}
    mounted_fs = {}
    disks_info = {}
    if os.path.isdir(disks_dir):
        for fsid in os.listdir(disks_dir):
            fs_path = os.path.normpath(os.path.abspath(
                                       os.path.join(disks_dir, fsid)))
            mounted_fs[fsid] = fs_path
    for (key, value) in mounted_fs.items():
        disks_info[key] = fetch_disk_info(value)

    print(mounted_fs)
    print(disks_info)
    return disks_info

def fetch_disk_info(dev_path):
    if os.path.exists(dev_path):
        try:
            return os.stat(dev_path)
        except Exception, e:
            pass #TODO can't fetch disk info
    return


if __name__ == '__main__':
    import logging
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler("./test.log", maxBytes=10*1024, backupCount=3)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    service = []
    config = None
    service_process(service, config, logger)
