import soundcloud
import settings
import icecast # see https://code.google.com/p/doogradio/ for the original code
import sys
import urllib2
from urllib import urlencode
from StringIO import StringIO
from time import sleep
import unicodedata
import logging
import re
try:
    import simplejson as json
except:
    import json

logging.basicConfig(filename='./cloud.log', level=logging.DEBUG)
logger = logging.getLogger()

# IMPORTANT
# if no certificates are found, you must provide CURL_CA_BUNDLE env var
# 
# CURL_CA_BUNDLE=/opt/local/share/curl/curl-ca-bundle.crt
    

def SoundCloudGen():
    logger.info("Connecting to soundcloud")
    client = soundcloud.Client(client_id=settings.client_id)
    limit = 100
    offset = 0
    while True:
        yield client.get("/tracks", license="cc-by", tags=settings.tags, order=settings.order, types="original", limit=limit, offset=offset)
        offset = offset + limit

def MixCloudGen():
    base_url = 'http://api.mixcloud.com'
    scraper_url = 'http://offliberty.com/off.php'
    playlists = json.load(urllib2.urlopen( '%s/%s/playlists/' % (base_url, settings.mixcloud_user)))

    class MX:
        def __init__(self, url, title):
            self.client_id = 0
            self.title = title
            self.stream_url = url
            self.user = {'username': settings.mixcloud_user}
    
    i = 0
    j = 0
    lists = []
    while True: 
        if len(lists) <= i:
            logger.debug('%s%s/cloudcasts/' % (base_url, playlists['data'][i]['key']))
            lists.append(json.load(urllib2.urlopen('%s%scloudcasts/' % (base_url, playlists['data'][i]['key']))))
        playlist = lists[i]
        cloudcast = lists[i]['data'][j % len(lists[i]['data'])]

        # since Mixcloud API doesn't give audio files urls, we use this dirty hack.
        scrapecast = urllib2.urlopen(scraper_url, urlencode({'refext':'', 'track': cloudcast['url']})).read()
        scrapecast_url = re.search('href="([^"]*)"', scrapecast, re.M + re.I).groups()[0]
        yield [MX(scrapecast_url, cloudcast['name'])]

        i = (i + 1) % len(playlists['data'])
        if i == 0:
            j = j + 1
    

if __name__ == "__main__":

    try:
        if settings.source == 'soundcloud':
            gen = SoundCloudGen()
        else if settings.source == 'mixcloud':
            gen = MixCloudGen()
        logger.info("Connecting to icecast")
        icecast.connect() 
    except Exception, e:
        logger.error(e)
        sys.exit(1)


    errorcount = 0.0
    playcount = 10.0

    while errorcount / playcount <= 1:
        try:
            tracks = gen.next() 
        except Exception, e:
            logger.error("client.get: %s" % e)
            logger.error("[ErrorRatio] %d %d %f" % (errorcount, playcount, errorcount / playcount))
            errorcount = errorcount + 1
            continue

        playcount = playcount + 1

        for track in tracks:
            try:
                logger.debug(track.stream_url)
                stream = urllib2.urlopen("%s?client_id=%s" % (track.stream_url, settings.client_id), timeout=10)
                streaming = True
            except Exception, e:
                logger.error("urllib2.urlopen: %s" % e)
                logger.error("[ErrorRatio] %d %d %f" % (errorcount, playcount, errorcount / playcount))
                errorcount = errorcount + 1
                if errorcount / playcount >= 1:
                    sys.exit(1)
            
            try:
                username = track.user["username"]
                title = track.title
                logger.info("Now playing: %s - %s" % (username, title))
                icecast.update_metadata(unicodedata.normalize("NFKD", title).encode('ascii', 'ignore'))
            except Exception, e:
                logger.error(e)
                logger.error("[ErrorRatio] %d %d %f" % (errorcount, playcount, errorcount / playcount))
            while streaming:
                io = StringIO()
                try:
                    io.write(stream.read(4096))
                except:
                    errorcount = errorcount + 1
                    streaming = False 
                    continue
                try:
                    icecast.send(io.getvalue())
                except:
                    icecast.close()
                    sleep(1)
                    icecast.connect()
                    logger.error("Failed connection with icecast server")
                    logger.error("[ErrorRatio] %d %d %f" % (errorcount, playcount, errorcount / playcount))
                    errorcount = errorcount + 1
                    streaming = False 
                finally:
                    if not io.tell():
                        streaming = False
                if errorcount / playcount >= 1:
                    sys.exit(1)

        
    icecast.close()
