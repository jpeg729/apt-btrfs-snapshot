# Copyright (C) 2011 Canonical
#
# Author:
#  Michael Vogt
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from __future__ import print_function, unicode_literals

import datetime
import os
import subprocess
import sys
import time
import tempfile
from dpkg_history import DpkgHistory
import cPickle as pickle
import textwrap


def debug(*args):
    print(*args)


class AptBtrfsSnapshotError(Exception):
    pass


class AptBtrfsNotSupportedError(AptBtrfsSnapshotError):
    pass


class FstabEntry(object):
    """ a single fstab entry line """
    @classmethod
    def from_line(cls, line):
        # split up
        args = line.partition("#")[0].split()
        # use only the first 7 args and ignore anything after them, mount
        # seems to do the same, see bug #873411 comment #7
        return FstabEntry(*args[0:6])

    def __init__(self, fs_spec, mountpoint, fstype, options, dump=0, passno=0):
        # uuid or device
        self.fs_spec = fs_spec
        self.mountpoint = mountpoint
        self.fstype = fstype
        self.options = options
        self.dump = dump
        self.passno = passno

    def __repr__(self):
        return "<FstabEntry '%s' '%s' '%s' '%s' '%s' '%s'>" % (
            self.fs_spec, self.mountpoint, self.fstype,
            self.options, self.dump, self.passno)


class Fstab(list):
    """ a list of FstabEntry items """
    def __init__(self, fstab="/etc/fstab"):
        super(Fstab, self).__init__()

        with open(fstab) as fstab_file:
            for line in (l.strip() for l in fstab_file):
                if line == "" or line.startswith("#"):
                    continue
                try:
                    entry = FstabEntry.from_line(line)
                except ValueError:
                    continue
                self.append(entry)

    def get_supported_btrfs_root_fstab_entry(self):
        """ return the supported btrfs root FstabEntry or None """
        for entry in self:
            if (
                    entry.mountpoint == "/" and
                    entry.fstype == "btrfs" and
                    "subvol=@" in entry.options):
                return entry
        return None

    def uuid_for_mountpoint(self, mountpoint, fstab="/etc/fstab"):
        """ return the device or UUID for the given mountpoint """
        for entry in self:
            if entry.mountpoint == mountpoint:
                return entry.fs_spec
        return None


def supported(fstab="/etc/fstab"):
    """ verify that the system supports apt btrfs snapshots
        by checking if the right fs layout is used etc
    """
    # check for the helper binary
    if not os.path.exists("/sbin/btrfs"):
        return False
    # check the fstab
    fstab = Fstab(fstab)
    entry = fstab.get_supported_btrfs_root_fstab_entry()
    return entry is not None


class LowLevelCommands(object):
    """ lowlevel commands invoked to perform various tasks like
        interact with mount and btrfs tools
    """
    def mount(self, fs_spec, mountpoint):
        ret = subprocess.call(["mount", fs_spec, mountpoint])
        return ret == 0

    def umount(self, mountpoint):
        ret = subprocess.call(["umount", mountpoint])
        return ret == 0

    def btrfs_subvolume_snapshot(self, source, dest):
        ret = subprocess.call(["btrfs", "subvolume", "snapshot",
                               source, dest])
        return ret == 0

    def btrfs_delete_snapshot(self, snapshot):
        ret = subprocess.call(["btrfs", "subvolume", "delete", snapshot])
        return ret == 0


