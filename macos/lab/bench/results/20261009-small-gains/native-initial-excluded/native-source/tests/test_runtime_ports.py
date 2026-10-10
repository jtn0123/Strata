"""Permit a quick restart after TCP close, while rejecting an active listener."""
import errno
from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run import assert_ports_available


class PortAvailabilityTests(unittest.TestCase):
    def listener(self):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        return listener

    def test_recently_closed_connection_does_not_block_a_restart(self):
        with self.listener() as listener:
            port = listener.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                connection, _ = listener.accept()
                with connection:
                    connection.shutdown(socket.SHUT_RDWR)
                self.assertEqual(client.recv(1), b"")
        assert_ports_available([port])

    def test_running_server_is_still_rejected(self):
        with self.listener() as listener:
            with self.assertRaises(OSError) as error:
                assert_ports_available([listener.getsockname()[1]])
            self.assertEqual(error.exception.errno, errno.EADDRINUSE)


if __name__ == "__main__":
    unittest.main()
