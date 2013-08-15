# -*- coding: utf-8 -*-
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
        snapshots.setup(self.mp)

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
    
    def create(self):
        # make snapshot
        snap_id = SNAP_PREFIX + self._get_now_str()
        res = self.commands.btrfs_subvolume_snapshot(
            os.path.join(self.mp, "@"),
            os.path.join(self.mp, snap_id))
        
        # find and store dpkg changes
        date, history = self._get_status()
        Snapshot(snap_id).changes = history
        
        # set root's new parent
        Snapshot("@").parent = snap_id
        
        return res

    def list(self):
        # The function name will not clash with reserved keywords. It is only
        # accessible via instance.list()
        print("Available snapshots:")
        print("  \n".join(snapshots.get_list()))
        return True

    def list_older_than(self, older_than):
        print("Available snapshots older than '%s':" % timefmt)
        print("  \n".join(snapshots.get_list(
            older_than=older_than)))
        return True

    def delete_older_than(self, older_than):
        res = True
        for snap in snapshots.get_list(
                older_than=older_than):
            res &= self.delete(snap)
        return res

    def set_default(self, snapshot):
        """ set new default """
        snapshot = Snapshot(snapshot)
        new_root = os.path.join(self.mp, snapshot.name)
        if (
                os.path.isdir(new_root) and
                snapshot.name.startswith(SNAP_PREFIX)):
            default_root = os.path.join(self.mp, "@")
            staging = os.path.join(self.mp, "@apt-btrfs-staging")
            # TODO check whether staging already exists and prompt to remove it

            # find and store dpkg changes
            date, history = self._get_status()
            Snapshot("@").changes = history
                
            # snapshot the requested default so as not to remove it
            res = self.commands.btrfs_subvolume_snapshot(new_root, staging)
            if not res:
                raise Exception("Could not create snapshot")

            # make backup name
            backup = os.path.join(self.mp, 
                SNAP_PREFIX + self._get_now_str())
            # if backup name is already in use, wait a sec and try again
            if os.path.exists(backup):
                time.sleep(1)
                backup = os.path.join(self.mp, 
                    SNAP_PREFIX + self._get_now_str())

            # move everything into place
            os.rename(default_root, backup)
            os.rename(staging, default_root)
            
            # remove @/etc/apt-btrfs-changes & set root's new parent
            new_default = Snapshot("@")
            new_default.changes = None
            new_default.parent = snapshot.name
            
            print("Default changed to %s, please reboot for changes to take "
                  "effect." % snapshot.name)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % SNAP_PREFIX)
        return True

    def rollback(self, how_many=1):
        back_to = Snapshot("@")
        for i in range(how_many):
            back_to = back_to.parent
            if back_to is None:
                raise Exception("Can't rollback that far")
        self.set_default(back_to)

    def delete(self, snapshot):
        snapshot = Snapshot(snapshot)
        to_delete = os.path.join(self.mp, snapshot.name)
        res = True
        if (
                os.path.isdir(to_delete) and
                snapshot.name.startswith(SNAP_PREFIX)):
            
            # correct parent links and combine change info
            parent = snapshot.parent
            children = snapshot.children
            old_history = snapshot.changes
            for child in children:
                child.parent = parent
                newer_history = child.changes
                combined = old_history + newer_history
                child.changes = combined
            
            res = self.commands.btrfs_delete_snapshot(to_delete)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % SNAP_PREFIX)
        return res

    def _print_up_to_junction(self, snapshot, column):
        """ walks up the snapshot tree until the next one has more than one 
            child, pretty printing each one
        """
        padding = u"│  " * (column - 1)
        pointer = ""
        if column > 0:
            pointer += u"┌──"
        print(padding + pointer + str(snapshot))
        if column > 0:
            pointer = u"├──"
        while True:
            snapshot = snapshot.parent
            if snapshot == None or len(snapshot.children) > 1:
                return snapshot
            print(padding + pointer + str(snapshot))
        
    def tree(self):
        """ pretty print a view of the tree """
        to_print = [Snapshot("@")]
        for snap in snapshots.get_list():
            if snap.children == None:
                to_print.append(snap)
        to_print.sort(key = lambda x: x.date)
        print(to_print)
        column = 1
        junction_branches = {}
        junction_columns = {}
        while True:
            try:
                snapshot = to_print.pop()
            except IndexError:
                break
            junction = self._print_up_to_junction(snapshot, column)
            if junction == None:
                pass
            elif junction.name in junction_branches.keys():
                junction_branches[junction.name] -= 1
                #print('junction ' + str(junction) + ' already seen ' + str(junction_branches[junction.name]))
                junction_columns[junction.name].append(column)
                if junction_branches[junction.name] == 0:
                    #print("joining", junction_columns[junction.name])
                    to_print.append(junction)
                    # print branch join up line
                    cols = junction_columns[junction.name]
                    joinup = u"│  " * (cols[0] - 1) + u"├──"
                    for i in range(cols[0] + 1, cols[-1]):
                        if i in cols:
                            joinup += u"┴──"
                        else:
                            joinup += u"───"
                    joinup += u"┘"
                    print(joinup)
                    column = junction_columns[junction.name][0] - 1
            else:
                #print('new junction found ' + str(junction) + str(len(junction.children) - 1))
                junction_branches[junction.name] = len(junction.children) - 1
                junction_columns[junction.name] = [column]
            
            column += 1
            
if __name__ == '__main__':
    import shutil
    selfdir = os.path.dirname(os.path.abspath(__file__))
    testdir = os.path.join(selfdir, "test")
    # make a copy of a model btrfs subvol tree
    model_root = os.path.join(testdir, "data", "model_root")
    sandbox_root = os.path.join(testdir, "data", "root3")
    if os.path.exists(sandbox_root):
        shutil.rmtree(sandbox_root)
    shutil.copytree(model_root, sandbox_root, symlinks=True)
    # setup snapshot class
    apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(testdir, "data", "fstab"),
            test_mp=sandbox_root)
    apt_btrfs.tree()
