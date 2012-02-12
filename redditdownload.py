"""Download images from a reddit.com subreddit."""

import re
import StringIO
import urllib2
import httplib
import argparse
import os
import reddit


class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""

def _extractImgurAlbumUrls(albumUrl):
    """
    Given an imgur album URL, attempt to extract the images within that
    album

    Returns:
        List of qualified imgur URLs
    """
    response = urllib2.urlopen(albumUrl)
    info = response.info()

    # Rudimentary check to ensure the URL actually specifies an HTML file
    if 'content-type' in info and not info['content-type'].startswith('text/html'):
        return []

    filedata = response.read()

    m = re.compile(r'\"hash\":\"(.[^\"]*)\"')

    items = []

    fp = StringIO.StringIO(filedata)

    for line in fp.readlines():
        results = re.findall(m, line)
        if not results:
            continue

        items += results

    fp.close()

    urls = ['http://i.imgur.com/%s.jpg' % (hash) for hash in items]

    return urls


def _downloadFromUrl(url, destDir):
    """
    Attempt to download file specified by url to 'destDir'

    Returns:
        Filename (derived from url and appended to 'destDir')

    Raises:
        WrongFileTypeException

            when content-type is not in the supported types or cannot
            be derived from the URL

        FileExceptionsException

            If the filename (derived from the URL) already exists in
            the destination directory.
    """
    response = urllib2.urlopen(url)
    info = response.info()

    # Work out file type either from the response or the url.
    if 'content-type' in info.keys():
        filetype = info['content-type']
    elif url.endswith('.jpg') or url.endswith('.jpeg'):
        filetype = 'image/jpeg'
    elif url.endswith('.png'):
        filetype = 'image/png'
    elif url.endswith('.gif'):
        filetype = 'image/gif'
    else:
        filetype = 'unknown'

    # Only try to download acceptable image types
    if not filetype in ['image/jpeg', 'image/png', 'image/gif']:
        raise WrongFileTypeException('WRONG fp TYPE: %s has type: %s!' % (url, filetype))

    filename = os.path.join(destDir, os.path.basename(url))

    # Don't download files multiple times!
    if os.path.exists(filename):
        raise FileExistsException('URL [%s] already downloaded.' % (url))

    filedata = response.read()
    fp = open(filename, 'wb')
    fp.write(filedata)
    fp.close()

    return filename


def _processImgurUrl(url):
    """
    Given an imgur URL, determine if it's a direct link to an image or an
    album.  If the latter, attempt to determine all images within the album

    Returns:
        list of imgur URLs
    """
    if 'imgur.com/a/' in url:
        return _extractImgurAlbumUrls(url)

    # Change .png to .jpg for imgur urls.
    if url.endswith('.png'):
        url = url.replace('.png', '.jpg')
    else:
        # Extract the file extension
        basename, ext = os.path.splitext(os.path.basename(url))
        if not ext:
            # Append a default
            url += '.jpg'

    return [url]


def _extractUrls(url):
    urls = []

    if 'imgur.com' in url:
        urls = _processImgurUrl(url)
    else:
        urls = [url]

    return urls

if __name__ == "__main__":
    p = argparse.ArgumentParser(description='Downloads files with specified extension from the specified subreddit.')
    p.add_argument('reddit', metavar='<subreddit>', help='Subreddit name.')
    p.add_argument('dir', metavar='<destdir>', help='Dir to put downloaded files in.')
    p.add_argument('--last', metavar='ID', default='', required=False, help='ID of the last downloaded file.')
    p.add_argument('--score', metavar='score', default=0, type=int, required=False, help='Minimum score of images to download.')
    p.add_argument('--num', metavar='count', default=0, type=int, required=False, help='Number of images to download.')
    p.add_argument('--update', default=False, action='store_true', required=False, help='Run until you encounter a file already downloaded.')
    p.add_argument('--sfw', default=False, action='store_true', required=False, help='Download safe for work images only.')
    p.add_argument('--nsfw', default=False, action='store_true', required=False, help='Download NSFW images only.')
    p.add_argument('--regex', default=None, action='store', required=False, help='Use Python regex to filter based on title.')
    p.add_argument('--verbose', default=False, action='store_true', required=False, help='Enable verbose output.')
    args = p.parse_args()

    print 'Downloading images from "%s" subreddit' % (args.reddit)

    nTotal = nDownloaded = nErrors = nSkipped = nFailed = 0
    bFinished = False

    # Create the specified directory if it doesn't already exist.
    if not os.path.exists(args.dir):
        os.mkdir(args.dir)

    # If a regex has been specified, compile the rule (once)
    reRule = None
    if args.regex:
        reRule = re.compile(args.regex)

    lastId = args.last

    while not bFinished:
        postings = reddit.getitems(args.reddit, lastId)
        if not postings:
            # No more items to process
            break

        for post in postings:
            nTotal += 1

            if post['score'] < args.score:
                if args.verbose:
                    print '    SCORE: %s has score of %s which is lower than required score of %s.' % (post['id'], post['score'], args.score)

                nSkipped += 1
                continue
            elif args.sfw and post['over_18']:
                if args.verbose:
                    print '    NSFW: %s is marked as NSFW.' % (post['id'])

                nSkipped += 1
                continue
            elif args.nsfw and not post['over_18']:
                if args.verbose:
                    print '    Not NSFW, skipping %s' % (post['id'])

                nSkipped += 1
                continue
            elif args.regex and not re.match(reRule, post['title']):
                if args.verbose:
                    print '    Regex match failed'

                nSkipped += 1
                continue

            for url in _extractUrls(post['url']):
                try:
                    filename = _downloadFromUrl(url, args.dir)

                    # Image downloaded successfully!
                    print '    Downloaded URL [%s].' % (url)
                    nDownloaded += 1

                    if args.num > 0 and nDownloaded >= args.num:
                        bFinished = True
                        break
                except WrongFileTypeException as error:
                    print '    %s' % (error)
                    nSkipped += 1
                except FileExistsException as error:
                    print '    %s' % (error)
                    nErrors += 1
                    if args.update:
                        print '    Update complete, exiting.'
                        bFinished = True
                        break
                except urllib2.HTTPError as error:
                    print '    HTTP error: Code %s for %s.' % (error.code, url)
                    nFailed += 1
                except urllib2.URLError as error:
                    print '    URL error: %s!' % (url)
                    nFailed += 1
                except httplib.InvalidURL as error:
                    print '    Invalid URL: %s!' % (url)
                    nFailed += 1

            if bFinished:
                break

        lastId = post['id']

    print 'Downloaded %d files (Processed %d, Skipped %d, Exists %d)' % (nDownloaded, nTotal, nSkipped, nErrors)
