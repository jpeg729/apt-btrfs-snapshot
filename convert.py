#!/usr/bin/python
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


import datetime
import os
import sys
import fcntl

from apt_btrfs_snapshot import (
    AptBtrfsSnapshot, 
    supported,
)
import snapshots
from snapshots import (
    Snapshot,
    SNAP_PREFIX,
)
from dpkg_history import DpkgHistory

if __name__ == "__main__":

    if os.getuid() != 0 and len(sys.argv) == 1:
        print(_("Sorry, you need to be root to run this program"))
        sys.exit(1)

    if not supported():
        print(_("Sorry, your system lacks support for the snapshot feature"))
        sys.exit(1)
    
    if len(sys.argv) > 1:
        apt_btrfs = AptBtrfsSnapshot(test_mp = sys.argv[1])
    else:
        apt_btrfs = AptBtrfsSnapshot()
    mountpoint = apt_btrfs.mp
    snaplist = snapshots.get_list()
    snaplist.sort(key = lambda x: x.date)
    
    previous = None
    for snap in snaplist:
        if previous:
            snap.parent = previous
            location = os.path.join(mountpoint, snap.name, "var")
            date = previous.date
            snap.changes = DpkgHistory(var_location=location, since=date)
        previous = snap
    Snapshot("@").parent = previous
