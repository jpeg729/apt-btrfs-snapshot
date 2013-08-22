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
from collections import defaultdict

from fstab import Fstab
from dpkg_history import DpkgHistory
import snapshots
from snapshots import (
    Snapshot,
    SNAP_PREFIX,
    PARENT_LINK, 
    CHANGES_FILE, 
)


NO_HISTORY = {'purge': [], 'upgrade': [], 'auto-install': [], 'remove': [],
    'install': []}


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

    def __init__(self, fstab="/etc/fstab", sandbox=None):
        self.fstab = Fstab(fstab)
        self.commands = LowLevelCommands()
        # if we haven't been given a testing ground to play in, mount the real
        # root volume
        self.test = sandbox is not None
        self.mp = sandbox
        if self.mp is None:
            uuid = self.fstab.uuid_for_mountpoint("/")
            mountpoint = tempfile.mkdtemp(prefix="apt-btrfs-snapshot-mp-")
            if not self.commands.mount(uuid, mountpoint):
                os.rmdir(mountpoint)
                raise Exception("Unable to mount root volume")
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

    def _parse_older_than_to_datetime(self, timefmt):
        if isinstance(timefmt, datetime.datetime):
            return timefmt
        now = datetime.datetime.now()
        if not timefmt.endswith("d"):
            raise Exception("Please specify time in days (e.g. 10d)")
        days = int(timefmt[:-1])
        return now - datetime.timedelta(days)
        
    def _get_last_snapshot_time(self):
        last_snapshot = datetime.datetime.fromtimestamp(0.0)
        if self.test:
            last_snapshot_file = '/tmp/apt_last_snapshot'
        else:
            last_snapshot_file = '/run/apt_last_snapshot'

        if os.path.exists(last_snapshot_file):
            try:
                t = open(last_snapshot_file)
                last_snapshot = \
                datetime.datetime.fromtimestamp(float(t.readline()))
            except:
                # If we fail to read the timestamp for some reason, just return
                # the default value silently
                pass
            finally:
                t.close()
        return last_snapshot

    def _save_last_snapshot_time(self):
        if self.test:
            last_snapshot_file = '/tmp/apt_last_snapshot'
        else:
            last_snapshot_file = '/run/apt_last_snapshot'
        f = open(last_snapshot_file, 'w')
        f.write(str(time.time()))
        f.close()

    def _get_status(self):
        
        parent = Snapshot("@").parent
        if parent is not None:
            date_parent = parent.date
        else:
            date_parent = None
        if self.test:
            testdir = os.path.dirname(os.path.abspath(__file__))
            if not testdir.endswith("test"):
                testdir = os.path.join(testdir, "test")
            var_location = os.path.join(testdir, "data/var")
            history = DpkgHistory(since = date_parent, 
                var_location = var_location)
        else:
            history = DpkgHistory(since = date_parent)
        return parent, history

    def _prettify_changes(self, history, i_indent="- ", s_indent="    "):
        if history == None or history == NO_HISTORY:
            return [i_indent + "No packages operations recorded"]
        output = []
        for op in ("install", "auto-install", "upgrade", "remove", "purge"):
            if len(history[op]) > 0:
                output.append("%s%ss (%d):" % (i_indent, op, len(history[op])))
                packages = []
                for p, v in history[op]:
                    packages.append(p)
                packages = ", ".join(packages)
                if sys.stdout.isatty():
                    # if we are in a terminal, wrap text to match its width
                    rows, columns = os.popen('stty size', 'r').read().split()
                    packages = textwrap.wrap(packages, width=int(columns), 
                        initial_indent=s_indent, subsequent_indent=s_indent,
                        break_on_hyphens=False)
                output.extend(packages)
        return output
    
    def status(self):
        """ show current root's parent and recent changes """
        return self.show("@")
    
    def show(self, snapshot, compact=False):
        """ show details pertaining to given snapshot """
        snapshot = Snapshot(snapshot)
        if snapshot.name == "@":
            parent, changes = self._get_status()
        else:
            parent, changes = snapshot.parent, snapshot.changes
        
        fca = snapshots.first_common_ancestor("@", snapshot)
        mainline = (fca == snapshot) and 'Is' or "Isn't"
        mainline = "%s an ancestor of @" % mainline
        
        pretty_history = self._prettify_changes(changes)

        if parent == None:
            parent = "unknown"
        else:
            parent = parent.name
        
        if not compact:
            title = "Snapshot %s" % snapshot.name
            print(title)
            if snapshot.name != "@":
                print(mainline)
            print("Parent: %s" % parent)
            if parent == "unknown" and snapshot.name == "@":
                print("dpkg history shown for the last 30 days")
            print("dpkg history:")
        else:
            print("dpkg history for %s" % snapshot.name)
        print("\n".join(pretty_history))
        
        return True
    
    def create(self, tag=""):
        """ create a new apt-snapshot of @, tagging it if a tag is given """
        if 'APT_NO_SNAPSHOTS' in os.environ and tag == "":
            print("Shell variable APT_NO_SNAPSHOTS found, skipping creation")
            return True
        elif 'APT_NO_SNAPSHOTS' in os.environ and tag != "":
            print("Shell variable APT_NO_SNAPSHOTS found, but tag supplied, "
                "creating snapshot")
        last = self._get_last_snapshot_time()

        # If there is a recent snapshot and no tag supplied, skip creation
        if tag == "" \
        and last > datetime.datetime.now() - datetime.timedelta(seconds=60):
            print("A recent snapshot already exists: %s" % last)
            return True
        
        # make snapshot
        snap_id = SNAP_PREFIX + self._get_now_str() + tag
        res = self.commands.btrfs_subvolume_snapshot(
            os.path.join(self.mp, "@"),
            os.path.join(self.mp, snap_id))
        
        # set root's new parent
        Snapshot("@").parent = snap_id
        
        # find and store dpkg changes
        parent, history = self._get_status()
        Snapshot(snap_id).changes = history
        
        self._save_last_snapshot_time()
        return res
    
    def tag(self, snapshot, tag):
        """ Adds/replaces the tag for the given snapshot """
        children = Snapshot(snapshot).children

        pos = len(SNAP_PREFIX)
        new_name = snapshot[:pos + 19] + tag
        old_snap = os.path.join(self.mp, snapshot)
        new_snap = os.path.join(self.mp, new_name)
        os.rename(old_snap, new_snap)
        
        tagged = Snapshot(new_name)
        for child in children:
            child.parent = tagged
        return True

    def list(self):
        # The function name will not clash with reserved keywords. It is only
        # accessible via self.list()
        print("Available snapshots:")
        print("  \n".join(snapshots.get_list()))
        return True

    def list_older_than(self, timefmt):
        older_than = self._parse_older_than_to_datetime(timefmt)
        print("Available snapshots older than '%s':" % timefmt)
        print("  \n".join(snapshots.get_list(older_than=older_than)))
        return True

    def _prompt_for_tag(self):
        print("You haven't specified a tag for the snapshot that will be created from the current state.")
        tag = raw_input("Please enter a tag: ")
        if tag:
            tag = "-" + tag
        return tag
    
    def set_default(self, snapshot, tag=""):
        """ backup @ and replace @ with a copy of given snapshot """
        if not tag:
            tag = self._prompt_for_tag()

        snapshot = Snapshot(snapshot)
        new_root = os.path.join(self.mp, snapshot.name)
        if (
                os.path.isdir(new_root) and
                snapshot.name.startswith(SNAP_PREFIX)):
            default_root = os.path.join(self.mp, "@")
            staging = os.path.join(self.mp, "@apt-btrfs-staging")
            if os.path.lexists(staging):
                raise Exception("Reserved directory @apt-btrfs-staging "
                    "exists\nPlease remove from btrfs volume root before "
                    "trying again")
            
            # find and store dpkg changes
            date, history = self._get_status()
            Snapshot("@").changes = history
                
            # snapshot the requested default so as not to remove it
            res = self.commands.btrfs_subvolume_snapshot(new_root, staging)
            if not res:
                raise Exception("Could not create snapshot")

            # make backup name
            backup = os.path.join(self.mp, 
                SNAP_PREFIX + self._get_now_str()) + tag
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

    def rollback(self, number=1, tag=""):
        back_to = Snapshot("@")
        for i in range(number):
            back_to = back_to.parent
            if back_to == None:
                raise Exception("Can't rollback that far")
                return False
        return self.set_default(back_to, tag)

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
            
            # clean-ups in the global vars of 
            snapshots.list_of.remove(snapshot)
            if parent != None and parent.name in snapshots.children:
                snapshots.children[parent.name].remove(snapshot)
            
            for child in children:
                child.parent = parent
                
                # and do the same again in the global vars of snapshots
                # messy but necessary for delete_older_than to work
                snapshots.parents[child.name] = parent
                if parent != None:
                    snapshots.children[parent.name].append(child) # necessary
                
                newer_history = child.changes
                if old_history == None:
                    combined = newer_history
                elif newer_history == None:
                    combined = None
                else:
                    combined = old_history + newer_history
                child.changes = combined
            
            res = self.commands.btrfs_delete_snapshot(to_delete)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that its name starts with "
                  "\"%s\"" % SNAP_PREFIX)
        return res
    
    def delete_older_than(self, timefmt):
        older_than = self._parse_older_than_to_datetime(timefmt)
        res = True
        list_of = snapshots.get_list(older_than=older_than)
        list_of.sort(key = lambda x: x.date, reverse = True)
        for snap in list_of:
            if len(snap.children) < 2 and snap.tag == "":
                res &= self.delete(snap)
        return res
    
    def prune(self, snapshot):
        snapshot = Snapshot(snapshot)
        res = True
        if len(snapshot.children) != 0:
            raise Exception("Snapshot is not the end of a branch")
        while True:
            parent = snapshot.parent
            res &= self.delete(snapshot)
            snapshot = parent
            if snapshot == None or len(snapshot.children) != 0:
                break
        return res
    
    def tree(self):
        date_parent, history = self._get_status()
        tree = TreeView(history)
        tree.print()
    
    def recent(self, number, snapshot):
        print("%s and its predecessors. Showing %d snapshots.\n" % (snapshot, 
            number))
        snapshot = Snapshot(snapshot)
        for i in range(number):
            self.show(snapshot, compact=True)
            snapshot = snapshot.parent
            if snapshot == None or i == number - 1:
                break
            else:
                print()
        return True
    
    def clean(self, what="apt-cache"):
        snapshot_list = snapshots.get_list()
        for snapshot in snapshot_list:
            path = os.path.join(self.mp, snapshot.name)
            if what == "apt-cache":
                path = os.path.join(path, "var/cache/apt/archives")
                if not os.path.exists(path):
                    continue
                dirlist = os.listdir(path)
                for f in dirlist:
                    fpath = os.path.join(path, f)
                    if f.endswith(".deb") and os.path.lexists(fpath):
                        os.remove(fpath)


