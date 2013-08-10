#!/usr/bin/python

try:
    from StringIO import StringIO
    StringIO  # pyflakes
except ImportError:
    from io import StringIO
#import mock
import os
import sys
import time
import unittest
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from dpkg_history import DpkgHistory


class TestDpkgHistory(unittest.TestCase):

    def test_get_date_from_string(self):
        log = DpkgHistory(var_location="data/var/", since = datetime(2013, 8, 01, 19, 53, 46))
        d1 = log._get_date_from_string("2013-08-09 21:08:01")
        d2 = log._get_date_from_string("2013-08-09_21:08:01")
        self.assertEqual(d1, d2)
        self.assertEqual(d1, datetime(2013, 8, 9, 21, 8, 01))

    def test_logfiles_to_check(self):
        log = DpkgHistory(var_location="data/var/", since = datetime(2012, 5, 3, 12, 20, 00))
        files = [f.name for f in log._logfiles_to_check()]
        self.assertEqual(files, [u'data/var/log/dpkg.log.1', u'data/var/log/dpkg.log'])
        
        log = DpkgHistory(var_location="data/var/", since = datetime(2012, 04, 25, 12, 04, 27))
        files = [f.name for f in log._logfiles_to_check()]
        self.assertEqual(files, [u'data/var/log/dpkg.log.2.gz', u'data/var/log/dpkg.log.1', u'data/var/log/dpkg.log'])
        
        log = DpkgHistory(var_location="data/var/", since = datetime(2013, 8, 01, 19, 53, 46))
        files = [f.name for f in log._logfiles_to_check()]
        self.assertEqual(files, [u'data/var/log/dpkg.log'])

    def test_read_files(self):
        
        class mock_file(object):
            def __iter__(self):
                for i in range(10):
                    yield str(i)
        
        log = DpkgHistory(var_location="data/var/", since = datetime(2013, 8, 01, 19, 53, 46))
        
        filelist = [mock_file(), mock_file(), mock_file()]
        lines = []
        for l in log._read_files(filelist):
            lines.append(l)
        expected = [str(i) for i in range(10) * 3]
        self.assertEqual(lines, expected)
        
        filelist = [mock_file()]
        lines = []
        for l in log._read_files(filelist):
            lines.append(l)
        expected = [str(i) for i in range(10)]
        self.assertEqual(lines, expected)

    def no_repeats(self, log):
        oplists = defaultdict(list)
        for op, pkgs in log.iteritems():
            for p in pkgs:
                oplists[op].append(p[0])
        for op in oplists.keys():
            for p in oplists[op]:
                for op2 in oplists.keys():
                    if op == op2: continue
                    self.assertFalse(p in oplists[op2])

    def lists_are_sorted(self):
        log = DpkgHistory(var_location="data/var/", 
                since = "2012-05-03 12:20:00")
        for v in log.values():
            self.assertEqual(v, sorted(v))
    
    def test_history_log(self):
        log = DpkgHistory(var_location="data/var/", 
                since = datetime(2013, 8, 01, 19, 53, 46))
        self.no_repeats(log)
        # These counts and those below have been meticulously verified
        total_installs = len(log['install']) + len(log['auto-install'])
        self.assertEqual(total_installs, 311)
        self.assertEqual(len(log['upgrade']), 47)
        self.assertEqual(len(log['remove']), 0)
        self.assertEqual(len(log['purge']), 0)
        self.lists_are_sorted()
        
    def test_history_log_longer(self):
        log = DpkgHistory(var_location="data/var/", 
                since = datetime(2012, 5, 3, 12, 20, 00))
        self.no_repeats(log)
        total_installs = len(log['install']) + len(log['auto-install'])
        self.assertEqual(total_installs, 741)
        self.assertEqual(len(log['upgrade']), 487)
        self.assertEqual(len(log['remove']), 68)
        self.assertEqual(len(log['purge']), 65)
        self.lists_are_sorted()
        
    def test_history_log_shorter(self):
        log = DpkgHistory(var_location="data/var/", 
                since = datetime(2013, 8, 6, 12, 20, 00))
        self.no_repeats(log)
        total_installs = len(log['install']) + len(log['auto-install'])
        self.assertEqual(total_installs, 17)
        self.assertEqual(len(log['upgrade']), 0)
        self.assertEqual(len(log['remove']), 0)
        self.assertEqual(len(log['purge']), 0)
        self.lists_are_sorted()

    def test_auto_installed_list(self):
        log = DpkgHistory(var_location="data/var/", 
                since = datetime(2013, 8, 6, 12, 20, 00))
        self.assertEqual(len(log.auto), 312)
        self.assertNotIn("gcc-4.6-base", log.auto)
        self.assertIn("gcc-4.6-base:i386", log.auto)

    def test_auto_installed_separation(self):
        log = DpkgHistory(var_location="data/var/", 
                since = datetime(2013, 8, 6, 12, 20, 00))
        self.assertIn('auto-install', log.keys())
        self.assertEqual(len(log['install']), 10)
        self.assertEqual(len(log['auto-install']), 7)
        expected = [(u'lib32asound2', u'1.0.25-1ubuntu10.2'), (u'lib32z1', u'1:1.2.3.4.dfsg-3ubuntu4'), (u'libc6-i386', u'2.15-0ubuntu10.4'), (u'linux-headers-3.8.0-27', u'3.8.0-27.40~precise3'), (u'linux-headers-3.8.0-27-generic', u'3.8.0-27.40~precise3'), (u'lynx-cur', u'2.8.8dev.9-2ubuntu0.12.04.1'), (u'python-gpgme', u'0.2-1')]
        self.assertEqual(log['auto-install'], expected)


if __name__ == "__main__":
    unittest.main()
