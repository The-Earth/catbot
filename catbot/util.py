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
