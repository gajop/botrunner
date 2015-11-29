#!/usr/bin/python3

# Copyright Hugh Perkins 2009
# hughperkins@gmail.com http://manageddreams.com
#
# Copyright Gajo Petrovic 2015
# gajopetrovic@gmail.com http://github.com/gajop
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
# =============================================================================
#


import time
import urllib.request, urllib.parse, urllib.error
import subprocess
import os
import sys
import io
from xml.dom import minidom
import tarfile
import base64
import xmlrpc.client
from optparse import OptionParser
import traceback
import imp
import psutil
import threading
import shutil
import logging

from unitsync import unitsync as unitsyncpkg

from utils import *
from multicall import MultiCall
version = None
try:
    import version
except:
    pass


config = None
unitsync = None
writableDataDirectory = None
numinstances = 0
matches = []
numinstanceslock = threading.Lock()

instanceids = 0
instanceidslock = threading.Lock()

unitsynclock = threading.Lock()

scriptdir = os.path.dirname(os.path.realpath(__file__))

options = {}
args = {}


class GameRunner(threading.Thread):
    def __init__(self, host, serverRequest):
        self.serverRequest = serverRequest
        self.host = host
        global instanceids, instanceidslock
        instanceidslock.acquire()
        self.instanceid = instanceids
        instanceids += 1
        instanceidslock.release()
        threading.Thread.__init__(self)

    def run(self):
        try:
            result = runGame(self.serverRequest, self.instanceid)
            uploadResults(self.host, self.serverRequest, result,
                    self.instanceid)
        except:
            logging.error("Something went wrong with botrunner, " +\
                    "not uploading to server")
            traceback.print_exc()
        global numinstances
        global numinstanceslock
        numinstanceslock.acquire()
        numinstances -= 1
        global writableDataDirectory
        datadir = writableDataDirectory + "tmpdir" + str(self.instanceid) + "/"
        scriptName = "script" + str(self.instanceid) + ".txt"
        # FIXME: Removing old files is temporary disabled as there are 0 byte replay uploads happening.
        #if os.path.exists(datadir):
            #shutil.rmtree(datadir)
        if os.path.exists(writableDataDirectory + scriptName):
            os.remove(writableDataDirectory + scriptName)
        matches.remove(self.serverRequest['matchrequest_id'])
        numinstanceslock.release()


def parseopts():
    global sessionid, options, args

    parser = OptionParser()
    parser.add_option("--sessionid",
            help='force sessionid to specific string', dest='sessionid')
    parser.add_option("--target-web-site",
            help='website we should subscribe to', dest='targetwebsite')
    parser.add_option("--botrunner-name", help='botrunner-name',
            dest='botrunnername')
    parser.add_option("--botrunner-shared-secret",
            help='botrunner shared secret', dest='botrunnersharedsecret')
    parser.add_option("--spring-source-path", help='path to spring source',
            dest='springsourcepath')
    parser.add_option("--spring-path", help='path to spring executable',
            dest='springpath')
    parser.add_option("--unitsync-path", help='path to unitsync library',
            dest='unitsyncpath')
    parser.add_option("--downloading-ok", help='ok to download AIs',
            dest='downloadingok', action='store_true')
    parser.add_option("--yes", help='automatically confirm', dest='yes',
            action='store_true')
    parser.add_option("--configpath", help='path to configfile ' +\
            '(default: config.py).  Note: must already exist.',
            dest='configpath')
    parser.add_option("--no-register-capabilities",
            help='do not register maps, mods or ais with web service',
            dest='noregistercapabilities', action='store_true')
    parser.add_option("--version", '-V', help='show version', dest='version',
            action='store_true')

    (options, args) = parser.parse_args()

    sessionid = options.sessionid


def requestgamefromwebserver(host):
    global sessionid
    try:
        [result, serverRequest] = getxmlrpcproxy(host).getrequest(
                config.botrunnername, config.sharedsecret, sessionid)
        if not result:
            logging.error("Something went wrong: " + serverRequest)
            return None

        if len(serverRequest) == 0:
            return None
        logging.info("got request, matchrequestid = " +\
                str(serverRequest[0]['matchrequest_id']))
        return serverRequest[0]  # can't handle passing None in python 2.4
    except:
        logging.error("Something went wrong: " + str(sys.exc_info()))
        traceback.print_exc()
        return None


# return xmlrpcproxy to communicate with web server
def getxmlrpcproxy(host):
    return xmlrpc.client.ServerProxy(uri=host)


# returns true if there is at least one host pinging ok
def ping(status):
    global sessionid
    atleastonehostsucceeded = False
    for host in config.websiteurls:
        try:
            logging.info("pinging " + host + " ...")
            getxmlrpcproxy(host).ping(
                    config.botrunnername, config.sharedsecret,
                    sessionid, status)
            atleastonehostsucceeded = True
        except Exception as e:
            logging.error("Failed to ping " + host)
            logging.error(e)
    return atleastonehostsucceeded


def getReplayPath(infologContents):
    splitlines = infologContents.split("\n")
    for line in splitlines:
        if line.find("Recording demo to: ") != -1:
            demopath = line.split("Recording demo to: ")[1]
            logging.info("demo path: [" + demopath + "]")
            return demopath
    return None


