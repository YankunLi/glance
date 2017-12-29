"""collect all disk information"""

import os
import sys

try:
    import psutil
except ImportError:
    psutil = None

FS_MOUNTS = '/proc/mounts'
FS_IDS = '/dev/disk/by-uuid'

class DiskCollector(object):
    def __init__(self):
        pass

    def collect(self):
        """collect partitions information"""
        fs_ids = self.get_fs_uuids()
        fs_mounts = self.get_file_systems()

        disks_informations = []
        for device in fs_ids.keys():
            if device in fs_mounts.keys():
                partition = Disk(device, fs_ids[device],
                        fs_mounts[device][mount_point])
                disks_informations.append(FilesystemInfo(partition))

        for fs in disks_informations:
            fs.init_fs()

        return disks_informations




    def get_file_systems(self):
        global FS_MOUNTS, FS_IDS
        fs_mounts = FS_MOUNTS
        fs_ids = FS_IDS
        result = {}
        if os.access(fs_ids, os.R_OK):
            try:
                with open(fs_mounts) as f:
                    for line in f:
                        mount = line.split()
                        device = mount[0]
                        mount_point = mount[1]
                        fs_type = mount[2]

                        if not device.startswith('/dev') or \
                           'storage' not in mount_point:
                            continue

                        result[device] = {
                                "mount_point": mount_point,
                                "fs_type": fs_type}
            except (IndexError, ValueError):
                continue

        else:
            if not psutil:
                #log
                return None
            partitions = psutil.disk_partitions(False)
            for partition in partitions:
                result[os.path.realpath(partition)] =  {
                        "mount_point": partition.mountpoint,
                        "fs_type": partition.fstype}

        return result



    def get_fs_uuids(self):
        global FS_IDS
        fs_ids = FS_IDS
        result = {}
        if os.access(fs_ids, os.R_OK):
            for fsid in os.listdir(fs_ids):
                result[os.path.realpath(
                       os.path.jion(fs_ids, fsid))] = fsid
        else:
            return None
        return result

    def get_all_disk(self):
        pass
