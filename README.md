# catbot

这里是一个协助使用 Python 开发 Telegram 机器人的轮子。设计思想是简化 API 请求，通过直观的传参和属性调用完成 API 调用和信息获取。此外还有获取 Telegram Update 的功能。目前只实现了部分 API，并会随着作者自己的需求变化逐步增加覆盖面，但并不以实现全部 API 为目标。

## 安装

在 [Release](https://github.com/The-Earth/catbot/releases) 中下载 `catbot-x.tar.gz`，然后用 pip 安装：

```
pip install catbot-x.tar.gz
```

## 历史

catbot 最初是作者自己的[一个 Telegram 机器人](https://github.com/The-Earth/Cat-big-bot)的一部分代码，后来在其他地方也有用到。使用时请参考那个机器人的代码。

## 使用方法简述

尽管 API 的使用被简化了，但使用者仍然需要了解 [Telegram API](https://core.telegram.org/bots/api) 本身，确保知道自己在做什么。例如获取 Update 的部分，catbot 会将收到的新 Message 对象传给 client code，但需要 client code 自行处理里面的指令。

关于获取 Update，catbot 要求 client code 提供一个条件函数和一个动作函数。这两个函数都接收 Message 或 Callback_query 对象作为参数。条件函数通过判断 Message 或 Callback_query 的内容、来源等信息来决定是否要作出反应，并返回 `True` 或 `False` 来告知 catbot。若决定要作出反应，catbot 会将这个 Message 或 Callback_query 交给动作函数来处理。

开始时在 client code 处建立一个配置文件 config.json ，内容参照 [config_example.json](config_example.json)。然后用下面这段代码创建 Bot 对象：

```python
import catbot
import json


config = json.load(open('config.json', 'r', encoding='utf-8'))
bot = catbot.Bot(config)
```

一组对应的条件和动作就是机器人的一个任务。假设已经写好了条件函数 `start_cri()` 和动作函数 `start()`，那么使用 `bot.add_msg_task(start_cri, start)`，机器人就会记录下这一组条件和动作。设置好所有的任务以后，使用 `bot.start()` 开始接收 Updates 并作出反应。

或者，您的任务只是单纯的推送消息，那么只要用前面的示例创建好 Bot 对象，然后在需要的地方使用 `bot.send_message(chat_id, text)` 即可。参数的填写可见代码内的注释及 Telegram API 文档。
