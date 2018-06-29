"""Remote Python Debugger (pdb wrapper).

Modified version that includes pull request [1] for issue #21 [2] as found in
Akrog's repository [3].

This is the only solution that won't break with OS-Brick.

[1]: https://github.com/tamentis/rpdb/pull/24
[2]: https://github.com/tamentis/rpdb/issues/21
[3]: https://raw.githubusercontent.com/Akrog/rpdb/master/rpdb/__init__.py


Copyright (c) 2010,2012 Bertrand Janin <tamentis@neopulsar.org>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:
1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
SUCH DAMAGE.
"""


__author__ = "Bertrand Janin <b@janin.com>"
__version__ = "0.1.6"

import pdb
import socket
import threading
import signal
import sys
import traceback
from functools import partial

DEFAULT_ADDR = "127.0.0.1"
DEFAULT_PORT = 4444


def makefile(clientsocket, *args, **kwargs):
    # Return a filetype object
    # Python 2 makefile doesn't support encoding parameter
    if hasattr(socket, '_fileobject'):
        class _fileobject(socket._fileobject):
            __slots__ = socket._fileobject.__slots__ + ['encoding', 'errors']
            errors = None

            def __init__(self, *args, **kwargs):
                self.encoding = kwargs.pop('encoding', '')
                super(_fileobject, self).__init__(*args, **kwargs)

            def isatty(self):
                return True
        return _fileobject(clientsocket._sock, *args, **kwargs)

    # Python 3 can set encoding on makefile but not isatty or errors
    result = clientsocket.makefile(*args, **kwargs)
    if not hasattr(result, 'isatty'):
        setattr(type(result), 'isatty', lambda self: True)
        setattr(type(result), 'errors', None)
    return result


class Rpdb(pdb.Pdb):

    def __init__(self, addr=DEFAULT_ADDR, port=DEFAULT_PORT, encoding=None):
        """Initialize the socket and initialize pdb."""

        # Backup stdin and stdout before replacing them by the socket handle
        self.old_stdout = sys.stdout
        self.old_stdin = sys.stdin
        self.port = port

        # Open a 'reusable' socket to let the webapp reload on the same port
        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.skt.bind((addr, port))
        self.skt.listen(1)

        # Writes to stdout are forbidden in mod_wsgi environments
        try:
            sys.stderr.write("pdb is running on %s:%d\n"
                             % self.skt.getsockname())
        except IOError:
            pass

        (clientsocket, address) = self.skt.accept()
        encoding = sys.stdin.encoding if encoding is None else encoding
        handle = makefile(clientsocket, 'rw', encoding=encoding)
        pdb.Pdb.__init__(self, completekey='tab', stdin=handle, stdout=handle)
        sys.stdout = sys.stdin = handle
        self.handle = handle
        OCCUPIED.claim(port, sys.stdout)

    def shutdown(self):
        """Revert stdin and stdout, close the socket."""
        sys.stdout = self.old_stdout
        sys.stdin = self.old_stdin
        self.handle.close()
        OCCUPIED.unclaim(self.port)
        self.skt.shutdown(socket.SHUT_RDWR)
        self.skt.close()

    def do_continue(self, arg):
        """Clean-up and do underlying continue."""
        try:
            return pdb.Pdb.do_continue(self, arg)
        finally:
            self.shutdown()

    do_c = do_cont = do_continue

    def do_quit(self, arg):
        """Clean-up and do underlying quit."""
        try:
            return pdb.Pdb.do_quit(self, arg)
        finally:
            self.shutdown()

    do_q = do_exit = do_quit

    def do_EOF(self, arg):
        """Clean-up and do underlying EOF."""
        try:
            return pdb.Pdb.do_EOF(self, arg)
        finally:
            self.shutdown()


def set_trace(addr=DEFAULT_ADDR, port=DEFAULT_PORT, frame=None):
    """Wrapper function to keep the same import x; x.set_trace() interface.

    We catch all the possible exceptions from pdb and cleanup.

    """
    try:
        debugger = Rpdb(addr=addr, port=port)
    except socket.error:
        if OCCUPIED.is_claimed(port, sys.stdout):
            # rpdb is already on this port - good enough, let it go on:
            sys.stdout.write("(Recurrent rpdb invocation ignored)\n")
            return
        else:
            # Port occupied by something else.
            raise
    try:
        debugger.set_trace(frame or sys._getframe().f_back)
    except Exception:
        traceback.print_exc()


def _trap_handler(addr, port, signum, frame):
    set_trace(addr, port, frame=frame)


def handle_trap(addr=DEFAULT_ADDR, port=DEFAULT_PORT):
    """Register rpdb as the SIGTRAP signal handler"""
    signal.signal(signal.SIGTRAP, partial(_trap_handler, addr, port))


def post_mortem(addr=DEFAULT_ADDR, port=DEFAULT_PORT):
    debugger = Rpdb(addr=addr, port=port)
    type, value, tb = sys.exc_info()
    traceback.print_exc()
    debugger.reset()
    debugger.interaction(None, tb)


class OccupiedPorts(object):
    """Maintain rpdb port versus stdin/out file handles.

    Provides the means to determine whether or not a collision binding to a
    particular port is with an already operating rpdb session.

    Determination is according to whether a file handle is equal to what is
    registered against the specified port.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.claims = {}

    def claim(self, port, handle):
        self.lock.acquire(True)
        self.claims[port] = id(handle)
        self.lock.release()

    def is_claimed(self, port, handle):
        self.lock.acquire(True)
        got = (self.claims.get(port) == id(handle))
        self.lock.release()
        return got

    def unclaim(self, port):
        self.lock.acquire(True)
        del self.claims[port]
        self.lock.release()

# {port: sys.stdout} pairs to track recursive rpdb invocation on same port.
# This scheme doesn't interfere with recursive invocations on separate ports -
# useful, eg, for concurrently debugging separate threads.
OCCUPIED = OccupiedPorts()
