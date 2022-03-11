import json
import threading
import time
from typing import Callable, Any

import requests


class User:
    def __init__(self, user_json: dict):
        self.raw = user_json
        self.id: int = user_json['id']
        self.is_bot: bool = user_json['is_bot']
        if 'last_name' in user_json:
            self.name = f"{user_json['first_name']} {user_json['last_name']}"
        else:
            self.name = user_json['first_name']
        if 'username' in user_json:
            self.username: str = user_json['username']
            self.link = 't.me/' + self.username
        else:
            self.username = ''
            self.link = ''


class Bot(User):
    def __init__(self, config: dict):
        self.config = config
        self.token: str = self.config['token']
        self.base_url = 'https://api.telegram.org/bot' + self.token + '/'

        if 'proxy' in self.config and self.config['proxy']['enable']:
            self.proxy_kw = {'proxies': {'https': self.config['proxy']['proxy_url']}}
        else:
            self.proxy_kw = {}
        get_me_resp: dict = requests.get(self.base_url + 'getMe', **self.proxy_kw).json()

        if not get_me_resp['ok']:
            raise APIError('Bot initialization failed.' + get_me_resp['description'])

        super().__init__(get_me_resp['result'])

        self.can_join_groups: bool = get_me_resp['result']['can_join_groups']
        self.can_read_all_group_messages: bool = get_me_resp['result']['can_read_all_group_messages']
        self.supports_inline_queries: bool = get_me_resp['result']['supports_inline_queries']

        self.msg_tasks = []
        self.query_tasks = []
        self.member_status_tasks = []

    def api(self, action: str, data: dict):
        resp = requests.post(self.base_url + action, json=data, **self.proxy_kw).json()
        if not resp['ok']:
            raise APIError(f'API request "{action}" failed. {resp["description"]}')

        return resp['result']

    def get_updates(self, offset: int = 0, timeout: int = 60) -> list:
        update_data = {'offset': offset,
                       'timeout': timeout,
                       'allowed_updates': [
                           # Accept all updates, but only part of them are available in catbot
                           'message',  # Available
                           'edited_message',
                           'channel_post',
                           'edited_channel_post',
                           'inline_query',
                           'chosen_inline_result',
                           'callback_query',  # Available
                           'shipping_query',
                           'pre_checkout_query',
                           'poll',
                           'poll_answer',
                           'my_chat_member',
                           'chat_member'  # Available
                       ]}
        updates = self.api('getUpdates', update_data)
        print(updates)
        return updates

    def add_msg_task(self, criteria: Callable[["Message"], bool], action: Callable[["Message"], None], **action_kw):
        """
        Add tasks for the bot to process. For message updates only. Use add_query_task for callback query updates.
        :param criteria:
            A function that lead flow of program into "action" function. It should take a Message-like object as the
            only argument and returns a bool. When it returns True, "action" will be executed. An example is to return
            True if the message starts with "/start", which is the standard starting of private chats with users.
        :param action:
            A function to be executed when criteria returns True. Typically it's the response on users' actions.
            It should take a Message-like object as the only positional argument and accept keyword arguments. Arguments
            in action_kw will be passed to it.
        :param action_kw:
            Keyword arguments that will be passed to action when it is called.
        :return:
        """
        self.msg_tasks.append((criteria, action, action_kw))

    def add_query_task(self, criteria: Callable[["CallbackQuery"], bool],
                       action: [["CallbackQuery", None]], **action_kw):
        """
        Similar to add_msg_task, which add criteria and action for callback queries, typically clicks from
        in-message buttons (I would like to call them in-message instead of inline, which is used by Telegram).
        """
        self.query_tasks.append((criteria, action, action_kw))

    def add_member_status_task(self, criteria: Callable[["ChatMemberUpdate"], bool],
                               action: [["ChatMemberUpdate"], None], **action_kw):
        """
        Similar to add_msg_task, which add criteria and action for chat member updates.
        """
        self.member_status_tasks.append((criteria, action, action_kw))

    def start(self):
        old_updates = self.get_updates(timeout=0)
        update_offset = old_updates[-1]['update_id'] + 1 if old_updates else 0
        while True:
            try:
                updates = self.get_updates(update_offset)
            except (APIError, requests.ConnectionError) as e:
                print(e.args[0])
                continue

            for item in updates:
                update_offset = item['update_id'] + 1
                if 'message' in item.keys():
                    msg = Message(item['message'])
                    for criteria, action, action_kw in self.msg_tasks:
                        if criteria(msg):
                            threading.Thread(target=action, args=(msg,), kwargs=action_kw).start()

                elif 'callback_query' in item.keys():
                    query = CallbackQuery(item['callback_query'])
                    if not hasattr(query, 'msg'):
                        continue
                    for criteria, action, action_kw in self.query_tasks:
                        if criteria(query):
                            threading.Thread(target=action, args=(query,), kwargs=action_kw).start()

                elif 'chat_member' in item.keys():
                    member_update = ChatMemberUpdate(item['chat_member'])
                    for criteria, action, action_kw in self.member_status_tasks:
                        if criteria(member_update):
                            threading.Thread(target=action, args=(member_update,), kwargs=action_kw).start()

                else:
                    continue

    def send_message(self, chat_id, **kw) -> "Message":
        """
        :param chat_id: Unique identifier for the target chat or username of the target channel
        :param kw: Keyword arguments defined in Telegram bot api. See https://core.telegram.org/bots/api#sendmessage<br>
            General keywords:<br>
                - parse_mode: Optional. Should be one of MarkdownV2 or HTML or Markdown.<br>
                - disable_web_page_preview: Optional. Should be True or False. Disables link previews for links
                                            in this message.<br>
                - disable_notification: Optional. Should be True or False. Sends the message silently. Users will
                                        receive a notification with no sound.<br>
                - reply_to_message_id: Optional. If the message is a reply, ID of the original message.<br>
                - allow_sending_without_reply: Optional. Pass True, if the message should be sent even if the specified
                                               replied-to message is not found<br>
            For plain text messages:<br>
                - text: Text of the message to be sent, 1-4096 characters after entities parsing.<br>
                - reply_markup: Additional interface options. A JSON-serialized object for an inline keyboard,
                                custom reply keyboard, instructions to remove reply keyboard or to force a reply
                                from the user. A common content of this param is an InlineKeyboard object.<br>
        :return:
        """
        if 'reply_markup' in kw.keys():
            kw['reply_markup'] = kw['reply_markup'].parse()

        msg_kw = {'chat_id': chat_id, **kw}
        return Message(self.api('sendMessage', msg_kw))

    def edit_message(self, chat_id, msg_id, **kw) -> "Message":
        if 'reply_markup' in kw.keys():
            kw['reply_markup'] = kw['reply_markup'].parse()

        msg_kw = {'chat_id': chat_id, 'message_id': msg_id, **kw}
        try:
            return Message(self.api('editMessageText', msg_kw))
        except APIError as e:
            if 'message is not modified' in e.args[0]:
                pass
            else:
                raise

    def forward_message(self, from_chat_id, to_chat_id, msg_id, disable_notification=False) -> "Message":
        """
        :param from_chat_id: Unique identifier for the chat where the original message was sent
        :param to_chat_id: Unique identifier for the target chat or username of the target channel
        :param msg_id: Message identifier in the chat specified in from_chat_id
        :param disable_notification: Optional. Sends the message silently. Users will receive a
                                     notification with no sound.
        :return: The forwarded message.
        """
        return Message(self.api('forwardMessage', {'from_chat_id': from_chat_id,
                                                   'chat_id': to_chat_id,
                                                   'message_id': msg_id,
                                                   'disable_notification': disable_notification}))

    def answer_callback_query(self, callback_query_id: str, **kwargs) -> bool:
        """
        :param callback_query_id: callback_query_id you receive in callback_query
        :param kwargs: Keyword arguments defined in Telegram bot api. You should always call this method after receiving
                       a valid callback_query, even if you have nothing to send back to user.
                       See https://core.telegram.org/bots/api#answercallbackquery
               - text: Optional. Text of the notification. If not specified, nothing will be shown to the
                       user, 0-200 characters.
               - show_alert: Optional. If true, an alert will be shown by the client instead of a notification
                             at the top of the chat screen. Defaults to false.
               - cache_time: Optional. The maximum amount of time in seconds that the result of the callback
                             query may be cached client-side. Telegram apps will support caching starting
                             in version 3.14. Defaults to 0.
        :return:
        """
        return self.api('answerCallbackQuery', {'callback_query_id': callback_query_id, **kwargs})

    def get_chat(self, chat_id) -> "Chat":
        try:
            chat = Chat(self.api('getChat', {'chat_id': chat_id}))
        except APIError as e:
            if e.args[0] == 'Bad Request: chat not found':
                raise ChatNotFoundError
            else:
                raise
        else:
            return chat

    def get_chat_member(self, chat_id, user_id) -> "ChatMember":
        """
        Typically, use this method to build a ChatMember object.
        :param chat_id: ID of the chat that the ChatMember object will belong to.
        :param user_id: ID of the target user.
        :return: A ChatMember object, including info about permissions granted to the user in a specific chat.
        """
        try:
            chat_member = ChatMember(self.api('getChatMember', {'chat_id': chat_id, 'user_id': user_id}), chat_id)
        except APIError as e:
            if 'Bad Request: user not found' in e.args[0]:
                raise UserNotFoundError
            else:
                raise
        else:
            return chat_member

    def restrict_chat_member(self, chat_id, user_id, until: int = 5, **permissions) -> bool:
        """
        :param chat_id: Unique identifier for the target chat or username of the target supergroup
        :param user_id: Unique identifier of the target user
        :param until: Optional. Time when restrictions will be lifted for the user, unix time.
                      If user is restricted for more than 366 days or less than 30 seconds from the current time,
                      they are considered to be restricted forever.
                      Default: Forever
        :param permissions: Chat permissions defined in Telegram bot api. Left blank to restrict all actions except
                            reading.
                            See https://core.telegram.org/bots/api#chatpermissions
            - can_send_messages: Optional. True, if the user is allowed to send text messages, contacts, locations and
                                 venues
            - can_send_media_messages: Optional. True, if the user is allowed to send audios, documents, photos, videos,
                                       video notes and voice notes, implies can_send_messages
            - can_send_polls: Optional. True, if the user is allowed to send polls, implies can_send_messages
            - can_send_other_messages: Optional. True, if the user is allowed to send animations, games, stickers and
                                       use inline bots, implies can_send_media_messages
            - can_add_web_page_previews: Optional. True, if the user is allowed to add web page previews to their
                                         messages, implies can_send_media_messages
            - can_change_info: Optional. True, if the user is allowed to change the chat title, photo and other
                               settings. Ignored in public supergroups
            - can_invite_users: Optional. True, if the user is allowed to invite new users to the chat
            - can_pin_messages: Optional. True, if the user is allowed to pin messages. Ignored in public supergroups
        :return: Return True on success, otherwise raise exception.
        """
        try:
            result = self.api('restrictChatMember', {'chat_id': chat_id, 'user_id': user_id, 'until_date': until,
                                                     'permissions': permissions})
        except APIError as e:
            if 'Bad Request: not enough rights to restrict/unrestrict chat member' in e.args[0]:
                raise InsufficientRightError
            elif 'Bad Request: user not found' in e.args[0]:
                raise UserNotFoundError
            elif 'Bad Request: user is an administrator' in e.args[0] or \
                    'Bad Request: can\'t remove chat owner' in e.args[0] or \
                    'Bad Request: not enough rights' in e.args[0]:
                raise RestrictAdminError
            else:
                raise
        else:
            return result

    def silence_chat_member(self, chat_id, user_id, until: int = 5) -> bool:
        """
        Remove can_send_messages permission from specified user.
        :param chat_id: Unique identifier for the target chat or username of the target supergroup
        :param user_id: Unique identifier of the target user
        :param until: Optional. Time when restrictions will be lifted for the user, unix time.
                      If user is restricted for more than 366 days or less than 30 seconds from the current time,
                      they are considered to be restricted forever.
                      Default: Forever
        :return: Return True on success, otherwise raise exception.
        """
        try:
            result = self.api('restrictChatMember', {'chat_id': chat_id, 'user_id': user_id, 'until_date': until,
                                                     'permissions': {'can_send_messages': False}})
        except APIError as e:
            if 'Bad Request: not enough rights to restrict/unrestrict chat member' in e.args[0]:
                raise InsufficientRightError
            elif 'Bad Request: user not found' in e.args[0]:
                raise UserNotFoundError
            elif 'Bad Request: user is an administrator' in e.args[0] or \
                    'Bad Request: can\'t remove chat owner' in e.args[0] or \
                    'Bad Request: not enough rights' in e.args[0]:
                raise RestrictAdminError
            else:
                raise
        else:
            return result

    def lift_restrictions(self, chat_id, user_id) -> bool:
        """
        Lift all restrictions on specified user.
        :param chat_id: Unique identifier for the target chat or username of the target supergroup
        :param user_id: Unique identifier of the target user
        :return: Return True on success, otherwise raise exception.
        """
        try:
            result = self.api('restrictChatMember', {'chat_id': chat_id, 'user_id': user_id,
                                                     'permissions': {'can_send_messages': True,
                                                                     'can_send_media_messages': True,
                                                                     'can_send_polls': True,
                                                                     'can_send_other_messages': True,
                                                                     'can_add_web_page_previews': True,
                                                                     'can_change_info': True,
                                                                     'can_invite_users': True,
                                                                     'can_pin_messages': True}})
        except APIError as e:
            if 'Bad Request: not enough rights to restrict/unrestrict chat member' in e.args[0]:
                raise InsufficientRightError
            elif 'Bad Request: user not found' in e.args[0]:
                raise UserNotFoundError
            elif 'Bad Request: user is an administrator' in e.args[0] or \
                    'Bad Request: can\'t remove chat owner' in e.args[0] or \
                    'Bad Request: not enough rights' in e.args[0]:
                raise RestrictAdminError
            else:
                raise
        else:
            return result

    def kick_chat_member(self, chat_id, user_id, until: int = 0, no_ban: bool = False) -> bool:
        """
        Kick chat member out. See https://core.telegram.org/bots/api#kickchatmember
        :param chat_id: Unique identifier for the target chat or username of the target supergroup
        :param user_id: Unique identifier of the target user
        :param until: Optional, default 0 (infinite ban). Date when the user will be unbanned, unix time. If user is
                      banned for more than 366 days or less than 30 seconds from the current time they are considered
                      to be banned forever
        :param no_ban: Kick out and then allow the user to join or send messages (from channel or somewhere else)
        :return: Return True on success, otherwise raise exception.
        """
        try:
            if no_ban:
                # That the way Telegram API acts
                result = self.api('unbanChatMember', {'chat_id': chat_id, 'user_id': user_id})
            else:
                result = self.api('kickChatMember', {'chat_id': chat_id, 'user_id': user_id, 'until_date': until})
        except APIError as e:
            if 'Bad Request: not enough rights to restrict/unrestrict chat member' in e.args[0]:
                raise InsufficientRightError
            elif 'Bad Request: user not found' in e.args[0]:
                raise UserNotFoundError
            elif 'Bad Request: user is an administrator' in e.args[0] or \
                    'Bad Request: can\'t remove chat owner' in e.args[0] or \
                    'Bad Request: not enough rights' in e.args[0]:
                raise RestrictAdminError
            else:
                raise
        else:
            return result

    def unban_chat_member(self, chat_id, user_id) -> bool:
        """
        Unban a banned user. See https://core.telegram.org/bots/api#unbanchatmember
        :param chat_id: Unique identifier for the target chat or username of the target supergroup
        :param user_id: Unique identifier of the target user
        """
        try:
            result = self.api('unbanChatMember', {'chat_id': chat_id, 'user_id': user_id, 'only_if_banned': True})
        except APIError as e:
            if 'Bad Request: not enough rights to restrict/unrestrict chat member' in e.args[0]:
                raise InsufficientRightError
            elif 'Bad Request: user not found' in e.args[0]:
                raise UserNotFoundError
            elif 'Bad Request: user is an administrator' in e.args[0] or \
                    'Bad Request: can\'t remove chat owner' in e.args[0] or \
                    'Bad Request: not enough rights' in e.args[0]:
                raise RestrictAdminError
            else:
                raise
        else:
            return result

    def delete_message(self, chat_id, msg_id) -> bool:
        try:
            result = self.api('deleteMessage', {'chat_id': chat_id, 'message_id': msg_id})
        except APIError as e:
            if 'Bad Request: message to delete not found' in e.args[0] or \
                    'Bad Request: message can\'t be deleted' in e.args[0]:
                raise DeleteMessageError
            else:
                raise
        else:
            return result

    """
    Methods below are bot-related utility methods which are not abstractions of Telegram apis.
    """

    def detect_command(self, cmd: str, msg: "Message") -> bool:
        """
        Detect two types of command (simple /cmd or /cmd@botname) that could be calling the bot.
        :param cmd: the command
        :param msg: incoming message to be checked
        :return: if one of two types of command is detected
        """
        if cmd in msg.commands:
            return msg.text.startswith(cmd)
        elif f'{cmd}@{self.username}' in msg.commands:
            return msg.text.startswith(f'{cmd}@{self.username}')
        else:
            return False

    def lift_and_preserve_restriction(self, chat_id, user_id, restricted_until: int) -> None:
        """
        Lift restriction but preserve previous restriction if needed. This is a utility method used in many cases.
        :param chat_id: Unique identifier for the target chat
        :param user_id: Unique identifier of the target user
        :param restricted_until: Until date of the previous restriction. If it is 30 seconds or less late
                                 than current time then the restriction will be removed.
        """
        member = self.get_chat_member(chat_id, user_id)
        if member.status == 'kicked':
            return
        try:
            if restricted_until <= time.time() + 35 and restricted_until != 0:
                self.lift_restrictions(chat_id, user_id)
            else:
                self.silence_chat_member(chat_id, user_id, until=restricted_until)
        except RestrictAdminError:
            pass
        except InsufficientRightError:
            pass
        except UserNotFoundError:
            pass

    def secure_record_fetch(self, key: str, data_type: type, file: str = None) -> tuple[Any, dict[str, Any]]:
        """
        Securely read a record json file. Create file or json objects if needed.
        :param file: file path
        :param key: Name of the data you want in record file
        :param data_type: Type of the data. For example, if it is trusted user list, data_type will be list.
        :return: a tuple. The first element is the data you asked for. The second is the deserialized record file.
        """
        if file is None:
            file = self.config['record']
        try:
            rec = json.load(open(file, 'r', encoding='utf-8'))
        except FileNotFoundError:
            record_list, rec = data_type(), {}
            json.dump({key: record_list}, open(self.config['record'], 'w', encoding='utf-8'), indent=2,
                      ensure_ascii=False)
        else:
            if key in rec.keys():
                record_list = rec[key]
            else:
                record_list = data_type()

        return record_list, rec


