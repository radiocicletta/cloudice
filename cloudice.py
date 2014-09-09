import soundcloud
import settings
import stream_settings as ss
import shout
import sys
import pycurl
from urllib import urlencode
from cStringIO import StringIO
from time import sleep
import unicodedata
import logging
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
            filter="steamable",
            tags=settings.tags,
            types="original",
            limit=limit,
            duration={'from': 90000},
            offset=offset)
        offset = offset + limit


proc = None

def create_shout():
    _shout = shout.Shout()
    _shout.port = ss.port
    _shout.host = ss.host
    _shout.password = ss.password
    _shout.mount = ss.mount_point
    _shout.protocol = "icy"
    _shout.format = "mp3"

    _shout.name = ss.name
    _shout.genre = ss.genre
    _shout.description = ss.description
    _shout.agent = ss.user_agent
    _shout.audio_info = {
        'samplerate': ss.samplerate,
        'bitrate': ss.bitrate,
        'channels': ss.channels
    }

    return _shout


def cbk_write(buf):
    global proc, icecast
    data = StringIO(buf)
    data_l = len(buf)
    while data_l > data.tell():
        try:
            proc.stdin.write(data.read(4096))
            #logger.debug("Data: %d", data.tell())
        except IOError:
            logger.error("Restarting transcoder")
            proc.terminate()
            proc = Popen(settings.transcoder.split(
                ' '), stdout=PIPE, stdin=PIPE)
        except Exception as e:
            logger.error(e)
        try:
            ready = select([proc.stdout], [], [], 0.5)
            if not len(ready[0]):
                continue
            tok = proc.stdout.read(4096)
            #logger.debug("Transcoded data: %d ", len(tok))
        except IOError:
            logger.error("Restarting transcoder")
            proc.terminate()
            proc = Popen(settings.transcoder.split(
                ' '), stdout=PIPE, stdin=PIPE)
        except Exception as e:
            logger.error(e)
        try:
            icecast.send(tok)
        except Exception as e:
            logger.error(e)
            icecast.close()
            sleep(1)
            icecast = create_shout()
            icecast.open()
            logger.error("Failed connection with icecast server")


if __name__ == "__main__":

    try:
        gen = SoundCloudGen()
        logger.info("Connecting to icecast")
    except Exception as e:
        logger.error(e)
        sys.exit(1)

    errorcount = 0.0
    playcount = 10.0
    curl = pycurl.Curl()
    curl.setopt(pycurl.FOLLOWLOCATION, 1)
    curl.setopt(pycurl.MAXREDIRS, 5)
    curl.setopt(pycurl.CONNECTTIMEOUT, 30)
    curl.setopt(pycurl.TIMEOUT, 300)
    curl.setopt(pycurl.NOSIGNAL, 1)
    curl.setopt(pycurl.WRITEFUNCTION, cbk_write)

    if len(settings.transcoder.strip()):
        proc = Popen(settings.transcoder.split(' '), stdout=PIPE, stdin=PIPE)
    else:
        sys.exit(1)

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

        global icecast
        icecast = create_shout()
        icecast.open()

        for track in tracks:
            try:
                curl.setopt(pycurl.URL, "%s?client_id=%s" % (
                    track.stream_url, settings.client_id))
                username = track.user["username"]
                title = track.title
                logger.info("Now playing: %s - %s" % (username, title))
                icecast.update_metadata(unicodedata.normalize(
                    "NFKD", title).encode('ascii', 'ignore'))
            except Exception as e:
                logger.error(e)
                logger.error("[ErrorRatio] %d %d %f" % (
                    errorcount, playcount, errorcount / playcount))
            try:
                curl.perform()
            except pycurl.error:
                pass  # go on, don't look back!

    icecast.close()
