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


class AptHistoryEntry(object):
    """ a single apt history.log entry """
    def __init__(self, start, end, installs, upgrades, removes, purges, 
                 show_auto, show_versions):
        self.start = start
        self.end = end
        self.installs = installs
        self.upgrades = upgrades
        self.removes = removes
        self.purges = purges
        self.show_auto = show_auto
        self.show_versions = show_versions
        
    def _format_op(self, op, columns):
        """ Looks through the relevant list of actions on packages and puts the
        info in a string formatted to the screens width.
        """
        pkgs = self.__dict__[op]
        if pkgs:
            opname = " %s:" % op[:-1].capitalize()
            
            # Collect package names and details
            pkgs = pkgs.replace(":amd64", "")
            entry = None
            entries = []
            versions = []
            for info in (i.strip(" ,") for i in pkgs.split(" ")):
                if not info: continue
                if entry is None: 
                    entry = info  # get package name
                elif "automatic" in info and not self.show_auto:
                    entry = None
                elif self.show_versions:
                    versions.append(info.strip("()"))
                if entry and info.endswith(")"):
                    if versions and self.show_versions:
                        entry += " (%s)" % ", ".join(versions)
                    entries.append(entry)
                    entry = None
                    versions = []

            # Concatenate making sure that lines don't exceed console width
            length = len(opname)
            out = []
            e = (i for i in entries)
            try:
                entry = e.next()
            except StopIteration:
                if self.show_auto:
                    return "%s None" % opname
                return "%s No non-automatic packages" % opname
            line = [opname]
            while True:
                try:
                    next_entry = e.next()
                    entry = entry + ","
                except StopIteration:
                    next_entry = None
                length = length + len(entry) + 1
                if length <= columns:
                    line.append(entry)
                else:
                    out.append(" ".join(line))
                    line = [entry]
                    length = len(entry) + 2
                if next_entry is None:
                    out.append(" ".join(line))
                    break
                entry = next_entry
            return "\n  ".join(out)

    def pretty_print(self):
        """ Prints out the packages installed, upgraded, removed and purged in 
        an operation. The output is adapted to the screen width with indenting
        on the left hand side to facilitate reading the output.
        """
        # Get console width
        rows, columns = os.popen('stty size', 'r').read().split()
        columns = int(columns)
        
        for op in ("installs", "upgrades", "removes", "purges"):
            out = self._format_op(op, columns)
            if out: print(out)

    def __repr__(self):
        return "<AptHistoryEntry '%s' '%s' '%s' '%s' '%s' '%s'>" % (
            self.start, self.end, self.installs,
            self.upgrades, self.removes, self.purges)


class AptHistoryLog(list):
    """ list of Apt history.log entries """
    def __init__(self, location="/var/log/apt/", show_auto=False, 
                 show_versions=True):
        super(AptHistoryLog, self).__init__()

        logfile = os.path.join(location, "history.log")
        with open(logfile) as log_file:
            start, end, installs, upgrades, removes, purges = "", "", "", "", "", ""
            for line in (l.strip() for l in log_file):
                if line == "" or line.startswith("#"):
                    continue
                
                linetype, contents = line.split(":", 1)
                
                #TODO parse dates into better formats
                if linetype == "Start-Date":
                    start = contents
                elif linetype == "End-Date":
                    end = contents
                elif linetype == "Install":
                    installs = contents
                elif linetype == "Upgrade":
                    upgrades = contents
                elif linetype == "Remove":
                    removes = contents
                elif linetype == "Purge":
                    purges = contents
                
                if end:
                    #try:
                    entry = AptHistoryEntry(start, end, installs, upgrades, 
                                            removes, purges, show_auto, 
                                            show_versions)
                    start, end = None, None
                    installs, upgrades, removes, purges = "", "", "", ""
                    #except ValueError:
                    #    continue
                    self.append(entry)