def trydownloadingsomething(host):
    global sessionid, config, writableDataDirectory
    try:
        [success, downloadrequestlist] = getxmlrpcproxy(host).\
                getdownloadrequest(config.botrunnername,
                        config.sharedsecret, sessionid)
        if not success:
            logging.info(downloadrequestlist)
            return

        if len(downloadrequestlist) == 0:
            logging.info("Nothing to download from " + host)
            return

        downloadrequest = downloadrequestlist[0]

        logging.info("Got download request: " + str(downloadrequest))
        if 'ai_name' in downloadrequest:
            return downloadai(host, downloadrequest)
        if 'map_name' in downloadrequest:
            return downloadmap(host, downloadrequest)
        if 'mod_name' in downloadrequest:
            return downloadmod(host, downloadrequest)
        logging.warning("Unknown download reqest type: " +\
                str(downloadrequest) +\
                ". Please check you are running the latest botrunner version.")

    except:
        logging.error("something went wrong: " + str(sys.exc_info()) + "\n" +\
                str(traceback.extract_tb(sys.exc_info()[2])))


def downloadmap(host, downloadrequest):
    mapname = downloadrequest['map_name']
    mapurl = downloadrequest['map_url']
    logging.info("Downloading map " + mapname + ' ' + mapurl + ' ...')

    serverRequesthandle = urllib.request.urlopen(mapurl, None)
    data = serverRequestarray = serverRequesthandle.read()
    file = open(writableDataDirectory + mapname, "wb")
    file.write(data)
    file.close()
    os.renames(writableDataDirectory + mapname,
            writableDataDirectory + "maps/" + mapname.split('.')[0] + ".sd7")

    initUnitSync()
    registermapsallhosts()
    return True


def downloadmod(host, downloadrequest):
    modname = downloadrequest['mod_name']
    modurl = downloadrequest['mod_url']
    logging.info("Downloading mod " + modname + ' ' + modurl + ' ...')

    serverRequesthandle = urllib.request.urlopen(modurl, None)
    data = serverRequestarray = serverRequesthandle.read()
    file = open(writableDataDirectory + modname, "wb")
    file.write(data)
    file.close()
    # need to rename it to .sd7, otherwise unitsync won't find it
    os.renames(writableDataDirectory + modname,
            writableDataDirectory + "mods/" +\
                    modname.replace(" ", "_") + ".sd7")

    initUnitSync()
    registermodsallhosts()
    return True


def downloadai(host, downloadrequest):
    global config, writableDataDirectory

    ai_name = downloadrequest['ai_name']
    ai_version = downloadrequest['ai_version']
    logging.info("Downloading ai " + str(downloadrequest))

    needscompiling = downloadrequest['ai_needscompiling']
    # ok, so we'll download it  to .... writableDataDirectory?
    # then use tar to extract it to .... the writableDataDirectory/AI ?
    # start by retrieving it:
    serverRequesthandle = urllib.request.urlopen(downloadrequest['ai_downloadurl'],
            None)
    downloadfilename = os.path.basename(downloadrequest['ai_downloadurl'])
    data = serverRequestarray = serverRequesthandle.read()
    file = open(writableDataDirectory + downloadfilename, "wb")
    file.write(data)
    file.close()

    extractdir = writableDataDirectory + "/extractdir"
    # should think about purgging the old directory...

    if not os.path.exists(extractdir):
        os.makedirs(extractdir)

    tar = tarfile.open(writableDataDirectory + downloadfilename)
    tar.extractall(extractdir)
    tar.close()
    os.remove(writableDataDirectory + downloadfilename)

    # java ai most likely, or some other scripted/bytecode ai
    if not needscompiling:
        # look for a directory with the name $ai_name/$ai_version
        sourcepath = None
        for root, dirs, files in os.walk(extractdir):
            possibledirs = [ai_name + "/" + ai_version,
                    ai_name + "\\" + ai_version]
            for possibledir in possibledirs:
                if root.find(possibledir) != -1:
                    sourcepath = root.split(possibledir)[0] + possibledir
                    break
            if sourcepath != None:
                break

        if sourcepath == None:
            logging.error("Failed to find ai in download")
            return

        logging.info("ai sourcepath: " + sourcepath)

        aiinfopath = sourcepath + "/AIInfo.lua"
        if not os.path.exists(aiinfopath):
            logging.warning("No AIAinfo.lua found, so aborting")
            return

        try:
            aiinfodict = aiinfoparser.parse(aiinfopath)
        except:
            logging.warning("Failed to parse AIInfo.lua, aborting " +\
                    str(sys.exc_info()) + "\n" +\
                    str(traceback.extract_tb(sys.exc_info()[2])))
            return

        if not 'shortName' in aiinfodict or not 'version' in aiinfodict:
            logging.warning("AIInfo.lua does not appear to contain shortName " +\
                    "or version -> aborting")
            return

        if ai_name != aiinfodict['shortName'] or\
                ai_version != aiinfodict['version']:
            logging.warning("shortName (" + aiinfodict['shortName'] +\
                    ") or version (" + aiinfodict['version'] +\
                    ") contained in AIInfo.lua do not match " +\
                    "requested download AI (" + ai_name + ", " +\
                    ai_version + ") -> aborting")
            return

        targetpath = config.aiinstallationdirectory + "/Skirmish/" +\
                ai_name + "/" + ai_version
        if not os.path.exists(targetpath):
            os.makedirs(targetpath)

        # copy the files across...
        filehelper.rsyncav(sourcepath, targetpath)

    else:  # needs compiling, probably a C++ AI
        # now what...
        # compile it first I guess :-P
        # assume we have a c compiler to hand and stuff
        # (we could make that configurable later)
        # ok, we will copy it into a subdirectory of
        # AI/Skirmish in the spring source
        # with the name of the AI
        # then we will run 'ccmake ..' from the build directory,
        # then 'make <ainame>'
        # we should probably remove any directory for that AI currently
        # in the spring source
        # then copy the directory we just unpacked exactly to that AI's
        # name in the AI/Skirmish
        # directory
        # sanity check: we will check there is a VERSION file,
        # and that is how we will determine
        # which directory to copy
        sourcepath = None
        for root, dirs, files in os.walk(extractdir):
            if 'VERSION' in files:
                sourcepath = root.split('VERSION')[0]

        if sourcepath == None:
            logging.warning("Failed to find ai in download, " +\
                    "ie we failed to find a file called VERSION.")
            return

        aitargetsourcedir = config.springSourcePath + "/AI/Skirmish/" + ai_name
        filehelper.rmdirrecursive(aitargetsourcedir)
        filehelper.rsyncav(sourcepath, aitargetsourcedir)

        # now, do a 'make install' on spring source, and cross-fingers :-P
        logging.info("launching make install for " + ai_name + " ...")
        os.chdir(config.springSourcePath + '/build')
        process = subprocess.Popen(['cmake', '..'])
        process.wait()
        # note: calling 'make' directly is not very portable
        process = subprocess.Popen(['make', ai_name])
        process.wait()
        logging.info("ai build finished finished")
        # run 'cmake -P AI/Skirmish/<ainame>/cmake_install.cmake'
        # to install the AI
        process = subprocess.Popen(['cmake', '-P', 'AI/Skirmish/' +\
                ai_name + '/cmake_install.cmake'])
        process.wait()
        logging.info("ai installed")

    # so it is installed....
    # rerun unitsync I guess?

    initUnitSync()
    registeraisallhosts()

    # tell base we're finished...
    getxmlrpcproxy(host).finisheddownloadingai(config.botrunnername,
            config.sharedsecret, sessionid, ai_name, ai_version)

    return True