class ChatMember(User):
    def __init__(self, member_json: dict, chat_id):
        """
        Typically, build a ChatMember object from Bot.get_chat_member() method, which automatically get corresponding
        Chat object.
        :param member_json: Raw response from "getChatMember" API
        :param chat_id: ID of the chat which this ChatMember belongs to.
        """
        super().__init__(member_json['user'])
        self.raw = f'{{"chat_member": {member_json}, "chat_id": {chat_id}}}'
        self.chat_id: int = chat_id
        # Can be “creator”, “administrator”, “member”, “restricted”, “left” or “kicked”
        self.status: str = member_json['status']
        if self.status == 'administrator' or self.status == 'creator':
            self.is_anonymous: str = member_json['is_anonymous']
        if self.status == 'administrator':
            self.can_be_edited: bool = member_json['can_be_edited']
            self.can_delete_messages: bool = member_json['can_delete_messages']
            self.can_promote_members: bool = member_json['can_promote_members']
        if self.status == 'administrator' or self.status == 'restricted':
            self.can_change_info: bool = member_json['can_change_info']
            self.can_invite_users: bool = member_json['can_invite_users']
        if self.status == 'restricted':
            self.until_date: int = member_json['until_date']
            self.is_member: bool = member_json['is_member']
            self.can_send_messages: bool = member_json['can_send_messages']
            self.can_send_media_messages: bool = member_json['can_send_media_messages']
            self.can_send_polls: bool = member_json['can_send_polls']
            self.can_send_other_messages: bool = member_json['can_send_other_messages']  # sticker, gif and inline bot
            self.can_add_web_page_previews: bool = member_json['can_add_web_page_previews']  # "embed links" in client
            self.can_pin_messages: bool = member_json['can_pin_messages']
        if self.status == 'kicked':
            self.until_date: int = member_json['until_date']

        if 'custom_title' in member_json.keys():
            self.custom_title: str = member_json['custom_title']

    def __str__(self):
        return self.raw


