# Copyright (C) 2013 jpeg729
#
# Author:
#  jpeg729
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
        self.i = self._parse(installs)
        self.u = self._parse(upgrades)
        self.r = self._parse(removes)
        self.p = self._parse(purges)

    def _parse(self, pkgs):
        """ Parses the op pkg list and returns a pair of dictionaries
            The first contains the non automatic changes, the second contains
            the others. key = pkg_name, value = version_info.
        """
        if not isinstance(pkgs, basestring):
            # already in tuple of dicts format
            return pkgs
        
        pkgs = pkgs.replace(":%s" % _arch, "")
        
        if pkgs == "":
            return {}, {}

        pkg_dict = {}
        auto = {}
        
        if ")" in pkgs:
            pkg_list = pkgs.split("), ")
        else:
            pkg_list = [pkgs]
        
        for i in pkg_list:
            k, v = i.split(" (")
            v = v.strip(")")
            if "automatic" in v:
                auto[k] = v.split(", automatic")[0]
            else:
                pkg_dict[k] = v

        return pkg_dict, auto

    def __repr__(self):
        return "<AptHistoryEntry '%s' '%s' '%s' '%s' '%s' '%s'>" % (
            self.start, self.end, self.i, self.u, self.r, self.p)


class AptHistoryLog(list):
    """ list of AptHistoryEntry's reflecting the apt history logs """
    def __init__(self, location="/var/log/", before = datetime.now(), 
                 after = None):
        super(AptHistoryLog, self).__init__()
        
        if isinstance(before, basestring):
            before = datetime.strptime(before.replace("  ", "_"), 
                                       "%Y-%m-%d_%H:%M:%S")
        self.before = before
        
        if isinstance(after, basestring):
            after = datetime.strptime(after.replace("  ", "_"), 
                                      "%Y-%m-%d_%H:%M:%S")
        if after is None:
            after = before - timedelta(365)
        self.after = after

        try:
            logfile = os.path.join(location, "apt", "history.log")
            self._parse_apt_logfile(open(logfile))
        except IOError:
            pass

        # Look through old log files until nothing more turns up
        for i in range(1, 10):
            length = len(self)
            try:
                logfile = os.path.join(location, "apt", "history.log.%d.gz" % i)
                self._parse_apt_logfile(gzip.GzipFile(logfile))
            except IOError:
                pass
            if len(self) == length:
                break
        
        # TODO read in /var/log/dpkg.log(.i) and see if that adds anything
        # pb: it only really makes sense to compare it with the consolidated
        # version
        
        # sort thyself
        self.sort(key = lambda x: x.start)

    def _parse_apt_logfile(self, log_file):
        """ Read file object in and parse the entries """
        start, end, installs, upgrades, removes, purges = "", "", "", "", "", ""
        for line in (l.strip().decode("utf-8") for l in log_file):
            if len(line) == 0 or line.startswith("#"):
                continue
            
            linetype, contents = line.split(":", 1)
            
            if linetype == "Start-Date":
                start = datetime.strptime(contents.strip(), 
                                          "%Y-%m-%d  %H:%M:%S")
            elif linetype == "End-Date":
                end = datetime.strptime(contents.strip(), 
                                        "%Y-%m-%d  %H:%M:%S")
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

    def consolidate(self):
        """ combines the info in all AptHistoryEntry's into one """
        start = self[0].start
        end = self[-1].end
        # installs, auto-installs, upgrades, removes, autoremoves, purges
        i = ({}, {})
        return AptHistoryEntry(start, end, i, i, i, i)


if __name__ == "__main__":
    log = AptHistoryLog(location="test/data")
    print(len(log))
    for e in log:
        print("Start", e.start)
        print(e)

