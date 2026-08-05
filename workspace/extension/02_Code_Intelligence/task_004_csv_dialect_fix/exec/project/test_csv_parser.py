import unittest

from csv_parser import parse_csv


class CsvParserTest(unittest.TestCase):
    def test_quoted_comma_and_escaped_quote(self):
        text = 'name,note\r\nA,"hello, world"\r\nB,"He said ""hi"""\r\n'
        self.assertEqual(
            parse_csv(text),
            [["name", "note"], ["A", "hello, world"], ["B", 'He said "hi"']],
        )

    def test_multiline_crlf_field(self):
        text = 'id,note\r\n1,"line one\r\nline two"\r\n2,end\r\n'
        self.assertEqual(
            parse_csv(text),
            [["id", "note"], ["1", "line one\r\nline two"], ["2", "end"]],
        )

    def test_blank_record_and_trailing_fields(self):
        self.assertEqual(
            parse_csv("a,b,\r\n\r\nc,,\r\n"),
            [["a", "b", ""], [], ["c", "", ""]],
        )

    def test_quote_inside_unquoted_field_is_literal(self):
        self.assertEqual(parse_csv('ab"cd",x\r\n'), [['ab"cd"', "x"]])


if __name__ == "__main__":
    unittest.main()
