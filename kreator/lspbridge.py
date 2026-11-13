"""The "language server" Kreator gives Kate's LSP client: a pipe to Kreator.

Kate's LSP client only talks to a server process it starts itself. Kreator
runs one qmlls for everything (its own symbols, diagnostics and qmllint list,
and Kate's editor features), so Kate starts this instead: it connects to
Kreator's local socket (KREATOR_LSP_SOCKET, inherited from Kreator) and passes
the bytes through both ways. Kreator shares the qmlls with Kate there (see
LspClient.attach in lsp.py).

Standard library only (started with python -I -S, so it starts quickly).
"""

import os
import socket
import sys
import threading


def main() -> int:
    path = os.environ.get("KREATOR_LSP_SOCKET", "")
    if not path:
        sys.stderr.write("kreator lspbridge: KREATOR_LSP_SOCKET is not set\n")
        return 2
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError as e:
        sys.stderr.write(f"kreator lspbridge: cannot connect to Kreator: {e}\n")
        return 1

    def upstream():
        # Kate -> Kreator
        try:
            while True:
                data = os.read(0, 65536)
                if not data:
                    break
                sock.sendall(data)
        except OSError:
            pass
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    threading.Thread(target=upstream, daemon=True).start()
    # Kreator -> Kate
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                break
            os.write(1, data)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
