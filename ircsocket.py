#!/usr/bin/env python
import socket
import tools

ENCODING = 'UTF-8'       # The method for encoding and decoding all messages (UTF-8 allows 4 bytes max per char)
LINE_ENDINGS = '\r\n'    # This is appended to all messages sent by the socket (should always be CRLF)
CONNECTION_TIMEOUT = 30  # The socket will timeout after this many seconds when trying to initialize the connection
RECV_TIMEOUT = 180       # The socket will timeout after this many seconds when trying to receive data
SEND_TIMEOUT = 30        # The socket will timeout after this many seconds when trying to send data
MAX_RECV_BYTES = 4096    # The maximum amount of bytes to be received by the socket at a time
DEBUG_MODE = False       # Allows printing of socket debug messages


class IrcSocket:
    """An abstraction of the base Python socket class, tailored specifically for IRC connections.

    Attributes:
        _socket -- Python socket object used for communicating back and forth with an IRC server.
        _is_connected -- Boolean value used to keep track of whether the connection is active at any given time.

    Methods:
        __init__() -- Initialize a socket and its connection status, but don't do anything else.
        connect(host, port) -- Initialize a connection to an IRC server. Takes two arguments.
        disconnect() -- Shutdown and close the socket.
        reset() -- Shutdown, close, and then re-initialize the socket so it can connect again.
        send_raw_text(raw_text) -- Encode and send a string to the IRC server. Takes one argument.
        recv_raw_text() -- Receive and decode data from the IRC server.
        is_connected() -- Return the connection status of the socket.
        _set_timeout(new_timeout) -- Set the socket object's timeout in seconds. Takes one argument.

    Exceptions:
        SocketError -- A subclass of OSError, and is the generic parent class of all custom IrcSocket exceptions.
        SocketTimeout -- A socket operation times out.
        SocketConnectFailed -- The socket fails to initialize a connection.
        SocketConnectionBroken -- An existing connection is terminated unexpectedly.
        SocketConnectionNotEstablished -- Disconnected socket attempts an action that requires an active connection.
        SocketAlreadyConnected -- The socket is already connected but tries to initialize a new connection.
    """
    def __init__(self):
        """Initialize a socket and its connection status, but don't do anything else."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._is_connected = False

    def connect(self, host, port):
        """Initialize a connection to an IRC server.

        Args:
            host -- The hostname or IP address of the IRC server.
            port -- The port to use when attempting to connect.

        Raises:
            SocketConnectFailed
            SocketTimeout
            SocketAlreadyConnected
        """
        if not self.is_connected():
            self._set_timeout(CONNECTION_TIMEOUT)
            tools.println('Connecting to {}:{}...'.format(host, port), tools.SEVERITY['DEBUG'], DEBUG_MODE)

            try:
                self._socket.connect((host, port))

            except socket.herror as err:
                error_message = 'Connection failed: {}'.format(err)
                tools.println(error_message, tools.SEVERITY['ERROR'])
                raise SocketConnectFailed(error_message)

            except socket.gaierror as err:
                error_message = 'Connection failed: {}'.format(err)
                tools.println(error_message, tools.SEVERITY['ERROR'])
                raise SocketConnectFailed(error_message)

            except socket.timeout:
                error_message = 'Connection failed: Operation timed out'
                tools.println(error_message, tools.SEVERITY['ERROR'])
                raise SocketTimeout(error_message)

            except socket.error as err:
                error_message = 'Connection failed: {}'.format(err)
                tools.println(error_message, tools.SEVERITY['ERROR'])
                raise SocketConnectFailed(error_message)

            else:
                tools.println('Connection successful.', tools.SEVERITY['DEBUG'], DEBUG_MODE)
                self._is_connected = True

        else:
            error_message = 'Connection failed: Socket is already connected to something.'
            tools.println(error_message, tools.SEVERITY['ERROR'])
            raise SocketAlreadyConnected(error_message)

    def disconnect(self):
        """Shutdown and close the socket."""
        tools.println('Shutting down the connection...', tools.SEVERITY['DEBUG'], DEBUG_MODE)
        self._is_connected = False

        try:
            self._socket.shutdown(socket.SHUT_RDWR)

        except socket.error as err:
            error_message = 'Shutdown failed: {}'.format(err)
            tools.println(error_message, tools.SEVERITY['WARN'])

        finally:
            tools.println('Cleaning up.', tools.SEVERITY['DEBUG'], DEBUG_MODE)
            self._socket.close()

    def reset(self):
        """Shutdown, close, and then re-initialize the socket so it can connect again."""
        tools.println('Resetting socket...', tools.SEVERITY['DEBUG'], DEBUG_MODE)
        self.disconnect()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tools.println('Socket reset.', tools.SEVERITY['DEBUG'], DEBUG_MODE)

    def send_raw_text(self, raw_text):
        """Encode and send a string to the IRC server. The encoding method is the value of ENCODING.

        Args:
            raw_text -- The string to be sent. If it is an empty string, then this method will do nothing.

        Raises:
            SocketTimeout
            SocketConnectionBroken
            SocketConnectionNotEstablished
        """
        if self.is_connected():
            if raw_text != '':
                encoded_msg = '{}{}'.format(raw_text, LINE_ENDINGS).encode(ENCODING)
                msg_len = len(encoded_msg)
                bytes_sent = 0

                self._set_timeout(SEND_TIMEOUT)

                # NOTE: This loop wrapping send() ensures the socket actually sends the whole message
                while bytes_sent < msg_len:
                    try:
                        num_bytes = self._socket.send(encoded_msg[bytes_sent:])

                    except socket.timeout:
                        error_message = 'Send failed: Operation timed out after {} second(s).'.format(SEND_TIMEOUT)
                        tools.println(error_message, tools.SEVERITY['ERROR'])
                        raise SocketTimeout(error_message)

                    except socket.error as err:
                        error_message = 'Send failed: {}'.format(err)
                        tools.println(error_message, tools.SEVERITY['ERROR'])
                        self._is_connected = False  # self.disconnect()
                        raise SocketConnectionBroken(error_message)

                    else:
                        # NOTE: If send() works but returns 0 bytes, it means the connection was terminated
                        if num_bytes == 0:
                            error_message = 'Send failed: Connection was closed unexpectedly.'
                            tools.println(error_message, tools.SEVERITY['ERROR'])
                            self._is_connected = False  # self.disconnect()
                            raise SocketConnectionBroken(error_message)

                        bytes_sent += num_bytes

                tools.println('>> SENT / {} Bytes: {}'.format(bytes_sent, raw_text), tools.SEVERITY['DEBUG'], DEBUG_MODE)

        else:
            error_message = 'Send failed: Connection has not been established.'
            tools.println(error_message, tools.SEVERITY['ERROR'])
            raise SocketConnectionNotEstablished(error_message)

    def recv_raw_text(self):
        """Receive and decode data from the IRC server. The decoding method is the value of ENCODING.

        Raises:
            SocketTimeout
            SocketConnectionBroken
            SocketConnectionNotEstablished

        Returns:
            list -- The lines of text received from the IRC server.
        """
        if self.is_connected():
            self._set_timeout(RECV_TIMEOUT)

            try:
                encoded_msg = self._socket.recv(MAX_RECV_BYTES)

            except socket.timeout:
                error_message = 'Receive failed: Operation timed out after {} second(s).'.format(RECV_TIMEOUT)
                tools.println(error_message, tools.SEVERITY['ERROR'])
                raise SocketTimeout(error_message)

            except socket.error as err:
                error_message = 'Receive failed: {}'.format(err)
                tools.println(error_message, tools.SEVERITY['ERROR'])
                self._is_connected = False  # self.disconnect()
                raise SocketConnectionBroken(error_message)

            else:
                # NOTE: If recv() works but returns a 0-byte message, it means the connection was terminated
                if encoded_msg == b'':
                    error_message = 'Receive failed: Connection was closed unexpectedly.'
                    tools.println(error_message, tools.SEVERITY['ERROR'])
                    self._is_connected = False  # self.disconnect()
                    raise SocketConnectionBroken(error_message)

                else:
                    bytes_recd = len(encoded_msg)

                    raw_text = encoded_msg.decode(ENCODING)

                    if raw_text[-(len(LINE_ENDINGS)):] == LINE_ENDINGS:
                        raw_text = raw_text[:-(len(LINE_ENDINGS))]

                    tools.println('<< RECV / {} Bytes: {}'.format(bytes_recd, raw_text), tools.SEVERITY['DEBUG'], DEBUG_MODE)

                    recvd_lines = raw_text.split(LINE_ENDINGS)

                    # TODO: Responding to PING messages should probably be the responsibility of the caller?
                    # -
                    for line in recvd_lines:
                        # NOTE: We have to echo the server's "PING <a string>" messages with "PONG <same string>"
                        if line.startswith('PING'):
                            try:
                                self.send_raw_text('PONG {}'.format(line.split()[1]))
                            except SocketTimeout:
                                raise
                            except SocketConnectionBroken:
                                raise
                            except SocketConnectionNotEstablished:
                                raise
                    # -
                    # END TODO

                    return recvd_lines

        else:
            error_message = 'Receive failed: Connection has not been established.'
            tools.println(error_message, tools.SEVERITY['ERROR'])
            raise SocketConnectionNotEstablished(error_message)

    def is_connected(self):
        """Return the connection status of the socket.

        Returns:
            bool -- True if connection is active. False if connection is inactive.
        """
        return self._is_connected

    def _set_timeout(self, new_timeout):
        """Set the socket object's timeout in seconds.

        Args:
            new_timeout -- The new timeout to be used in seconds (can be represented as a float or int)
        """
        if float(new_timeout) != self._socket.gettimeout():
            tools.println('Timeout set to {} second(s).'.format(new_timeout), tools.SEVERITY['DEBUG'], DEBUG_MODE)
            self._socket.settimeout(new_timeout)


class SocketError(OSError):
    """A socket error occurred."""
    def __init__(self, message='A socket error occurred.', errors=None):
        self.message = message
        self.errors = errors
        super().__init__(message)


class SocketTimeout(SocketError):
    """Socket operation timed out."""
    def __init__(self, message='Operation timed out.', errors=None):
        super().__init__(message, errors)


class SocketConnectFailed(SocketError):
    """Socket connection attempt failed."""
    def __init__(self, message='Socket connection attempt failed.', errors=None):
        super().__init__(message, errors)


class SocketConnectionBroken(SocketError):
    """Socket connection was closed unexpectedly."""
    def __init__(self, message='Socket connection was closed unexpectedly.', errors=None):
        super().__init__(message, errors)


class SocketConnectionNotEstablished(SocketError):
    """Socket connection has not been established."""
    def __init__(self, message='Socket connection has not been established.', errors=None):
        super().__init__(message, errors)


class SocketAlreadyConnected(SocketError):
    """Socket is already connected to something."""
    def __init__(self, message='Socket is already connected to something.', errors=None):
        super().__init__(message, errors)
