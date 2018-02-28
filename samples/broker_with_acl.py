import asyncio
import logging
import redis
from hbmqtt.broker import Broker
from trans import Trans
from apnsTrans import APNsTrans
import json

logger = logging.getLogger(__name__)

config = {
    'listeners': {
        'internal': {
            'type': 'tcp',
            'bind': '127.0.0.1:1883',
            'subscribe_acl_plugins': None,
            'deliver_acl_plugins': None,
        },
        'default': {
            'type': 'tcp',
            'bind': '0.0.0.0:8883',
            'ssl': 'off',
            'subscribe_acl_plugins': ['acl'],
            'deliver_acl_plugins': ['acl'],
            # 'certfile': 'server.crt',
            # 'keyfile': 'server.key',
        }
    },
    'sys_interval': 1,
    'auth': {
        'allow-anonymous': False,
        'user-db-connect-pool': redis.ConnectionPool(host="localhost", port=6379, db=1),
        'plugins': []

    }
}

broker = Broker(config)


@asyncio.coroutine
def start_broker():
    yield from broker.start()


def start_mqtt_trans():
    trans_thread = Trans()
    trans_thread.start()


def start_apns_trans():
    connection = redis.Redis(connection_pool=config['auth']['user-db-connect-pool'])
    apps = connection.lrange('apps', 0, -1)
    for app in apps:
        _app = json.loads(app.decode('utf8'))
        appid = _app['id']
        cert = _app['cert']
        key = _app['key']
        sandbox = _app['sandbox']
        topic = _app['topic']
        apns_trans = APNsTrans(appid, cert, key, topic, sandbox)
        apns_trans.start()


broker = Broker(config)

@asyncio.coroutine
def test_coro():
    yield from broker.start()
    #yield from asyncio.sleep(5)
    #yield from broker.shutdown()


if __name__ == '__main__':
    formatter = "[%(asctime)s] :: %(levelname)s :: %(name)s :: %(message)s"
    #formatter = "%(asctime)s :: %(levelname)s :: %(message)s"
    logging.basicConfig(level=logging.INFO, format=formatter)
    asyncio.get_event_loop().run_until_complete(test_coro())
    asyncio.get_event_loop().run_forever()