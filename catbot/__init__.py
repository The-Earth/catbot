from dataclasses import dataclass
import json
import logging
import threading
import time
from typing import Callable, Any, Optional

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
    def __init__(self, config: dict = None, config_path: str = None):
        if config_path is None:
            self.config = config
            self.config_path = ''
        else:
            self.config = json.load(open(config_path, 'r', encoding='utf-8'))
            self.config_path = config_path
        self.token: str = self.config['token']
        self.base_url = 'https://api.telegram.org/bot' + self.token + '/'
        if 'record' in self.config:
            try:
                self.record = json.load(open(self.config['record'], 'r', encoding='utf-8'))
            except FileNotFoundError:
                self.record = {}
        else:
            self.record = None

        if 'proxy' in self.config and self.config['proxy']['enable']:
            self.proxies = {'https': self.config['proxy']['proxy_url']}
        else:
            self.proxies = {}
        get_me_resp = self.api('getMe', data={})

        super().__init__(get_me_resp)

        self.can_join_groups: bool = get_me_resp['can_join_groups']
        self.can_read_all_group_messages: bool = get_me_resp['can_read_all_group_messages']
        self.supports_inline_queries: bool = get_me_resp['supports_inline_queries']

        self.msg_tasks: list[tuple[Callable, Callable, dict]] = []
        self.query_tasks: list[tuple[Callable, Callable, dict]] = []
        self.member_status_tasks: list[tuple[Callable, Callable, dict]] = []
        self.my_member_status_tasks: list[tuple[Callable, Callable, dict]] = []
        self.chat_join_request_tasks: list[tuple[Callable, Callable, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save_config_and_record()

    def save_config_and_record(self):
        if self.config_path:
            json.dump(self.config, open(self.config_path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        if self.record:
            json.dump(self.record, open(self.config['record'], 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

    def api(self, action: str, data: dict, timeout=60):
        resp = requests.post(self.base_url + action, json=data, timeout=timeout, proxies=self.proxies).json()
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
                           'chat_member',  # Available
                           'chat_join_request'  # Available
                       ]}
        updates = self.api('getUpdates', update_data, timeout=timeout + 10)
        logging.debug(updates)
        return updates

    def add_msg_task(
            self,
            criteria: Callable[["Message"], bool],
            action: Callable[["Message"], None],
            **action_kw
    ):
        """
        Add tasks for the bot to process. For message updates only. Use add_query_task for callback query updates.
        :param criteria:
            A function that leads flow of program into "action" function. It should take a Message-like object as the
            only argument and returns a bool. When it returns True, "action" will be executed. An example is to return
            True if the message starts with "/start", which is the standard starting of private chats with users.
        :param action:
            A function to be executed when criteria returns True. Typically, it's the response on users' actions.
            It should take a Message-like object as the only positional argument and accept keyword arguments. Arguments
            in action_kw will be passed to it.
        :param action_kw:
            Keyword arguments that will be passed to action when it is called.
        :return:
        """
        self.msg_tasks.append((criteria, action, action_kw))
        logging.warning("Bot.add_msg_task() is deprecated. Please use @Bot.msg_task instead.")

    def msg_task(self, criteria: Callable[["Message"], bool]):
        """
        Tag a function as action function for message updates.
        :param criteria:
            A function that leads flow of program into "action" function. It should take a Message-like object as the
            only argument and returns a bool. When it returns True, "action" will be executed. An example is to return
            True if the message starts with "/start", which is the standard starting of private chats with users.
        :return:
        """

        def decorator(action: Callable[["Message"], None]) -> Callable[["Message"], None]:
            self.msg_tasks.append((criteria, action, {}))
            return action

        return decorator

    def add_query_task(
            self,
            criteria: Callable[["CallbackQuery"], bool],
            action: Callable[["CallbackQuery"], None],
            **action_kw
    ):
        """
        Similar to add_msg_task, which add criteria and action for callback queries, typically clicks from
        in-message buttons (I would like to call them in-message instead of inline, which is used by Telegram).
        """
        self.query_tasks.append((criteria, action, action_kw))

    def query_task(self, criteria: Callable[["CallbackQuery"], bool]):
        """
        Similar to msg_Task, which tag an action function for callback queries, typically clicks from
        in-message buttons (I would like to call them in-message instead of inline, which is used by Telegram).
        """

        def decorator(action: Callable[["CallbackQuery"], None]) -> Callable[["CallbackQuery"], None]:
            self.query_tasks.append((criteria, action, {}))
            return action

        return decorator

    def add_member_status_task(
            self,
            criteria: Callable[["ChatMemberUpdate"], bool],
            action: Callable[["ChatMemberUpdate"], None],
            **action_kw
    ):
        """
        Similar to add_msg_task, which add criteria and action for chat member updates.
        """
        self.member_status_tasks.append((criteria, action, action_kw))

    def member_status_task(self, criteria: Callable[["ChatMemberUpdate"], bool]):
        """
        Similar to msg_task, which add criteria and action for chat member updates.
        """

        def decorator(action: Callable[["ChatMemberUpdate"], None]) -> Callable[["ChatMemberUpdate"], None]:
            self.member_status_tasks.append((criteria, action, {}))
            return action

        return decorator

    def add_my_member_status_task(
            self,
            criteria: Callable[["ChatMemberUpdate"], bool],
            action: Callable[["ChatMemberUpdate"], None],
            **action_kw
    ):
        """
        Similar to add_msg_task, which add criteria and action for bot chat member updates.
        """
        self.my_member_status_tasks.append((criteria, action, action_kw))

    def my_member_status_task(self, criteria: Callable[["ChatMemberUpdate"], bool]):
        """
        Similar to msg_task, which add criteria and action for bot chat member updates.
        """

        def decorator(action: Callable[["ChatMemberUpdate"], None]) -> Callable[["ChatMemberUpdate"], None]:
            self.my_member_status_tasks.append((criteria, action, {}))
            return action

        return decorator

    def add_chat_join_request_task(
            self, criteria: Callable[["ChatJoinRequestUpdate"], bool],
            action: Callable[["ChatJoinRequestUpdate"], None],
            **action_kw
    ):
        """
        Similar to add_msg_task, which add criteria and action for bot chat join request updates.
        """
        self.chat_join_request_tasks.append((criteria, action, action_kw))

    def chat_join_request_task(self, criteria: Callable[["ChatJoinRequestUpdate"], bool]):
        """
        Similar to msg_task, which add criteria and action for bot chat join request updates.
        """

        def decorator(action: Callable[["ChatJoinRequestUpdate"], None]) -> Callable[["ChatJoinRequestUpdate"], None]:
            self.chat_join_request_tasks.append((criteria, action, {}))
            return action

        return decorator

    def start(self, stop_event=None, print_log=False, timeout=60):
        old_updates = self.get_updates(offset=0, timeout=0)
        update_offset = old_updates[-1]['update_id'] + 1 if old_updates else 0
        while stop_event is None or not stop_event.is_set():
            try:
                updates = self.get_updates(offset=update_offset, timeout=timeout)
            except (APIError, requests.RequestException) as e:
                logging.warning(e.args[0])
                continue

            for item in updates:
                if print_log:
                    print(item)
                update_offset = item['update_id'] + 1
                if 'message' in item:
                    msg = Message(item['message'])
                    for criteria, action, action_kw in self.msg_tasks:
                        if criteria(msg):
                            threading.Thread(target=action, args=(msg,), kwargs=action_kw).start()

                elif 'callback_query' in item:
                    query = CallbackQuery(item['callback_query'])
                    if not hasattr(query, 'msg'):
                        continue
                    for criteria, action, action_kw in self.query_tasks:
                        if criteria(query):
                            threading.Thread(target=action, args=(query,), kwargs=action_kw).start()

                elif 'chat_member' in item:
                    member_update = ChatMemberUpdate(item['chat_member'])
                    for criteria, action, action_kw in self.member_status_tasks:
                        if criteria(member_update):
                            threading.Thread(target=action, args=(member_update,), kwargs=action_kw).start()
                elif 'my_chat_member' in item:
                    member_update = ChatMemberUpdate(item['my_chat_member'])
                    for criteria, action, action_kw in self.my_member_status_tasks:
                        if criteria(member_update):
                            threading.Thread(target=action, args=(member_update,), kwargs=action_kw).start()

                elif 'chat_join_request' in item:
                    join_request_update = ChatJoinRequestUpdate(item['chat_join_request'])
                    for criteria, action, action_kw in self.chat_join_request_tasks:
                        if criteria(join_request_update):
                            threading.Thread(target=action, args=(join_request_update,), kwargs=action_kw).start()
                else:
                    continue

        self.save_config_and_record()

    def send_message(self, chat_id, text: str, **kw) -> "Message":
        """
        :param chat_id: Unique identifier for the target chat or username of the target channel
        :param text: Text of the message to be sent, 1-4096 characters after entities parsing.
                     For plain text, catbot will split text longer than 4000 into multiple messages.
        :param kw: Keyword arguments defined in Telegram bot api. See https://core.telegram.org/bots/api#sendmessage<br>
            General keywords:<br>
                - parse_mode: Optional. Should be one of MarkdownV2 or HTML or Markdown.<br>
                - disable_web_page_preview: Optional. Should be True or False. Disables link previews for links
                                            in this message.<br>
                - disable_notification: Optional. Should be True or False. Sends the message silently. Users will
                                        receive a notification with no sound.<br>
                - reply_to_message_id: Deprecated. Optional. If the message is a reply, ID of the original message.<br>
                - reply_parameters: Optional, Object of ReplyParameters. Description of the message to reply to
                - allow_sending_without_reply: Optional. Pass True, if the message should be sent even if the specified
                                               replied-to message is not found<br>
            For plain text messages:<br>
                - text: Text of the message to be sent, 1-4096 characters after entities parsing.<br>
                - reply_markup: Additional interface options. A JSON-serialized object for an inline keyboard,
                                custom reply keyboard, instructions to remove reply keyboard or to force a reply
                                from the user. A common content of this param is an InlineKeyboard object.<br>
        :return: Message sent or the last message sent for it's split.
        """
        if 'reply_markup' in kw:
            kw['reply_markup'] = kw['reply_markup'].parse()
        if 'reply_parameters' in kw:
            kw['reply_parameters'] = kw['reply_parameters'].to_dict()

        if len(text) > 4000 and 'parse_mode' not in kw:
            text_part = [text[i * 4000: (i + 1) * 4000] for i in range(len(text) // 4000 + 1)]
            sent_msg = None
            for i in range(len(text_part)):
                msg_payload = {
                    'chat_id': chat_id,
                    'text': text_part[i] + f'\n\n({i + 1} / {len(text_part)})',
                    **kw
                }
                sent_msg = Message(self.api('sendMessage', msg_payload))
                time.sleep(0.5)
        else:
            msg_payload = {'chat_id': chat_id, 'text': text, **kw}
            sent_msg = Message(self.api('sendMessage', msg_payload))
        return sent_msg

    def edit_message(self, chat_id, msg_id, **kw) -> "Message | None":
        if 'reply_markup' in kw:
            kw['reply_markup'] = kw['reply_markup'].parse()

        msg_kw = {'chat_id': chat_id, 'message_id': msg_id, **kw}
        try:
            return Message(self.api('editMessageText', msg_kw))
        except APIError as e:
            if 'message is not modified' in e.args[0]:
                pass
            elif 'message to edit not found' in e.args[0]:
                raise MessageNotFoundError from e
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
        return Message(self.api('forwardMessage', {
            'from_chat_id': from_chat_id,
            'chat_id': to_chat_id,
            'message_id': msg_id,
            'disable_notification': disable_notification
        }))

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
            raise api_error_transformer(e) from e
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
            chat_member = ChatMember(self.api('getChatMember', {
                'chat_id': chat_id,
                'user_id': user_id
            }), chat_id)
        except APIError as e:
            raise api_error_transformer(e) from e
        else:
            return chat_member

    def restrict_chat_member(
            self,
            chat_id,
            user_id,
            until: int = 5,
            use_independent_chat_permissions: bool = False,
            **permissions
    ) -> bool:
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
            - can_send_audios: Optional. True, if the user is allowed to send audios
            - can_send_documents: Optional. True, if the user is allowed to send documents
            - can_send_photos: Optional. True, if the user is allowed to send photos
            - can_send_videos: Optional. True, if the user is allowed to send videos
            - can_send_video_notes: Optional. True, if the user is allowed to send video notes
            - can_send_voice_notes: Optional. True, if the user is allowed to send voice notes
            - can_send_polls: Optional. True, if the user is allowed to send polls, implies can_send_messages
            - can_send_other_messages: Optional. True, if the user is allowed to send animations, games, stickers and
                                       use inline bots
            - can_add_web_page_previews: Optional. True, if the user is allowed to add web page previews to their
                                         messages
            - can_change_info: Optional. True, if the user is allowed to change the chat title, photo and other
                               settings. Ignored in public supergroups
            - can_invite_users: Optional. True, if the user is allowed to invite new users to the chat
            - can_pin_messages: Optional. True, if the user is allowed to pin messages. Ignored in public supergroups
        :param use_independent_chat_permissions: Pass True if chat permissions are set independently. Otherwise,
                                                 the can_send_other_messages and can_add_web_page_previews permissions
                                                 will imply the can_send_messages, can_send_audios, can_send_documents,
                                                 can_send_photos, can_send_videos, can_send_video_notes,
                                                 and can_send_voice_notes permissions; the can_send_polls permission
                                                 will imply the can_send_messages permission.
        :return: Return True on success, otherwise raise exception.
        """
        try:
            result = self.api('restrictChatMember', {
                'chat_id': chat_id,
                'user_id': user_id,
                'until_date': until,
                'use_independent_chat_permissions': use_independent_chat_permissions,
                'permissions': permissions
            })
        except APIError as e:
            raise api_error_transformer(e) from e
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
        return self.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until=until,
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )

    def lift_restrictions(self, chat_id, user_id) -> bool:
        """
        Lift all restrictions on specified user.
        :param chat_id: Unique identifier for the target chat or username of the target supergroup
        :param user_id: Unique identifier of the target user
        :return: Return True on success, otherwise raise exception.
        """
        return self.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until=int(time.time()) + 35,
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )

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
            raise api_error_transformer(e) from e
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
            raise api_error_transformer(e) from e
        else:
            return result

    def delete_message(self, chat_id, msg_id) -> bool:
        try:
            result = self.api('deleteMessage', {'chat_id': chat_id, 'message_id': msg_id})
        except APIError as e:
            raise api_error_transformer(e) from e
        else:
            return result

    def approve_chat_join_request(self, chat_id, user_id) -> bool:
        try:
            result = self.api('approveChatJoinRequest', {'chat_id': chat_id, 'user_id': user_id})
        except APIError as e:
            raise api_error_transformer(e) from e
        else:
            return result

    def decline_chat_join_request(self, chat_id, user_id) -> bool:
        try:
            result = self.api('declineChatJoinRequest', {'chat_id': chat_id, 'user_id': user_id})
        except APIError as e:
            raise api_error_transformer(e) from e
        else:
            return result

    def get_file(self, file_id: str) -> "File | None":
        try:
            result = File(self.api('getFile', {'file_id': file_id}))
        except APIError as e:
            if 'invalid file_id' in e.args[0]:
                raise InvalidFileIdError from e
        else:
            return result

    def download(self, file: "File", path: str = None):
        """
        Download the file to path
        :param file: the File object to download
        :param path: optional, where downloaded content is saved
        :return: if path is not given, return byte buffer
        """
        if file.file_path:
            res = requests.get(f'https://api.telegram.org/file/bot{self.token}/{file.file_path}')
            if res.status_code == 200:
                content = res.content
            else:
                raise FilePathError(f'File path {file.file_path} error or expired.')
        else:
            raise FilePathError('File path not found.')
        if path:
            with open(path, 'wb') as f:
                f.write(content)
                return None
        else:
            return content

    """
    Methods below are bot-related utility methods which are not abstractions of Telegram apis.
    """

    def detect_command(self, cmd: str, msg: "Message", require_username=False) -> bool:
        """
        Detect two types of command (simple /cmd or /cmd@botname) that could be calling the bot.
        :param cmd: the command
        :param msg: incoming message to be checked
        :param require_username: True if only commands with username of the bot are detected, e.g. /start@somebot
                     False if all commands are considered
        :return: if one of two types of command is detected
        """
        if cmd in msg.commands and not require_username:
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
            if key in rec:
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

        # Admin privileges are False for non-admins
        self.is_anonymous = False
        self.can_be_edited = False
        self.can_delete_messages = False
        self.can_promote_members = False
        self.can_post_messages = False
        self.can_edit_messages = False
        self.can_pin_messages = False
        self.can_change_info = False
        self.can_invite_users = False
        self.custom_title: Optional[str] = None

        if self.status == 'administrator' or self.status == 'creator':
            self.is_anonymous: bool = member_json['is_anonymous']
            if 'custom_title' in member_json:
                self.custom_title: Optional[str] = member_json['custom_title']
        if self.status == 'administrator':
            self.can_be_edited: bool = member_json['can_be_edited']
            self.can_delete_messages: bool = member_json['can_delete_messages']
            self.can_promote_members: bool = member_json['can_promote_members']
            # If it is a channel
            if 'can_post_messages' in member_json:
                self.can_post_messages = member_json['can_post_messages']
                self.can_edit_messages = member_json['can_edit_messages']
            # If it is a group
            else:
                self.can_pin_messages = member_json['can_pin_messages']
        if self.status == 'administrator' or self.status == 'restricted':
            self.can_change_info: bool = member_json['can_change_info']
            self.can_invite_users: bool = member_json['can_invite_users']

        # Restricted actions are allowed for non-restricted users
        self.until_date: Optional[int] = None
        self.is_member = True
        self.can_send_messages = True
        self.can_send_audios = True
        self.can_send_documents = True
        self.can_send_photos = True
        self.can_send_videos = True
        self.can_send_video_notes = True
        self.can_send_voice_notes = True
        self.can_send_polls = True
        self.can_send_other_messages = True
        self.can_add_web_page_previews = True
        self.can_pin_messages = True

        if self.status == 'restricted':
            self.until_date: Optional[int] = member_json['until_date']
            self.is_member: bool = member_json['is_member']
            self.can_send_messages: bool = member_json['can_send_messages']
            self.can_send_audios: bool = member_json['can_send_audios']
            self.can_send_documents: bool = member_json['can_send_documents']
            self.can_send_photos: bool = member_json['can_send_photos']
            self.can_send_videos: bool = member_json['can_send_videos']
            self.can_send_video_notes: bool = member_json['can_send_video_notes']
            self.can_send_voice_notes: bool = member_json['can_send_voice_notes']
            self.can_send_polls: bool = member_json['can_send_polls']
            self.can_send_other_messages: bool = member_json['can_send_other_messages']  # sticker, gif and inline bot
            self.can_add_web_page_previews: bool = member_json['can_add_web_page_previews']  # "embed links" in client
            self.can_pin_messages: bool = member_json['can_pin_messages']
        if self.status == 'kicked':
            self.until_date: int = member_json['until_date']

    def __str__(self):
        return self.raw


class Message:
    def __init__(self, msg_json: dict):
        self.raw = msg_json
        self.chat = Chat(msg_json['chat'])
        self.id: int = msg_json['message_id']

        # Empty for message in channels
        if 'from' in msg_json:
            self.from_: Optional[User] = User(msg_json['from'])
        else:
            self.from_: Optional[User] = None

        if str(self.chat.id).startswith('-100'):
            self.link: str = f't.me/c/{str(self.chat.id).replace("-100", "")}/{self.id}'
        else:
            self.link: str = ''

        # The channel itself for channel messages. The supergroup itself for messages from anonymous group 
        # administrators. The linked channel for messages automatically forwarded to the discussion group
        if 'sender_chat' in msg_json:
            self.sender_chat: Optional[Chat] = Chat(msg_json['sender_chat'])
        else:
            self.sender_chat: Optional[Chat] = None
        self.date: int = msg_json['date']

        # Signature of the post author for messages in channels, or the custom title of an anonymous group administrator
        if 'author_signature' in msg_json:
            self.author_signature: Optional[str] = msg_json['author_signature']
        else:
            self.author_signature: Optional[str] = None

        if 'forward_from' in msg_json:
            # forwarded from users who allowed a link to their account in forwarded message
            self.forward_from: Optional[User] = User(msg_json['forward_from'])
            self.forward = True
        else:
            self.forward_from: Optional[User] = None
            self.forward = False
        if 'forward_sender_name' in msg_json:
            # forwarded from users who disallowed a link to their account in forwarded message
            self.forward_sender_name: Optional[str] = msg_json['forward_sender_name']
            self.forward = True
        else:
            self.forward_sender_name: Optional[str] = None
            self.forward = False
        if 'forward_from_message_id' in msg_json:
            # forwarded from channels
            self.forward_from_chat: Optional[Chat] = Chat(msg_json['forward_from_chat'])
            self.forward_from_message_id: Optional[int] = msg_json['forward_from_message_id']
            if 'forward_signature' in msg_json:
                self.forward_signature: Optional[str] = msg_json['forward_signature']
            else:
                self.forward_signature: Optional[str] = None
            self.forward = True
        else:
            self.forward_from_chat: Optional[Chat] = None
            self.forward_from_message_id: Optional[int] = None
            self.forward = False
        if 'forward_from_chat' in msg_json:
            # forwarded from anonymous admins
            self.forward_from_chat: Optional[Chat] = Chat(msg_json['forward_from_chat'])
            self.forward = True
        else:
            self.forward_from_chat: Optional[Chat] = None
            self.forward = False

        if self.forward:
            self.forward_date: Optional[int] = msg_json['forward_date']
        else:
            self.forward_date: Optional[int] = None

        if 'reply_to_message' in msg_json:
            self.reply_to_message: Optional[Message] = Message(msg_json['reply_to_message'])
            self.reply = True
        else:
            self.reply_to_message: Optional[Message] = None
            self.reply = False

        if 'edit_date' in msg_json:
            self.edit_date: Optional[int] = msg_json['edit_date']
            self.edit = True
        else:
            self.edit_date: Optional[int] = None
            self.edit = False

        if 'text' in msg_json:
            self.text: str = msg_json['text']
        elif 'caption' in msg_json:
            self.text: str = msg_json['caption']
        else:
            self.text: str = ''

        if 'photo' in msg_json:
            self.photo: Optional[list[PhotoSize]] = []
            self.has_photo = True
            for photo in msg_json['photo']:
                self.photo.append(PhotoSize(photo))
        else:
            self.photo: Optional[list[PhotoSize]] = None
            self.has_photo = False

        if 'new_chat_members' in msg_json:
            self.new_chat_members: Optional[list[User]] = []
            for user_json in msg_json['new_chat_members']:
                self.new_chat_members.append(User(user_json))
        else:
            self.new_chat_members: Optional[list[User]] = None

        if 'left_chat_member' in msg_json:
            self.left_chat_member: Optional[User] = User(msg_json['left_chat_member'])
        else:
            self.left_chat_member: Optional[User] = None

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
        if 'entities' in msg_json or 'caption_entities' in msg_json:
            entity_type = 'entities' if 'entities' in msg_json else 'caption_entities'
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

        if 'dice' in msg_json:
            self.dice = True
            self.dice_emoji: Optional[str] = msg_json['dice']['emoji']
            self.dice_value: Optional[int] = msg_json['dice']['value']
        else:
            self.dice = False
            self.dice_emoji: Optional[str] = None
            self.dice_value: Optional[str] = None

        if 'reply_markup' in msg_json:
            self.reply_markup: Optional[InlineKeyboard] = InlineKeyboard.from_json(msg_json['reply_markup'])
        else:
            self.reply_markup: Optional[InlineKeyboard] = None

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
        if 'url' in kwargs:
            self.url: str = kwargs['url']
        else:
            self.url = ''
        if 'callback_data' in kwargs:
            self.callback_data: str = kwargs['callback_data']
        else:
            self.callback_data: str = ''

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

        # Message with the callback button that originated the query.
        # Note that message content and message date will not be available if the message is too old
        if 'message' in query_json:
            self.msg: Optional[Message] = Message(query_json['message'])
        else:
            self.msg: Optional[Message] = None
        self.chat_instance: str = query_json['chat_instance']

        if 'data' in query_json:
            self.data: str = query_json['data']
        else:
            self.data = ''
        if 'inline_message_id' in query_json:
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


class ChatJoinRequestUpdate:
    def __init__(self, update_json: dict):
        self.raw = update_json
        self.chat = Chat(update_json['chat'])
        self.from_ = User(update_json['from'])
        self.user_chat_id: int = update_json['user_chat_id']
        self.date: int = update_json['date']
        if 'bio' in update_json:
            self.bio: Optional[str] = update_json['bio']
        else:
            self.bio: Optional[str] = None
        if 'invite_link' in update_json:
            self.invite_link: Optional[ChatInviteLink] = ChatInviteLink(update_json['invite_link'])
        else:
            self.invite_link: Optional[ChatInviteLink] = None

    def __str__(self):
        return str(self.raw)


class ChatInviteLink:
    def __init__(self, link_json: dict):
        self.raw = link_json
        self.invite_link = link_json['invite_link']
        self.creator = User(link_json['creator'])
        self.creates_join_request: bool = link_json['creates_join_request']
        self.is_primary: bool = link_json['is_primary']
        self.is_revoked: bool = link_json['is_revoked']
        if 'name' in link_json:
            self.name: Optional[str] = link_json['name']
        else:
            self.name: Optional[int] = None
        if 'expire_date' in link_json:
            self.expire_date: Optional[int] = link_json['expire_date']
        else:
            self.expire_date: Optional[int] = None
        if 'member_limit' in link_json:
            self.member_limit: Optional[int] = link_json['member_limit']
        else:
            self.member_limit: Optional[int] = None
        if 'pending_join_request_count' in link_json:
            self.pending_join_request_count: Optional[int] = link_json['pending_join_request_count']
        else:
            self.pending_join_request_count: Optional[int] = None

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
            if 'last_name' in chat_json:
                self.name = f'{chat_json["first_name"]} {chat_json["last_name"]}'
            else:
                self.name = chat_json['first_name']

        if 'username' in chat_json:
            self.username: str = chat_json['username']
            self.link = 't.me/' + self.username
        else:
            self.username = ''
            self.link = ''

        # Returned by get_chat
        if 'bio' in chat_json:
            # If the chat is private chat
            self.bio: Optional[str] = chat_json['bio']
        else:
            self.bio: Optional[str] = None
        if 'description' in chat_json:
            # If the chat is group, supergroup or channel
            self.description: Optional[str] = chat_json['description']
        else:
            self.description: Optional[str] = None
        if 'pinned_message' in chat_json:
            self.pinned_message: Optional[Message] = Message(chat_json['pinned_message'])
        else:
            self.pinned_message: Optional[Message] = None
        if 'slow_mode_delay' in chat_json:
            # If the chat is supergroup
            self.slow_mode_delay: int = chat_json['slow_mode_delay']
        else:
            self.slow_mode_delay = 0
        if 'join_by_request' in chat_json:
            self.join_by_request: bool = chat_json['join_by_request']
        else:
            self.join_by_request = False
        if 'linked_chat_id' in chat_json:
            # If the supergroup or channel has a linked channel or supergroup, respectively
            self.linked_chat_id: Optional[int] = chat_json['linked_chat_id']
        else:
            self.linked_chat_id: Optional[int] = None
        if 'invite_link' in chat_json:
            self.invite_link: Optional[str] = chat_json['invite_link']
        else:
            self.invite_link: Optional[str] = None

    def __str__(self):
        return str(self.raw)


class File:
    def __init__(self, file_json: dict):
        self.file_id: str = file_json['file_id']
        self.file_unique_id: str = file_json['file_unique_id']
        if 'file_size' in file_json:
            self.file_size: int = file_json['file_size']
        else:
            self.file_size = -1
        if 'file_path' in file_json:
            self.file_path: str = file_json['file_path']
        else:
            self.file_path = ''


class PhotoSize:
    def __init__(self, photo_json: dict):
        self.file_id: str = photo_json['file_id']
        self.file_unique_id: str = photo_json['file_unique_id']
        self.width: int = photo_json['width']
        self.height: int = photo_json['height']
        if 'file_size' in photo_json:
            self.file_size: int = photo_json['file_size']
        else:
            self.file_size = -1


@dataclass(kw_only=True)
class ReplyParameters:
    """
    Describes reply parameters for the message that is being sent.
    https://core.telegram.org/bots/api#replyparameters

    :param message_id Identifier of the message that will be replied to in the current chat, or in the chat
        chat_id if it is specified
    :param chat_id or String Optional. If the message to be replied to is from a different chat, unique
        identifier for the chat or username of the channel (in the format @channelusername). Not supported for
        messages sent on behalf of a business account and messages from channel direct messages chats.
    :param allow_sending_without_reply Optional. Pass True if the message should be sent even if the specified
        message to be replied to is not found. Always False for replies in another chat or forum topic. Always True
        for messages sent on behalf of a business account.
    :param quote Optional. Quoted part of the message to be replied to; 0-1024 characters after entities parsing.
        The quote must be an exact substring of the message to be replied to, including bold, italic, underline,
        strikethrough, spoiler, and custom_emoji entities. The message will fail to send if the quote isn't found
         in the original message.
    :param quote_parse_mode Optional. Mode for parsing entities in the quote. See formatting options for more details.
    :param quote_entities of MessageEntity Optional. A JSON-serialized list of special entities that appear in
        the quote. It can be specified instead of quote_parse_mode.
    :param quote_position Optional. Position of the quote in the original message in UTF-16 code units
    :param checklist_task_id Optional. Identifier of the specific checklist task to be replied to
    """
    message_id: int
    chat_id: int | None = None
    allow_sending_without_reply: bool | None = None
    quote: str | None = None
    quote_parse_mode: str | None = None
    quote_entities: list[dict] | None = None
    quote_position: int | None = None
    checklist_task_id: int | None = None


    def to_dict(self) -> dict[str, Any]:
        result = {}
        for key in self.__dict__:
            if self.__dict__[key] is not None:
                result[key] = self.__dict__[key]
        return result


class APIError(Exception):
    pass


class UserNotFoundError(APIError):
    pass


class ChatNotFoundError(APIError):
    pass


class MessageNotFoundError(APIError):
    pass


class InsufficientRightError(APIError):
    pass


class RestrictAdminError(APIError):
    pass


class DeleteMessageError(APIError):
    pass


class InvalidFileIdError(APIError):
    pass


class FilePathError(APIError):
    pass


class JoinRequestNotFoundError(APIError):
    pass


class JoinRequestUserAlreadyParticipantError(APIError):
    pass


def api_error_transformer(e: APIError) -> APIError:
    if 'Bad Request: not enough rights to restrict/unrestrict chat member' in e.args[0]:
        return InsufficientRightError(e.args[0])
    elif 'Bad Request: user not found' in e.args[0]:
        return UserNotFoundError(e.args[0])
    elif 'Bad Request: user is an administrator' in e.args[0] or \
            'Bad Request: can\'t remove chat owner' in e.args[0] or \
            'Bad Request: not enough rights' in e.args[0]:
        return RestrictAdminError(e.args[0])
    elif 'Bad Request: message identifier is not specified' in e.args[0] or \
            'Bad Request: message can\'t be deleted' in e.args[0] or \
            'Bad Request: message to delete not found' in e.args[0]:
        return DeleteMessageError(e.args[0])
    elif 'Bad Request: USER_ALREADY_PARTICIPANT' in e.args[0]:
        return JoinRequestUserAlreadyParticipantError(e.args[0])
    elif 'Bad Request: USER_ID_INVALID' in e.args[0] or \
            'Bad Request: HIDE_REQUESTER_MISSING' in e.args[0]:
        return JoinRequestNotFoundError(e.args[0])
    elif 'Bad Request: chat not found' in e.args[0]:
        return ChatNotFoundError(e.args[0])
    else:
        return e