def stopProcess(process):
    printError = process.poll() != None
    try:
        # first wait on the process to close itself
        if process.poll() == None:
            waitTime = 30
            logging.info("Waiting " + str(waitTime) + " seconds for Spring to close itself")
            while process.poll() == None and waitTime > 0:
                time.sleep(1)
                waitTime = waitTime - 1
        # then send a .terminate() and wait some more
        if process.poll() == None:
            waitTime = 30
            logging.info("Sending terminate and waiting " + str(waitTime) + " seconds for Spring to close")
            process.terminate()
            while process.poll() == None and waitTime > 0:
                time.sleep(1)
                waitTime = waitTime - 1
        # then just kill it
        process.kill()
    except:
        if printError:
            logging.error("Failed stopping the process")
            traceback.print_exc()

def runGame(serverRequest, instanceid):
    global config, writableDataDirectory, unitsynclock
    hasCustomTemplate = False
    customTemplateFile = scriptdir + "/script_templates/" + serverRequest['map_name'] + ".txt"
    if os.path.exists(customTemplateFile):
        hasCustomTemplate = True
        logging.info("There is a custom template for the map.")
        scripttemplatecontents = filehelper.readFile(customTemplateFile)
    else:
        scripttemplatecontents = filehelper.readFile(
            scriptdir + "/" + config.scripttemplatefilename)

    scriptContents = scripttemplatecontents
    scriptContents = scriptContents.replace("%MAP%",
            serverRequest['map_name'])
    scriptContents = scriptContents.replace("%MOD%",
            serverRequest['mod_name'])
    scriptContents = scriptContents.replace("%AI0%",
            serverRequest['ai0_name'])
    scriptContents = scriptContents.replace("%AI0VERSION%",
            serverRequest['ai0_version'])
    scriptContents = scriptContents.replace("%AI1%",
            serverRequest['ai1_name'])
    scriptContents = scriptContents.replace("%AI1VERSION%",
            serverRequest['ai1_version'])
    scriptContents = scriptContents.replace("%SPEED%",
            str(serverRequest['speed']))
    scriptContents = scriptContents.replace("%TEAM0SIDE%",
            serverRequest['ai0_side'])
    scriptContents = scriptContents.replace("%TEAM1SIDE%",
            serverRequest['ai1_side'])

    speed = serverRequest['speed']
    softtimeout = serverRequest['softtimeout']
    hardtimeout = serverRequest['hardtimeout']
    unitsynclock.acquire()
    map_info = unitsyncpkg.MapInfo()
    unitsync.GetMapInfoEx(str(serverRequest['map_name']), map_info, 1)
    maphash = unitsync.GetMapChecksumFromName(str(serverRequest['map_name']))
    modhash = unitsync.GetPrimaryModChecksumFromName(str(serverRequest['mod_name']))
    team0startpos = map_info.StartPos[0]
    team1startpos = map_info.StartPos[1]
    unitsynclock.release()
    # we always play team 0 on startpos0 ,and team1 on startpos1,
    # for repeatability
    # it is for the website to decide which team should go on which side,
    # not the botrunner
    if not hasCustomTemplate:
        scriptContents = scriptContents.replace("%TEAM0STARTPOSX%",
            str(team0startpos.x))
        scriptContents = scriptContents.replace("%TEAM0STARTPOSZ%",
            str(team0startpos.y))
        scriptContents = scriptContents.replace("%TEAM1STARTPOSX%",
            str(team1startpos.x))
        scriptContents = scriptContents.replace("%TEAM1STARTPOSZ%",
            str(team1startpos.y))

    scriptContents = scriptContents.replace("%MAPHASH%",
            str(maphash))
    scriptContents = scriptContents.replace("%MODHASH%",
            str(modhash))

    scriptName = "script" + str(instanceid) + ".txt"
    infologname = "tmpdir" + str(instanceid) + "/infolog.txt"
    datadir = writableDataDirectory + "tmpdir" + str(instanceid) + "/"