class AptBtrfsSnapshot(object):
    """ the high level object that interacts with the snapshot system """

    # normal snapshot
    SNAP_PREFIX = "@apt-snapshot-"
    # backname when changing
    BACKUP_PREFIX = SNAP_PREFIX + "old-root-"

    def __init__(self, fstab="/etc/fstab", test_mp=None):
        self.fstab = Fstab(fstab)
        self.commands = LowLevelCommands()
        self.parents = None
        self.children = None
        # if we haven't been given a testing ground to play in, mount the real
        # root volume
        self.test = test_mp is not None
        self.mp = test_mp
        if self.mp is None:
            self.mp = self.mount_btrfs_root_volume()

    def __del__(self):
        """ unmount root volume if necessary """
        # This will probably not get run if there are cyclic references.
        # check thoroughly because we get called even if __init__ fails
        if not self.test and self.mp is not None:
            self.umount_btrfs_root_volume()

    def mount_btrfs_root_volume(self):
        uuid = self.fstab.uuid_for_mountpoint("/")
        mountpoint = tempfile.mkdtemp(prefix="apt-btrfs-snapshot-mp-")
        if not self.commands.mount(uuid, mountpoint):
            return None
        self.mp = mountpoint
        return self.mp

    def umount_btrfs_root_volume(self):
        res = self.commands.umount(self.mp)
        os.rmdir(self.mp)
        self.mp = None
        return res

    def _get_now_str(self):
        return datetime.datetime.now().replace(microsecond=0).isoformat(
            str('_'))

    def _get_status(self):
        mp = self.mp
        # find package changes
        parent_file = os.path.join(mp, "@", "etc", "apt-btrfs-parent")
        if os.path.exists(parent_file):
            p = 6 + len(self.SNAP_PREFIX)
            date_parent = os.readlink(parent_file)[p:p + 19].replace("_", " ")
        else:
            date_parent = None
        if self.test:
            history = DpkgHistory(since = date_parent, 
                var_location = "data/var")
        else:
            history = DpkgHistory(since = date_parent)
        return date_parent, history

    def status(self):
        date_parent, history = self._get_status()
        if date_parent is None:
            print("Cannot find a previous snapshot. The dpkg logs mention:")
        else:
            print("Since the previous snapshot taken on %s, there have been:" % 
                date_parent)
        for op in ("install", "auto-install", "upgrade", "remove", "purge"):
            if len(history[op]) > 0:
                print("%d %ss:" % (len(history[op]), op))
                packages = []
                for p, v in history[op]:
                    packages.append(p)
                packages = ", ".join(packages)
                if sys.stdout.isatty():
                    # if we are in a terminal, wrap text to match its width
                    rows, columns = os.popen('stty size', 'r').read().split()
                    packages = textwrap.fill(packages, width=int(columns), 
                        initial_indent='  ', subsequent_indent='  ')
                print(packages)

    def snapshot(self):
        mp = self.mp
        
        # make snapshot
        snap_id = self.SNAP_PREFIX + self._get_now_str()
        res = self.commands.btrfs_subvolume_snapshot(
            os.path.join(mp, "@"),
            os.path.join(mp, snap_id))
        
        # find and store dpkg changes
        date, history = self._get_status()
        changes_file = os.path.join(mp, snap_id, "etc", "apt-btrfs-changes")
        pickle.dump(history, open(changes_file, "wb"))
        
        # set root's new parent
        self._link(snap_id, "@")
        return res

    def _parse_tree(self):
        mp = self.mp
        self.parents = {}
        self.children = {}
        snapshots = self.get_btrfs_root_snapshots_list()
        snapshots.append("@")
        for snapshot in snapshots:
            parent_file = os.path.join(mp, snapshot, "etc", "apt-btrfs-parent")
            try:
                link_to = os.readlink(parent_file)
            except OSError:
                continue
            path, parent = os.path.split(link_to)
            self.parents[snapshot] = parent
            if parent in self.children.keys():
                self.children[parent].append(snapshot)
            else:
                self.children[parent] = [snapshot]

    def _get_parent(self, snapshot):
        if self.parents is None:
            self._parse_tree()
        if snapshot in self.parents.keys():
            return self.parents[snapshot]
        return None

    def _get_children(self, snapshot):
        if self.children is None:
            self._parse_tree()
        if snapshot in self.children.keys():
            return self.children[snapshot]
        return None

    def _link(self, parent, child):
        """ sets symlink from child to parent 
            or deletes it if parent == None 
        """
        parent_file = os.path.join(self.mp, child, "etc", "apt-btrfs-parent")
        # remove parent link from child
        if os.path.exists(parent_file):
            os.remove(parent_file)
        # link to parent
        if parent is not None:
            parent_path = os.path.join("..", "..", parent)
            os.symlink(parent_path, parent_file)

    def get_btrfs_root_snapshots_list(self, older_than=False):
        """ get the list of available snapshot
            If "older_then" is given (in datetime format) it will only include
            snapshots that are older then the given date)
        """
        l = []
        mp = self.mp
        for e in os.listdir(mp):
            if e.startswith(self.SNAP_PREFIX):
                d = e[len(self.SNAP_PREFIX):]
                try:
                    date = datetime.datetime.strptime(d, "%Y-%m-%d_%H:%M:%S")
                except ValueError:
                    # have found a named snapshot
                    date = older_than
                if older_than == False or date < older_than:
                    l.append(e)
        return l

    def list(self):
        print("Available snapshots:")
        print("  \n".join(self.get_btrfs_root_snapshots_list()))
        return True

    def _parse_older_than_to_datetime(self, timefmt):
        now = datetime.datetime.now()
        if not timefmt.endswith("d"):
            raise Exception("Please specify time in days (e.g. 10d)")
        days = int(timefmt[:-1])
        return now - datetime.timedelta(days)

    def list_older_than(self, timefmt):
        older_than = self._parse_older_than_to_datetime(timefmt)
        print("Available snapshots older than '%s':" % timefmt)
        print("  \n".join(self.get_btrfs_root_snapshots_list(
            older_than=older_than)))
        return True

    def delete_older_than(self, timefmt):
        res = True
        older_than = self._parse_older_than_to_datetime(timefmt)
        for snap in self.get_btrfs_root_snapshots_list(
                older_than=older_than):
            res &= self.delete(snap)
        return res

    def set_default(self, snapshot_name):
        """ set new default """
        mp = self.mp
        new_root = os.path.join(mp, snapshot_name)
        if (
                os.path.isdir(new_root) and
                snapshot_name.startswith(self.SNAP_PREFIX)):
            default_root = os.path.join(mp, "@")
            staging = os.path.join(mp, "@apt-btrfs-staging")
            # TODO check whether staging already exists and prompt to remove it
            # TODO find apt changes and pickle them
            # snapshot the requested default so as not to remove it
            res = self.commands.btrfs_subvolume_snapshot(new_root, staging)
            if not res:
                raise Exception("Could not create snapshot")
            # rename @ to make backup
            backup = os.path.join(mp, self.SNAP_PREFIX + self._get_now_str())
            # Avoid overwriting last backup if you try again within the same 
            # second
            if os.path.exists(backup):
                time.sleep(1)
                backup = os.path.join(mp, 
                    self.SNAP_PREFIX + self._get_now_str())
            os.rename(default_root, backup)
            os.rename(staging, default_root)
            # set parent and clean-up @/etc/apt-btrfs housekeeping files
            changes_file = os.path.join(mp, "@", "etc", "apt-btrfs-changes")
            if os.path.exists(changes_file):
                os.remove(changes_file)
            # set root's new parent
            self._link(snapshot_name, "@")
            
            print("Default changed to %s, please reboot for changes to take "
                  "effect." % snapshot_name)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % self.SNAP_PREFIX)
        return True

    def rollback(self, how_many=1):
        debug("rolling back", how_many)
        back_to = "@"
        for i in range(how_many):
            back_to = self._get_parent(back_to)
        debug("back to", back_to)
        try:self.set_default(back_to)
        except: time.sleep(20)

    def delete(self, snapshot_name):
        mp = self.mp
        to_delete = os.path.join(mp, snapshot_name)
        res = True
        if (
                os.path.isdir(to_delete) and
                snapshot_name.startswith(self.SNAP_PREFIX)):
            # correct parent links
            parent = self._get_parent(snapshot_name)
            children = self._get_children(snapshot_name)
            for child in children:
                self._link(parent, child)
            res = self.commands.btrfs_delete_snapshot(to_delete)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % self.SNAP_PREFIX)
        return res