class Message:
    def __init__(self, msg_json: dict):
        self.raw = msg_json
        self.chat = Chat(msg_json['chat'])
        self.id: int = msg_json['message_id']

        # Empty for message in channels
        if 'from' in msg_json.keys():
            self.from_ = User(msg_json['from'])

        if str(self.chat.id).startswith('-100'):
            self.link = f't.me/c/{str(self.chat.id).replace("-100", "")}/{self.id}'
        else:
            self.link = ''

        # The channel itself for channel messages. The supergroup itself for messages from anonymous group 
        # administrators. The linked channel for messages automatically forwarded to the discussion group
        if 'sender_chat' in msg_json.keys():
            self.sender_chat = Chat(msg_json['sender_chat'])
        self.date: int = msg_json['date']

        # Signature of the post author for messages in channels, or the custom title of an anonymous group administrator
        if 'author_signature' in msg_json.keys():
            self.author_signature: str = msg_json['author_signature']

        if 'forward_from' in msg_json.keys():
            # forwarded from users who allowed a link to their account in forwarded message
            self.forward_from = User(msg_json['forward_from'])
            self.forward = True
        elif 'forward_sender_name' in msg_json.keys():
            # forwarded from users who disallowed a link to their account in forwarded message
            self.forward_sender_name: str = msg_json['forward_sender_name']
            self.forward = True
        elif 'forward_from_message_id' in msg_json.keys():
            # forwarded from channels
            self.forward_from_chat = Chat(msg_json['forward_from_chat'])
            self.forward_from_message_id: int = msg_json['forward_from_message_id']
            if 'forward_signature' in msg_json.keys():
                self.forward_signature: str = msg_json['forward_signature']
            else:
                self.forward_signature = ''
            self.forward = True
        elif 'forward_from_chat' in msg_json.keys():
            # forwarded from anonymous admins
            self.forward_from_chat = Chat(msg_json['forward_from_chat'])
            self.forward = True
        else:
            self.forward = False

        if self.forward:
            self.forward_date: int = msg_json['forward_date']

        if 'reply_to_message' in msg_json.keys():
            self.reply_to_message = Message(msg_json['reply_to_message'])
            self.reply = True
        else:
            self.reply = False

        if 'edit_date' in msg_json.keys():
            self.edit_date: int = msg_json['edit_date']
            self.edit = True
        else:
            self.edit = False

        if 'text' in msg_json.keys():
            self.text: str = msg_json['text']
        elif 'caption' in msg_json.keys():
            self.text: str = msg_json['caption']
        else:
            self.text: str = ''

        if 'new_chat_members' in msg_json.keys():
            self.new_chat_members: list[User] = []
            for user_json in msg_json['new_chat_members']:
                self.new_chat_members.append(User(user_json))

        if 'left_chat_member' in msg_json.keys():
            self.left_chat_member: User = User(msg_json['left_chat_member'])

        self.mentions = []
        self.hashtags = []
        self.cashtags = []
        self.commands = []
        self.links = []
        self.bolds = []
        self.italics = []
        self.underlines = []
        self.strikethroughs = []
        self.spoilers = []
        self.codes = []
        self.text_links = []
        self.text_mention = []
        self.html_formatted_text = self.text
        if 'entities' in msg_json.keys() or 'caption_entities' in msg_json.keys():
            entity_type = 'entities' if 'entities' in msg_json.keys() else 'caption_entities'
            entity_to_be_formatted = []
            for item in msg_json[entity_type]:
                offset = item['offset']
                length = item['length']
                if item['type'] == 'mention':
                    self.mentions.append(self.text[offset:offset + length])
                elif item['type'] == 'hashtag':
                    self.hashtags.append(self.text[offset:offset + length])
                elif item['type'] == 'cashtag':
                    self.cashtags.append(self.text[offset:offset + length])
                elif item['type'] == 'bot_command':
                    self.commands.append(self.text[offset:offset + length])
                elif item['type'] == 'url':
                    self.links.append(self.text[offset:offset + length])
                elif item['type'] == 'bold':
                    self.bolds.append(self.text[offset:offset + length])
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'italic':
                    self.italics.append(self.text[offset:offset + length])
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'underline':
                    self.underlines.append(self.text[offset:offset + length])
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'strikethrough':
                    self.strikethroughs.append(self.text[offset:offset + length])
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'spoiler':
                    self.spoilers.append(self.text[offset:offset + length])
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'code':
                    self.codes.append(self.text[offset:offset + length])
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'text_link':
                    self.text_links.append((self.text[offset:offset + length], item['url']))
                    entity_to_be_formatted.append(item)
                elif item['type'] == 'text_mention':
                    self.text_mention.append((self.text[offset:offset + length], User(item['user'])))
                    entity_to_be_formatted.append(item)

            entity_to_be_formatted = sorted(entity_to_be_formatted, key=lambda x: x['offset'], reverse=True)
            for item in entity_to_be_formatted:
                offset = item['offset']
                length = item['length']
                if item['type'] == 'bold':
                    self.html_formatted_text = self.text[:offset] + f'<b>{self.text[offset:offset + length]}</b>' + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'italic':
                    self.html_formatted_text = self.text[:offset] + f'<i>{self.text[offset:offset + length]}</i>' + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'underline':
                    self.html_formatted_text = self.text[:offset] + f'<u>{self.text[offset:offset + length]}</u>' + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'strikethrough':
                    self.html_formatted_text = self.text[:offset] + f'<s>{self.text[offset:offset + length]}</s>' + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'spoiler':
                    self.html_formatted_text = self.text[:offset] + \
                                               f'<tg-spoiler>{self.text[offset:offset + length]}</tg-spoiler>' + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'code':
                    self.html_formatted_text = self.text[:offset] + \
                                               f'<code>{self.text[offset:offset + length]}</code>' + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'text_link':
                    self.html_formatted_text = self.text[:offset] + f"<a href=\"{item['url']}\">" \
                                                                    f"{self.text[offset:offset + length]}</a>" + \
                                               self.html_formatted_text[offset + length:]
                elif item['type'] == 'text_mention':
                    self.html_formatted_text = self.text[:offset] + f"<a href=\"tg://user?id={item['user']['id']}\">" \
                                                                    f"{self.text[offset:offset + length]}</a>" + \
                                               self.html_formatted_text[offset + length:]

        if 'dice' in msg_json.keys():
            self.dice = True
            self.dice_emoji = msg_json['dice']['emoji']
            self.dice_value = msg_json['dice']['value']
        else:
            self.dice = False

        if 'reply_markup' in msg_json.keys():
            self.reply_markup: InlineKeyboard = InlineKeyboard.from_json(msg_json['reply_markup'])

    def __str__(self):
        return self.raw