#t  infologname = "infolog.txt" #need to be able to specify different infologs

    scriptpath = writableDataDirectory + scriptName
    filehelper.writeFile(scriptpath, scriptContents)

    if os.path.exists(datadir):
        shutil.rmtree(datadir)

    if os.path.exists(writableDataDirectory + infologname):
        os.remove(writableDataDirectory + infologname)

    os.chdir(writableDataDirectory)
    existingenv = {}
    for varname in list(os.environ.keys()):
        if os.getenv(varname) != None:
            existingenv[varname] = os.getenv(varname)
    existingenv["SPRING_DATADIR"] = datadir
    if config.JAVA_HOME != None:
        existingenv["JAVA_HOME"] = os.path.dirname(config.JAVA_HOME)
    fnull = None
    if not config.debug:
        fnull = open(os.devnull, 'w')
    if os.name == 'nt':
        try:
            process = subprocess.Popen(
                    [config.springPath, writableDataDirectory + scriptName, "-d " + datadir],
                    env=existingenv, stdout=fnull,
                    stderr=fnull, creationflags=0x40)
            #0x40 sets idle-level process priority for windows
        except:
            logging.info("setting idle process priority failed for nt platform. " +\
                    "trying to start without priority settings")
            process = subprocess.Popen(
                    [config.springPath, writableDataDirectory + scriptName, "-d " + datadir],
                    env=existingenv, stdout=fnull, stderr=fnull)
    else:
        process = subprocess.Popen(
                [config.springPath, writableDataDirectory + scriptName, "-d " + datadir],
                env=existingenv, stdout=fnull, stderr=fnull)
    finished = False
    starttimeseconds = time.time()
    ping("playing game " + serverRequest['ai0_name'] + " vs " +\
            serverRequest['ai1_name'] + " on " + serverRequest['map_name'] +\
            " " + serverRequest['mod_name'])
    lastpingtimeseconds = time.time()
    gameresult = {}
    waitingcount = 0
    while not finished:
        if waitingcount % 30 == 0:
            logging.info("botrunner instance " + str(instanceid) +\
                    ": waiting for game to terminate...")
        waitingcount = waitingcount + 1
        if time.time() - lastpingtimeseconds > config.pingintervalminutes * 60:
            ping("playing game " + serverRequest['ai0_name'] + " vs " +\
                    serverRequest['ai1_name'] + " on " +\
                    serverRequest['map_name'] + " " +\
                    serverRequest['mod_name'])
            lastpingtimeseconds = time.time()
        infologContents = ''  # initialize just in case it doesn't exist yet
        if os.path.exists(writableDataDirectory + infologname):
            infologContents = filehelper.readFile(
                    writableDataDirectory + infologname)
        gameEndString = "Alliance %TEAMNUMBER% wins!"
        ai0endstring = gameEndString.replace(
                "%TEAMNUMBER%", "0")
        ai1endstring = gameEndString.replace(
                "%TEAMNUMBER%", "1")
        if infologContents.find(ai1endstring) != - 1:
            # ai1 won
            logging.info("team 1 won!")
            gameresult['winningai'] = 1
            gameresult['resultstring'] = "ai1won"
            stopProcess(process)
            gameresult['replaypath'] = getReplayPath(infologContents)
            return gameresult
        elif infologContents.find(ai0endstring) != -1:
            # ai0 won
            logging.info("team 0 won!")
            gameresult['winningai'] = 0
            gameresult['resultstring'] = "ai0won"
            stopProcess(process)
            gameresult['replaypath'] = getReplayPath(infologContents)
            return gameresult
        elif infologContents.find("Nobody wins!") != -1:
            # both died...
            logging.info("A draw...")
            gameresult['winningai'] = -1
            gameresult['resultstring'] = "draw"
            stopProcess(process)
            gameresult['replaypath'] = getReplayPath(infologContents)
            return gameresult

        # check timeout in game time:
        infologlines = infologContents.split("\n")
        lastguaranteedinfologline = infologlines[len(infologlines) - 1]
        if lastguaranteedinfologline.find("[") != -1:
            numstring = lastguaranteedinfologline.\
                    split("[")[1].split("]")[0].strip()
            #print(("frame number string: " + numstring))
            try:
                frames = int(numstring)
                logging.info("frames: " + str(frames))
                if frames / 30 > softtimeout * 60:
                    # timeout
                    logging.info("Game timed out")
                    gameresult['winningai'] = -1
                    gameresult['resultstring'] = "gametimeout"
                    stopProcess(process)
                    gameresult['replaypath'] = getReplayPath(infologContents)
                    return gameresult
            except:
                pass

        # check timeout (== draw)
        if (time.time() - starttimeseconds) > hardtimeout * 60.0:  # magic
            # timeout
            logging.info("Game timed out")
            gameresult['winningai'] = -1
            gameresult['resultstring'] = "gametimeout"
            stopProcess(process)
            gameresult['replaypath'] = getReplayPath(infologContents)
            return gameresult

        if process.poll() != None:
            # spring finished / died / crashed
            # presumably if we got here, it crashed,
            # otherwise infolog would have been written
            logging.warning("Crashed")
            stopProcess(process)
            gameresult['winningai'] = -1
            gameresult['resultstring'] = "crashed"
            gameresult['replaypath'] = getReplayPath(infologContents)
            return gameresult

        proc = psutil.Process(process.pid)
        # Backward compatibility
        if proc.get_memory_info:
            rss = proc.get_memory_info()[0]
        else:
            rss = proc.memory_info()[0]
        if rss / (1024 * 1024) > config.maxmemory:
            logging.warning("Killing, it's using too much memory")
            stopProcess(process)
            gameresult['winningai'] = -1
            gameresult['resultstring'] = "crashed"
            gameresult['replaypath'] = getReplayPath(infologContents)
            return gameresult

        time.sleep(1)

    return gameresult


