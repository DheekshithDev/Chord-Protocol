import socket
import pickle
import sys

# This IP is loopback IP
SERVER_IP = "127.0.0.1"
SERVER_PORT = 8000


def initialize():
    try:
        init_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        init_server_sock.bind((SERVER_IP, SERVER_PORT))
        init_server_sock.listen(1)
        print("Chord INIT Server is awaiting inc_conn_obj......")
        connection, client_address = init_server_sock.accept()
        print("Connected to : ", client_address)
        success = setup(connection, client_address)
        if success:
            connection.close()
            init_server_sock.close()
            sys.exit("Program Closed.")

    except socket.error as E:
        print(E)


def setup(connection, client_address):
    int_test = 123456
    # Default here is 'utf-8'
    connection.sendall(str(int_test).encode())
    print("Message Sent for Initial Chord Setup!\n")
    return True


# RUN THE SCRIPT
initialize()

