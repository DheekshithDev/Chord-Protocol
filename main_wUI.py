import datetime
import hashlib
import itertools
import random
import socket
import pickle
import sys
import threading
import time
from collections import OrderedDict
from collections import deque
# from pandas import DataFrame
import PySimpleGUI as gui
import re

# This is for actual application. Not for testing
IPADDR = socket.gethostbyname(socket.gethostname())
PORT = 3000

M = 10  # m-bit # 10-bit
KEY_SPACE = pow(2, M)
BUFFER = 4096

# This IP is loopback IP
INIT_SERVER_IP = "127.0.0.1"
INIT_SERVER_PORT = 8000


def get_hash(key):
    val = hashlib.sha1(key.encode())
    return int(val.hexdigest(), 16) % KEY_SPACE


# Class for message objects
class Chat:
    def __init__(self, f_id, f_dets):
        # f is a dictionary {id: ('username', (address))}
        # f_id, f_dets = f_dict.popitem()  # f_id is key; f_dets is value
        self.chat_id = f_id
        self.chat_username = f_dets[0]
        self.chat_address = f_dets[1]
        self.chat_list = []

    def message_process(self, chat_id, message):
        performed_msg = f'{[chat_id]} {message}'
        # self.chat_list.append(performed_msg)
        return performed_msg

    def message_deprocess(self, de_message):
        try:
            pattern = r"\[(\d+)\]\s+(.*)"
            matcher = re.search(pattern, de_message)  # This gives 'None' if pattern didn't match
            msg_user_id = matcher.group(1)
            unperf_msg = matcher.group(2)
            return msg_user_id, unperf_msg
        except AttributeError as E:
            # This catch is for matcher.group(1) as 'None' type doesn't have group function which raised AttributeError
            print("No '[digit]' found in the text. Something went wrong.")
            #window['-LOGS-'].print(datetime.datetime.now(), ":", "No '[digit]' found in the text. Something went wrong.")
            print(E)
            return None


class Node:
    def __init__(self, ip, zero_port, username, connector_addr):
        # Server Conn here
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Here I am binding the node's own ip and port
            self.server.bind((ip, zero_port))
            # Here I don't need ip_not_need because it will be the same ip captured before class initiation
            ip_not_need, port = self.server.getsockname()
            # Here it can maximum listen to as many as the entire keyspace
            self.server.listen(KEY_SPACE)

        except socket.error as E:
            print("__init__ Exception: ", E)
            sys.exit("Something went wrong.")

        self.ip = ip
        self.port = port
        print("port = ", self.port)
        self.username = username
        self.address = (ip, port)
        print("addr = ", self.address)
        self.id = get_hash(ip + "," + str(port))
        print("id = ", self.id)
        # NTC WHETHER ASSIGNING 'NONE' IS BETTER THAN SELF HERE FOR PRED AND SUCC?
        self.successor_id = self.id
        self.successor_addr = (ip, port)
        # NTC if 'None' only for pred here is better?
        # self.predecessor_id = self.id
        # self.predecessor_addr = (ip, port)
        self.predecessor_id = None
        self.predecessor_addr = None
        # key = equ_id and value = tuple(actual_node_id, (address))
        self.fingertable = OrderedDict()
        # successor_list is a deque list of tuples where 1st element = id and 2nd element = (ip, port) address
        self.successor_list = deque(maxlen=M)
        self.leave_request = False
        # Local variable friends_list is a list of dictionaries with 0'th element being the requestor # [{id: ('username', (address))}]
        # self.friends_dict_objs is dictionary of Class Chat objects
        self.friends_dict_objs = OrderedDict()
        self.semaphore = threading.Semaphore(1)
        # self.kill = None
        self.window = None
        self.dict_vals = None

        for i in range(M):
            temp_id = (self.id + (pow(2, i))) % KEY_SPACE
            # Initializing all values as 'None'
            self.fingertable[temp_id] = (self.id, self.address)

        # func
        if (connector_addr[0] == INIT_SERVER_IP) and (connector_addr[1] == INIT_SERVER_PORT):
            self.initial_setup()
        else:
            # Here, node_connect_addr is a tuple () of len 2
            successor = self.get_successor(self.id, connector_addr)
            self.join_setup(successor)

        print("Joined Network Successfully!\n")
        # window['-LOGS-'].print(datetime.datetime.now(), ":", "Joined Network Successfully!")

