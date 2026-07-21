import socket
import ssl

def main():
    # Load or generate certs? We can use mitmproxy's cert!
    # Mitmproxy auto-generates ~/.mitmproxy/mitmproxy-ca-cert.pem and private key
    certfile = '/Users/hipoglisemi/.mitmproxy/mitmproxy-ca.pem'
    
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=certfile)
    
    bindsocket = socket.socket()
    bindsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bindsocket.bind(('0.0.0.0', 8083))
    bindsocket.listen(5)
    print("Listening on 8083 with SSL...")
    
    while True:
        newsocket, fromaddr = bindsocket.accept()
        try:
            connstream = context.wrap_socket(newsocket, server_side=True)
            data = connstream.recv(4096)
            print("--- RECEIVED DATA ---")
            print(data.decode('utf-8', errors='ignore'))
            
            # Send a fake HTTP response
            response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
            connstream.sendall(response)
            connstream.close()
        except Exception as e:
            print("Error:", e)

if __name__ == '__main__':
    main()
