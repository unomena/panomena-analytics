import urllib
import urlparse

from django import template
from django.core.urlresolvers import reverse

from panomena_general.exceptions import RequestContextRequiredException

from panomena_analytics import CAMPAIGN_TRACKING_PARAMS


register = template.Library()


class GANode(template.Node):
    """Tag node for building the link to the internal google analytics
    image.
    
    """

    def __init__(self, debug):
        self.debug = debug

    def render(self, context):
        # attempt get the request from the context
        request = context.get('request', None)
        if request is None:
            raise RequestContextRequiredException()
        # intialise the parameters collection
        params = {}
        # collect the campaign tracking parameters from the request
        for param in CAMPAIGN_TRACKING_PARAMS:
            value = request.REQUEST.get(param, None)
            if value: params[param] = value
        # pass on the referer if present
        referer = request.META.get('HTTP_REFERER', None)
        if referer: params['r'] = referer
        # remove collected parameters from the path and pass it on
        path = request.path
        parsed_url = urlparse.urlparse(path)
        query = urlparse.parse_qs(parsed_url.query)
        for param in params:
            if query.has_key(param): del query[param]
        query = urllib.urlencode(query)
        new_url = parsed_url._replace(query=query)
        params['p'] = new_url.geturl()
        # append the debug parameter if requested
        if self.debug: params['utmdebug'] = 1
        # build and return the url
        url = reverse('ga')
        if len(params) > 0:
            url += '?' + urllib.urlencode(params)
        return url


@register.tag
def ga(parser, token):
    """Parser method that build a GANode for rendering."""
    bits = token.split_contents()
    # collect parameters if available
    debug = 'False'
    if len(bits) > 1: debug = bits[1]
    if len(debug) > 0:
        debug = (debug[0].lower() == 't')
    # build and return the node
    return GANode(debug)
