"""Reference implementation for RFC 4180-style records."""

import csv
import io


def parse_csv(text):
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return list(csv.reader(io.StringIO(text, newline="")))
