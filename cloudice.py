import soundcloud
import icecast # see https://code.google.com/p/doogradio/ for the original code
import sys
import urllib2
from StringIO import StringIO

client_id = "3d9056dfcd65690dc8d0adff567bc6bd"
client_secret = "2d311d8a8b11b6b64d12e556476b329c"

# IMPORTANT
# if no certificates are found, you must provide CURL_CA_BUNDLE env var
# 
# CURL_CA_BUNDLE=/opt/local/share/curl/curl-ca-bundle.crt

if __name__ == "__main__":

    try:
        client = soundcloud.Client(client_id=client_id)
        icecast.connect() 
    except Exception, e:
        print e
        sys.exit(1)

    limit = 100
    offset = 0

    while True:
        tracks = client.get("/tracks", license="cc-by", tags="rock", types="original", limit=limit, offset=offset)

        for track in tracks:
            print "Now playing: ", track.user["username"], " - ", track.title
            stream = urllib2.urlopen("%s?client_id=%s" % (track.stream_url, client_id))
            streaming = True
            try:
                title = ascii(track.title)
                icecast.update_metadata(title)
            except:
                pass
            while streaming:
                io = StringIO()
                io.write(stream.read(4096))
                try:
                    icecast.send(io.getvalue())
                except:
                   streaming = False 
                finally:
                    if not io.tell():
                        streaming = False

        offset = offset + limit
        
    icecast.close()
    
