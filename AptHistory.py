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
    def __init__(self, start, end, ops):
        self.start = start
        self.end = end
        self.i = self._parse(ops["install"])
        self.u = self._parse(ops["upgrade"])
        self.r = self._parse(ops["remove"])
        self.p = self._parse(ops["purge"])
        if "configure" in ops.keys():
            self.c = self._parse(ops["configure"])

    def _parse(self, pkgs):
        """ Parses the op pkg list and returns a pair of dictionaries
            The first contains the non automatic changes, the second contains
            the automatic ones. key = pkg_name, value = version_info.
            In fact, only installs can be marked automatic.
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


class DpkgHistoryEntry(object):
    """ a single dpkg history.log entry """
    def __init__(self, date, linetype, package, version):
        self.date = date
        self.type = linetype
        self.package = package
        self.version = version

    def __repr__(self):
        return "<DpkgHistoryEntry '%s' '%s' '%s' '%s'>" % (
            self.start, self.type, self.package, self.version)


class AptHistoryLog(object):
    """ Parser for the apt and dpkg history logs """
    def __init__(self, location="/var/log/", after = None):
        self.after = self._get_after_date(after)
        self.history = self._get_apt_history(location)
        dpkg_history = self._get_dpkg_history(location)
        #self.history.extend(dpkg_history)
        self.history.sort(key = lambda x: x.start)

    def _get_after_date(self, after):
        if isinstance(after, basestring):
            after = datetime.strptime(after.replace("  ", "_"), 
                                      "%Y-%m-%d_%H:%M:%S")
        if after is None:
            after = datetime.now() - timedelta(30)
        return after

    def _get_apt_history(self, location):
        """ Read apt history.log's and return a sorted list of entries """
        # Read current log file
        logfile = os.path.join(location, "apt", "history.log")
        try:
            history = self._parse_apt_logfile(open(logfile))
        except IOError:
            pass
        # Look through old log files until nothing more turns up
        for i in range(1, 10):
            logfile = os.path.join(location, "apt", "history.log.%d.gz" % i)
            entries = []
            try:
                entries = self._parse_apt_logfile(gzip.GzipFile(logfile))
            except IOError:
                pass
            if len(entries) == 0:
                break
            history.extend(entries)
        return sorted(history, key = lambda x: x.start)

    def _parse_apt_logfile(self, log_file):
        """ Read file object in and parse the entries """
        start, end = None, None
        ops = {"install":"", "upgrade":"", "remove":"", "purge":""}
        entries = []
        for line in (l.strip().decode("utf-8") for l in log_file):
            if line == "":
                continue
            
            linetype, contents = line.split(":", 1)
            linetype = linetype.lower()
            
            if linetype == "start-date":
                start = datetime.strptime(contents.strip(), 
                                          "%Y-%m-%d  %H:%M:%S")
            elif linetype == "end-date":
                end = datetime.strptime(contents.strip(), 
                                        "%Y-%m-%d  %H:%M:%S")
            elif linetype in ops.keys():
                ops[linetype] = contents.strip()
            
            if end:
                if start > self.after:
                    entry = AptHistoryEntry(start, end, ops)
                    entries.append(entry)
                start, end = None, None
                ops = {"install":"", "upgrade":"", "remove":"", "purge":""}
        return entries

    def _get_dpkg_history(self, location):
        """ Read dpkg.log's and return a list of AptHistoryEntry's
            corresponding to manual dpkg operations not covered by the apt
            history logs.
        """
        # Read current log file
        logfile = os.path.join(location, "dpkg.log")
        try:
            history = self._parse_dpkg_logfile(open(logfile))
        except IOError:
            pass
        # Look through old log files until entries are all too old
        for i in range(1, 10):
            logfile = os.path.join(location, "dpkg.log.%d" % i)
            try:
                entries = self._parse_dpkg_logfile(open(logfile))
            except IOError:
                pass    
            if len(entries) == 0:
                break
            history.extend(entries)
        return sorted(history, key=lambda x: x.date)

    def _date_outside_apt_history(self, date):
        for e in self.history:
            if date > e.start and date < e.end:
                return False
        return True

    def _parse_dpkg_logfile(self, log_file):
        """ Read file object in and parse the entries """
        print("hi dpkg parsing logfile")
        entries = []
        installs, upgrades, removes, purges, configures = [], [], [], [], []
        file_is_new_enough = False
        first, last = None, None
        for line in (l.strip().decode("utf-8") for l in log_file):
            if line == "":
                continue
            
            bits = line.split(" ")
            date = datetime.strptime(line[0:19], "%Y-%m-%d %H:%M:%S")
            linetype = bits[2]
            package = bits[3]
            
            if linetype not in ("install", "upgrade", "remove", "purge", 
                    "configure") or date < self.after:
                continue

            file_is_new_enough = True
            if date > end:
                print("date", date, " greater than", end)
                which += 1
                start, end = self._get_start_end(which)
                # Make an entry if there is anything to put in it
                if first is not None:
                    installs = ", ".join(installs)
                    upgrades = ", ".join(upgrades)
                    removes = ", ".join(removes)
                    purges = ", ".join(purges)
                    configures = ", ".join(configures)
                    
                    entry = "blah"#AptHistoryEntry(first, last, installs, upgrades, 
                                  #      removes, purges, configures)
                    print("packing entry:", entry)
                    entries.append(entry)
                    installs, upgrades, removes, purges, configures = \
                        [], [], [], [], []
                    first, last = None, None
            if date < start:
                # We have an interesting entry, lets put the info aside
                if first is None:
                    first = date
                else:
                    last = date
                if linetype == "install":
                    version = bits[5]
                    installs.append("%s (%s)" % (package, version))
                elif linetype == "upgrade":
                    version = ", ".join(bits[4:5])
                    upgrades.append("%s (%s)" % (package, version))
                elif linetype == "remove":
                    version = bits[4]
                    removes.append("%s (%s)" % (package, version))
                elif linetype == "purge":
                    version = bits[4]
                    purges.append("%s (%s)" % (package, version))
                elif linetype == "configure":
                    version = bits[4]
                    configures.append("%s (%s)" % (package, version))
                print("found:", linetype, date, package,  version)
        
        return entries, file_is_new_enough

    def consolidate(self):
        """ combines the info in the history list """
        start = self.history[0].start
        end = self.history[-1].end
        # installs, auto-installs, upgrades, removes, purges
        i = ({}, {})
        return AptHistoryEntry(start, end, i, i, i, i)


if __name__ == "__main__":
    log = AptHistoryLog(location="test/data/var/log", after=datetime(2013,07,31))
    print(len(log.history))
    for e in log.history:
        print("Start", e.start)
        #print(e)

