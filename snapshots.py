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


SNAP_PREFIX = "@apt-snapshot-"
CHANGES_FILE = "etc/apt-btrfs-changes"
PARENT_LINK = "etc/apt-btrfs-parent"
# If you modify PARENT_LINK don't forget to modify the line
# parent_path = os.path.join("..", "..", parent)
# in Snapshot._link()

# mp will be set by AptBtrfsSnapshot.__init__
mp = None

parents, children, orphans = None, None, None
list_of = None


def get_list(older_than=False):
    """ get the list of available snapshots
        If "older_then" is given (as a datetime) it will only include
        snapshots that are older then the given date)
    """
    if list_of is None:
        l = []
        for e in os.listdir(mp):
            if e.startswith(SNAP_PREFIX):
                pos = len(SNAP_PREFIX)
                d = e[pos:pos + 19]
                try:
                    date = datetime.datetime.strptime(d, "%Y-%m-%d_%H:%M:%S")
                except ValueError:
                    # have found a badly named snapshot
                    continue
                if older_than == False or date < older_than:
                    l.append(Snapshot(e))
    list_of = l
    return list_of[:]

def _parse_tree():
    global parents, children, orphans
    parents = {}
    children = {}
    orphans = []
    snapshots = get_list()
    snapshots.append("@")
    for name in snapshots:
        parent_file = os.path.join(mp, name, PARENT_LINK)
        try:
            link_to = os.readlink(parent_file)
        except OSError:
            orphans.append(Snapshot(name))
            continue
        path, parent = os.path.split(link_to)
        parents[self.name] = Snapshot(parent)
        if parent in children.keys():
            children[parent].append(Snapshot(name))
        else:
            children[parent] = [Snapshot(name)]


class Snapshot(object):

    def __init__(self, name):
        self.name = name
        
        pos = len(SNAP_PREFIX)
        d = name[pos:pos + 19]
        try:
            self.date = datetime.datetime.strptime(d, "%Y-%m-%d_%H:%M:%S")
        except ValueError:
            if self.name != "@":
                raise Hell # TODO better error message
                
        if list_of is None:
            get_list()

        if parents is None:
            _parse_tree()
    
    def __getattr__(self, attr):
        if attr == "parent":
            return self._get_parent()
        if attr == "children":
            return self._get_children()
        if attr == changes:
            return self._load_changes()
    
    def __setattr__(self, attr, value):
        if attr == "parent":
            self._link(value)
        if attr == "changes":
            self._store_changes(value)
    
    def __str__(self):
        return self.name
    
    def _load_changes(self):
        changes_file = os.path.join(self.mp, self.name, CHANGES_FILE)
        try:
            history = pickle.load(open(changes_file, "rb"))
            return history
        except IOError:
            return None
    
    def _store_changes(self, changes):
        changes_file = os.path.join(self.mp, self.name, CHANGES_FILE)
        pickle.dump(changes, open(changes_file, "wb"))
    
    def _get_parent(self):
        if self.name in parents.keys():
            return parents[self.name]
        return None

    def _get_children(self):
        if self.name in children.keys():
            return children[self.name]
        return None

    def _link(self, parent):
        """ sets symlink from child to parent 
            or deletes it if parent == None 
        """
        parent_file = os.path.join(self.mp, self.name, PARENT_LINK)
        # remove parent link from child
        if os.path.exists(parent_file):
            os.remove(parent_file)
        # link to parent
        if parent is not None:
            parent_path = os.path.join("..", "..", parent)
            os.symlink(parent_path, parent_file)

