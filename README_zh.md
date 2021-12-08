# catbot

catbot 是一个多线程的 [Telegram](https://t.me) 机器人开发库，提供 [Telegram bot API](https://core.telegram.org/bots/api) 的 Python 接口，并帮助管理机器人收到的[新消息](https://core.telegram.org/bots/api#getting-updates) 。

## 安装

在 [Release](https://github.com/The-Earth/catbot/releases) 中下载 `catbot-x.tar.gz`，然后用 pip 安装：

```shell
pip install catbot-x.tar.gz
```

## 使用方法简述

使用 catbot 之前，先建立一个 json 配置文件（或者直接给初始化方法传入一个 dict）。必须的配置是机器人 token 和网络代理设置（见 [example config](config_example.json)）。如果您的机器人不需要使用代理，将 `proxy - enable` 设置为 `false` 即可。另外，您可以添加机器人可能用到的其他配置，例如一些用来自动回复的消息等等。

假设配置文件是 `config.json`，我们可以创建一个 bot 对象：

```python
import catbot
import json

config = json.load(open('config.json', 'r', encoding='utf-8'))
bot = catbot.Bot(config)
```

以下例子将创建一个自动回应私聊的 `/start` 指令的机器人。私聊中的 `/start` 是用户开始使用机器人的时候都会发送的指令。

首先，写一个函数来告诉 catbot 是否需要创建新线程来处理收到的消息。这个函数里应该只有一些简单快速的判断，以免阻塞机器人的运行。耗时较长的任务（数据库查询、网络请求等）应该放到后面的动作函数中，

```python
def start_cri(msg: catbot.Message) -> bool:
    return msg.chat.type == 'private' and msg.text == '/start'
```

这个函数会检查消息是否来自私聊，且内容为刚好是 `/start`。然后建立一个动作函数：

```python
def start(msg: catbot.Message):
    bot.send_message(chat_id=msg.chat.id, text='Hello')
```

这个函数会向收到 `/start` 的那个聊天中发送 `Hello`。最后，将这两个函数加入任务列表。需要注意的是，这个任务需要响应 Telegram 的 [Message](https://core.telegram.org/bots/api#message) 对象（也就是 catbot 中的 `Message` 类）。所以我们使用 `add_msg_task` 方法。（对于其他类型的事件， catbot 目前支持 [CallbackQuery](https://core.telegram.org/bots/api#callbackquery) 和 [ChatMemberUpdated](https://core.telegram.org/bots/api#chatmemberupdated) ，对应 `add_query_tast` 和 `add_member_status_task`。）

```python
bot.add_msg_task(start_cri, start)
```

最后启动机器人：

```python
bot.start()
```

## 更多

`Bot` 类的大多数方法（也就是机器人的动作）在代码中都有文档。一般来说，这些方法的参数和 [Telegram bot API](https://core.telegram.org/bots/api) 中的描述相同或非常相近。如果想要使用的方法 catbot 还不支持，也可以用 `bot.api(action: str, data: dict)` 直接调用原始 api。
