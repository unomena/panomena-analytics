import time
import uuid
import random
import urllib
import httplib2
import re
import struct

from hashlib import md5

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


CAMPAIGN_TRACKING_PARAMS = (
    ('utm_campaign', 'utmccn', '(direct)'),
    ('utm_source', 'utmcsr', '(direct)'),
    ('utm_medium', 'utmcmd', '(none)'),
)

VERSION = '5.1.2'
CAMPAIGN_PARAMS_KEY = 'ga_campaign_params'
GA_COOKIE_PREFIX = '__utm'

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


def generate_domain_hash(domain_name):
    """Generate a hash of a domain name."""
    domain_hash = 0
    g = 0
    i = len(domain_name) - 1
    while i>=0:
        c = ord(domain_name[i])
        domain_hash = ((domain_hash << 6) & 0xfffffff) + c + (c << 14)
        g = domain_hash & 0xfe00000
        if g!=0:
            i = i - 1
            domain_hash = domain_hash ^ (g >> 21)
    return domain_hash


def generate_utma(utmc):
    rnd = str(random.randint(1147483647, 2147483647))
    time_num = str(time.time()).split('.')[0]
    return '%s.%s.%s.%s.%s.%s' % (utmc, rnd, time_num, time_num, time_num, 1)


def generate_utmz(request, utmc):
    """Generate the referral string."""
    current_time = str(time.time()).split('.')[0]
    # collect campaign tracking parameters
    campaign_params = []
    for key, value, default in CAMPAIGN_TRACKING_PARAMS:
        campaign_params.append(value + '=' + request.GET.get(key, default))
    campaign_params = '|'.join(campaign_params)
    # generate the final string
    return '%s.%s.1.1.%s' % (utmc, current_time, campaign_params)


def generate_utmb(request, utmc):
    """Generate the session tracking string."""
    current_time = str(time.time()).split('.')[0]
    return '%s.1.10.%s' % (utmc, current_time)


def ga_request(request, response, path=None, event=None):
    """Sends a request to google analytics."""
    meta = request.META
    cookies = request.COOKIES
    # get the account id
    try: account = settings.GOOGLE_ANALYTICS_ID     
    except: raise Exception, "No Google Analytics ID configured"
    # determine the domian
    domain = meta.get('HTTP_HOST', '')
    # determine the referrer
    referer = request.GET.get('r', '')
    # get the path from the referer header
    path = path or request.GET.get('p', '/')
    # try and get visitor cookie from the request
    user_agent = meta.get('HTTP_USER_AGENT', 'Unknown')
    # set the cookie variables
    utma = cookies.get('__utma')
    utmc = cookies.get('__utmc')
    if not utmc and utma:
        utmc = utma.split('.')[0]
    else:
        utmc = cookies.get('__utmc') or generate_domain_hash(domain)
    utma = utma or generate_utma(utmc)
    utmb = cookies.get('__utmb') or generate_utmb(utmc)
    utmz = cookies.get('__utmz') or generate_utmz(request, utmc)
    # build the parameter collection
    params = {
        'utmwv': VERSION,
        'utmn': str(random.randint(0, 0x7fffffff)),
        'utmhn': domain,
        'utmsr': '',
        'utme': '',
        'utmr': referer,
        'utmp': path,
        'utmac': account,
        'utmcc': urllib.quote('__utma=%s;+__utmz=%s;' % (utma, utmz)),
        'utmip': meta.get('REMOTE_ADDR', ''),
    }
    # add event parameters if supplied
    if event:
        params.update({
            'utmt': 'event',
            'utme': '5(%s)' % '*'.join(event),
        })
    # construct the gif hit url
    utm_gif_location = "http://www.google-analytics.com/__utm.gif"
    utm_url = utm_gif_location + "?" + urllib.urlencode(params)
    # always try and add the cookies to the response
    response.set_cookie('__utma', utma, 63072000) 
    response.set_cookie('__utmb', utmb, 1800) 
    response.set_cookie('__utmc', utmc) 
    response.set_cookie('__utmz', utmz, 15552000) 
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

