# catbot

catbot is a multithread library for [Telegram](https://t.me) bot development. It provides a Python interface for [Telegram bot API](https://core.telegram.org/bots/api) and manages [update steam](https://core.telegram.org/bots/api#getting-updates) for bot developers. 

## Installation

Find `catbot-x.tar.gz` in [release](https://github.com/The-Earth/catbot/releases), download the latest version and install it by 

```shell
pip install catbot-x.tar.gz
```

## Quick start

By using catbot, a configuration json file is needed (or alternatively pass a dict to the initializer). Necessary configurations are bot token and proxy settings (see [example config](config_example.json)). If your bot does not use proxy to access Telegram server, simple set `proxy - enable` to `false`. Other configs could be helpful, such as a set of messages for auto-reply.

Let's say your config file is `config.json`, then create a bot instance:

```python
import catbot
import json

config = json.load(open('config.json', 'r', encoding='utf-8'))
bot = catbot.Bot(config)
```

Let's start with auto-replying the `/start` command in private chat with users, which is the very beginning of interactions with users.

First, create a criteria function to tell catbot if there is a need to create a new thread to deal with the received message. Only simple and fast jobs should be put in this function in order not to block the main thread. Move time-consuming tasks (database querying, web requests) into action functions, which are running in separate threads.

```python
def start_cri(msg: catbot.Message) -> bool:
    return msg.chat.type == 'private' and msg.text == '/start'
```

This function checks whether the message is from a private chat and its content is exactly `/start`. Then we need an action function.

```python
def start(msg: catbot.Message):
    bot.send_message(chat_id=msg.chat.id, text='Hello')
```

This function send a `Hello` to the chat it received a `/start` from. Finally, add both two functions to task list. Notice that this task responds to [Message](https://core.telegram.org/bots/api#message) objects (also, `Message` class in catbot). So we use `add_msg_task` method here. (For other types of incoming events, catbot supports [CallbackQuery](https://core.telegram.org/bots/api#callbackquery) and [ChatMemberUpdated](https://core.telegram.org/bots/api#chatmemberupdated), with `add_query_task` and `add_member_status_task`.)

```python
bot.add_msg_task(start_cri, start)
```

And start the bot:

```python
bot.start()
```

## Go further

Most methods of the `Bot` class (actions of a bot) have their inline documents. Generally, arguments of the methods are just the same or very similar to what [Telegram bot API](https://core.telegram.org/bots/api) says. If your desired method is not supported by catbot yet, catbot provides support for raw api call by `bot.api(action: str, data: dict)`.
