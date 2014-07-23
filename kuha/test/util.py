import logging

class LogCapture(logging.Handler):
    """Context manager for capturing log output of a module."""

    def __init__(self, module, level=logging.DEBUG):
        self._module_name = module.__name__
        self.reset()
        super(LogCapture, self).__init__(level)

    def __enter__(self):
        logger = logging.getLogger(self._module_name)
        # Make sure that logging is enabled.
        logger.disabled = False
        logger.setLevel(self.level)
        logger.addHandler(self)
        return self

    def __exit__(self, *args):
        logger = logging.getLogger(self._module_name)
        logger.removeHandler(self)

    def assert_emitted(self, message):
        """Verify captured log output.

        Assert that the given message is part of the captured log.

        Parameters
        ----------
        message: str
            The expected log message.
        """
        output = '\n'.join(self.messages)
        assert message in output, \
            'Message "{0}" not found in "{1}"'.format(message, output)

    def emit(self, record):
        self.messages.append(record.getMessage())

    def reset(self):
        self.messages = []