class InlineKeyboardButton:
    def __init__(self, text: str, **kwargs):
        """
        :param text: Text showed on the button.
        :param kwargs: Other optional params defined in Telegram bot api.
                       See https://core.telegram.org/bots/api#inlinekeyboardbutton
            - url: Optional. HTTP or tg:// url to be opened when button is pressed
            - callback_data: Optional. Data to be sent in a callback query to the bot when button is pressed, 1-64 bytes
        """
        self.text = text
        if len(kwargs) == 0:
            raise APIError('Inline keyboard button must have either url or callback_data.')
        if 'url' in kwargs.keys():
            self.url = kwargs['url']
        if 'callback_data' in kwargs.keys():
            self.callback_data = kwargs['callback_data']

    @classmethod
    def from_json(cls, button_json: dict):
        return cls(**button_json)

    def parse(self) -> dict:
        """
        :return: self.__dict__ for follow-up usage like json serialization.
        """
        return self.__dict__


class InlineKeyboard:
    def __init__(self, key_list: list[list[InlineKeyboardButton]]):
        """
        :param key_list: Use InlineKeyBoardButton to structure the buttons you want and pass it into this
                         initializer. Each sublist represent a row. Buttons in the same sublist will be
                         placed in the same row.
        """
        self.key_list = key_list

    @classmethod
    def from_json(cls, markup_json: dict) -> "InlineKeyboard":
        markup_list: list[list[dict]] = markup_json['inline_keyboard']
        key_list: list[list[InlineKeyboardButton]] = []
        for i in range(len(markup_json)):
            key_list.append([])
            for j in range(len(markup_json)):
                key_list[i].append(InlineKeyboardButton.from_json(markup_list[i][j]))

        return cls(key_list)

    def parse(self) -> dict[str, list[list[dict]]]:
        key_list: list[list[dict]] = []
        for i in range(len(self.key_list)):
            key_list.append([])
            for j in range(len(self.key_list[i])):
                key_list[i].append(self.key_list[i][j].parse())

        return {'inline_keyboard': key_list}