# End of class creation here

    def listening_thread(self):
        # def kill():
        #     self.server.close()
        #     return True
        # self.kill = kill
        while True:
            try:
                # print("Listening for connections.....")
                inc_conn_obj, inc_address = self.server.accept()  # Code Block
                inc_conn_obj.settimeout(160)
                # print("inc_address = ", inc_address)
                # This processor_thread is non-daemon; it will keep running even after main thread is done
                process_thread = threading.Thread(target=self.processor_thread, args=(inc_conn_obj, inc_address))
                process_thread.start()

                # if not process_thread.is_alive():
                #     inc_conn_obj.close()
                #     if self.leave_request:  # Leave Request Received
                #         # self.server.shutdown(socket.SHUT_RDWR)
                #         self.server.close()
                #         # os._exit(0)
                #         return

                # process_thread.join()
                # inc_conn_obj.close()
            except socket.error as E:
                if self.leave():
                    self.server.close()
                    return
                print("Listening Thread Exception: ", E)
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", E)

    def processor_thread(self, inc_conn_obj, inc_address):
        try:
            inc_data_form = pickle.loads(inc_conn_obj.recv(BUFFER))  # Code Block
            request_type = inc_data_form[0]
            # print(datetime.datetime.now(), ":", f"req_type = {request_type}")
            # Handle all types of requests here using list entries
            # Maybe I can write return statement to end func in every request type because each req type runs only once

            # Lookup request
            if request_type == 1:
                # Here, inc_data_form[1] is id of the node that is trying to find its successor in the ring
                id_to_find = inc_data_form[1]
                found_successor = self.find_successor(id_to_find)
                inc_conn_obj.sendall(pickle.dumps(found_successor))
                # print(datetime.datetime.now(), ":", "Look up request served!")
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", "Look-up request served.")
                return

            # Join request for updating
            elif request_type == 2:
                # I found a new predecessor_addr, I am gonna change my predecessor_addr details now.
                # Actually I can send just id and get address from inc_con_address but just to be careful, I am doing this
                new_predecessor_id = inc_data_form[1][0]
                new_predecessor_address = inc_data_form[1][1]
                # Checking if new predecessor_addr node is a closer, immediate predecessor_addr of me and if that is the case change my predecessor_addr
                # I need this check if there is only one node in the ring unlike find_successor func
                if self.predecessor_id is None:
                    self.predecessor_id = new_predecessor_id
                    self.predecessor_addr = new_predecessor_address

                if self.is_in_interval(start=self.predecessor_id, end=self.id, target=new_predecessor_id):
                    self.predecessor_id = new_predecessor_id
                    self.predecessor_addr = new_predecessor_address

                # I don't think I need stabilize or fix_fingers func here as they will be running every t sec automatically
                # print(datetime.datetime.now(), ":", "Join request served!")
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", "Join request served.")
                return

            # Regular stabilize check & successor_list refresh
            elif request_type == 3:
                data_form = [(self.predecessor_id, self.predecessor_addr), self.successor_list]
                # Sending my predecessor for stabilize check
                inc_conn_obj.sendall(pickle.dumps(data_form))
                # print(datetime.datetime.now(), ":", "Stabilize request served!")
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", "Stabilize request served.")
                return

            # Regular notify (w.r.t. stabilize) check
            # 0 -> req_type | 1 -> id | 2 -> address from notify func
            elif request_type == 4:
                pred_checker_id = inc_data_form[1]
                pred_checker_addr = inc_data_form[2]
                # Notify check can go by taking the path to predecessor in two ways: 1-anti-clockwise(own) 2-clockwise(as showed in paper)
                # Here, I am taking my own method unlike the research paper to check interval

                if self.predecessor_id == pred_checker_id:
                    return

                # If this request_type is triggered by leave func then there are two ways, I can handle this
                # 1- This below if check will fail and else triggers, where I can just simply check if my predecessor's predecessor is in interval of me (self.id) and my predecessor (pred_id) in "clock-wise" direction
                # 2- Just make predecessor_id as 'None' beforehand using leaving_node by telling its successor (currently here self.id) to make its predecessor as 'None'
                # I am using Method 1.
                if self.predecessor_id is None or self.is_in_interval(start=self.predecessor_id, end=self.id, target=pred_checker_id):
                    self.predecessor_id = pred_checker_id
                    self.predecessor_addr = pred_checker_addr
                else:
                    if self.is_in_interval(start=self.id, end=self.predecessor_id, target=pred_checker_id):
                        self.predecessor_id = pred_checker_id
                        self.predecessor_addr = pred_checker_addr
                    else:
                        print("Something went wrong.")
                    # Here, I could send a success reply back to better handle notify func but unnecessary data transfers, so doing nothing #This comment is for general notify only not leave func
                # print(datetime.datetime.now(), ":", "Notify Request Served!")
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", "Notify request served.")
                return

            # Check predecessor request
            elif request_type == 5:
                # I don't need to do anything here, because my successor is just checking if I am alive or not through sock.connect()
                # If I am dead, then my successor's sock.connect() with throw an exception (timeout or some other), it will be handled
                # print(datetime.datetime.now(), ":", "Check Predecessor Request Served!")
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", "Check Predecessor Request Served.")
                return

            # Leave request received from other node (Leave request of a different node)
            # 0 -> req_type | 1 -> succ_id | 2 -> address of succ
            elif request_type == 6:
                succ_id = inc_data_form[1][0]
                succ_addr = inc_data_form[1][1]
                if self.notify(succ_id, succ_addr):
                    self.successor_id = succ_id
                    self.successor_addr = succ_addr
                    # Ancillary successor list added here
                    self.successor_list.clear()
                    self.successor_list.appendleft((self.successor_id, self.successor_addr))
                return

            # Self Leave Request
            # elif request_type == 6.5:
            #     # time.sleep(20)
            #     self.leave_request = True
            #     return

            # Display all friends request received
            # 0 -> req_type | 1 -> [{id: (username, (address))}]
            elif request_type == 7:
                recv_friends_list = inc_data_form[1]
                requestor_checker = next(iter(recv_friends_list[0]))  # Alternative to the usual I used in other places
                # I am the requestor and I received the friends list after a successful cycle
                if requestor_checker == self.id:
                    # friends_list is a list of dictionaries # [{id: ('username', (address))}]
                    friends_list = deque(recv_friends_list)
                    friends_list.popleft()
                    for f_dict in friends_list:
                        # f_dict is a dictionary {id: ('username', (address))}
                        f_id, f_dets = f_dict.popitem()  # f_id is key; f_dets is value
                        if f_id not in self.friends_dict_objs:
                            f_obj = Chat(f_id, f_dets)
                            self.friends_dict_objs[f_id] = f_obj
                    self.semaphore.release()
                    # End
                else:
                    next_elem = {self.id: (self.username, self.address)}  # self.address is again a tuple here
                    recv_friends_list.append(next_elem)
                    # Forward the request
                    for successor in self.successor_list:
                        successor_addr = successor[1]
                        disp_friends_sock_cont = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        disp_friends_sock_cont.settimeout(10)
                        try:
                            disp_friends_sock_cont.connect(successor_addr)
                        except socket.error as E:
                            print("Display Friends Forward Part-1 Exception: ", E)
                            if self.window:
                                self.window['-LOGS-'].print(datetime.datetime.now(), ":", E)
                            disp_friends_sock_cont.close()
                            continue
                        try:
                            data_form = [7, recv_friends_list]
                            disp_friends_sock_cont.settimeout(None)
                            disp_friends_sock_cont.sendall(pickle.dumps(data_form))
                            disp_friends_sock_cont.close()
                            break
                            # End
                        except socket.error as E:
                            print("Display Friends Forward Part-2 Exception: ", E)
                            if self.window:
                                self.window['-LOGS-'].print(datetime.datetime.now(), ":", E)
                            disp_friends_sock_cont.close()
                            continue

            # Receive message request received
            # 0 -> req_type | 1 -> (sender_id, sender_performed_message) # 1 is a tuple ()
            elif request_type == 8:
                sender_id = inc_data_form[1][0]
                sender_perf_msg = inc_data_form[1][1]
                if sender_id in self.friends_dict_objs:
                    chat_obj = self.friends_dict_objs[sender_id]
                    chat_obj.chat_list.append(sender_perf_msg)
                    # Display that msg immediately.
                    if self.dict_vals and len(self.window['-LIST-'].Widget.curselection()) != 0:
                        index = self.window['-LIST-'].get_indexes()[0]
                        if index is not None:
                            checker_chat_obj = self.dict_vals[index]
                            if checker_chat_obj.chat_id == chat_obj.chat_id:
                                msg_user_id, unperf_msg = chat_obj.message_deprocess(sender_perf_msg)  # msg_user_id not using this
                                self.window['-CHAT_DISPLAY-'].print(chat_obj.chat_username + ":", text_color='blue', end='')
                                self.window['-CHAT_DISPLAY-'].print(f' {unperf_msg}')
                else:
                    # This else won't trigger in any case
                    pass

        finally:
            inc_conn_obj.close()
            # if self.leave_request:
            #     pass

    def initial_setup(self):
        try:
            initial_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            initial_sock.connect((INIT_SERVER_IP, INIT_SERVER_PORT))
            test_data = initial_sock.recv(1024)
            test_string = test_data.decode('utf8')
            int_test = int(test_string)
            if int_test == 123456:
                self.successor_id = self.id
                self.successor_addr = (self.ip, self.port)
                self.predecessor_id = None
                self.predecessor_addr = None
                initial_sock.close()
            else:
                print("Something went wrong!\n")
                initial_sock.close()
        except socket.error as E:
            print("The initial server you are trying to connect is closed. "
                  "You need to have the IP address and port of a Node inside the Chord network to connect.\n")
            print("Exception: ", E)
            sys.exit("Please re-run the script.")

    # There is no reason for this func to be non-static (inside the class). I put it here for general housekeeping/propriety.
    def is_in_interval(self, start, end, target):

        if (start is None) or (end is None) or (target is None):
            return False

        # I changed from just s > e to s >= e here
        if start >= end:
            # Is including = here to make the range inclusive good or bad?
            return (target < end) or (target > start)
        else:
            # Is including = here to make the range inclusive good or bad?
            return start < target < end

    # This is a thread constantly checking if finger table first entry has been changed or not
    def ftable_first_entry_setter(self):
        while True:
            # Run every 5 sec
            time.sleep(2.5)
            # Here, all variables are first entry always
            k = list(self.fingertable.keys())[0]
            c_id = list(self.fingertable.values())[0][0]
            c_addr = list(self.fingertable.values())[0][1]  # Redundant check

            if c_id == self.successor_id and c_addr == self.successor_addr:
                continue

            self.fingertable[k] = (self.successor_id, self.successor_addr)
            #window['-LOGS-'].print(datetime.datetime.now(), ":", "Fixed a finger.")

    def get_successor(self, connector_id, connector_address):
        if self.id == connector_id and self.address == connector_address:
            same_successor = (self.id, self.address)
            return same_successor

        # Need to establish time-out functionality here #Successor list
        send_ping_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # send_ping_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Timeout for 10 sec for connection but not for sending or receiving data
        send_ping_sock.settimeout(10)
        try:
            send_ping_sock.connect(connector_address)
        except socket.timeout as T:
            # Timeout triggered; maybe not responding node
            # Need to implement successor list functionality here
            send_ping_sock.close()
            print("Get Successor Timeout Exception: ", T)
            print("Please check the IP address you entered.")
            return None
        except socket.error as E:
            send_ping_sock.close()
            print("Get Successor Part-1 Exception: ", E)
            if self.window:
                self.window['-LOGS-'].print(datetime.datetime.now(), ":", E)
            return None
        try:
            data_form = [1, connector_id]
            send_ping_sock.settimeout(None)
            send_ping_sock.sendall(pickle.dumps(data_form))
            my_successor = pickle.loads(send_ping_sock.recv(BUFFER))
            send_ping_sock.close()
            return my_successor
        except socket.error as E:
            send_ping_sock.close()
            print("Get Successor Part-2 Exception: ", E)
            if self.window:
                self.window['-LOGS-'].print(datetime.datetime.now(), ":", E)
            return None

    def find_successor(self, id_to_find):
        # Here, no need to write id_to_find <= self.successor_id <= because = will never work as sha1 values are unique
        # and the chances of hash collision happening is very rare.
        # Here, successor_id is finger table's first entry

        # I dont need this check when there is only one node in the ring because this is handled by closest_preceding_node func
        # if self.id == self.successor_id:
        #     pass

        # This check will return false and invoke closest_preceding_node func which will also handle only one node in the entire ring
        if self.is_in_interval(start=self.id, end=self.successor_id, target=id_to_find):
            return self.successor_id, self.successor_addr
        else:
            # No need for checker_id here, it is what caused a huge error in the code.
            checker_id, checker_addr = self.closest_preceding_node_check(id_to_find)
            my_successor = self.get_successor(id_to_find, checker_addr)
            return my_successor

    def closest_preceding_node_check(self, id_to_find):
        # Iterate from reverse
        # Here, I am using fingertable length as max range instead of M because my fingertable dict doesn't allow duplicates
        for i in range((M - 1), -1, -1):
            # NTC target val here
            id_checker = list(self.fingertable.values())[i][0]
            id_checker_addr = list(self.fingertable.values())[i][1]
            if self.is_in_interval(start=self.id, end=id_to_find, target=id_checker):
                return id_checker, id_checker_addr
        # This return will send the one and only node's id after failing above func step #Refer find_successor func
        return self.id, self.address

    def join_setup(self, successor):
        # Might need try except check here
        if successor is None:
            print("The IP address or port you entered might be wrong. Cannot join the chord network. Exiting\n")
            sys.exit(-1)

        successor_id = successor[0]
        successor_address = successor[1]
        join_network_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            join_network_sock.connect(successor_address)
            data_form = [2, (self.id, self.address)]
            join_network_sock.sendall(pickle.dumps(data_form))
            # Updated mine after sending updation to my successor
            self.successor_id = successor_id
            self.successor_addr = successor_address
            self.successor_list.append((self.successor_id, self.successor_addr))
        except socket.error as E:
            print("Join Setup Exception: ", E)
            join_network_sock.close()
            # Joining failed; exiting
            sys.exit(-1)

        join_network_sock.close()

    # def quit_request(self):
    #     final_quit_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     try:
    #         final_quit_sock.connect(self.address)
    #         data_form = [6.5]
    #         final_quit_sock.sendall(pickle.dumps(data_form))
    #         final_quit_sock.close()
    #         return True
    #     except socket.error as E:
    #         print(E)
    #         final_quit_sock.close()
    #         return False

    def leave(self):
        # IMPLEMENT KEY TRANSFER

        if self.predecessor_addr is not None and self.predecessor_id is not None:
            leave_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                leave_sock.connect(self.predecessor_addr)
                data_form = [6, (self.successor_id, self.successor_addr)]
                leave_sock.sendall(pickle.dumps(data_form))
                # Processor_thread should've taken care of closing server sock for us to prevent more server.accept()
                leave_sock.close()
                self.leave_request = True
                self.server.close()
                if self.server.fileno() == -1:
                    return True
                return False
                # if self.kill():
                #     return True
                # return False
                # if self.quit_request():
                #     return True
                # return False
            except socket.error as E:
                # This means my predecessor is not empty but not responding
                print("Leave Exception: ", E)
                if self.window:
                    self.window['-LOGS-'].print(datetime.datetime.now(), ":", E)
                leave_sock.close()
                return False
        else:
            # This means I am only one node in the network or some intricate error.
            # server.close() from a diff thread won't close server.accept() because of underlying OS socket implementation
            # if self.quit_request():
            #     return True
            self.leave_request = True
            self.server.close()
            # time.sleep(0.3)
            if self.server.fileno() == -1:
                return True
            return False
            # if self.kill():
            #     return True
            # return False

    def stabilize(self):
        i = 1
        # One is empty list; one is None because it doesn't matter
        prev_succ_list = []  # This is for checking before performing any operations for better time complexity
        temp_succ_list = None  # This is for checking after performing all operations but before extending self.successor_list
        while True:
            # Every t = Any random time from (3 to 6) seconds
            time.sleep(round(random.uniform(6, 11), 2))
            # print(datetime.datetime.now(), ":", f"Sending Stabilize Request {i}"); i = i + 1
            if self.window:
                self.window['-LOGS-'].print(datetime.datetime.now(), ":", f"Sending Stabilize Request {i}"); i += 1
            # I dont want run stabilize if only one node
            if self.id == self.successor_id and self.predecessor_id is None:
                continue
            prev_id = None
            for i in range(M):
                # Here, s_id means stabilize_id
                s_id = list(self.fingertable.values())[i][0]
                if prev_id == s_id:
                    continue
                prev_id = s_id
                s_addr = list(self.fingertable.values())[i][1]
                stabilize_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                stabilize_sock.settimeout(10)  # Tries to connect for 10 seconds
                try:
                    stabilize_sock.connect(s_addr)
                except socket.error as E:
                    # This except will handle any connection related issues including 10sec timeout
                    # If any error occurs, means the node is not responding,etc will try for the next finger table entry
                    print("Stabilize Part-1 Exception: ", E)
                    stabilize_sock.close()
                    continue
                try:
                    data_form = [3]
                    # I don't want to limit package transfer timeout
                    stabilize_sock.settimeout(None)
                    stabilize_sock.sendall(pickle.dumps(data_form))
                    items = pickle.loads(stabilize_sock.recv(BUFFER))
                    pred_id, pred_addr = items[0]
                    succ_list = items[1]
                    # It's always better to have duplicates and pop last element in deque rather than iterating over it coz it has O(n) time complexity
                    # You can handle the duplicates when you are actually accessing/using the successor_list
                    # Comparing two tuples
                    if succ_list and not succ_list[0] == (self.id, self.address):

                        if prev_succ_list != succ_list:
                            prev_succ_list = succ_list

                            if len(succ_list) > (M - 1):
                                succ_list.pop()

                            if (self.id, self.address) in succ_list:
                                index = succ_list.index((self.id, self.address))
                                succ_list = deque(itertools.islice(succ_list, 0, index))
                                # del succ_list[index:]

                            # for count, element in enumerate(succ_list):
                            #     if element == (self.id, self.address):
                            #         del succ_list[count:]
                            #         break
                            # succ_list = [*set(succ_list)]
                            if succ_list != temp_succ_list:
                                self.successor_list.extend(succ_list)
                            temp_succ_list = succ_list
                            # if succ_list[0] not in self.successor_list:
                            #     self.successor_list.extend(succ_list)
                            # succ_list.appendleft((self.successor_id, self.successor_addr))
                            # self.successor_list = succ_list
                    else:
                        if len(self.successor_list) > 1:
                            self.successor_list.clear()
                            self.successor_list.appendleft((self.successor_id, self.successor_addr))

                    if pred_id == self.id:
                        stabilize_sock.close()
                        # print(" No need to stabilize now. ")
                        break

                    # ftable_first_entry_setter this will take care of finger table first entry updation next
                    # Maybe I should use pred_id is not = self.id
                    if pred_id is not None and self.is_in_interval(start=self.id, end=s_id, target=pred_id):
                        if self.notify(pred_id, pred_addr):
                            self.successor_id = pred_id
                            self.successor_addr = pred_addr
                            # print("successor_dets_in_stab_1 = ", self.successor_id, self.successor_addr)
                            stabilize_sock.close()
                            # if self.successor_list:
                            #     self.successor_list.popleft()
                            #     self.successor_list.appendleft((self.successor_id, self.successor_addr))
                            # Got new successor here; so wiping everything and appending only the new successor in the list
                            self.successor_list.clear()
                            self.successor_list.appendleft((self.successor_id, self.successor_addr))
                            break
                        else:
                            # This check is if notify fails then re-run stabilize without changing anything
                            stabilize_sock.close()
                            break
                    else:
                        if self.notify(s_id, s_addr):
                            self.successor_id = s_id
                            self.successor_addr = s_addr
                            # print("successor_dets_in_stab_2 = ", self.successor_id, self.successor_addr)
                            stabilize_sock.close()
                            # Got new successor here; so wiping everything and appending only the new successor in the list
                            self.successor_list.clear()
                            self.successor_list.appendleft((self.successor_id, self.successor_addr))
                            break
                        else:
                            # This check is if notify fails then re-run stabilize without changing anything
                            stabilize_sock.close()
                            break
                except EOFError:
                    # Two or more nodes are trying to stabilize each other parallely. #Handled Correctly
                    # stabilize_sock.close()
                    time.sleep(3.5)
                    # break
                except socket.error as E:
                    # This except will handle data transfer issue which is not necessarily a chord issue
                    print("Stabilize Part-2 Exception: ", E)
                    print("Something went wrong.")
                    stabilize_sock.close()
                    break
                except TypeError as TE:
                    # This could mean I was able to connect but unable to receive successor's predecessor data
                    print("Stabilize TypeError Exception: ", TE)
                    stabilize_sock.close()
                    break

        # Need to implement successor list capability here # DONE!

    def fix_fingers(self):
        # This func can be run less frequently than stabilize # 3 seconds
        i = 1
        next = 0
        while True:
            # Every t=3.0 seconds
            time.sleep(round(random.uniform(7, 13), 2))
            # print(datetime.datetime.now(), ":", f"Sending Fix Fingers Request {i}"); i = i + 1
            if self.window:
                self.window['-LOGS-'].print(datetime.datetime.now(), ":", f"Sending Fix Fingers Request {i}"); i += 1
            # I dont want run this if only one node
            # NTC Is there a better check than this?
            if self.id == self.successor_id:
                # print("No need to fix finger now.")
                # NTC if continue here is good? or simply leaving the current finger and go on fixing others
                continue

            if next >= M:
                next = 0

            equ_id = list(self.fingertable.keys())[next]

            try:
                actual_id, actual_addr = self.find_successor(equ_id)
                # Here, actual_addr is a tuple of len 2 (ip, port)
                self.fingertable[equ_id] = (actual_id, actual_addr)
            except TypeError as TE:
                # Do nothing; just go to next finger
                print("Fix Fingers TypeError Exception: ", TE)
                continue

            # print("Fixed one finger: ", equ_id, "with : ", actual_id)
            next = next + 1

    def notify(self, notify_id, notify_addr):
        # If only two nodes in the network.
        if (notify_id, notify_addr) == (self.id, self.address):
            # I don't need to set my pred to 'None' here because check_predecessor thread will handle it eventually,
            # but this is immediate and don't need to wait for check_predecessor to run
            self.predecessor_id = None
            self.predecessor_addr = None
            return True

        notify_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        notify_sock.settimeout(10)
        try:
            notify_sock.connect(notify_addr)
        except socket.error as E:
            print("Notify Part-1 Exception: ", E)
            notify_sock.close()
            return False
        try:
            data_form = [4, self.id, self.address]
            # I don't want to limit package transfer timeout
            notify_sock.settimeout(None)
            notify_sock.sendall(pickle.dumps(data_form))
        except socket.error as E:
            print("Notify Part-2 Exception: ", E)
            notify_sock.close()
            return False

        notify_sock.close()
        return True

    def check_predecessor(self):
        i = 1
        while True:
            # Every t=1.5 seconds
            time.sleep(round(random.uniform(8, 15), 2))
            # print(datetime.datetime.now(), ":", f"Sending Check Predecessor Request {i}"); i = i + 1
            if self.window:
                self.window['-LOGS-'].print(datetime.datetime.now(), ":", f"Sending Check Predecessor Request {i}"); i += 1

            # Redundant check for pred_addr here
            # Maybe I should use self.pred_id is not = self.id
            if self.predecessor_id is None or self.predecessor_addr is None:
                # print("No need to check predecessor now.")
                continue

            # Particularly here and in other functions in this program, the socket object creation with the below line of code should always be created for each connection/iteration
            check_pred_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            check_pred_sock.settimeout(10)
            # And instead of simply trying to connect and sending req num [5], I can receive a reply num from my pred to bolster better handling but I'm not
            # or maybe this additional check might entail unnecessary intricate complexes.
            try:
                check_pred_sock.connect(self.predecessor_addr)
                # If my pred is dead, then I will handle with exception block.
            except EOFError:
                time.sleep(3.5)
            except socket.error as E:
                # Problem occurred while trying to connect with my predecessor which means set it to 'None'
                print("Check Predecessor Part-1 Exception: ", E)
                self.predecessor_id = None
                self.predecessor_addr = None
                check_pred_sock.close()
                continue
            try:
                data_form = [5]
                check_pred_sock.settimeout(None)
                check_pred_sock.sendall(pickle.dumps(data_form))
                check_pred_sock.close()
            except socket.error as E:
                # This means if connection was successful but sending minimal data has an issue, then try again for my same pred.
                # This check is needed because there might be a chance where my pred left amidst the process of me sending data, then in next iteration, my connect() will handle it.
                print("Check Predecessor Part-2 Exception: ", E)
                check_pred_sock.close()

    def disp_everyone(self):
        i = 1
        while True:
            time.sleep(round(random.uniform(9, 21), 2))
            # print(datetime.datetime.now(), ":", f"Sending Get All Users Request {i}"); i = i + 1
            if self.window:
                self.window['-LOGS-'].print(datetime.datetime.now(), ":", f"Sending Get All Users Request {i}"); i += 1

            if (self.id == self.successor_id) or (self.address == self.successor_addr) or (self.successor_id is None):
                self.friends_dict_objs.clear()
                continue

            self.semaphore.acquire()

            # List of Dictionaries
            friends_list = []
            head = {self.id: (self.username, self.address)}  # self.address is again a tuple here
            friends_list.append(head)

            # Connection
            for successor in self.successor_list:
                successor_addr = successor[1]
                disp_friends_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                disp_friends_sock.settimeout(10)
                try:
                    disp_friends_sock.connect(successor_addr)
                except socket.error as E:
                    print("Display Friends Part-1 Exception: ", E)
                    disp_friends_sock.close()
                    continue
                try:
                    data_form = [7, friends_list]
                    disp_friends_sock.settimeout(None)
                    disp_friends_sock.sendall(pickle.dumps(data_form))
                    disp_friends_sock.close()
                    break
                except socket.error as E:
                    print("Display Friends Part-2 Exception: ", E)
                    disp_friends_sock.close()
                    continue

    # def list_refresher(self, dict_vals):
    #     while True:
    #         time.sleep(3)
    #         if len(self.friends_dict_objs) == 0:
    #             # Empty the ListBox prior, which is little better
    #             if self.window:
    #                 self.window['-LIST-'].update([])
    #         if dict_vals and self.window:
    #             self.window['-LIST-'].update([obj.chat_username for obj in dict_vals])

    def display_thread(self): # Main Thread
        # Tab INFO
        elem_1 = [gui.Text("My IP Address: ", font=('Helvetica', 11, ''))]
        elem_2 = [gui.Text("My Listening Port: ", font=('Helvetica', 11, ''))]
        elem_3 = [gui.Text("My ID (hashed): ", font=('Helvetica', 11, ''))]
        elem_7 = [gui.Text("My Username: ", font=('Helvetica', 11, ''))]
        elem_4 = [gui.Text("My Successor: ", font=('Helvetica', 11, ''))]
        elem_5 = [gui.Text("My Predecessor: ", font=('Helvetica', 11, ''))]
        elem_6 = [gui.Text("My Successor List: ", font=('Helvetica', 11, ''))]

        d1 = [gui.Text("", font=('Helvetica', 11, ''), key='-DET_IP-')]
        d2 = [gui.Text("", font=('Helvetica', 11, ''), key='-DET_PORT-')]
        d3 = [gui.Text("", font=('Helvetica', 11, 'bold'), key='-DET_ID-')]
        d7 = [gui.Text("", font=('Helvetica', 11, 'bold italic'), key='-DET_UNAME-')]
        d4 = [gui.Text("", font=('Helvetica', 11, 'bold'), key='-DET_SUCC-')]
        d5 = [gui.Text("", font=('Helvetica', 11, 'bold'), key='-DET_PRED-')]
        d6 = [gui.Text("", font=('Helvetica', 11), key='-DET_SUCC_LIST-')]

        pg_col_1 = [elem_1, elem_2, elem_3, elem_7, elem_4, elem_5, elem_6]
        pg_col_2 = [d1, d2, d3, d7, d4, d5, d6]

        # Tab HOME
        # Listbox is empty here
        e1 = [[gui.Text("My username:", font=('Helvetica', 11, '')), gui.Text("", font=('Helvetica', 11, 'italic'), key='-DISP_UNAME-', text_color='red')],
              [gui.Listbox([], size=(20, 15), font=('Helvetica', 11), expand_y=True, enable_events=True,
                           key='-LIST-', default_values=[], select_mode=gui.LISTBOX_SELECT_MODE_SINGLE, tooltip="People currently in the network will show up here")],
              [gui.Button("Refresh", enable_events=True, key="-REFR_LIST-", tooltip="Refresh the list")]]

        e2 = [[gui.Multiline(pad=10, enable_events=True, do_not_clear=False, key='-CHAT_DISPLAY-', autoscroll=True,
                             auto_refresh=True, expand_x=False, expand_y=False, disabled=True, size=(50, 15),
                             tooltip="Type '/exit/' to exit")],
              [gui.Input("", enable_events=True, key='-ACT_MSG-', tooltip="Type '/exit/' to exit"),
               gui.Button("Send", enable_events=True, key="-SEND_MSG-", bind_return_key=False)]]

        tab_1 = [[gui.Column(e1, element_justification='c', pad=10), gui.VerticalSeparator(pad=15), gui.Column(e2, pad=10, element_justification='c')]]  # Tab HOME
        tab_2 = [[gui.Column(pg_col_1), gui.Column(pg_col_2)]]  # Tab INFO
        tab_3 = [[gui.Multiline(pad=10, enable_events=False, do_not_clear=True, key='-LOGS-',
                                autoscroll=True, auto_refresh=True, expand_x=True, expand_y=True, disabled=True,
                                size=(85, 19))]]  # Tab LOGS
        heading = ['ID', 'Successor ID', 'IP Address', 'Port']
        rows = [[]]
        tab_4 = [[gui.Table(values=rows, headings=heading, auto_size_columns=True, key='-F_TABLE-', justification='c', expand_x=True, expand_y=True, enable_events=False, enable_click_events=False)]]  # Tab FINGER TABLE
        tab_5 = [[gui.Text(" - Developed by Dheekshith.M (A9ThuR)", justification='right', font=('Helvetica', 15, 'bold'))]]  # Tab LEGAL

        layout_3 = [[gui.TabGroup([[gui.Tab("Home", tab_1, key='-HOME_TAB-'), gui.Tab("Info", tab_2, key='-INFO_TAB-', expand_x=True, expand_y=True),
                                    gui.Tab("Logs", tab_3, key='-LOGS_TAB-'), gui.Tab("Finger Table", tab_4, key='-F_TBL-'),
                                    gui.Tab("Legal", tab_5, key='-LEGAL_TAB-')]], enable_events=True, key='-TGRP-')],
                    [gui.Button("Leave Network", key='-EXIT-')]]

        # Create the window
        window = gui.Window("Chord Network", layout_3, margins=(15, 15), element_justification='c', return_keyboard_events=True, resizable=False)
        # window.bind('<FocusIn>', 'FocusIn')
        self.window = window

        # list_refresher_thread = None

        # Create an event loop
        while True:
            #window.refresh()
            event, values = window.read()

            dict_vals = [self.friends_dict_objs[x] for x in self.friends_dict_objs.keys()]
            self.dict_vals = dict_vals  # Unnecessary in general; only used in one functionality.
            # dict_vals = [x for x in self.friends_dict_objs.values()]

            # if not list_refresher_thread:
            #     list_refresher_thread = threading.Thread(target=self.list_refresher, args=(dict_vals))
            #     list_refresher_thread.daemon = True
            #     list_refresher_thread.start()

            if event == gui.WIN_CLOSED or event == '-EXIT-':
                gui.popup_quick_message('Leaving Network....')
                # gui.popup_notify('Leaving Network....')
                window['-LOGS-'].print('Leave network call initiated.')
                print("Leaving Network....")
                if self.leave():
                    gui.popup_quick_message('Successfully left! Closing window')
                    window['-LOGS-'].print('Left the network.')
                    print("Successfully left!")
                else:
                    gui.popup_auto_close("Something went wrong.", title="Leave Network Error!", auto_close_duration=2)
                    window['-LOGS-'].print("Unable to leave network. 'Leave Network' call failed.")
                    print("Something went wrong.")
                    # Might be better to write continue and wait the user than simply breaking
                    # continue
                break

            if event == '-SEND_MSG-' or event in ('\r', QT_ENTER_KEY1, QT_ENTER_KEY2):
                if not values['-LIST-']:
                    gui.popup_quick_message('Please select an username on the left', non_blocking=True)
                    continue
                message = values['-ACT_MSG-']
                if not message:
                    gui.popup_quick_message("The message box can't be empty. Please type a message", background_color='red', non_blocking=True)
                    continue
                if message == "/exit/":
                    gui.popup_quick_message('Leaving Network....')
                    window['-LOGS-'].print('Leave network call initiated.')
                    print("Leaving Network....")
                    if self.leave():
                        gui.popup_quick_message('Successfully left! Closing window')
                        window['-LOGS-'].print('Left the network.')
                        print("Successfully left!")
                    else:
                        gui.popup_auto_close("Something went wrong.", title="Leave Network Error!", auto_close_duration=2)
                        window['-LOGS-'].print("Unable to leave network. 'Leave Network' call failed.")
                        print("Something went wrong.")
                        # continue
                        # sys.exit(-1)
                        # Might be better to write continue and wait the user than simply breaking
                    break
                try:
                    index = window['-LIST-'].get_indexes()[0]
                    # Sending the selected chat object from ListBox and the actual message to required function
                    chat_obj = dict_vals[index]
                    performed_message = chat_obj.message_process(self.id, message)
                    if self.send_message(chat_obj, performed_message):
                        chat_obj.chat_list.append(performed_message)
                        window['-CHAT_DISPLAY-'].print(self.username + ":", text_color='red', end='', justification='right')
                        window['-CHAT_DISPLAY-'].print(f' {message}', justification='right')
                        window['-ACT_MSG-'].update("")
                    else:
                        gui.popup_auto_close("Something went wrong in sending message. Try again.", title="Send Message Error!", auto_close_duration=2)
                        window['-LIST-'].update([obj.chat_username for obj in dict_vals])
                except (KeyError, AttributeError, IndexError) as E:
                    print(E)
                    window['-LOGS-'].print(datetime.datetime.now(), ":", "Unable to send message.")
                    # continue # This will continue as it reached end of statement

            elif event == '-TGRP-' and values[event] == '-INFO_TAB-':
                window['-DET_IP-'].update(self.ip)
                window['-DET_PORT-'].update(self.port)
                window['-DET_ID-'].update(self.id)
                window['-DET_UNAME-'].update(self.username)
                window['-DET_SUCC-'].update(self.successor_id)
                window['-DET_PRED-'].update(self.predecessor_id)
                window['-DET_SUCC_LIST-'].update(list(self.successor_list))

            elif event == '-REFR_LIST-':
                time.sleep(0.3)

                if not values['-LIST-']:
                    window['-CHAT_DISPLAY-'].update("")  # Clearing the Multiline widget

                if len(self.friends_dict_objs) == 0:
                    # Empty the ListBox prior, which is little better
                    window['-LIST-'].update([])
                window['-LIST-'].update([obj.chat_username for obj in dict_vals])

                if len(window['-LIST-'].Widget.curselection()) == 0:
                    window['-LIST-'].Widget.select_set([0])

            elif event == '-TGRP-' and values[event] == '-HOME_TAB-':
                # window['-DISP_UNAME-'].update("My Username: %s" % self.username)
                window['-DISP_UNAME-'].update(self.username)

                if not values['-LIST-']:
                    window['-CHAT_DISPLAY-'].update("")  # Clearing the Multiline widget

                if len(self.friends_dict_objs) == 0:
                    # Empty the ListBox prior, which is little better
                    window['-LIST-'].update([])
                window['-LIST-'].update([obj.chat_username for obj in dict_vals])

                if len(window['-LIST-'].Widget.curselection()) == 0:
                    # window['-LIST-'].set_focus()
                    window['-LIST-'].Widget.select_set([0])

            elif event == '-LIST-' and values['-LIST-']:
                try:
                    index = window['-LIST-'].get_indexes()[0]
                    chat_obj = dict_vals[index]
                    window['-CHAT_DISPLAY-'].update("")  # Clearing the Multiline widget
                    for msg in chat_obj.chat_list:
                        # msg_user_id is str here; need to cast into int
                        msg_user_id, unperf_msg = chat_obj.message_deprocess(msg)
                        if int(msg_user_id) in self.friends_dict_objs:
                            receiver_uname = self.friends_dict_objs[int(msg_user_id)].chat_username  # obj.chat_username
                            window['-CHAT_DISPLAY-'].print(receiver_uname + ":", text_color='blue', end='')
                            window['-CHAT_DISPLAY-'].print(f' {unperf_msg}')
                        else:
                            window['-CHAT_DISPLAY-'].print(self.username + ":", text_color='red', end='', justification='right')
                            window['-CHAT_DISPLAY-'].print(f' {unperf_msg}', justification='right')

                except (KeyError, AttributeError, IndexError) as E:
                    print(E)
                    window['-LOGS-'].print("Unable to retrieve data.")
                    # continue # This will continue as it reached end of statement

            elif event == '-TGRP-' and values[event] == '-F_TBL-':
                rows.clear()
                for k, val in self.fingertable.items():
                    rows.append([k, val[0], val[1][0], val[1][1]])
                window['-F_TABLE-'].update(values=rows)

            if len(window['-LIST-'].Widget.curselection()) == 0:
                window['-LIST-'].Widget.select_set([0])

        # gui.popup_notify('Exited Application!')
        window.close()
        sys.exit(0)

        # while True:
        #     time.sleep(0.5)
        #     print("1. Send Message\n")
        #     print("2. Leave Network\n")
        #     print("3. Show Successor and Predecessor\n")
        #     print("4. Show Finger Table\n")
        #     print("5. Show Successor List\n")
        #
        #     user_input = int(input("Type any associated number for the above options\n"))
        #
        #     if user_input == 1:
        #         print(list(self.friends_list))
        #     elif user_input == 2:
        #         print("Leaving Network....")
        #         if self.leave():
        #             print("Successfully left!")
        #             sys.exit(0)
        #         else:
        #             print("Something went wrong.")
        #             sys.exit(-1)
        #             # os._exit(0)
        #     elif user_input == 3:
        #         print("My Successor: \n", self.successor_id)
        #         print("My Predecessor: \n", self.predecessor_id)
        #     elif user_input == 4:
        #         df = DataFrame([self.fingertable])
        #         pandas.set_option('display.max_colwidth', None)
        #         pandas.set_option('display.max_rows', None)
        #         pandas.set_option('display.max_columns', None)
        #         print(df)
        #     elif user_input == 5:
        #         print("Successor List: \n", list(self.successor_list))
        #     else:
        #         print("Not a valid option.")

    def send_message(self, chat_obj, performed_message):
        chat_addr = chat_obj.chat_address
        send_message_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        send_message_sock.settimeout(10)
        try:
            send_message_sock.connect(chat_addr)
        except socket.error as E:
            print("Send Message Part-1 Exception: ", E)
            send_message_sock.close()
            return False
        try:
            data_form = [8, (self.id, performed_message)]
            send_message_sock.settimeout(None)
            send_message_sock.sendall(pickle.dumps(data_form))
            send_message_sock.close()
        except socket.error as E:
            print("Send Message Part-2 Exception: ", E)
            send_message_sock.close()
            return False
        return True

    def start(self):
        # Here, Order is preserved
        all_funcs = [self.listening_thread, self.stabilize, self.fix_fingers,
                     self.ftable_first_entry_setter, self.check_predecessor, self.disp_everyone]
        for func in all_funcs:
            thread = threading.Thread(target=func, args=())
            thread.daemon = True
            # if func == self.listening_thread:
            #     thread.daemon = False
            thread.start()

        # Initiate Display on Main thread
        self.display_thread()

