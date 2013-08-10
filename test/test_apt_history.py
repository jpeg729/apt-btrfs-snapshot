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
from datetime import datetime

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from AptHistory import AptHistoryLog, AptHistoryEntry


class TestAptHistoryLog(unittest.TestCase):

    def setUp(self):
        self.log = AptHistoryLog(location="data/var/log", after = datetime(2013, 05, 15, 00, 06, 10))

    def test_history_log(self):
        self.assertEqual(self.log[0].__repr__(), "")
        self.assertEqual(self.log[1].__repr__(), "")
        self.assertEqual(self.log[2].__repr__(), "")
        self.assertEqual(self.log[3].__repr__(), "")
        
    def test_history_log_dicts(self):
        dictkv, auto = self.log[3].i
        self.assertEqual(dictkv.keys(), [u'python-qt4-dbus', u'python-qt4'])
        self.assertEqual(auto.keys(), [u'libqt4-designer', u'libqt4-help', u'python-sip', u'libqt4-test', u'libqtwebkit4:i386', u'libqtassistantclient4', u'libqt4-scripttools'])

    def test_history_before_after(self):
        log = AptHistoryLog(location="data/var/log", 
                            before = datetime(2013, 05, 22, 0, 6, 30),
                            after = datetime(2013, 05, 16, 23, 55, 45))
        self.assertEqual(log[0].__repr__(), "")

    @unittest.expectedFailure
    def test_consolidate(self):
        combined_entry = self.log.consolidate()
        self.assertIsInstance(combined_entry, AptHistoryEntry)
        
        
if __name__ == "__main__":
    unittest.main()
