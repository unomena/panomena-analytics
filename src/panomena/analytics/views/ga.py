import time
import uuid
import random
import httplib2
import re
import struct

from hashlib import md5
from urllib import quote

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


VERSION = '4.4sh'
COOKIE_NAME = '__utmmobile'
COOKIE_PATH = '/'
COOKIE_USER_PERSISTENCE = 63072000

GIF_DATA = reduce(lambda x,y: x + struct.pack('B', y), 
                  [0x47,0x49,0x46,0x38,0x39,0x61,
                   0x01,0x00,0x01,0x00,0x80,0x00,
                   0x00,0x00,0x00,0x00,0xff,0xff,
                   0xff,0x21,0xf9,0x04,0x01,0x00,
                   0x00,0x00,0x00,0x2c,0x00,0x00,
                   0x00,0x00,0x01,0x00,0x01,0x00, 
                   0x00,0x02,0x01,0x44,0x00,0x3b], '')


def get_ip(remote_address):
    if not remote_address:
        return ''
    matches = re.match('^([^.]+\.[^.]+\.[^.]+\.).*', remote_address)
    if matches:
        return matches.groups()[0] + "0"
    else:
        return ''


def get_visitor_id(guid, account, user_agent, cookie):
    """Generate a visitor id for this hit.
    If there is a visitor id in the cookie, use that, otherwise
    use the guid if we have one, otherwise use a random number.
    """
    if cookie:
        return cookie
    message = ""
    if guid:
        # create the visitor id using the guid.
        message = guid + account
    else:
        # otherwise this is a new user, create a new random id.
        message = user_agent + str(uuid.uuid4())
    md5String = md5(message).hexdigest()
    return "0x" + md5String[:16]


def gen_utma(domain_name):
    domain_hash = 0
    g = 0
    i = len(domain_name) - 1
    while i>=0:
        c = ord(domain_name[i])
        domain_hash = ((domain_hash << 6) & 0xfffffff) + c + (c << 14)
        g = domain_hash & 0xfe00000
        if g!=0:
            domain_hash = domain_hash ^ (g >> 21)
            i = i - 1
            rnd_num = str(random.randint(1147483647, 2147483647))
            time_num = str(time.time()).split('.')[0]
            _utma = '%s.%s.%s.%s.%s.%s' % (domain_hash, rnd_num, time_num,
                time_num, time_num, 1)
    return _utma


def ga_request(request, response, path=None, event=None):
    """Sends a request to google analytics."""
    meta = request.META
    time_tup = time.localtime(time.time() + COOKIE_USER_PERSISTENCE)
    # get the account id
    try: account = settings.GOOGLE_ANALYTICS_ID     
    except: raise Exception, "No Google Analytics ID configured"
    # determine the domian
    domain = meta.get('HTTP_HOST', '')
    # determine the referrer
    referer = request.GET.get('r', '')
    # get the path from the referer header
    path = path or meta.get('HTTP_REFERER', '')
    # try and get visitor cookie from the request
    user_agent = meta.get('HTTP_USER_AGENT', 'Unknown')
    cookie = request.COOKIES.get(COOKIE_NAME)
    visitor_id = get_visitor_id(meta.get('HTTP_X_DCMGUID', ''), account, user_agent, cookie)
    # always try and add the cookie to the response
    response.set_cookie(
        COOKIE_NAME,
        value=visitor_id,
        expires=time.strftime('%a, %d-%b-%Y %H:%M:%S %Z', time_tup),
        path=COOKIE_PATH,
    )
    # construct the gif hit url
    utm_gif_location = "http://www.google-analytics.com/__utm.gif"
    utm_url = utm_gif_location + "?" + \
        "utmwv=" + VERSION + \
        "&utmn=" + str(random.randint(0, 0x7fffffff)) + \
        "&utmhn=" + quote(domain) + \
        "&utmsr=" + '' + \
        "&utme=" + '' + \
        "&utmr=" + quote(referer) + \
        "&utmp=" + quote(path) + \
        "&utmac=" + account + \
        "&utmcc=__utma%3D" + gen_utma(domain) + "%3B" + \
        "&utmvid=" + visitor_id + \
        "&utmip=" + get_ip(meta.get('REMOTE_ADDR', ''))
    # add event parameters if supplied
    if event:
        utm_url += '&utmt=event' + \
            '&utme=5(%s)' % '*'.join(event)
    # send the request
    http = httplib2.Http()    
    try:
        resp, content = http.request(
            utm_url, 'GET', 
            headers={
                'User-Agent': user_agent,
                'Accepts-Language:': meta.get('HTTP_ACCEPT_LANGUAGE', '')
            }
        )
        # send debug headers if debug mode is set
        if request.GET.get('utmdebug', False):
            response['X-GA-MOBILE-URL'] = utm_url
            response['X-GA-RESPONSE'] = resp
        # return the augmented response
        return response
    except httplib2.HttpLib2Error:
        raise Exception("Error opening: %s" % utm_url)


@never_cache
def ga(request):
    """Image that sends data to Google Analytics."""
    event = request.GET.get('event', None)
    if event: event = event.split(',')
    response = HttpResponse('', 'image/gif', 200)
    response.write(GIF_DATA)
    return ga_request(request, response, event=event)

