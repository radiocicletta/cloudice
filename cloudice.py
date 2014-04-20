import soundcloud
import settings
import icecast  # see https://code.google.com/p/doogradio/ for the original code
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
from subprocess import Popen, PIPE
from select import select

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
        yield client.get(
            "/tracks",
            license="cc-by",
            tags=settings.tags,
            order=settings.order,
            types="original",
            limit=limit,
            offset=offset)
        offset = offset + limit

if __name__ == "__main__":

    try:
        gen = SoundCloudGen()
        logger.info("Connecting to icecast")
        icecast.connect()
    except Exception as e:
        logger.error(e)
        sys.exit(1)

    if len(settings.transcoder.strip()):
        proc = Popen(settings.transcoder.split(' '), stdout=PIPE, stdin=PIPE)
    else:
        proc = None

    errorcount = 0.0
    playcount = 10.0

    while errorcount / playcount <= 1:
        try:
            tracks = gen.next()
        except Exception as e:
            logger.error("client.get: %s" % e)
            logger.error("[ErrorRatio] %d %d %f" % (
                errorcount, playcount, errorcount / playcount))
            errorcount = errorcount + 1
            continue

        playcount = playcount + 1

        for track in tracks:
            try:
                logger.debug(track.stream_url)
                stream = urllib2.urlopen("%s?client_id=%s" % (
                    track.stream_url, settings.client_id), timeout=10)
                streaming = True
            except Exception as e:
                logger.error("urllib2.urlopen: %s" % e)
                logger.error("[ErrorRatio] %d %d %f" % (
                    errorcount, playcount, errorcount / playcount))
                errorcount = errorcount + 1
                if errorcount / playcount >= 1:
                    sys.exit(1)

            try:
                username = track.user["username"]
                title = track.title
                logger.info("Now playing: %s - %s" % (username, title))
                icecast.update_metadata(unicodedata.normalize(
                    "NFKD", title).encode('ascii', 'ignore'))
            except Exception as e:
                logger.error(e)
                logger.error("[ErrorRatio] %d %d %f" % (
                    errorcount, playcount, errorcount / playcount))
            readcount = 0
            while streaming:
                io = StringIO()
                try:
                    if proc:
                        proc.stdin.write(stream.read(4096))
                        ready = select([proc.stdout], [], [], 1)
                        if not len(ready[0]):
                            readcount = readcount + 1
                            if readcount == 10:
                                streaming = False
                            continue
                        tok = proc.stdout.read(4096)
                        readcount = 0
                        if len(tok) < 4096:
                            streaming = False
                            continue
                        io.write(tok)
                    else:
                        io.write(stream.read())
                except IOError:
                    logger.debug("IOError")
                    proc.terminate()
                    proc = Popen(settings.transcoder.split(
                        ' '), stdout=PIPE, stdin=PIPE)
                    logger.debug("reopened")
                except Exception as e:
                    logger.error(e)
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
                    logger.error("[ErrorRatio] %d %d %f" % (
                        errorcount, playcount, errorcount / playcount))
                    errorcount = errorcount + 1
                    streaming = False
                finally:
                    if not io.tell():
                        streaming = False
                if errorcount / playcount >= 1:
                    sys.exit(1)

    icecast.close()
