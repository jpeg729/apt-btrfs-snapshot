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
import cPickle as pickle
import textwrap

from fstab import (
    Fstab,
)
from dpkg_history import DpkgHistory
import snapshots
from snapshots import (
    Snapshot,
    SNAP_PREFIX,
    PARENT_LINK, 
    CHANGES_FILE, 
)


def debug(*args):
    print(*args)


class AptBtrfsSnapshotError(Exception):
    pass


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

    def __init__(self, fstab="/etc/fstab", test_mp=None):
        self.fstab = Fstab(fstab)
        self.commands = LowLevelCommands()
        self.parents = None
        self.children = None
        self.orphans = None
        # if we haven't been given a testing ground to play in, mount the real
        # root volume
        self.test = test_mp is not None
        self.mp = test_mp
        if self.mp is None:
            uuid = self.fstab.uuid_for_mountpoint("/")
            mountpoint = tempfile.mkdtemp(prefix="apt-btrfs-snapshot-mp-")
            if not self.commands.mount(uuid, mountpoint):
                return None
            self.mp = mountpoint
        snapshots.mp = self.mp

    def __del__(self):
        """ unmount root volume if necessary """
        # This will probably not get run if there are cyclic references.
        # check thoroughly because we get called even if __init__ fails
        if not self.test and self.mp is not None:
            res = self.commands.umount(self.mp)
            os.rmdir(self.mp)
            self.mp = None

    def _get_now_str(self):
        return datetime.datetime.now().replace(microsecond=0).isoformat(
            str('_'))

    def _get_status(self):
        mp = self.mp
        # find package changes
        parent_file = os.path.join(mp, "@", PARENT_LINK)
        if os.path.exists(parent_file):
            p = 6 + len(SNAP_PREFIX)
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

    def _load_changes(self, snapshot):
        changes_file = os.path.join(self.mp, snapshot, CHANGES_FILE)
        try:
            history = pickle.load(open(changes_file, "rb"))
            return history
        except IOError:
            return None
    
    def _store_changes(self, snapshot, changes):
        changes_file = os.path.join(self.mp, snapshot, CHANGES_FILE)
        pickle.dump(changes, open(changes_file, "wb"))
    
    def create(self):
        mp = self.mp
        
        # make snapshot
        snap_id = SNAP_PREFIX + self._get_now_str()
        res = self.commands.btrfs_subvolume_snapshot(
            os.path.join(self.mp, "@"),
            os.path.join(self.mp, snap_id))
        
        # find and store dpkg changes
        date, history = self._get_status()
        self._store_changes(snap_id, history)
        
        # set root's new parent
        self._link(snap_id, "@")
        
        return res

    def _parse_tree(self):
        mp = self.mp
        self.parents = {}
        self.children = {}
        self.orphans = []
        snapshots = self.get_btrfs_root_snapshots_list()
        snapshots.append("@")
        for snapshot in snapshots:
            parent_file = os.path.join(mp, snapshot, PARENT_LINK)
            try:
                link_to = os.readlink(parent_file)
            except OSError:
                self.orphans.append(snapshot)
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
        parent_file = os.path.join(self.mp, child, PARENT_LINK)
        # remove parent link from child
        if os.path.exists(parent_file):
            os.remove(parent_file)
        # link to parent
        if parent is not None:
            parent_path = os.path.join("..", "..", parent)
            os.symlink(parent_path, parent_file)

    def get_btrfs_root_snapshots_list(self, older_than=False):
        """ get the list of available snapshots
            If "older_then" is given (as a datetime) it will only include
            snapshots that are older then the given date)
        """
        l = []
        mp = self.mp
        for e in os.listdir(mp):
            if e.startswith(SNAP_PREFIX):
                pos = len(SNAP_PREFIX)
                d = e[pos:pos + 19]
                try:
                    date = datetime.datetime.strptime(d, "%Y-%m-%d_%H:%M:%S")
                except ValueError:
                    # something is wrong
                    raise Hell
                if older_than == False or date < older_than:
                    l.append(e)
        return l

    def list(self):
        print("Available snapshots:")
        print("  \n".join(self.get_btrfs_root_snapshots_list()))
        return True

    def list_older_than(self, older_than):
        print("Available snapshots older than '%s':" % timefmt)
        print("  \n".join(self.get_btrfs_root_snapshots_list(
            older_than=older_than)))
        return True

    def delete_older_than(self, older_than):
        res = True
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
                snapshot_name.startswith(SNAP_PREFIX)):
            default_root = os.path.join(mp, "@")
            staging = os.path.join(mp, "@apt-btrfs-staging")
            # TODO check whether staging already exists and prompt to remove it

            # find and store dpkg changes
            date, history = self._get_status()
            self._store_changes("@", history)
                
            # snapshot the requested default so as not to remove it
            res = self.commands.btrfs_subvolume_snapshot(new_root, staging)
            if not res:
                raise Exception("Could not create snapshot")

            # make backup name
            backup = os.path.join(mp, SNAP_PREFIX + self._get_now_str())
            # if backup name is already in use, wait a sec and try again
            if os.path.exists(backup):
                time.sleep(1)
                backup = os.path.join(mp, 
                    SNAP_PREFIX + self._get_now_str())

            # move everything into place
            os.rename(default_root, backup)
            os.rename(staging, default_root)
            
            # clean-up @/etc/apt-btrfs-changes
            changes_file = os.path.join(mp, "@", CHANGES_FILE)
            if os.path.exists(changes_file):
                os.remove(changes_file)
            
            # set root's new parent
            self._link(snapshot_name, "@")
            
            print("Default changed to %s, please reboot for changes to take "
                  "effect." % snapshot_name)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % SNAP_PREFIX)
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
                snapshot_name.startswith(SNAP_PREFIX)):
            
            # correct parent links and combine change info
            parent = self._get_parent(snapshot_name)
            children = self._get_children(snapshot_name)
            old_history = self._load_changes(snapshot_name)
            for child in children:
                self._link(parent, child)
                newer_history = self._load_changes(child)
                combined = old_history + newer_history
                self._store_changes(child, combined)
            
            res = self.commands.btrfs_delete_snapshot(to_delete)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % SNAP_PREFIX)
        return res
