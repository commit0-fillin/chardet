"""
Module containing the UniversalDetector detector class, which is the primary
class a user of ``chardet`` should use.

:author: Mark Pilgrim (initial port to Python)
:author: Shy Shalom (original C code)
:author: Dan Blanchard (major refactoring for 3.0)
:author: Ian Cordasco
"""
import codecs
import logging
import re
from .charsetgroupprober import CharSetGroupProber
from .enums import InputState, LanguageFilter, ProbingState
from .escprober import EscCharSetProber
from .latin1prober import Latin1Prober
from .mbcsgroupprober import MBCSGroupProber
from .sbcsgroupprober import SBCSGroupProber
from .utf1632prober import UTF1632Prober

class UniversalDetector:
    """
    The ``UniversalDetector`` class underlies the ``chardet.detect`` function
    and coordinates all of the different charset probers.

    To get a ``dict`` containing an encoding and its confidence, you can simply
    run:

    .. code::

            u = UniversalDetector()
            u.feed(some_bytes)
            u.close()
            detected = u.result

    """
    MINIMUM_THRESHOLD = 0.2
    HIGH_BYTE_DETECTOR = re.compile(b'[\x80-\xff]')
    ESC_DETECTOR = re.compile(b'(\x1b|~{)')
    WIN_BYTE_DETECTOR = re.compile(b'[\x80-\x9f]')
    ISO_WIN_MAP = {'iso-8859-1': 'Windows-1252', 'iso-8859-2': 'Windows-1250', 'iso-8859-5': 'Windows-1251', 'iso-8859-6': 'Windows-1256', 'iso-8859-7': 'Windows-1253', 'iso-8859-8': 'Windows-1255', 'iso-8859-9': 'Windows-1254', 'iso-8859-13': 'Windows-1257'}

    def __init__(self, lang_filter=LanguageFilter.ALL):
        self._esc_charset_prober = None
        self._utf1632_prober = None
        self._charset_probers = []
        self.result = None
        self.done = None
        self._got_data = None
        self._input_state = None
        self._last_char = None
        self.lang_filter = lang_filter
        self.logger = logging.getLogger(__name__)
        self._has_win_bytes = None
        self.reset()

    def reset(self):
        """
        Reset the UniversalDetector and all of its probers back to their
        initial states.  This is called by ``__init__``, so you only need to
        call this directly in between analyses of different documents.
        """
        self.result = {'encoding': None, 'confidence': 0.0, 'language': None}
        self.done = False
        self._got_data = False
        self._input_state = InputState.PURE_ASCII
        self._last_char = b''
        self._has_win_bytes = False
        self._esc_charset_prober = None
        self._utf1632_prober = None
        self._charset_probers = []
        
        if self.lang_filter & LanguageFilter.CHINESE_SIMPLIFIED:
            self._charset_probers.append(GB2312Prober())
        if self.lang_filter & LanguageFilter.JAPANESE:
            self._charset_probers.append(EUCJPProber())
            self._charset_probers.append(SJISProber())
        if self.lang_filter & LanguageFilter.KOREAN:
            self._charset_probers.append(EUCKRProber())
        if self.lang_filter & LanguageFilter.NON_CJK:
            self._charset_probers.append(Latin1Prober())
        
        self._utf1632_prober = UTF1632Prober()
        self._esc_charset_prober = EscCharSetProber()

    def feed(self, byte_str):
        """
        Takes a chunk of a document and feeds it through all of the relevant
        charset probers.

        After calling ``feed``, you can check the value of the ``done``
        attribute to see if you need to continue feeding the
        ``UniversalDetector`` more data, or if it has made a prediction
        (in the ``result`` attribute).

        .. note::
           You should always call ``close`` when you're done feeding in your
           document if ``done`` is not already ``True``.
        """
        if self.done:
            return

        if not len(byte_str):
            return

        if not self._got_data:
            self._got_data = True
            if byte_str.startswith(codecs.BOM_UTF8):
                self.result = {'encoding': 'UTF-8-SIG', 'confidence': 1.0, 'language': ''}
                self.done = True
                return

        for prober in [self._utf1632_prober, self._esc_charset_prober] + self._charset_probers:
            if prober.feed(byte_str) == ProbingState.FOUND_IT:
                self.result = {'encoding': prober.charset_name,
                               'confidence': prober.get_confidence(),
                               'language': prober.language}
                self.done = True
                return

        if self._input_state == InputState.PURE_ASCII:
            if self.HIGH_BYTE_DETECTOR.search(byte_str):
                self._input_state = InputState.HIGH_BYTE
            elif self._input_state == InputState.PURE_ASCII and self.ESC_DETECTOR.search(self._last_char + byte_str):
                self._input_state = InputState.ESC_ASCII

        self._last_char = byte_str[-1:]

        if self._input_state == InputState.ESC_ASCII:
            if not self._esc_charset_prober:
                self._esc_charset_prober = EscCharSetProber()
            if self._esc_charset_prober.feed(byte_str) == ProbingState.FOUND_IT:
                self.result = {'encoding': self._esc_charset_prober.charset_name,
                               'confidence': self._esc_charset_prober.get_confidence(),
                               'language': self._esc_charset_prober.language}
                self.done = True
        elif self._input_state == InputState.HIGH_BYTE:
            if not self._charset_probers:
                self._charset_probers = [MBCSGroupProber(self.lang_filter)]
                self._charset_probers.append(SBCSGroupProber())
                self._charset_probers.append(Latin1Prober())
            for prober in self._charset_probers:
                if prober.feed(byte_str) == ProbingState.FOUND_IT:
                    self.result = {'encoding': prober.charset_name,
                                   'confidence': prober.get_confidence(),
                                   'language': prober.language}
                    self.done = True
                    return

        if self.WIN_BYTE_DETECTOR.search(byte_str):
            self._has_win_bytes = True

    def close(self):
        """
        Stop analyzing the current document and come up with a final
        prediction.

        :returns:  The ``result`` attribute, a ``dict`` with the keys
                   `encoding`, `confidence`, and `language`.
        """
        if self.done:
            return self.result
        if not self._got_data:
            self.logger.warning('no data received!')

        if self._input_state == InputState.PURE_ASCII:
            self.result = {'encoding': 'ascii', 'confidence': 1.0, 'language': ''}
            return self.result

        if self._input_state == InputState.HIGH_BYTE:
            probers = self._charset_probers + [self._utf1632_prober]
            prober_confidences = [(prober, prober.get_confidence()) for prober in probers]
            max_prober = max(prober_confidences, key=lambda x: x[1])
            
            if max_prober[1] > self.MINIMUM_THRESHOLD:
                charset_name = max_prober[0].charset_name
                lower_charset_name = charset_name.lower()
                confidence = max_prober[1]
                
                if self._has_win_bytes and lower_charset_name in self.ISO_WIN_MAP:
                    charset_name = self.ISO_WIN_MAP[lower_charset_name]
                    
                self.result = {'encoding': charset_name,
                               'confidence': confidence,
                               'language': max_prober[0].language}
            else:
                self.result = {'encoding': None, 'confidence': 0.0, 'language': None}

        elif self._input_state == InputState.ESC_ASCII:
            self.result = {'encoding': 'ascii', 'confidence': 1.0, 'language': ''}

        self.done = True
        return self.result
