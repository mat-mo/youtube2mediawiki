#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4
# GPL 3+ 2011
import cookielib
import itertools
import json
import mimetools
import mimetypes
import os
import re
import shutil
import tempfile
import urllib2
from urllib import urlencode
import webbrowser
from xml.dom.minidom import parseString


__version__ = 0.1

DEBUG=1
USER_AGENT='youtube2mediawiki/%s (+http://www.mediawiki.org/wiki/User:BotInc/youtube2mediawiki)' % __version__
DESCRIPTION = '''
== {{int:filedesc}} ==
{{Information
|Description={{%(description)s}}
|Source={{Own}}
|Author=%(author)s
|Date=%(date)s
|Permission=
|other_versions=%(url)s
}}

<!--{{ImageUpload|full}}-->
== {{int:license}} ==
{{self|cc-by-sa-3.0,2.5,2.0,1.0}}

%(wiki_categories)s
'''

class Youtube:
    '''
    Example:
        yt = Youtube()
        yt.downlaod(id, filename)
    '''
    def __init__(self):
        self.cj = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [
	        ('User-Agent',
	         'Mozilla/5.0 (X11; Linux i686; rv:2.0) Gecko/20100101 Firefox/4.0'),
            ('Accept-Language', 'en-us, en;q=0.50')
        ]

        #join html5 beta
        url = 'http://www.youtube.com/html5'
        u = self.opener.open(url)
        data = u.read()
        u.close()
        token = re.compile("'XSRF_TOKEN': '(.*?)',").findall(data)[0]
        u = self.opener.open(url, urlencode({
            "enable_html5": "true",
            "session_token": token
        }))
        u.read()
        u.close()

    def info(self, id):
        info = {}
        url = "http://gdata.youtube.com/feeds/api/videos/%s?v=2" % id
        u = self.opener.open(url)
        data = u.read()
        u.close()
        xml = parseString(data)
        info['url'] = 'http://www.youtube.com/watch?v=%s'%id
        info['title'] = xml.getElementsByTagName('title')[0].firstChild.data
        info['description'] = xml.getElementsByTagName('media:description')[0].firstChild.data
        info['date'] = xml.getElementsByTagName('published')[0].firstChild.data.split('T')[0]
        info['author'] = "http://www.youtube.com/user/%s"%xml.getElementsByTagName('name')[0].firstChild.data

        info['categories'] = []
        for cat in xml.getElementsByTagName('media:category'):
            info['categories'].append(cat.firstChild.data)

        info['keywords'] = xml.getElementsByTagName('media:keywords')[0].firstChild.data.split(', ')
        info['wiki_categories'] = '\n'.join(['[[Category:%s]]'%c for c in info['categories']])

        url = "http://www.youtube.com/watch?v=%s" % id
        u = self.opener.open(url)
        data = u.read()
        u.close()
        match = re.compile('<h4>License:</h4>(.*?)</p>', re.DOTALL).findall(data)
        if match:
            info['license'] = match[0].strip()
            info['license'] = re.sub('<.+?>', '', info['license']).strip()
        return info

    def download(self, id, filename):
        #find info on html5 videos in html page and decode json blobs
        url = "http://www.youtube.com/watch?v=%s" % id
        u = self.opener.open(url)
        data = u.read()
        u.close()
        match = re.compile('"html5_fmt_map": \[(.*?)\]').findall(data)
        if match:
            streams = match[0].replace('}, {', '}\n\n{').split('\n\n')
            streams = map(json.loads, streams)
        else:
            streams = []

        #get largest webm video
        stream_type = 'video/webm; codecs="vp8.0, vorbis"'
        webm = filter(lambda s: s['type'] == stream_type, streams)
        large = filter(lambda s: s['quality'] == 'large', webm)
        medium = filter(lambda s: s['quality'] == 'medium', webm)
        if large:
            url = large[0]['url']
        elif medium:
            url = medium[0]['url']
        else:
            print "no WebM video found"
            return False

        #download video and save to file.
        #this only works if you keep the cookies,
        #just passing the url to wget will not work
        u = self.opener.open(url)
        f = open(filename, 'w')
        data = True
        while data:
            data = u.read(4096)
            f.write(data)
        f.close()
        u.close()
        return True