# when spring crashes, the replay is called 'unnamed',
# so we'll grab that file instead
def getreplayfullpath(writableDataDirectory, relativereplaypathfrominfolog):
    if relativereplaypathfrominfolog == None:
        logging.warning("No replay found", relativereplaypathfrominfolog)
        return None

    replayfullpath = writableDataDirectory + relativereplaypathfrominfolog
    if os.path.isfile(replayfullpath):
        return replayfullpath

    demo_folderpath = os.path.dirname(replayfullpath)
#   demo_filename = os.path.basename( replayfullpath )

#   demo_splitunder = demo_filename.split('_')
#   demo_newname = '_'.join(demo_splitunder[:3] +\
#   ['unnamed',] + demo_splitunder[4:])
#   demo_newpath = os.path.join(demo_folderpath, demo_newname)
    demo_newpath = os.path.join(demo_folderpath,
            os.listdir(demo_folderpath)[0])

    if not os.path.isfile(demo_newpath):
        logging.warning("No replay found", demo_newpath)
        return None

    logging.warning('Spring bug: replay is actually named:', demo_newpath)
    return demo_newpath


def uploadResults(host, serverRequest, gameresult, instanceid):
    global writableDataDirectory

    # upload gameresult and serverRequest to server...
    # ...

    # first we should take care of the replay
    infologname = "infolog.txt"
    replaytarname = 'thisreplay' + str(instanceid) + '.tar.bz2'
    infologtarname = 'thisinfolog' + str(instanceid) + '.tar.bz2'
    uploaddatadict = {}  # dict of 'replay': replaydata, etc ...
    datadir = writableDataDirectory + "tmpdir" + str(instanceid) + "/"
    # TODO: getreplayfullpath is probably not needed anymore
    #replaypath = getreplayfullpath(datadir, gameresult['replaypath'])
    replaypath = gameresult['replaypath']

    if replaypath != '' and replaypath != None and os.path.exists(replaypath):
        # first tar.bz2 it
        tarhandle = tarfile.open(datadir + replaytarname, "w:bz2")
        # cd in, so that we don't embed the paths
        os.chdir(os.path.dirname(replaypath))
                     # in the tar file...
        tarhandle.add(os.path.basename(replaypath))
        tarhandle.close()

        # replayfilehandle = open(datadir + replaytarname, 'rb')
        # NOTICE: Using the RAW file for upload
        replayfilehandle = open(replaypath, 'rb')
        replaycontents = replayfilehandle.read()
        replayfilehandle.close()

        logging.info("replay binary length: " + str(len(replaycontents)))
        replaybinarywrapper = xmlrpc.client.Binary(replaycontents)
        uploaddatadict['replay'] = replaybinarywrapper

    # TODO: should move this stuff to a function,
    # but just hacking it in for now to get it working
    if os.path.exists(datadir + infologname):
        # first tar.bz2 it
        tarhandle = tarfile.open(datadir + infologtarname, "w:bz2")
        os.chdir(datadir)
                     # cd in, so that we don't embed the paths
                     # in the tar file...
        tarhandle.add(os.path.basename(infologname))
        tarhandle.close()

        # replayfilehandle = open(datadir + infologtarname, 'rb')
        # NOTICE: Using the RAW file for upload
        replayfilehandle = open(datadir + infologname, 'rb')
        replaycontents = replayfilehandle.read()
        replayfilehandle.close()

        logging.info("infolog binary length: " + str(len(replaycontents)))
        replaybinarywrapper = xmlrpc.client.Binary(replaycontents)
        uploaddatadict['infolog'] = replaybinarywrapper

    requestuploadedok = False
    while not requestuploadedok:
        try:
            (result, errormessage) = getxmlrpcproxy(host).submitresult(
                    config.botrunnername, config.sharedsecret,
                    serverRequest['matchrequest_id'],
                    gameresult['resultstring'], uploaddatadict)
            logging.info("upload result: " + str(result) + " " + errormessage)
            requestuploadedok = True
        except:
            logging.error("Something went wrong uploading to the server: " +\
                    str(sys.exc_info()[1]) + ".\nRetrying ... ")
            time.sleep(5)