######
# CODE STARTS HERE
######

# NEED TO IMPLEMENT TERMINAL CONTROLS HERE

# print("The system will automatically capture your IP address and port as soon as you run the script,"
#       " but for testing you need to manually enter your port.\n")

# Here it is 'localhost' which can be either loopback ip address (127.0.0.1) or local network ip (192.168.x.x)
# You can hardcode the loopback address always
user_ip = socket.gethostbyname(socket.gethostname())
# Here, port 0 binds to whatever available port in the system
user_port = 0
# user_port = input("Enter a port number for the system: ")  # This is for testing only # I should use 0 for real-time.

# while True:
#     user_username = input("Enter your username for public display: ")
#
#     if len(user_username) < 4:
#         print("The username must me at least four characters long\n")
#         continue
#     elif user_username.isdigit():
#         print("This is not a valid username\n")
#         continue
#     else:
#         break

# print("If you are the first node, then try to enter the init_server IP node address and node port.\n "
#       "The system throws exception if you are not the first node ever.")

# node_connect_ip = input("Enter the IP address of any node in chord or init_server: ")
#
# while True:
#     node_connect_port = input("Enter the port of the node: ")
#     if not node_connect_port.isdigit():
#         print("This is not a valid port number. Try Again.\n")
#         continue
#     break
#
# node_connect_addr = (node_connect_ip, int(node_connect_port))
# Theme
gui.theme('LightBlue3')
# Layout 1 Starts Here
layout_1 = [[gui.Text("The system will automatically capture your IP address and port as soon as you launch, \n"
                    "but if you are local system for testing then same IP will be used with different available ports.")],
            [gui.HSeparator(pad=15)],
            [gui.Text("Enter your username for public display: "), gui.Input(key='-USERNAME-', tooltip="Username", font=('Helvetica', 11, 'italic'), enable_events=True)],
            [gui.Submit("Submit", key='-SUBMIT_L1-', pad=15)],
            [gui.Text(text_color='RED', key='-ERR_MSG_L1-')]]

