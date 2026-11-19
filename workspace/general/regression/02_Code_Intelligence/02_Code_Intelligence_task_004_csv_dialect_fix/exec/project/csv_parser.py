"""Small CSV parser used by a Windows import path."""


def parse_csv(text):
    """Parse CSV text into a list of records."""
    rows = []
    for line in text.splitlines():
        if not line:
            continue
        fields = []
        current = []
        quoted = False
        for char in line:
            if char == '"':
                quoted = not quoted
            elif char == "," and not quoted:
                fields.append("".join(current))
                current = []
            else:
                current.append(char)
        if current:
            fields.append("".join(current))
        rows.append(fields)
    return rows