class Junction(object):
    def __init__(self, snapshot, start_column):
        self.name = snapshot.name
        self.branches_left_to_print = len(snapshot.children)
        self.columns = [start_column]
        self.date = snapshot.date


class TreeView(object):
    """ TreeView pretty printer """
    
    def __init__(self, latest_changes):
        self.latest_changes = latest_changes
    
    def _print_up_to_junction(self, snapshot):
        """ walks up the snapshot tree until the next one has more than one 
            child, pretty printing each one
        """
        padding = self._spacer()
        
        while True:
            print(padding + str(snapshot) + self._brief_changes(snapshot))
            snapshot = snapshot.parent
            if snapshot == None or len(snapshot.children) > 1:
                return snapshot
    
    def _brief_changes(self, snapshot):
        if snapshot.name == '@':
            changes = self.latest_changes
        else:
            changes = snapshot.changes
        if changes == None:
            return " (unknown)"
        codes = {"i": "+", "a": "+", "u": "^", "r": "-", "p": "-"}
        brief = defaultdict(int)
        for i in ("install", "auto-install", "upgrade", "remove", "purge"):
            if len(changes[i]) > 0:
                brief[codes[i[0]]] += len(changes[i])
        out = []
        for i in ("+", "^", "-"):
            if brief[i] > 0:
                out.append("%s%d" % (i, brief[i])) 
        if len(out) == 0:
            out = ["none"]
        return " (" + " ".join(out) + ")"
    
    def _spacer(self, stop_before_column=None):
        connected = u"│  "
        orphan = u"   "
        spacer = ""
        if stop_before_column == None:
            stop_before_column = self.column
        for col in range(1, stop_before_column):
            if col in self.orphans:
                spacer += orphan
            else:
                spacer += connected
        return spacer
    
    def _sort_key(self, snapshot):
        """ key for sorting the to_print list in order to assure that the 
            different branches are printed coherently
        """
        if snapshot.name == "@" or len(self.junctions) == 0:
            return snapshot.date
        junctions = self.junctions.keys()
        junctions.sort(key = lambda x: x.date)
        oldest = junctions[0]
        newest = junctions[-1]
        fca = snapshots.first_common_ancestor(newest, snapshot) 
        if fca == None or oldest.date < fca.date:
            return snapshot.date
        return fca.date
    
    def print(self):
        """ pretty print a view of the tree """
        self.column = 1
        self.orphans = []
        self.junctions = {}
        
        no_children = [Snapshot("@")]
        for snap in snapshots.get_list():
            if len(snap.children) == 0:
                no_children.append(snap)
        to_print = no_children
        to_print.sort(key = self._sort_key)
        
        while True:
            try:
                snapshot = to_print.pop()
            except IndexError:
                break

            junction = self._print_up_to_junction(snapshot)
            to_print.sort(key = self._sort_key)
            
            if junction == None:
                
                # We have reached the end of a disconnected branch
                self.orphans.append(self.column)
                print(self._spacer() + u"×  ")
                        
            elif junction not in self.junctions:
                
                # new junction found
                print(self._spacer() + u"│  ")
                
                self.junctions[junction] = Junction(junction, self.column)
                self.junctions[junction].branches_left_to_print -= 1
                
            else:
                # already seen this junction
                self.junctions[junction].branches_left_to_print -= 1
                self.junctions[junction].columns.append(self.column)
                
                if self.junctions[junction].branches_left_to_print == 0:
                
                    to_print.append(junction)
                    
                    # construct and print branch join up line
                    cols = self.junctions[junction].columns
                    joinup = self._spacer(cols[0]) + u"├──"
                    for i in range(cols[0] + 1, cols[-1]):
                        if i in cols:
                            joinup += u"┴──"
                        else:
                            joinup += u"───"
                    joinup += u"┘"
                    print(joinup)
                    
                    # clean-ups
                    self.column = self.junctions[junction].columns[0] - 1
                    self.orphans = [x for x in self.orphans 
                                          if x <= self.column]
                    del self.junctions[junction]
            
            self.column += 1
    
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
            sandbox=sandbox_root)
    apt_btrfs.tree()
    for k,v in apt_btrfs.__class__.__dict__.items():
        if not k.startswith("_"):
            print(k)
