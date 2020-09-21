from localasync import asynchat, asyncore
import logging
import socket
from utility import *
from utility import rbac
import re
import commands
from datetime import datetime, timedelta
from threading import Thread
from queue import Queue
import importlib

logger = logging.getLogger(name="tmi")


class TwitchChat(object):

    def __init__(self, user, admin, oauth, channels):
        self.logger = logging.getLogger(name="twitch_chat")
        self.channels = channels
        self.admin = admin
        self.user = user
        self.oauth = oauth
        self.server = 'irc.chat.twitch.tv:6667'
        self.irc_client = IrcClient(self.server, self.handle_message)

        self.state = f.load("texts/global_state.txt", default=dict())
        self.limiter = MessageLimiter()
        self.twitch_status = TwitchStatus(user, channels, commands.ID_cache)

        self.admins = commands.ADMIN
        self.commands = commands.COMMAND
        self.clearchat = commands.CLEARCHAT
        self.notice = commands.NOTICE
        self.returns = commands.RETURNS
        self.saves = commands.SAVE
        self.repeating_tasks = {func_name: TimedTask(func, loop_time, self) for func_name, (func, loop_time) in
                                commands.REPEAT.items()}
        for func_name, setup_func in commands.REPEAT_SETUP.items():
            self.repeating_tasks.get(func_name).setup(setup_func)

        self.active = True
        self.command_thread = Thread(target=self.handle_commandline_input)
        self.command_thread.daemon = True
        self.command_thread.start()
        self.backup_t = Thread(target=self.backup_thread)
        self.backup_t.daemon = True
        self.backup_t.start()

    def init_caps(self):
        self.logger.info('Connected..authenticating as {0}'.format(self.user))
        client = self.irc_client
        client.send_message('Pass ' + self.oauth + '\r\n')
        client.send_message('NICK ' + self.user.lower() + '\r\n')
        client.send_message('CAP REQ :twitch.tv/tags\r\n')
        client.send_message('CAP REQ :twitch.tv/membership\r\n')
        client.send_message('CAP REQ :twitch.tv/commands\r\n')

    def save(self):
        f.save(self.state, "texts/global_state.txt")
        for name, func in self.saves.items():
            logger.info(f"Calling {name}")
            func()

    def reload(self):
        importlib.reload(commands)
        self.admins = commands.ADMIN
        self.commands = commands.COMMAND
        self.clearchat = commands.CLEARCHAT
        self.notice = commands.NOTICE
        self.returns = commands.RETURNS
        self.saves = commands.SAVE
        for repeating_task in self.repeating_tasks.values():
            repeating_task.stop()
        self.repeating_tasks = {func_name: TimedTask(func, loop_time, self) for func_name, (func, loop_time) in
                                commands.REPEAT.items()}
        for func_name, setup_func in commands.REPEAT_SETUP.items():
            self.repeating_tasks.get(func_name).setup(setup_func)
        for repeating_task in self.repeating_tasks.values():
            repeating_task.start()

    def start(self):
        self.irc_client.start()
        for repeating_task in self.repeating_tasks.values():
            repeating_task.start()

        # wait till irc is connected
        while not self.irc_client.connected:
            pass

        # init twitch
        self.init_caps()

        # Joining channels
        self.logger.info("Joining channels: {0}".format(self.channels))
        for chan in self.channels:
            self.join_twitch_channel(chan)

    def join(self):
        self.irc_client.asynloop_thread.join()

    def stop_all(self):
        self.active = False
        self.irc_client.stop()
        for task in self.repeating_tasks.values():
            task.stop()

    def join_twitch_channel(self, channel: str):
        self.state[channel] = self.state.get(channel, dict())
        # Turn bot off when joining a channel (except for functional and chat messages)
        # if it doesn't have a state yet for that channel.
        if len(self.state[channel]) == 0:
            self.toggle_channel(channel, ToggleType.OFF)
        self.logger.info('Joining channel {0}'.format(channel))
        channels = self.channels
        if channel not in channels:
            channels.append(channel)
        self.channels = channels
        client = self.irc_client
        client.send_message("JOIN #" + channel.lower() + "\r\n")

    def leave_twitch_channel(self, channel: str):
        self.logger.info('Leaving channel {0}'.format(channel))
        client = self.irc_client
        client.send_message("PART #" + channel.lower() + "\r\n")
        channels = self.channels
        updated_channels = [chan for chan in channels if chan != channel]
        self.channels = updated_channels

    def toggle_channel(self, channel, toggle_type: ToggleType):
        if toggle_type == ToggleType.ON:
            for tipe in ToggleType:
                if tipe.value >= TOGGLEABLE:
                    self.state[channel][tipe.name] = "True"
        elif toggle_type == ToggleType.OFF:
            for tipe in ToggleType:
                if tipe.value >= TOGGLEABLE:
                    self.state[channel][tipe.name] = "False"
        else:
            self.state[channel][toggle_type.name] = str(not convert(self.state.get(channel).get(toggle_type.name)))

    def send_message(self, message: Message):
        if self.can_send_type(message.channel, message.type) and count_capitals(message.content) < 50:
            client = self.irc_client
            client.send_message(u'PRIVMSG #{0} :{1}\n'.format(message.channel, message.content))

    def can_send_type(self, channel, msg_type: MessageType):
        return convert(self.state.get(channel).get(msg_type.name, "True"))

    def handle_message(self, irc_message, client):
        """Handle incoming IRC messages"""
        self.logger.debug(irc_message)
        if self.check_message(irc_message):
            return
        elif self.check_join(irc_message):
            return
        elif self.check_part(irc_message):
            return
        elif self.check_clearchat(irc_message):
            return
        elif self.check_usernotice(irc_message):
            return
        elif self.check_ping(irc_message, client):
            return
        elif self.check_error(irc_message):
            return

    def check_error(self, irc_message):
        """Check for a login error notification and terminate if found"""
        if re.search(r":tmi.twitch.tv NOTICE \* :Error logging i.*", irc_message):
            self.logger.critical(
                "Error logging in to twitch irc, check your oauth and username are set correctly in config.txt!")
            self.stop_all()
            return True

    def check_join(self, irc_message):
        """Watch for successful channel join messages"""
        match = re.search(r':{0}!{0}@{0}\.tmi\.twitch\.tv JOIN #(.*)'.format(self.user), irc_message)
        if match:
            if match.group(1) in self.channels:
                self.logger.info("Joined channel {0} successfully".format(match.group(1)))
                return True

    def check_part(self, irc_message):
        """Watch for successful channel join messages"""
        match = re.search(r':{0}!{0}@{0}\.tmi\.twitch\.tv PART #(.*)'.format(self.user), irc_message)
        if match:
            self.logger.info("Left channel {0} successfully".format(match.group(1)))
            return True

    def check_usernotice(self, irc_message):
        """Parse out new twitch subscriber messages and then call... python subscribers"""
        if irc_message[0] == '@':
            arg_regx = r"([^=;]*)=([^ ;]*)"
            arg_regx = re.compile(arg_regx, re.UNICODE)
            args = dict(re.findall(arg_regx, irc_message[1:]))
            regex = (
                r'^@[^ ]* :tmi.twitch.tv'
                r' USERNOTICE #(?P<channel>[^ ]*)'  # channel
                r'((?: :)?(?P<message>.*))?')  # message
            regex = re.compile(regex, re.UNICODE)
            match = re.search(regex, irc_message)
            if match:
                args['channel'] = match.group(1)
                args['message'] = match.group(2)
                for func_name, func in self.notice.items():
                    func(self, args)
                return True

    def check_clearchat(self, irc_message):
        if irc_message[0] == '@':
            arg_regx = r"([^=;]*)=([^ ;]*)"
            arg_regx = re.compile(arg_regx, re.UNICODE)
            args = dict(re.findall(arg_regx, irc_message[1:]))
            regex = (
                r'^@[^ ]* :tmi.twitch.tv'
                r' CLEARCHAT #(?P<channel>[^ ]*)'  # channel
                r'((?: :)?(?P<message>.*))?')  # message
            regex = re.compile(regex, re.UNICODE)
            match = re.search(regex, irc_message)
            if match:
                args['channel'] = match.group(1)
                args['message'] = match.group(2)
                for func_name, func in self.clearchat.items():
                    func(self, args)
                return True

    @staticmethod
    def check_ping(irc_message, client):
        """Respond to ping messages or twitch boots us off"""
        if re.search(r"PING :tmi\.twitch\.tv", irc_message):
            message = "PING :pong\r\n"
            client.send_message(message)
            return True

    def check_message(self, irc_message):
        """Watch for chat messages and notifiy subsribers"""
        if irc_message[0] == "@":
            arg_regx = r"([^=;]*)=([^ ;]*)"
            arg_regx = re.compile(arg_regx, re.UNICODE)
            args = dict(re.findall(arg_regx, irc_message[1:]))
            regex = (r'^@[^ ]* :([^!]*)![^!]*@[^.]*.tmi.twitch.tv'  # username
                     r' PRIVMSG #([^ ]*)'  # channel
                     r' :(.*)')  # message
            regex = re.compile(regex, re.UNICODE)
            match = re.search(regex, irc_message)
            if match:
                args['username'] = match.group(1)
                args['channel'] = match.group(2)
                args['message'] = match.group(3)
                self.logger.debug(args["message"])
                if args["username"] == self.admin:
                    for func_name, func in self.admins.items():
                        func(self, args)
                if rbac.has_roles(args['username'], args['channel']):
                    funcs = rbac.get_allowed_functions(args['username'], args['channel'])
                    for func in funcs:
                        if func(self, args):
                            rbac.log_access(args, args['channel'])
                for func_name, func in self.returns.items():
                    if func(self, args):
                        return True
                for func_name, func in self.commands.items():
                    func(self, args)
                return True

    def backup_thread(self):
        while self.active:
            time.sleep(600)
            self.logger.info("Backup thread go BRRRRRRRR")
            self.save()

    def handle_commandline_input(self):
        while self.active:
            ans = input()
            match = re.match(r'send (.*)', ans)
            if ans == "save":
                self.save()
            elif ans == "stop":
                self.active = False
                self.save()
                self.stop_all()
            elif ans == "join":
                print("Which channel?")
                channel = input()
                self.join_twitch_channel(channel)
            elif ans == "leave":
                print("Which channel?")
                channel = input()
                if channel not in self.channels:
                    print("Not following {0}".format(channel))
                else:
                    self.leave_twitch_channel(channel)
            elif ans == "reload":
                commands.reload()
            elif ans == "state":
                print(self.state)
            elif ans == "db":
                print(commands.db)
            elif match:
                print("channel?")
                ans = input()
                if ans in self.channels:
                    msg = Message(match.group(1), MessageType.CHAT, ans)
                    self.send_message(msg)
            else:
                print("save\nstop\njoin\nleave\nreload\nstate\ndb\nsend (msg)")


