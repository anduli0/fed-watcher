"""Minimal sgmllib stub for feedparser on Python 3.11+ (sgmllib removed in 3.10).

Only the names feedparser touches at import time are provided.
"""
import re
from html.parser import HTMLParser


class SGMLParseError(Exception):
    pass


class SGMLParser(HTMLParser):
    pass


entityref = re.compile(r"&([a-zA-Z][-.a-zA-Z0-9]*)[^-a-zA-Z0-9]")
incomplete = re.compile(r"&[a-zA-Z#]")
interesting = re.compile(r"&|<")
shorttagopen = re.compile(r"<[a-zA-Z][-.a-zA-Z0-9]*/")
starttagopen = re.compile(r"<[>a-zA-Z]")
endbracket = re.compile(r"[<>]")
