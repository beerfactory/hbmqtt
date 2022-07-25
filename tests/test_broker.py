# Copyright (c) 2015 Nicolas JOUANIN
#
# See the file license.txt for copying permission.
import asyncio
import logging
import unittest
from unittest.mock import patch, call, MagicMock

from hbmqtt.adapters import StreamReaderAdapter, StreamWriterAdapter
from hbmqtt.broker import (
    EVENT_BROKER_PRE_START,
    EVENT_BROKER_POST_START,
    EVENT_BROKER_PRE_SHUTDOWN,
    EVENT_BROKER_POST_SHUTDOWN,
    EVENT_BROKER_CLIENT_CONNECTED,
    EVENT_BROKER_CLIENT_DISCONNECTED,
    EVENT_BROKER_CLIENT_SUBSCRIBED,
    EVENT_BROKER_CLIENT_UNSUBSCRIBED,
    EVENT_BROKER_MESSAGE_RECEIVED,
    Broker)
from hbmqtt.client import MQTTClient, ConnectException
from hbmqtt.mqtt import (
    ConnectPacket, ConnackPacket, PublishPacket, PubrecPacket,
    PubrelPacket, PubcompPacket, DisconnectPacket)
from hbmqtt.mqtt.connect import ConnectVariableHeader, ConnectPayload
from hbmqtt.mqtt.constants import QOS_0, QOS_1, QOS_2


formatter = "[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"
logging.basicConfig(level=logging.DEBUG, format=formatter)
log = logging.getLogger(__name__)

test_config = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '127.0.0.1:1883',
            'max_connections': 10
        },
    },
    'sys_interval': 0,
    'auth': {
        'allow-anonymous': True,
    }
}

# monkey patch MagicMock
# taken from https://stackoverflow.com/questions/51394411/python-object-magicmock-cant-be-used-in-await-expression
async def async_magic():
    pass

MagicMock.__await__ = lambda x: async_magic().__await__()


class BrokerTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch('hbmqtt.broker.PluginManager')
    def test_start_stop(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                self.assertDictEqual(broker._sessions, {})
                self.assertIn('default', broker._servers)
                MockPluginManager.assert_has_calls(
                    [call().fire_event(EVENT_BROKER_PRE_START),
                     call().fire_event(EVENT_BROKER_POST_START)], any_order=True)
                MockPluginManager.reset_mock()
                await broker.shutdown()
                MockPluginManager.assert_has_calls(
                    [call().fire_event(EVENT_BROKER_PRE_SHUTDOWN),
                     call().fire_event(EVENT_BROKER_POST_SHUTDOWN)], any_order=True)
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_connect(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                client = MQTTClient()
                ret = await client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)
                self.assertIn(client.session.client_id, broker._sessions)
                await client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                self.assertDictEqual(broker._sessions, {})
                MockPluginManager.assert_has_calls(
                    [call().fire_event(EVENT_BROKER_CLIENT_CONNECTED, client_id=client.session.client_id),
                     call().fire_event(EVENT_BROKER_CLIENT_DISCONNECTED, client_id=client.session.client_id)],
                    any_order=True)
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_connect_will_flag(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())

                conn_reader, conn_writer = \
                    await asyncio.open_connection('127.0.0.1', 1883, loop=self.loop)
                reader = StreamReaderAdapter(conn_reader)
                writer = StreamWriterAdapter(conn_writer)

                vh = ConnectVariableHeader()
                payload = ConnectPayload()

                vh.keep_alive = 10
                vh.clean_session_flag = False
                vh.will_retain_flag = False
                vh.will_flag = True
                vh.will_qos = QOS_0
                payload.client_id = 'test_id'
                payload.will_message = b'test'
                payload.will_topic = '/topic'
                connect = ConnectPacket(vh=vh, payload=payload)
                await connect.to_stream(writer)
                await ConnackPacket.from_stream(reader)

                await asyncio.sleep(0.1)

                disconnect = DisconnectPacket()
                await disconnect.to_stream(writer)

                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                self.assertDictEqual(broker._sessions, {})
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_connect_clean_session_false(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                client = MQTTClient(client_id="", config={'auto_reconnect': False})
                return_code = None
                try:
                    await client.connect('mqtt://127.0.0.1/', cleansession=False)
                except ConnectException as ce:
                    return_code = ce.return_code
                self.assertEqual(return_code, 0x02)
                self.assertNotIn(client.session.client_id, broker._sessions)
                await client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_subscribe(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                client = MQTTClient()
                ret = await client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)
                await client.subscribe([('/topic', QOS_0)])

                # Test if the client test client subscription is registered
                self.assertIn('/topic', broker._subscriptions)
                subs = broker._subscriptions['/topic']
                self.assertEqual(len(subs), 1)
                (s, qos) = subs[0]
                self.assertEqual(s, client.session)
                self.assertEqual(qos, QOS_0)

                await client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                MockPluginManager.assert_has_calls(
                    [call().fire_event(EVENT_BROKER_CLIENT_SUBSCRIBED,
                                       client_id=client.session.client_id,
                                       topic='/topic', qos=QOS_0)], any_order=True)
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_subscribe_twice(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                client = MQTTClient()
                ret = await client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)
                await client.subscribe([('/topic', QOS_0)])

                # Test if the client test client subscription is registered
                self.assertIn('/topic', broker._subscriptions)
                subs = broker._subscriptions['/topic']
                self.assertEqual(len(subs), 1)
                (s, qos) = subs[0]
                self.assertEqual(s, client.session)
                self.assertEqual(qos, QOS_0)

                await client.subscribe([('/topic', QOS_0)])
                self.assertEqual(len(subs), 1)
                (s, qos) = subs[0]
                self.assertEqual(s, client.session)
                self.assertEqual(qos, QOS_0)

                await client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                MockPluginManager.assert_has_calls(
                    [call().fire_event(EVENT_BROKER_CLIENT_SUBSCRIBED,
                                       client_id=client.session.client_id,
                                       topic='/topic', qos=QOS_0)], any_order=True)
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_unsubscribe(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                client = MQTTClient()
                ret = await client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)
                await client.subscribe([('/topic', QOS_0)])

                # Test if the client test client subscription is registered
                self.assertIn('/topic', broker._subscriptions)
                subs = broker._subscriptions['/topic']
                self.assertEqual(len(subs), 1)
                (s, qos) = subs[0]
                self.assertEqual(s, client.session)
                self.assertEqual(qos, QOS_0)

                await client.unsubscribe(['/topic'])
                await asyncio.sleep(0.1)
                self.assertEqual(broker._subscriptions['/topic'], [])
                await client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                MockPluginManager.assert_has_calls(
                    [
                        call().fire_event(EVENT_BROKER_CLIENT_SUBSCRIBED,
                                          client_id=client.session.client_id,
                                          topic='/topic', qos=QOS_0),
                        call().fire_event(EVENT_BROKER_CLIENT_UNSUBSCRIBED,
                                          client_id=client.session.client_id,
                                          topic='/topic')
                    ], any_order=True)
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_publish(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                pub_client = MQTTClient()
                ret = await pub_client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)

                ret_message = await pub_client.publish('/topic', b'data', QOS_0)
                await pub_client.disconnect()
                self.assertEqual(broker._retained_messages, {})

                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                MockPluginManager.assert_has_calls(
                    [
                        call().fire_event(EVENT_BROKER_MESSAGE_RECEIVED,
                                          client_id=pub_client.session.client_id,
                                          message=ret_message),
                    ], any_order=True)
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    #@patch('hbmqtt.broker.PluginManager')
    def test_client_publish_dup(self):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())

                conn_reader, conn_writer = \
                    await asyncio.open_connection('127.0.0.1', 1883, loop=self.loop)
                reader = StreamReaderAdapter(conn_reader)
                writer = StreamWriterAdapter(conn_writer)

                vh = ConnectVariableHeader()
                payload = ConnectPayload()

                vh.keep_alive = 10
                vh.clean_session_flag = False
                vh.will_retain_flag = False
                payload.client_id = 'test_id'
                connect = ConnectPacket(vh=vh, payload=payload)
                await connect.to_stream(writer)
                await ConnackPacket.from_stream(reader)

                publish_1 = PublishPacket.build('/test', b'data', 1, False, QOS_2, False)
                await publish_1.to_stream(writer)
                asyncio.ensure_future(PubrecPacket.from_stream(reader), loop=self.loop)

                await asyncio.sleep(2)

                publish_dup = PublishPacket.build('/test', b'data', 1, True, QOS_2, False)
                await publish_dup.to_stream(writer)
                await PubrecPacket.from_stream(reader)
                pubrel = PubrelPacket.build(1)
                await pubrel.to_stream(writer)
                await PubcompPacket.from_stream(reader)

                disconnect = DisconnectPacket()
                await disconnect.to_stream(writer)

                await asyncio.sleep(0.1)
                await broker.shutdown()
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_publish_invalid_topic(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                pub_client = MQTTClient()
                ret = await pub_client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)

                await pub_client.publish('/+', b'data', QOS_0)
                await asyncio.sleep(0.1)
                await pub_client.disconnect()

                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_publish_big(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                pub_client = MQTTClient()
                ret = await pub_client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)

                ret_message = await pub_client.publish('/topic', bytearray(b'\x99' * 256 * 1024), QOS_2)
                await pub_client.disconnect()
                self.assertEqual(broker._retained_messages, {})

                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                MockPluginManager.assert_has_calls(
                    [
                        call().fire_event(EVENT_BROKER_MESSAGE_RECEIVED,
                                          client_id=pub_client.session.client_id,
                                          message=ret_message),
                    ], any_order=True)
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_publish_retain(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())

                pub_client = MQTTClient()
                ret = await pub_client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)
                await pub_client.publish('/topic', b'data', QOS_0, retain=True)
                await pub_client.disconnect()
                await asyncio.sleep(0.1)
                self.assertIn('/topic', broker._retained_messages)
                retained_message = broker._retained_messages['/topic']
                self.assertEqual(retained_message.source_session, pub_client.session)
                self.assertEqual(retained_message.topic, '/topic')
                self.assertEqual(retained_message.data, b'data')
                self.assertEqual(retained_message.qos, QOS_0)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_publish_retain_delete(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())

                pub_client = MQTTClient()
                ret = await pub_client.connect('mqtt://127.0.0.1/')
                self.assertEqual(ret, 0)
                await pub_client.publish('/topic', b'', QOS_0, retain=True)
                await pub_client.disconnect()
                await asyncio.sleep(0.1)
                self.assertNotIn('/topic', broker._retained_messages)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_subscribe_publish(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                sub_client = MQTTClient()
                await sub_client.connect('mqtt://127.0.0.1')
                ret = await sub_client.subscribe([('/qos0', QOS_0), ('/qos1', QOS_1), ('/qos2', QOS_2)])
                self.assertEqual(ret, [QOS_0, QOS_1, QOS_2])

                await self._client_publish('/qos0', b'data', QOS_0)
                await self._client_publish('/qos1', b'data', QOS_1)
                await self._client_publish('/qos2', b'data', QOS_2)
                await asyncio.sleep(0.1)
                for qos in [QOS_0, QOS_1, QOS_2]:
                    message = await sub_client.deliver_message()
                    self.assertIsNotNone(message)
                    self.assertEqual(message.topic, '/qos%s' % qos)
                    self.assertEqual(message.data, b'data')
                    self.assertEqual(message.qos, qos)
                await sub_client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_subscribe_invalid(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                sub_client = MQTTClient()
                await sub_client.connect('mqtt://127.0.0.1')
                ret = await sub_client.subscribe(
                    [('+', QOS_0), ('+/tennis/#', QOS_0), ('sport+', QOS_0), ('sport/+/player1', QOS_0)])
                self.assertEqual(ret, [QOS_0, QOS_0, 0x80, QOS_0])

                await asyncio.sleep(0.1)
                await sub_client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_subscribe_publish_dollar_topic_1(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                sub_client = MQTTClient()
                await sub_client.connect('mqtt://127.0.0.1')
                ret = await sub_client.subscribe([('#', QOS_0)])
                self.assertEqual(ret, [QOS_0])

                await self._client_publish('/topic', b'data', QOS_0)
                message = await sub_client.deliver_message()
                self.assertIsNotNone(message)

                await self._client_publish('$topic', b'data', QOS_0)
                await asyncio.sleep(0.1)
                message = None
                try:
                    message = await sub_client.deliver_message(timeout=2)
                except Exception as e:
                    pass
                self.assertIsNone(message)
                await sub_client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_subscribe_publish_dollar_topic_2(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                sub_client = MQTTClient()
                await sub_client.connect('mqtt://127.0.0.1')
                ret = await sub_client.subscribe([('+/monitor/Clients', QOS_0)])
                self.assertEqual(ret, [QOS_0])

                await self._client_publish('/test/monitor/Clients', b'data', QOS_0)
                message = await sub_client.deliver_message()
                self.assertIsNotNone(message)

                await self._client_publish('$SYS/monitor/Clients', b'data', QOS_0)
                await asyncio.sleep(0.1)
                message = None
                try:
                    message = await sub_client.deliver_message(timeout=2)
                except Exception as e:
                    pass
                self.assertIsNone(message)
                await sub_client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    @patch('hbmqtt.broker.PluginManager')
    def test_client_publish_retain_subscribe(self, MockPluginManager):
        async def test_coro():
            try:
                broker = Broker(test_config, plugin_namespace="hbmqtt.test.plugins")
                await broker.start()
                self.assertTrue(broker.transitions.is_started())
                sub_client = MQTTClient()
                await sub_client.connect('mqtt://127.0.0.1', cleansession=False)
                ret = await sub_client.subscribe([('/qos0', QOS_0), ('/qos1', QOS_1), ('/qos2', QOS_2)])
                self.assertEqual(ret, [QOS_0, QOS_1, QOS_2])
                await sub_client.disconnect()
                await asyncio.sleep(0.1)

                await self._client_publish('/qos0', b'data', QOS_0, retain=True)
                await self._client_publish('/qos1', b'data', QOS_1, retain=True)
                await self._client_publish('/qos2', b'data', QOS_2, retain=True)
                await sub_client.reconnect()
                for qos in [QOS_0, QOS_1, QOS_2]:
                    log.debug("TEST QOS: %d" % qos)
                    message = await sub_client.deliver_message()
                    log.debug("Message: " + repr(message.publish_packet))
                    self.assertIsNotNone(message)
                    self.assertEqual(message.topic, '/qos%s' % qos)
                    self.assertEqual(message.data, b'data')
                    self.assertEqual(message.qos, qos)
                await sub_client.disconnect()
                await asyncio.sleep(0.1)
                await broker.shutdown()
                self.assertTrue(broker.transitions.is_stopped())
                future.set_result(True)
            except Exception as ae:
                future.set_exception(ae)

        future = asyncio.Future(loop=self.loop)
        self.loop.run_until_complete(test_coro())
        if future.exception():
            raise future.exception()

    async def _client_publish(self, topic, data, qos, retain=False):
        pub_client = MQTTClient()
        ret = await pub_client.connect('mqtt://127.0.0.1/')
        self.assertEqual(ret, 0)
        ret = await pub_client.publish(topic, data, qos, retain)
        await pub_client.disconnect()
        return ret
