import xmlrpc.client

class MultiCall(object):

    def __init__(self, xmlServerProxy):
        self._xmlServerProxy = xmlServerProxy
        self._attrs = []

    def __call__(self):
        if 'system.multiCall' in self._xmlServerProxy.system.listMethods():
            multicall = xmlrpc.client.MultiCall(self._xmlServerProxy)
        else:
            multicall = self._xmlServerProxy

        results = []
        for attr in self._attrs:
            currAttr = attr
            current = multicall.__getattr__(attr.name)
            while currAttr._child is not None:
                currAttr = currAttr._child
                current = current.__getattr__(currAttr.name)
            results.append(current.__call__(*currAttr._args))
        return results

    def __getattr__(self, name):
        cal = Callable(name)
        self._attrs.append(cal)
        return cal

class Callable(object):

    def __init__(self, name):
        self.name = name
        self._child = None

    def __call__(self, *args):
        self._args = args

    def __getattr__(self, name):
        self._child = Callable(name)
        return self._child
