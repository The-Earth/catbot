def html_refer(ori: str) -> str:
    refer = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;'
    }
    for k in refer:
        ori = ori.replace(k, refer[k])

    return ori
