def html_refer(ori: str) -> str:
    refer = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        '“': '&#8220;',
        '”': '&#8221;'
    }
    for k in refer:
        ori = ori.replace(k, refer[k])

    return ori
