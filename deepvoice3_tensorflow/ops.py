import tensorflow as tf
from tensorflow.python.ops.nn_ops import conv1d_transpose


def causal_conv(value, filter_, dilation, name='causal_conv'):
    '''

    :param value: (B, T, C)
    :param filter_: (filter_width, in_channels, out_channels)
    :param dilation:
    :param name:
    :return:
    '''
    with tf.name_scope(name):
        filter_width = tf.shape(filter_)[0]
        restored = tf.nn.convolution(value, filter_, padding='VALID', dilation_rate=[dilation])
        # Remove excess elements at the end.
        out_width = tf.shape(value)[1] - (filter_width - 1) * dilation
        # [batch, out_width, out_channels]
        result = tf.slice(restored, [0, 0, 0], [-1, out_width, -1])
        return result


def noncausal_conv(value, filter_, dilation):
    return tf.nn.convolution(value, filter_, padding='SAME', dilation_rate=[dilation])


def conv_transpose_1d(value, filter_, output_shape, stride, padding="SAME"):
    return conv1d_transpose(value, filter_, output_shape, stride, padding)


# ToDo: do not use tf.layers.Layer. see tf.nn.convolution.
class Conv1dIncremental(tf.layers.Layer):
    def __init__(self, weight, in_channels, out_channels, kernel_size, dilation=1, name="conv1d_incremental",
                 trainable=True, **kwargs):
        '''

        :param weight: (out_channels, in_channels, kernel_size)
        :param in_channels:
        :param out_channels:
        :param kernel_size:
        :param dilation:
        :param bias:
        :param name:
        :param trainable:
        :param kwargs:
        '''
        super(Conv1dIncremental, self).__init__(name=name, trainable=trainable, **kwargs)
        # (out_channels, in_channels, kernel_size)
        self.weight = weight
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.dilation = dilation

    def build(self, input_shape):
        # input: bsz x len x dim
        self.batch_size = input_shape[0]
        self.shape_c = input_shape[2]
        with tf.control_dependencies(
                [tf.assert_equal(tf.shape(self.weight), (self.out_channels, self.in_channels, self.kernel_size))]):
            super(Conv1dIncremental, self).build(input_shape)

    def call(self, inputs, input_buffer=None, training=False):
        # input: (B, T, C) where T=1
        if training:
            raise RuntimeError('Conv1dIncremental only supports eval mode')
        if input_buffer is None:
            raise ValueError("input_buffer tensor is required")
        input_buffer_shape = input_buffer.get_shape()

        dilation = self.dilation

        input_buffer = tf.slice(input_buffer, begin=[0, 1, 0], size=[-1, -1, -1])
        # append next input
        input_buffer = tf.concat(
            [input_buffer,
             tf.slice(inputs, begin=[0, tf.shape(inputs)[1] - 1, 0], size=[-1, -1, -1])],
            axis=1)
        input_buffer.set_shape(input_buffer_shape)
        next_input_buffer = input_buffer
        if dilation > 1:
            input_buffer = input_buffer[:, 0::dilation, :]

        # (out_channels, in_channels, dilation(kernel_size))
        weight = tf.transpose(self.weight, perm=[0, 2, 1])
        # (out_channels, dilation(kernel_size) * in_channels)
        weight = tf.reshape(weight, shape=[self.out_channels, -1])
        # (batch_size, dilation(kernel_size) * in_channels)
        inputs = tf.reshape(input_buffer, shape=[self.batch_size, -1])
        # (batch_size, out_channels)
        output = tf.matmul(inputs, tf.transpose(weight))
        # (batch_size, 1, out_channels)
        output = tf.reshape(output, shape=[self.batch_size, 1, -1])
        return output, next_input_buffer

    def initial_input_buffer(self):
        kw = self.kernel_size
        input_buffer = tf.zeros(shape=[self.batch_size, kw + (kw - 1) * (self.dilation - 1), self.shape_c])
        return input_buffer
