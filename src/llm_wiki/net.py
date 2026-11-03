"""urlopen with retries for transient connection failures."""
import socket
import ssl
import time
import urllib.error
import urllib.request

ATTEMPTS = 4
WAIT_SECONDS = 5
TRANSIENT = (socket.gaierror, ConnectionError, ssl.SSLError)


def urlopen(request, timeout):
    """Retry only failures that happen before a response. HTTP errors are final."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            if attempt == ATTEMPTS or not isinstance(e.reason, TRANSIENT):
                raise
        except ConnectionError:  # urllib does not wrap a drop while reading the response headers
            if attempt == ATTEMPTS:
                raise
        time.sleep(WAIT_SECONDS * attempt)