MAX_SEND_RATE = 20
SEND_RATE_WITHIN_SECONDS = 30


class IrcClient(asynchat.async_chat, object):

    def __init__(self, server, message_callback):
        self.logger = logging.getLogger(name="tmi_client[{0}]".format(server))
        self.logger.info('TMI initializing')
        self.map = {}
        asynchat.async_chat.__init__(self, map=self.map)
        self.received_data = bytearray()
        servernport = server.split(":")
        self.server = servernport[0]
        self.port = int(servernport[1])
        self.set_terminator(b'\n')
        self.asynloop_thread = Thread(target=self.run)
        self.send_thread = Thread(target=self.send_loop)
        self.send_thread.daemon = True
        self.running = False
        self.message_callback = message_callback
        self.connected = False
        self.message_queue = Queue()
        self.messages_sent = []
        self.logger.info('TMI initialized')
        return

    def send_message(self, msg: str):
        self.message_queue.put(msg)

    def handle_connect(self):
        """Socket connected successfully"""
        self.connected = True

    def handle_error(self):
        if self.socket:
            self.close()
        raise

    def collect_incoming_data(self, data):
        """Dump recieved data into a buffer"""
        self.received_data += data

    def found_terminator(self):
        """Processes each line of text received from the IRC server."""
        txt = self.received_data.rstrip(b'\r')  # accept RFC-compliant and non-RFC-compliant lines.
        del self.received_data[:]
        self.message_callback(txt.decode("utf-8"), self)

    def start(self):
        """Connect start message watching thread"""
        if not self.asynloop_thread.is_alive():
            self.running = True
            self.asynloop_thread = Thread(target=self.run)
            self.asynloop_thread.daemon = True
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connect((self.server, self.port))
            self.asynloop_thread.start()

            self.send_thread.start()

        else:
            self.logger.critical("Already running can't run twice")

    def stop(self):
        """Terminate the message watching thread by killing the socket"""
        self.running = False
        if self.asynloop_thread.is_alive():
            if self.socket:
                self.close()
            try:
                self.asynloop_thread.join()
                self.send_thread.join()
            except RuntimeError as e:
                if str(e) == "cannot join current thread":
                    # this is thrown when joining the current thread and is ok.. for now"
                    pass
                else:
                    raise e

    def send_loop(self):
        while self.running:
            if len(self.messages_sent) < MAX_SEND_RATE:
                if not self.message_queue.empty():
                    to_send = self.message_queue.get()
                    self.push(to_send.encode("UTF-8"))
                    self.logger.info(to_send)
                    self.messages_sent.append(datetime.now())
                    time.sleep(random.randint(50, 150) / 100)
            else:
                time_cutoff = datetime.now() - timedelta(seconds=SEND_RATE_WITHIN_SECONDS)
                self.messages_sent = [dt for dt in self.messages_sent if dt < time_cutoff]

    def run(self):
        """Loop!"""
        try:
            asyncore.loop(map=self.map)
        finally:
            self.running = False
