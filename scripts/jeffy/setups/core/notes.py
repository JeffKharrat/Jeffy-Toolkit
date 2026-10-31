"""Teaching notes: one line on each node a wire creates, saying what the node does.

They live in Maya's own per-node **Notes** (the ``notes`` string attribute,
shown at the bottom of the Attribute Editor), so you can understand a wire
by clicking its nodes, in the Node Editor or the Outliner.
"""

from maya import cmds

ATTR = "notes"


def write(node, text):
    """Set ``node``'s Notes to ``text`` (adds the attribute when needed). Returns ``node``."""
    if not cmds.attributeQuery(ATTR, node=node, exists=True):
        cmds.addAttr(node, longName=ATTR, dataType="string")
    cmds.setAttr("%s.%s" % (node, ATTR), text, type="string")
    return node


def read(node):
    if not cmds.objExists(node) or not cmds.attributeQuery(ATTR, node=node, exists=True):
        return ""
    return cmds.getAttr("%s.%s" % (node, ATTR)) or ""
