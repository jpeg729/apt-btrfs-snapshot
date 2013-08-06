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

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from AptHistory import AptHistoryLog


class TestFstab(unittest.TestCase):

    def test_history_log(self):
        log = AptHistoryLog(location="data", show_versions=False)
        self.assertEqual(log[0].__repr__(), "<AptHistoryEntry ' 2013-05-16  23:52:45' ' 2013-05-16  23:55:44' ' kde-l10n-fr:amd64 (4.10.2-0ubuntu1, automatic), language-pack-gnome-fr:amd64 (13.04+20130418), language-pack-fr-base:amd64 (13.04+20130418, automatic), hunspell-fr:amd64 (3.3.0-2ubuntu3), calligra-l10n-fr:amd64 (2.6.3-0ubuntu1), language-pack-gnome-fr-base:amd64 (13.04+20130418, automatic), gimp-help-common:amd64 (2.6.1-1, automatic), firefox-locale-fr:amd64 (21.0+build2-0ubuntu0.13.04.2, automatic), gimp-help-en:amd64 (2.6.1-1), gimp-help-fr:amd64 (2.6.1-1), wfrench:amd64 (1.2.3-10), wbritish:amd64 (7.1-1), language-pack-fr:amd64 (13.04+20130418)' ' firefox-locale-en:amd64 (20.0+build1-0ubuntu2, 21.0+build2-0ubuntu0.13.04.2)' '' ''>")
        self.assertEqual(log[1].__repr__(), "<AptHistoryEntry ' 2013-05-16  23:57:19' ' 2013-05-16  23:58:34' '' '' '' ' casper:amd64 (1.331), sbsigntool:amd64 (0.6-0ubuntu2), gir1.2-timezonemap-1.0:amd64 (0.4.0), ubuntustudio-live-settings:amd64 (0.43), libtimezonemap1:amd64 (0.4.0), lvm2:amd64 (2.02.95-6ubuntu4), libdmraid1.0.0.rc16:amd64 (1.0.0.rc16-4.2ubuntu1), libdebconfclient0:amd64 (0.181ubuntu1), python3-cairo:amd64 (1.10.0+dfsg-3~exp3ubuntu1), jfsutils:amd64 (1.1.15-2ubuntu1), kpartx-boot:amd64 (0.4.9-3ubuntu7), gparted:amd64 (0.12.1-2), gir1.2-json-1.0:amd64 (0.15.2-0ubuntu1), python3-gi-cairo:amd64 (3.8.0-2), ubiquity-frontend-gtk:amd64 (2.14.6), ubiquity:amd64 (2.14.6), user-setup:amd64 (1.47ubuntu1), kpartx:amd64 (0.4.9-3ubuntu7), rdate:amd64 (1.2-5), gir1.2-appindicator3-0.1:amd64 (12.10.1daily13.04.15-0ubuntu1), python3-pyicu:amd64 (1.4-1ubuntu3), xfsprogs:amd64 (3.1.9), ubiquity-ubuntu-artwork:amd64 (2.14.6), libdebian-installer4:amd64 (0.85ubuntu3), ubiquity-slideshow-ubuntustudio:amd64 (70), apt-clone:amd64 (0.3.1~ubuntu4), localechooser-data:amd64 (2.49ubuntu4), ubiquity-casper:amd64 (1.331), lupin-casper:amd64 (0.53), reiserfsprogs:amd64 (3.6.21-1build2), dpkg-repack:amd64 (1.37), cifs-utils:amd64 (5.5-1ubuntu2), archdetect-deb:amd64 (1.92ubuntu1), dmraid:amd64 (1.0.0.rc16-4.2ubuntu1), watershed:amd64 (7), gir1.2-xkl-1.0:amd64 (5.2.1-1ubuntu2)'>")
        self.assertEqual(log[2].__repr__(), "<AptHistoryEntry ' 2013-05-22  00:06:10' ' 2013-05-22  00:06:29' '' '' ' nvidia-common:amd64 (0.2.76), libupnp6:amd64 (1.6.17-1.2), libssh2-1:amd64 (1.4.2-1.1), jockey-common:amd64 (0.9.7-0ubuntu13), python-xkit:amd64 (0.5.0ubuntu1)' ' steam-launcher:amd64 (1.0.0.39)'>")
        
if __name__ == "__main__":
    unittest.main()