def getSpringPath():
    potentialpaths = []
    if os.name == 'posix':
        potentialpaths = ('/usr/games/spring',
                '/usr/games/spring-headlessstubs')
    elif os.name == 'nt':
        potentialpaths = ('C:\Program Files\Spring\spring.exe',
                'C:\Program Files\Spring\spring-headlessstubs.exe')

    return userinput.getPath("the Spring executable", potentialpaths)


def getUnitSyncPath():
    potentialpaths = []
    if os.name == 'posix':
        potentialpaths = ('/usr/lib/spring/unitsync.so',)
    elif os.name == 'nt':
        potentialpaths = ("C:\\Program Files\\Spring\\unitsync.dll",)

    return userinput.getPath("unitsync", potentialpaths)


def setupConfig():
    global config, options

    print(
"""
Welcome to botrunner.
Let's get you set up...""")
    gotdata = False

    while not gotdata:
        print("")
        if options.targetwebsite != None:
            weburl = options.targetwebsite
        else:
            weburl = userinput.getChoice(
                    "Which webserver to you want to subscribe to?",
                    ['manageddreams.com/springgrid',
                        'manageddreams.com/springgridstaging',
                        'localhost/springgrid'], None, None)
            print("")
        if weburl.lower().find("http://") == -1:
            weburl = "http://" + weburl
        if options.botrunnername != None:
            botrunnername = options.botrunnername
        else:
            botrunnername = userinput.getValueFromUser(
                    "What name do you want to give to your botrunner? " +\
                            "This name will be shown on the website.")
            print("")
        if options.botrunnersharedsecret != None:
            botrunnersharedsecret = options.botrunnersharedsecret
        else:
            botrunnersharedsecret = userinput.getValueFromUser(
                "What sharedsecret do you want to use with this botrunner? " +\
                "This will be used to authenticate your botrunner " +\
                "to the website. " +\
                "Just pick something, and remember it.")
            print("")

        if options.springsourcepath != None:
            springSourcePath = options.springsourcepath
        else:
            springSourcePath = userinput.getPath("path to Spring sourcecode",\
                    ['/home/user/springheadless'])
            print(("Spring source path: " + springSourcePath))
            print("")

        if options.springpath != None:
            springPath = options.springpath
        else:
            springPath = getSpringPath()
            if springPath == '':
                print(("Spring executable not found. " +\
                        "Please check that it is installed"))
                return False
            print(("Spring executable found: " + springPath))
            print("")
        if options.unitsyncpath != None:
            unitsyncPath = options.unitsyncpath
        else:
            unitsyncPath = getUnitSyncPath()
            if unitsyncPath == '':
                print("UnitSync not found. Please check that it is installed")
                return False
            print(("UnitSync found: " + unitsyncPath))
            print("")
        if os.getenv('JAVA_HOME') != None:
            JAVA_HOME = os.getenv('JAVA_HOME')
            usejava = True
        else:
            usejava = userinput.getbooleanfromuser(
                    "Do you have Java installed?  " +\
                            "This will increase the number of AIs " +\
                            "this botrunner can run.")
            if usejava:
                print("")
                JAVA_HOME = userinput.getPath(
                        "Appropriate value for JAVA_HOME " +\
                                "(eg /usr/lib/jvm/java-6-sun/jre or " +\
                                "c:\\program files\\sun jdk\\bin\\java)",
                        ['c:\\program files\\sun jdk',
                            '/usr/lib/jvm/java-6-sun/jre'])
            else:
                JAVA_HOME = None
            print("")
        if options.downloadingok:
            downloadingok = True
        else:
            downloadingok = userinput.getbooleanfromuser("""Do you wish to
            enable downloading new AIs, maps and mods?  For your security, you
            should probably only answer yes if you are running the botrunner in
            an isolated environment, such as a VirtualBox instance, a pc you
            don't use for anything else, or an EC2 instance.""")
            print("")
        print("You have input:")
        print(("   target web server: " + weburl))
        print(("   botrunner name: " + botrunnername))
        print(("   botrunner shared secret: " + botrunnersharedsecret))
        print(("   spring source path: " + springSourcePath))
        print(("   spring executable path: " + springPath))
        print(("   UnitSync path: " + unitsyncPath))
        print(("   Enable Java AIs: " + str(usejava)))
        if usejava:
            print(("   JAVA_HOME: " + JAVA_HOME))
        print(("   Downloading ok: " + str(downloadingok)))
        print("")
        if options.yes or userinput.getConfirmation("Is this correct?"):
            gotdata = True

    # that's all we need, let's create the config file...
    # wait, need writable datadirectory from unitsync:

    initUnitSyncWithUnitSyncPath(unitsyncPath)

    templatecontents = filehelper.readFile(scriptdir + "/config.py.template")
    newconfig = templatecontents
    newconfig = newconfig.replace("WEBSITEURL", weburl)
    newconfig = newconfig.replace("BOTRUNNERNAME", botrunnername)
    newconfig = newconfig.replace("SHAREDSECRET", botrunnersharedsecret)
    newconfig = newconfig.replace("SPRINGSOURCEPATH", springSourcePath)
    newconfig = newconfig.replace("SPRINGPATH", springPath)
    newconfig = newconfig.replace("UNITSYNCPATH", unitsyncPath)
    newconfig = newconfig.replace("ALLOWDOWNLOADING", str(downloadingok))
    newconfig = newconfig.replace("AIINSTALLATIONDIRECTORY",
            writableDataDirectory + 'AI')
    newconfig = newconfig.replace("CANCOMPILE", 'False')
    if usejava:
        newconfig = newconfig.replace("$JAVA_HOME", JAVA_HOME)
    else:
        newconfig = newconfig.replace("$JAVA_HOME", "None")
    filehelper.writeFile(scriptdir + "/config.py", newconfig)

    # and import it...
    import config

    return True


