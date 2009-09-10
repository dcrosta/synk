import sys

__all__ = ['as_map', 'as_tree', 'from_tree']

def as_map(sequence, key='id'):
    # return a map of the items in the sequence,
    # keyed by the given attribute
    return dict(zip(map(lambda x: x[key], sequence), sequence))

def as_tree(item_map, root_key='id', root_value='', parent_key='parent_id', order_key='seq', remove_keys=[]):
    # from a map of items keyed by the given attribute,
    # create a tree, where the children are stored in an
    # attribute "children"

    def add_children(root):
        id = root[root_key]
        kids = [item for item in item_map.itervalues() if item[parent_key] == id]
        kids.sort(key=lambda x: x.get(order_key, sys.maxint))
        
        for item in kids:
            add_children(item)

        root['children'] = kids

    roots = [item for item in item_map.itervalues() if item.get(parent_key, None) == root_value]
    for root in roots:
        add_children(root)

    # this works since the tree will have
    # references to the same items
    for item in item_map.itervalues():
        for key in remove_keys:
            if key in item:
                del item[key]

    return roots

def from_tree(tree, parent_key='id', child_parent_key='parent_id', order_key='seq', sort_keys=[]):
    # from a tree (as returned by as_tree) create a
    # list of the elements in the tree. each item's
    # "children" node will be removed. the elements
    # in the tree will be sorted according to the
    # sort orders defined in sort_keys
    #
    # also assigns seq and parent_id
    items = []

    def unroll(item, parent_id):
        item[child_parent_key] = parent_id
        items.append(item)
        id = item.get(parent_key, None)
        for seq, child in enumerate(item.get('children', [])):
            item[order_key] = seq
            unroll(child, id)
        if 'children' in item:
            del item['children']

    for seq, item in enumerate(tree):
        item[order_key] = seq
        unroll(item, '')

    for key in reversed(sort_keys):
        items.sort(key=lambda x: item.get(x, key, sys.maxint))

    return items

if __name__ == '__main__':
    class Thing(object):
        def __init__(self, id, parent_id, seq, **kwargs):
            self.id = id
            self.parent_id = parent_id
            self.seq = seq

            for key, value in kwargs.iteritems():
                setattr(self, key, value)

        def __repr__(self):
            return repr(self.__dict__)

    items = []
    items.append(Thing('1', '', 1, foo='foo'))
    items.append(Thing('2', '', 2, foo='bar'))
    items.append(Thing('3', '1', 1, foo='baz'))
    items.append(Thing('4', '1', 2, foo='FOO'))
    items.append(Thing('5', '1', 3, foo='BAR'))
    items.append(Thing('6', '2', 1, foo='BAZ'))
    items = as_map(items)

    tree = as_tree(items)

    import pprint
    pprint.pprint(tree, indent=4)

    unrolled = from_tree(tree, sort_keys=['parent_id', 'seq'])
    pprint.pprint(unrolled)

