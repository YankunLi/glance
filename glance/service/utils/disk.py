"""disk information"""

import os
import sys
import stat

class FSPointException(Exception):
    pass

class DevException(Exception):
    pass

class Disk(object):
    def __init__(self, dev, fsid, mount_point):
        dev_stat = os.stat(dev)
        if stat.S_ISBLK(dev_stat.st_mode):
            self.name = dev
        else:
            raise DevException("Is not a block device")
        self.fsid = fsid
        self.mount_point = mount_point

class FilesystemInfo(object):
    def __init__(self, disk):
        self._inited_fs = False
        self._name = disk.name
        self._uuid = disk.fsid
        self._mount_point = disk.mount_point

        self._total_size = None
        self._avail_size = None
        self._used_size = None
        self._used_percentage = None

    def init_fs(self):
        try:
            self._fetch_fs_info()
            self._inited_fs = True
        except FSPointException:
            self._inited_fs = False

    def get_fs_type(self):
        pass

    @property
    def used_size(self):
        # if self._used_size and self._total_size and self._avail_size:
        self._used_size = self.total_size - self.avail_size
        return self._used_size

    @property
    def avail_percentage(self):
        if self._avail_size and self._total_size:
            return (1 - (self._avail_size / self._total_size)) * 100
        return

    @property
    def avail_size(self):
        if self._avail_size:
            return self._avail_size
        if self._inited_fs:
            self._avail_size = self.fs_bavail * self.fs_bsize
            return self._avail_size
        return

    @property
    def total_size(self):
        if self._total_size:
            return self._total_size
        if self._inited_fs:
            self._total_size = self.fs_blocks * self.fs_bsize
            return self._total_size
        else:
            return

    @total_size.setter
    def total_size(self, value):
        self._total_size = value

    def _fetch_fs_info(self):
        """fetch fs information"""
        if self._mount_point:
            if os.path.exists(self._mount_point):
                try:
                    fs_info = os.statvfs(self._mount_point)
                except Exception:
                    raise FSPointException("syscall statvfs error")
                self.fs_bsize   = fs_info.f_bsize
                self.fs_frsize  = fs_info.f_frsize
                self.fs_blocks  = fs_info.f_blocks
                self.fs_bfree   = fs_info.f_bfree
                self.fs_bavail  = fs_info.f_bavail
                self.fs_files   = fs_info.f_files
                self.fs_ffree   = fs_info.f_ffree
                self.fs_favail  = fs_info.f_favail
                self.fs_flag    = fs_info.f_flag
                self.fs_namemax = fs_info.f_namemax
                return

        raise FSPointException("mount point is not exist")


if __name__ == "__main__":
    dev = Disk('/dev/sdb1', '159bf3ec-ca95-4695-9319-a4fefbb35d74', '/var/lib/ceph/osd/ceph-1')
    fs = FilesystemInfo(dev)
    fs.init_fs()
    print("dev : %(device)s \nfilesystem id: %(fsid)s \nmount point: %(mount_point)s \n \
            total size: %(total_size)s \nused size: %(used_size)s \navail size: %(avail_size)s\npercentage: %(avail_per)s"
           % {"device":fs._name,
               "fsid":fs._uuid,
               "mount_point":fs._mount_point,
               "total_size":fs.total_size,
               "used_size":fs.used_size,
               "avail_size":fs.avail_size,
               "avail_per":fs.avail_percentage})

