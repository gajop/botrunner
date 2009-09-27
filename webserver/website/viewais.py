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
from core import *

dbconnection.connectdb()

loginhelper.processCookie()

menu.printPageTop()

ais = dbconnection.querytomaplist( "select ai_name, ai_version, ai_downloadurl from ais", ('ai_name','ai_version', 'ai_downloadurl' ) )

print "<h3>AILadder - AI List</h3>"

print "<table border='1' padding='3'>" \
"<tr class='tablehead'><td>AI Name</td><td>AI Version</td><td>Compatible Options</td><td>Download url</td></tr>"

for ai in ais:
   print "<tr>"
   print "<td><a href='viewai.py?ainame=" + ai['ai_name'] + "&aiversion=" + ai['ai_version'] + "'>" + ai['ai_name'] + "</a></td>"
   print "<td>" + ai['ai_version'] + "</td>"

   print "<td>"
   options = dbconnection.querytolistwithparams("select option_name "\
      " from aioptions, ai_allowedoptions, ais " \
      " where aioptions.option_id = ai_allowedoptions.option_id "\
      " and ai_allowedoptions.ai_id = ais.ai_id "\
      " and ais.ai_name = %s "\
      " and ais.ai_version = %s ",
      ( ai['ai_name'], ai['ai_version'] ) )
   print ' '.join( options )
   print "</td>"

   print "<td><a href='" + ai['ai_downloadurl'] + "'>" + ai['ai_downloadurl'] + "</a></td>"
   print "</tr>"

print "</table>"

if loginhelper.gusername != '':

   print "<p />"
   print "<hr />"
   print "<p />"

   print "<h4>Register new AI:</h4>"
   print "Note that the AI name is case-sensitive.<p />"
   print "Download url should be for a file in .tgz .tar.gz or .tar.bz2 format.<p />"
   print "<form action='addai.py' method='post'>" \
   "<table border='1' padding='3'>" \
   "<tr><td>AI name</td><td><input name='ainame'</td></tr>" \
   "<tr><td>AI version</td><td><input name='aiversion'</td></tr>" \
   "<tr><td>Download url</td><td><input name='downloadurl'</td></tr>" \
   "<tr><td></td><td><input type='submit' value='Add' /></td></tr>" \
   "</table>" \
   "</form>" 


#print "</body>" \
#"</html>"

menu.printPageBottom()

dbconnection.disconnectdb()


