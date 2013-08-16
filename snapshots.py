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
import cPickle as pickle


SNAP_PREFIX = "@apt-snapshot-"
CHANGES_FILE = "etc/apt-btrfs-changes"
PARENT_LINK = "etc/apt-btrfs-parent"
# If you modify PARENT_LINK don't forget to modify the line
# parent_path = os.path.join("..", "..", parent)
# in Snapshot._link()

# mp is the mountpoint of the btrfs volume root. It will be set by 
# the setup function called from AptBtrfsSnapshot.__init__
mp = None

list_of = None
parents, children, orphans = {}, {}, []
junctions, ancestor_junctions = [], {}
common_ancestors, origins = {}, {}


def setup(mountpoint):
    global mp, list_of
    mp = mountpoint
    _make_list()
    _parse_tree()

def get_list(older_than=False):
    """ return the list of available snapshots
        If "older_than" is given (as a datetime) it will only include
        snapshots that are older then the given date)
    """
    if older_than == False:
        return list_of[:]
    older = [s for s in list_of if s.date < older_than]
    return older

def first_common_ancestor(younger, older):
    """ find first common ancestor """
    global common_ancestors
    if younger.date < older.date:
        younger, older = older, younger
    key = younger.name + older.name
    if key in common_ancestors:
        print('found', key)
        return common_ancestors[key]
    
    while True:
        if younger.date < older.date:
            younger, older = older, younger
        younger = younger.parent
        if younger == None or younger == older:
            common_ancestors[key] = younger
            return younger
            

def _make_list():
    """ make the list of available snapshots """
    global list_of
    list_of = []
    for e in os.listdir(mp):
        if e.startswith(SNAP_PREFIX):
            pos = len(SNAP_PREFIX)
            d = e[pos:pos + 19]
            try:
                date = datetime.datetime.strptime(d, "%Y-%m-%d_%H:%M:%S")
            except ValueError:
                # have found a badly named snapshot
                if e != "@":
                    raise Hell
                continue
            list_of.append(Snapshot(e))

def _parse_tree():
    global parents, children, orphans, junctions
    parents = {}
    children = {}
    orphans = []
    snapshots = get_list()
    snapshots.append("@")
    for snapshot in snapshots:
        name = str(snapshot)
        parent_file = os.path.join(mp, name, PARENT_LINK)
        try:
            link_to = os.readlink(parent_file)
        except OSError:
            orphans.append(snapshot)
            continue
        path, parent = os.path.split(link_to)
        parents[name] = Snapshot(parent)
        if parent in children.keys():
            children[parent].append(snapshot)
        else:
            children[parent] = [snapshot]
    junctions = [s for s in list_of if len(s.children) > 1]


class Snapshot(object):

    def __init__(self, name):
        if isinstance(name, Snapshot):
            self.name = name.name
            self.date = name.date
            return
        # name
        self.name = name
        # date
        pos = len(SNAP_PREFIX)
        date = name[pos:pos + 19]
        try:
            self.date = datetime.datetime.strptime(date, "%Y-%m-%d_%H:%M:%S")
        except ValueError:
            self.date = None
            if self.name != "@":
                raise Hell # TODO better error message
            else:
                self.date = datetime.datetime.now()
        
    def __getattr__(self, attr):
        if attr == "parent":
            return self._get_parent()
        if attr == "children":
            return self._get_children()
        if attr == "changes":
            return self._load_changes()
        if attr == "ancestor_junctions":
            return self._get_ancestor_junctions()
        if attr == "origin":
            return self._get_origin()
    
    def __setattr__(self, attr, value):
        if attr == "parent":
            self._link(value)
        elif attr == "changes":
            self._store_changes(value)
        else:
            object.__setattr__(self, attr, value)
    
    def __unicode__(self):
        return self.name
        
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return '<Snapshot %s>' % self.name
        
    def __hash__(self):
        return hash(self.date)
        
    def __eq__(self, other):
        if isinstance(other, Snapshot):
            return self.name == other.name
        return False
    
    def _load_changes(self):
        changes_file = os.path.join(mp, self.name, CHANGES_FILE)
        try:
            history = pickle.load(open(changes_file, "rb"))
            return history
        except IOError:
            return None
    
    def _store_changes(self, changes):
        changes_file = os.path.join(mp, self.name, CHANGES_FILE)
        if changes is None:
            if os.path.exists(changes_file):
                os.remove(changes_file)
        else:
            pickle.dump(changes, open(changes_file, "wb"))
    
    def _get_parent(self):
        if self.name in parents.keys():
            return parents[self.name]
        return None

    def _get_children(self):
        if self.name in children.keys():
            return children[self.name]
        return []

    def _link(self, parent):
        """ sets symlink from child to parent 
            or deletes it if parent == None 
        """
        parent_file = os.path.join(mp, self.name, PARENT_LINK)
        # remove parent link from child
        if os.path.exists(parent_file):
            os.remove(parent_file)
        # link to parent
        if parent is not None:
            parent_path = os.path.join("..", "..", str(parent))
            os.symlink(parent_path, parent_file)

    def _get_ancestor_junctions(self):
        """ returns a list of ancestors that have more than one child ordered
            by age, youngest first.
            Stocks the result to avoid recalculating.
        """
        global ancestor_junctions, origins
        if self in ancestor_junctions:    
            return ancestor_junctions[self][:]
        snapshot = self
        l = []
        while True:
            next = snapshot.parent
            if next == None:
                break
            else:
                snapshot = next
            if len(snapshot.children) > 1:
                l.append(snapshot)
        origins[self] = snapshot
        ancestor_junctions[self] = l
        return l[:]
        
    def _get_origin(self):
        """ Returns oldest parent """
        if self not in origins:
            self._get_ancestor_junctions()
        return origins[self]
