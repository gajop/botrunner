#!/usr/bin/python

# Copyright Hugh Perkins 2009
# hughperkins@gmail.com http://manageddreams.com
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
#  more details.
#
# You should have received a copy of the GNU General Public License along
# with this program in the file licence.txt; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-
# 1307 USA
# You can find the licence also on the web at:
# http://www.opensource.org/licenses/gpl-license.php
#

# carry out some basic diagnostics

import cgitb; cgitb.enable()
import datetime
import sys
import os

from utils import *
from core import *

import config

scriptdir = os.path.dirname( os.path.realpath( __file__ ) )

# carry out some verification checks on the installation
def runchecks():
   print "<p>Checking replays directory...</p>"

   # check replays directory is writable
   if not os.path.exists(scriptdir + "/replays"):
      try:
         os.makedirs( scriptdir + "/replays" )
      except:
         print "Cannot create 'replays' directory in website directory.  Please create the 'replays' directory in the website directory, and ensure it is writable"
         return False
   # if we got here, replays directory exists, check writable...
   testfilepath = scriptdir + "/replays/~test"
   if os.path.exists( testfilepath ):
      try:
         os.remove( testfilepath )
      except:
         print str(sys.exc_value) + "<br />"
      if os.path.exists( testfilepath ):  
         print "Cannot delete old testfile from 'replays' directory on website.  Please check that the 'replays' directory in the website directory is writable, and then try again."
         return False

   try:
      filehelper.writeFile( testfilepath, "foo" )
   except:
      print str(sys.exc_value) + "<br /><br />"

   if not os.path.exists( testfilepath ):  
      print "Please check that the 'replays' directory in the website directory is writable, and then try again."
      return False

   os.remove( testfilepath )

   print "<p> ... replays directory exists and is writable.  PASS.</p>"

   return True

def go():
   print "<h3>Diagnostics</h3>"

   print "<p>This page carries out some basic diagnostics to check the health of your AILadder website.</p>"

   if runchecks():
      print "<p>All checks PASSED</p>"
   else:
      print "<p>Issues were found.  Please check these issues and try again.</p>"

dbconnection.connectdb()

loginhelper.processCookie()

menu.printPageTop()

go()

menu.printPageBottom()

dbconnection.disconnectdb()


