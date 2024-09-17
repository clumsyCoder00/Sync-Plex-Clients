import os
import platform
import time
from xml.etree import ElementTree
import eyed3
import requests
from inputimeout import inputimeout, TimeoutOccurred

# ---- DEPENDENCIES ----
# eyed3
# requests
# inputimeout

# ---- MUST CHANGE CONTENTS BELOW TO MATCH ----
# - change plex url from: '<PLEX URL>" to match
# - fill out videoClientID & audioClientID to match
#   - client IDs can be found here: '<PLEX URL>/clients'

videoClientID = "<VIDEO CLIENT ID>"
audioClientID = "<AUDIO CLIENT ID>"

thisFile = ""
thisAudioKey = ""
thisVideoKey = ""
videoClientDevice = ""
musicVideoKey = ""
vidAvail = False
audAvail = False
remTXT = False
reloadAudio = False

def convertMillis(millis):
    seconds=int(millis/1000)%60
    minutes=int(millis/(1000*60))%60
    hours=int(millis/(1000*60*60))%24
    return str(hours).zfill(2) + ":" + str(minutes).zfill(2) + ":" + str(seconds).zfill(2)
    
def getPlexSession():
    plexSessions = requests.get('<PLEX URL>/status/sessions')
    return ElementTree.fromstring(plexSessions.content)
# -----------------
plexClients = requests.get('<PLEX URL>/clients')
plexClientsXML = ElementTree.fromstring(plexClients.content)
    
for client in plexClientsXML:
    if client.attrib['machineIdentifier'] == videoClientID:
        vidAvail = True
    elif client.attrib['machineIdentifier'] == audioClientID:
        audAvail = True

if not audAvail:
    print("Audio player is not available")
    time.sleep(1)
    exit()
elif not vidAvail:
    print("Video player is not available, try shutting down Plexamp")
    time.sleep(1)
    exit()

print("\nGetting session information")
plexSessionsXML = getPlexSession()

# get active player tracks
for track in plexSessionsXML:
    if track.find('Player').attrib['machineIdentifier'] == videoClientID:
        videoClientDevice = track.find('Player').attrib['device']
        thisVideoKey = track.attrib['key']
        
    if track.find('Player').attrib['machineIdentifier'] == audioClientID:
        thisTitle = track.attrib['title']
        thisAudioKey = track.attrib['key'] #/library/metadata/269473
        curAudioPos = track.attrib['viewOffset']
        audioClientDevice = track.find('Player').attrib['device']
        thisAlbum = track.attrib['parentKey']
        # print("thisAlbum: " + thisAlbum)
        thisFile = track.find('Media').find('Part').attrib['file']
        musicVideoKey = track.get('primaryExtraKey')
        if not musicVideoKey:
            print("\n" + thisTitle + " has no associated video.")
            time.sleep(2)
            exit()
        if track.find('Player').attrib['state'] == "paused":
            print("Audio file is paused.")
            time.sleep(1)
            exit()
            
if musicVideoKey == "":
    print("No track playing.")
    time.sleep(1)
    exit()

# get the name of the music video associated with the active audio track
print("\nGetting music video information")
musicVideoMeta = requests.get('<PLEX URL>' + musicVideoKey)
musicVideoMetaXML = ElementTree.fromstring(musicVideoMeta.content)

while musicVideoMetaXML.text is None:
    # https://python-plexapi.readthedocs.io/en/latest/modules/base.html#plexapi.base.PlexPartialObject.refresh
    print("Music Video Error, refreshing metadata")
    requests.put('<PLEX URL>' + thisAlbum + "/refresh")
    #reloadAudio = True
    time.sleep(1)
    
    # ------------ reload audio ---------------
    audHeaders = {'X-Plex-Target-Client-Identifier' : audioClientID}
    audURL = "<PLEX URL>/player/playback/playMedia"
    audParams = {'key': thisAudioKey, 'offset': curAudioPos, 'address': '10.0.1.3', 'port': 32400, 'machineIdentifier': 'e4eeef8242e31570f2472074c48aa78130bfd73f'}
    requests.get(audURL, params=audParams, headers=audHeaders)
    # ------------ try to get music video data again ---------------
    musicVideoMeta = requests.get('<PLEX URL>' + musicVideoKey)
    musicVideoMetaXML = ElementTree.fromstring(musicVideoMeta.content)

musicVideoTitle = musicVideoMetaXML[0].attrib['title']

curAudioPosString = convertMillis(int(curAudioPos))

if platform.system() == "Windows":
    localPath = thisFile.replace("/mnt/pond", "G:")
    localPath = localPath.replace("/", "\\\\")
else:
    localPath = thisFile.replace("/mnt/pond", "/Volumes/pond")

# ---- get offset stored in text file if it exists ----
eyed3.log.setLevel("ERROR")
audiofile = eyed3.load(localPath)

print("\nGetting saved video offset")
localtxtPath = localPath[:-4]+".txt"
if os.path.isfile(localtxtPath):
    file = open(localtxtPath, "r")
    savedOffset = file.read()
    file.close()
    remTXT = True

# ---- get offset stored in metadata ----
else:
    savedFrame = audiofile.tag.user_text_frames.get("OFF")
    if savedFrame != None:
        savedOffset = savedFrame.text
    else:
        savedOffset = 0

    if savedOffset == "":
        print("no offset saved in file")
        savedOffset = 0

try:
    offsetTime = inputimeout(prompt=("\nAudio Title: " + thisTitle + "\nVideo Title: " + musicVideoTitle + "\nCurrent Position: " + curAudioPosString + "\nCurrent Offset: " + str(float(savedOffset)/1000) + " seconds\nEnter new Offset: ").strip())
except TimeoutOccurred:
    print("stored offset used: " + str(float(savedOffset)/1000) + " seconds")
    offsetTime = float(savedOffset)/1000

if offsetTime == '':
    offsetTime = float(savedOffset)/1000
    
offsetVideoPosition = (int(curAudioPos) - ((float(offsetTime) * 1000) + 340))

# ---- save new offset to audio file if changed or from txt file ----
if (float(offsetTime) * 1000) != float(savedOffset) or remTXT:
    print("\nSaving new offset")
    audiofile.tag.user_text_frames.set(str(float(offsetTime) * 1000), u"OFF")
    audiofile.tag.save()

if remTXT:
    os.remove(localtxtPath)

# ---- if the video position would be negative, add the offset to both the video and audio positions
if offsetVideoPosition < 0:
    curAudioPos = int(curAudioPos) + (float(offsetTime) * 1000)
    offsetVideoPosition = offsetVideoPosition + (float(offsetTime) * 1000)

vidHeaders = {'X-Plex-Target-Client-Identifier' : videoClientID}
if thisVideoKey == musicVideoKey:
    vidURL = "<PLEX URL>/player/playback/seekTo"
    vidParams = {'offset': offsetVideoPosition, 'type': 'video'}
else:
    vidURL = "<PLEX URL>/player/playback/playMedia"
    vidParams = {'key': musicVideoKey, 'offset': offsetVideoPosition, 'address': '10.0.1.3', 'port': 32400, 'machineIdentifier': 'e4eeef8242e31570f2472074c48aa78130bfd73f'}

audHeaders = {'X-Plex-Target-Client-Identifier' : audioClientID}
audURL = "<PLEX URL>/player/playback/seekTo"
audParams = {'offset': curAudioPos, 'type': 'music'}

print("\nSyncing Plex players")
requests.get(vidURL, params=vidParams, headers=vidHeaders)
requests.get(audURL, params=audParams, headers=audHeaders)