def registermaps(host, registeredmaps):
    global unitsynclock
    logging.info(registeredmaps)

    multicall = MultiCall(getxmlrpcproxy(host))
    unitsynclock.acquire()
    for i in range(unitsync.GetMapCount()):
        mapname = unitsync.GetMapName(i).decode("utf-8")
        if registeredmaps.count(mapname) == 0:
            logging.info("registering map " + mapname + " ...")
            unitsync.GetMapArchiveCount(mapname)
            archivename = unitsync.GetMapArchiveName(0)
            #print unitsync.GetMapArchiveName(1)
            archivechecksum = unitsync.GetArchiveChecksum(archivename)
            multicall.registersupportedmap(config.botrunnername,
                    config.sharedsecret, mapname, str(archivechecksum))
    unitsynclock.release()
    results = multicall()
    successcount = 0
    total = 0
    for result in results:
        total = total + 1
        if result[0]:
            successcount = successcount + 1
    if total > 0:
        logging.info(str(successcount) + " successes out of " + str(total))


def registermods(host, registeredmods):
    global unitsynclock
    logging.info(registeredmods)

    multicall = MultiCall(getxmlrpcproxy(host))
    unitsynclock.acquire()
    for i in range(unitsync.GetPrimaryModCount()):
        modname = unitsync.GetPrimaryModName(i).decode("utf-8")
        unitsync.GetPrimaryModArchiveCount(i)
        modarchive = unitsync.GetPrimaryModArchive(i)
        modarchivechecksum = unitsync.GetArchiveChecksum(modarchive)
        unitsync.RemoveAllArchives()
        unitsync.AddAllArchives(modarchive)
        if registeredmods.count(modname) == 0:
            logging.info("registering mod " + modname + " ...")
            logging.info("#Sides: " + str(unitsync.GetSideCount()))
            sides = [unitsync.GetSideName(i).decode("utf-8") for i in
                    range(unitsync.GetSideCount())]
            modarchive = modarchive
            logging.info(sides)
            if len(sides) == 0:
                continue
                unitsynclock.release()
                #raise Exception()
            multicall.registersupportedmod(config.botrunnername,
                    config.sharedsecret, modname, str(modarchivechecksum),
                    sides)
    unitsynclock.release()
    results = multicall()
    successcount = 0
    total = 0
    for result in results:
        total = total + 1
        if result[0]:
            successcount = successcount + 1
        else:
            logging.info(result[1])
    if total > 0:
        logging.info(str(successcount) + " successes out of " + str(total))


def registerais(host, registeredais):
    global unitsynclock
    logging.info("REGISTERING AIs")
    #logging.info(registeredais)

    multicall = MultiCall(getxmlrpcproxy(host))
    registeredaiswehave = []
    # we'll go through this and figure out which ones we don't
    # have,
      # then unregister them
    unitsynclock.acquire()
    for i in range(unitsync.GetSkirmishAICount()):
        shortname = ''
        version = ''
        for j in range(unitsync.GetSkirmishAIInfoCount(i)):
            if unitsync.GetInfoKey(j) == b"shortName":
                shortname = unitsync.GetInfoValue(j).decode("utf-8")
            if unitsync.GetInfoKey(j) == b"version":
                version = unitsync.GetInfoValue(j).decode("utf-8")
        if shortname != '' and version != '':
            if registeredais.count([shortname, version]) == 0:
                logging.info("registering ai " + shortname + " version " + version +\
                        " ...")
                multicall.registersupportedai(config.botrunnername,
                        config.sharedsecret, shortname, version)
            else:
                registeredaiswehave.append([shortname, version])
    unitsynclock.release()

    # HACK for ZK's CAI
    multicall.registersupportedai(config.botrunnername,
                        config.sharedsecret, "CAI", "")
    for shortname, version in registeredais:
        if shortname == "CAI":
            continue
        if registeredaiswehave.count([shortname, version]) == 0:
            logging.info("un-registering ai " + shortname + " version " + version +\
                    " ...")
            multicall.registerunsupportedai(config.botrunnername,
                    config.sharedsecret, shortname, version)

    results = multicall()
    successcount = 0
    total = 0
    for result in results:
        total = total + 1
        if result[0]:
            successcount = successcount + 1
    if total > 0:
        logging.info(str(successcount) + " successes out of " + str(total))


