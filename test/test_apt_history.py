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
        self.log = AptHistoryLog(location="data", after = datetime(2013, 05, 15, 00, 06, 10))

    def test_history_log(self):
        self.assertEqual(self.log[0].__repr__(), "<AptHistoryEntry '2013-05-16 23:52:45' '2013-05-16 23:55:44' '({u'hunspell-fr': u'3.3.0-2ubuntu3', u'calligra-l10n-fr': u'2.6.3-0ubuntu1', u'language-pack-gnome-fr': u'13.04+20130418', u'wfrench': u'1.2.3-10', u'language-pack-fr': u'13.04+20130418', u'gimp-help-en': u'2.6.1-1', u'gimp-help-fr': u'2.6.1-1', u'wbritish': u'7.1-1'}, {u'language-pack-fr-base': u'13.04+20130418', u'language-pack-gnome-fr-base': u'13.04+20130418', u'kde-l10n-fr': u'4.10.2-0ubuntu1', u'gimp-help-common': u'2.6.1-1', u'firefox-locale-fr': u'21.0+build2-0ubuntu0.13.04.2'})' '({u'firefox-locale-en': u'20.0+build1-0ubuntu2, 21.0+build2-0ubuntu0.13.04.2'}, {})' '({}, {})' '({}, {})'>")
        self.assertEqual(self.log[1].__repr__(), "<AptHistoryEntry '2013-05-16 23:57:19' '2013-05-16 23:58:34' '({}, {})' '({}, {})' '({}, {})' '({u'xfsprogs': u'3.1.9', u'lvm2': u'2.02.95-6ubuntu4', u'ubiquity-ubuntu-artwork': u'2.14.6', u'casper': u'1.331', u'dpkg-repack': u'1.37', u'dmraid': u'1.0.0.rc16-4.2ubuntu1', u'ubiquity': u'2.14.6', u'kpartx-boot': u'0.4.9-3ubuntu7', u'lupin-casper': u'0.53', u'python3-pyicu': u'1.4-1ubuntu3', u'ubiquity-casper': u'1.331', u'libtimezonemap1': u'0.4.0', u'gir1.2-json-1.0': u'0.15.2-0ubuntu1', u'user-setup': u'1.47ubuntu1', u'ubuntustudio-live-settings': u'0.43', u'gparted': u'0.12.1-2', u'sbsigntool': u'0.6-0ubuntu2', u'kpartx': u'0.4.9-3ubuntu7', u'archdetect-deb': u'1.92ubuntu1', u'gir1.2-timezonemap-1.0': u'0.4.0', u'localechooser-data': u'2.49ubuntu4', u'python3-gi-cairo': u'3.8.0-2', u'libdebconfclient0': u'0.181ubuntu1', u'libdebian-installer4': u'0.85ubuntu3', u'ubiquity-slideshow-ubuntustudio': u'70', u'rdate': u'1.2-5', u'libdmraid1.0.0.rc16': u'1.0.0.rc16-4.2ubuntu1', u'cifs-utils': u'5.5-1ubuntu2', u'reiserfsprogs': u'3.6.21-1build2', u'apt-clone': u'0.3.1~ubuntu4', u'watershed': u'7', u'python3-cairo': u'1.10.0+dfsg-3~exp3ubuntu1', u'jfsutils': u'1.1.15-2ubuntu1', u'ubiquity-frontend-gtk': u'2.14.6', u'gir1.2-xkl-1.0': u'5.2.1-1ubuntu2', u'gir1.2-appindicator3-0.1': u'12.10.1daily13.04.15-0ubuntu1'}, {})'>")
        self.assertEqual(self.log[2].__repr__(), "<AptHistoryEntry '2013-05-22 00:06:10' '2013-05-22 00:06:29' '({}, {})' '({}, {})' '({u'jockey-common': u'0.9.7-0ubuntu13', u'python-xkit': u'0.5.0ubuntu1', u'libupnp6': u'1.6.17-1.2', u'nvidia-common': u'0.2.76', u'libssh2-1': u'1.4.2-1.1'}, {})' '({u'steam-launcher': u'1.0.0.39'}, {})'>")
        self.assertEqual(self.log[3].__repr__(), "<AptHistoryEntry '2013-08-02 00:24:05' '2013-08-02 00:30:00' '({u'python-qt4-dbus': u'4.9.1-2ubuntu1', u'python-qt4': u'4.9.1-2ubuntu1'}, {u'libqt4-designer': u'4.8.1-0ubuntu4.4', u'libqt4-help': u'4.8.1-0ubuntu4.4', u'python-sip': u'4.13.2-1', u'libqt4-test': u'4.8.1-0ubuntu4.4', u'libqtwebkit4:i386': u'2.2.1-1ubuntu4', u'libqtassistantclient4': u'4.6.3-3ubuntu2', u'libqt4-scripttools': u'4.8.1-0ubuntu4.4'})' '({u'libpulse0': u'1.1-0ubuntu15.3, 1.1-0ubuntu15.3+1', u'libpulse0:i386': u'1.1-0ubuntu15.3, 1.1-0ubuntu15.3+1', u'pulseaudio-utils': u'1.1-0ubuntu15.3, 1.1-0ubuntu15.3+1'}, {})' '({}, {})' '({}, {})'>")
        
    def test_history_log_dicts(self):
        dictkv, auto = self.log[3].i
        self.assertEqual(dictkv.keys(), [u'python-qt4-dbus', u'python-qt4'])
        self.assertEqual(auto.keys(), [u'libqt4-designer', u'libqt4-help', u'python-sip', u'libqt4-test', u'libqtwebkit4:i386', u'libqtassistantclient4', u'libqt4-scripttools'])

    def test_history_before_after(self):
        log = AptHistoryLog(location="data/logs", 
                            before = datetime(2013, 05, 22, 0, 6, 30),
                            after = datetime(2013, 05, 16, 23, 55, 45))
        self.assertEqual(log[0].__repr__(), "<AptHistoryEntry '2013-05-16 23:57:19' '2013-05-16 23:58:34' '({}, {})' '({}, {})' '({}, {})' '({u'xfsprogs': u'3.1.9', u'lvm2': u'2.02.95-6ubuntu4', u'ubiquity-ubuntu-artwork': u'2.14.6', u'casper': u'1.331', u'dpkg-repack': u'1.37', u'dmraid': u'1.0.0.rc16-4.2ubuntu1', u'ubiquity': u'2.14.6', u'kpartx-boot': u'0.4.9-3ubuntu7', u'lupin-casper': u'0.53', u'python3-pyicu': u'1.4-1ubuntu3', u'ubiquity-casper': u'1.331', u'libtimezonemap1': u'0.4.0', u'gir1.2-json-1.0': u'0.15.2-0ubuntu1', u'user-setup': u'1.47ubuntu1', u'ubuntustudio-live-settings': u'0.43', u'gparted': u'0.12.1-2', u'sbsigntool': u'0.6-0ubuntu2', u'kpartx': u'0.4.9-3ubuntu7', u'archdetect-deb': u'1.92ubuntu1', u'gir1.2-timezonemap-1.0': u'0.4.0', u'localechooser-data': u'2.49ubuntu4', u'python3-gi-cairo': u'3.8.0-2', u'libdebconfclient0': u'0.181ubuntu1', u'libdebian-installer4': u'0.85ubuntu3', u'ubiquity-slideshow-ubuntustudio': u'70', u'rdate': u'1.2-5', u'libdmraid1.0.0.rc16': u'1.0.0.rc16-4.2ubuntu1', u'cifs-utils': u'5.5-1ubuntu2', u'reiserfsprogs': u'3.6.21-1build2', u'apt-clone': u'0.3.1~ubuntu4', u'watershed': u'7', u'python3-cairo': u'1.10.0+dfsg-3~exp3ubuntu1', u'jfsutils': u'1.1.15-2ubuntu1', u'ubiquity-frontend-gtk': u'2.14.6', u'gir1.2-xkl-1.0': u'5.2.1-1ubuntu2', u'gir1.2-appindicator3-0.1': u'12.10.1daily13.04.15-0ubuntu1'}, {})'>")

    def test_consolidate(self):
        combined_entry = self.log.consolidate()
        self.assertIsInstance(combined_entry, AptHistoryEntry)
        
        
if __name__ == "__main__":
    unittest.main()
