# Quick UDP Internet Protocol
# pip install aioquic

import ssl
import asyncio
from aioquic.asyncio import connect, serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration

SERVER_CERT = "server.crt"
SERVER_KEY = "server.key"

class EchoQuicProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_data = None

    async def handle_stream(self, stream_id: int) -> None:
        try:
            if self._quic._role == 'SERVER':
                await self._quic.send_stream_data(stream_id, b"Hello from server!")
            else:
                self.request_data = await self._quic.receive_stream_data(stream_id)
                print("Client received:", self.request_data.decode())
        except Exception as e:
            print(f"Error handling stream: {e}")

async def run_client():
    try:
        configuration = QuicConfiguration(is_client=True)
        configuration.verify_mode = ssl.CERT_NONE
        async with connect("localhost", 4242, configuration=configuration) as protocol:
            stream_id = protocol._quic.get_next_available_stream_id()
            await protocol.handle_stream(stream_id)
    except Exception as e:
        print(f"Client error: {e}")

async def run_server():
    try:
        configuration = QuicConfiguration(is_client=False)
        configuration.load_cert_chain(SERVER_CERT, SERVER_KEY)
        server = await serve("localhost", 4242, configuration=configuration, create_protocol=EchoQuicProtocol)
        await server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_server())
        loop.run_until_complete(run_client())
    except KeyboardInterrupt:
        print("Interrupted by user. Exiting...")