class CallbackQuery:
    def __init__(self, query_json: dict):
        self.raw = query_json
        self.id: str = query_json['id']
        self.from_ = User(query_json['from'])
        if 'message' not in query_json.keys():
            self.msg = ''
        else:
            self.msg = Message(query_json['message'])
        self.chat_instance: str = query_json['chat_instance']
        if 'data' in query_json.keys():
            self.data: str = query_json['data']
        else:
            self.data = ''
        if 'inline_message_id' in query_json.keys():
            self.inline_message_id: str = query_json['inline_message_id']
        else:
            self.inline_message_id = ''

    def __str__(self):
        return self.raw


class ChatMemberUpdate:
    def __init__(self, update_json: dict):
        self.raw = update_json
        self.chat = Chat(update_json['chat'])
        self.from_ = User(update_json['from'])
        self.date: int = update_json['date']
        self.old_chat_member = ChatMember(update_json['old_chat_member'], self.chat.id)
        self.new_chat_member = ChatMember(update_json['new_chat_member'], self.chat.id)

    def __str__(self):
        return str(self.raw)


class Chat:
    def __init__(self, chat_json: dict):
        self.raw = chat_json
        self.id: int = chat_json['id']
        self.type: str = chat_json['type']

        if self.type == 'supergroup' or self.type == 'group' or self.type == 'channel':
            self.name: str = chat_json['title']
        else:
            if 'last_name' in chat_json.keys():
                self.name = f'{chat_json["first_name"]} {chat_json["last_name"]}'
            else:
                self.name = chat_json['first_name']

        if 'username' in chat_json.keys():
            self.username: str = chat_json['username']
            self.link = 't.me/' + self.username
        else:
            self.username = ''
            self.link = ''

        # Returned by get_chat
        if 'bio' in chat_json.keys():
            # If the chat is private chat
            self.bio: str = chat_json['bio']
        if 'description' in chat_json.keys():
            # If the chat is group, supergroup or channel
            self.description: str = chat_json['description']
        if 'pinned_message' in chat_json.keys():
            self.pinned_message = Message(chat_json['pinned_message'])
        if 'slow_mode_delay' in chat_json.keys():
            # If the chat is supergroup
            self.slow_mode_delay: int = chat_json['slow_mode_delay']
        if 'linked_chat_id' in chat_json.keys():
            # If the supergroup or channel has a linked channel or supergroup, respectively
            self.linked_chat_id: int = chat_json['linked_chat_id']

    def __str__(self):
        return str(self.raw)


class APIError(Exception):
    pass


class UserNotFoundError(APIError):
    pass


class ChatNotFoundError(APIError):
    pass


class InsufficientRightError(APIError):
    pass


class RestrictAdminError(APIError):
    pass


class DeleteMessageError(APIError):
    pass
