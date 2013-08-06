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

from datetime import datetime, timedelta
import os
import time
import gzip
import textwrap
import platform

_arch = platform.machine()
if _arch == "x86_64": _arch = "amd64"


class AptHistoryEntry(object):
    """ a single apt history.log entry """
    def __init__(self, start, end, installs, upgrades, removes, purges):
        self.start = start
        self.end = end
        self.installs = installs
        self.upgrades = upgrades
        self.removes = removes
        self.purges = purges

    def get(self, op):
        pkgs = self.__dict__[op]
        pkgs = pkgs.replace(":%s" % _arch, "")

        pkg_dict = {}
        auto = {}

        pkg_list = pkgs.split("), ")
        for i in pkg_list:
            k, v = i.split(" (")
            v = v.strip(")")
            if "automatic" in v:
                auto[k] = v.split(",")[0]
            else:
                pkg_dict[k] = v

        return pkg_dict, auto
        
    def _format_op(self, op, columns, show_auto, show_versions):
        """ Looks through the relevant list of actions on packages and puts the
        info in a string formatted to the screens width.
        """
        pkgs = self.__dict__[op]
        if pkgs:
            opname = "%s:" % op[:-1].capitalize()
            
            # Collect package names and details
            pkgs = pkgs.replace(":%s" % _arch, "")
            entry = None
            entries = []
            versions = []
            for info in (i.strip(" ,") for i in pkgs.split(" ")):
                if not info: continue
                if entry is None: 
                    entry = info  # get package name
                elif "automatic" in info and not show_auto:
                    entry = None
                elif show_versions:
                    versions.append(info.strip("()"))
                if entry and info.endswith(")"):
                    if versions and show_versions:
                        entry += " (%s)" % ", ".join(versions)
                    entries.append(entry)
                    entry = None
                    versions = []

            # Concatenate making sure that lines don't exceed console width
            listing = "%s %s" % (opname, ", ".join(entries))
            out = textwrap.fill(listing, width=columns, initial_indent=' ', subsequent_indent='  ')
            return out

    def pretty_print(self, show_auto = False, show_versions = False):
        """ Prints out the packages installed, upgraded, removed and purged in 
        an operation. The output is adapted to the screen width with indenting
        on the left hand side to facilitate reading the output.
        """
        # Get console width
        rows, columns = os.popen('stty size', 'r').read().split()
        columns = int(columns)
        
        for op in ("installs", "upgrades", "removes", "purges"):
            out = self._format_op(op, columns, show_auto, show_versions)
            if out: print(out)

    def __repr__(self):
        return "<AptHistoryEntry '%s' '%s' '%s' '%s' '%s' '%s'>" % (
            self.start, self.end, self.installs,
            self.upgrades, self.removes, self.purges)


class AptHistoryLog(list):
    """ list of Apt history.log entries """
    def __init__(self, location="/var/log/apt/", before = datetime.now(), after = None):
        super(AptHistoryLog, self).__init__()
        
        if isInstance(before, str):
            before = datetime.strptime(before, "%Y-%m-%d  %H:%M:%S")
        self.before = before
        
        if isInstance(after, str):
            after = datetime.strptime(after, "%Y-%m-%d  %H:%M:%S")
        if after is None:
            after = before - timedelta(30)
        self.after = after

        try:
            logfile = os.path.join(location, "history.log")
            with open(logfile) as log_file:
                self._parse_file(log_file)
        except IOError:
            pass

        try:
            logfile = os.path.join(location, "history.log.1.gz")
            with gzip.GzipFile(logfile) as log_file:
                self._parse_file(log_file)
        except IOError:
            pass

    def _parse_file(self, log_file):
        start, end, installs, upgrades, removes, purges = "", "", "", "", "", ""
        for line in (l.strip() for l in log_file):
            if line == "" or line.startswith("#"):
                continue
            
            linetype, contents = line.split(":", 1)
            
            #TODO parse dates into better formats
            if linetype == "Start-Date":
                start = datetime.strptime(contents.strip(), "%Y-%m-%d  %H:%M:%S")
            elif linetype == "End-Date":
                end = datetime.strptime(contents.strip(), "%Y-%m-%d  %H:%M:%S")
            elif linetype == "Install":
                installs = contents.strip()
            elif linetype == "Upgrade":
                upgrades = contents.strip()
            elif linetype == "Remove":
                removes = contents.strip()
            elif linetype == "Purge":
                purges = contents.strip()
            
            if end:
                if start > self.after and end < self.before:
                    entry = AptHistoryEntry(start, end, installs, upgrades, 
                                            removes, purges)
                    self.append(entry)
                start, end = None, None
                installs, upgrades, removes, purges = "", "", "", ""
                

if __name__ == "__main__":
    log = AptHistoryLog(location="test/data")
    for e in log:
        print("Start", e.start)
        e.pretty_print(show_auto = True, show_versions = True)
        print(e.installs)
