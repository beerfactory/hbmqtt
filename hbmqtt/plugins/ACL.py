import asyncio
from hbmqtt.broker import BrokerContext


class NoPermissionException(Exception):
    pass


class AclPlugin:
    def __init__(self, context: BrokerContext):
        self.context = context
        self.auth_config = self.context.config['auth']
        self.listener_config = self.context.config['listeners']

    @asyncio.coroutine
    def subscribe(self, *args, **kwargs):
        return True

    @asyncio.coroutine
    def deliver(self,*args, **kwargs):
        return False
