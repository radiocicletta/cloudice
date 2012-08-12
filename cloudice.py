import soundcloud
import settings
import icecast # see https://code.google.com/p/doogradio/ for the original code
import sys
import urllib2
from StringIO import StringIO
import codecs


# IMPORTANT
# if no certificates are found, you must provide CURL_CA_BUNDLE env var
# 
# CURL_CA_BUNDLE=/opt/local/share/curl/curl-ca-bundle.crt

if __name__ == "__main__":

    try:
        client = soundcloud.Client(client_id=settings.client_id)
        icecast.connect() 
    except Exception, e:
        print e
        sys.exit(1)

    limit = 100
    offset = 0

    errorcount = 0.0
    playcount = 10.0

    while errorcount / playcount <= 1:
        try:
            tracks = client.get("/tracks", license="cc-by", tags=settings.tags, order=settings.order, types="original", limit=limit, offset=offset)
        except:
            errorcount = errorcount + 1
            continue

        playcount = playcount + 1

        for track in tracks:
            try:
                stream = urllib2.urlopen("%s?client_id=%s" % (track.stream_url, settings.client_id))
                streaming = True
            except:
                errorcount = errorcount + 1
                if errorcount / playcount >= 1:
                    sys.exit(1)
            
            try:
                username = unicode(track.user["username"].strip(codecs.BOM_UTF8), 'utf-8')
                title = unicode(track.title.strip(codecs.BOM_UTF8), 'utf-8')
                print "Now playing: ", username, " - ", title
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
    
