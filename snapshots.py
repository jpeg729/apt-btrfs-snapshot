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

from dpkg_history import DpkgHistory


SNAP_PREFIX = "@apt-snapshot-"
CHANGES_FILE = "etc/apt-btrfs-changes"
PARENT_LINK = "etc/apt-btrfs-parent"
PARENT_DOTS = "../../"

# mp is the mountpoint of the btrfs volume root. It will be set by 
# the setup function called from AptBtrfsSnapshot.__init__
mp = None

list_of = None
parents, children, orphans = {}, {}, []


class BadSnapshotError(Exception):
    pass


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
    if isinstance(older_than, basestring):
        older_than = datetime.datetime.strptime(older_than, "%Y-%m-%d_%H:%M:%S")
    if older_than == False:
        return list_of[:]
    older = [s for s in list_of if s.date < older_than]
    return older

def first_common_ancestor(one, another):
    """ find first common ancestor of two snapshots """
    younger = Snapshot(one)
    older = Snapshot(another)
    
    while True:
        if younger.date < older.date:
            younger, older = older, younger
        younger = younger.parent
        if younger == None or younger == older:
            return younger
            

def _make_list():
    """ make the list of available snapshots """
    global list_of
    list_of = []
    for e in os.listdir(mp):
        pos = len(SNAP_PREFIX)
        if e.startswith(SNAP_PREFIX) and len(e) >= pos + 19:
            try:
                list_of.append(Snapshot(e))
            except BadSnapshotError:
                continue

def _parse_tree():
    """ go through list finding parents and populating the global
        parents, children and orphans lists for later use
    """
    global parents, children, orphans
    parents = {}
    children = {}
    orphans = []
    snapshots = get_list()
    snapshots.append(Snapshot("@"))
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
            if self.name != "@":
                raise BadSnapshotError
            self.date = datetime.datetime.now()
        
    def __getattr__(self, attr):
        if "_get" not in attr and hasattr(self, "_get_%s" % attr):
            return self.__getattribute__("_get_%s" % attr)()
    
    def __setattr__(self, attr, value):
        if hasattr(self, "_set_%s" % attr):
            return self.__getattribute__("_set_%s" % attr)(value)
        else:
            object.__setattr__(self, attr, value)
    
    def __unicode__(self):
        return unicode(self.name)
        
    def __str__(self):
        return str(self.name)
        
    def __hash__(self):
        return hash(self.date)
        
    def __eq__(self, other):
        if isinstance(other, Snapshot):
            return self.name == other.name
        return False
    
    def _get_changes(self):
        changes_file = os.path.join(mp, self.name, CHANGES_FILE)
        try:
            history = pickle.load(open(changes_file, "rb"))
            return history
        except IOError:
            return None
    
    def _set_changes(self, changes):
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

    def _set_parent(self, parent):
        """ sets symlink from child to parent 
            or deletes it if parent == None 
        """
        old_parent = self.parent
        parent_file = os.path.join(mp, self.name, PARENT_LINK)
        # remove parent link from self
        if os.path.lexists(parent_file):
            os.remove(parent_file)
        # link to parent
        if parent is not None:
            parent_path = os.path.join(PARENT_DOTS, str(parent))
            os.symlink(parent_path, parent_file)

    def _get_children(self):
        if self.name in children.keys():
            return children[self.name]
        return []
    
    def _get_tag(self):
        pos = len(SNAP_PREFIX)
        if len(self.name) > pos + 19:
            return self.name[pos + 20:]
        return ""

    def will_delete(self):
        """ correct parent links and change info for a snapshot about to be
            deleted. Does internal housekeeping as well.
            A messy solution needed for delete_older_than to work.
        """
        # correct parent links and combine change info
        parent = self.parent
        kids = self.children
        old_history = self.changes
        
        # clean-ups
        list_of.remove(self) # necessary
        if self.name in children:
            del children[self.name] # unnecessary
        if self.name in parents: # unnecessary
            del parents[self.name]
        if parent != None and parent.name in children:
            children[parent.name].remove(self) # necessary
        
        for child in kids:
            child.parent = parent
            
            # housekeeping
            parents[child.name] = parent
            if parent != None:
                children[parent.name].append(child) # necessary
            
            newer_history = child.changes
            if old_history == None:
                combined = newer_history
            elif newer_history == None:
                combined = None
            else:
                combined = old_history + newer_history
            child.changes = combined