# we do a single multicall to retrieve all registerdd mods, maps and ais
# first, which should speed up launch after initial launch
def registercapabilities(host):
    multicall = MultiCall(getxmlrpcproxy(host))
    multicall.getsupportedmaps(config.botrunnername, config.sharedsecret)
    multicall.getsupportedmods(config.botrunnername, config.sharedsecret)
    multicall.getsupportedais(config.botrunnername, config.sharedsecret)
    resultsets = multicall()
    registeredmaps = resultsets[0]
    registeredmods = resultsets[1]
    registeredais = resultsets[2]
    registermaps(host, registeredmaps)
    registermods(host, registeredmods)
    registerais(host, registeredais)


# registers ais to all hosts
# used after downloading a new AI
def registeraisallhosts():
    for host in config.websiteurls:
        registeredais = getxmlrpcproxy(host).\
                getsupportedais(config.botrunnername,
                config.sharedsecret)
        registerais(host, registeredais)


# registers maps to all hosts
# used after downloading a new map
def registermapsallhosts():
    for host in config.websiteurls:
        registeredmaps = getxmlrpcproxy(host).\
                getsupportedmaps(config.botrunnername,
                config.sharedsecret)
        registermaps(host, registeredmaps)


# registers mods to all hosts
# used after downloading a new mod
def registermodsallhosts():
    for host in config.websiteurls:
        registeredmods = getxmlrpcproxy(host).\
                getsupportedmods(config.botrunnername,
                config.sharedsecret)
        registermods(host, registeredmods)


def initUnitSync():
    global config
    initUnitSyncWithUnitSyncPath(config.unitsyncPath)


def initUnitSyncWithUnitSyncPath(unitsyncpath):
    global unitsync, writableDataDirectory, unitsynclock
    unitsynclock.acquire()
    unitsync = unitsyncpkg.Unitsync(unitsyncpath)
    unitsync.Init(True, 1)
    writableDataDirectory = unitsync.GetWritableDataDirectory().decode("utf-8")
    unitsynclock.release()


def main():
    #logging.basicConfig(filename='botrunner.log', level=logging.INFO)
    logging.basicConfig(level=logging.INFO)

    global config, unitsync, writableDataDirectory
    global sessionid, options

    parseopts()

    if options.version:
        if version != None:
            logging.info("AILadder, version: " + version.version)
        else:
            logging.info("AILadder, version: dev code, not a versioned release.")
        return

    # check for config, question user if doesn't exist
    try:
        if options.configpath != None:
            config = imp.load_source('config', options.configpath)
        else:
            import config
        logging.info("Configuration found, using")
    except:
        ok = setupConfig()
        if not ok:
            return
    if config.maxinstances == 'auto':
        try:
            import multiprocessing
            config.maxinstances = multiprocessing.cpu_count()
        except:
            logging.warning("failed to import multiprocessing, set maxinstances manually")
            config.maxinstances = 1

    initUnitSync()

    if sessionid == None:
        sessionid = stringhelper.getRandomAlphaNumericString(60)
    logging.info("Sessionid: " + sessionid)

    if not ping("Connection Test!"):
        logging.error("""Failed to ping all configured websites.  Please check your
        configuration and internet connection and try again.""")
        return

    for host in config.websiteurls:
        if not options.noregistercapabilities:
            try:
                logging.info("registering capabilities with " + host + " ...")
                registercapabilities(host)
            except:
                logging.error("Couldn't register capabilities to host " + host +\
                        " " + str(sys.exc_info()))
                traceback.print_exc()

    #try to set process niceness
    if os.name == 'posix':
        try:
            os.nice(19)
        except:
            logging.info("setting os niceness failed for posix platform")
    while True:
        # go through each host getting a request
        # Process each request, then go back to start of loop,
        # otherwise wait a bit
        global numinstanceslock
        global numinstances
        numinstanceslock.acquire()
        if numinstances < config.maxinstances:
            numinstanceslock.release()
            logging.info("Checking for new request...")
            gotrequest = False
            for host in config.websiteurls:
                logging.info("checking " + host + " ...")
                serverRequest = requestgamefromwebserver(host)
                if serverRequest != None:
                    # we have a request to process
                    numinstanceslock.acquire()
                    matchid = serverRequest['matchrequest_id']
                    if numinstances < config.maxinstances and\
                            matchid not in matches:
                        matches.append(matchid)
                        GameRunner(host, serverRequest).start()
                        numinstances += 1
                        gotrequest = True
                    numinstanceslock.release()
            # see if we can download a new ai
            if not gotrequest and config.allowdownloading:
                logging.info("checking for download request ... ")
                for host in config.websiteurls:
                    if trydownloadingsomething(host) != None:
                        gotrequest = True
                        break

            if not gotrequest:
                logging.info("Nothing to do.  Sleeping...")
                ping("sleeping")
                time.sleep(config.sleepthislongwhennothingtodoseconds)
        else:
            numinstanceslock.release()


if __name__ == '__main__':
    main()
