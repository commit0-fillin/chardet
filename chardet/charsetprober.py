import logging
import re
from .enums import ProbingState
INTERNATIONAL_WORDS_PATTERN = re.compile(b'[a-zA-Z]*[\x80-\xff]+[a-zA-Z]*[^a-zA-Z\x80-\xff]?')

class CharSetProber:
    SHORTCUT_THRESHOLD = 0.95

    def __init__(self, lang_filter=None):
        self._state = None
        self.lang_filter = lang_filter
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def filter_international_words(buf):
        """
        We define three types of bytes:
        alphabet: english alphabets [a-zA-Z]
        international: international characters [\x80-ÿ]
        marker: everything else [^a-zA-Z\x80-ÿ]
        The input buffer can be thought to contain a series of words delimited
        by markers. This function works to filter all words that contain at
        least one international character. All contiguous sequences of markers
        are replaced by a single space ascii character.
        This filter applies to all scripts which do not use English characters.
        """
        filtered = bytearray()
        i = 0
        while i < len(buf):
            if INTERNATIONAL_WORDS_PATTERN.match(buf[i:]):
                match = INTERNATIONAL_WORDS_PATTERN.match(buf[i:])
                filtered.extend(buf[i:i+match.end()])
                i += match.end()
            else:
                # If no match, it's a marker. Replace contiguous markers with a space.
                filtered.append(ord(' '))
                i += 1
                while i < len(buf) and not (buf[i] >= ord('a') and buf[i] <= ord('z')) and not (buf[i] >= ord('A') and buf[i] <= ord('Z')) and not (buf[i] >= 0x80 and buf[i] <= 0xFF):
                    i += 1
        return bytes(filtered)

    @staticmethod
    def remove_xml_tags(buf):
        """
        Returns a copy of ``buf`` that retains only the sequences of English
        alphabet and high byte characters that are not between <> characters.
        This filter can be applied to all scripts which contain both English
        characters and extended ASCII characters, but is currently only used by
        ``Latin1Prober``.
        """
        filtered = bytearray()
        in_tag = False
        for byte in buf:
            if byte == ord('<'):
                in_tag = True
            elif byte == ord('>'):
                in_tag = False
            elif not in_tag:
                if (byte >= ord('a') and byte <= ord('z')) or \
                   (byte >= ord('A') and byte <= ord('Z')) or \
                   (byte >= 0x80):
                    filtered.append(byte)
        return bytes(filtered)
