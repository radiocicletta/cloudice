import soundcloud
import settings
import icecast # see https://code.google.com/p/doogradio/ for the original code
import sys
import urllib2
from StringIO import StringIO
import unicodedata
import logging

logging.basicConfig(filename='./cloud.log', level=logging.DEBUG)
logger = logging.getLogger()

# IMPORTANT
# if no certificates are found, you must provide CURL_CA_BUNDLE env var
# 
# CURL_CA_BUNDLE=/opt/local/share/curl/curl-ca-bundle.crt

if __name__ == "__main__":

    try:
        logger.info("Connecting to soundcloud")
        client = soundcloud.Client(client_id=settings.client_id)
        logger.info("Connecting to icecast")
        icecast.connect() 
    except Exception, e:
        logger.error(e)
        sys.exit(1)

    limit = 100
    offset = 0

    errorcount = 0.0
    playcount = 10.0

    while errorcount / playcount <= 1:
        try:
            tracks = client.get("/tracks", license="cc-by", tags=settings.tags, order=settings.order, types="original", limit=limit, offset=offset)
        except Exception, e:
            logger.error("client.get: %s" % e)
            logger.error("[ErrorRatio] %d %d %f" % (errorcount, playcount, errorcount / playcount))
            errorcount = errorcount + 1
            continue

        playcount = playcount + 1

        for track in tracks:
            try:
                stream = urllib2.urlopen("%s?client_id=%s" % (track.stream_url, settings.client_id))
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
                io.write(stream.read(4096))
                try:
                    icecast.send(io.getvalue())
                except:
                    icecast.close()
                    icecast.connect()
                    logger.error("[ErrorRatio] %d %d %f" % (errorcount, playcount, errorcount / playcount))
                    errorcount = errorcount + 1
                    streaming = False 
                finally:
                    if not io.tell():
                        streaming = False
                if errorcount / playcount >= 1:
                    sys.exit(1)

        offset = offset + limit
        
    icecast.close()
    
