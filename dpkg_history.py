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
from collections import defaultdict
import platform

_arch = platform.machine()
if _arch == "x86_64": _arch = "amd64"


class DpkgHistory(dict):
    """ Parser for the dpkg history logs """
    def __init__(self, var_location="/var/", since = None):
        super(DpkgHistory, self).__init__()

        self["install"] = []
        self["auto-install"] = []
        self["upgrade"] = []
        self["remove"] = []
        self["purge"] = []

        self.var_location = var_location
        self.since = self._get_date_from_string(since)
        self._get_dpkg_history()
        if len(self['install']) > 0:
            self.auto = self._find_auto_installs()
            self._split_installs_by_auto()
        self._sort_lists()

    def _get_date_from_string(self, since):
        if isinstance(since, basestring):
            since = datetime.strptime(since.replace(" ", "_"), 
                                      "%Y-%m-%d_%H:%M:%S")
        if since is None:
            since = datetime.now() - timedelta(30)
        return since

    def _get_dpkg_history(self):
        """ Read dpkg.log's and return dictionary of ops
        """
        logfiles = self._logfiles_to_check()
        self._parse(logfiles)

    def _logfiles_to_check(self):
        """ Return an ordered list of opened logfiles young enough to be 
            interesting.
        """
        logfile = os.path.join(self.var_location, "log", "dpkg.log")
        try:
            logfiles = [open(logfile)]
        except IOError:
            return []
        if self._get_earliest_date(logfiles[0]) < self.since:
            return logfiles
        # Add older log files to the list until they are too old
        for i in range(1, 10):
            try:
                logfiles.append(open("%s.%d" % (logfile, i)))
            except IOError:
                try:
                    logfiles.append(gzip.GzipFile("%s.%d.gz" % (logfile, i)))
                except IOError:
                    break
            if self._get_earliest_date(logfiles[-1]) < self.since:
                break
        return reversed(logfiles)

    def _get_earliest_date(self, logfile):
        """ read in first line of file and parse the date """
        line = logfile.readline()
        date = datetime.strptime(line[0:19], "%Y-%m-%d %H:%M:%S")
        logfile.seek(0)
        return date

    def _read_files(self, files):
        for f in files:
            for line in f:
                yield line.strip()

    def _parse(self, logfiles):
        """ reads in the opened logfiles and makes lists of the ops mentioned.
            Returns a dictionary of lists, each list contains (pkg, version)
            tuples.
        """
        ops_by_package = defaultdict(list)
        version = defaultdict(list)
        # List ops per package
        for line in self._read_files(logfiles):
            if line == "":
                continue
            
            bits = line.split(" ")
            
            linetype = bits[2]
            if linetype not in ("install", "upgrade", "remove", "purge"):
                continue
                
            date = datetime.strptime(line[0:19], "%Y-%m-%d %H:%M:%S")
            if date < self.since:
                continue
            
            package = bits[3]
            ops_by_package[package].append(linetype)
            version[package].append(bits[4:6])
        
        instup = ("install", "upgrade")
        remurge = ("remove", "purge")
        # Decide which op to remember for each package
        for package, ops in ops_by_package.iteritems():
        
            oldest_version = version[package][0][0]
            newest_version = version[package][-1][1]
            version_change = "%s, %s" % (oldest_version, newest_version)
            
            if ops[0] == "install" and ops[-1] not in remurge:
            
                self['install'].append((package, newest_version))
                
            elif ops[0] == "upgrade" and ops[-1] in instup:
                
                self['upgrade'].append((package, version_change))
                
            elif ops[0] == "upgrade" and ops[-1] in remurge:
                
                self[ops[-1]].append((package, oldest_version))
                
            elif ops[0] in remurge and ops[-1] in instup:
            
                if oldest_version != newest_version:
                    self['upgrade'].append((package, version_change))
                
            elif ops[0] in remurge and ops[-1] in remurge:
            
                self[ops[-1]].append((package, oldest_version))

    def _find_auto_installs(self):
        states_filename = os.path.join(self.var_location, "lib", "apt", 
                "extended_states")
        try:
            states_file = open(states_filename)
        except IOError:
            return []
        
        package = ""
        auto_installed = []
        for line in (line.strip() for line in states_file):
            if line == "":
                continue
            
            contents = line.split(" ")[1]
            
            if line.startswith("Package: "):
                package = contents
            
            elif line.startswith("Architecture: "):
                if contents != _arch:
                    package += ":" + contents
            
            elif line.startswith("Auto-Installed: ") and package:
                if contents == "1":
                    auto_installed.append(package)
                    package = ""

        return auto_installed

    def _split_installs_by_auto(self):
        manual_installs = []
        auto_installs = []
        for package, version in self['install']:
            if package in self.auto:
                auto_installs.append((package, version))
            else:
                manual_installs.append((package, version))
        self['install'] = manual_installs
        self['auto-install'] = auto_installs

    def _sort_lists(self):
        for v in self.values():
            v.sort(key = lambda x: x[0])


if __name__ == "__main__":
    date = datetime(2013, 8, 6, 12, 20, 00)
    log = DpkgHistory(var_location="test/data/var/", since=date)
#    print("Changes since", date)
#    for op, packages in log.iteritems():
#        print(op, len(packages))
    for i in log.auto: 
        print(i)

