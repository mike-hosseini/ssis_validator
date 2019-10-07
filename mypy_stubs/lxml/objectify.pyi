# source: https://github.com/JelleZijlstra/lxml-stubs

from typing import Any, Union

from lxml.etree import ElementBase, XMLParser

# dummy for missing stubs
def __getattr__(name) -> Any: ...

class ObjectifiedElement(ElementBase):
    pass

def fromstring(
    text: Union[bytes, str],
    parser: XMLParser = ...,
    *,
    base_url: Union[bytes, str] = ...
) -> ObjectifiedElement: ...