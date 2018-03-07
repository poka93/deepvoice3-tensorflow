import tensorflow as tf
import numpy as np
from hypothesis import given, settings, unlimited, assume
from hypothesis.strategies import integers, composite
from hypothesis.extra.numpy import arrays
from deepvoice3_tensorflow.deepvoice3 import Decoder, MultiHopAttentionArgs

even_number = lambda x: x % 2 == 0


@composite
def query_tensor(draw, batch_size, c, t_size=integers(2, 20), elements=integers(-5, 5).filter(lambda x: x != 0)):
    t = draw(t_size)
    btc = draw(arrays(dtype=np.float32, shape=[batch_size, t, c], elements=elements))
    return btc


@composite
def memory_tensor(draw, batch_size, input_length=integers(5, 20),
                  embed_dim=integers(4, 20).filter(even_number), elements=integers(-5, 5)):
    il = draw(input_length)
    md = draw(embed_dim)
    t = draw(arrays(dtype=np.float32, shape=[batch_size, il, md], elements=elements))
    return t


@composite
def mha_arg(draw, out_channels, kernel_size=integers(2, 10), dilation=integers(1, 20)):
    ks = draw(kernel_size)
    dl = draw(dilation)
    return MultiHopAttentionArgs(out_channels, ks, dl, dropout=1.0, kernel_initializer_seed=123,
                                 weight_initializer_seed=456)


@composite
def all_args(draw, batch_size=integers(1, 3), query_channels=integers(2, 20).filter(even_number),
             in_dim=integers(2, 20), r=integers(1, 1)):
    bs = draw(batch_size)
    _in_dim = draw(in_dim)
    _r = draw(r)
    qc = draw(query_channels)
    query = draw(query_tensor(bs, _in_dim * _r))
    mha = draw(mha_arg(qc))
    memory = draw(memory_tensor(bs))
    return query, mha, memory, _in_dim, _r


class DecoderTest(tf.test.TestCase):

    @given(args=all_args(), num_preattention=integers(1, 1),
           num_mha=integers(1, 4))
    @settings(max_examples=3, timeout=unlimited)
    def test_decoder(self, args, num_preattention, num_mha):
        tf.set_random_seed(12345678)
        query, mha_arg, memory, in_dim, r = args
        batch_size = 1
        max_positions = 30
        T_query = query.shape[1]
        embed_dim = memory.shape[2]
        T_memory = memory.shape[1]
        assume(T_query < max_positions and T_memory < max_positions)
        preattention_in_features = r * in_dim
        preattention_args = ((preattention_in_features, mha_arg.out_channels),) * num_preattention
        decoder = Decoder(embed_dim, in_dim, r, max_positions, preattention=preattention_args,
                          mh_attentions=(mha_arg,) * num_mha,
                          dropout=1.0, is_incremental=False)

        decoder_online = Decoder(embed_dim, in_dim, r, max_positions, preattention=preattention_args,
                                 mh_attentions=(mha_arg,) * num_mha,
                                 dropout=1.0, max_decoder_steps=T_query, min_decoder_steps=T_query, is_incremental=True)

        frame_positions = tf.zeros(shape=(batch_size, T_query), dtype=tf.int32) + tf.range(0, T_query, dtype=tf.int32)
        text_positions = tf.zeros(shape=(batch_size, T_memory), dtype=tf.int32) + tf.range(0, T_memory, dtype=tf.int32)

        keys, values = tf.constant(memory), tf.constant(memory)
        out, done = decoder((keys, values), input=tf.constant(query),
                            frame_positions=frame_positions)

        out_online = decoder_online((keys, values),
                                    frame_positions=frame_positions, text_positions=text_positions, test_inputs=tf.constant(query))

        with self.test_session() as sess:
            sess.run(tf.global_variables_initializer())
            out = sess.run(out)
            print(out)
            out_online = sess.run(out_online)
            print(out_online)
            print("-" * 100)
            self.assertAllClose(out, out_online)

    @given(args=all_args(), num_preattention=integers(1, 1),
           num_mha=integers(1, 4))
    @settings(max_examples=3, timeout=unlimited)
    def test_decoder_inference(self, args, num_preattention, num_mha):
        query, mha_arg, memory, in_dim, r = args
        batch_size = 1
        max_positions = 30
        T_query = query.shape[1]
        embed_dim = memory.shape[2]
        T_memory = memory.shape[1]
        assume(T_query < max_positions and T_memory < max_positions)
        preattention_in_features = r * in_dim
        preattention_args = ((preattention_in_features, mha_arg.out_channels),) * num_preattention
        decoder_online = Decoder(embed_dim, in_dim, r, max_positions, preattention=preattention_args,
                                 mh_attentions=(mha_arg,) * num_mha,
                                 dropout=1.0, max_decoder_steps=T_query, min_decoder_steps=T_query, is_incremental=True)

        frame_positions = tf.zeros(shape=(batch_size, T_query), dtype=tf.int32) + tf.range(0, T_query, dtype=tf.int32)
        text_positions = tf.zeros(shape=(batch_size, T_memory), dtype=tf.int32) + tf.range(0, T_memory, dtype=tf.int32)

        keys, values = tf.constant(memory), tf.constant(memory)
        out_online = decoder_online((keys, values),
                                    frame_positions=frame_positions, text_positions=text_positions)

        with self.test_session() as sess:
            sess.run(tf.global_variables_initializer())
            out_online = sess.run(out_online)
            print(out_online)
            print("-" * 100)