# Layout 2 Starts Here
text_1 = [gui.Text("Enter the IP address of any node in chord or init_server: ")]
text_2 = [gui.Text("Enter the port of the node: ")]
inp_1 = [gui.Input(key='-IP_ADDR_L2-', tooltip="IP Address", enable_events=True)]
inp_2 = [gui.Input(key='-PORT_NUM_L2-', tooltip="Port", enable_events=True)]
col_1 = [text_1, text_2]
col_2 = [inp_1, inp_2]

layout_2 = [[gui.Text("If you are the first node, enter IP Address: '127.0.0.1' and Port: '8000'. \n"
                      "If you are not the first node, then you must know the address of at least one node that is already inside the network.")],
            [gui.HSeparator(pad=15)],
            [gui.Column(col_1), gui.Column(col_2)],
            [gui.Submit("Submit", key='-SUBMIT_L2-', pad=15)],
            [gui.Text(text_color='RED', key='-ERR_MSG_L2-')]]


layout = [[gui.Column(layout_1, key='-L1-', element_justification='c'),
           gui.Column(layout_2, visible=False, key='-L2-', element_justification='c')]]

# Create the window
window = gui.Window("Chord Network", layout, margins=(15, 15), element_justification='c', return_keyboard_events=True)

layout_num = 1

