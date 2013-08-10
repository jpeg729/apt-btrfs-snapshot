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


class DpkgHistory(list):
    """ Parser for the dpkg history logs """
    def __init__(self, var_location="/var/", since = None):
        self.var_location = var_location
        self.since = self._get_since_date(since)
        self.history = self._get_dpkg_history()

    def _get_since_date(self, since):
        if isinstance(since, basestring):
            since = datetime.strptime(since.replace("  ", "_"), 
                                      "%Y-%m-%d_%H:%M:%S")
        if since is None:
            since = datetime.now() - timedelta(30)
        return since

    def _get_dpkg_history(self):
        """ Read dpkg.log's and return dictionary of ops
        """
        logfiles = self._logfiles_to_check()
        ops = self._parse(logfiles)
        return ops

    def _logfiles_to_check(self):
        """ Return an ordered list of opened logfiles young enough to be 
            interesting.
        """
        logfile = os.path.join(self.var_location, "log", "dpkg.log")
        try:
            logfiles = [open(logfile)]
        except IOError:
            return []
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
        oplists = {"install":[], "upgrade":[], "remove":[], "purge":[]}
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
            
            # DEBUG
            if len(ops) > 1:
                pass#print(package, ops, version_change)
            
            if ops[0] == "install" and ops[-1] not in remurge:
            
                oplists['install'].append((package, newest_version))
                
            elif ops[0] == "upgrade" and ops[-1] in instup:
                
                oplists['upgrade'].append((package, version_change))
                
            elif ops[0] == "upgrade" and ops[-1] in remurge:
                
                oplists[ops[-1]].append((package, oldest_version))
                
            elif ops[0] in remurge and ops[-1] in instup:
            
                if oldest_version != newest_version:
                    oplists['upgrade'].append((package, version_change))
                
            elif ops[0] in remurge and ops[-1] in remurge:
            
                oplists[ops[-1]].append((package, oldest_version))
                
        return oplists


if __name__ == "__main__":
    log = DpkgHistory(var_location="test/data/var/", since=datetime(2013, 8, 6, 12, 20, 00))
    print(" ")
    for op, packages in log.history.iteritems():
        print(op, len(packages))
        for p in packages:
            pass
            if op == "upgrade": # and p[0].startswith('libmuff'):
                print(p[0])
    print(" ")
    #print(log.history['install'], len(log.history['install']))

