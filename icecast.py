"""icecast.py -- icecast2 source in pure python

connection settings are in stream_settings.py.
takes care of protocol and timing.
example:
    icecast.connect()
    while 1:
        ...
        icecast.send(mp3data) # bitrate is maintained by sleeping in this function
    icecast.close()
"""
import socket
import stream_settings
import time
from base64 import b64encode
from urllib import urlencode

# format a dict as HTTP request headers, but with configurable line endings
# (since icecast wants \n instead of \r\n in some places)
def request_format(request, line_separator="\n"):
    return line_separator.join(["%s: %s" % (key, str(val)) for (key, val) in request.items()])

def connect():
    global s, packets_sent, start_time
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((stream_settings.host, stream_settings.port))
    s.sendall("SOURCE %s ICE/1.0\n%s\n%s\n\n" % (
        stream_settings.mount_point, 
        request_format({
            'content-type': 'audio/mpeg',
            'Authorization': 'Basic ' + b64encode("source:" + stream_settings.password),
            'User-Agent': stream_settings.user_agent
        }),
        request_format({
            'ice-name': stream_settings.name,
            'ice-url': stream_settings.url,
            'ice-genre': stream_settings.genre,
            'ice-bitrate': stream_settings.bitrate,
            'ice-private': 0,
            'ice-public': 1,
            'ice-description': stream_settings.description,
            'ice-audio-info': "ice-samplerate=%d;ice-bitrate=%d;ice-channels=%d" %
                (stream_settings.samplerate, stream_settings.bitrate, stream_settings.channels)
        })
    ))
    
    response = s.recv(4096)
    if len(response) == 0:
        raise Exception("No response from icecast server")
    if response.find(r"HTTP/1.0 200 OK") == -1:
        raise Exception("Server response: %s" % response)
    start_time = time.time()
    packets_sent = 0
    
        
# update the metadata using a new socket -- i guess there's no other useful keys besides "song"
def update_metadata(song):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((stream_settings.host, stream_settings.port))
    s.sendall("GET /admin/metadata?%s HTTP/1.0\r\n%s\r\n\r\n" % (
        urlencode({
            'mode': 'updinfo',
            'pass': stream_settings.password,
            'mount': stream_settings.mount_point,
            'song': song
        }),
        request_format({
            'Authorization': 'Basic ' + b64encode("source:" + stream_settings.password),
            'User-Agent': stream_settings.user_agent
        }, "\r\n")
    ))
    s.shutdown(1)
    s.close()

def send(buf):
    global s, packets_sent, start_time
    packet_start_time = time.time()
    s.send(buf)
    packets_sent += 1
    packet_elapsed_time = time.time() - packet_start_time
    total_elapsed_time =  (time.time() - start_time)
    # total packets needed = seconds * bits per second / bits per packet
    packets_needed = int( total_elapsed_time * stream_settings.bitrate * 1000.0 / (4096 * 8) )
    extra_packets = packets_sent - packets_needed

    # return immediately if we're going too slow
    if extra_packets <= stream_settings.buffer_packets:
        return
    # sleep for however much time is remaining to meet our bitrate
    total_packet_time = extra_packets * (4096.0 * 8) / (stream_settings.bitrate * 1000.0)
    time.sleep((total_packet_time - packet_elapsed_time) % 1)

def close():
    try:
        s.shutdown(1)
        s.close()
    except:
        pass