node_connect_ip = None
node_connect_port = None
username = None

# Create an event loop
while True:
    event, values = window.read()

    if event == gui.WIN_CLOSED:
        break

    if layout_num == 1:
        if event == '-SUBMIT_L1-':
            username = values['-USERNAME-']
            if len(username) < 4:
                window['-ERR_MSG_L1-'].update("The username must me at least four characters long")
                continue
            elif username.isdigit():
                window['-ERR_MSG_L1-'].update("This is not a valid username")
                continue

            window['-L1-'].update(visible=False)
            window['-L2-'].update(visible=True)
            window['-IP_ADDR_L2-'].set_focus()
            layout_num = 2

        elif event == "-USERNAME-":
            window["-ERR_MSG_L1-"].update("")

    elif layout_num == 2:
        # if event == 'KeyPress:Return':
        #     window['-SUBMIT_L2-'].click()
        QT_ENTER_KEY1 = 'special 16777220'
        QT_ENTER_KEY2 = 'special 16777221'

        if event == '-SUBMIT_L2-' or event in ('\r', QT_ENTER_KEY1, QT_ENTER_KEY2):
            node_connect_ip = values['-IP_ADDR_L2-']
            node_connect_port = values['-PORT_NUM_L2-']
            if len(node_connect_ip) == 0:
                window['-ERR_MSG_L2-'].update("Please enter an IP Address.")
                continue
            if len(node_connect_port) == 0:
                window['-ERR_MSG_L2-'].update("Please enter a Port Number.")
                continue
            if not node_connect_port.isdigit():
                window['-ERR_MSG_L2-'].update("This is not a valid port number. Try Again.")
                continue

            break

        elif event == '-PORT_NUM_L2-' or event == '-IP_ADDR_L2-':
            window['-ERR_MSG_L2-'].update("")

window.close()

if (node_connect_ip is None) or (node_connect_port is None) or (username is None):
    print("Unable to get IP address or Port or Username....Launch Again.\n")
    sys.exit(-1)

node_connect_addr = (node_connect_ip, int(node_connect_port))

# Here, node_connect_addr is a tuple () of len 2
# Need to remove int() here if I use port number 0 for real-time
node_obj = Node(user_ip, int(user_port), username, node_connect_addr)
node_obj.start()