class MultiPartForm(object):
    """Accumulate the data to be used when posting a form."""

    def __init__(self):
        self.form_fields = []
        self.files = []
        self.boundary = mimetools.choose_boundary()
        return
    
    def get_content_type(self):
        return 'multipart/form-data; boundary=%s' % self.boundary

    def add_field(self, name, value):
        """Add a simple field to the form data."""
        if isinstance(name, unicode):
            name = name.encode('utf-8')
        if isinstance(value, unicode):
            value = value.encode('utf-8')
        self.form_fields.append((name, value))
        return

    def add_file(self, fieldname, filename, fileHandle, mimetype=None):
        """Add a file to be uploaded."""
        if isinstance(fieldname, unicode):
            fieldname = fieldname.encode('utf-8')
        if isinstance(filename, unicode):
            filename = filename.encode('utf-8')
        if hasattr(fileHandle, 'read'):
            body = fileHandle.read()
        else:
            body = fileHandle
        if mimetype is None:
            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        self.files.append((fieldname, filename, mimetype, body))
        return
    
    def __str__(self):
        """Return a string representing the form data, including attached files."""
        # Build a list of lists, each containing "lines" of the
        # request.  Each part is separated by a boundary string.
        # Once the list is built, return a string where each
        # line is separated by '\r\n'.  
        parts = []
        part_boundary = '--' + self.boundary
        
        # Add the form fields
        parts.extend(
            [ part_boundary,
              'Content-Disposition: form-data; name="%s"' % name,
              '',
              value,
            ]
            for name, value in self.form_fields
            )
        
        # Add the files to upload
        parts.extend(
            [ part_boundary,
              'Content-Disposition: file; name="%s"; filename="%s"' % \
                 (field_name, filename),
              'Content-Type: %s' % content_type,
              '',
              body,
            ]
            for field_name, filename, content_type, body in self.files
            )
        
        # Flatten the list and add closing boundary marker,
        # then return CR+LF separated data
        flattened = list(itertools.chain(*parts))
        flattened.append('--' + self.boundary + '--')
        flattened.append('')
        return '\r\n'.join(flattened)

class Mediawiki(object):
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password

        self.cj = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj),
                                           urllib2.HTTPHandler(debuglevel=0))
        self.opener.addheaders = [
	        ('User-Agent', USER_AGENT)
        ]
        r = self.login()
        if not r['login']['result'] == 'Success':
            print r
            raise Exception('login failed')

    def post(self, form):
        try:
            request = urllib2.Request(self.url)
            body = str(form)
            request.add_header('Content-type', form.get_content_type())
            request.add_header('Content-length', len(body))
            request.add_data(body)
            result = self.opener.open(request).read().strip()
            return json.loads(result)
        except urllib2.HTTPError, e:
            if DEBUG:
                if e.code >= 500:
                    with open('/tmp/error.html', 'w') as f:
                        f.write(e.read())
                    webbrowser.open_new_tab('/tmp/error.html')
            result = e.read()
            try:
                result = json.loads(result)
            except:
                result = {'status':{}}
            result['status']['code'] = e.code
            result['status']['text'] = str(e)
            return result

    def api(self, action, data={}, files={}):
        form = MultiPartForm()
        form.add_field('format', 'json')
        form.add_field('action', action)
        for key in data:
            form.add_field(key, data[key])
        for key in files:
            form.add_file(key, os.path.basename(files[key]), open(files[key]))
        return self.post(form)

    def login(self):
        form = MultiPartForm()
        form.add_field('format', 'json')
        form.add_field('action','login')
        form.add_field('lgname', self.username)
        form.add_field('lgpassword', self.password)
        r = self.post(form)
        self.token = r['login']['token']
        self.sessionid = r['login']['sessionid']
        return self.api('login', {
            'lgname': self.username,
            'lgpassword': self.password,
            'lgtoken': self.token
        })

    def get_token(self, page, intoken='edit'):
        return str(self.api('query', {
            'prop': 'info',
            'titles': page,
            'intoken': intoken
        })['query']['pages']['-1']['edittoken'])

    def upload(self, filename, description, text):
        fn = os.path.basename(filename)
        pagename = 'File:' + fn.replace(' ', '_')
        token = self.get_token(pagename, 'edit')
        return self.api('upload', {
            'comment': description,
            'text': text,
            'filename': fn,
            'token': token
        }, {'file': filename})

def safe_name(s):
    s = s.strip()
    s = s.replace(' ', '_')
    s = re.sub(r'[:/\\]', '_', s)
    s = s.replace('__', '_').replace('__', '_')
    return s

def import_youtube(youtube_id, username, password, mediawiki_url):
    yt = Youtube()
    wiki = Mediawiki(mediawiki_url, username, password)
    info = yt.info(youtube_id)
    d = tempfile.mkdtemp()
    filename = os.path.join(d, u"%s.webm" % safe_name(info['title']))
    description = DESCRIPTION % info
    if yt.download(youtube_id, filename):
        r = wiki.upload(filename, 'Imported from %s'%info['url'], description)
        if r['upload']['result'] == 'Success':
            print 'Uploaded to', r['upload']['imageinfo']['descriptionurl']
        else:
            print 'Upload failed.'
    else:
        print 'Download failed.'
    shutil.rmtree(d)

def parse_id(url):
    match = re.compile('\?v=([^&]+)').findall(url)
    if match:
        return match[0]
    return url

if __name__ == "__main__":
    from optparse import OptionParser
    import sys

    usage = "Usage: %prog [options] youtubeid"
    parser = OptionParser(usage=usage)
    parser.add_option('-u', '--username', dest='username', help='wiki username', type='string')
    parser.add_option('-p', '--password', dest='password', help='wiki password', type='string')
    parser.add_option('-w', '--url', dest='url', help='wiki api url',
                      default='http://commons.wikimedia.org/w/api.php', type='string')
    (opts, args) = parser.parse_args()

    if None in (opts.username, opts.password) or not args:
        parser.print_help()
        sys.exit(-1)

    youtube_id = parse_id(args[0])
    import_youtube(youtube_id, opts.username, opts.password, opts.url)
