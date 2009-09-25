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

import cgitb; cgitb.enable()

from utils import *

dbconnection.connectdb()

loginhelper.processCookie()

print "Content-type: text/html"
print ""
print ""

maps = dbconnection.querytomaplist( "select map_name, map_hash from maps", ('map_name','map_hash' ) )

print "<html>" \
"<head>" \
"<title>AILadder - Map List</title>" \
"</head>" \
"<body>" \
"<h3>AILadder - Map List</h3>" \
"<table border='1' padding='3'>" \
"<tr><td>Map name</td><td>Map hash</td></tr>"

for map in maps:
   print "<tr><td>" + map['map_name'] + "</td><td>" + map['map_hash'] + "</td></tr>"

print "</table>"

if loginhelper.gusername != '':
   print "<p />"
   print "<hr />"
   print "<p />"

   print "<h4>Register new map:</h4>"
   print "Note: the mapname and the maphash should be set to whatever is used "
   print "in the startscript, so an easy way to get them is to start a game "
   print "from the lobby, then look at the file 'script.txt' in the spring "
   print "game directory<p />"
   print "<form action='addmap.py' method='post'>" \
   "<table border='1' padding='3'>" \
   "<tr><td>Map name</td><td><input name='mapname'</td></tr>" \
   "<tr><td>Map hash</td><td><input name='maphash'</td></tr>" \
   "<tr><td></td><td><input type='submit' value='Add' /></td></tr>" \
   "</table>" \
   "</form>" \


print "</body>" \
"</html>"

dbconnection.disconnectdb()


