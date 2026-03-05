def html_escape(ori: str) -> str:
    escape = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        '“': '&#8220;',
        '”': '&#8221;'
    }
    for k in escape:
        ori = ori.replace(k, escape[k])

    return ori


def partly_hide_name(name: str) -> str:
    """
    Partly hide text, typically usernames
    Transplant from mosaic funciton by policr-mini
    """
    if not name:
        return ""

    name_len = len(name)

    # 1个字符 - 不处理
    if name_len == 1:
        return html_escape(name)

    # 2个字符
    if name_len == 2:
        first = html_escape(name[0])
        second = html_escape(name[1])
        return f"{first}<tg-spoiler>{second}</tg-spoiler>"

    # 3个字符及以上
    first = html_escape(name[0])
    middle = html_escape(name[1:-1])
    last = html_escape(name[-1])
    return f"{first}<tg-spoiler>{middle}</tg-spoiler>{last}"
